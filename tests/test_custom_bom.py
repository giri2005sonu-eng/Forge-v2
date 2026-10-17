import datetime as dt
import json

import pytest

from core import bill, custom_bom, ledger, pipeline, tf

DAY = dt.date(2026, 10, 17)


class R:
    def __init__(self, d): self.text = json.dumps(d)
class G:
    def __init__(self, d): self.models = type("M", (), {"generate_content": lambda s, **k: R(d)})()
def gem(monkeypatch, d):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = G(d)

DRONE = dict(project_label="Quadcopter drone", check_notes=["ESC current must exceed motor current", "Check battery cell count"],
             components=[dict(name="Brushless motor 2207", role="motor", qty=4, search_query="2207 brushless motor 2400KV", why="Spins the propellers"),
                         dict(name="30A ESC", role="esc", qty=4, search_query="30A BLHeli ESC", why="Drives each motor"),
                         dict(name="Flight controller", role="controller", qty=1, search_query="F405 flight controller"),
                         dict(name="Brushless motor 2207", qty=9, search_query="duplicate")])


def test_clean_plan_keeps_quantity_dedupes_and_has_no_prices():
    plan = custom_bom.clean_plan(DRONE, "drone with 4 motor")
    assert [p["name"] for p in plan["parts"]] == ["Brushless motor 2207", "30A ESC", "Flight controller"]
    assert plan["parts"][0]["qty"] == 4 and all(p["seed_price"] is None for p in plan["parts"])
    assert plan["label"] == "Quadcopter drone" and len(plan["notes"]) == 2


def test_clean_plan_rejects_junk_and_clamps():
    plan = custom_bom.clean_plan({"components": ["x", None, {"name": ""}, {"name": "Prop", "qty": 9999, "search_query": ""},
                                                 {"name": "Bad\x00qty", "qty": "abc"}]}, "an idea")
    assert [p["name"] for p in plan["parts"]] == ["Prop", "Bad qty"]
    assert plan["parts"][0]["qty"] == custom_bom.MAX_QTY and plan["parts"][0]["query"] == "Prop" and plan["parts"][1]["qty"] == 1
    assert plan["label"] == "an idea"
    assert custom_bom.clean_plan("not a dict")["parts"] == []


def test_clean_plan_caps_part_count():
    many = {"components": [{"name": f"Part {i}"} for i in range(50)]}
    assert len(custom_bom.clean_plan(many)["parts"]) == custom_bom.MAX_PARTS


def test_ids_differ_between_ideas_so_offers_never_leak():
    assert custom_bom.part_id("Battery", "3S lipo") != custom_bom.part_id("Battery", "18650 pack")


def test_plan_components_calls_gemini_and_validates(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    gem(monkeypatch, DRONE)
    plan = custom_bom.plan_components("drone with 4 motor", 5000)
    assert plan["parts"][0]["qty"] == 4 and plan["parts"][0]["custom"]


def test_plan_components_needs_a_key_and_an_idea(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        custom_bom.plan_components("a drone")
    with pytest.raises(ValueError, match="Type what"):
        custom_bom.plan_components("   ")


def test_plan_components_reports_empty_and_failed_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    gem(monkeypatch, {"components": []})
    with pytest.raises(ValueError, match="no usable components"):
        custom_bom.plan_components("a drone")
    monkeypatch.setattr(pipeline, "_generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(ValueError, match="could not plan"):
        custom_bom.plan_components("another idea")


def test_gemini_names_go_to_tinyfish_with_their_search_phrase(monkeypatch):
    plan = custom_bom.clean_plan(DRONE)
    seen = []
    monkeypatch.setattr(pipeline, "source_part", lambda part, log=print: seen.append(part["query"]) or [dict(url="https://a.in/x", price=500.0, name="n", quote="Rs. 500", in_stock=True)])
    live = custom_bom.source_all(plan["parts"], {}, log=lambda m: None)
    assert sorted(seen) == sorted(["2207 brushless motor 2400KV", "30A BLHeli ESC", "F405 flight controller"]) and set(live) == {p["id"] for p in plan["parts"]}


def test_one_failed_part_does_not_stop_the_others(monkeypatch):
    plan = custom_bom.clean_plan(DRONE)
    def fake(part, log=print):
        if part["name"] == "30A ESC": raise RuntimeError("search down")
        return [dict(url="https://a.in/x", price=100.0, name="n", quote="Rs. 100", in_stock=True)]
    monkeypatch.setattr(pipeline, "source_part", fake)
    logs = []
    live = custom_bom.source_all(plan["parts"], {}, log=logs.append)
    assert len(live) == 2 and any("search down" in m for m in logs)


def test_bill_uses_quantity_and_leaves_unpriced_parts_out_of_the_total():
    plan = custom_bom.clean_plan(DRONE)
    parts = custom_bom.parts_map(plan)
    motor, esc, fc = plan["parts"]
    live = {motor["id"]: [dict(url="https://a.in/m", price=700.0, name="2207 motor", quote="Rs. 700", in_stock=True)],
            esc["id"]: [dict(url="https://a.in/e", price=None)]}
    b = bill.make(parts, live, {}, 5000, plan["label"], DAY)
    assert b["tot"]["subtotal"] == 700 * 4 and b["tot"]["n_live"] == 1 and b["tot"]["n_missing"] == 2 and b["tot"]["n_seed"] == 0
    assert [l["qty"] for l in b["lines"]] == [4, 4, 1] and b["lines"][1]["source"] == "missing" and b["lines"][1]["unit"] is None
    assert "not in total" in b["html"] and b["pdf"][:4] == b"%PDF"


def test_ledger_marks_missing_price_instead_of_inventing_one():
    plan = custom_bom.clean_plan(DRONE)
    rows = ledger.rows(custom_bom.parts_map(plan), {}, {})
    assert rows and all(r["status"] == "unverified" and r["value"] == "" for r in rows)
    assert {r["role"] for r in rows} == {"motor", "esc", "controller"}


def test_existing_seed_builds_are_unchanged():
    best = pipeline.select("line_follower", 5000, False, {})["best"]["parts"]
    b = bill.make(best, {}, {}, 5000, "Line follower", DAY)
    assert b["tot"]["n_missing"] == 0 and b["tot"]["n_seed"] == len(b["lines"])
    assert [l["qty"] for l in b["lines"] if l["role"] == "motor"] == [2]
