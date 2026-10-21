from fastapi import APIRouter

from core.recommendation_catalog import STAR_PROJECTS

router = APIRouter(prefix="/api/stars", tags=["star projects"])


@router.get("")
def list_star_projects():
    return {"projects": STAR_PROJECTS, "count": len(STAR_PROJECTS)}
