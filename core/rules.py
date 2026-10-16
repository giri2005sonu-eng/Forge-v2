import re
from types import SimpleNamespace as NS
ROLE = dict(c="controller", d="driver", m="motor", b="battery", s="sensor")

def _ctx(parts):
    return {k: NS(**dict(parts[r]["specs"])) for k, r in ROLE.items()}

def _get(ctx, ref):
    r, s = ref.split(".")
    return getattr(ctx[r], s, None)

def evaluate(parts, rules, needs_bluetooth=False):
    """Return list of {id,title,status,msg}. PASS / FAIL / UNKNOWN; UNKNOWN when any needed spec is missing."""
    ctx, out = _ctx(parts), []
    for r in rules:
        if r.get("uses_sensor") and parts["sensor"].get("none"): continue
        missing = [n for n in r["needs"] if _get(ctx, n) is None]
        if missing:
            out.append(dict(id=r["id"], title=r["title"], status="UNKNOWN", msg="Missing: " + ", ".join(missing))); continue
        ok = eval(r["check"], {"__builtins__": {}}, ctx)  # rules are our own constants
        msg = "OK" if ok else re.sub(r"\{(\w)\.(\w+)\}", lambda m: str(getattr(ctx[m[1]], m[2])), r["fail"])
        out.append(dict(id=r["id"], title=r["title"], status="PASS" if ok else "FAIL", msg=msg))
    if needs_bluetooth:
        bt = getattr(ctx["c"], "bluetooth", None)
        out.append(dict(id="bluetooth", title="Bluetooth requested", status="UNKNOWN" if bt is None else "PASS" if bt else "FAIL", msg="" if bt else "Controller has no Bluetooth"))
    return out
