"""Streamlit flow: dropdown (0 Gemini) and 'build anything new' (1 Gemini, then remembered)."""
import json, pathlib
import pytest
from streamlit.testing.v1 import AppTest
from core import pipeline, tf

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_LEARNED_PATH", str(tmp_path / "learned.json"))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(tf, "cache_get", lambda k: None); monkeypatch.setattr(tf, "cache_set", lambda k, v: None)
    calls = {"n": 0}
    plan = dict(project_label="Plant watering robot", check_notes=["Check pump voltage"],
                components=[dict(name="Mini water pump", role="pump", qty=1, search_query="mini water pump 5V", why="moves water")])
    class R: text = json.dumps(plan)
    def gen(p, c, k): calls["n"] += 1; return R()
    monkeypatch.setattr(pipeline, "_generate", gen)
    return calls


def app():
    at = AppTest.from_file(APP, default_timeout=30); at.session_state["stage"] = "bom"; at.run(); return at


def click(at, label):
    [b for b in at.button if b.label == label][0].click().run()


def test_dropdown_lists_168_and_uses_no_gemini(env):
    at = app(); assert not at.exception
    assert len(at.selectbox(key="bom_catalog_pick").options) == 168
    at.selectbox(key="bom_catalog_pick").set_value("competition:omnidirectional_striker_bot").run()
    click(at, "Generate BOM"); assert not at.exception
    assert env["n"] == 0
    text = " ".join(m.value for m in at.markdown) + " ".join(s.value for s in at.subheader) + " ".join(i.value for i in at.info)
    assert "Omnidirectional" in text and "Robo Soccer" in text and "Energy-storing kicker" in text
    assert at.session_state["custom"]["origin"] == "dataset" and len(at.session_state["custom"]["parts"]) >= 10
    assert any("No Gemini call" in s.value for s in at.success)


def test_rule_checked_project_from_dropdown_still_uses_rule_builder(env):
    at = app(); at.selectbox(key="bom_catalog_pick").set_value("general:line_follower").run(); click(at, "Generate BOM")
    assert not at.exception and at.session_state["res"]["best"] and at.session_state["custom"] is None and env["n"] == 0


def test_software_only_project_says_so(env):
    at = app(); at.selectbox(key="bom_catalog_pick").set_value("general:ros2_gazebo_sim").run(); click(at, "Generate BOM")
    assert not at.exception and any("Software only" in i.value for i in at.info) and env["n"] == 0


def test_new_idea_calls_gemini_once_then_is_remembered(env):
    at = app(); at.text_input(key="bom_new_idea").set_value("a robot that waters my plants").run(); click(at, "Plan new build")
    assert not at.exception and env["n"] == 1 and at.session_state["custom"]["origin"] == "gemini"
    click(at, "Plan new build"); assert env["n"] == 1 and at.session_state["custom"]["origin"] == "learned"
    fresh = app()                                                    # a brand new visitor: store persists on disk
    fresh.text_input(key="bom_new_idea").set_value("a robot that waters my plants").run(); click(fresh, "Plan new build")
    assert env["n"] == 1 and fresh.session_state["custom"]["origin"] == "learned"


def test_similar_catalog_projects_are_offered_before_gemini(env):
    at = app(); at.text_input(key="bom_new_idea").set_value("maze solver").run(); click(at, "Plan new build")
    assert not at.exception and env["n"] == 0 and any("Use “" in b.label for b in at.button)
    click(at, [b.label for b in at.button if b.label.startswith("Use “")][0])
    assert env["n"] == 0 and at.session_state["custom"] is not None or at.session_state["res"] is not None
