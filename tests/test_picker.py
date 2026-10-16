import json
from core import picker, pipeline
from core.data import PROJECTS

def test_beginner_short_time_gets_simple_builds():
    top = [k for k, _ in picker.rank({"time": [2], "skill": [1], "budget": [2000], "goal": ["learn"]})[:2]]
    assert "bluetooth_car" in top

def test_unfinished_projects_are_hidden():
    assert not {"sumo_bot", "maze_solver"} & set(PROJECTS)

def test_no_answers_still_ranks_everything():
    r = picker.rank({}); assert len(r) == len(PROJECTS) and all(0 <= s <= 100 for _, s in r)

def test_multiple_answers_are_flexible():
    tight = picker.score("line_follower", {"time": [1]}); flexible = picker.score("line_follower", {"time": [1, 45]})
    assert flexible > tight

def test_chart_has_every_axis_label():
    h = picker.chart_html(picker.fits("line_follower", {}))
    assert all(name in h for name, _ in picker.AXES) and h.count("<polygon") == len(picker.AXES)

def test_every_project_builds_a_valid_bom():
    for k in PROJECTS:
        r = pipeline.select(k, 5000, PROJECTS[k]["bt"])
        assert r["best"] and r["best"]["fails"] == 0, k

def test_bluetooth_car_needs_bluetooth_controller_and_no_sensor():
    b = pipeline.select("bluetooth_car", 5000, True)["best"]
    assert b["parts"]["controller"]["id"] == "ctrl_esp32" and b["parts"]["sensor"].get("none")
    assert "logic_level" not in {c["id"] for c in b["checks"]}

class R:
    def __init__(self, d): self.text = json.dumps(d)
class C:
    def __init__(self, d): self.models = type("M", (), {"generate_content": lambda s, **k: R(d)})()

def test_idea_maps_to_supported_project(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = C(dict(project="line_follower", reason="follows a path"))
    assert pipeline.map_idea("car that follows a black path")["project"] == "line_follower"
def test_unsupported_or_invented_project_is_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = C(dict(project="quadcopter", reason="flies"))
    assert pipeline.map_idea("a drone")["project"] is None
