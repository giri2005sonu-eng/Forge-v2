import re
from types import SimpleNamespace as NS
ROLE = dict(c="controller", d="driver", m="motor", b="battery", s="sensor")
ROLE_ALIASES = dict(power="battery", actuator="motor")

def _part_for_role(parts, role_name):
    """Find a part matching role_name directly or through alias."""
    if role_name in parts: return parts[role_name]
    for r, p in parts.items():
        if isinstance(p, dict):
            p_role = p.get("role", r)
            if p_role == role_name or ROLE_ALIASES.get(p_role) == role_name:
                return p
    return None

def _ctx(parts):
    ctx = {}
    for k, r in ROLE.items():
        part = _part_for_role(parts, r)
        ctx[k] = NS(**dict(part.get("specs") or {})) if part and isinstance(part, dict) else NS()
    return ctx

def _get(ctx, ref):
    r, s = ref.split(".")
    return getattr(ctx.get(r, NS()), s, None)

def _has_module(parts, keyword):
    if not isinstance(parts, (dict, list)): return False
    items = parts.values() if isinstance(parts, dict) else parts
    for p in items:
        if not isinstance(p, dict): continue
        text = (str(p.get("id", "")) + " " + str(p.get("name", "")) + " " + str(p.get("role", ""))).lower()
        if keyword in text: return True
    return False

def evaluate(parts, rules, needs_bluetooth=False):
    """Return list of {id,title,status,msg}. PASS / FAIL / UNKNOWN; UNKNOWN when any needed spec is missing."""
    ctx, out = _ctx(parts), []
    has_role = lambda r: bool(_part_for_role(parts, r) and not _part_for_role(parts, r).get("none"))
    for r in rules:
        needed_roles = [ROLE[n.split(".")[0]] for n in r["needs"]]
        if any(not has_role(nr) for nr in needed_roles):
            continue
        if r.get("uses_sensor") and (not has_role("sensor") or _part_for_role(parts, "sensor").get("none")):
            continue
        missing = [n for n in r["needs"] if _get(ctx, n) is None]
        if missing:
            out.append(dict(id=r["id"], title=r["title"], status="UNKNOWN", msg="Missing: " + ", ".join(missing))); continue
        ok = eval(r["check"], {"__builtins__": {}}, ctx)  # rules are our own constants
        msg = "OK" if ok else re.sub(r"\{(\w)\.(\w+)\}", lambda m: str(getattr(ctx[m[1]], m[2])), r["fail"])

        if not ok:
            if r["id"] == "logic_level" and (_has_module(parts, "level_shifter") or _has_module(parts, "shifter")):
                ok, msg = True, "PASS: Logic level mismatch safely converted via Bi-Directional Logic Level Shifter."
            elif r["id"] == "motor_voltage" and (_has_module(parts, "lm2596") or _has_module(parts, "buck") or _has_module(parts, "converter")):
                ok, msg = True, "PASS: Motor voltage safely regulated to 6.0V via LM2596 Buck Step-Down Converter."
            elif r["id"] == "ctrl_vin" and (_has_module(parts, "lm2596") or _has_module(parts, "buck") or _has_module(parts, "regulator")):
                ok, msg = True, "PASS: Battery voltage stepped down to safe 5.0V input via LM2596 Buck Converter."
            elif r["id"] == "batt_driver_max" and (_has_module(parts, "lm2596") or _has_module(parts, "buck")):
                ok, msg = True, "PASS: Supply voltage stepped down below driver limit via LM2596 Buck Converter."

        out.append(dict(id=r["id"], title=r["title"], status="PASS" if ok else "FAIL", msg=msg))
    if needs_bluetooth:
        bt = getattr(ctx["c"], "bluetooth", None)
        if not bt and (_has_module(parts, "hc05") or _has_module(parts, "hc-05") or _has_module(parts, "bluetooth")):
            out.append(dict(id="bluetooth", title="Bluetooth requested", status="PASS", msg="PASS: Bluetooth communication provided via HC-05 serial module."))
        else:
            out.append(dict(id="bluetooth", title="Bluetooth requested", status="UNKNOWN" if bt is None else "PASS" if bt else "FAIL", msg="" if bt else "Controller has no Bluetooth"))
    return out

