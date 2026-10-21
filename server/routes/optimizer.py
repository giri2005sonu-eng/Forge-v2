from fastapi import APIRouter, Cookie, HTTPException
from typing import Optional

from core import component_catalog as cat, optimizer as opt
from core.data import PROJECTS
from server.schemas import OptimizerSwapRequest
from server.state import store

router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])


@router.get("/candidates")
def get_swap_candidates(role: str):
    """Return catalog candidates for a given role."""
    candidates = cat.candidates_for(role)
    return [{"id": c["id"], "name": c["name"], "price": c.get("seed_price")} for c in candidates]


@router.post("/evaluate")
def evaluate_swap(req: OptimizerSwapRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    if not parts:
        raise HTTPException(status_code=400, detail="No active BOM build")

    swap_part = cat.find_part(req.swap_part_id)
    if not swap_part:
        raise HTTPException(status_code=404, detail=f"Part '{req.swap_part_id}' not found")

    eval_res = opt.evaluate_swap(
        base_parts=parts,
        swap_role=req.role,
        swap_part=swap_part,
        project=session.project,
        budget=session.budget,
        bt=session.bluetooth or PROJECTS.get(session.project, {}).get("bt", False),
        live=session.live,
    )
    summary = opt.impact_summary(eval_res)
    return {"evaluation": eval_res, "summary": summary}


@router.post("/apply")
def apply_swap(req: OptimizerSwapRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    session.opt_swaps[req.role] = req.swap_part_id
    return {"status": "ok", "swaps": session.opt_swaps}


@router.post("/reset")
def reset_swaps(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    session.opt_swaps.clear()
    return {"status": "ok"}
