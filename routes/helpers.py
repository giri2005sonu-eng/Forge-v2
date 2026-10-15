"""Shared serialization helpers and client factories for API routes."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from core.common.schemas import Part
from core.common.state import get_state
from core.engineering.catalog import load_catalog
from core.engineering.power import analyze_power
from core.engineering.rules import load_rules
from core.engineering.selector import Build
from core.engineering.wiring import generate_wiring_plan
from core.intelligence.llm import DEFAULT_MODEL, GeminiClient
from core.intelligence.tinyfish import TinyFishClient
from core.reporting.bom import bom_table, checks_table, ledger_table


def get_rules():
    state = get_state()
    from core.common.config import DATA_DIR
    return load_rules(DATA_DIR / "rules.yaml", state.spec_defs)


def get_llm() -> Optional[GeminiClient]:
    state = get_state()
    key = state.runtime_keys["gemini"]
    model = state.runtime_keys["model"] or DEFAULT_MODEL
    return GeminiClient(key, model) if key else None


def get_tf() -> Optional[TinyFishClient]:
    state = get_state()
    key = state.runtime_keys["tinyfish"]
    return TinyFishClient(key) if key else None


def serialize_part(p: Part) -> dict[str, Any]:
    d = p.model_dump(mode="json")
    d["price_value"] = p.price.value if p.price else None
    d["price_method"] = p.price.evidence.method if p.price else "none"
    d["stock_value"] = p.in_stock.value if p.in_stock else None
    d["specs_flat"] = {k: v.value for k, v in p.specs.items()}
    return d


def serialize_build(b: Optional[Build]) -> Optional[dict[str, Any]]:
    if b is None:
        return None
    state = get_state()
    power = analyze_power(b, state.config)
    wiring = generate_wiring_plan(b)
    bom = bom_table(b).to_dict(orient="records")
    ledger = ledger_table(b, state.spec_defs).to_dict(orient="records")
    checks = checks_table(b).to_dict(orient="records")
    budget_inr = (state.active["ctx"] or {}).get("budget_inr")

    return {
        "status": b.status,
        "counts": b.counts,
        "parts_cost": b.parts_cost,
        "shipping_total": b.shipping_total,
        "total": b.total,
        "budget_inr": budget_inr,
        "budget_remaining": (budget_inr - b.total) if budget_inr is not None else 0,
        "parts": {
            cat: {
                **serialize_part(p),
                "qty": b.qty.get(cat, 1),
                "line_total": b.qty.get(cat, 1) * (p.price.value if p.price else 0),
            }
            for cat, p in b.parts.items()
        },
        "shipping_rows": b.shipping_rows,
        "checks": [
            {
                "rule_id": c.rule_id,
                "title": c.title,
                "category": c.category,
                "status": c.status,
                "message": c.message,
                "missing": c.missing,
                "evidence": [e.model_dump(mode="json") for e in c.evidence],
            }
            for c in b.checks
        ],
        "bom": bom,
        "ledger": ledger,
        "power": asdict(power) if power else None,
        "wiring": {
            "connections": [asdict(x) for x in wiring.connections],
            "warnings": wiring.warnings,
            "assembly_steps": wiring.assembly_steps,
            "mermaid_diagram": wiring.mermaid_diagram,
        },
    }
