"""Hardware and robot engineering pipeline: catalog, rules, validation, power, wiring."""
from .catalog import (
    CatalogError,
    load_catalog,
    load_overlay,
    load_seed,
    normalize_part,
    reset_overlay,
    save_overlay,
)
from .rules import (
    PART_ROLES,
    REQ_KEYS,
    DERIVED_KEYS,
    DERIVED_DEPS,
    Rule,
    RuleError,
    evaluate_rule,
    load_rules,
    rule_status,
)
from .validator import derive, evaluate_build, quick_eval
from .selector import (
    Build,
    Candidate,
    Selection,
    _make_build,
    qty_for,
    select_build,
    shipping_breakdown,
)
from .power import PowerAnalysis, analyze_power
from .wiring import WireConnection, WiringPlan, generate_wiring_plan

__all__ = [
    "CatalogError",
    "load_catalog",
    "load_overlay",
    "load_seed",
    "normalize_part",
    "reset_overlay",
    "save_overlay",
    "PART_ROLES",
    "REQ_KEYS",
    "DERIVED_KEYS",
    "DERIVED_DEPS",
    "Rule",
    "RuleError",
    "evaluate_rule",
    "load_rules",
    "rule_status",
    "derive",
    "evaluate_build",
    "quick_eval",
    "Build",
    "Candidate",
    "Selection",
    "_make_build",
    "qty_for",
    "select_build",
    "shipping_breakdown",
    "PowerAnalysis",
    "analyze_power",
    "WireConnection",
    "WiringPlan",
    "generate_wiring_plan",
]
