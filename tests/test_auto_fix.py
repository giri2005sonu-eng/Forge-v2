"""Tests for core.auto_fix: 1-click resolution of electrical and hardware incompatibilities."""
import pytest
from core import auto_fix, rules, data
from core.data import CATALOG

P = {p["id"]: p for p in CATALOG}

def test_auto_fix_logic_level_failure():
    # ESP32 (3.3V) with HC-SR04 (5V) triggers logic_level failure
    bad_build = {
        "controller": P["ctrl_esp32"],
        "driver": P["drv_tb6612"],
        "motor": P["mot_n20"],
        "battery": P["bat_2s"],
        "sensor": P["sen_hcsr04"]
    }
    st_before = {c["id"]: c["status"] for c in rules.evaluate(bad_build, data.RULES)}
    assert st_before["logic_level"] == "FAIL"

    fixes = auto_fix.get_fixes_for_rule("logic_level", bad_build)
    assert any(f["id"] == "add_level_shifter" for f in fixes)

    # Apply fix
    fixed_build = auto_fix.apply_auto_fix(bad_build, "add_level_shifter")
    eval_after = {c["id"]: c for c in rules.evaluate(fixed_build, data.RULES)}
    assert eval_after["logic_level"]["status"] == "PASS"
    assert "Bi-Directional Logic Level Shifter" in eval_after["logic_level"]["msg"]

def test_auto_fix_motor_voltage_buck_converter():
    # 3S Battery (11.1V / 12.6V) with 6V N20 motors triggers motor_voltage failure
    bad_build = {
        "controller": P["ctrl_nano"],
        "driver": P["drv_tb6612"],
        "motor": P["mot_n20"],
        "battery": P["bat_3s"],
        "sensor": P["sen_line5"]
    }
    st_before = {c["id"]: c["status"] for c in rules.evaluate(bad_build, data.RULES)}
    assert st_before["motor_voltage"] == "FAIL"

    fixes = auto_fix.get_fixes_for_rule("motor_voltage", bad_build)
    fix_ids = [f["id"] for f in fixes]
    assert "insert_buck_converter" in fix_ids
    assert "swap_to_2s" in fix_ids

    # Option A: Buck converter
    fixed_buck = auto_fix.apply_auto_fix(bad_build, "insert_buck_converter")
    eval_buck = {c["id"]: c for c in rules.evaluate(fixed_buck, data.RULES)}
    assert eval_buck["motor_voltage"]["status"] == "PASS"
    assert "LM2596" in eval_buck["motor_voltage"]["msg"]

def test_auto_fix_motor_voltage_swap_to_2s():
    bad_build = {
        "controller": P["ctrl_nano"],
        "driver": P["drv_tb6612"],
        "motor": P["mot_n20"],
        "battery": P["bat_3s"],
        "sensor": P["sen_line5"]
    }
    # Option B: Swap to 2S
    fixed_2s = auto_fix.apply_auto_fix(bad_build, "swap_to_2s")
    assert fixed_2s["battery"]["id"] == "bat_2s"
    eval_2s = {c["id"]: c for c in rules.evaluate(fixed_2s, data.RULES)}
    assert eval_2s["motor_voltage"]["status"] == "PASS"

def test_auto_fix_bluetooth():
    # Nano without Bluetooth when Bluetooth is requested
    parts = {
        "controller": P["ctrl_nano"],
        "driver": P["drv_l298n"],
        "motor": P["mot_n20"],
        "battery": P["bat_2s"],
        "sensor": P["sen_line5"]
    }
    st_before = {c["id"]: c["status"] for c in rules.evaluate(parts, data.RULES, needs_bluetooth=True)}
    assert st_before["bluetooth"] == "FAIL"

    fixes = auto_fix.get_fixes_for_rule("bluetooth", parts)
    fix_ids = [f["id"] for f in fixes]
    assert "add_hc05_bluetooth" in fix_ids
    assert "upgrade_to_esp32" in fix_ids

    # Option A: Add HC-05
    fixed_hc05 = auto_fix.apply_auto_fix(parts, "add_hc05_bluetooth")
    eval_hc05 = {c["id"]: c for c in rules.evaluate(fixed_hc05, data.RULES, needs_bluetooth=True)}
    assert eval_hc05["bluetooth"]["status"] == "PASS"

    # Option B: Upgrade to ESP32
    fixed_esp = auto_fix.apply_auto_fix(parts, "upgrade_to_esp32")
    assert fixed_esp["controller"]["id"] == "ctrl_esp32"
    eval_esp = {c["id"]: c for c in rules.evaluate(fixed_esp, data.RULES, needs_bluetooth=True)}
    assert eval_esp["bluetooth"]["status"] == "PASS"

def test_auto_fix_list_structure():
    # Test on custom builds where parts is a list of dicts
    parts_list = [
        {"role": "controller", "name": "ESP32 DevKit", "id": "ctrl_esp32", "specs": {"logic_v": 3.3}},
        {"role": "sensor", "name": "HC-SR04", "id": "sen_hcsr04", "specs": {"supply_min_v": 5, "supply_max_v": 5}}
    ]
    fixed_list = auto_fix.apply_auto_fix(parts_list, "add_level_shifter")
    assert len(fixed_list) == 3
    assert any("shifter" in p.get("id", "") for p in fixed_list)

def test_standby_fix_activates_ready_and_replaces():
    from core import optimizer as opt, component_catalog as cat
    records = cat.load()
    base = {
        "controller": P["ctrl_esp32"],
        "driver": P["drv_tb6612"],
        "motor": P["mot_n20"],
        "battery": P["bat_2s"],
        "sensor": P["sen_line5"]
    }
    nano = P["ctrl_nano"]

    # 1. Without fix: replacing ESP32 with Nano fails bluetooth
    prop_no_fix = opt.replace(base, "controller", nano)
    res_no_fix = opt.compare_builds(base, prop_no_fix, {"controller"}, records, live={}, needs_bt=True)
    sm_no_fix = res_no_fix["summary_proposed"]
    assert sm_no_fix["ready"] is False
    assert sm_no_fix["state"] == "incompatible"

    # 2. Standby stage: HC-05 module added on standby
    fix = auto_fix.AUTO_FIX_CATALOG["add_hc05_bluetooth"]
    prop_staged = dict(prop_no_fix)
    prop_staged["comms"] = fix["part"]
    res_staged = opt.compare_builds(base, prop_staged, {"controller", "comms"}, records, live={}, needs_bt=True)
    sm_staged = res_staged["summary_proposed"]
    # Now build is ready, which activates the "Keep this replacement" button!
    assert sm_staged["ready"] is True
    assert sm_staged["fail"] == 0

    # 3. Simulate keeping replacement and standby fix
    opt_kept = {}
    opt_kept["controller"] = nano
    opt_kept["comms"] = fix["part"]
    current = dict(base)
    for r_k, p in opt_kept.items():
        if r_k in current:
            current = opt.replace(current, r_k, p)
        else:
            current[r_k] = p
    assert current["controller"]["id"] == "ctrl_nano"
    assert current["comms"]["id"] == "mod_hc05"

