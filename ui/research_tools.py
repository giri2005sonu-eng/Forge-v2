import streamlit as st

from core import part_specs, research
from core.data import PROJECTS


def render(state, build, tinyfish_enabled, gemini_enabled):
    custom = bool(build.get("custom"))  # Gemini-planned build: parts and label come from the build, not the fixed catalog
    parts = build["parts"] if custom else build["best"]["parts"]
    project_label = build["label"] if custom else PROJECTS[state.project]["label"]

    st.divider()
    st.markdown("#### Research & component tools")
    with st.container(border=True):
        st.markdown("**Research what this project needs** · Search + Fetch (free)")
        if st.button("Research build guides", disabled=not (tinyfish_enabled and gemini_enabled)):
            with st.status("Reading build guides...", expanded=True):
                state.research[project_label] = research.research(project_label, log=st.write)
        result = state.research.get(project_label)
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
        st.markdown("**Part specs** · typical datasheet values, best value in green when comparing")
        # Resolve any specs from dataset/learned cache if not already attached
        for p in parts.values():
            if not p.get("specs") and not p.get("none"):
                sp = part_specs.find_specs_in_dataset(p.get("name"))
                if sp:
                    p["specs"] = sp

        spec_parts = {part["name"]: part for part in parts.values() if not part.get("none") and part.get("specs")}
        without = [part["name"] for part in parts.values() if not part.get("none") and not part.get("specs")]
        if spec_parts:
            chosen = st.selectbox("Component in your build", list(spec_parts), key="spec_part")
            part = spec_parts[chosen]
            st.markdown(part_specs.compare_html(part_specs.compare([(chosen, part["specs"])])), unsafe_allow_html=True)
            pool = part_specs.alternatives(part["role"], part["specs"], exclude_name=chosen, limit=60, min_shared=1)
            names = {name: key for key, name, _ in pool}
            if pool and st.toggle(f"Compare with other {part_specs.plural(part['role'])}", key=f"cmp_on_{part['id']}"):
                picked = st.multiselect(f"Pick {part_specs.plural(part['role'])} to compare (most similar first)", list(names),
                                        default=list(names)[:3], max_selections=4, key=f"cmp_with_{part['id']}")
                if picked:
                    items = [(chosen, part["specs"])] + [(n, part_specs.specs_for(names[n])) for n in picked]
                    st.markdown(part_specs.compare_html(part_specs.compare(items)), unsafe_allow_html=True)
                else:
                    st.caption("Pick one or more parts to compare.")
            elif not pool:
                st.caption(f"No other {part_specs.plural(part['role'])} with comparable typed specs in the library.")
            st.caption("Typed by the team for the common hobby board or chip; a different listing can differ. Prices are not shown here: they come only from live pages.")
        else:
            st.caption("No part in this build has typed specs.")
        if without:
            st.caption("No typed specs for: " + ", ".join(without[:8]) + (" ..." if len(without) > 8 else ""))
            if gemini_enabled:
                if st.button("Fetch specs for missing parts with Gemini", key="btn_fetch_missing_specs"):
                    with st.spinner("Fetching datasheet specs with Gemini..."):
                        from core import custom_bom
                        custom_bom.fetch_and_apply_missing_specs([p for p in parts.values() if p["name"] in without])
                        st.rerun()