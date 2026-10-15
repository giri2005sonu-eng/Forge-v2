"""Derived values + whole-build evaluation."""
from __future__ import annotations

import math
from collections import Counter
from typing import Optional

from .rules import Rule, evaluate_rule, rule_status
from .schemas import CheckResult, Part


def derive(parts: dict[str, Part], req: dict, assumptions: dict) -> dict:
    """Numbers computed from specs. Any missing input makes the result None (-> Unknown)."""
    def sv(role: str, key: str) -> Optional[float]:
        p = parts.get(role)
        return None if p is None else p.spec_value(key)

    def add(*xs):
        return None if any(x is None for x in xs) else sum(xs)

    n = req["motor_count"]
    frac = assumptions["avg_load_fraction"]
    usable = assumptions["battery_usable_fraction"]
    d: dict = {"motor_qty": n}

    ch = sv("sensor", "channels")
    d["sensor_qty"] = math.ceil(req["sensor_channels"] / ch) if ch else None

    stall = sv("motor", "stall_current_a")
    ctrl_i = sv("controller", "current_a")
    sens_i = sv("sensor", "current_a")
    sensors_a = None if (sens_i is None or d["sensor_qty"] is None) else sens_i * d["sensor_qty"]

    d["peak_current_a"] = add(None if stall is None else n * stall, ctrl_i, sensors_a)
    d["avg_current_a"] = add(None if stall is None else n * stall * frac, ctrl_i, sensors_a)

    cap = sv("battery", "capacity_mah")
    avg = d["avg_current_a"]
    d["runtime_h"] = (cap / 1000.0) * usable / avg if (cap is not None and avg) else None

    nominal, maxv, drop = sv("battery", "nominal_v"), sv("battery", "max_v"), sv("driver", "voltage_drop_v")
    d["motor_supply_nominal_v"] = None if (nominal is None or drop is None) else nominal - drop
    d["motor_supply_max_v"] = None if (maxv is None or drop is None) else maxv - drop

    cpm, extra, sig = (sv("driver", "control_pins_per_motor"), sv("driver", "extra_pins"),
                       sv("sensor", "signal_pins"))
    if None in (cpm, extra, sig) or d["sensor_qty"] is None:
        d["pins_required"] = None
    else:
        d["pins_required"] = cpm * n + extra + sig * d["sensor_qty"]
    pwm = sv("driver", "pwm_pins_per_motor")
    d["pwm_required"] = None if pwm is None else pwm * n
    return d


def quick_eval(parts: dict[str, Part], req: dict, rules: list[Rule], assumptions: dict) -> tuple[list[str], list[str]]:
    """Fast: returns (failed_rule_ids, unknown_rule_ids) without building messages."""
    derived = derive(parts, req, assumptions)
    fails, unknowns = [], []
    for r in rules:
        s = rule_status(r, parts, req, derived)
        if s == "fail":
            fails.append(r.id)
        elif s == "unknown":
            unknowns.append(r.id)
    return fails, unknowns


def evaluate_build(parts: dict[str, Part], req: dict, rules: list[Rule], assumptions: dict
                   ) -> tuple[list[CheckResult], dict, str, dict]:
    """Full evaluation with messages and evidence."""
    derived = derive(parts, req, assumptions)
    checks = [evaluate_rule(r, parts, req, derived) for r in rules]
    checks = [c for c in checks if c.status != "skipped"]
    cnt = Counter(c.status for c in checks)
    counts = {"pass": cnt["pass"], "fail": cnt["fail"], "unknown": cnt["unknown"]}
    status = "invalid" if counts["fail"] else ("unverified" if counts["unknown"] else "verified")
    return checks, counts, status, derived
