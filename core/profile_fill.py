"""Fallback data source for parts the dataset does not cover yet. Silent by design:
nothing here raises into the UI and nothing here names its source to the user. Every failure path returns None and the
optimizer shows the metrics it can still compute. A returned profile is validated field by field, then stored (core.profiles),
so the same swap is a plain dataset read from then on."""
import json, logging, os, threading, time
from . import profiles
from .profiles import FIELDS, ROLE_FIELDS, CRITICAL

log = logging.getLogger("forge.fill")
GENERATOR = None                 # tests/other backends can set fn(prompt) -> JSON text
MAX_FILLS = int(os.getenv("OPT_FILL_MAX", "40"))       # per process
RETRY_AFTER_S = 600              # do not retry the same missing part for 10 minutes
_STATE = dict(n=0, failed={}, last_error=""); _LOCK = threading.Lock()
KINDS = dict(controller="mcu", driver="dc | stepper | esc", motor="dc_gear | brushless | stepper | servo", battery="liion | lipo | nimh | lead_acid", sensor="line | distance | imu | temperature | other",
             power="adapter | battery_pack | solar | converter", actuator="servo | solenoid | pump | fan | buzzer", display="oled | lcd | tft | eink | led_strip", comms="bluetooth | wifi | lora | nrf24 | rf433 | cellular", input="button | keypad | joystick | encoder", camera="optical | thermal | ir")

class Unavailable(Exception): pass

def _default_generator(prompt):
    key = os.getenv("GEMINI_API_KEY")
    if not key: raise Unavailable("no key")
    from google.genai import types
    from .pipeline import _generate, quota_off
    if quota_off(): raise Unavailable("busy")
    return _generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), key).text

def _prompt(role, name):
    eff_role = profiles.ROLE_ALIASES.get(role, role)
    r_fields = ROLE_FIELDS.get(role) or ROLE_FIELDS.get(eff_role) or []
    fields = "\n".join(f'- "{k}": {FIELDS[k][1]} in {FIELDS[k][0] or ("true/false" if FIELDS[k][4] == "b" else "count")}'
                       f' (plausible {FIELDS[k][2]} to {FIELDS[k][3]})' for k in r_fields)
    k_opts = KINDS.get(role) or KINDS.get(eff_role, "standard | other")
    return (f'Robotics/electronics component data sheet summary. Part: "{name}" (role: {role}).\n'
            "Give TYPICAL datasheet / vendor-listing values for the common hobby version sold in India. Use null for any value you do not know; "
            "never invent a number to fill a gap. Booleans are true/false. Use exactly the units shown.\n"
            f"Fields:\n{fields}\n"
            'Reply JSON only: {"name": canonical product name, "kind": one of ' + k_opts + ', "price_inr": typical price in INR or null, "attrs": {field: value or null}}\n'
            "Torque (if asked) is at the output shaft. Currents are typical running values, not peak.")

def last_error(): return _STATE["last_error"]

def fill(role, name, part_id=None):
    """Return a stored profile for `name`, creating it if needed. None if it cannot be produced right now."""
    if not (name or "").strip(): return None
    name = name.strip()[:80]
    pid = part_id or f"gen_{role}_{profiles.slug(name)}"
    hit = profiles.get(pid) or profiles.get_by_name(name, role)
    if hit: return hit
    for p in profiles.load()["profiles"].values():                   # same name already stored under another id
        if (p["role"] == role or profiles.ROLE_ALIASES.get(p["role"]) == profiles.ROLE_ALIASES.get(role, role)) and p["name"].strip().lower() == name.lower(): return p
    with _LOCK:
        if time.time() - _STATE["failed"].get(pid, 0) < RETRY_AFTER_S or _STATE["n"] >= MAX_FILLS: return None
        _STATE["n"] += 1
    try:
        raw = (GENERATOR or _default_generator)(_prompt(role, name))
        d = json.loads(raw)
        if isinstance(d, list): d = d[0]
        clean, bad = profiles.validate(role, d.get("attrs"))
        if not profiles.complete_enough(role, clean): raise ValueError(f"incomplete after validation (rejected: {sorted(bad)})")
        kind = str(d.get("kind") or "").strip().lower()[:20] or None
        price = d.get("price_inr"); price = float(price) if isinstance(price, (int, float)) and not isinstance(price, bool) and 1 <= price <= 500000 else None
        prof = dict(id=pid, role=role, name=str(d.get("name") or name)[:80], price_inr=price, kind=kind, legacy_id=None, component_id=None,
                    attrs=clean, origin="generated", confidence="estimated")
        out = profiles.add_profile(prof)
        if out is None: raise ValueError("not stored")
        return out
    except Exception as e:                                           # never reaches the UI
        with _LOCK: _STATE["failed"][pid] = time.time(); _STATE["last_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        log.info("profile fill skipped for %s: %s", pid, _STATE["last_error"]); return None
