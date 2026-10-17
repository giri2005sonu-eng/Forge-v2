"""Typed specs for the whole parts library, side-by-side comparison, and the generic spec check."""
import json
from core import ledger, part_specs as ps, pipeline, project_store, specs

LIB = ps._lib()


def test_every_library_part_has_specs_or_a_stated_reason():
    assert len(LIB) >= 231
    assert [k for k in LIB if k not in ps.SPECS and k not in ps.NO_SPECS] == []
    assert not set(ps.SPECS) & set(ps.NO_SPECS)
    assert [k for k in list(ps.SPECS) + list(ps.NO_SPECS) if k not in LIB] == []   # no stale keys


def test_every_spec_key_is_defined_and_ranges_are_sane():
    assert {k for s in ps.SPECS.values() for k in s} <= set(ps.SPEC_DEFS)
    for lo, hi in (("vin_min_v", "vin_max_v"), ("supply_min_v", "supply_max_v"), ("min_v", "max_v"), ("temp_min_c", "temp_max_c")):
        assert [k for k, s in ps.SPECS.items() if lo in s and hi in s and s[lo] > s[hi]] == []
    for k, s in ps.SPECS.items():
        assert s, k
        for key, v in s.items():
            assert isinstance(v, (bool, str)) or v > 0 or key.endswith("_c"), (k, key, v)   # only temperatures may be zero or negative


def test_battery_specs_are_internally_consistent():
    for k, s in ps.SPECS.items():
        if "cells_s" in s and "nominal_v" in s and "max_v" in s and k not in ("bat_aa4",):
            assert abs(s["nominal_v"] - 3.7 * s["cells_s"]) < 0.6 and abs(s["max_v"] - 4.2 * s["cells_s"]) < 0.01, k


def test_dataset_plan_parts_carry_specs():
    plan = project_store.get_plan("general:led_chaser")
    by_key = {p["id"]: p for p in plan["parts"]}
    assert by_key["d_nano"]["specs"]["logic_v"] == 5 and by_key["d_nano"]["specs"]["flash_kb"] == 32
    assert all(isinstance(p["specs"], dict) for p in plan["parts"])
    p = by_key["d_nano"]; p["specs"]["logic_v"] = 99
    assert ps.specs_for("nano")["logic_v"] == 5          # callers get copies, the table is not mutated


def test_name_lookup_is_exact_and_case_insensitive():
    assert ps.specs_for_name("hc-sr04 ultrasonic")["range_cm"] == 400
    assert ps.specs_for_name("HC-SR04 ultrasonic sensor from somewhere") == {} and ps.specs_for_name("") == {}


def test_compare_marks_the_best_value_per_row():
    t = ps.compare([("HC-SR04", ps.SPECS["hcsr04"]), ("VL53L0X", ps.SPECS["tof"]), ("TF-Luna", ps.SPECS["tf_luna"])])
    rows = {r["key"]: r for r in t["rows"]}
    assert rows["range_cm"]["best"] == [2] and rows["min_range_cm"]["best"] == [0] and rows["current_ma"]["best"] == [0]
    assert rows["interface"]["best"] == [] and rows["supply_min_v"]["best"] == []   # no direction -> no winner
    assert rows["sample_hz"]["values"] == [None, None, 250]                          # missing stays missing, never guessed


def test_compare_does_not_crown_ties_or_single_values():
    t = ps.compare([("a", dict(max_a=2.0)), ("b", dict(max_a=2.0))]); assert t["rows"][0]["best"] == []
    t = ps.compare([("a", dict(max_a=2.0)), ("b", dict())]); assert t["rows"][0]["best"] == []


def test_booleans_are_not_numbers():
    assert not ps.is_number(True) and ps.is_number(1) and ps.fmt("wifi", True) == "Yes" and ps.fmt("channels", 1) == "1"
    assert "wifi" not in ps.numeric_specs(ps.SPECS["esp32"]) and ps.numeric_specs(ps.SPECS["esp32"])["clock_mhz"] == 240


def test_alternatives_share_spec_keys_and_skip_self():
    alts = ps.alternatives("driver", ps.SPECS["l298n"], exclude_name="L298N driver", limit=3, min_shared=3)
    names = [n for _, n, _ in alts]
    assert "L298N driver" not in names and "TB6612FNG driver" in names
    assert ps.alternatives("driver", {}, limit=3) == []     # no typed specs, nothing is comparable


def test_compare_html_escapes_and_highlights():
    t = ps.compare([("<b>x</b>", dict(max_a=1)), ("y", dict(max_a=2))])
    h = ps.compare_html(t)
    assert "&lt;b&gt;" in h and "<b>x</b>" not in h and 'class="best"' in h


def test_has_number_matches_whole_numbers_only():
    assert specs.has_number("Input 7-12V", 7) and specs.has_number("Price 1,299.00", 1299)
    assert not specs.has_number("current 0.85 A", 0.8) and not specs.has_number("Rs. 1,250", 5)
    assert specs.has_number("stall current 800 mA", 0.8, "A") and not specs.has_number("stall current 800 mA", 0.8, "V")


class R:
    def __init__(self, d): self.text = json.dumps(d)
class G:
    def __init__(self, d): self.calls = []; self.models = type("M", (), {"generate_content": lambda s, **k: (self.calls.append(k) or R(d))})()


def test_spec_check_works_for_a_library_part(monkeypatch):
    part = dict(id="d_hcsr04", name="HC-SR04 ultrasonic", role="sensor", specs=ps.specs_for("hcsr04"))
    page = "HC-SR04 Working Voltage: DC 5V. Working Current: 15mA. Ranging distance: 2cm - 400cm. Measuring angle 15 degree"
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    pipeline._G = G(dict(range_cm=dict(value=400, quote="Ranging distance: 2cm - 400cm"), min_range_cm=dict(value=2, quote="Ranging distance: 2cm - 400cm"),
                         current_ma=dict(value=20, quote="Working Current: 15mA"), supply_min_v=dict(value=5, quote="made up")))
    found = specs.find_specs(part, page, "x")
    assert set(found) == {"range_cm", "min_range_cm"}      # wrong number for the quote (20 vs 15mA) and an invented quote are both rejected
    rows = {r["spec"]: r for r in specs.compare(part, found)}
    assert rows["range_cm"]["status"] == "match" and rows["current_ma"]["status"] == "not stated" and rows["range_cm"]["label"] == "Max range"
    assert "interface" not in rows                           # text specs are never number-checked
    assert specs.summarize(list(rows.values()))["match"] == 2


def test_spec_check_batches_keys_and_flags_differences(monkeypatch):
    big = dict(id="x", name="Big part", role="sensor", specs={k: 1.0 for k in list(ps.SPEC_DEFS)[:30] if ps.SPEC_DEFS[k][1]})
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = G({})
    specs.find_specs(big, "page", "x")
    assert len(pipeline._G.calls) == -(-len(specs.checkable(big)) // specs.BATCH) and len(pipeline._G.calls) > 1
    p = dict(id="y", name="Y", role="driver", specs=dict(max_a=2.0))
    row = specs.compare(p, dict(max_a=dict(value=1.2, quote="1.2A", url="u")))[0]
    assert row["status"] == "differs" and row["delta_pct"] == -40


def test_ledger_labels_library_specs_as_seed_with_units():
    part = dict(id="d_tof", name="VL53L0X ToF distance sensor", role="sensor", seed_price=None, specs=ps.specs_for("tof"))
    rows = [r for r in ledger.rows({"sensor": part}, {}) if r["field"] == "range_cm"]
    assert rows and rows[0]["status"] == "seed" and rows[0]["unit"] == "cm" and rows[0]["value"] == 200


def test_plural_role_names_for_the_compare_switch():
    assert ps.plural("controller") == "microcontrollers" and ps.plural("driver") == "motor drivers" and ps.plural("weird") == "weird parts"
    assert all(ps.plural(v["role"]) for v in LIB.values())
