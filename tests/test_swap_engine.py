"""Swap dataset + impact engine + silent fallback. Offline: the data generator is always a stub here."""
import copy, json, math, re, pytest
from core import impact, optimizer as opt, pipeline, profile_fill as pf, profiles, swap_dataset, component_catalog as cat
from core.data import CATALOG

RECS = cat.load(); P = {p["id"]: p for p in CATALOG}
def base(): return pipeline.select("line_follower", 3500, False, {})["best"]["parts"]

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_SWAP_STORE", str(tmp_path / "store.json"))
    monkeypatch.setattr(pf, "GENERATOR", None); pf._STATE.update(n=0, failed={}, last_error="")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

def boom(prompt): raise AssertionError("fallback must not be called for parts already in the dataset")
DUE = dict(name="Arduino Due", kind="mcu", price_inr=1800, attrs=dict(clock_mhz=84, flash_kb=512, sram_kb=96, cores=1, arch_bits=32, wifi=False, bluetooth=False, bt_classic=False,
           gpio=54, adc_channels=12, adc_bits=12, pwm_channels=12, logic_v=3.3, vin_min_v=7, vin_max_v=12, current_ma=100, weight_g=36))

# ---- curated dataset
def test_every_curated_profile_validates_and_is_complete():
    cur = json.load(open(profiles.CURATED))["profiles"]
    assert len(cur) >= 50
    for pid, p in cur.items():
        clean, bad = profiles.validate(p["role"], p["attrs"]); assert not bad and clean == p["attrs"], pid
        assert profiles.complete_enough(p["role"], clean), pid
def test_every_app_catalog_part_has_a_profile():
    for p in CATALOG: assert profiles.get(p["id"]), p["id"]
def test_pair_records_shipped_for_same_role_pairs():
    pairs = json.load(open(profiles.CURATED))["pairs"]
    assert swap_dataset.pair_key("controller", "ctrl_nano", "ctrl_esp32") in pairs and len(pairs) > 300

# ---- engine answers the user's example from the dataset, with no fallback call
def test_nano_to_esp32_reports_what_changes_without_fallback(monkeypatch):
    monkeypatch.setattr(pf, "GENERATOR", boom)
    b = base(); res = opt.compare_builds(b, opt.replace(b, "controller", P["ctrl_esp32"]), {"controller"}, RECS)
    text = " ".join(c["text"] for c in res["chips"]); k = {r["key"]: r for r in res["rows"]}
    assert "Gains Wi-Fi" in text and "Bluetooth" in text and "15.0x" in text and "level shifting" in text
    assert k["wifi"]["status"] == "improved" and k["processing"]["proposed"] == 240 and k["runtime"]["status"] == "reduced"
    assert k["speed"]["status"] == "not_affected" and res["lookup"] == {"controller": "dataset"} and k["runtime"]["quality"] == "typical"
def test_battery_voltage_scales_speed_and_torque_first_order():
    b = base(); k = {r["key"]: r for r in opt.compare_builds(b, opt.replace(b, "battery", P["bat_3s"]), {"battery"}, RECS)["rows"]}
    want = (11.1 - 2.0) / (7.4 - 2.0)       # L298N drops 2 V
    assert math.isclose(k["speed"]["proposed"] / k["speed"]["original"], want, rel_tol=1e-6)
    assert math.isclose(k["torque"]["proposed"] / k["torque"]["original"], want, rel_tol=1e-6)
def test_driver_drop_changes_efficiency_and_speed():
    b = base(); k = {r["key"]: r for r in opt.compare_builds(b, opt.replace(b, "driver", P["drv_tb6612"]), {"driver"}, RECS)["rows"]}
    assert k["efficiency"]["status"] == "improved" and k["speed"]["status"] == "improved" and k["wifi"]["status"] == "not_affected"
def test_motor_swap_changes_speed_torque_and_current():
    b = base(); k = {r["key"]: r for r in opt.compare_builds(b, opt.replace(b, "motor", P["mot_tt"]), {"motor"}, RECS)["rows"]}
    assert k["speed"]["status"] == "improved" and k["torque"]["status"] == "reduced" and k["runtime"]["status"] == "reduced"
def test_original_never_mutated():
    b = base(); before = copy.deepcopy(b); opt.compare_builds(b, opt.replace(b, "motor", P["mot_tt"]), {"motor"}, RECS); assert b == before
def test_new_goals_rank_with_values():
    r = opt.rank_candidates(base(), "motor", "higher_speed", RECS)
    vals = [o["rows"]["speed"]["proposed"] for o in r["ranked"]]
    assert r["rankable"] and vals == sorted(vals, reverse=True)
    assert opt.rank_candidates(base(), "controller", "higher_speed", RECS)["rankable"] is False     # a controller swap cannot change speed
def test_dataset_widens_candidate_pool():
    names = {c["name"] for c in opt.candidates(base(), "controller")}
    assert {"Raspberry Pi Pico (RP2040)", "ESP32-S3 DevKitC-1", "STM32 Black Pill (F411)"} <= names and len(names) > 15
    assert all(c["kind"] == "line" for c in opt.candidates(base(), "sensor", "line"))

# ---- silent fallback: miss -> generate -> validate -> store -> next time a plain read
def test_missing_part_is_generated_once_then_served_from_store(monkeypatch):
    calls = []
    def gen(prompt): calls.append(prompt); return json.dumps(DUE)
    monkeypatch.setattr(pf, "GENERATOR", gen)
    part = opt.custom_part("controller", "Arduino Due"); assert part and part["specs"]["logic_v"] == 3.3 and part["_estimated"] is True
    assert len(calls) == 1 and "Arduino Due" in calls[0]
    b = base(); res = opt.compare_builds(b, opt.replace(b, "controller", part), {"controller"}, RECS, allow_fill=False)
    assert res["lookup"] == {"controller": "computed"} and {r["key"]: r for r in res["rows"]}["processing"]["quality"] == "estimated"
    res2 = opt.compare_builds(b, opt.replace(b, "controller", part), {"controller"}, RECS, allow_fill=False); assert res2["lookup"] == {"controller": "dataset"}
    assert opt.custom_part("controller", "arduino due")["id"] == part["id"] and len(calls) == 1          # same name: no second call
    stored = json.load(open(profiles.store_path())); assert part["id"] in stored["profiles"] and stored["profiles"][part["id"]]["origin"] == "generated"
    assert part["id"] in {c["id"] for c in opt.candidates(b, "controller")}                               # now offered like any other part
def test_invalid_or_incomplete_data_is_rejected_and_not_retried(monkeypatch):
    calls = []
    def gen(prompt): calls.append(1); return json.dumps(dict(name="X", kind="mcu", attrs=dict(clock_mhz=9e9, logic_v=3.3, wifi=True, bluetooth=False)))
    monkeypatch.setattr(pf, "GENERATOR", gen)
    assert opt.custom_part("controller", "Mystery board") is None and opt.custom_part("controller", "Mystery board") is None and len(calls) == 1
    assert not json.load(open(profiles.store_path())).get("profiles") if profiles.store_path().exists() else True
def test_no_key_or_failure_is_silent_and_comparison_still_works(monkeypatch):
    assert opt.custom_part("controller", "Anything") is None
    def bad(prompt): raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(pf, "GENERATOR", bad); assert opt.custom_part("motor", "Some motor") is None
    ghost = dict(id="x_ghost", role="controller", name="Ghost board", seed_price=300, query="ghost", kind="mcu", specs={})
    b = base(); res = opt.compare_builds(b, opt.replace(b, "controller", ghost), {"controller"}, RECS)
    k = {r["key"]: r for r in res["rows"]}
    assert k["wifi"]["status"] == "unknown" and res["data_gaps"] == ["Ghost board"] and k["cost"]["status"] != "unknown"
def test_generated_profile_feeds_compatibility_rules(monkeypatch):
    monkeypatch.setattr(pf, "GENERATOR", lambda p: json.dumps(DUE)); part = opt.custom_part("controller", "Arduino Due")
    b = opt.replace(base(), "sensor", P["sen_hcsr04"]); res = opt.compare_builds(b, opt.replace(b, "controller", part), {"controller"}, RECS)
    assert {c["rule_id"]: c["status"] for c in res["compat_proposed"]}["logic_level"] == "FAIL"           # 3.3 V board + 5 V ultrasonic
def test_store_write_is_atomic_json_and_curated_file_untouched():
    before = profiles.CURATED.read_bytes()
    for i in range(3): profiles.add_profile(dict(id=f"gen_controller_t{i}", role="controller", name=f"T{i}", price_inr=None, kind="mcu", attrs=DUE["attrs"], origin="generated", confidence="estimated"))
    assert len(json.load(open(profiles.store_path()))["profiles"]) == 3 and profiles.CURATED.read_bytes() == before

# ---- nothing in user-facing text names the data source
def test_user_facing_text_never_mentions_the_fallback(monkeypatch):
    monkeypatch.setattr(pf, "GENERATOR", lambda p: json.dumps(DUE)); part = opt.custom_part("controller", "Arduino Due"); b = base()
    for new in (P["ctrl_esp32"], part):
        res = opt.compare_builds(b, opt.replace(b, "controller", new), {"controller"}, RECS)
        blob = json.dumps([res["rows"], res["chips"], opt.plain_explanation(res)]).lower()
        assert not re.search(r"gemini|\bai\b|llm|generated|language model", blob)
