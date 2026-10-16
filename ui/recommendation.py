import streamlit as st
import streamlit.components.v1 as components

from core import picker, pipeline, resume, tf
from core.data import PROJECTS


def _label(project_key):
    return PROJECTS[project_key]["label"]


def _show_chart(chart_html, height):
    if hasattr(st, "iframe"):
        st.iframe(chart_html, height=height)
    else:
        components.html(chart_html, height=height)


def _survey_box(state):
    """Survey card: the questions open when the user clicks the box. Returns the answers as {question: [labels]}."""
    answered_before = state.A or {}
    with st.container(border=True):
        st.markdown("#### 📝 Answer a few questions")
        count_slot = st.empty()
        with st.expander("Start the survey"):
            answers = {}
            for key, question, options in picker.QUESTIONS:
                saved = [label for label, value in options.items() if value in answered_before.get(key, [])]
                answers[key] = st.pills(question, list(options), selection_mode="multi", default=saved or None, key=f"q_{key}") or []
        count = sum(bool(v) for v in answers.values())
        count_slot.caption(f"{count} of {len(picker.QUESTIONS)} answered. Pick as many answers as you like; every question is optional.")
    return answers


def _resume_box(state):
    """Resume card: upload, show what was detected, allow removal. Only detected skills are kept in session state."""
    with st.container(border=True):
        st.markdown("#### 📄 Upload your resume / CV")
        if state.resume is None:
            st.caption("PDF, DOCX or TXT. It is read in memory on this app; the text is not saved or sent to any AI service.")
            uploaded = st.file_uploader("Resume", type=["pdf", "docx", "txt"], key=f"resume_file_{state.resume_n}", label_visibility="collapsed")
            if uploaded is not None:
                try:
                    state.resume = dict(resume.analyze(resume.extract_text(uploaded.name, uploaded.getvalue())), name=uploaded.name)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        else:
            found = [resume.SKILLS[name][0] for name in state.resume["skills"]]
            st.caption(f"Read **{state.resume['name']}**.")
            if found:
                st.markdown("Skills found: " + " · ".join(f"`{label}`" for label in found))
                st.caption("These count as one factor in the ranking. Your survey answers always take priority over the resume.")
            else:
                st.warning("No robotics or electronics skills were detected, so the ranking will rely on the survey only.")
            if st.button("Remove resume"):
                state.resume, state.resume_n = None, state.resume_n + 1
                st.rerun()


def render_picker(state):
    st.subheader("Not sure what to build?")
    st.caption("Tell us about yourself with the survey, your resume, or both. We rank the projects that fit you best.")
    survey_col, resume_col = st.columns(2)
    with survey_col:
        answers = _survey_box(state)
    with resume_col:
        _resume_box(state)

    has_input = any(answers.values()) or state.resume is not None
    choose_col, skip_col, _ = st.columns([1, 1, 3])
    if choose_col.button("Recommend projects", disabled=not has_input):
        state.A = {key: [options[value] for value in answers[key]] for key, _, options in picker.QUESTIONS}
        state.pick, state.idea, state.examples = None, None, None
        state.stage = "results"
        st.rerun()
    if not has_input:
        st.caption("Answer at least one question or upload a resume to get a ranking.")
    if skip_col.button("Skip"):
        state.stage = "bom"
        st.rerun()


def render_results(state, tinyfish_enabled):
    st.subheader("Projects that fit you")
    answered = sum(bool(v) for v in state.A.values())
    st.caption(f"Based on {answered} survey answer{'s' if answered != 1 else ''}" + (f" and your resume ({state.resume['name']})." if state.resume else "."))
    R = state.resume
    recommendations = picker.rank(state.A, R)[:4]
    for column, (project_key, score) in zip(st.columns(len(recommendations)), recommendations):
        with column, st.container(border=True):
            st.markdown(f"### {score}%")
            st.markdown(f"**{_label(project_key)}**")
            st.caption(PROJECTS[project_key]["desc"])
            matched = len(resume.matches(project_key, R))
            if matched:
                st.caption(f"📄 {matched} resume skill{'s' if matched != 1 else ''} match")
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
        fit = picker.fits(state.pick, state.A, R)
        left, right = st.columns([2, 3])
        with left, st.container(border=True):
            st.markdown(f"### {project['label']} · {picker.score(state.pick, state.A, R)}% match")
            st.write(project["desc"])
            evidence = resume.matches(state.pick, R)
            if evidence:
                st.markdown("**Why, from your resume**")
                for label, quote in evidence:
                    st.markdown(f"- **{label}**: \u201c\u2026{quote}\u2026\u201d")
            if resume.already_mentions(state.pick, R):
                st.info("Your resume already mentions this kind of project. Choose it for a stronger version, or pick another to show range.")
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