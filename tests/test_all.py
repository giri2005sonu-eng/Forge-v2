import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog import load_seed, normalize_part  # noqa: E402
from core.config import DATA_DIR, load_config, load_spec_defs  # noqa: E402
from core.live import (discover_parts, extract_from_page, pick_urls, refresh_part,  # noqa: E402
                       verify_extraction)
from core.parser import heuristic_parse, parse_requirements  # noqa: E402
from core.rules import RuleError, load_rules  # noqa: E402
from core.schemas import Requirements  # noqa: E402
from core.selector import select_build  # noqa: E402
from core.testrunner import load_cases, run_case  # noqa: E402
from core.llm import parse_json_loose  # noqa: E402

SD = load_spec_defs()
CFG = load_config()
SEED = load_seed(SD)
RULES = load_rules(DATA_DIR / "rules.yaml", SD)


# ---------------- validator proof set
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"][:40])
def test_validator_known_builds(case):
    r = run_case(case, SEED, RULES, CFG)
    assert r["ok"], r


def test_unknown_is_never_pass():
    case = [c for c in load_cases() if "UNKNOWN" in c["name"]][0]
    r = run_case(case, SEED, RULES, CFG)
    assert r["actual"] == "unverified" and not r["fails"]


# ---------------- rule engine safety
def _write_rules(tmp_path, check, needs, extra=""):
    p = tmp_path / "r.yaml"
    p.write_text(f"""rules:
  - id: x
    title: t
    category: power
    needs: {needs}
    check: "{check}"
    pass_msg: "ok"
    fail_msg: "no"
{extra}""")
    return p


def test_rule_rejects_code_execution(tmp_path):
    with pytest.raises(RuleError):
        load_rules(_write_rules(tmp_path, "__import__('os').system('x')", "[battery.nominal_v]"), SD)


def test_rule_rejects_unknown_spec(tmp_path):
    with pytest.raises(RuleError):
        load_rules(_write_rules(tmp_path, "battery.voltage > 1", "[battery.voltage]"), SD)


def test_rule_requires_refs_in_needs(tmp_path):
    with pytest.raises(RuleError):
        load_rules(_write_rules(tmp_path, "battery.nominal_v > battery.max_v", "[battery.nominal_v]"), SD)


# ---------------- selector
def test_default_selection_is_verified_and_in_budget():
    ctx = Requirements().to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    b = sel.chosen
    assert b and b.status == "verified" and sel.within_budget and b.total <= ctx["budget_inr"]
    assert sel.naive.fail_ids, "naive cheapest build should be incompatible (before/after story)"


def test_bluetooth_forces_esp32():
    ctx = Requirements(needs_bluetooth=True).to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    assert sel.chosen.parts["controller"].id == "ctrl_esp32"


def test_obstacle_avoider_with_esp32_avoids_5v_sensor():
    ctx = Requirements(robot_type="obstacle_avoider", needs_bluetooth=True, budget_inr=3500).to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    assert sel.chosen.parts["sensor"].id == "sen_vl53"


def test_cost_changes_the_pick():
    """Live prices must be able to change the answer (TinyFish must not be decorative)."""
    ctx = Requirements().to_ctx(CFG)
    base = select_build(SEED, ctx, CFG, RULES).chosen.parts["driver"].id
    cat = {k: v.model_copy(deep=True) for k, v in SEED.items()}
    cat["drv_l298n"].price.value = 900.0
    assert select_build(cat, ctx, CFG, RULES).chosen.parts["driver"].id != base


def test_out_of_stock_part_is_excluded():
    from core.schemas import Spec
    ctx = Requirements().to_ctx(CFG)
    cat = {k: v.model_copy(deep=True) for k, v in SEED.items()}
    cat["ctrl_nano"].in_stock = Spec(value=False)
    sel = select_build(cat, ctx, CFG, RULES)
    assert sel.chosen.parts["controller"].id != "ctrl_nano"
    assert any(e["reason"] == "out of stock" for e in sel.excluded)


def test_over_budget_is_flagged_not_hidden():
    ctx = Requirements(budget_inr=1000).to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    assert sel.chosen and not sel.within_budget and sel.message


def test_no_valid_build_reports_cleanly():
    cat = {k: v for k, v in SEED.items() if k not in ("bat_2s",)}  # only batteries that can't work remain
    cat = {k: v for k, v in cat.items() if k not in ("bat_6aa",)}
    ctx = Requirements().to_ctx(CFG)
    sel = select_build(cat, ctx, CFG, RULES)
    assert sel.chosen is None and "No compatible build" in sel.message


# ---------------- parser
def test_parser_with_fake_llm():
    fake = lambda prompt, system: {"robot_type": "line_follower", "budget_inr": 2500, "motor_count": 4,
                                   "min_runtime_h": 2, "needs_bluetooth": True, "sensor_channels": None, "notes": []}
    req, notes = parse_requirements(fake, "x", CFG)
    assert req.budget_inr == 2500 and req.motor_count == 2 and req.needs_bluetooth
    assert any("one driver" in n for n in notes)


def test_parser_rejects_unsupported():
    req, notes = parse_requirements(lambda p, s: {"robot_type": "unsupported"}, "a drone", CFG)
    assert req is None and notes


def test_heuristic_parser():
    req, _ = heuristic_parse("line follower under Rs 2,500 with bluetooth, 2 hours", CFG)
    assert req.budget_inr == 2500 and req.needs_bluetooth and req.min_runtime_h == 2


def test_json_loose():
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('here you go: {"a": 2} thanks') == {"a": 2}


# ---------------- live extraction safeguards (no network)
PAGE = ("# L298N Motor Driver Module\nPrice: Rs. 1,299.00 In stock\n"
        "Max current: 2A per channel. Drive voltage 5V-35V. Logic voltage 5V.")


def _good_raw():
    return {"product_name": "L298N Motor Driver Module", "matches_requested_part": True,
            "price_inr": {"value": 1299, "quote": "Price: Rs. 1,299.00 In stock"},
            "in_stock": {"value": True, "quote": "In stock"},
            "specs": {"max_continuous_current_a": {"value": 2, "unit": "A", "quote": "Max current: 2A per channel"},
                      "motor_supply_max_v": {"value": 35, "unit": "V", "quote": "Drive voltage 5V-35V"}}}


def test_verified_values_accepted():
    ex = verify_extraction(_good_raw(), SD["driver"], PAGE)
    assert ex.price[0] == 1299 and ex.stock[0] is True
    assert ex.specs["max_continuous_current_a"][0] == 2.0 and not ex.rejected


def test_hallucinated_quote_is_rejected():
    raw = _good_raw()
    raw["specs"]["voltage_drop_v"] = {"value": 1.4, "unit": "V", "quote": "Voltage drop is 1.4V"}
    ex = verify_extraction(raw, SD["driver"], PAGE)
    assert "voltage_drop_v" not in ex.specs and any("voltage_drop_v" in r for r in ex.rejected)


def test_price_must_appear_in_quote_and_range():
    raw = _good_raw()
    raw["price_inr"] = {"value": 99, "quote": "Price: Rs. 1,299.00 In stock"}
    assert verify_extraction(raw, SD["driver"], PAGE).price is None
    raw["price_inr"] = {"value": 9999999, "quote": "Price: Rs. 1,299.00"}
    assert verify_extraction(raw, SD["driver"], PAGE).price is None


def test_out_of_range_spec_rejected():
    raw = _good_raw()
    raw["specs"]["max_continuous_current_a"] = {"value": 500, "unit": "A", "quote": "Max current: 2A per channel"}
    ex = verify_extraction(raw, SD["driver"], PAGE)
    assert "max_continuous_current_a" not in ex.specs


class FakeTF:
    def __init__(self, pages):
        self.pages = pages

    def search(self, q):
        return [{"url": u, "site_name": "robu.in", "title": "t"} for u in self.pages]

    def fetch(self, urls, ttl=0):
        return [{"url": u, "final_url": u, "text": self.pages[u]} for u in urls], []


def test_refresh_changes_price_and_adds_evidence():
    part = SEED["drv_l298n"]
    tf = FakeTF({"https://robu.in/l298n": PAGE})
    updated, rep = refresh_part(part, tf, lambda p, s: _good_raw(), SD, ["robu.in"])
    assert updated.price.value == 1299 and updated.price.evidence.method == "scraped"
    assert updated.price.evidence.source_url == "https://robu.in/l298n"
    assert updated.vendor == "robu.in"
    assert part.price.value == 130  # original untouched


def test_refresh_skips_non_matching_page():
    raw = _good_raw()
    raw["matches_requested_part"] = False
    updated, rep = refresh_part(SEED["drv_l298n"], FakeTF({"https://robu.in/x": PAGE}), lambda p, s: raw, SD, ["robu.in"])
    assert updated.price.value == 130 and rep["problems"]


def test_refresh_survives_llm_failure():
    def boom(p, s):
        raise RuntimeError("quota")
    updated, rep = refresh_part(SEED["drv_l298n"], FakeTF({"https://robu.in/x": PAGE}), boom, SD, ["robu.in"])
    assert updated.price.value == 130 and any("extraction failed" in p for p in rep["problems"])


def test_report_generation_supports_disabling_power_and_wiring():
    from core.power import analyze_power
    from core.wiring import generate_wiring_plan
    from core.reporting.export import generate_markdown_report

    ctx = Requirements().to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    build = sel.chosen
    power = analyze_power(build, CFG)
    wiring = generate_wiring_plan(build)

    md = generate_markdown_report(build, Requirements(), CFG, SD, power=power, wiring=wiring,
                                 include_power=False, include_wiring=False)
    assert "Power & Battery Discharge Analysis" not in md
    assert "Pinout & Interconnect Wiring Guide" not in md


def test_discover_creates_scraped_part_that_validates():
    parts, rep = discover_parts("driver", "q", FakeTF({"https://robu.in/l298n": PAGE}), lambda p, s: _good_raw(), SD, ["robu.in"])
    assert len(parts) == 1
    p = normalize_part(parts[0], SD)
    assert p.price.value == 1299 and p.specs["max_continuous_current_a"].evidence.quote


def test_pick_urls_prefers_known_vendors():
    res = [{"url": "https://youtube.com/x"}, {"url": "https://random.com/a"}, {"url": "https://www.robu.in/b"}]
    assert pick_urls(res, ["robu.in"], 3) == ["https://www.robu.in/b", "https://random.com/a"]


# ---------------- end-to-end: live refresh persists and changes the BOM
def test_e2e_live_refresh_changes_bom(tmp_path):
    import shutil
    from core.catalog import load_catalog, save_overlay
    shutil.copy(DATA_DIR / "parts_catalog.json", tmp_path / "parts_catalog.json")
    ctx = Requirements().to_ctx(CFG)
    before = select_build(load_catalog(SD, tmp_path), ctx, CFG, RULES).chosen
    assert before.parts["driver"].id == "drv_l298n"

    # Live page says the L298N now costs Rs 1,299 -> overlay -> a different driver should win.
    updated, _ = refresh_part(SEED["drv_l298n"], FakeTF({"https://robu.in/l298n": PAGE}),
                              lambda p, s: _good_raw(), SD, ["robu.in"])
    save_overlay([normalize_part(updated, SD)], tmp_path)
    after = select_build(load_catalog(SD, tmp_path), ctx, CFG, RULES).chosen
    assert after.parts["driver"].id != "drv_l298n"
    assert after.status == "verified"
    live = load_catalog(SD, tmp_path)["drv_l298n"]
    assert live.price.evidence.source_url == "https://robu.in/l298n" and live.price.evidence.quote
