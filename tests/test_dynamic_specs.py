import json
import pytest
from core import custom_bom, part_specs as ps, pipeline


@pytest.fixture
def temp_specs_store(tmp_path, monkeypatch):
    test_path = tmp_path / "learned_specs.json"
    monkeypatch.setenv("FORGE_LEARNED_SPECS_PATH", str(test_path))
    return test_path


def test_library_parts_found_in_dataset(temp_specs_store):
    # Exact name
    s1 = ps.find_specs_in_dataset("Capacitive Soil Moisture Sensor")
    assert s1 and s1.get("interface") == "analog" and s1.get("supply_min_v") == 3.3

    # Smart alias matching for common library variants
    s2 = ps.find_specs_in_dataset("Arduino Uno R3 Compatible Board")
    assert s2 and s2.get("logic_v") == 5 and s2.get("clock_mhz") == 16

    s3 = ps.find_specs_in_dataset("L298N Dual Motor Driver")
    assert s3 and s3.get("channels") == 2 and s3.get("max_a") == 2.0

    # Unknown component
    assert ps.find_specs_in_dataset("Super Quantum Warp Drive 5000") is None
    assert ps.has_specs("Super Quantum Warp Drive 5000") is False


def test_dynamic_specs_store_persists_and_memoizes(temp_specs_store):
    assert ps.learned_specs_count() == 0
    pump_specs = {"supply_min_v": 2.5, "supply_max_v": 6.0, "nominal_v": 5.0, "current_ma": 150, "power_w": 1.2}

    saved = ps.save_learned_spec("5V Submersible Water Pump", pump_specs, source="gemini")
    assert saved is True
    assert ps.learned_specs_count() == 1

    # Check persistence on disk
    assert temp_specs_store.exists()
    disk_data = json.loads(temp_specs_store.read_text(encoding="utf-8"))
    assert "5v submersible water pump" in disk_data["specs"]

    # Check case-insensitive / whitespace-tolerant lookup
    retrieved = ps.find_learned_spec("  5V   submersible   WATER pump  ")
    assert retrieved is not None
    assert retrieved["supply_min_v"] == 2.5
    assert retrieved["nominal_v"] == 5.0

    # find_specs_in_dataset now immediately finds it
    dataset_specs = ps.find_specs_in_dataset("5V Submersible Water Pump")
    assert dataset_specs == retrieved
    assert ps.has_specs("5V Submersible Water Pump") is True


def test_clean_plan_preserves_dataset_specs_and_learns_new_specs(temp_specs_store):
    raw_plan = {
        "project_label": "Automated Plant Watering",
        "components": [
            {
                "name": "Arduino Uno R3 Compatible Board",
                "role": "controller",
                "qty": 1,
                "search_query": "Arduino Uno R3",
                "specs": {"logic_v": 3.3}  # Gemini wrongly guessing 3.3V, but dataset has 5V
            },
            {
                "name": "5V Submersible Water Pump",
                "role": "actuator",
                "qty": 1,
                "search_query": "5V mini water pump",
                "specs": {"supply_min_v": 2.5, "supply_max_v": 6.0, "nominal_v": 5.0, "current_ma": 180}
            }
        ]
    }

    plan = custom_bom.clean_plan(raw_plan, "plant watering")
    parts = {p["name"]: p for p in plan["parts"]}

    # 1. For Uno, dataset specs (logic_v=5) must win over remote guess
    assert parts["Arduino Uno R3 Compatible Board"]["specs"]["logic_v"] == 5

    # 2. For pump, because it wasn't in dataset, Gemini specs were stored into learned specs
    assert parts["5V Submersible Water Pump"]["specs"]["nominal_v"] == 5.0
    assert ps.has_specs("5V Submersible Water Pump") is True

    # Next time, even if Gemini provides NO specs, dataset lookup finds the learned specs
    raw_plan_2 = {
        "project_label": "Hydroponics System",
        "components": [
            {
                "name": "5V Submersible Water Pump",
                "role": "actuator",
                "qty": 2,
                "search_query": "5V mini water pump"
                # no specs provided
            }
        ]
    }
    plan_2 = custom_bom.clean_plan(raw_plan_2, "hydroponics")
    assert plan_2["parts"][0]["specs"]["nominal_v"] == 5.0


def test_fetch_and_apply_missing_specs_calls_gemini_only_for_missing(temp_specs_store, monkeypatch):
    calls = []
    def fake_generate(prompt, cfg, key):
        calls.append(prompt)
        reply = {
            "components": [
                {
                    "name": "Custom Acrylic Robot Chassis",
                    "specs": {"length_mm": 200, "width_mm": 150, "thickness_mm": 3, "material": "acrylic"}
                }
            ]
        }
        class R: text = json.dumps(reply)
        return R()

    monkeypatch.setattr(pipeline, "_generate", fake_generate)
    monkeypatch.setenv("GEMINI_API_KEY", "test_key")

    parts = [
        {"name": "Arduino Uno R3 Compatible Board", "role": "controller", "specs": {}},  # Present in dataset via alias
        {"name": "Custom Acrylic Robot Chassis", "role": "frame", "specs": {}}           # Missing in dataset
    ]

    custom_bom.fetch_and_apply_missing_specs(parts, key="test_key")

    # Only 1 Gemini call should have occurred, specifically asking for Custom Acrylic Robot Chassis
    assert len(calls) == 1
    assert "Custom Acrylic Robot Chassis" in calls[0]
    assert "Arduino Uno" not in calls[0]  # Already in dataset, so not asked!

    # Both parts now have specs
    assert parts[0]["specs"]["logic_v"] == 5
    assert parts[1]["specs"]["material"] == "acrylic"

    # And Custom Acrylic Robot Chassis is now stored in learned specs
    assert ps.find_learned_spec("Custom Acrylic Robot Chassis")["thickness_mm"] == 3

    # If called again with the same parts, 0 Gemini calls happen!
    calls.clear()
    custom_bom.fetch_and_apply_missing_specs(parts, key="test_key")
    assert len(calls) == 0


def test_learned_specs_in_compare_and_alternatives(temp_specs_store):
    ps.save_learned_spec("Custom Gear Motor 12V", {"nominal_v": 12, "rpm": 300, "torque_kgcm": 2.5, "stall_a": 1.2})
    ps.save_learned_spec("Custom High-Speed Motor 12V", {"nominal_v": 12, "rpm": 600, "torque_kgcm": 1.2, "stall_a": 1.8})

    s1 = ps.specs_for("Custom Gear Motor 12V")
    s2 = ps.specs_for("Custom High-Speed Motor 12V")
    assert s1["rpm"] == 300
    assert s2["rpm"] == 600

    # Side-by-side comparison
    cmp = ps.compare([("Custom Gear Motor 12V", s1), ("Custom High-Speed Motor 12V", s2)])
    assert "rpm" in [r["key"] for r in cmp["rows"]]
    html = ps.compare_html(cmp)
    assert "300 rpm" in html
    assert "600 rpm" in html
