"""Hybrid planning: learned store + dataset first, Gemini once, then never again for the same idea."""
import json
import pytest
from core import custom_bom, hybrid_bom, pipeline, project_store as ps, tf


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_LEARNED_PATH", str(tmp_path / "learned.json"))
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(tf, "cache_get", lambda k: None); monkeypatch.setattr(tf, "cache_set", lambda k, v: None)
    calls = {"n": 0}
    PLAN = dict(project_label="Plant watering robot", check_notes=["Check pump voltage"],
                components=[dict(name="Mini water pump", role="pump", qty=1, search_query="mini water pump 5V", why="moves water"),
                            dict(name="Soil moisture sensor", role="sensor", qty=2, search_query="soil moisture sensor")])
    class R:  text = json.dumps(PLAN)
    def gen(prompt, cfg, key): calls["n"] += 1; return R()
    monkeypatch.setattr(pipeline, "_generate", gen)
    return calls


def test_new_idea_costs_one_gemini_call_then_zero(store):
    c = {"n": 0}
    a = hybrid_bom.resolve("a robot that waters my plants", 3000, False, c)
    assert a["origin"] == "gemini" and a["gemini_calls"] == 1 and store["n"] == 1 and c["n"] == 1
    assert a["plan"]["parts"][0]["source"] == "gemini" and all(p["seed_price"] is None for p in a["plan"]["parts"])
    b = hybrid_bom.resolve("a robot that waters my plants", 3000, False, c)           # same idea
    d = hybrid_bom.resolve("Plants waters my robot that a", 3000, False, c)           # same words, other order
    assert b["origin"] == d["origin"] == "learned" and store["n"] == 1 and c["n"] == 1
    assert [p["name"] for p in b["plan"]["parts"]] == [p["name"] for p in a["plan"]["parts"]]


def test_learned_store_survives_restart_and_is_resanitised(store, tmp_path):
    hybrid_bom.resolve("a robot that waters my plants", None, False, {"n": 0})
    path = tmp_path / "learned.json"; data = json.loads(path.read_text())
    entry = next(iter(data["entries"].values())); assert entry["reviewed"] is False and entry["source"] == "gemini"
    entry["plan"]["components"].append(dict(name="Evil\x00part", qty=99999, search_query="x"))   # hand-edited / hostile file
    path.write_text(json.dumps(data))
    plan = hybrid_bom.resolve("a robot that waters my plants", None, False, {"n": 0})["plan"]
    assert plan["parts"][-1]["qty"] == custom_bom.MAX_QTY and "\x00" not in plan["parts"][-1]["name"] and store["n"] == 1


def test_different_quantity_is_a_different_idea(store):
    c = {"n": 0}
    hybrid_bom.resolve("drone with 4 motor", None, False, c); hybrid_bom.resolve("drone with 6 motor", None, False, c)
    assert store["n"] == 2 and ps.learned_count() == 2


def test_catalog_name_match_uses_dataset_with_zero_gemini(store):
    out = hybrid_bom.resolve("Camera-based line follower", None, False, {"n": 0})
    assert out["origin"] == "dataset" and out["plan"]["key"] == "general:vision_line_follower" and store["n"] == 0
    assert any(p["name"].startswith("Raspberry Pi") for p in out["plan"]["parts"])


def test_numbers_never_auto_match_the_catalog(store):
    out = hybrid_bom.resolve("line follower robot with 4 sensors", None, False, {"n": 0})
    assert out["origin"] != "dataset"


def test_ambiguous_idea_offers_suggestions_without_spending_gemini(store):
    out = hybrid_bom.resolve("maze solver", None, False, {"n": 0})
    assert out["plan"] is None and len(out["suggestions"]) >= 2 and store["n"] == 0
    forced = hybrid_bom.resolve("maze solver", None, False, {"n": 0}, skip_local=True)
    assert forced["origin"] == "gemini" and store["n"] == 1


def test_keyword_rules_still_route_to_rule_based_builds_for_free(store):
    out = hybrid_bom.resolve("a car that follows a black line", None, False, {"n": 0})
    assert out["origin"] == "rule" and out["project"] == "line_follower" and store["n"] == 0


def test_session_cap_and_missing_key(store, monkeypatch):
    monkeypatch.setenv("FORGE_GEMINI_PLANS_PER_SESSION", "1")
    c = {"n": 0}
    hybrid_bom.resolve("first brand new idea about bees", None, False, c)
    with pytest.raises(ValueError, match="used its 1"):
        hybrid_bom.resolve("second brand new idea about ants", None, False, c)
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        hybrid_bom.resolve("third brand new idea about wasps", None, False, {"n": 0})
    assert store["n"] == 1


def test_gemini_failure_saves_nothing_and_known_ideas_still_work(store, monkeypatch):
    def boom(*a, **k): raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(pipeline, "_generate", boom)
    with pytest.raises(ValueError, match="could not plan"):
        hybrid_bom.resolve("an idea about owls", None, False, {"n": 0})
    assert ps.learned_count() == 0
    assert hybrid_bom.resolve("Camera-based line follower", None, False, {"n": 0})["origin"] == "dataset"   # offline-safe


def test_learned_cap_drops_oldest(store, monkeypatch):
    monkeypatch.setattr(ps, "MAX_LEARNED", 3)
    for i in range(5):
        ps.save_learned(f"idea number {i} alpha", dict(label="L", parts=[dict(name="P", role="r", qty=1, query="some part")], notes=[]))
    assert ps.learned_count() == 3
