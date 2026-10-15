"""Build optimization, requirement parsing, and component swap routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.common.schemas import BuildRequest, ParseRequest, Requirements, SwapRequest
from core.common.state import get_state
from core.engineering.catalog import load_catalog
from core.engineering.selector import _make_build, qty_for, select_build
from core.intelligence.llm import LLMError
from core.intelligence.parser import heuristic_parse, parse_requirements
from routes.helpers import get_llm, get_rules, serialize_build

router = APIRouter(prefix="/api", tags=["Builds"])


@router.post("/parse")
def parse(body: ParseRequest):
    state = get_state()
    try:
        llm = get_llm()
        if llm:
            req, notes = parse_requirements(llm.json, body.prompt, state.config)
        else:
            req, notes = heuristic_parse(body.prompt, state.config)
            notes.insert(0, "Gemini is not configured; used the local keyword parser.")
        if req is None:
            raise HTTPException(422, "The robot type could not be mapped to a supported type.")
        return {
            "requirements": req.model_dump(mode="json"),
            "notes": notes,
            "parser": "gemini" if llm else "keyword",
        }
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/build")
def build(body: BuildRequest):
    state = get_state()
    try:
        req = Requirements(**body.model_dump())
        ctx = req.to_ctx(state.config)
        rules = get_rules()
        catalog = load_catalog(state.spec_defs)

        selection = select_build(catalog, ctx, state.config, rules)
        chosen = selection.chosen

        state.active.update({
            "requirements": req,
            "selection": selection,
            "build": chosen,
            "ctx": ctx,
        })

        return {
            "message": selection.message,
            "within_budget": selection.within_budget,
            "evaluated": selection.evaluated,
            "truncated": selection.truncated,
            "excluded": selection.excluded,
            "alternatives": [serialize_build(x) for x in selection.alternatives[:5]],
            "rejected_count": len(selection.rejected),
            "chosen": serialize_build(chosen),
            "naive": serialize_build(selection.naive) if selection.naive else None,
            "fail_stats": dict(selection.fail_stats),
        }
    except Exception as e:
        raise HTTPException(400, f"Build failed: {e}")


@router.post("/swap")
def swap(body: SwapRequest):
    state = get_state()
    if not state.active.get("build") or not state.active.get("ctx"):
        raise HTTPException(409, "Build a BOM before testing component swaps.")

    catalog = load_catalog(state.spec_defs)
    rules = get_rules()
    parts = dict(state.active["build"].parts)

    for cat, pid in body.part_ids.items():
        p = catalog.get(pid)
        if p is None or p.category != cat:
            raise HTTPException(422, f"Invalid replacement for {cat}")
        parts[cat] = p

    qty = {c: qty_for(c, p, state.active["ctx"]) for c, p in parts.items()}
    b = _make_build(parts, qty, state.active["ctx"], state.config, rules)
    return {
        "build": serialize_build(b),
        "cost_delta": b.total - state.active["build"].total,
    }
