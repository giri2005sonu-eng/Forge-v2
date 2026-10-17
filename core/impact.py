"""Swap-impact engine. Given the original build and a build with one part replaced, work out what changes:
connectivity, processing, I/O, power, runtime, speed, torque, efficiency, weight (+ the plain-language 'what changes' list).
Inputs are part PROFILES (core/profiles). Pure functions: no Streamlit, no network, never mutates its inputs.
Anything the profiles cannot support is reported as unknown (with what is missing), never filled with a guess.

First-order physics used (stated in each row's reason):
  motor voltage  V_m = V_battery_nominal - driver_drop
  speed          v   = rpm_noload * (V_m / V_rated) * pi * d / 60      (ideal, no load, no slip)
  torque         T   = T_stall * (V_m / V_rated)                        (stall torque per motor at the gearbox output)
  current        I   = controller + sensor + n_motors * running current
  runtime        t   = 0.8 * capacity / I                               (20 % derating, stated)
  efficiency     eta = bridge efficiency * V_m / V_battery              (motor-stage only)"""
import math
from . import engineering_calculations as calc, profiles
from .profiles import LABEL, UNIT

WHEEL_D_M = 0.065        # default wheel diameter: the generic 2WD chassis in EXTRAS. Pass wheel_d_m to override.
USABLE = 0.8
QTY_MOTOR = 2

def _a(p, k): return (p or {}).get("attrs", {}).get(k)
def _origin(*ps):
    """'typical' if every profile involved is curated, else 'estimated'; None if a profile is missing."""
    if any(p is None for p in ps): return None
    return "typical" if all(p.get("origin", "curated") == "curated" for p in ps) else "estimated"

def derive(prof, n_motors=QTY_MOTOR, wheel_d_m=WHEEL_D_M):
    """prof: role -> profile (or None). Returns {metric: (value|None, [missing], [assumptions])}."""
    c, d, m, b, s = (prof.get(r) for r in ("controller", "driver", "motor", "battery", "sensor"))
    out = {}
    def need(**kw): return [k for k, v in kw.items() if v is None]
    vb, drop, rated = _a(b, "nominal_v"), _a(d, "drop_v"), _a(m, "rated_v")
    vm = None if vb is None or drop is None else max(vb - drop, 0.0)
    out["motor_v"] = (vm, need(battery_nominal_v=vb, driver_drop_v=drop), ["V_motor = battery nominal - driver drop"])
    ok = vm is not None and rated
    rpm, tq = _a(m, "no_load_rpm"), _a(m, "stall_torque_kgcm")
    miss = need(motor_rated_v=rated, motor_no_load_rpm=rpm) + (out["motor_v"][1])
    out["speed"] = ((rpm * vm / rated) * math.pi * wheel_d_m / 60 if not miss else None, miss,
                    [f"wheel diameter {wheel_d_m * 1000:.0f} mm (generic chassis)", "ideal no-load, no slip", "rpm scales with voltage"])
    miss = need(motor_rated_v=rated, motor_stall_torque=tq) + (out["motor_v"][1])
    out["torque"] = (tq * 0.0980665 * vm / rated if not miss else None, miss, ["stall torque per motor at the wheel axle", "torque scales with voltage"])
    t = out["torque"][0]
    out["traction"] = (n_motors * t / (wheel_d_m / 2) if t is not None else None, out["torque"][1], [f"{n_motors} motors, stall, ideal grip"])
    ci, cs, cm = _a(c, "current_ma"), (0 if s is None or s.get("none") else _a(s, "current_ma")), _a(m, "run_a")
    miss = need(controller_current=ci, sensor_current=cs, motor_running_current=cm)
    cur = None if miss else ci + cs + n_motors * cm * 1000
    out["current"] = (cur, miss, ["typical currents added; startup/stall peaks excluded", "controller figure is with radio idle"])
    out["power"] = (None if cur is None or vb is None else vb * cur, miss + ([] if vb is not None else ["battery_nominal_v"]), [f"battery nominal voltage x total current"])
    cap = _a(b, "capacity_mah")
    out["runtime"] = (None if cur is None or cap is None else USABLE * cap / cur, miss + ([] if cap is not None else ["battery_capacity"]),
                      [f"{USABLE:.0%} of rated capacity usable", "constant average current"])
    wts = {"controller": _a(c, "weight_g"), "driver": _a(d, "weight_g"), "motor": _a(m, "weight_g"), "battery": _a(b, "weight_g"), "sensor": 0 if s is None or s.get("none") else _a(s, "weight_g")}
    mw = [k for k, v in wts.items() if v is None]
    out["weight"] = (None if mw else wts["controller"] + wts["driver"] + n_motors * wts["motor"] + wts["battery"] + wts["sensor"], [f"{k}_weight" for k in mw], ["five electronics parts only; chassis and wires excluded"])
    eff = _a(d, "eff_pct")
    miss = need(driver_eff=eff) + out["motor_v"][1]
    out["efficiency"] = (eff * vm / vb if not miss and vb else None, miss, ["bridge efficiency x (V_motor / V_battery)", "motor-stage only; motor and gearbox losses excluded"])
    pins_have, pins_need = _a(c, "gpio"), (_a(d, "pins_needed") or 0) + (0 if s is None or s.get("none") else (_a(s, "pins_needed") or 0))
    out["gpio"] = (None if pins_have is None else pins_have - pins_need, [] if pins_have is not None else ["controller_gpio"], [f"build needs about {pins_need} pins (driver + sensor)"])
    return out

def _fmt(v, unit, nd=1):
    if v is None: return "unknown"
    s = f"{v:,.{nd}f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
    return f"{s} {unit}".strip()

def _chip(tone, text): return dict(tone=tone, text=text)
def _pct(a, b): return None if a in (None, 0) or b is None else 100 * (b - a) / abs(a)

def intrinsic(role, pa, pb):
    """Part-vs-part deltas from profiles alone (no build context). -> list of dict(key,label,unit,a,b,pct)."""
    rows = []
    for k in [k for k in LABEL if k in (pa or {}).get("attrs", {}) or k in (pb or {}).get("attrs", {})]:
        a, b = _a(pa, k), _a(pb, k)
        if a is None and b is None or a == b: continue
        rows.append(dict(key=k, label=LABEL[k], unit=UNIT[k], a=a, b=b, pct=None if isinstance(a, bool) or isinstance(b, bool) else _pct(a, b)))
    return rows

def part_chips(role, po, pn):
    """Plain-language differences between two parts, from profiles alone. This is what the pair dataset stores."""
    ch = []
    ao, an = (po or {}).get("attrs", {}), (pn or {}).get("attrs", {})
    if role == "controller":
        for key, name in (("wifi", "Wi-Fi"),):
            if ao.get(key) is not None and an.get(key) is not None and ao[key] != an[key]: ch.append(_chip("good" if an[key] else "bad", f"{'Gains' if an[key] else 'Loses'} {name}"))
        if ao.get("bluetooth") is not None and an.get("bluetooth") is not None and ao["bluetooth"] != an["bluetooth"]:
            kind = "Bluetooth Classic + BLE" if an.get("bt_classic") else "Bluetooth Low Energy (BLE only)"
            ch.append(_chip("good" if an["bluetooth"] else "bad", f"Gains {kind}" if an["bluetooth"] else "Loses Bluetooth"))
        elif an.get("bluetooth") and ao.get("bt_classic") is not None and an.get("bt_classic") is not None and ao["bt_classic"] != an["bt_classic"]:
            ch.append(_chip("bad" if ao["bt_classic"] else "good", "Bluetooth Classic dropped: phone serial-terminal apps will not connect (BLE only)" if ao["bt_classic"] else "Adds Bluetooth Classic"))
        if ao.get("clock_mhz") and an.get("clock_mhz") and ao["clock_mhz"] != an["clock_mhz"]:
            r = an["clock_mhz"] / ao["clock_mhz"]
            extra = f", {_fmt(ao.get('sram_kb'), 'kB')} to {_fmt(an.get('sram_kb'), 'kB')} RAM" if ao.get("sram_kb") and an.get("sram_kb") else ""
            ch.append(_chip("good" if r > 1 else "bad", f"Clock {_fmt(ao['clock_mhz'], 'MHz')} to {_fmt(an['clock_mhz'], 'MHz')} ({r:.1f}x){extra}"))
        if ao.get("arch_bits") and an.get("arch_bits") and ao["arch_bits"] != an["arch_bits"]: ch.append(_chip("good" if an["arch_bits"] > ao["arch_bits"] else "bad", f"{ao['arch_bits']}-bit to {an['arch_bits']}-bit core"))
        if ao.get("logic_v") and an.get("logic_v") and ao["logic_v"] != an["logic_v"]:
            ch.append(_chip("warn", f"Logic level {ao['logic_v']:g} V to {an['logic_v']:g} V" + (": 5 V sensors/drivers may need level shifting" if an["logic_v"] < ao["logic_v"] else "")))
        for k, nm in (("gpio", "GPIO pins"), ("adc_channels", "ADC channels"), ("pwm_channels", "PWM channels")):
            if ao.get(k) is not None and an.get(k) is not None and ao[k] != an[k]: ch.append(_chip("good" if an[k] > ao[k] else "bad", f"{nm}: {ao[k]:g} to {an[k]:g}"))
        if ao.get("adc_bits") and an.get("adc_bits") and ao["adc_bits"] != an["adc_bits"]: ch.append(_chip("good" if an["adc_bits"] > ao["adc_bits"] else "bad", f"ADC resolution {ao['adc_bits']:g} to {an['adc_bits']:g} bit"))
    if role == "motor":
        for k in ("no_load_rpm", "stall_torque_kgcm", "stall_a"):
            if ao.get(k) and an.get(k) and ao[k] != an[k]:
                tone = ("bad" if an[k] > ao[k] else "good") if k == "stall_a" else ("good" if an[k] > ao[k] else "bad")
                ch.append(_chip(tone, f"{LABEL[k]} {_fmt(ao[k], UNIT[k])} to {_fmt(an[k], UNIT[k])}"))
        if ao.get("encoder") is not None and an.get("encoder") is not None and ao["encoder"] != an["encoder"]: ch.append(_chip("good" if an["encoder"] else "neutral", "Gains wheel encoder (closed-loop speed control)" if an["encoder"] else "Loses wheel encoder"))
    if role == "driver":
        for k in ("drop_v", "max_a", "eff_pct"):
            if ao.get(k) is not None and an.get(k) is not None and ao[k] != an[k]:
                better = (an[k] < ao[k]) if k == "drop_v" else (an[k] > ao[k]); ch.append(_chip("good" if better else "bad", f"{LABEL[k]} {_fmt(ao[k], UNIT[k])} to {_fmt(an[k], UNIT[k])}"))
    if role == "battery":
        for k in ("nominal_v", "capacity_mah", "max_a"):
            if ao.get(k) and an.get(k) and ao[k] != an[k]: ch.append(_chip("good" if an[k] > ao[k] else "bad" if k != "nominal_v" else "warn", f"{LABEL[k]} {_fmt(ao[k], UNIT[k])} to {_fmt(an[k], UNIT[k])}"))
    if role == "sensor":
        for k in ("range_max_cm", "range_min_cm", "rate_hz", "current_ma"):
            if ao.get(k) is not None and an.get(k) is not None and ao[k] != an[k]:
                better = (an[k] < ao[k]) if k in ("current_ma", "range_min_cm") else (an[k] > ao[k]); ch.append(_chip("good" if better else "bad", f"{LABEL[k]} {_fmt(ao[k], UNIT[k])} to {_fmt(an[k], UNIT[k])}"))
    return ch

def system_chips(d0, d1):
    """Consequences that depend on the whole build (speed, runtime, weight...). Always computed live."""
    ch = []
    for key, name, unit, hib in (("speed", "Top speed", "m/s", True), ("torque", "Wheel torque", "N·m", True), ("runtime", "Battery runtime", "h", True), ("weight", "Weight", "g", False), ("power", "Power draw", "mW", False)):
        a, b = d0[key][0], d1[key][0]
        if a is None or b is None or abs(b - a) < 1e-9: continue
        pc = _pct(a, b); better = (b > a) == hib
        if pc is not None and abs(pc) >= 3: ch.append(_chip("good" if better else "bad", f"{name} {pc:+.0f}% ({_fmt(a, unit, 2 if abs(a) < 10 else 0)} to {_fmt(b, unit, 2 if abs(b) < 10 else 0)})"))
    return ch

def rows(original, proposed, changed, prof_o, prof_p, n_motors=QTY_MOTOR, wheel_d_m=WHEEL_D_M):
    """Metric rows for the optimizer table. original/proposed: role -> part; prof_*: role -> profile or None."""
    d0, d1 = derive(prof_o, n_motors, wheel_d_m), derive(prof_p, n_motors, wheel_d_m)
    c0, c1 = prof_o.get("controller"), prof_p.get("controller")
    out = []
    def row(key, metric, unit, hib, reason, roles, orig=None, prop=None, assume=None):
        o, p = (orig, prop) if orig is not None or prop is not None else (d0[key][0], d1[key][0])
        q = _origin(*[x for r in roles for x in (prof_o.get(r), prof_p.get(r))])
        if o is None or p is None:
            miss = sorted(set(d0.get(key, (0, [], []))[1] + d1.get(key, (0, [], []))[1])) if key in d0 else []
            return dict(key=key, metric=metric, unit=unit, original=None, proposed=None, diff=None, pct=None, status="unknown", quality="unavailable",
                        reason="No data yet for: " + (", ".join(miss) if miss else "one of the parts") + ".", evidence=[])
        cmp_ = calc.compare(o, p, hib, tol=1e-9 if abs(o) < 1 else 1e-6 * abs(o))
        return dict(key=key, metric=metric, unit=unit, original=o, proposed=p, diff=cmp_["diff"], pct=cmp_["pct"], status=cmp_["status"], quality=q,
                    reason=reason + (" Assumes " + "; ".join(assume) + "." if assume else ""), evidence=[])
    eff_changed = {profiles.ROLE_ALIASES.get(r, r) for r in changed} | set(changed)
    def aff(*roles): return bool(set(roles) & eff_changed)
    def flag(key, metric, unit): return dict(key=key, metric=metric, unit=unit, original=None, proposed=None, diff=None, pct=None, status="not_affected", quality="n/a", reason="This change does not influence this metric.", evidence=[])
    # connectivity / processing: controller only
    if "controller" in eff_changed:
        for k, nm, desc in (("wifi", "Wi-Fi available", "Yes = 1, No = 0."), ("bluetooth", "Bluetooth available", "Yes = 1, No = 0. Classic vs BLE is listed under 'What changes'.")):
            o, p = _a(c0, k), _a(c1, k)
            out.append(row(k, nm, "", True, desc, ["controller"], None if o is None else int(o), None if p is None else int(p)) if o is not None and p is not None else
                       dict(key=k, metric=nm, unit="", original=None, proposed=None, diff=None, pct=None, status="unknown", quality="unavailable", reason="No data yet for: " + k + ".", evidence=[]))
        for k, nm, unit, desc in (("clock_mhz", "Clock frequency", "MHz", "Clock only; an 8-bit AVR and a 32-bit core are not equal at the same MHz."), ("sram_kb", "RAM", "kB", "On-chip RAM."), ("flash_kb", "Program memory", "kB", "Flash available for firmware.")):
            o, p = _a(c0, k), _a(c1, k)
            out.append(row("processing" if k == "clock_mhz" else k, nm, unit, True, desc, ["controller"], o, p) if o is not None and p is not None else
                       dict(key="processing" if k == "clock_mhz" else k, metric=nm, unit=unit, original=None, proposed=None, diff=None, pct=None, status="unknown", quality="unavailable", reason="No data yet for: " + k + ".", evidence=[]))
        for k, nm, unit in (("adc_channels", "ADC channels", "ch"), ("pwm_channels", "PWM channels", "ch")):
            o, p = _a(c0, k), _a(c1, k)
            out.append(row(k, nm, unit, True, "Capability of the controller.", ["controller"], o, p) if o is not None and p is not None else
                       dict(key=k, metric=nm, unit=unit, original=None, proposed=None, diff=None, pct=None, status="unknown", quality="unavailable", reason="No data yet for: " + k + ".", evidence=[]))
    else:
        for k, nm, unit in (("wifi", "Wi-Fi available", ""), ("bluetooth", "Bluetooth available", ""), ("processing", "Clock frequency", "MHz")): out.append(flag(k, nm, unit))
    g0, g1 = d0["gpio"], d1["gpio"]
    out.append(row("gpio", "Spare GPIO pins", "pins", True, "Controller pins minus pins the driver and sensor need.", ["controller", "driver", "sensor"], g0[0], g1[0], g1[2]) if aff("controller", "driver", "sensor") else flag("gpio", "Spare GPIO pins", "pins"))
    spec = [("power", "Power consumption", "mW", False, "Battery nominal voltage x total typical current.", ("controller", "driver", "motor", "battery", "sensor")),
            ("runtime", "Battery runtime", "h", True, "Usable capacity / total typical current. Theoretical, not measured.", ("controller", "driver", "motor", "battery", "sensor")),
            ("speed", "Top speed (ideal)", "m/s", True, "Motor rpm at the voltage it actually receives, times wheel circumference.", ("driver", "motor", "battery")),
            ("torque", "Wheel torque (stall, per motor)", "N·m", True, "Stall torque at the voltage the motor actually receives.", ("driver", "motor", "battery")),
            ("traction", "Pushing force (stall, total)", "N", True, "All driven wheels, ideal grip. Matters for sumo-style pushing.", ("driver", "motor", "battery")),
            ("efficiency", "Motor-stage efficiency", "%", True, "How much battery power survives the driver's voltage drop and switching loss.", ("driver", "battery")),
            ("weight", "Weight (electronics)", "g", False, "Sum of the five electronics parts.", ("controller", "driver", "motor", "battery", "sensor"))]
    has_motor = bool(prof_o.get("motor") or prof_p.get("motor"))
    for key, nm, unit, hib, reason, roles in spec:
        if not aff(*roles): out.append(flag(key, nm, unit)); continue
        if key in ("speed", "torque", "traction", "efficiency") and not has_motor:
            out.append(flag(key, nm, unit)); continue
        out.append(row(key, nm, unit, hib, reason, list(roles), assume=d1[key][2]))
    return dict(rows=out, d0=d0, d1=d1)
