from core.data import CATALOG, RULES
from core.pipeline import select
from core.rules import evaluate
P = {p["id"]: p for p in CATALOG}
def parts(c, d, m, b, s): return dict(controller=P[c], driver=P[d], motor=P[m], battery=P[b], sensor=P[s])
def st(res): return {c["id"]: c["status"] for c in res}

def test_known_good_has_no_fail():
    assert not [c for c in evaluate(parts("ctrl_nano", "drv_l298n", "mot_n20", "bat_2s", "sen_line5"), RULES) if c["status"] == "FAIL"]
def test_single_cell_with_l298n_fails():
    s = st(evaluate(parts("ctrl_nano", "drv_l298n", "mot_n20", "bat_1s", "sen_line5"), RULES))
    assert s["batt_driver_min"] == "FAIL" and s["ctrl_vin"] == "FAIL"
def test_esp32_with_5v_only_sensor_fails():
    assert st(evaluate(parts("ctrl_esp32", "drv_tb6612", "mot_n20", "bat_2s", "sen_hcsr04"), RULES))["logic_level"] == "FAIL"
def test_missing_spec_is_unknown_not_guessed():
    p = parts("ctrl_nano", "drv_l298n", "mot_n20", "bat_2s", "sen_line5"); p["motor"] = dict(P["mot_n20"], specs={})
    assert st(evaluate(p, RULES))["driver_stall"] == "UNKNOWN"
def test_bluetooth_requirement():
    assert st(evaluate(parts("ctrl_nano", "drv_l298n", "mot_n20", "bat_2s", "sen_line5"), RULES, True))["bluetooth"] == "FAIL"
def test_select_returns_valid_build_under_budget():
    r = select("line_follower", 3000)
    assert r["best"] and r["best"]["fails"] == 0 and r["best"]["cost"] <= 3000
def test_impossible_budget_returns_none():
    assert select("line_follower", 500)["best"] is None
