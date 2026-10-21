"""Human-reviewed role-to-skill mappings used to estimate portfolio relevance."""
import csv
from pathlib import Path

from .recommender_config import (
    IMPACT_BASE_RELEVANCE,
    IMPACT_RELEVANCE_WEIGHT,
    MAX_FACTOR_RATING,
    MAX_PROJECT_SKILLS_FOR_ROLE,
)

ROLE_SKILLS = {
    "embedded": {"embedded", "stm32", "rtos", "can_bus", "pcb_design", "embedded_linux", "fpga", "power_electronics"},
    "robotics": {"ros", "control", "motor_control", "sensors", "mechanical_design", "cad"},
    "ml_vision": {"ml", "vision", "python", "signal_processing"},
    "hardware": {"pcb_design", "power_electronics", "pcb_soldering", "fpga"},
    "iot": {"esp32", "iot_cloud", "rf_comms", "wireless_other", "bluetooth"},
}

CAREER_ROLE_MAP = {
    "embedded": "embedded",
    "robotics": "robotics",
    "vision": "ml_vision",
    "iot": "iot",
    "undecided": None,
    "sensing": "robotics",
    "mechanics": "robotics",
    "control": "robotics",
    "power": "hardware",
    "digital": "embedded",
    "fabrication": "hardware",
    "assistive": "robotics",
    "drones": "robotics",
    "space_aerospace": "embedded",
}

_OVERRIDE_FILE = Path(__file__).with_name("project_data") / "role_impact_overrides.csv"


def load_role_impact_overrides(path=_OVERRIDE_FILE):
    """Load optional hand-reviewed project/role impact values; absent file means no overrides."""
    if not path.exists():
        return {}
    overrides = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            try:
                impact = float(row.get("impact", ""))
            except (TypeError, ValueError):
                continue
            if row.get("id") and row.get("role") and 0 <= impact <= 1:
                overrides.setdefault(row["id"], {})[row["role"]] = impact
    return overrides


ROLE_IMPACT_OVERRIDES = load_role_impact_overrides()


def impact_for(project_key, project, roles):
    """Return normalized role-specific impact, or raw demo impact for unknown roles."""
    skills = set(project.get("required_skills", set()))
    impact_rating = project.get("portfolio_impact", 0) / MAX_FACTOR_RATING
    if not roles:
        return impact_rating
    scores = []
    for role in roles:
        override = ROLE_IMPACT_OVERRIDES.get(project_key, {}).get(role)
        if override is not None:
            scores.append(override)
        elif role not in ROLE_SKILLS:
            scores.append(impact_rating)
        else:
            denominator = min(MAX_PROJECT_SKILLS_FOR_ROLE, max(1, len(skills)))
            relevance = min(1.0, len(skills & ROLE_SKILLS[role]) / denominator)
            scores.append(
                impact_rating
                * (IMPACT_BASE_RELEVANCE + IMPACT_RELEVANCE_WEIGHT * relevance)
            )
    return max(scores, default=impact_rating)
