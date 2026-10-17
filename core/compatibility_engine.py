"""Compatibility results with rule id, status, components, actual/limit, explanation and action.
Wraps the existing rule engine (core/rules.py, core/data.RULES) and adds catalog-aware rules. PASS / WARN / FAIL / UNKNOWN; missing data is never a pass."""
from .data import RULES
from .rules import evaluate

ACTION = dict(batt_driver_min="Use a battery with a higher voltage or a driver with a lower minimum supply.",
              batt_driver_max="Use a lower-voltage battery or a driver that accepts the charged voltage.",
              motor_voltage="Pick a motor rated for the voltage left after the driver drop, or change battery/driver.",
              driver_stall="Use a driver rated above the motor's stall current.",
              ctrl_vin="Add a regulator or choose a battery within the controller's input range.",
              logic_level="Add a level shifter or choose a sensor that works at the controller's logic voltage.",
              bluetooth="Choose a controller with Bluetooth.")
INVOLVES = dict(batt_driver_min="battery, driver", batt_driver_max="battery, driver", motor_voltage="battery, driver, motor", driver_stall="driver, motor",
                ctrl_vin="controller, battery", logic_level="controller, sensor", bluetooth="controller")

def _row(rule_id, title, status, comps, msg, action="", actual=None, limit=None, quality="seed"):
    return dict(rule_id=rule_id, title=title, status=status, components=comps, explanation=msg, action=action if status in ("FAIL", "WARN") else "", actual=actual, limit=limit, quality=quality)

def check(parts, catalog_by_legacy=None, needs_bt=False):
    """parts: role -> part dict whose specs may already be merged with verified catalog values (see optimizer.merge_specs)."""
    out = []
    for c in evaluate(parts, RULES, needs_bt):
        out.append(_row(c["id"], c["title"], c["status"], INVOLVES.get(c["id"], ""), c["msg"], ACTION.get(c["id"], "")))
    # extra rule: battery voltage vs a controller whose docs give only a fixed supply (e.g. 5 V pin) -> cannot confirm direct connection
    ctrl = parts.get("controller") or next((p for p in parts.values() if isinstance(p, dict) and p.get("role") == "controller"), None)
    bat = parts.get("battery") or parts.get("power") or next((p for p in parts.values() if isinstance(p, dict) and p.get("role") in ("battery", "power")), None)
    if ctrl and bat and not bat.get("none"):
        sup, bmax = ctrl.get("_verified", {}).get("supply_nominal_v"), (bat.get("specs") or {}).get("max_v")
        if sup is not None and (ctrl.get("specs") or {}).get("vin_max_v") is not None and ctrl.get("_provenance", {}).get("vin_max_v") != "verified":
            if bmax is None: out.append(_row("ctrl_fixed_supply", "Controller supply documented for this battery", "UNKNOWN", "controller, battery", "Battery voltage unknown.", quality="verified"))
            elif bmax > sup + 0.5:
                out.append(_row("ctrl_fixed_supply", "Controller supply documented for this battery", "WARN", "controller, battery",
                                f"Official docs only describe a {sup:g} V supply for {ctrl['name']}; the battery reaches {bmax:g} V and no wider input range is documented.",
                                "Add a regulator (e.g. buck converter) to 5 V instead of connecting the battery directly.", actual=bmax, limit=sup, quality="verified"))
            else: out.append(_row("ctrl_fixed_supply", "Controller supply documented for this battery", "PASS", "controller, battery", "Battery within the documented supply.", actual=bmax, limit=sup, quality="verified"))
    return out

def summary(rows):
    c = lambda s: sum(r["status"] == s for r in rows)
    return dict(fail=c("FAIL"), warn=c("WARN"), unknown=c("UNKNOWN"), passed=c("PASS"),
                ready=c("FAIL") == 0, state="incompatible" if c("FAIL") else "caution" if c("WARN") or c("UNKNOWN") else "compatible")
