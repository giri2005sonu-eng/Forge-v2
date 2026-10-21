from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SurveyAnswerRequest(BaseModel):
    answers: Dict[str, Any]
    step: Optional[int] = None


class SurveyRankRequest(BaseModel):
    answers: Optional[Dict[str, Any]] = None
    limit: int = 5


class CareerResearchRequest(BaseModel):
    query: str


class IdeaMatchRequest(BaseModel):
    text: str


class ResumeConfirmRequest(BaseModel):
    group: str  # "skills", "languages", "tools", "projects"
    index: int
    confirmed: bool


class BomGenerateRequest(BaseModel):
    project: Optional[str] = None
    budget: int = 3500
    bluetooth: bool = False
    custom_idea: Optional[str] = None
    skip_local: bool = False


class BomChoiceRequest(BaseModel):
    action: str = Field(..., description="'pick', 'manual', or 'reset'")
    part_id: Optional[str] = None
    url: Optional[str] = None
    price: Optional[float] = None
    name: Optional[str] = None


class DeliveryOptimizeRequest(BaseModel):
    shipping_fee: Optional[float] = None
    free_threshold: Optional[float] = None


class OptimizerSwapRequest(BaseModel):
    role: str
    swap_part_id: str


class GuidesResearchRequest(BaseModel):
    project_label: Optional[str] = None


class SpecsCompareRequest(BaseModel):
    part_name: str
    compare_with: Optional[List[str]] = None


class CartCheckRequest(BaseModel):
    url: str
    expected_price: float


class StateResponse(BaseModel):
    stage: str
    project: str
    budget: int
    bluetooth: bool
    survey_step: int
    survey_answers: Dict[str, Any]
    bom_origin: Optional[str]
    has_custom: bool
    has_res: bool
