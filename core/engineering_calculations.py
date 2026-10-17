"""Deterministic engineering formulas. No UI, no AI, no eval. Every function returns a Calc and never guesses a missing input:
if any required input is None / non-positive where that is invalid, the result is status='insufficient' with the list of what is missing."""
import math
from dataclasses import dataclass, field

@dataclass
class Calc:
    value: float | None
    unit: str
    status: str                     # 'ok' | 'insufficient' | 'invalid'
    reason: str = ""
    assumptions: list = field(default_factory=list)
    missing: list = field(default_factory=list)

def _missing(**kw): return [k for k, v in kw.items() if v is None]
def _insufficient(unit, missing, what): return Calc(None, unit, "insufficient", f"{what}: missing {', '.join(missing)}", missing=missing)
def _invalid(unit, why): return Calc(None, unit, "invalid", why)

def bom_total(lines):
    """lines: [(unit_price, qty)]. A line with a None price makes the total insufficient rather than silently 0."""
    if any(p is None for p, _ in lines): return _insufficient("INR", ["unit price"], "BOM total")
    return Calc(sum(p * q for p, q in lines), "INR", "ok")

def power_w(v, i_a):
    m = _missing(voltage_v=v, current_a=i_a)
    if m: return _insufficient("W", m, "Electrical power")
    if v < 0 or i_a < 0: return _invalid("W", "negative voltage or current")
    return Calc(v * i_a, "W", "ok", assumptions=["P = V x I at the stated operating point"])

def runtime_hours(capacity_mah, avg_current_ma, usable_fraction=None):
    """Theoretical runtime = usable capacity / average current. usable_fraction (0-1] is an explicit derating the caller must justify; None = 1.0 (labelled)."""
    m = _missing(capacity_mah=capacity_mah, avg_current_ma=avg_current_ma)
    if m: return _insufficient("h", m, "Battery runtime")
    if capacity_mah <= 0 or avg_current_ma <= 0: return _invalid("h", "capacity and current must be positive")
    f = 1.0 if usable_fraction is None else usable_fraction
    if not 0 < f <= 1: return _invalid("h", "usable_fraction must be in (0, 1]")
    note = "no capacity derating applied (theoretical upper bound)" if usable_fraction is None else f"{f:.0%} of rated capacity assumed usable"
    return Calc(capacity_mah / 1000 * f / (avg_current_ma / 1000), "h", "ok", "Theoretical estimate, not measured.", [note, "constant average current"])

def wheel_speed_mps(output_rpm, wheel_diameter_m, gear_ratio=None, rpm_is_output_shaft=True):
    """v = rpm * pi * d / 60. If the published rpm is already at the gearbox output (rpm_is_output_shaft=True) the ratio is NOT applied again."""
    if rpm_is_output_shaft: m = _missing(output_rpm=output_rpm, wheel_diameter_m=wheel_diameter_m)
    else: m = _missing(output_rpm=output_rpm, wheel_diameter_m=wheel_diameter_m, gear_ratio=gear_ratio)
    if m: return _insufficient("m/s", m, "Wheel speed")
    if output_rpm < 0 or wheel_diameter_m <= 0 or (not rpm_is_output_shaft and gear_ratio <= 0): return _invalid("m/s", "rpm >= 0, diameter > 0, ratio > 0 required")
    rpm = output_rpm if rpm_is_output_shaft else output_rpm / gear_ratio
    return Calc(rpm * math.pi * wheel_diameter_m / 60, "m/s", "ok", "Ideal no-load estimate; load, voltage, slip and losses reduce it.",
                ["published rpm is already at the output shaft" if rpm_is_output_shaft else "rpm is motor-side and divided by gear ratio", "no wheel slip"])

def wheel_torque_nm(torque_nm, gear_ratio=None, efficiency=None, torque_is_output=True):
    """Torque at the wheel axle. Documented output torque is used as is; motor-side torque needs an explicit ratio AND efficiency (never defaulted)."""
    if torque_is_output:
        m = _missing(torque_nm=torque_nm)
    else:
        m = _missing(torque_nm=torque_nm, gear_ratio=gear_ratio, efficiency=efficiency)
    if m: return _insufficient("N·m", m, "Wheel torque")
    if torque_nm < 0: return _invalid("N·m", "negative torque")
    if torque_is_output: return Calc(torque_nm, "N·m", "ok", "Uses the documented output torque; check whether it is stall or rated torque.", ["gearbox ratio not applied twice"])
    if gear_ratio <= 0 or not 0 < efficiency <= 1: return _invalid("N·m", "gear_ratio > 0 and 0 < efficiency <= 1 required")
    return Calc(torque_nm * gear_ratio * efficiency, "N·m", "ok", "Estimate from motor-side torque.", [f"drivetrain efficiency {efficiency:.0%} (stated by caller)"])

def mechanical_power_w(torque_nm, rpm):
    m = _missing(torque_nm=torque_nm, rpm=rpm)
    if m: return _insufficient("W", m, "Mechanical power")
    if torque_nm < 0 or rpm < 0: return _invalid("W", "negative torque or rpm")
    return Calc(torque_nm * rpm * 2 * math.pi / 60, "W", "ok", assumptions=["P = torque x angular velocity at one operating point"])

def efficiency(p_out_w, p_in_w):
    """Output/input power, valid only when both come from the SAME operating point (caller's responsibility, stated in assumptions)."""
    m = _missing(p_out_w=p_out_w, p_in_w=p_in_w)
    if m: return _insufficient("%", m, "Efficiency")
    if p_in_w <= 0 or p_out_w < 0: return _invalid("%", "input power must be > 0 and output >= 0")
    if p_out_w > p_in_w: return _invalid("%", "output power exceeds input power: inputs are not from the same operating point")
    return Calc(100 * p_out_w / p_in_w, "%", "ok", assumptions=["input and output measured at the same operating point"])

def total_current_ma(items):
    """items: [(name, current_ma_or_None, qty)]. Any unknown current -> insufficient (names listed). Sum of the given typical currents only."""
    missing = [n for n, c, _ in items if c is None]
    if missing: return Calc(None, "mA", "insufficient", "Power budget incomplete: no current for " + ", ".join(missing), missing=missing)
    return Calc(sum(c * q for _, c, q in items), "mA", "ok", assumptions=["sum of the supplied currents; startup/stall peaks not included"])

def compare(orig, prop, higher_is_better=True, tol=1e-9):
    """Difference between two numbers. pct is None when the original is 0 (undefined)."""
    if orig is None or prop is None: return dict(status="unknown", diff=None, pct=None)
    d = prop - orig
    if abs(d) <= tol: return dict(status="unchanged", diff=0.0, pct=0.0)
    better = d > 0 if higher_is_better else d < 0
    return dict(status="improved" if better else "reduced", diff=d, pct=None if orig == 0 else 100 * d / abs(orig))

def gpio_check(required, available):
    """required/available: dict like {'gpio': n, 'pwm': n}. None available -> unknown (never pass)."""
    rows = []
    for k, need in required.items():
        have = available.get(k)
        rows.append(dict(item=k, required=need, available=have, status="UNKNOWN" if have is None else "PASS" if have >= need else "FAIL"))
    return rows
