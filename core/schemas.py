"""Data models shared by every layer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Evidence(BaseModel):
    """Where a value came from. Every spec and price carries one."""
    source_url: Optional[str] = None
    retrieved_at: str = Field(default_factory=now_iso)
    method: Literal["curated", "scraped", "manual"] = "curated"
    quote: Optional[str] = None   # verbatim text from the page (scraped values only)
    note: Optional[str] = None


class Spec(BaseModel):
    value: Any = None             # float | str | bool | None
    unit: Optional[str] = None
    evidence: Evidence = Field(default_factory=Evidence)


class Part(BaseModel):
    id: str
    category: str
    name: str
    vendor: str = "Seed catalog (est.)"
    url: Optional[str] = None
    kind: Optional[str] = None            # sensors only: "line" | "distance"
    search_query: Optional[str] = None
    price: Optional[Spec] = None          # INR per unit
    in_stock: Optional[Spec] = None       # value True/False; None = unknown
    specs: dict[str, Spec] = Field(default_factory=dict)

    def spec_value(self, key: str) -> Any:
        s = self.specs.get(key)
        return None if s is None else s.value


class Requirements(BaseModel):
    robot_type: str = "line_follower"
    budget_inr: float = Field(3000, ge=500, le=200000)
    motor_count: int = Field(2, ge=1, le=2)
    min_runtime_h: float = Field(1.0, ge=0.1, le=48)
    needs_bluetooth: bool = False
    sensor_channels: Optional[int] = Field(None, ge=1, le=16)

    def to_ctx(self, config: dict) -> dict:
        rt = config["robot_types"][self.robot_type]
        return {
            "robot_type": self.robot_type,
            "budget_inr": float(self.budget_inr),
            "motor_count": int(self.motor_count),
            "min_runtime_h": float(self.min_runtime_h),
            "needs_bluetooth": bool(self.needs_bluetooth),
            "sensor_channels": int(self.sensor_channels or rt["default_sensor_channels"]),
        }


class EvidenceRef(BaseModel):
    part: str
    field: str
    value: Any
    unit: Optional[str] = None
    source_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    method: Optional[str] = None


class CheckResult(BaseModel):
    rule_id: str
    title: str
    category: str
    status: Literal["pass", "fail", "unknown", "skipped"]
    message: str
    missing: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
