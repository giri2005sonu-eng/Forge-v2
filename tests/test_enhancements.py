import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog import load_seed, normalize_part
from core.config import DATA_DIR, load_config, load_spec_defs
from core.export import generate_html_report, generate_markdown_report
from core.live import import_part_from_url
from core.power import analyze_power
from core.rules import load_rules
from core.schemas import Requirements
from core.selector import select_build, shipping_breakdown
from core.wiring import generate_wiring_plan

SD = load_spec_defs()
CFG = load_config()
SEED = load_seed(SD)
RULES = load_rules(DATA_DIR / "rules.yaml", SD)


class FakeTF:
    def __init__(self, pages):
        self._pages = pages

    def fetch(self, urls, ttl=0):
        found = [{"url": u, "text": self._pages[u]} for u in urls if u in self._pages]
        errs = [{"url": u, "error": "404"} for u in urls if u not in self._pages]
        return found, errs


PAGE = "L298N dual motor driver module for hobby robotics. Price: Rs 1,299. Max current 2.0 A."


def test_wiring_plan_generation():
    ctx = Requirements().to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    wiring = generate_wiring_plan(sel.chosen)
    assert wiring.common_ground_required
    assert len(wiring.connections) >= 5
    assert any(c.wire_type == "Ground" for c in wiring.connections)
    assert "mermaid" in wiring.mermaid_diagram or "flowchart" in wiring.mermaid_diagram
    assert len(wiring.assembly_steps) >= 5


def test_power_analysis():
    ctx = Requirements().to_ctx(CFG)
    sel = select_build(SEED, ctx, CFG, RULES)
    power = analyze_power(sel.chosen, CFG)
    assert power is not None
    assert power.system_idle_current_a > 0
    assert power.system_typical_current_a > power.system_idle_current_a
    assert power.system_peak_stall_current_a >= power.system_typical_current_a
    assert power.runtime_typical_h > 0
    assert power.battery_safety_margin_pct >= 0


def test_export_reports():
    ctx = Requirements().to_ctx(CFG)
    req = Requirements()
    sel = select_build(SEED, ctx, CFG, RULES)
    md = generate_markdown_report(sel.chosen, req, CFG, SD)
    html = generate_html_report(sel.chosen, req, CFG, SD)
    assert "# Robot Engineering Report" in md
    assert "Bill of Materials" in md
    assert "<!DOCTYPE html>" in html
    assert "Compatibility Checks" in html


def test_import_part_from_url():
    url = "https://robu.in/product/test-part"
    tf = FakeTF({url: PAGE})
    raw = {
        "product_name": "L298N Dual Motor Driver",
        "price_inr": {"value": 1299.0, "quote": "Price: Rs 1,299"},
        "in_stock": {"value": True, "quote": "L298N dual motor driver"},
        "specs": {"max_continuous_current_a": {"value": 2.0, "quote": "Max current 2.0 A."}},
    }
    part, rep = import_part_from_url(url, "driver", tf, lambda p, s: raw, SD)
    assert part is not None
    assert part.name == "L298N Dual Motor Driver"
    assert part.price.value == 1299.0
    assert part.specs["max_continuous_current_a"].value == 2.0
    assert part.vendor == "robu.in"


def test_shipping_free_threshold_robu():
    from core.schemas import Part, Spec
    part = SEED["mot_tt"].model_copy(deep=True)
    part.vendor = "robu.in"
    part.price = Spec(value=1050.0, unit="INR")
    rows, total = shipping_breakdown({"motor": part}, {"motor": 1}, CFG)
    assert rows[0]["vendor"] == "robu.in"
    assert rows[0]["subtotal"] == 1050.0
    assert rows[0]["shipping"] == 0.0  # Free above 999
    assert total == 0.0
