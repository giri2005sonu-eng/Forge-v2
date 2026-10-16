"""Candidate catalog for recommendation-only projects, separate from BOM-supported builds."""
import csv
from collections import Counter
from pathlib import Path

from .data import PROJECTS, PROJECT_FACTORS as BUILT_FACTORS

DATA_DIR = Path(__file__).with_name("project_data")
RATING_FIELDS = {
    "difficulty": "difficulty",
    "electronics": "electronics",
    "programming": "programming",
    "fabrication": "mechanical",
    "control_math": "control_math",
    "ai_vision": "ai_ml",
    "wireless_iot": "wireless",
    "portfolio_impact": "demo_impact",
}
DOMAIN_TAGS = {
    "embedded_basics": "embedded", "stm32_embedded": "embedded", "rtos_firmware": "embedded",
    "mobile_robots": "robotics", "ros_robotics": "robotics", "drones_flying": "drones",
    "arms_mechatronics": "mechanics", "iot_home": "iot", "vision_ai": "vision",
    "energy_power": "power", "comms_wireless": "iot", "wearables_assistive": "assistive",
    "env_audio_display": "sensing", "pcb_cad_fab": "fabrication", "advanced_control": "control",
    "fpga_digital": "digital",
}
TOOL_NAMES = {
    "soldering": "soldering_iron", "hand_tools": "hand_tools", "multimeter": "multimeter",
    "3d_printer": "3d_printer", "oscilloscope": "oscilloscope", "logic_analyzer": "logic_analyzer",
}


def _tokens(value):
    return {token.strip().lower() for token in str(value or "").split("|") if token.strip() and token.strip().lower() != "none"}


def _int(row, field, default=0):
    try:
        return int(row.get(field, ""))
    except (TypeError, ValueError):
        return default


def _load_rows(path, competition=False):
    factors, projects = {}, {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            key = row.get("id", "").strip()
            if not key or key in BUILT_FACTORS or key in factors:
                continue
            rating = {name: max(1, min(5, _int(row, column, 1))) for name, column in RATING_FIELDS.items()}
            raw_tools = _tokens(row.get("tools"))
            tools = {TOOL_NAMES.get(tool, tool) for tool in raw_tools}
            values = dict(
                domain=DOMAIN_TAGS.get(row.get("domain", "").strip(), row.get("domain", "other").strip()),
                **rating,
                build_hours=max(0, _int(row, "build_hours")),
                cost_inr=max(0, _int(row, "cost_inr")),
                parts_availability_india=max(1, min(5, _int(row, "parts_availability", 1))),
                tools_required=tools,
                required_skills=_tokens(row.get("skills")),
                prerequisites=_tokens(row.get("prerequisites")),
                safety=_tokens(row.get("safety")),
                tier=row.get("tier", "").strip(),
            )
            if competition:
                values["domain"] = row.get("domain", values["domain"]).strip().lower().replace(" ", "_")
                values["competition_event"] = row.get("competition_event", "").strip()
                values["constraints"] = row.get("constraints", "").strip()
            factors[key] = values
            projects[key] = dict(
                label=row.get("name", key).strip(),
                desc=row.get("description", "").strip(),
                category=row.get("domain", "").strip(),
                bom_supported=False,
                catalog_source="competition list" if competition else "projects.csv",
            )
            if competition:
                projects[key]["competition_event"] = values["competition_event"]
                projects[key]["constraints"] = values["constraints"]
    return factors, projects


PROJECT_CATALOG = {
    key: dict(label=project["label"], desc=project["desc"], category=BUILT_FACTORS[key]["domain"], bom_supported=True,
              catalog_source="BOM catalog")
    for key, project in PROJECTS.items()
}
PROJECT_FACTOR_CATALOG = dict(BUILT_FACTORS)

for _filename, _competition in (("projects.csv", False), ("competition_projects.csv", True)):
    _factors, _projects = _load_rows(DATA_DIR / _filename, competition=_competition)
    PROJECT_FACTOR_CATALOG.update(_factors)
    PROJECT_CATALOG.update(_projects)

RECOMMENDATION_PROJECT_KEYS = frozenset(
    key for key, project in PROJECT_CATALOG.items() if not project["bom_supported"]
)
COMPETITION_PROJECT_KEYS = tuple(
    key for key in PROJECT_CATALOG
    if PROJECT_CATALOG[key]["catalog_source"] == "competition list"
    and PROJECT_FACTOR_CATALOG[key].get("competition_event")
)
COMPETITION_EVENT_COUNTS = Counter(
    PROJECT_FACTOR_CATALOG[key]["competition_event"] for key in COMPETITION_PROJECT_KEYS
)
COMPETITION_EVENTS = tuple(sorted(
    COMPETITION_EVENT_COUNTS,
    key=lambda event: (-COMPETITION_EVENT_COUNTS[event], event.casefold()),
))


def competition_projects_for_event(event):
    return sorted(
        (key for key in COMPETITION_PROJECT_KEYS if PROJECT_FACTOR_CATALOG[key]["competition_event"] == event),
        key=lambda key: PROJECT_CATALOG[key]["label"].casefold(),
    )
