"""Live web scraping, TinyFish seller discovery, and Gemini quote-checking routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.common.schemas import (
    DiscoverRequest,
    ImportUrlRequest,
    LiveRefreshRequest,
    PriceCheckRequest,
)
from core.common.state import get_state
from core.engineering.catalog import load_catalog, normalize_part, save_overlay
from core.intelligence.live import discover_parts, import_part_from_url, refresh_part
from core.intelligence.llm import LLMError
from core.intelligence.sourcing import check_prices, find_sources
from core.intelligence.tinyfish import TinyFishError
from routes.helpers import get_llm, get_tf, serialize_part

router = APIRouter(prefix="/api", tags=["Sourcing & Live"])


@router.get("/part/{part_id}/sources")
def part_sources(part_id: str, refresh: bool = False, min_links: int = 5):
    """TinyFish Search -> at least `min_links` selling links for this part."""
    state = get_state()
    p = load_catalog(state.spec_defs).get(part_id)
    if not p:
        raise HTTPException(404, "Part not found")
    import app as appmod
    tf_getter = getattr(appmod, "_tf", get_tf)
    tf = tf_getter()
    if not tf:
        raise HTTPException(400, "TinyFish API key is not configured. Add it in Settings & API keys.")
    fn = getattr(appmod, "find_sources", find_sources)
    try:
        return fn(
            p, tf, state.config["allowed_vendor_domains"],
            target=max(1, min(min_links, 8)), refresh=refresh
        )
    except (TinyFishError, RuntimeError) as e:
        raise HTTPException(502, f"TinyFish search failed: {e}")


@router.post("/part/{part_id}/sources/prices")
def part_source_prices(part_id: str, body: PriceCheckRequest):
    """TinyFish Fetch (live page) -> Gemini extraction -> quote-verified price per link."""
    state = get_state()
    p = load_catalog(state.spec_defs).get(part_id)
    if not p:
        raise HTTPException(404, "Part not found")
    tf, llm = get_tf(), get_llm()
    if not tf or not llm:
        raise HTTPException(400, "Configure both Gemini and TinyFish API keys in Settings first.")
    try:
        return check_prices(p, body.urls, tf, llm.json, state.spec_defs)
    except (TinyFishError, LLMError) as e:
        raise HTTPException(502, str(e))


@router.post("/live/refresh")
def live_refresh(body: LiveRefreshRequest):
    state = get_state()
    if not (state.runtime_keys["gemini"] and state.runtime_keys["tinyfish"]):
        raise HTTPException(400, "Configure both Gemini and TinyFish API keys in Settings first.")
    if body.category not in state.spec_defs:
        raise HTTPException(422, "Unknown category")

    catalog = load_catalog(state.spec_defs)
    chosen = [catalog[i] for i in body.part_ids if i in catalog and catalog[i].category == body.category]
    if not chosen:
        raise HTTPException(422, "No valid parts selected for this category")

    reports = []
    tf = get_tf()
    llm = get_llm()

    for p in chosen:
        try:
            refreshed, report = refresh_part(
                p, tf, llm.json, state.spec_defs, state.config["allowed_vendor_domains"],
                max_pages=body.pages_per_part
            )
            if refreshed:
                save_overlay([normalize_part(refreshed, state.spec_defs)])
            reports.append({"part": p.name, "report": report})
        except Exception as e:
            reports.append({"part": p.name, "error": str(e)})

    return {"results": reports}


@router.post("/live/discover")
def live_discover(body: DiscoverRequest):
    state = get_state()
    if not (state.runtime_keys["gemini"] and state.runtime_keys["tinyfish"]):
        raise HTTPException(400, "Configure both Gemini and TinyFish API keys in Settings first.")
    if body.category not in state.spec_defs:
        raise HTTPException(422, "Unknown category")

    try:
        known = {p.url for p in load_catalog(state.spec_defs).values() if p.url}
        found, report = discover_parts(
            body.category, body.query, get_tf(), get_llm().json,
            state.spec_defs, state.config["allowed_vendor_domains"],
            kind=body.kind, known_urls=known
        )
        return {"items": [serialize_part(p) for p in found], "report": report}
    except (TinyFishError, LLMError) as e:
        raise HTTPException(502, str(e))


@router.post("/live/import-url")
def live_import(body: ImportUrlRequest):
    state = get_state()
    if not (state.runtime_keys["gemini"] and state.runtime_keys["tinyfish"]):
        raise HTTPException(400, "Configure both Gemini and TinyFish API keys in Settings first.")
    if body.category not in state.spec_defs:
        raise HTTPException(422, "Unknown category")

    try:
        p, report = import_part_from_url(
            body.url, body.category, get_tf(), get_llm().json, state.spec_defs, kind=body.kind
        )
        return {"part": serialize_part(p) if p else None, "report": report}
    except (TinyFishError, LLMError) as e:
        raise HTTPException(502, str(e))
