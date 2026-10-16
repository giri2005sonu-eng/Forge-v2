import io
import pytest
from core import picker, resume
from core.data import PROJECTS

LF = "Built a line follower robot using Arduino, IR sensors and PID motor control. Soldered the PCB myself."
BT = "Made a Bluetooth car with ESP32 and an HC-05 module."


def test_every_project_has_resume_hints():
    assert set(PROJECTS) == set(resume.PROJECT_SKILLS) == set(resume.DIRECT)


def test_skills_found_with_short_evidence_and_no_raw_text_kept():
    r = resume.analyze(LF)
    assert {"line_following", "arduino", "sensors", "motor_control", "pcb_soldering"} <= set(r["skills"])
    assert set(r) == {"skills", "level", "interests"}
    assert all(len(v) <= 90 for v in r["skills"].values())


def test_same_resume_same_result():
    assert resume.analyze(LF) == resume.analyze(LF)


def test_empty_or_irrelevant_resume_adds_nothing():
    r = resume.analyze("Worked as a cashier. Good at teamwork.")
    assert r["skills"] == {} and r["level"] is None
    assert all(picker.score(k, {}, r) == picker.score(k, {}) for k in PROJECTS)


def test_no_resume_scores_are_unchanged():
    assert picker.rank({"skill": [2]}) == picker.rank({"skill": [2]}, None)


def test_resume_lifts_the_matching_project():
    r = resume.analyze(LF)
    assert picker.score("line_follower", {}, r) > picker.score("line_follower", {})
    assert picker.rank({}, r)[0][0] == "line_follower"
    r2 = resume.analyze(BT)
    assert picker.rank({}, r2)[0][0] == "bluetooth_car"


def test_affinity_is_between_0_and_1_and_direct_match_counts_double():
    full = dict(skills={n: "x" for n in resume.SKILLS}, level=3, interests=[])
    assert all(resume.affinity(k, full) == 1.0 for k in PROJECTS)
    assert all(resume.affinity(k, None) == 0.0 for k in PROJECTS)
    shared = dict(skills={"arduino": "x", "sensors": "x"}, level=2, interests=[])
    direct = dict(skills={"arduino": "x", "line_following": "x"}, level=2, interests=[])
    assert resume.affinity("line_follower", direct) > resume.affinity("line_follower", shared)


def test_direct_match_breaks_the_tie_between_similar_projects():
    r = resume.analyze(LF)
    top, second = picker.rank({}, r)[:2]
    assert top[0] == "line_follower" and top[1] > second[1]


def test_survey_answers_win_over_resume():
    r = resume.analyze(LF)  # resume says experienced
    assert picker.effective({"skill": [1]}, r)["skill"] == [1]
    assert picker.effective({}, r)["skill"] == [r["level"]]
    assert picker.effective({"int": ["wireless"]}, r)["int"] == ["wireless"]


def test_scores_stay_in_range():
    r = dict(skills={n: "x" for n in resume.SKILLS}, level=3, interests=["ai", "sensors"])
    assert all(0 <= s <= 100 for _, s in picker.rank({"goal": ["win"]}, r))


def test_already_mentions_flag():
    r = resume.analyze(LF)
    assert resume.already_mentions("line_follower", r) and not resume.already_mentions("bluetooth_car", r)


def test_extract_txt_and_rejects_other_types():
    assert "Arduino" in resume.extract_text("cv.txt", b"I know Arduino")
    with pytest.raises(ValueError):
        resume.extract_text("cv.exe", b"x")
    with pytest.raises(ValueError):
        resume.extract_text("cv.txt", b"   ")
    with pytest.raises(ValueError):
        resume.extract_text("cv.pdf", b"not a pdf")


def test_extract_rejects_big_files():
    with pytest.raises(ValueError):
        resume.extract_text("cv.txt", b"a" * (resume.MAX_BYTES + 1))


def test_extract_docx_roundtrip():
    docx = pytest.importorskip("docx")
    d = docx.Document(); d.add_paragraph("Skills: Arduino, ROS"); buf = io.BytesIO(); d.save(buf)
    assert set(resume.analyze(resume.extract_text("cv.docx", buf.getvalue()))["skills"]) == {"arduino", "ros"}


def test_extract_pdf_roundtrip():
    pytest.importorskip("pypdf"); reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    buf = io.BytesIO(); c = reportlab.Canvas(buf); c.drawString(72, 700, "Built an Arduino line follower"); c.save()
    assert "line_following" in resume.analyze(resume.extract_text("cv.pdf", buf.getvalue()))["skills"]
