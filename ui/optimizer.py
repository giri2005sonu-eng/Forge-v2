"""Project Optimizer panel (drawn inside the BOM page, below Component details). All numbers come from core.optimizer; this file only draws them."""
import copy
import datetime as dt
import streamlit as st
from core import auto_fix, bill, component_catalog as cat, optimizer as opt, pipeline
from core.data import PROJECTS, QTY

CSS = """<style>
/* Optimizer panel – premium dark tokens matching global FORGE theme */
.opt-sub{color:#64748B;margin:-6px 0 14px;font-size:.82rem;letter-spacing:.01em}

/* Status pills */
.pill{display:inline-block;padding:3px 12px;border-radius:99px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#fff}
.improved  {background:linear-gradient(135deg,#059669,#10B981);box-shadow:0 2px 8px rgba(16,185,129,.3)}
.reduced   {background:linear-gradient(135deg,#DC2626,#F43F5E);box-shadow:0 2px 8px rgba(244,63,94,.3)}
.unchanged {background:rgba(51,65,85,.9);border:1px solid rgba(71,85,105,.6)}
.incompatible{background:linear-gradient(135deg,#9F1239,#F43F5E);box-shadow:0 2px 8px rgba(244,63,94,.35)}
.unknown   {background:linear-gradient(135deg,#B45309,#F59E0B);box-shadow:0 2px 8px rgba(245,158,11,.3)}
.not_affected{background:rgba(30,41,59,.8);border:1px solid rgba(51,65,85,.5);color:#64748B}

/* Rule-check pills */
.PASS  {background:linear-gradient(135deg,#059669,#10B981);box-shadow:0 2px 8px rgba(16,185,129,.3)}
.FAIL  {background:linear-gradient(135deg,#DC2626,#F43F5E);box-shadow:0 2px 8px rgba(244,63,94,.3)}
.WARN  {background:linear-gradient(135deg,#B45309,#F59E0B);box-shadow:0 2px 8px rgba(245,158,11,.3)}
.UNKNOWN{background:linear-gradient(135deg,#B45309,#D97706);box-shadow:0 2px 8px rgba(245,158,11,.25)}

/* System impact chips */
.chip{display:inline-block;margin:3px 6px 3px 0;padding:5px 13px;border-radius:8px;font-size:12.5px;
      border:1px solid rgba(51,65,85,.5);background:rgba(15,23,42,.8);color:#CBD5E1;font-weight:500}
.chip.good{border-color:#10B981;background:rgba(16,185,129,.08);color:#6EE7B7}
.chip.bad {border-color:#F43F5E;background:rgba(244,63,94,.08);color:#FDA4AF}
.chip.warn{border-color:#F59E0B;background:rgba(245,158,11,.08);color:#FCD34D}

/* Quality badge */
.q{font-size:10px;padding:2px 9px;border-radius:99px;border:1px solid rgba(51,65,85,.5);color:#475569;
   background:rgba(15,23,42,.7);letter-spacing:.04em}
</style>"""
QUALITY = dict(typical="Typical data", estimated="Estimated", rules="Rule check", unavailable="No data yet", unverified="Unverified")
LABEL = dict(improved="Improved", reduced="Worse", unchanged="Unchanged", incompatible="Incompatible", unknown="Insufficient data", not_affected="Not affected")

def _fmt(r, v):
    if v is None: return "—"
    if r["key"] in ("bluetooth", "wifi"): return "Yes" if v else "No"
    if r["key"] == "cost": return bill.inr(v)
    return f"{v:,.2f} {r['unit']}".strip() if isinstance(v, (int, float)) else str(v)

def render(S, project, budget, bt, live):
    """S = st.session_state. Supports rule-checked builds, all 168 catalog projects, and custom builds."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.subheader("Project Optimizer")
    st.markdown("<div class='opt-sub'>Change any component. Understand the impact. Build smarter robots.</div>", unsafe_allow_html=True)
    res = S.get("res")
    custom = S.get("custom")
    if not (res and res.get("best")) and not custom:
        st.info("Generate a BOM first (back on the BOM page). The optimizer compares changes against that build."); return

    if res and res.get("best"):
        parts_map = res["best"]["parts"]
        label = PROJECTS.get(project, {}).get("label", str(project).replace("_", " ").title())
    else:
        parts_list = custom.get("parts", [])
        parts_map = {}
        for idx, p in enumerate(parts_list):
            r = p.get("role", "part")
            key = r if r not in parts_map else f"{r}_{p.get('id', idx)}"
            parts_map[key] = copy.deepcopy(p)
        label = custom.get("label") or str(project).replace("_", " ").title()

    records = cat.load()
    S.setdefault("opt_base", None); S.setdefault("opt_kept", {}); S.setdefault("opt_custom", {})
    S.setdefault("opt_standby_fixes", {})

    # Deduplicate S.opt_kept by part id to ensure no duplicated modules
    if S.get("opt_kept"):
        seen_ids = set()
        cleaned_kept = {}
        for k, p in S.opt_kept.items():
            if isinstance(p, dict) and p.get("id"):
                if p["id"] in seen_ids:
                    continue
                seen_ids.add(p["id"])
            cleaned_kept[k] = p
        S.opt_kept = cleaned_kept

    ident = (project, tuple(p.get("id", "") for p in parts_map.values()))
    if S.opt_base is None or S.get("opt_base_for") != ident:
        S.opt_base, S.opt_base_for, S.opt_kept = opt.snapshot(parts_map), ident, {}
        S.opt_standby_fixes = {}
    base = S.opt_base                                       # original configuration, never modified

    proj_info = PROJECTS.get(project, {})
    kind = proj_info.get("sensor")
    if not kind:
        for p in base.values():
            if isinstance(p, dict) and p.get("role") == "sensor" and p.get("kind"):
                kind = p["kind"]; break
    needs_bt = bt or proj_info.get("bt", False)
    if not needs_bt:
        for p in base.values():
            if isinstance(p, dict) and (p.get("specs", {}).get("bluetooth") or "bluetooth" in p.get("name", "").lower()):
                needs_bt = True; break

    current = dict(base)
    for r_k, p in S.opt_kept.items():
        if r_k in current:
            current = opt.replace(current, r_k, p)
        else:
            current[r_k] = copy.deepcopy(p)

    # Hybrid combination assessment (dataset -> Gemini fallback -> dynamic persistence)
    from core import combination_store
    combo_eval = combination_store.evaluate_combination_hybrid(current, project_label=label, budget=budget, live=live)
    if combo_eval.get("summary"):
        with st.expander("System Configuration Assessment (Hybrid Analyzer)", expanded=False):
            tag = "⚡ Rule Check" if combo_eval.get("source") == "rules" else "🧠 Gemini AI Review (Saved)" if combo_eval.get("source") == "gemini_learned" else "💾 Local Dataset (0 Gemini calls)"
            st.caption(f"Status: **{combo_eval.get('status', '').upper()}** · Source: `{tag}`")
            st.markdown(f"**Engineering summary:** {combo_eval.get('summary')}")
            for note in combo_eval.get("notes", []):
                st.markdown(f"- {note}")

    st.markdown("##### 1 · Current configuration")
    by = cat.by_legacy(records)
    with st.container(border=True):
        for role_key, p in current.items():
            if not isinstance(p, dict) or p.get("none"): continue
            role = p.get("role", role_key.split("_")[0])
            q = p.get("qty", QTY.get(role, 1))
            pr, src = pipeline.price_of(p, live); rec = by.get(p.get("id"))
            tag = f" · {rec['verification_status'].replace('_', ' ')}" if rec else " · not in verified catalog"
            kept = " · ✎ replaced" if role_key in S.opt_kept else ""
            st.markdown(f"**{p['name']}** · {role} × {q} · {bill.inr(pr * q)} (`{src}`){tag}{kept}")
            sp = ", ".join(f"{k}={v}" for k, v in (p.get("specs") or {}).items())
            if sp: st.caption(sp)

    st.markdown("##### 2 · Replace a component")
    roles = [r for r in base.keys() if isinstance(current.get(r), dict) and not current[r].get("none")]
    def _role_label(r):
        p = current.get(r, {})
        r_name = p.get("role", r.split("_")[0]).capitalize()
        p_name = p.get("name")
        return f"{r_name}: {p_name}" if p_name else r_name

    c1, c2, c3 = st.columns([1, 2, 2])
    role = c1.selectbox("Component", roles, format_func=_role_label, key="opt_role")
    cur = current[role]
    comp_role = cur.get("role", role.split("_")[0])
    cands = opt.candidates(base, comp_role, kind) + [p for p in S.opt_custom.get(role, []) if p["id"] not in {c["id"] for c in opt.candidates(base, comp_role, kind)}]
    names = {p["id"]: p["name"] for p in cands}
    picks = c2.multiselect("Alternatives to compare (against the ORIGINAL build)", [p["id"] for p in cands if p["id"] != base[role].get("id")],
                           format_func=names.get, key=f"opt_pick_{role}")
    goal = c3.selectbox("Optimization goal", list(opt.GOALS), format_func=opt.GOALS.get, key="opt_goal", index=0)
    with st.expander("Compare a part that is not in the list"):
        d1, d2 = st.columns([3, 1]); typed = d1.text_input("Part name (e.g. Arduino Due, DRV8871 driver)", key=f"opt_free_{role}", label_visibility="collapsed", placeholder="Part name, e.g. Arduino Due")
        if d2.button("Add", key=f"opt_free_add_{role}") and typed.strip():
            with st.spinner("Looking up impact data..."): found = opt.custom_part(comp_role, typed)
            if found: S.opt_custom.setdefault(role, []).append(found); S[f"opt_pick_{role}"] = list(S.get(f"opt_pick_{role}", [])) + [found["id"]]; st.rerun()
            else: st.info("No impact data for that part yet. Try the exact product name, or pick one from the list.")
    if not picks: st.caption("Pick one or more alternatives. Categories are filtered: only same-role parts are offered."); 
    pool = {p["id"]: p for p in cands}

    ranking = opt.rank_candidates(base, role, goal, records, live, needs_bt, kind)
    with st.expander(f"Goal check: {opt.GOALS[goal]}"):
        if not ranking["rankable"]: st.warning(ranking["note"])
        else:
            for i, o in enumerate(ranking["ranked"], 1): st.markdown(f"{i}. **{o['part']['name']}** · {bill.inr(o['cost'])} · {o['state']}")
            st.caption("Trade-offs are shown, not hidden: a lower-cost option may add warnings. See the dashboard below.")
        for o in ranking["incompatible"]:
            fails = [ck for ck in o["result"]["compat_proposed"] if ck["status"] == "FAIL"]
            reason_str = "; ".join(ck["explanation"] for ck in fails)
            st.markdown(f"✗ **{o['part']['name']}** fails a rule (still inspectable below)")
            if reason_str: st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;↳ **Reason:** {reason_str}")

    for pid in picks:
        new_part = pool[pid]
        proposed = opt.replace(base, role, new_part)
        staged_fixes = S.setdefault("opt_standby_fixes", {}).setdefault(pid, {})
        changed_roles = {role}
        for f_id, fix in list(staged_fixes.items()):
            f_part = copy.deepcopy(fix["part"])
            if fix.get("action") == "swap":
                swap_role = fix.get("swap_role", f_part.get("role"))
                proposed[swap_role] = f_part
                changed_roles.add(swap_role)
            else:
                role_key = f_part.get("role", "mod_" + f_id)
                if role_key in proposed:
                    role_key = f"{role_key}_{f_id}"
                f_part["role"] = role_key
                proposed[role_key] = f_part
                changed_roles.add(role_key)

        with st.spinner("Analysing impact..."):
            result = opt.compare_builds(base, proposed, changed_roles, records, live, needs_bt)
        sm = result["summary_proposed"]
        st.markdown("---")
        st.markdown(f"##### 3 · {base[role]['name']} → **{new_part['name']}**")
        badge = {"compatible": "PASS", "caution": "WARN", "incompatible": "FAIL"}[sm["state"]]
        st.markdown(f"<span class='pill {badge}'>{sm['state'].upper()}</span> {sm['fail']} fail · {sm['warn']} warning · {sm['unknown']} unknown · {sm['passed']} pass", unsafe_allow_html=True)

        if staged_fixes:
            for f_id, fix in list(staged_fixes.items()):
                sb_c1, sb_c2 = st.columns([5, 1])
                sb_c1.info(f"⚡ **Auto-Resolve on Standby:** `{fix['part']['name']}` ({bill.inr(fix['part'].get('seed_price', 0))}) is staged. Incompatibility resolved! Click **'Keep this replacement'** below to fetch live prices via TinyFish and add both to cart.")
                if sb_c2.button("✕ Remove", key=f"rm_standby_{pid}_{f_id}", help="Remove this staged fix"):
                    del S["opt_standby_fixes"][pid][f_id]
                    if not S["opt_standby_fixes"][pid]:
                        del S["opt_standby_fixes"][pid]
                    st.rerun()

        if not sm["ready"]:
            st.error("This is NOT a ready-to-build configuration: a compatibility rule fails. You can still inspect the numbers below.")
            fails = [ck for ck in result["compat_proposed"] if ck["status"] == "FAIL"]
            warns = [ck for ck in result["compat_proposed"] if ck["status"] == "WARN"]
            with st.expander("▼ Why did this build fail? (Click to view failure details)", expanded=True):
                for ck in fails:
                    st.markdown(f"**❌ {ck['title']}** (`{ck['components']}`)")
                    st.caption(f"**Reason:** {ck['explanation']}")
                    if ck.get("action"): st.caption(f"💡 **Suggested Fix:** {ck['action']}")
                    rule_key = ck.get("rule_id") or ck.get("id", "")
                    fixes = auto_fix.get_fixes_for_rule(rule_key, proposed)
                    if fixes:
                        st.markdown("**🔧 1-Click Auto-Resolve Actions:**")
                        btn_cols = st.columns(min(3, len(fixes)))
                        for f_idx, fix in enumerate(fixes):
                            with btn_cols[f_idx % len(btn_cols)]:
                                is_staged = fix["id"] in staged_fixes
                                btn_label = f"✓ {fix['label']} (Staged)" if is_staged else f"{fix['icon']} {fix['label']}"
                                if st.button(btn_label, key=f"opt_fix_{pid}_{rule_key}_{fix['id']}", help=fix["description"], disabled=is_staged):
                                    S.setdefault("opt_standby_fixes", {}).setdefault(pid, {})[fix["id"]] = copy.deepcopy(fix)
                                    st.success(f"Staged {fix['label']} on standby! Issue resolved.")
                                    st.rerun()
                if warns:
                    st.markdown("---")
                    st.caption("**Warnings / Cautions:**")
                    for ck in warns:
                        st.markdown(f"**⚠️ {ck['title']}** (`{ck['components']}`)")
                        st.caption(f"**Notice:** {ck['explanation']}")
                        if ck.get("action"): st.caption(f"💡 **Suggested Fix:** {ck['action']}")
                        rule_key = ck.get("rule_id") or ck.get("id", "")
                        fixes = auto_fix.get_fixes_for_rule(rule_key, proposed)
                        if fixes:
                            btn_cols = st.columns(min(3, len(fixes)))
                            for f_idx, fix in enumerate(fixes):
                                with btn_cols[f_idx % len(btn_cols)]:
                                    is_staged = fix["id"] in staged_fixes
                                    btn_label = f"✓ {fix['label']} (Staged)" if is_staged else f"{fix['icon']} {fix['label']}"
                                    if st.button(btn_label, key=f"opt_warn_fix_{pid}_{rule_key}_{fix['id']}", help=fix["description"], disabled=is_staged):
                                        S.setdefault("opt_standby_fixes", {}).setdefault(pid, {})[fix["id"]] = copy.deepcopy(fix)
                                        st.success(f"Staged: {fix['label']} on standby!")
                                        st.rerun()
        for side, r_, nm, (k, seed, ver) in result["conflicts"]:
            st.warning(f"Catalog correction ({side}): {nm} `{k}` is {seed} in FORGE's team seed, but official documentation says {ver}. The verified value is used.")
        rows = result["rows"]
        if result["chips"]:
            st.markdown("**What changes**")
            st.markdown("".join(f"<span class='chip {c['tone']}'>{c['text']}</span>" for c in result["chips"]), unsafe_allow_html=True)
        if result["data_gaps"]: st.caption("Some figures for " + ", ".join(result["data_gaps"]) + " are not available yet, so those rows show what is missing.")
        for r in rows:
            with st.container(border=True):
                a, b, c, d = st.columns([2, 2, 2, 2])
                a.markdown(f"**{r['metric']}**"); a.markdown(f"<span class='pill {r['status']}'>{LABEL[r['status']]}</span>", unsafe_allow_html=True)
                b.caption("Original"); b.markdown(_fmt(r, r["original"]))
                c.caption("Proposed"); c.markdown(_fmt(r, r["proposed"]))
                d.caption("Difference")
                d.markdown("—" if r["diff"] is None else f"{r['diff']:+,.2f} {r['unit']}".strip() + ("" if r["pct"] is None else f" ({r['pct']:+.1f}%)"))
                st.caption(r["reason"] + (f"  ·  {QUALITY.get(r['quality'], r['quality'])}" if r["quality"] not in ("n/a",) else ""))
        with st.expander("Compatibility rules and evidence"):
            for ck in result["compat_proposed"]:
                st.markdown(f"<span class='pill {ck['status']}'>{ck['status']}</span> **{ck['title']}** · {ck['components']}", unsafe_allow_html=True)
                if ck["status"] != "PASS": st.caption(ck["explanation"] + (f" **Do this:** {ck['action']}" if ck["action"] else ""))
            for role_, part in opt.effective(proposed, records).items():
                rec = by.get(part.get("id"))
                if rec:
                    for e in rec["specification_sources"]: st.caption(f"{part['name']} · {e['field']} = {e['value']} {e['unit']} · {e['document_title']} §{e['section']} · {e['source_url']} · {e['retrieved']}")
        with st.expander("Explanation of trade-offs"): st.text(opt.plain_explanation(result))
        b1, b2, b3 = st.columns([1, 1, 3])
        if b1.button("Keep this replacement", key=f"keep_{role}_{pid}", disabled=not sm["ready"] or new_part.get("seed_price") is None):
            with st.spinner("TinyFish: Fetching live prices and links for replacement & auto-fix parts..."):
                if pid and pid not in live:
                    try:
                        p_copy = copy.deepcopy(new_part)
                        p_copy.setdefault("query", p_copy.get("name", ""))
                        live[pid] = pipeline.source_part(p_copy, log=st.write)
                    except Exception as e:
                        st.caption(f"TinyFish quote for {new_part['name']}: {str(e)[:80]}")

                staged = S.get("opt_standby_fixes", {}).get(pid, {})
                for f_id, fix in staged.items():
                    f_part = fix["part"]
                    f_pid = f_part.get("id")
                    if f_pid and f_pid not in live:
                        try:
                            f_copy = copy.deepcopy(f_part)
                            f_copy.setdefault("query", f_copy.get("name", ""))
                            live[f_pid] = pipeline.source_part(f_copy, log=st.write)
                        except Exception as e:
                            st.caption(f"TinyFish quote for {f_part['name']}: {str(e)[:80]}")

            S.opt_kept[role] = copy.deepcopy(new_part)
            staged = S.get("opt_standby_fixes", {}).pop(pid, {})
            for f_id, fix in staged.items():
                f_part = copy.deepcopy(fix["part"])
                if fix.get("action") == "swap":
                    swap_role = fix.get("swap_role", f_part.get("role"))
                    S.opt_kept[swap_role] = f_part
                else:
                    existing_key = next((k for k, p in S.opt_kept.items() if isinstance(p, dict) and p.get("id") == f_part.get("id")), None)
                    if existing_key:
                        S.opt_kept[existing_key] = f_part
                    else:
                        role_key = f_part.get("role", "mod_" + f_id)
                        if role_key in S.opt_kept and S.opt_kept[role_key].get("id") != f_part.get("id"):
                            role_key = f"{role_key}_{f_id}"
                        f_part["role"] = role_key
                        S.opt_kept[role_key] = f_part

            st.success("Replaced component and committed auto-resolve part(s) with live pricing!")
            st.rerun()

        if b2.button("Find live price", key=f"live_{pid}", help="TinyFish Search + Fetch. Prices need a verified quote."):
            try:
                p_copy = copy.deepcopy(new_part)
                p_copy.setdefault("query", p_copy.get("name", ""))
                live[pid] = pipeline.source_part(p_copy, log=st.write)
                st.rerun()
            except Exception as e:
                st.warning(f"TinyFish unavailable: {str(e)[:120]}. The estimate stays labelled as an estimate.")

    st.markdown("##### 4 · Save and export")
    if S.opt_kept:
        st.success(f"✓ **{len(S.opt_kept)} replacement(s) applied to your final build!** See your single final bill below.")
        col_undo, col_pdf = st.columns([1, 2])
        if col_undo.button("Undo all replacements", key="undo_opt_replacements"):
            S.opt_kept = {}
            S.opt_standby_fixes = {}
            st.rerun()
        safe_slug = "".join(c for c in str(project).lower() if c.isalnum() or c == "_")
        B = bill.make(current, live, {}, budget, f"{label} (optimized)")
        col_pdf.download_button("Download final BOM as PDF", B["pdf"], file_name=f"forge_{safe_slug}_{B['ref'][3:11]}.pdf", mime="application/pdf", type="primary")
    else: st.caption("Keep a replacement above to apply it to your final build. The original build is untouched either way.")

