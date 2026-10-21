"""Candidate catalog for recommendation-only projects, separate from BOM-supported builds."""
import csv
from collections import Counter
from pathlib import Path

from .data import PROJECTS, PROJECT_FACTORS as BUILT_FACTORS

DATA_DIR = Path(__file__).with_name("project_data")
COMPETITION_DOMAIN_MAP = {
    "Drone": "drones_flying",
    "Robo Race": "mobile_robots",
    "Robo Soccer": "mobile_robots",
    "Line Follower": "mobile_robots",
}
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
    "space_aerospace": "space_aerospace",
    "arms_mechatronics": "mechanics", "iot_home": "iot", "vision_ai": "vision",
    "energy_power": "power", "comms_wireless": "iot", "wearables_assistive": "assistive",
    "env_audio_display": "sensing", "pcb_cad_fab": "fabrication", "advanced_control": "control",
    "fpga_digital": "digital",
}
SKILL_TAG_ALIASES = {
    "wireless": {"wireless_other", "rf_comms"},
}
PRICE_REVIEW_PENDING = frozenset({
    "qdd_robot_arm",
    "cubesat_flatsat",
    "imitation_learning_arm",
})
TOOL_NAMES = {
    "soldering": "soldering_iron", "hand_tools": "hand_tools", "multimeter": "multimeter",
    "3d_printer": "3d_printer", "oscilloscope": "oscilloscope", "logic_analyzer": "logic_analyzer",
}


def _tokens(value):
    return {token.strip().lower() for token in str(value or "").split("|") if token.strip() and token.strip().lower() != "none"}


def _skill_tokens(value):
    return {
        normalized
        for token in _tokens(value)
        for normalized in SKILL_TAG_ALIASES.get(token, {token})
    }


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
            rating = {name: max(0, min(5, _int(row, column, 0))) for name, column in RATING_FIELDS.items()}
            raw_tools = _tokens(row.get("tools"))
            tools = {TOOL_NAMES.get(tool, tool) for tool in raw_tools}
            values = dict(
                domain=DOMAIN_TAGS.get(row.get("domain", "").strip(), row.get("domain", "other").strip()),
                **rating,
                build_hours=max(0, _int(row, "build_hours")),
                cost_inr=max(0, _int(row, "cost_inr")),
                parts_availability_india=max(1, min(5, _int(row, "parts_availability", 1))),
                tools_required=tools,
                required_skills=_skill_tokens(row.get("skills")),
                prerequisites=_tokens(row.get("prerequisites")),
                safety=_tokens(row.get("safety")),
                tier=row.get("tier", "").strip(),
            )
            if competition:
                category = row.get("domain", "").strip()
                values["domain"] = COMPETITION_DOMAIN_MAP[category]
                values["competition_event"] = row.get("competition_event", "").strip()
                values["constraints"] = row.get("constraints", "").strip()
            values["is_star"] = False
            values["last_verified"] = row.get("last_verified", "").strip() or None
            values["price_source"] = row.get("price_source", "").strip() or None
            factors[key] = values
            projects[key] = dict(
                label=row.get("name", key).strip(),
                desc=row.get("description", "").strip(),
                category=row.get("domain", "").strip(),
                bom_supported=False,
                catalog_source="competition list" if competition else "projects.csv",
                is_star=False,
            )
            if competition:
                projects[key]["competition_event"] = values["competition_event"]
                projects[key]["constraints"] = values["constraints"]
    return factors, projects


def _load_star_projects():
    projects = []
    with (DATA_DIR / "star_projects.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            key = row.get("id", "").strip()
            if not key:
                continue
            projects.append({
                "key": key,
                "name": row.get("name", key).strip(),
                "domain": row.get("domain", "").strip(),
                "description": row.get("description", "").strip(),
                **{
                    name: max(0, min(5, _int(row, column, 0)))
                    for name, column in RATING_FIELDS.items()
                },
                "build_hours": max(0, _int(row, "build_hours")),
                "cost_inr": None if key in PRICE_REVIEW_PENDING else max(0, _int(row, "cost_inr")),
                "price_status": "pending_verification" if key in PRICE_REVIEW_PENDING else "unverified_estimate",
                "parts_availability": max(1, min(5, _int(row, "parts_availability", 1))),
                "tools": sorted(_tokens(row.get("tools"))),
                "skills": sorted(_skill_tokens(row.get("skills"))),
                "prerequisites": sorted(_tokens(row.get("prerequisites"))),
                "safety": sorted(_tokens(row.get("safety"))),
                "tier": row.get("tier", "").strip(),
                "last_verified": row.get("last_verified", "").strip() or None,
                "price_source": row.get("price_source", "").strip() or None,
            })
    return projects


STAR_PROJECTS = _load_star_projects()
STAR_KEYS = frozenset(project["key"] for project in STAR_PROJECTS)
STAR_COLLISION_ALLOWLIST = frozenset({
    "stm32_bldc_foc",
    "quadcopter_fc",
    "ros2_nav2_autonomy",
    "fpga_riscv_core",
    "lqr_balancing_robot",
    "tiny_rtos_scheduler",
    "buildroot_linux_driver",
    "mppt_charge_controller",
    "esp32_usbc_board",
})


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

for key, label in (
    ("basic_circuits", "Basic circuits foundation"),
    ("basic_programming", "Basic programming foundation"),
):
    PROJECT_CATALOG[key] = {
        "label": label,
        "desc": "Foundational knowledge prerequisite; not a separately ranked build.",
        "category": "embedded",
        "bom_supported": False,
        "catalog_source": "foundation prerequisite",
        "is_star": False,
        "prerequisite_only": True,
    }
    PROJECT_FACTOR_CATALOG[key] = {
        "domain": "embedded",
        "difficulty": 1,
        "electronics": 1,
        "programming": 1,
        "fabrication": 0,
        "control_math": 0,
        "ai_vision": 0,
        "wireless_iot": 0,
        "portfolio_impact": 0,
        "build_hours": 0,
        "cost_inr": 0,
        "parts_availability_india": 5,
        "tools_required": set(),
        "required_skills": set(),
        "prerequisites": set(),
        "safety": set(),
        "tier": "foundation",
        "is_star": False,
        "prerequisite_only": True,
    }

for star in STAR_PROJECTS:
    key = star["key"]
    if key not in PROJECT_CATALOG:
        PROJECT_CATALOG[key] = {
            "label": star["name"],
            "desc": star["description"],
            "category": star["domain"],
            "bom_supported": False,
            "catalog_source": "star projects",
            "is_star": True,
        }
        PROJECT_FACTOR_CATALOG[key] = {
            "domain": star["domain"],
            **{name: star[name] for name in RATING_FIELDS},
            "build_hours": star["build_hours"],
            "cost_inr": star["cost_inr"],
            "parts_availability_india": star["parts_availability"],
            "tools_required": {TOOL_NAMES.get(tool, tool) for tool in star["tools"]},
            "required_skills": set(star["skills"]),
            "prerequisites": set(star["prerequisites"]),
            "safety": set(star["safety"]),
            "tier": star["tier"],
            "is_star": True,
            "last_verified": star["last_verified"],
            "price_source": star["price_source"],
            "price_status": star["price_status"],
        }
    else:
        PROJECT_CATALOG[key]["is_star"] = True
        PROJECT_FACTOR_CATALOG[key]["is_star"] = True

RECOMMENDATION_PROJECT_KEYS = frozenset(
    key for key, project in PROJECT_CATALOG.items()
    if not project["bom_supported"]
    and project["catalog_source"] != "star projects"
    and not project.get("prerequisite_only")
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
