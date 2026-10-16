import streamlit as st

from core import bill, pipeline
from core.data import PROJECTS, QTY


def _label(project_key):
    return PROJECTS[project_key]["label"]


def _pick_offer(state, part_id, url):
    state.choice[part_id] = url


def render(state, tinyfish_enabled, gemini_enabled):
    if not (tinyfish_enabled and gemini_enabled):
        st.warning("Add TINYFISH_API_KEY and GEMINI_API_KEY to .env for live prices. Without them the app uses seed prices (labelled).")

    with st.container(border=True):
        project_col, budget_col, bluetooth_col = st.columns([2, 1, 1])
        project_keys = list(PROJECTS)
        robot = project_col.selectbox("Project", project_keys, index=project_keys.index(state.project), format_func=_label)
        budget = budget_col.number_input("Budget (₹)", 1000, 100000, state.budget, 500)
        bluetooth = bluetooth_col.toggle("Needs Bluetooth", value=PROJECTS[robot]["bt"])
        generate_col, help_col, _ = st.columns([1, 1, 3])
        if generate_col.button("Generate BOM"):
            state.project = robot
            state.res = pipeline.select(robot, budget, bluetooth or PROJECTS[robot]["bt"], state.live)
        if help_col.button("Help me choose"):
            state.stage = "pick"
            st.rerun()

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
    st.subheader(f"{_label(state.project)} · ₹{best['cost']:,.0f}")
    st.caption(f"Checked {result['evaluated']} combinations; {result['rejected']} rejected for failing a rule.")
    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        for role, part in best["parts"].items():
            if part.get("none"):
                continue
            price, source = pipeline.price_of(part, state.live)
            quantity = QTY.get(role, 1)
            st.markdown(f"**{part['name']}** · {role} × {quantity} · ₹{price * quantity:,.0f} · `{source} price`")
            warning = pipeline.spread_warning(state.live.get(part["id"], []))
            if warning:
                st.warning(warning)
            for offer in state.live.get(part["id"], []):
                if offer.get("price"):
                    st.caption(f"✓ ₹{offer['price']:,.0f} · {offer.get('name') or 'product name not verified'} · {offer['url']} — “{offer['quote'][:90]}”")
                else:
                    st.caption(f"Link found, price not verified: {offer['url']}")
    with right, st.container(border=True):
        st.markdown("**Compatibility checks**")
        for check in best["checks"]:
            st.markdown(f"<span class='b {check['status']}'>{check['status']}</span> {check['title']}", unsafe_allow_html=True)
            if check["status"] != "PASS":
                st.caption(check["msg"])

    if result["alternatives"]:
        with st.expander("Other valid builds"):
            for alternative in result["alternatives"]:
                names = ", ".join(part["name"] for part in alternative["parts"].values() if not part.get("none"))
                st.write(f"₹{alternative['cost']:,.0f} · {names}")

    st.divider()
    st.markdown("#### Live data from TinyFish")
    if st.button("Find live prices (TinyFish Search + Fetch)", disabled=not (tinyfish_enabled and gemini_enabled)):
        state.log = []

        def log(message):
            state.log.append(str(message))
            st.write(message)

        with st.status("Searching vendors and reading pages...", expanded=True) as status:
            for part in best["parts"].values():
                if part.get("none"):
                    continue
                try:
                    state.live[part["id"]] = pipeline.source_part(part, log=log)
                except Exception as error:
                    log(f"{part['name']}: {error}")
            status.update(label="Done. Prices with a verified quote are now used in the BOM.", state="complete")
        state.res = pipeline.select(state.project, budget, bluetooth or PROJECTS[state.project]["bt"], state.live)
        st.rerun()
    if state.log:
        with st.expander("Last TinyFish research log", expanded=True):
            for message in state.log:
                st.write(message)

    st.divider()
    st.markdown("#### Compare shops and build your bill")
    st.caption("Each row is a part of the build. The cheapest verified listing is ticked; tick another one to buy that instead. The bill below updates straight away.")
    if st.button("Reset to cheapest"):
        state.choice = {}
        st.rerun()
    columns = [1.7] + [1.35] * bill.MAX_OFFERS + [0.95]
    headers = st.columns(columns)
    for column, title in zip(headers, ["Part", "Cheapest", "Option 2", "Option 3", "Option 4", "Line total"]):
        column.caption(title)

    for role, part in best["parts"].items():
        if part.get("none"):
            continue
        offers = bill.offers_for(part["id"], state.live)
        quantity = QTY.get(role, 1)
        selected_url = bill.chosen_url(part["id"], state.live, state.choice)
        with st.container(border=True):
            offer_columns = st.columns(columns)
            offer_columns[0].markdown(f"**{bill.md_escape(part['name'])}**")
            offer_columns[0].caption(f"{role.capitalize()} × {quantity}")
            if not offers:
                offer_columns[1].markdown(f"**{bill.inr(part['seed_price'])}**")
                offer_columns[1].caption("Estimate, no verified shop price yet")
                line_total = part["seed_price"] * quantity
            for index, offer in enumerate(offers):
                key = f"pk_{part['id']}_{index}"
                state[key] = offer["url"] == selected_url
                offer_columns[1 + index].checkbox(
                    f"**{bill.inr(offer['price'])}**" + (" · cheapest" if index == 0 else ""),
                    key=key,
                    on_change=_pick_offer,
                    args=(state, part["id"], offer["url"]),
                )
                url = bill.safe_url(offer["url"])
                shop = bill.md_escape(bill.vendor(offer["url"]))
                details = bill.md_escape((offer.get("name") or "product name not verified")[:60])
                stock = "  \n:red[Out of stock]" if offer.get("in_stock") is False else ""
                link = f"[{shop}]({url})" if url else shop
                offer_columns[1 + index].caption(f"{link}  \n{details}{stock}")
            if offers:
                line_total = next(offer["price"] for offer in offers if offer["url"] == selected_url) * quantity
            offer_columns[-1].markdown(f"**{bill.inr(line_total)}**")
            unverified_count = len(bill.unverified_for(part["id"], state.live))
            if unverified_count:
                st.caption(f"{unverified_count} more link{'s' if unverified_count > 1 else ''} found without a verifiable price, so not offered here.")
            warning = pipeline.spread_warning(state.live.get(part["id"], []))
            if warning:
                st.warning(warning)

    invoice = bill.make(best["parts"], state.live, state.choice, budget, _label(state.project))
    st.markdown("#### Your bill")
    st.markdown(invoice["html"], unsafe_allow_html=True)
    st.download_button(
        "Download bill as PDF",
        invoice["pdf"],
        file_name=f"forge_bill_{state.project}_{invoice['ref'][3:11]}.pdf",
        mime="application/pdf",
        type="primary",
    )
    return {"best": best, "budget": budget, "bluetooth": bluetooth}