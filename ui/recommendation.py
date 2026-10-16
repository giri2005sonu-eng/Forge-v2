import streamlit as st
import streamlit.components.v1 as components

from core import picker, pipeline, tf
from core.data import PROJECTS


def _label(project_key):
    return PROJECTS[project_key]["label"]


def _show_chart(chart_html, height):
    if hasattr(st, "iframe"):
        st.iframe(chart_html, height=height)
    else:
        components.html(chart_html, height=height)


def render_picker(state):
    st.subheader("Not sure what to build?")
    st.caption("Pick as many answers as you like on each question. Every question is optional.")
    with st.container(border=True):
        answers = {
            key: st.pills(question, list(options), selection_mode="multi", key=f"q_{key}") or []
            for key, question, options in picker.QUESTIONS
        }
        choose_col, skip_col, _ = st.columns([1, 1, 3])
        if choose_col.button("Recommend projects"):
            state.A = {key: [options[value] for value in answers[key]] for key, _, options in picker.QUESTIONS}
            state.pick, state.idea, state.examples = None, None, None
            state.stage = "results"
            st.rerun()
        if skip_col.button("Skip"):
            state.stage = "bom"
            st.rerun()


def render_results(state, tinyfish_enabled):
    st.subheader("Projects that fit you")
    recommendations = picker.rank(state.A)[:4]
    for column, (project_key, score) in zip(st.columns(len(recommendations)), recommendations):
        with column, st.container(border=True):
            st.markdown(f"### {score}%")
            st.markdown(f"**{_label(project_key)}**")
            st.caption(PROJECTS[project_key]["desc"])
            if st.button("Choose", key=f"c_{project_key}"):
                state.pick = project_key
                state.examples = None

    with st.container(border=True):
        st.markdown("**Or describe your own idea**")
        idea_text = st.text_input("e.g. a car that follows my hand", label_visibility="collapsed")
        if st.button("Match my idea") and idea_text.strip():
            state.idea = pipeline.map_idea(idea_text)
            if state.idea["project"]:
                state.pick = state.idea["project"]
        if state.idea:
            message = (
                f"Closest supported project: {_label(state.idea['project'])}. "
                if state.idea["project"] else "Not supported yet. "
            ) + state.idea["reason"]
            (st.success if state.idea["project"] else st.warning)(message)

    if state.pick:
        project = PROJECTS[state.pick]
        fit = picker.fits(state.pick, state.A)
        left, right = st.columns([2, 3])
        with left, st.container(border=True):
            st.markdown(f"### {project['label']} · {picker.score(state.pick, state.A)}% match")
            st.write(project["desc"])
            st.caption("Scores are my estimates, not measured data. Triangle size and colour show fit for your answers.")
            if st.button("Real examples from the web (TinyFish Search)", disabled=not tinyfish_enabled):
                try:
                    state.examples = tf.search(f"{project['label']} robot project hackathon")[:5]
                except Exception as error:
                    state.examples = [dict(title=f"Search failed: {str(error)[:100]}", url="")]
            for example in state.examples or []:
                if example["url"]:
                    st.markdown(f"- [{example['title'][:70]}]({example['url']})")
                else:
                    st.markdown(f"- {example['title']}")
            if st.button("Build the BOM for this project"):
                state.project = state.pick
                state.budget = int(max(state.A.get("budget", [3500]) or [3500]))
                state.res = None
                state.stage = "bom"
                st.rerun()
        with right, st.container(border=True):
            _show_chart(picker.chart_html(fit), 440)

    change_col, bom_col = st.columns(2)
    if change_col.button("Change answers"):
        state.stage = "pick"
        st.rerun()
    if bom_col.button("Skip to BOM agent"):
        state.stage = "bom"
        st.rerun()