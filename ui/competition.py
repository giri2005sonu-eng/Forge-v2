import streamlit as st

from core.recommendation_catalog import (
    COMPETITION_EVENT_COUNTS,
    COMPETITION_EVENTS,
    PROJECT_CATALOG,
    PROJECT_FACTOR_CATALOG,
    competition_projects_for_event,
)


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
        st.markdown(f"**Selected for {event}: {len(selected)}**")
        for key in selected:
            project = PROJECT_CATALOG[key]
            factors = PROJECT_FACTOR_CATALOG[key]
            with st.container(border=True):
                st.markdown(f"**{project['label']}**")
                st.caption(project["desc"])
                st.caption(f"Estimated {factors['build_hours']} hours · ₹{factors['cost_inr']:,} · Parts availability {factors['parts_availability_india']}/5")
                st.caption("Key constraints: " + factors.get("constraints", "Not specified"))
                st.caption("Required skills: " + (", ".join(sorted(factors["required_skills"])) or "Not specified"))
                if factors.get("safety"):
                    st.warning("Safety: " + ", ".join(sorted(factors["safety"])))
        st.info("These projects are saved to your current session shortlist. Their competition-specific BOMs are not yet supported by the builder.")
    else:
        st.caption("No projects selected for this event yet.")
