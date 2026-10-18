"""Cart check (opt-in). Opens the listing you chose in the bill, adds ONE unit to the cart and reads the cart, then compares what the shop shows with
what our bill predicted. robu.in and robocraze.com go through the TinyFish Browser (fixed Playwright script, never checks out by construction);
any other shop, or a failed browser run, goes through the TinyFish Web Agent (USES CREDITS; told never to check out, an instruction not a technical block)."""
import streamlit as st

from core import bill, browser_cart, tf

MAX_STEPS = 12   # hard cap passed to the agent: about 12 credits per run at TinyFish's published 1 credit per step (check your dashboard)


def options(parts, live, choice):
    """{label: (url, expected_unit_price)} for every part whose bill line uses a verified listing."""
    out = {}
    for p in parts.values():
        if p.get("none"): continue
        url = bill.chosen_url(p["id"], live, choice or {})
        offer = next((o for o in bill.offers_for(p["id"], live) if o["url"] == url), None) if url else None
        if offer: out[f"{p['name']} · {bill.vendor(url)}"] = (url, float(offer["price"]))
    return out


def compare(expected, result, tol=0.02):
    """Pure check of the agent's answer against the bill. Returns (status, message); status is match | differs | not read | not added."""
    r = (result or {}).get("result") or {}
    if r.get("added_to_cart") is False:
        if r.get("in_stock") is False:
            return "not added", "Nothing was added to the cart: the shop's product page shows this item as out of stock. The listed price may still be right, but you cannot buy it right now. Check availability before ordering."
        return "not added", "Nothing could be added to the cart (the item may be unavailable or need a choice we did not make, such as a variant)."
    got = r.get("unit_price_inr")
    if not isinstance(got, (int, float)) or isinstance(got, bool) or got <= 0: return "not read", "The agent did not report a unit price."
    if abs(got - expected) <= max(2.0, tol * expected): return "match", f"Cart unit price {bill.inr(got)} matches the bill ({bill.inr(expected)})."
    return "differs", f"Cart unit price {bill.inr(got)} differs from the bill ({bill.inr(expected)}). Trust the shop's cart and recheck the listing."


def run(state, url):
    """One agent run (cached by tf.agent; failed runs are not cached). Errors are stored, never raised into the UI."""
    store = state.setdefault("agent", {})
    try: store[url] = browser_cart.check(url, agent=lambda u: tf.agent(u, max_steps=MAX_STEPS))
    except Exception as e: store[url] = dict(status="ERROR", error=str(e)[:200])
    return store[url]


def executor_line(res):
    """One line saying who did the check, e.g. '🌐 Executed by the TinyFish Browser'. Fallbacks say why; agent runs say which limits really applied."""
    m = res.get("method")
    if not m: return ""
    line = f"{browser_cart.icon(m)} Executed by the {browser_cart.label(m)}" + (f" (fallback: {res['fallback_reason']})" if res.get("fallback_reason") else "")
    if m == "agent" and "mode" in res:
        notes = []
        if res.get("mode") == "default": notes.append("default mode, because strict mode is not enabled on this TinyFish account")
        if res.get("step_cap") is None: notes.append(f"NO step cap, because this TinyFish account cannot set one; it used {res.get('num_of_steps', 'n/a')} steps")
        if res.get("time_cap") is None: notes.append("no time cap either")
        if notes: line += " · " + "; ".join(notes)
    return line


def render(state, build, tinyfish_enabled):
    parts = build["parts"] if build.get("custom") else build["best"]["parts"]
    opts = options(parts, state.get("live", {}), state.get("choice", {}))
    with st.container(border=True):
        st.markdown("**Cart check** · TinyFish Browser for robu.in and robocraze.com, Web Agent for other shops")
        st.caption("Opens the listing you chose in the bill, adds ONE unit to the cart and reads the cart. "
                   "🌐 **Browser** (robu.in, robocraze.com): a TinyFish cloud browser driven by a fixed script that only opens the page, clicks Add to cart and opens the cart. It never types anything and never reaches checkout. "
                   f"🤖 **Web Agent** (every other shop, or if the browser run fails): AI-driven, told never to check out or enter details (an instruction, not a technical block, so use public shop pages only), asks for a cap of {MAX_STEPS} steps and 180 s, which some TinyFish accounts cannot set (the result then says so), uses credits. "
                   "Repeat runs are cached and free.")
        if not opts:
            st.caption("Get verified live prices first. The cart check only runs on listings whose price was read from the page.")
            return
        tagged = {f"{browser_cart.icon(browser_cart.route(u))} {k}  [{browser_cart.label(browser_cart.route(u)).replace('TinyFish ', '')}]": (u, e) for k, (u, e) in opts.items()}
        label = st.selectbox("Listing to check", list(tagged), key="cart_check_pick")
        url, expected = tagged[label]
        who = browser_cart.label(browser_cart.route(url))
        if st.button("Run cart check", disabled=not tinyfish_enabled, key="cart_check_run"):
            with st.spinner(f"{who} running..."): run(state, url)
        res = state.get("agent", {}).get(url)
        if res:
            if res.get("error") or str(res.get("status", "")).upper().startswith("ERR"):
                st.warning(f"Cart check failed: {bill.md_escape(str(res.get('error') or res.get('status'))[:200])}")
                return
            status, msg = compare(expected, res)
            {"match": st.success, "differs": st.warning}.get(status, st.info)(msg)
            st.markdown(f"**{executor_line(res)}**" if res.get("method") else "")
            if res.get("route_note"): st.caption(bill.md_escape(res["route_note"]))
            for n, s in enumerate(res.get("steps") or [], 1):
                st.caption(f"{n}. {browser_cart.icon(s.get('actor'))} {browser_cart.label(s.get('actor')).replace('TinyFish ', '')} · {bill.md_escape(str(s.get('text'))[:200])}")
            r = res.get("result") or {}
            added = r.get("added_to_cart") is not False      # a cart that stayed empty has no total or delivery estimate worth showing
            if added and r.get("cart_total_inr") is not None: st.caption(f"Cart total shown by the shop: {bill.md_escape(str(r['cart_total_inr']))}")
            if added and r.get("delivery_estimate"): st.caption(f"Delivery estimate: {bill.md_escape(str(r['delivery_estimate'])[:120])}")
            st.caption(f"Status {bill.md_escape(str(res.get('status')))} · steps used {res.get('num_of_steps', 'n/a')}" + (" · cached, no credits used" if res.get("cached") else ""))
