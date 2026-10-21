import streamlit as st

from core.recommendation_catalog import (
    COMPETITION_EVENT_COUNTS,
    COMPETITION_EVENTS,
    PROJECT_CATALOG,
    PROJECT_FACTOR_CATALOG,
    competition_projects_for_event,
)


def _open_in_bom(state, project_key: str, factors: dict):
    """Directly transition to Stage 4 (Planning & BOM) with the selected competition project."""
    from core import project_store
    dataset_key = project_store.key_for_id(project_key) or (
        project_key if project_key.startswith("competition:") else f"competition:{project_key}"
    )
    state["bom_catalog_pick"] = dataset_key
    state.auto_open_catalog = True
    cost = factors.get("cost_inr")
    if cost:
        state.budget = int(cost)
    state.res = None
    state.custom = None
    state.stage = "bom"
    st.rerun()


def render(state):
    back_col, title_col = st.columns([1, 5])
    if back_col.button("Back", key="competition_back"):
        state.stage = "pick"
        st.rerun()
    title_col.subheader("Build to compete")
    st.caption("Choose an event, then shortlist projects tagged for it. Event mention counts come from the competition-project catalog.")

    if not COMPETITION_EVENTS:
        st.info("No competition-tagged projects are available yet.")
        return

    event = st.selectbox(
        "Competition or event",
        COMPETITION_EVENTS,
        format_func=lambda value: f"{value} · {COMPETITION_EVENT_COUNTS[value]} project mentions",
        key="competition_event",
    )
    project_keys = competition_projects_for_event(event)
    previous = state.get("competition_selected_by_event", {}).get(event, [])
    labels = {key: PROJECT_CATALOG[key]["label"] for key in project_keys}
    selected = st.multiselect(
        "Projects you want to compete with",
        project_keys,
        default=[key for key in previous if key in labels],
        format_func=lambda key: labels[key],
        key=f"competition_projects_{COMPETITION_EVENTS.index(event)}",
    )

    selections = dict(state.get("competition_selected_by_event", {}))
    selections[event] = selected
    state.competition_selected_by_event = selections

    if selected:
        top_c1, top_c2 = st.columns([3, 2])
        top_c1.markdown(f"**Selected for {event}: {len(selected)} project{'s' if len(selected) > 1 else ''}**")
        latest_key = selected[-1]
        latest_proj = PROJECT_CATALOG[latest_key]
        latest_factors = PROJECT_FACTOR_CATALOG[latest_key]
        if top_c2.button(f"🚀 Plan “{latest_proj['label'][:25]}” in BOM ➔", key="quick_open_latest_bom", type="primary", use_container_width=True):
            _open_in_bom(state, latest_key, latest_factors)

        for key in selected:
            project = PROJECT_CATALOG[key]
            factors = PROJECT_FACTOR_CATALOG[key]
            with st.container(border=True):
                head_col, btn_col = st.columns([3, 1.4])
                head_col.markdown(f"### {project['label']}")
                if btn_col.button(f"⚡ Plan & Build BOM", key=f"build_bom_{key}", type="primary", use_container_width=True):
                    _open_in_bom(state, key, factors)

                st.caption(project["desc"])
                st.caption(f"Estimated {factors['build_hours']} hours · ₹{factors['cost_inr']:,} · Parts availability {factors['parts_availability_india']}/5")
                st.caption("Key constraints: " + factors.get("constraints", "Not specified"))
                st.caption("Required skills: " + (", ".join(sorted(factors["required_skills"])) or "Not specified"))
                if factors.get("safety"):
                    st.warning("Safety: " + ", ".join(sorted(factors["safety"])))
        st.success("🎯 Click **Plan & Build BOM** on any competition project above to open its verified architecture, components, live pricing, and wiring in the Planning & Execution studio.")
    else:
        st.caption("Choose from the candidate projects below to open their BOM immediately, or use the multi-select above to shortlist:")
        for key in project_keys:
            project = PROJECT_CATALOG[key]
            factors = PROJECT_FACTOR_CATALOG[key]
            with st.container(border=True):
                head_col, btn_col = st.columns([3, 1.4])
                head_col.markdown(f"**{project['label']}**")
                if btn_col.button(f"⚡ Open & Plan BOM", key=f"quick_build_{key}", type="primary", use_container_width=True):
                    _open_in_bom(state, key, factors)
                st.caption(project["desc"])
                st.caption(f"Estimated {factors['build_hours']} hours · ₹{factors['cost_inr']:,} · Parts availability {factors['parts_availability_india']}/5")
                if factors.get("constraints"):
                    st.caption(f"Constraints: {factors['constraints']}")
