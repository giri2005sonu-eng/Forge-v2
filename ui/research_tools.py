import streamlit as st

from core import research, specs, tf
from core.data import PROJECTS


def render(state, build, tinyfish_enabled, gemini_enabled):
    best = build["best"]
    project_label = PROJECTS[state.project]["label"]

    st.divider()
    st.markdown("#### More TinyFish tools")
    with st.container(border=True):
        st.markdown("**Research what this project needs** · Search + Fetch (free)")
        if st.button("Research build guides", disabled=not (tinyfish_enabled and gemini_enabled)):
            with st.status("Reading build guides...", expanded=True):
                state.research[state.project] = research.research(project_label, log=st.write)
        result = state.research.get(state.project)
        if result:
            mapped = [item for item in result["items"] if item["role"] != "other"]
            st.caption(
                f"{len(result['items'])} components stated in {len(result['guides'])} guides; "
                f"{len(mapped)} map to parts we can rule-check, {len(result['items']) - len(mapped)} do not (shown as not covered)."
            )
            for item in result["items"]:
                role = item["role"] if item["role"] != "other" else "not covered by our catalog"
                icon = "✅" if item["role"] != "other" else "⚠️"
                st.markdown(f"{icon} **{item['name']}** · {role}")
                st.caption(f"“{item['quote'][:140]}” — {item['url']}")

    with st.container(border=True):
        st.markdown("**Check our specs against the shop pages** · uses the pages already fetched")
        candidates = {
            part["name"]: part
            for part in best["parts"].values()
            if not part.get("none") and state.live.get(part["id"])
        }
        if candidates:
            selected_name = st.selectbox("Part", list(candidates), key="spec_part")
            if st.button("Check specs", disabled=not gemini_enabled):
                part = candidates[selected_name]
                urls = [offer["url"] for offer in state.live[part["id"]]]
                state.specs[part["id"]] = specs.check_part(part, tf.fetch(urls), log=st.write)
            for row in state.specs.get(candidates[selected_name]["id"], []):
                icon = {"match": "✅", "differs": "❌", "not stated": "➖"}[row["status"]]
                live_value = row["live"] if row["live"] is not None else "not stated"
                st.markdown(f"{icon} `{row['spec']}` ours **{row['seed']}** · page **{live_value}** · {row['status']}")
                if row["quote"]:
                    st.caption(f"“{row['quote']}” — {row['url']}")
        else:
            st.caption("Run Find live prices first so there are pages to check.")

    with st.container(border=True):
        st.markdown("**Cart check with the Web Agent** · uses TinyFish credits")
        offers = {
            f"{part['name']} · {offer['url'].split('/')[2]}": offer["url"]
            for part in best["parts"].values()
            if not part.get("none")
            for offer in state.live.get(part["id"], [])
            if offer.get("price")
        }
        st.caption("Opens the shop page, adds ONE unit to the cart and reads the cart. It is told never to check out or enter any details. Capped at 12 steps (about 12 credits per TinyFish pricing).")
        if offers:
            selected_offer = st.selectbox("Verified listing", list(offers), key="agent_pick")
            if st.button("Run cart check", disabled=not tinyfish_enabled):
                with st.spinner("Web Agent running..."):
                    try:
                        state.agent[offers[selected_offer]] = tf.agent(offers[selected_offer])
                    except Exception as error:
                        state.agent[offers[selected_offer]] = dict(status="ERROR", error=str(error)[:200])
            result = state.agent.get(offers[selected_offer])
            if result:
                st.json(result.get("result") or result.get("error") or result)
                cached = " · cached, no credits used" if result.get("cached") else ""
                st.caption(f"Status {result.get('status')} · steps used {result.get('num_of_steps', 'n/a')}{cached}")
        else:
            st.caption("Run Find live prices first so there are verified listings to check.")