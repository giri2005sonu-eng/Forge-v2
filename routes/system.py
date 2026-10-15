"""System health, metadata, settings, rules listing, and regression tests."""
from __future__ import annotations

from fastapi import APIRouter

from core.common.schemas import SettingsRequest
from core.common.state import get_state
from core.common.testrunner import load_cases, run_case
from core.engineering.catalog import load_catalog, load_seed
from routes.helpers import get_rules

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "BuilderBot Engineering Agent",
        "version": "2.0.0",
    }


@router.get("/meta")
def meta():
    state = get_state()
    catalog = load_catalog(state.spec_defs)
    return {
        "robot_types": state.config["robot_types"],
        "categories": {k: {"label": k.title(), "specs": v} for k, v in state.spec_defs.items()},
        "catalog_count": len(catalog),
        "live_price_count": sum(1 for p in catalog.values() if p.price and p.price.evidence.method == "scraped"),
        "gemini_configured": bool(state.runtime_keys["gemini"]),
        "tinyfish_configured": bool(state.runtime_keys["tinyfish"]),
        "model": state.runtime_keys["model"],
    }


@router.get("/settings/status")
def settings_status():
    state = get_state()
    return state.get_settings_status()


@router.post("/settings")
def settings(body: SettingsRequest):
    state = get_state()
    return state.update_keys(
        gemini_key=body.gemini_api_key,
        tinyfish_key=body.tinyfish_api_key,
        model=body.gemini_model,
    )


@router.get("/rules")
def rules():
    rules_list = get_rules()
    return {
        "items": [
            {
                "id": r.id,
                "category": r.category,
                "title": r.title,
                "needs": r.needs,
                "check": r.check,
                "when": r.when or "",
            }
            for r in rules_list
        ]
    }


@router.post("/tests")
def run_tests():
    state = get_state()
    seed = load_seed(state.spec_defs)
    rules_list = get_rules()
    results = [run_case(c, seed, rules_list, state.config) for c in load_cases()]
    return {
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "items": results,
    }
