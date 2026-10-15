"""Deterministic rule engine. Rules are data (YAML); formulas are parsed with `ast`
and restricted to a tiny whitelist, so a rule can never execute arbitrary code.

Status logic (never guesses):
  any needed value missing  -> UNKNOWN
  formula true              -> PASS
  formula false             -> FAIL
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from .schemas import CheckResult, EvidenceRef, Part

PART_ROLES = ("controller", "driver", "motor", "battery", "sensor", "chassis")
REQ_KEYS = {"robot_type", "budget_inr", "motor_count", "min_runtime_h", "needs_bluetooth", "sensor_channels"}
DERIVED_KEYS = {
    "motor_qty", "sensor_qty", "peak_current_a", "avg_current_a", "runtime_h",
    "motor_supply_nominal_v", "motor_supply_max_v", "pins_required", "pwm_required",
}
# Which part specs each derived value is computed from (used to explain UNKNOWN results)
DERIVED_DEPS: dict[str, list[str]] = {
    "motor_qty": [],
    "sensor_qty": ["sensor.channels"],
    "peak_current_a": ["motor.stall_current_a", "controller.current_a", "sensor.current_a", "sensor.channels"],
    "avg_current_a": ["motor.stall_current_a", "controller.current_a", "sensor.current_a", "sensor.channels"],
    "runtime_h": ["battery.capacity_mah", "motor.stall_current_a", "controller.current_a",
                  "sensor.current_a", "sensor.channels"],
    "motor_supply_nominal_v": ["battery.nominal_v", "driver.voltage_drop_v"],
    "motor_supply_max_v": ["battery.max_v", "driver.voltage_drop_v"],
    "pins_required": ["driver.control_pins_per_motor", "driver.extra_pins", "sensor.signal_pins", "sensor.channels"],
    "pwm_required": ["driver.pwm_pins_per_motor"],
}

_FUNCS: dict[str, Callable] = {"min": min, "max": max, "abs": abs, "ceil": math.ceil}
_CMP_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_REF_RE = re.compile(r"\{([a-z_]+)\.([a-z_0-9]+)\}")


class RuleError(Exception):
    pass


class _NS:
    """Attribute namespace used while evaluating a formula."""
    def __init__(self, d: dict):
        self._d = d

    def __getattr__(self, k: str):
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError(k)


@dataclass
class Rule:
    id: str
    title: str
    category: str
    needs: list[str]
    check: str
    pass_msg: str
    fail_msg: str
    when: Optional[str] = None
    code: Any = field(default=None, repr=False)
    when_code: Any = field(default=None, repr=False)
    when_refs: list[str] = field(default_factory=list)
    msg_refs: list[str] = field(default_factory=list)


def _validate_node(node: ast.AST, refs: set[str]) -> None:
    if isinstance(node, ast.Expression):
        _validate_node(node.body, refs)
    elif isinstance(node, ast.BoolOp):
        for v in node.values:
            _validate_node(v, refs)
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BIN_OPS):
            raise RuleError("operator not allowed")
        _validate_node(node.left, refs)
        _validate_node(node.right, refs)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.Not, ast.USub)):
            raise RuleError("unary operator not allowed")
        _validate_node(node.operand, refs)
    elif isinstance(node, ast.Compare):
        if not all(isinstance(o, _CMP_OPS) for o in node.ops):
            raise RuleError("comparison not allowed")
        _validate_node(node.left, refs)
        for c in node.comparators:
            _validate_node(c, refs)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str, bool)):
            raise RuleError("constant type not allowed")
    elif isinstance(node, ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id in PART_ROLES + ("req", "derived")):
            raise RuleError("only <role>.<field> references are allowed")
        refs.add(f"{node.value.id}.{node.attr}")
    elif isinstance(node, ast.Call):
        if not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS) or node.keywords:
            raise RuleError("function not allowed")
        for a in node.args:
            _validate_node(a, refs)
    else:
        raise RuleError(f"syntax not allowed: {type(node).__name__}")


def _compile(expr: str) -> tuple[Any, set[str]]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise RuleError(f"syntax error in '{expr}': {e}") from e
    refs: set[str] = set()
    _validate_node(tree, refs)
    return compile(tree, "<rule>", "eval"), refs


def _check_ref(ref: str, spec_defs: dict, allow_name: bool = False) -> None:
    role, _, key = ref.partition(".")
    if role in PART_ROLES:
        if key == "name" and allow_name:
            return
        if key not in spec_defs.get(role, {}):
            raise RuleError(f"unknown spec '{ref}'")
    elif role == "req":
        if key not in REQ_KEYS:
            raise RuleError(f"unknown requirement field '{ref}'")
    elif role == "derived":
        if key not in DERIVED_KEYS:
            raise RuleError(f"unknown derived value '{ref}'")
    else:
        raise RuleError(f"unknown reference '{ref}'")


def load_rules(path: Path, spec_defs: dict) -> list[Rule]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    rules: list[Rule] = []
    seen: set[str] = set()
    for r in raw["rules"]:
        rid = r.get("id", "?")
        try:
            if rid in seen:
                raise RuleError("duplicate rule id")
            seen.add(rid)
            code, refs = _compile(r["check"])
            needs = list(r["needs"])
            for n in needs:
                _check_ref(n, spec_defs)
            if not refs <= set(needs):
                raise RuleError(f"check uses refs not listed in needs: {sorted(refs - set(needs))}")
            when_code, when_refs = None, set()
            if r.get("when"):
                when_code, when_refs = _compile(r["when"])
                if any(not x.startswith("req.") for x in when_refs):
                    raise RuleError("'when' may only use req.* values")
                for x in when_refs:
                    _check_ref(x, spec_defs)
            msg_refs: set[str] = set()
            for msg in (r["pass_msg"], r["fail_msg"]):
                for role, key in _REF_RE.findall(msg):
                    ref = f"{role}.{key}"
                    _check_ref(ref, spec_defs, allow_name=True)
                    if not key == "name" and ref not in needs:
                        raise RuleError(f"message uses {ref} which is not in needs")
                    msg_refs.add(ref)
            rules.append(Rule(
                id=rid, title=r["title"], category=r["category"], needs=needs, check=r["check"],
                pass_msg=r["pass_msg"], fail_msg=r["fail_msg"], when=r.get("when"),
                code=code, when_code=when_code, when_refs=sorted(when_refs), msg_refs=sorted(msg_refs),
            ))
        except (KeyError, RuleError) as e:
            raise RuleError(f"rule '{rid}': {e}") from e
    return rules


def _eval(code: Any, values: dict[str, Any]) -> Any:
    ns: dict[str, Any] = {}
    for ref, v in values.items():
        role, _, key = ref.partition(".")
        ns.setdefault(role, {})[key] = v
    env = {role: _NS(d) for role, d in ns.items()}
    return eval(code, {"__builtins__": {}, **_FUNCS}, env)  # safe: AST whitelisted at load time


def _fmt(v: Any) -> str:
    if v is None:
        return "?"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def _make_lookup(parts: dict[str, Part], req: dict, derived: dict) -> Callable[[str], Any]:
    def lookup(ref: str) -> Any:
        role, _, key = ref.partition(".")
        if role == "req":
            return req.get(key)
        if role == "derived":
            return derived.get(key)
        p = parts.get(role)
        if p is None:
            return None
        if key == "name":
            return p.name
        s = p.specs.get(key)
        return None if s is None else s.value
    return lookup


def _run(rule: Rule, lookup: Callable[[str], Any]) -> tuple[str, dict, list[str]]:
    """Core evaluation: returns (status, values, missing_refs)."""
    if rule.when_code is not None:
        if not bool(_eval(rule.when_code, {r: lookup(r) for r in rule.when_refs})):
            return "skipped", {}, []
    values = {ref: lookup(ref) for ref in rule.needs}
    missing = [ref for ref, v in values.items() if v is None]
    if missing:
        return "unknown", values, missing
    try:
        ok = bool(_eval(rule.code, values))
    except (TypeError, ValueError, ZeroDivisionError):
        return "unknown", values, []
    return ("pass" if ok else "fail"), values, []


def rule_status(rule: Rule, parts: dict[str, Part], req: dict, derived: dict) -> str:
    """Fast path used while searching thousands of candidate builds."""
    return _run(rule, _make_lookup(parts, req, derived))[0]


def _expand_missing(missing: list[str], lookup: Callable[[str], Any]) -> list[str]:
    out: list[str] = []
    for ref in missing:
        if ref.startswith("derived."):
            deps = DERIVED_DEPS.get(ref.split(".", 1)[1], [])
            real = [d for d in deps if lookup(d) is None]
            out.extend(real or [ref])
        else:
            out.append(ref)
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def evaluate_rule(rule: Rule, parts: dict[str, Part], req: dict, derived: dict) -> CheckResult:
    lookup = _make_lookup(parts, req, derived)
    status, values, missing = _run(rule, lookup)
    if status == "skipped":
        return CheckResult(rule_id=rule.id, title=rule.title, category=rule.category,
                           status="skipped", message="Not applicable")
    real_missing = _expand_missing(missing, lookup)
    if status == "unknown":
        if real_missing:
            human = []
            for ref in real_missing:
                role, _, key = ref.partition(".")
                p = parts.get(role)
                human.append(f"{key} of {p.name}" if p else ref)
            msg = "Cannot verify - spec not found: " + "; ".join(human)
        else:
            msg = "Cannot verify - values could not be compared"
    else:
        template = rule.pass_msg if status == "pass" else rule.fail_msg
        mv = {ref: lookup(ref) for ref in rule.msg_refs}
        msg = _REF_RE.sub(lambda m: _fmt(mv.get(f"{m.group(1)}.{m.group(2)}")), template)

    evidence: list[EvidenceRef] = []
    refs_for_evidence: list[str] = []
    for ref in rule.needs:
        if ref.startswith("derived."):
            refs_for_evidence.extend(DERIVED_DEPS.get(ref.split(".", 1)[1], []))
        else:
            refs_for_evidence.append(ref)
    seen: set[str] = set()
    for ref in refs_for_evidence:
        if ref in seen:
            continue
        seen.add(ref)
        role, _, key = ref.partition(".")
        p = parts.get(role)
        if p is None or role in ("req", "derived"):
            continue
        s = p.specs.get(key)
        if s is not None and s.value is not None:
            evidence.append(EvidenceRef(
                part=p.name, field=key, value=s.value, unit=s.unit,
                source_url=s.evidence.source_url, retrieved_at=s.evidence.retrieved_at,
                method=s.evidence.method))
    return CheckResult(rule_id=rule.id, title=rule.title, category=rule.category, status=status,
                       message=msg, missing=real_missing, evidence=evidence)
