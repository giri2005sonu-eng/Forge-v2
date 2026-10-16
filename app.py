import os
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from core import bill, picker, pipeline, research, specs, tf
from core.data import PROJECTS, QTY

load_dotenv()
st.set_page_config(page_title="FORGE", page_icon="🤖", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;700&family=DM+Sans:wght@400;500&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif} h1,h2,h3{font-family:Sora,sans-serif!important}
.stButton>button{border-radius:14px;padding:.6rem 1.3rem;border:0;background:linear-gradient(135deg,#0F8F9A,#3CC4CF);color:#fff;font-weight:500;
 box-shadow:0 4px 14px rgba(60,196,207,.3);transition:transform .15s,box-shadow .15s}
.stButton>button:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(60,196,207,.4)}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:18px}
.block-container{padding-top:2rem;max-width:1100px} #MainMenu,footer{visibility:hidden}
.b{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700;color:#fff}
.PASS{background:#2FA36B}.FAIL{background:#D8505B}.UNKNOWN{background:#B08A1E}
</style>""", unsafe_allow_html=True)

S = st.session_state
for k, v in dict(live={}, res=None, log=[], stage="pick", A={}, pick=None, project="line_follower", budget=3500, idea=None, examples=None, research={}, specs={}, agent={}, choice={}).items():
    S.setdefault(k, v)
tf_key, gem_key = bool(os.getenv("TINYFISH_API_KEY")), bool(os.getenv("GEMINI_API_KEY"))

def show_html(html, height):
    """st.iframe on new Streamlit; falls back to the older components API. HTML here is built only from our own constants."""
    st.iframe(html, height=height) if hasattr(st, "iframe") else components.html(html, height=height)

def go(stage): S.stage = stage
def label(k): return PROJECTS[k]["label"]

st.title("FORGE")
st.caption("Robot BOM agent. TinyFish finds and reads live vendor pages, rules decide compatibility, every price carries its quote.")

# ---------------- 1. recommendation helper (skippable) ----------------
if S.stage == "pick":
    st.subheader("Not sure what to build?")
    st.caption("Pick as many answers as you like on each question. Every question is optional.")
    with st.container(border=True):
        ans = {k: st.pills(q, list(o), selection_mode="multi", key=f"q_{k}") or [] for k, q, o in picker.QUESTIONS}
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("Recommend projects"):
            S.A = {k: [o[x] for x in ans[k]] for k, q, o in picker.QUESTIONS}
            S.pick, S.idea, S.examples = None, None, None; go("results"); st.rerun()
        if c2.button("Skip"): go("bom"); st.rerun()

elif S.stage == "results":
    st.subheader("Projects that fit you")
    rec = picker.rank(S.A)[:4]
    for col, (k, sc) in zip(st.columns(len(rec)), rec):
        with col, st.container(border=True):
            st.markdown(f"### {sc}%"); st.markdown(f"**{label(k)}**"); st.caption(PROJECTS[k]["desc"])
            if st.button("Choose", key=f"c_{k}"): S.pick = k; S.examples = None
    with st.container(border=True):
        st.markdown("**Or describe your own idea**")
        txt = st.text_input("e.g. a car that follows my hand", label_visibility="collapsed")
        if st.button("Match my idea") and txt.strip():
            S.idea = pipeline.map_idea(txt)
            if S.idea["project"]: S.pick = S.idea["project"]
        if S.idea:
            (st.success if S.idea["project"] else st.warning)((f"Closest supported project: {label(S.idea['project'])}. " if S.idea["project"] else "Not supported yet. ") + S.idea["reason"])
    if S.pick:
        p, fit = PROJECTS[S.pick], picker.fits(S.pick, S.A)
        L, R = st.columns([2, 3])
        with L, st.container(border=True):
            st.markdown(f"### {p['label']} · {picker.score(S.pick, S.A)}% match"); st.write(p["desc"])
            st.caption("Scores are my estimates, not measured data. Triangle size and colour show fit for your answers.")
            if st.button("Real examples from the web (TinyFish Search)", disabled=not tf_key):
                try: S.examples = tf.search(f"{p['label']} robot project hackathon")[:5]
                except Exception as e: S.examples = [dict(title=f"Search failed: {str(e)[:100]}", url="")]
            for e in S.examples or []: st.markdown(f"- [{e['title'][:70]}]({e['url']})" if e["url"] else f"- {e['title']}")
            if st.button("Build the BOM for this project"):
                S.project, S.budget, S.res = S.pick, int(max(S.A.get("budget", [3500]) or [3500])), None; go("bom"); st.rerun()
        with R, st.container(border=True): show_html(picker.chart_html(fit), 440)
    c1, c2 = st.columns(2)
    if c1.button("Change answers"): go("pick"); st.rerun()
    if c2.button("Skip to BOM agent"): go("bom"); st.rerun()

# ---------------- 2. BOM agent ----------------
else:
    if not (tf_key and gem_key):
        st.warning("Add TINYFISH_API_KEY and GEMINI_API_KEY to .env for live prices. Without them the app uses seed prices (labelled).")
    with st.container(border=True):
        a, b, c = st.columns([2, 1, 1])
        keys = list(PROJECTS)
        robot = a.selectbox("Project", keys, index=keys.index(S.project), format_func=label)
        budget = b.number_input("Budget (₹)", 1000, 100000, S.budget, 500)
        bt = c.toggle("Needs Bluetooth", value=PROJECTS[robot]["bt"])
        g1, g2, _ = st.columns([1, 1, 3])
        if g1.button("Generate BOM"):
            S.project = robot; S.res = pipeline.select(robot, budget, bt or PROJECTS[robot]["bt"], S.live)
        if g2.button("Help me choose"): go("pick"); st.rerun()

    res = S.res
    if res and not res["best"]:
        st.error(f"No fully compatible build fits ₹{budget:,.0f}. {res['rejected']} of {res['evaluated']} combinations failed a rule. Raise the budget or relax a requirement.")
    elif res:
        best = res["best"]
        st.subheader(f"{label(S.project)} · ₹{best['cost']:,.0f}")
        st.caption(f"Checked {res['evaluated']} combinations; {res['rejected']} rejected for failing a rule.")
        left, right = st.columns([3, 2])
        with left, st.container(border=True):
            for role, p in best["parts"].items():
                if p.get("none"): continue
                price, src = pipeline.price_of(p, S.live); q = QTY.get(role, 1)
                st.markdown(f"**{p['name']}** · {role} × {q} · ₹{price * q:,.0f} · `{src} price`")
                w = pipeline.spread_warning(S.live.get(p["id"], []))
                if w: st.warning(w)
                for o in S.live.get(p["id"], []):
                    if o.get("price"): st.caption(f"✓ ₹{o['price']:,.0f} · {o.get('name') or 'product name not verified'} · {o['url']} — “{o['quote'][:90]}”")
                    else: st.caption(f"Link found, price not verified: {o['url']}")
        with right, st.container(border=True):
            st.markdown("**Compatibility checks**")
            for ck in best["checks"]:
                st.markdown(f"<span class='b {ck['status']}'>{ck['status']}</span> {ck['title']}", unsafe_allow_html=True)
                if ck["status"] != "PASS": st.caption(ck["msg"])
        if res["alternatives"]:
            with st.expander("Other valid builds"):
                for r in res["alternatives"]: st.write(f"₹{r['cost']:,.0f} · " + ", ".join(p["name"] for p in r["parts"].values() if not p.get("none")))
        st.divider()
        st.markdown("#### Live data from TinyFish")
        if st.button("Find live prices (TinyFish Search + Fetch)", disabled=not (tf_key and gem_key)):
            S.log = []
            def lg(m): S.log.append(str(m)); st.write(m)
            with st.status("Searching vendors and reading pages...", expanded=True) as stt:
                for p in best["parts"].values():
                    if p.get("none"): continue
                    try: S.live[p["id"]] = pipeline.source_part(p, log=lg)
                    except Exception as e: lg(f"{p['name']}: {e}")
                stt.update(label="Done. Prices with a verified quote are now used in the BOM.", state="complete")
            S.res = pipeline.select(S.project, budget, bt or PROJECTS[S.project]["bt"], S.live); st.rerun()
        if S.log:
            with st.expander("Last TinyFish research log", expanded=True):
                for m in S.log: st.write(m)

        # ---------------- vendor comparison + bill ----------------
        st.divider()
        st.markdown("#### Compare shops and build your bill")
        st.caption("Each row is a part of the build. The cheapest verified listing is ticked; tick another one to buy that instead. The bill below updates straight away.")
        if st.button("Reset to cheapest"): S.choice = {}; st.rerun()
        COLS = [1.7] + [1.35] * bill.MAX_OFFERS + [0.95]
        hd = st.columns(COLS)
        for c, t in zip(hd, ["Part", "Cheapest", "Option 2", "Option 3", "Option 4", "Line total"]): c.caption(t)
        def pick_offer(pid, url): S.choice[pid] = url
        for role, p in best["parts"].items():
            if p.get("none"): continue
            offers, q = bill.offers_for(p["id"], S.live), QTY.get(role, 1)
            sel = bill.chosen_url(p["id"], S.live, S.choice)
            with st.container(border=True):
                cols = st.columns(COLS)
                cols[0].markdown(f"**{bill.md_escape(p['name'])}**")
                cols[0].caption(f"{role.capitalize()} × {q}")
                if not offers:
                    cols[1].markdown(f"**{bill.inr(p['seed_price'])}**")
                    cols[1].caption("Estimate, no verified shop price yet")
                    tot_line = p["seed_price"] * q
                for j, o in enumerate(offers):
                    S[f"pk_{p['id']}_{j}"] = o["url"] == sel  # keep the ticks in step with the stored choice
                    cols[1 + j].checkbox(f"**{bill.inr(o['price'])}**" + (" · cheapest" if j == 0 else ""), key=f"pk_{p['id']}_{j}", on_change=pick_offer, args=(p["id"], o["url"]))
                    u = bill.safe_url(o["url"]); shop = bill.md_escape(bill.vendor(o["url"]))
                    cols[1 + j].caption((f"[{shop}]({u})" if u else shop) + f"  \n{bill.md_escape((o.get('name') or 'product name not verified')[:60])}" + ("  \n:red[Out of stock]" if o.get("in_stock") is False else ""))
                if offers: tot_line = next(o["price"] for o in offers if o["url"] == sel) * q
                cols[-1].markdown(f"**{bill.inr(tot_line)}**")
                nv = len(bill.unverified_for(p["id"], S.live))
                if nv: st.caption(f"{nv} more link{'s' if nv > 1 else ''} found without a verifiable price, so not offered here.")
                w = pipeline.spread_warning(S.live.get(p["id"], []))
                if w: st.warning(w)
        B = bill.make(best["parts"], S.live, S.choice, budget, label(S.project))
        st.markdown("#### Your bill")
        st.markdown(B["html"], unsafe_allow_html=True)
        st.download_button("Download bill as PDF", B["pdf"], file_name=f"forge_bill_{S.project}_{B['ref'][3:11]}.pdf", mime="application/pdf", type="primary")

        st.divider()
        st.markdown("#### More TinyFish tools")
        # --- research what the project needs (Search + Fetch, free) ---
        with st.container(border=True):
            st.markdown("**Research what this project needs** · Search + Fetch (free)")
            if st.button("Research build guides", disabled=not (tf_key and gem_key)):
                with st.status("Reading build guides...", expanded=True):
                    S.research[S.project] = research.research(label(S.project), log=st.write)
            rr = S.research.get(S.project)
            if rr:
                mapped = [i for i in rr["items"] if i["role"] != "other"]
                st.caption(f"{len(rr['items'])} components stated in {len(rr['guides'])} guides; {len(mapped)} map to parts we can rule-check, {len(rr['items']) - len(mapped)} do not (shown as not covered).")
                for i in rr["items"]:
                    st.markdown(f"{'✅' if i['role'] != 'other' else '⚠️'} **{i['name']}** · {i['role'] if i['role'] != 'other' else 'not covered by our catalog'}")
                    st.caption(f"“{i['quote'][:140]}” — {i['url']}")
        # --- spec check (Fetch pages already read, free) ---
        with st.container(border=True):
            st.markdown("**Check our specs against the shop pages** · uses the pages already fetched")
            cand = {p["name"]: p for p in best["parts"].values() if not p.get("none") and S.live.get(p["id"])}
            if cand:
                pick = st.selectbox("Part", list(cand), key="spec_part")
                if st.button("Check specs", disabled=not gem_key):
                    p = cand[pick]; urls = [o["url"] for o in S.live[p["id"]]]
                    S.specs[p["id"]] = specs.check_part(p, tf.fetch(urls), log=st.write)
                for r in S.specs.get(cand[pick]["id"], []):
                    icon = {"match": "✅", "differs": "❌", "not stated": "➖"}[r["status"]]
                    st.markdown(f"{icon} `{r['spec']}` ours **{r['seed']}** · page **{r['live'] if r['live'] is not None else 'not stated'}** · {r['status']}")
                    if r["quote"]: st.caption(f"“{r['quote']}” — {r['url']}")
            else: st.caption("Run Find live prices first so there are pages to check.")
        # --- Web Agent cart check (USES CREDITS, opt-in) ---
        with st.container(border=True):
            st.markdown("**Cart check with the Web Agent** · uses TinyFish credits")
            offers = {f"{p['name']} · {o['url'].split('/')[2]}": o["url"] for p in best["parts"].values() if not p.get("none") for o in S.live.get(p["id"], []) if o.get("price")}
            st.caption("Opens the shop page, adds ONE unit to the cart and reads the cart. It is told never to check out or enter any details. Capped at 12 steps (about 12 credits per TinyFish pricing).")
            if offers:
                ch = st.selectbox("Verified listing", list(offers), key="agent_pick")
                if st.button("Run cart check", disabled=not tf_key):
                    with st.spinner("Web Agent running..."):
                        try: S.agent[offers[ch]] = tf.agent(offers[ch])
                        except Exception as e: S.agent[offers[ch]] = dict(status="ERROR", error=str(e)[:200])
                r = S.agent.get(offers[ch])
                if r:
                    st.json(r.get("result") or r.get("error") or r)
                    st.caption(f"Status {r.get('status')} · steps used {r.get('num_of_steps', 'n/a')}" + (" · cached, no credits used" if r.get("cached") else ""))
            else: st.caption("Run Find live prices first so there are verified listings to check.")
