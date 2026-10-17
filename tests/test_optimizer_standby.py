"""Tests for standby auto-resolve staging and commit flow in Project Optimizer."""
import copy
from core import auto_fix, component_catalog as cat, optimizer as opt, pipeline
from core.data import CATALOG, PROJECTS

def test_standby_fix_staging_and_commit():
    records = cat.load()
    P = {p["id"]: p for p in CATALOG}
    base = {
        "controller": P["ctrl_esp32"],
        "driver": P["drv_tb6612"],
        "motor": P["mot_n20"],
        "battery": P["bat_2s"],
        "sensor": P["sen_line5"]
    }
    nano = P["ctrl_nano"]
    role = "controller"
    pid = nano["id"]

    # Simulating UI Session State
    S = {
        "opt_base": copy.deepcopy(base),
        "opt_kept": {},
        "opt_standby_fixes": {}
    }

    # Step 1: Candidate initially proposed without fix
    proposed = opt.replace(base, role, nano)
    res1 = opt.compare_builds(base, proposed, {role}, records, live={}, needs_bt=True)
    sm1 = res1["summary_proposed"]
    assert sm1["ready"] is False
    assert sm1["fail"] > 0

    # Step 2: User clicks 1-Click Auto-Resolve Action for HC-05
    # The fix is staged on standby (NOT in opt_kept yet!)
    fixes = auto_fix.get_fixes_for_rule("bluetooth", proposed)
    hc05_fix = next(f for f in fixes if f["id"] == "add_hc05_bluetooth")
    S["opt_standby_fixes"].setdefault(pid, {})[hc05_fix["id"]] = copy.deepcopy(hc05_fix)

    assert S["opt_kept"] == {}
    assert pid in S["opt_standby_fixes"]

    # Step 3: Streamlit rerun: Candidate is re-evaluated with standby fix
    proposed2 = opt.replace(base, role, nano)
    staged_fixes = S["opt_standby_fixes"].get(pid, {})
    changed_roles = {role}
    for f_id, fix in staged_fixes.items():
        f_part = copy.deepcopy(fix["part"])
        if fix.get("action") == "swap":
            swap_role = fix.get("swap_role", f_part.get("role"))
            proposed2[swap_role] = f_part
            changed_roles.add(swap_role)
        else:
            role_key = f_part.get("role", "mod_" + f_id)
            if role_key in proposed2:
                role_key = f"{role_key}_{f_id}"
            f_part["role"] = role_key
            proposed2[role_key] = f_part
            changed_roles.add(role_key)

    res2 = opt.compare_builds(base, proposed2, changed_roles, records, live={}, needs_bt=True)
    sm2 = res2["summary_proposed"]
    # The compatibility rule now passes, making ready=True, activating "Keep this replacement"!
    assert sm2["ready"] is True
    assert sm2["fail"] == 0

    # Step 4: User clicks "Keep this replacement"
    # S.opt_kept receives the candidate replacement AND the staged standby parts
    S["opt_kept"][role] = copy.deepcopy(nano)
    staged = S["opt_standby_fixes"].pop(pid, {})
    for f_id, fix in staged.items():
        f_part = copy.deepcopy(fix["part"])
        if fix.get("action") == "swap":
            swap_role = fix.get("swap_role", f_part.get("role"))
            S["opt_kept"][swap_role] = f_part
        else:
            role_key = f_part.get("role", "mod_" + f_id)
            if role_key in S["opt_kept"]:
                role_key = f"{role_key}_{f_id}"
            f_part["role"] = role_key
            S["opt_kept"][role_key] = f_part

    assert "controller" in S["opt_kept"]
    assert "comms" in S["opt_kept"]
    assert S["opt_kept"]["controller"]["id"] == "ctrl_nano"
    assert S["opt_kept"]["comms"]["id"] == "mod_hc05"
    assert pid not in S["opt_standby_fixes"]

    # Step 5: Updated 'current' build contains both
    current = dict(base)
    for r_k, p in S["opt_kept"].items():
        if r_k in current:
            current = opt.replace(current, r_k, p)
        else:
            current[r_k] = copy.deepcopy(p)

    assert current["controller"]["name"] == "Arduino Nano"
    assert current["comms"]["name"] == "HC-05 Bluetooth Serial Module"
