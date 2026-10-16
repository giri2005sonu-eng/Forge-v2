import streamlit as st
import streamlit.components.v1 as components

from core import picker, pipeline, resume, tf
from core.recommendation_catalog import PROJECT_CATALOG, PROJECT_FACTOR_CATALOG, RECOMMENDATION_PROJECT_KEYS


def _label(project_key):
    return PROJECT_CATALOG[project_key]["label"]


def _show_chart(chart_html, height):
    if hasattr(st, "iframe"):
        st.iframe(chart_html, height=height)
    else:
        components.html(chart_html, height=height)


def _save_survey_field(answer_key, widget_key):
    answers = dict(st.session_state.get("survey_answers", {}))
    answers[answer_key] = st.session_state.get(widget_key)
    st.session_state["survey_answers"] = answers


def _capture_question(step):
    answers = dict(st.session_state.get("survey_answers", {}))
    key = picker.QUESTIONS[step][0]
    if picker.QUESTIONS[step][2]:
        selected = st.session_state.get(f"q_{key}", [])
        answers[key] = selected[:3] if key == "interests" else selected
    if key == "career":
        answers["dream_job"] = st.session_state.get("q_dream_job", "")
    elif key == "schedule":
        answers["hours_per_week"] = st.session_state.get("q_hours_per_week", 0)
        choice = st.session_state.get("q_deadline", "Not set")
        answers["deadline_weeks"] = {"1 week": 1, "2 weeks": 2, "1 month": 4, "2 months": 8, "3 months": 12, "6 months": 24}.get(choice)
    elif key == "budget":
        answers["budget_inr"] = st.session_state.get("q_budget_inr", 0) or None
    elif key == "goal":
        answers["team"] = st.session_state.get("q_team", "Not set")
    st.session_state["survey_answers"] = answers


def _move_survey(step, delta):
    _capture_question(step)
    st.session_state["survey_step"] = step + delta


def _survey_box(state):
    """Collect the nine ranking inputs in a one-question-at-a-time flow."""
    saved = dict(state.get("survey_answers", {}))
    step = max(0, min(state.get("survey_step", 0), len(picker.QUESTIONS) - 1))
    finish_requested = False
    with st.container(border=True):
        st.markdown("#### 📝 Tell us about yourself")
        key, question, options = picker.QUESTIONS[step]
        st.caption(f"Question {step + 1} of {len(picker.QUESTIONS)} · Optional")
        if options:
            widget_key = f"q_{key}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = saved.get(key, [])
            selected = st.pills(question, list(options), selection_mode="multi", key=widget_key,
                                on_change=_save_survey_field, args=(key, widget_key)) or []
            saved[key] = selected[:3] if key == "interests" else selected
            if key == "interests" and len(selected) > 3:
                st.info("The ranking uses your first three selected interests.")

        if key == "career":
            widget_key = "q_dream_job"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = saved.get("dream_job", "")
            saved["dream_job"] = st.text_input("Dream job, company, or destination industry", key=widget_key,
                                                on_change=_save_survey_field, args=("dream_job", widget_key))
        elif key == "schedule":
            hours_key, deadline_key = "q_hours_per_week", "q_deadline"
            if hours_key not in st.session_state:
                st.session_state[hours_key] = saved.get("hours_per_week", 0)
            if deadline_key not in st.session_state:
                saved_week = saved.get("deadline_weeks")
                st.session_state[deadline_key] = {1: "1 week", 2: "2 weeks", 4: "1 month", 8: "2 months", 12: "3 months", 24: "6 months"}.get(saved_week, "Not set")
            saved["hours_per_week"] = st.number_input("Hours available per week (0 = not specified)", min_value=0, max_value=100,
                                                      step=1, key=hours_key, on_change=_save_survey_field,
                                                      args=("hours_per_week", hours_key))
            deadline_options = ["Not set", "1 week", "2 weeks", "1 month", "2 months", "3 months", "6 months"]
            deadline = st.selectbox("Finish by", deadline_options, key=deadline_key,
                                    on_change=_save_survey_field, args=("deadline_choice", deadline_key))
            saved["deadline_weeks"] = {"1 week": 1, "2 weeks": 2, "1 month": 4, "2 months": 8, "3 months": 12, "6 months": 24}.get(deadline)
        elif key == "budget":
            widget_key = "q_budget_inr"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = saved.get("budget_inr") or 0
            saved["budget_inr"] = st.number_input("Maximum budget in ₹ (0 = not specified)", min_value=0,
                                                 max_value=200000, step=100, key=widget_key,
                                                 on_change=_save_survey_field, args=("budget_inr", widget_key)) or None
        elif key == "goal":
            widget_key = "q_team"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = saved.get("team", "Not set")
            saved["team"] = st.selectbox("Working arrangement", ["Not set", "Solo", "Team"], key=widget_key,
                                          on_change=_save_survey_field, args=("team", widget_key))

        st.session_state["survey_answers"] = saved
        back_col, next_col = st.columns(2)
        back_col.button("Back", disabled=step == 0, key="survey_back", on_click=_move_survey, args=(step, -1))
        if step == len(picker.QUESTIONS) - 1:
            finish_requested = next_col.button("See recommendations", key="survey_finish")
        else:
            next_col.button("Next", key="survey_next", on_click=_move_survey, args=(step, 1))

        count = sum(bool(saved.get(name)) for name in ("career", "experience", "languages", "tools", "hardware", "goal", "interests"))
        count += bool(saved.get("hours_per_week") or saved.get("deadline_weeks"))
        count += bool(saved.get("budget_inr"))
        st.caption(f"{count} of {len(picker.QUESTIONS)} questions answered")
    return saved, finish_requested


def _resume_box(state, gemini_enabled):
    """Send resume text only for Gemini extraction; keep verified factors, never the raw text."""
    with st.container(border=True):
        st.markdown("#### 📄 Upload your resume / CV")
        st.caption("Your resume text is sent to Google Gemini to extract skills, languages, tools, and past projects. Only factors with exact supporting quotes are kept in this session; the raw text is not stored.")
        if state.resume is None:
            if not gemini_enabled:
                st.warning("Add GEMINI_API_KEY to extract resume factors. Survey-only recommendations are available without it.")
            uploaded = st.file_uploader("Resume", type=["pdf", "docx", "txt"], key=f"resume_file_{state.resume_n}",
                                        label_visibility="collapsed", disabled=not gemini_enabled)
            if uploaded is not None:
                try:
                    text = resume.extract_text(uploaded.name, uploaded.getvalue())
                    factors = pipeline.extract_resume_factors(text)
                    state.resume = dict(factors, name=uploaded.name)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                except Exception as error:
                    st.error(f"Resume extraction failed ({type(error).__name__}).")
        else:
            data = state.resume
            st.caption(f"Read **{data.get('name', 'resume')}**. The raw text was not kept.")
            normalized = picker.normalize_survey_answers(state.get("survey_answers", {}))
            groups = (("skills", set(normalized.get("experience", []))),
                      ("languages", set(normalized.get("languages", []))),
                      ("tools", set(normalized.get("tools", []))))
            for group, reported in groups:
                for index, item in enumerate(data.get(group, [])):
                    if item.get("id") in reported:
                        item["confirmed"] = True
                        continue
                    item["confirmed"] = st.checkbox(
                        f"Your resume mentions {item['name']} ({item['quote']}). Is that right? Include it?",
                        key=f"resume_confirm_{group}_{index}_{item['id']}", value=item.get("confirmed", False))
            for index, item in enumerate(data.get("projects", [])):
                item["confirmed"] = st.checkbox(
                    f"Your resume describes {item['name']} as {item['domain']} ({item['quote']}). Is that accurate? Use this domain as an interest?",
                    key=f"resume_confirm_project_{index}", value=item.get("confirmed", False))
            state.resume = data
            detected = [item["name"] for group in ("skills", "languages", "tools") for item in data.get(group, [])]
            if detected:
                st.markdown("Extracted factors: " + " · ".join(f"`{name}`" for name in detected))
            for item in data.get("projects", []):
                st.caption(f"Past project: {item['name']} · {item['domain']} · “{item['quote']}”")
            if st.button("Remove resume"):
                state.resume, state.resume_n = None, state.resume_n + 1
                st.rerun()


def render_picker(state, tinyfish_enabled, gemini_enabled):
    st.subheader("Not sure what to build?")
    st.caption("Tell us what you have done, what you can access, and where you want to go. Deterministic scoring ranks supported builds; Gemini only structures resume evidence.")
    survey_col, resume_col = st.columns(2)
    with survey_col:
        answers, finish_requested = _survey_box(state)
    with resume_col:
        _resume_box(state, gemini_enabled)

    profile = picker.normalize_survey_answers(answers)
    has_profile_input = any(profile.get(key) for key in ("career", "experience", "languages", "tools", "hardware", "goal", "interests"))
    has_profile_input |= bool(profile.get("budget_inr") or profile["schedule"].get("hours_per_week") or profile["schedule"].get("deadline_weeks") or profile.get("dream_job"))
    has_input = has_profile_input or state.resume is not None
    choose_col, skip_col, _ = st.columns([1, 1, 3])
    if choose_col.button("Recommend projects", disabled=not has_input) or finish_requested:
        if not has_input:
            st.warning("Answer at least one question or upload a resume to get a ranking.")
            return
        resume_factors = state.resume or dict(skills=[], languages=[], tools=[], projects=[])
        profile["experience"] = list(dict.fromkeys(profile.get("experience", []) + [item["id"] for item in resume_factors.get("skills", []) if item.get("confirmed")]))
        profile["languages"] = list(dict.fromkeys(profile.get("languages", []) + [item["id"] for item in resume_factors.get("languages", []) if item.get("confirmed")]))
        profile["tools"] = list(dict.fromkeys(profile.get("tools", []) + [item["id"] for item in resume_factors.get("tools", []) if item.get("confirmed")]))
        profile["resume"] = resume_factors
        profile["career_research"] = None
        state.career_research = None
        if profile.get("dream_job") and tinyfish_enabled:
            try:
                with st.spinner("Researching current role requirements with TinyFish…"):
                    state.career_research = pipeline.research_career_target(profile["dream_job"])
                profile["career_research"] = state.career_research
            except Exception as error:
                state.career_research = dict(query=profile["dream_job"], signals=[], sources=[], error=str(error)[:180])
        state.A = profile
        state.survey_answer_count = sum(bool(answers.get(key)) for key in ("career", "experience", "languages", "tools", "hardware", "goal", "interests"))
        state.survey_answer_count += bool(answers.get("hours_per_week") or answers.get("deadline_weeks"))
        state.survey_answer_count += bool(answers.get("budget_inr"))
        state.pick, state.idea, state.examples = None, None, None
        state.stage = "results"
        st.rerun()
    if not has_input:
        st.caption("Answer at least one question or upload a resume to get a ranking.")
    if skip_col.button("Skip"):
        state.stage = "bom"
        st.rerun()


def render_results(state, tinyfish_enabled):
    heading_col, back_col = st.columns([4, 1])
    heading_col.subheader("Projects that fit you")
    if back_col.button("Back to questions", key="results_back"):
        state.stage = "pick"
        st.rerun()
    count = state.survey_answer_count
    resume_data = state.A.get("resume", {})
    st.caption(f"Based on {count} survey answer{'s' if count != 1 else ''}" + (f" and verified factors from {resume_data['name']}." if resume_data.get("name") else "."))
    recommendations = picker.rank_factor_projects(state.A, limit=5)
    st.caption(f"Ranked from {len(RECOMMENDATION_PROJECT_KEYS)} additional projects. The three existing BOM projects are excluded from this list; new recommendations are not yet BOM-supported.")
    for column, (project_key, score) in zip(st.columns(len(recommendations)) if recommendations else [], recommendations):
        project = PROJECT_CATALOG[project_key]
        meta = PROJECT_FACTOR_CATALOG[project_key]
        with column, st.container(border=True):
            st.markdown(f"### {score}%")
            st.markdown(f"**{_label(project_key)}**")
            st.caption(project["desc"])
            st.caption(f"{meta['domain'].title()} · {meta['build_hours']} hours · ₹{meta['cost_inr']:,}")
            if meta.get("competition_event"):
                st.caption(f"Event: {meta['competition_event']}")
            if meta.get("constraints"):
                st.caption(f"Competition constraints: {meta['constraints']}")
            if st.button("Choose", key=f"c_{project_key}"):
                state.pick = project_key
                state.examples = None

    if not recommendations:
        st.warning("No supported project meets all the limits you provided. Review the excluded-project reasons below.")
    excluded = [(key, picker.eligibility(key, state.A)["reasons"]) for key in RECOMMENDATION_PROJECT_KEYS
                if not picker.eligibility(key, state.A)["eligible"]]
    if excluded:
        with st.expander("Projects filtered by your hard limits"):
            for key, reasons in excluded:
                st.markdown(f"**{_label(key)}**: " + "; ".join(reasons))

    research = state.get("career_research")
    if research:
        with st.expander("Career-target research (TinyFish)", expanded=bool(research.get("sources"))):
            if research.get("error"):
                st.warning(f"Career search was unavailable: {research['error']}")
            if research.get("signals"):
                st.caption("Relevant domains found: " + ", ".join(research["signals"]))
            for source in research.get("sources", []):
                st.markdown(f"[{source['title']}]({source['url']})")
                st.caption(source["excerpt"][:500])
            if not research.get("sources") and not research.get("error"):
                st.info("TinyFish found no readable career pages; ranking uses your survey and confirmed resume factors.")

    with st.container(border=True):
        st.markdown("**Or describe your own idea**")
        idea_text = st.text_input("e.g. a car that follows my hand", label_visibility="collapsed")
        if st.button("Match my idea") and idea_text.strip():
            state.idea = pipeline.map_idea(idea_text)
            if state.idea["project"]:
                state.pick = state.idea["project"]
        if state.idea:
            message = (f"Closest supported project: {_label(state.idea['project'])}. " if state.idea["project"] else "Not supported yet. ") + state.idea["reason"]
            (st.success if state.idea["project"] else st.warning)(message)

    if state.pick:
        project = PROJECT_CATALOG[state.pick]
        meta = PROJECT_FACTOR_CATALOG[state.pick]
        fit = picker.factor_breakdown(state.pick, state.A)
        left, right = st.columns([2, 3])
        with left, st.container(border=True):
            st.markdown(f"### {project['label']} · {picker.factor_score(state.pick, state.A)}% fit")
            st.write(project["desc"])
            st.markdown(f"**Domain:** {meta['domain']}  \n**Estimated build time:** {meta['build_hours']} hours  \n**Estimated cost:** ₹{meta['cost_inr']:,}  \n**Parts availability in India:** {meta['parts_availability_india']}/5")
            st.markdown("**Tools required:** " + ", ".join(sorted(meta["tools_required"])))
            st.markdown("**Required skills:** " + ", ".join(sorted(meta["required_skills"])))
            st.markdown("**Prerequisites:** " + ", ".join(sorted(meta["prerequisites"])))
            if meta.get("safety"):
                st.warning("Safety considerations: " + ", ".join(sorted(meta["safety"])))
            st.caption("Eight depth factors use 1–5 project ratings; build time, cost, availability, and tools use their stated units. Values are estimates.")
            rows = [{"Factor": label, "Project rating": f"{meta[key]}/5", "Fit": f"{fit[key]}%"} for label, key in picker.AXES]
            st.dataframe(rows, hide_index=True, use_container_width=True)
            evidence = [item for item in resume_data.get("skills", []) if item.get("confirmed") and item.get("id") in meta["required_skills"]]
            evidence += [item for item in resume_data.get("projects", []) if item.get("domain") == meta["domain"]]
            if evidence:
                st.markdown("**Confirmed resume evidence**")
                for item in evidence:
                    st.markdown(f"- {item['name']}: “{item['quote']}”")
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
            if project["bom_supported"]:
                if st.button("Build the BOM for this project"):
                    state.project = state.pick
                    state.budget = int(state.A.get("budget_inr") or 3500)
                    state.res = None
                    state.stage = "bom"
                    st.rerun()
            else:
                st.info("This is a recommendation candidate only. Its project-specific BOM is not in the builder yet.")
        with right, st.container(border=True):
            _show_chart(picker.chart_html(fit), 440)

    if st.button("Skip to BOM agent"):
        state.stage = "bom"
        st.rerun()