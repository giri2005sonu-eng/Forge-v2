"""Backward-compatibility shim. Implementation moved to core.engineering.rules."""
from core.engineering.rules import *
from core.engineering.rules import (
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
