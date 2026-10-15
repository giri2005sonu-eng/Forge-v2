"""Catalog viewing, part inspection, and catalog management routes."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException

from core.common.schemas import Part
from core.common.state import get_state
from core.engineering.catalog import (
    load_catalog,
    normalize_part,
    reset_overlay,
    save_overlay,
)
from core.intelligence.sourcing import clear_cache
from routes.helpers import serialize_part

router = APIRouter(prefix="/api", tags=["Catalog"])


@router.get("/catalog")
def catalog(category: Optional[str] = None, q: Optional[str] = None):
    state = get_state()
    parts = list(load_catalog(state.spec_defs).values())
    if category:
        parts = [p for p in parts if p.category == category]
    if q:
        parts = [p for p in parts if q.lower() in (p.name + " " + p.vendor + " " + p.id).lower()]
    return {
        "items": [serialize_part(p) for p in parts],
        "total": len(parts),
    }


@router.get("/part/{part_id}")
def part_detail(part_id: str):
    state = get_state()
    p = load_catalog(state.spec_defs).get(part_id)
    if not p:
        raise HTTPException(404, "Part not found")
    return serialize_part(p)


@router.post("/catalog/add")
def catalog_add(body: dict):
    state = get_state()
    try:
        parts = [normalize_part(Part.model_validate(x), state.spec_defs) for x in body.get("items", [])]
        if not parts:
            raise HTTPException(422, "No parts supplied")
        save_overlay(parts)
        return {"added": len(parts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, str(e))


@router.post("/catalog/reset")
def catalog_reset():
    state = get_state()
    reset_overlay()
    clear_cache()
    state.reset_active()
    return {"status": "reset"}
