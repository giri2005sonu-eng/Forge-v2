import copy
import os
import re

import streamlit as st

from ui import delivery_panel, optimizer as optimizer_panel, wiring_panel
from core import auto_fix, bill, compatibility_engine as ce, custom_bom, hybrid_bom, ledger, pipeline, project_store
from core import kept as kept_mod
from core.data import PROJECTS, QTY
from core.recommendation_catalog import PROJECT_CATALOG


def _label(project_key):
    return PROJECTS[project_key]["label"]


def _pick_offer(state, part_id, url):
    state.choice[part_id] = url
    state.manual.pop(part_id, None)  # a verified listing replaces any unverified pick


def _toggle_unverified(state, part, offer, key):
    """Tick = the user wants this unverified listing; untick = back to the verified choice. Never set automatically."""
    current = state.manual.get(part["id"]) or {}
    if state[key]:
        keep = current.get("price") if current.get("url") == offer["url"] else 0.0
        state.manual[part["id"]] = dict(url=offer["url"], name=offer.get("name"), price=keep or 0.0)
    elif current.get("url") == offer["url"]:
        state.manual.pop(part["id"], None)


def _when(stamp):
    """ISO timestamp from the sourcing engine -> short text. Never invents a time."""
    return stamp.replace("T", " ")[:16] + " UTC" if stamp else "Not available"


def _price_status(offers, unverified):
    """(label, colour) for the collapsed card. Live = a price with a quote was read from a page."""
    if offers:
        return "LIVE PRICE", "green"
    return ("UNVERIFIED", "orange") if unverified else ("ESTIMATED", "gray")


def _badge(text, cls):
    return f"<span class='b {cls}'>{text}</span>"


def _offer_row(state, part, offer, index, selected_url, lowest_price):
    """One verified supplier row: price, store, listing name, evidence, link and the 'use this listing' tick."""
    key = f"pk_{part['id']}_{index}"
    state[key] = offer["url"] == selected_url  # keep the tick in step with the stored choice (same keys as before)
    name_ok = bool(offer.get("name"))
    badges = _badge("VERIFIED PRICE", "PASS")
    if offer["price"] == lowest_price:
        badges += " " + (_badge("LOWEST VERIFIED PRICE", "PASS") if name_ok else _badge("LOWEST PRICE · NAME NOT VERIFIED", "UNKNOWN"))
    if not name_ok:
        badges += " " + _badge("NAME NOT VERIFIED", "UNKNOWN")
    if offer.get("suspect"):
        badges += " " + _badge("UNUSUALLY LOW · CHECK", "FAIL")
    url = bill.safe_url(offer["url"])
    shop = bill.md_escape(bill.vendor(offer["url"]))
    with st.container(border=True):
        price_col, info_col, link_col = st.columns([1.2, 3, 1.2])
        price_col.markdown(f"**{bill.inr(offer['price'])}**")
        price_col.checkbox("Use this", key=key, on_change=_pick_offer, args=(state, part["id"], offer["url"]))
        info_col.markdown(f"**{shop}** · {bill.md_escape((offer.get('name') or 'Listing name not verified')[:90])}")
        info_col.markdown(badges, unsafe_allow_html=True)
        quote = offer.get("quote")
        info_col.caption(f"Evidence: “{bill.md_escape(quote[:140])}”" if quote else "Evidence quote: Not available")
        info_col.caption(f"Checked {_when(offer.get('checked_at'))} · Method: {bill.md_escape(offer.get('method') or 'Not available')}")
        if offer.get("note"):
            info_col.warning(offer["note"])
        if offer.get("suspect_note"):
            info_col.warning(offer["suspect_note"])
        link_col.markdown(f"[View product ↗]({url})" if url else "Link unavailable")


def _unverified_row(state, part, offer, index):
    """A listing whose price could not be confirmed. Never suggested; the user may still choose it and type the price they saw."""
    key = f"um_{part['id']}_{index}"
    current = state.manual.get(part["id"]) or {}
    picked = current.get("url") == offer["url"]
    state[key] = picked  # keep the tick in step with the stored pick
    url = bill.safe_url(offer["url"])
    shop = bill.md_escape(bill.vendor(offer["url"]))
    with st.container(border=True):
        info_col, link_col = st.columns([4, 1.2])
        info_col.markdown(f"**{shop}** · " + _badge("PRICE NOT VERIFIED", "UNKNOWN") + (" " + _badge("YOUR PICK", "UNKNOWN") if picked else ""), unsafe_allow_html=True)
        info_col.caption(bill.md_escape(offer["name"][:90]) if offer.get("name") else "Listing name: Not verified")
        if offer.get("note"):
            info_col.warning(offer["note"])
        info_col.checkbox("Use this listing anyway (I will enter the price)", key=key, on_change=_toggle_unverified, args=(state, part, offer, key))
        if picked:
            price = info_col.number_input("Price you saw on the page (₹)", min_value=0.0, max_value=10_000_000.0, step=1.0,
                                          value=float(current.get("price") or 0.0), key=f"up_{part['id']}_{index}")
            state.manual[part["id"]] = dict(current, price=price)
            if price > 0:
                info_col.caption("Counted in the bill as a price entered by you. It was not read or checked from the page.")
            else:
                info_col.caption("Enter the price to include this listing in the bill. Until then the verified choice is used.")
        link_col.markdown(f"[View product ↗]({url})" if url else "Link unavailable")


def _component_card(state, role, part, line):
    """One collapsed-by-default card per component; every supplier result lives inside its own card."""
    offers = bill.offers_for(part["id"], state.live)
    unverified = bill.unverified_for(part["id"], state.live)
    warning = pipeline.spread_warning(state.live.get(part["id"], []))
    status, colour = _price_status(offers, unverified)
    if line["source"] == "manual":
        status, colour = "YOUR PICK · PRICE ENTERED BY YOU", "orange"
    flag = " :orange[⚠]" if warning or any(o.get("note") for o in state.live.get(part["id"], [])) else ""
    title = (f"**{bill.md_escape(part['name'])}** · {role.upper()} · × {line['qty']} · "
             f"{bill.money(line['unit'])} · :{colour}[**{status}**]{flag}")
    with st.expander(title, expanded=False):
        if offers:
            # display order: lowest price first; equal prices fall back to store name so the order never flickers
            ordered = sorted(offers, key=lambda o: (o["price"], bill.vendor(o["url"]), o["url"]))
            selected_url = None if bill.manual_pick(part["id"], state.manual) else bill.chosen_url(part["id"], state.live, state.choice)
            st.markdown("**Verified prices · lowest first**")
            for index, offer in enumerate(ordered):
                lowest = min((o["price"] for o in ordered if not o.get("suspect")), default=ordered[0]["price"])
                _offer_row(state, part, offer, index, selected_url, lowest)
        elif part.get("seed_price") is None:
            st.caption("No verified shop price found yet. This part is not included in the total.")
        else:
            st.caption(f"No verified shop price yet. Using the team estimate of {bill.inr(part['seed_price'])} (not checked on any page).")
        if part.get("note"):
            st.caption(f"Engineering note (from the FORGE dataset, not verified): {bill.md_escape(part['note'])}")
        if part.get("why"):
            st.caption(f"Why Gemini suggested it: {bill.md_escape(part['why'])} (AI suggestion, not verified)")
        if warning:
            st.warning(warning)
        picked = state.manual.get(part["id"])
        if picked and not any(o["url"] == picked.get("url") for o in unverified):  # keep a chosen listing visible after a new search
            unverified = unverified + [dict(url=picked["url"], name=picked.get("name"), price=None)]
        if unverified:
            st.markdown("**Price not verified**")
            st.caption("These pages were found but no price could be confirmed from their text. They are never chosen for you, "
                       "but you can pick one yourself and enter the price you saw.")
            for index, offer in enumerate(unverified):
                _unverified_row(state, part, offer, index)
        if not state.live.get(part["id"]):
            st.caption("Run “Find live prices” to look for supplier listings.")


def _match_project(text):
    """Turn what the user typed into a BOM-supported project, or say honestly that the builder cannot do it yet."""
    text = str(text or "").strip()
    if not text:
        return dict(project=None, reason="Type what you want to build first.", similar=[])
    for key, project in PROJECTS.items():  # an exact project name always wins
        if text.casefold() == project["label"].casefold():
            return dict(project=key, reason="Exact match to a supported build.", similar=[])
    hit = pipeline.map_idea(text)
    if hit["project"]:
        return dict(hit, similar=[])
    words = {w for w in re.findall(r"[a-z0-9]{3,}", text.lower())}
    scored = []
    for item in PROJECT_CATALOG.values():
        if item["bom_supported"]:
            continue
        overlap = len(words & set(re.findall(r"[a-z0-9]{3,}", (item["label"] + " " + item["desc"]).lower())))
        if overlap:
            scored.append((-overlap, item["label"]))
    similar = [label for _, label in sorted(scored)[:3]]
    reason = ("The BOM builder only has parts and compatibility rules for " + ", ".join(p["label"] for p in PROJECTS.values())
              + ". Nothing there clearly matches your idea yet.")
    return dict(project=None, reason=reason + " " + hit["reason"], similar=similar)


def _bill_section(state, invoice, parts, file_tag):
    """Final bill, PDF download, Delivery Optimizer and evidence ledger. Shared by the rule-based build and the Gemini-planned custom build."""
    delivery_panel.render(state, parts, invoice["lines"], project_label=str(file_tag).replace("_", " ").title())
    st.markdown("#### Your bill")
    st.markdown(invoice["html"], unsafe_allow_html=True)
    st.download_button(
        "Download bill as PDF",
        invoice["pdf"],
        file_name=f"forge_bill_{file_tag}_{invoice['ref'][3:11]}.pdf",
        mime="application/pdf",
        type="primary",
    )

    rows = ledger.rows(parts, state.live, state.choice, state.manual)
    summary = ledger.summary(rows)
    with st.expander(f"Evidence ledger · {summary['verified']} verified · {summary['seed']} seed values · {summary['unverified']} unverified links"):
        st.caption("Every number in this BOM and where it came from. **verified** = quote read from the shop page (URL, time, method shown). "
                   "**seed** = typed in by the team, not checked on any page. Nothing here is guessed.")
        st.dataframe([{k: str(r.get(k, "")) for k in ledger.FIELDS} for r in rows], hide_index=True)
        st.download_button("Download evidence ledger (CSV)", ledger.to_csv(rows), file_name=f"forge_ledger_{file_tag}.csv", mime="text/csv")


def _fetch_prices(state, parts, origin, tinyfish_enabled, status):
    """TinyFish looks up every part (Search + Fetch + quote-checked price). Dataset/learned parts never use Gemini to read a page by default."""
    state.log = []

    def log(message):
        state.log.append(str(message))
        st.write(message)

    if not tinyfish_enabled:
        status.update(label="Components ready. Add TINYFISH_API_KEY to look up live prices.", state="complete")
        return
    status.update(label="TinyFish is searching vendors and reading pages...")
    gem = None if origin == "gemini" else int(os.getenv("FORGE_DATASET_GEMINI_FALLBACK", "0"))
    custom_bom.source_all(parts, state.live, log=log, gemini_max=gem, skip_done=True)
    status.update(label="Done. Prices with a verified quote are used in the bill.", state="complete")


def _show_plan(state, plan, idea, tinyfish_enabled):
    """A component list (dataset, learned or Gemini) is on screen: remember it and let TinyFish price it."""
    state.res = None
    state.custom_error, state.suggest = None, None
    state.custom = dict(idea=idea, label=plan["label"], parts=plan["parts"], notes=plan.get("notes", []), origin=plan["origin"], meta=plan)
    state.bom_origin = plan["origin"]
    if plan.get("software_only") or not plan["parts"]:
        return
    with st.status(f"{len(plan['parts'])} components listed. Fetching live prices...", expanded=True) as status:
        _fetch_prices(state, plan["parts"], plan["origin"], tinyfish_enabled, status)


def _fetch_rule_build_prices(state, project_id, budget, needs_bt, tinyfish_enabled):
    """Same live TinyFish panel as 'Plan new build', for the rule-checked builds of the dropdown.
    The compatible parts are chosen first (rules, no AI); TinyFish then prices exactly those parts, and the build is re-selected
    with the verified prices. Parts that already have listings are kept, so opening the same project again is quick."""
    best = (state.res or {}).get("best")
    if not tinyfish_enabled or not best:
        return
    parts = pipeline.candidate_parts(project_id)   # every candidate, not only the current winner, so the final comparison is fair
    if not parts:
        return
    with st.status(f"{len(parts)} candidate components.  Fetching live prices...", expanded=True) as status:
        _fetch_prices(state, parts, "rule", tinyfish_enabled, status)
    state.res = pipeline.select(project_id, budget, needs_bt, state.live)


def _open_catalog_project(state, key, budget, bluetooth, tinyfish_enabled):
    """Dropdown path: NO Gemini. Rule-checked builds use the rule builder; every other catalog project reads its own component list."""
    plan = project_store.get_plan(key)
    project_id = key.split(":", 1)[1]
    state.custom_error, state.suggest = None, None
    if key.startswith("general:") and project_id in PROJECTS:
        state.custom, state.project, state.bom_origin = None, project_id, "rule"
        needs_bt = bluetooth or PROJECTS[project_id]["bt"]
        state.res = pipeline.select(project_id, budget, needs_bt, state.live)
        _fetch_rule_build_prices(state, project_id, budget, needs_bt, tinyfish_enabled)
        return
    _show_plan(state, plan, plan["label"], tinyfish_enabled)


def _plan_new_idea(state, idea, budget, bluetooth, tinyfish_enabled, skip_local=False):
    """Free-text path: learned plans and the catalog first, Gemini only when both have nothing (and then it is saved)."""
    counter = state.setdefault("gemini_counter", {"n": 0})
    state.custom, state.custom_error, state.res = None, None, None
    try:
        with st.spinner("Checking what FORGE already knows..."):
            out = hybrid_bom.resolve(idea, budget, bluetooth, counter, skip_local=skip_local)
    except ValueError as error:
        state.custom_error, state.bom_origin = str(error), None
        return
    if out["origin"] == "rule":
        state.custom, state.project, state.bom_origin = None, out["project"], "rule"
        needs_bt = bluetooth or PROJECTS[out["project"]]["bt"]
        state.res = pipeline.select(out["project"], budget, needs_bt, state.live)
        _fetch_rule_build_prices(state, out["project"], budget, needs_bt, tinyfish_enabled)
        return
    if out["plan"] is None:  # similar catalog projects exist: ask before guessing (no Gemini spent yet)
        state.suggest = dict(idea=idea, items=out["suggestions"])
        state.bom_origin = None
        return
    _show_plan(state, out["plan"], idea, tinyfish_enabled)


def _optimizer_section(state, budget, bluetooth, rule_checked=True):
    """Separate 'Project Optimizer' button below Component details. Opens the swap/impact tool inline; the button toggles it."""
    st.markdown("---")
    is_open = bool(state.get("opt_open"))
    button_col, caption_col = st.columns([1, 3])
    if button_col.button("Close Project Optimizer" if is_open else "Project Optimizer", key="opt_toggle", use_container_width=True):
        state.opt_open = not is_open
        st.rerun()
    caption_col.caption("Change any component. Understand the impact. Build smarter robots.")
    if not is_open:
        return
    optimizer_panel.render(state, state.project, budget, bluetooth, state.live)



def _render_custom(state, tinyfish_enabled, budget):
    """Bill for an idea outside the rule-based builder: Gemini-named parts, TinyFish-verified prices, no compatibility rules."""
    custom = state.custom
    if not custom["parts"]:  # software-only catalog projects (simulators etc.)
        st.subheader(custom["label"])
        st.info("Software only: this project needs no hardware to buy. " + " ".join(custom.get("notes") or []))
        return None
    base_build = kept_mod.keyed_parts(custom["parts"])
    active = kept_mod.active_build(state, state.project, base_build)      # original parts + replacements kept in the Project Optimizer
    active_list = [p for p in active.values() if not p.get("none")]
    n_swaps = kept_mod.count(state, state.project, base_build)
    parts = kept_mod.by_id(active)
    shown_label = f"{custom['label']} (optimized)" if n_swaps else custom["label"]
    invoice = bill.make(parts, state.live, state.choice, budget, shown_label, manual=state.manual)
    totals, lines = invoice["tot"], invoice["lines"]
    line_for = {line["part_id"]: line for line in lines}

    st.subheader(f"{shown_label} · {bill.inr(totals['subtotal'])}")
    if n_swaps:
        st.success(f"This bill includes {n_swaps} replacement(s) you kept in the Project Optimizer. Open it and press 'Undo all replacements' to go back to the original parts.")
    origin = custom.get("origin", "gemini")
    meta = custom.get("meta") or {}
    st.caption({"dataset": "Component list from the FORGE catalog dataset (written by the team, no AI used), priced from shop pages read by TinyFish.",
                "learned": "Component list saved from an earlier Gemini plan (no new Gemini call), priced from shop pages read by TinyFish.",
                }.get(origin, "Custom build: components were named by Gemini and priced from shop pages read by TinyFish."))
    if meta.get("description"):
        st.write(meta["description"])
    if meta.get("competition_event"):
        st.info(f"Competition: {meta['competition_event']} · Requirements from the catalog: {meta['constraints']}. "
                "These are requirements to design against, not proof that any listed part meets them.")
    if meta.get("safety"):
        st.warning("Safety tags: " + ", ".join(t.replace("_", " ") for t in meta["safety"]))
    if origin in ("dataset", "learned"):
        st.caption("Draft component list: names and quantities are proposed, not verified for compatibility. Spec values are typical datasheet numbers for the common hobby part, not verified for your exact listing (use Check specs).")
    count_col, cost_col, status_col = st.columns(3)
    count_col.metric("Components", len(lines))
    cost_col.metric("Estimated BOM cost", bill.inr(totals["subtotal"]))
    status_col.metric("Sourcing", f"{totals['n_live']} of {len(lines)} live-priced",
                      help="Live = a price with a quote was read from a shop page. Parts with no verified price are left out of the total.")
    if totals["n_missing"]:
        st.warning(f"{totals['n_missing']} of {len(lines)} parts have no verified price, so the total above is incomplete.")
    if meta.get("catalog_cost_inr"):
        st.caption(f"For comparison, the project catalog lists a rough cost of {bill.inr(meta['catalog_cost_inr'])} (an estimate, not a quote).")
    st.info("Compatibility is NOT rule-checked for custom builds: this app has no verified rules for these parts. Check the points below before buying.")
    if custom.get("notes"):
        with st.expander("Things to verify yourself (not rule-checked)", expanded=True):
            for note in custom["notes"]:
                st.markdown(f"- {bill.md_escape(note)}")

    if st.button("Search prices again (TinyFish)", disabled=not tinyfish_enabled):
        state.log = []

        def log(message):
            state.log.append(str(message))
            st.write(message)

        with st.status("Searching vendors and reading pages...", expanded=True) as status:
            custom_bom.source_all(active_list, state.live, log=log, gemini_max=None if origin == "gemini" else int(os.getenv("FORGE_DATASET_GEMINI_FALLBACK", "0")))
            status.update(label="Done.", state="complete")
        st.rerun()
    if state.log:
        with st.expander("Last TinyFish research log", expanded=False):
            for message in state.log:
                st.write(message)

    st.markdown("#### Component details")
    st.caption("Open a component to see its supplier results and evidence. The cheapest verified listing is used unless you tick another.")
    if st.button("Reset to cheapest"):
        state.choice, state.manual = {}, {}
        st.rerun()
    for part in active_list:
        if part["id"] in line_for:
            _component_card(state, part["role"], part, line_for[part["id"]])
    _optimizer_section(state, budget, False, rule_checked=True)
    wiring_panel.render(state, active_list, project_label=custom["label"])
    _bill_section(state, invoice, parts, "custom")
    return {"parts": parts, "label": shown_label, "custom": True, "budget": budget, "bluetooth": False}


def render(state, tinyfish_enabled, gemini_enabled):
    """Draw the BOM screen. Returns {"best", "budget", "bluetooth"} once a build exists, else None."""
    if not tinyfish_enabled:
        st.warning("Add TINYFISH_API_KEY to .env for live prices. Without it the app uses seed prices (labelled).")
    elif not gemini_enabled:
        st.info("No GEMINI_API_KEY: live prices still work (read from the page text by rules). Gemini only adds a backup for pages the rules cannot read.")

    options = project_store.options()
    labels = {o["key"]: f"{o['label']}  ·  {o['group']}" for o in options}
    state.setdefault("bom_catalog_pick", f"general:{state.project}")
    if state.bom_catalog_pick not in labels:
        state.bom_catalog_pick = options[0]["key"]
    counter = state.setdefault("gemini_counter", {"n": 0})
    with st.container(border=True):
        budget_col, bluetooth_col = st.columns([1, 1])
        budget = budget_col.number_input("Budget (₹)", 1000, 100000, state.budget, 500)
        bluetooth = bluetooth_col.toggle("Needs Bluetooth", value=PROJECTS[state.project]["bt"])
        st.markdown("**1 · Select Architecture from Catalog** (168 pre-verified component lists)")
        pick_col, go_col = st.columns([4, 1])
        pick_col.selectbox("Project", [o["key"] for o in options], key="bom_catalog_pick", format_func=labels.get, label_visibility="collapsed")
        auto_open = state.pop("auto_open_catalog", False)  # arriving from a recommendation: open that project straight away
        if go_col.button("Generate BOM", use_container_width=True) or auto_open:
            _open_catalog_project(state, state.bom_catalog_pick, budget, bluetooth, tinyfish_enabled)
        st.markdown("**2 · Or Ideate & Plan Custom Build** (Autonomous Copilot Architecture)")
        idea_col, plan_col = st.columns([4, 1])
        idea = idea_col.text_input("New idea", key="bom_new_idea", label_visibility="collapsed",
                                   placeholder="e.g. a plant-watering robot, or a drone with 4 motors")
        if plan_col.button("Plan new build", use_container_width=True):
            _plan_new_idea(state, idea, budget, bluetooth, tinyfish_enabled)
        suggest = state.get("suggest")
        if suggest:
            st.info("Similar projects are already in the catalog. Using one costs no Gemini call:")
            for index, (key, label, score) in enumerate(suggest["items"]):
                if st.button(f"Use “{label}”", key=f"sg_{index}"):
                    _open_catalog_project(state, key, budget, bluetooth, tinyfish_enabled)
                    st.rerun()
            if st.button("None of these: plan my idea with Gemini", key="sg_gemini"):
                _plan_new_idea(state, suggest["idea"], budget, bluetooth, tinyfish_enabled, skip_local=True)
                st.rerun()
        if state.get("custom_error"):
            st.error(state.custom_error)
        origin_note = {"rule": "Rule-checked build: parts chosen by the compatibility rules (no AI).",
                       "dataset": "Component list read from the FORGE dataset. No Gemini call.",
                       "learned": "Reused a plan Gemini made earlier for this idea. No new Gemini call.",
                       "gemini": "Gemini planned this once. It is now saved, so the same idea is free next time."}.get(state.get("bom_origin"))
        if origin_note:
            st.success(origin_note)
        st.caption(f"Gemini plans this session: {counter['n']} of {hybrid_bom.gemini_cap()} · ideas saved for reuse: {project_store.learned_count()}")
        help_col, _ = st.columns([1, 4])
        if help_col.button("Help me choose"):
            state.stage = "pick"
            st.rerun()

    if state.get("custom") and not state.res:
        return _render_custom(state, tinyfish_enabled, budget)

    result = state.res
    if result and not result["best"]:
        st.error(
            f"No fully compatible build fits ₹{budget:,.0f}. {result['rejected']} of {result['evaluated']} "
            "combinations failed a rule. Raise the budget or relax a requirement."
        )
        return None
    if not result:
        return None

    best = result["best"]

    # Sanitize state.opt_kept to remove any duplicate part IDs
    if state.get("opt_kept"):
        seen_ids = set()
        cleaned_kept = {}
        for k, p in state.opt_kept.items():
            if isinstance(p, dict) and p.get("id"):
                if p["id"] in seen_ids:
                    continue
                seen_ids.add(p["id"])
            cleaned_kept[k] = p
        state.opt_kept = cleaned_kept

    # Final active parts = this build + the replacements kept for THIS build (a swap kept on another project never applies here)
    active_parts = kept_mod.active_build(state, state.project, best["parts"])
    n_swaps = kept_mod.count(state, state.project, best["parts"])

    project_title = f"{_label(state.project)} (optimized)" if n_swaps else _label(state.project)
    invoice = bill.make(active_parts, state.live, state.choice, budget, project_title, manual=state.manual)
    totals, lines = invoice["tot"], invoice["lines"]
    line_for = {line["part_id"]: line for line in lines}

    # ---------------- 1. summary ----------------
    st.subheader(f"{project_title} · {bill.inr(totals['subtotal'])}")
    st.caption(f"Checked {result['evaluated']} combinations; {result['rejected']} rejected for failing a rule.")
    n_parts = len(lines)
    count_col, cost_col, status_col = st.columns(3)
    count_col.metric("Components", n_parts)
    cost_col.metric("Estimated BOM cost", bill.inr(totals["subtotal"]))
    status_col.metric("Sourcing", f"{totals['n_live']} of {n_parts} live-priced",
                      help="Live = a price with a quote was read from a shop page. The rest use the team's seed estimate.")

    if st.button("Find live prices (TinyFish Search + Fetch)", disabled=not tinyfish_enabled):
        state.log = []

        def log(message):
            state.log.append(str(message))
            st.write(message)

        with st.status("Searching vendors and reading pages...", expanded=True) as status:
            for part in pipeline.candidate_parts(state.project):
                try:
                    state.live[part["id"]] = pipeline.source_part(part, log=log)
                except Exception as error:
                    log(f"{part['name']}: {error}")
            status.update(label="Done. Prices with a verified quote are now used in the BOM.", state="complete")
        state.res = pipeline.select(state.project, budget, bluetooth or PROJECTS[state.project]["bt"], state.live)
        st.rerun()
    st.caption("Prices are read from each page's text first (free). Gemini is only a capped backup for pages that cannot be read, so a missing or rate-limited Gemini key does not stop this.")
    if state.log:
        with st.expander("Last TinyFish research log", expanded=False):
            for message in state.log:
                st.write(message)

    # ---------------- 2. component details ----------------
    st.markdown("#### Component details")
    st.caption("Open a component to see its supplier results, evidence and warnings. The cheapest verified listing is used unless you tick another.")
    if st.button("Reset to cheapest"):
        state.choice, state.manual = {}, {}
        st.rerun()
    for role, part in active_parts.items():
        if not isinstance(part, dict) or part.get("none"):
            continue
        p_id = part.get("id", "")
        if p_id in line_for:
            _component_card(state, role, part, line_for[p_id])

    _optimizer_section(state, budget, bluetooth, rule_checked=True)
    wiring_panel.render(state, active_parts, project_label=project_title)

    # ---------------- 3. compatibility summary ----------------
    st.markdown("#### Compatibility")
    checks = best["checks"]
    counts = {name: sum(c["status"] == name for c in checks) for name in ("PASS", "UNKNOWN", "FAIL")}
    st.markdown(" ".join(_badge(f"{n} {name}", name) for name, n in counts.items()), unsafe_allow_html=True)
    passed = [c["title"] for c in checks if c["status"] == "PASS"]
    if passed:
        st.caption("Passed: " + " · ".join(passed))
    for check in checks:
        if check["status"] != "PASS":  # failures and unknowns stay visible, never hidden inside a card
            st.markdown(f"{_badge(check['status'], check['status'])} {check['title']}", unsafe_allow_html=True)
            st.caption(check["msg"])
            rule_key = check.get("id") or check.get("rule_id", "")
            fixes = auto_fix.get_fixes_for_rule(rule_key, best["parts"])
            if fixes:
                btn_cols = st.columns(min(3, len(fixes)))
                for f_idx, fix in enumerate(fixes):
                    with btn_cols[f_idx % len(btn_cols)]:
                        if st.button(f"{fix['icon']} {fix['label']}", key=f"fix_bom_{rule_key}_{fix['id']}", help=fix["description"]):
                            updated = auto_fix.apply_auto_fix(best["parts"], fix["id"])
                            best["parts"] = updated
                            best["checks"] = ce.check(best["parts"], needs_bt=bluetooth)
                            st.success(f"Applied: {fix['label']}! Re-checked compatibility.")
                            st.rerun()
    if result["alternatives"]:
        with st.expander("Other valid builds"):
            for alternative in result["alternatives"]:
                names = ", ".join(part["name"] for part in alternative["parts"].values() if not part.get("none"))
                st.write(f"₹{alternative['cost']:,.0f} · {names}")

    _bill_section(state, invoice, active_parts, state.project)

    return {"best": best, "budget": budget, "bluetooth": bluetooth}
