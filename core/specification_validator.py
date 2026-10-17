"""Data-quality checks for data/components.json. Never fills, converts or upgrades values.
Run: python -m core.specification_validator"""
import re, sys
from urllib.parse import urlparse
from . import component_catalog as cat

CATEGORIES = {"controller", "motor", "driver", "battery", "sensor", "mechanical", "power", "accessory"}
COMMON = ["id", "name", "category", "specifications", "specification_sources", "verification_status", "notes", "description"]
STATUSES = {"verified", "partially_verified", "unverified"}
REQUIRED = dict(controller=["vin_min_v", "vin_max_v", "logic_v"], driver=["supply_min_v", "supply_max_v", "continuous_current_a_per_channel"],
                motor=["rated_voltage_min_v", "rated_voltage_max_v", "stall_current_a"], battery=["nominal_v", "full_charge_v", "capacity_mah"],
                sensor=["supply_min_v", "supply_max_v"])
UNITS = {"V": "V", "A": "A", "mA": "mA", "mAh": "mAh", "MHz": "MHz", "kB": "kB", "rpm": "rpm", "count": "count", "bool": "bool", "°C": "°C", "kg·cm": "kg·cm"}
RANGE = {"V": (0, 60), "A": (0, 100), "mA": (0, 20000), "mAh": (0, 100000), "MHz": (0, 5000), "kB": (0, 1e7), "rpm": (0, 100000), "count": (0, 1000), "°C": (-100, 300), "kg·cm": (0, 1000)}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def validate(records):
    """Returns list of dict(level='error'|'warning', id, msg)."""
    out, seen = [], set()
    add = lambda lvl, i, m: out.append(dict(level=lvl, id=i, msg=m))
    for r in records:
        i = r.get("id", "?")
        for f in COMMON:
            if f not in r: add("error", i, f"missing field '{f}'")
        if i in seen: add("error", i, "duplicate id")
        seen.add(i)
        if r.get("category") not in CATEGORIES: add("error", i, f"invalid category {r.get('category')!r}")
        if r.get("verification_status") not in STATUSES: add("error", i, "invalid verification_status")
        specs = r.get("specifications", {})
        for k in REQUIRED.get(r.get("category"), []):
            if k not in specs: add("error", i, f"required spec '{k}' missing (use null if unknown)")
        for k, s in specs.items():
            if not isinstance(s, dict) or "value" not in s or "unit" not in s: add("error", i, f"{k}: must be {{value, unit}}"); continue
            u, v = s["unit"], s["value"]
            if u not in UNITS: add("error", i, f"{k}: unknown unit {u!r}"); continue
            if v is None: continue
            if u == "bool":
                if not isinstance(v, bool): add("error", i, f"{k}: expected true/false/null")
            elif isinstance(v, bool) or not isinstance(v, (int, float)): add("error", i, f"{k}: not a number ({v!r})")
            else:
                lo, hi = RANGE[u]
                if v == 0 and k.endswith(("_v", "_mah", "_rpm")) and k not in ("drop_v",): add("warning", i, f"{k}: 0 is suspicious (unknown must be null)")
                if not lo <= v <= hi: add("error", i, f"{k}: {v} {u} outside plausible range {lo}..{hi}")
        # ---- evidence ----
        ev = r.get("specification_sources", [])
        for e in ev:
            for f in ("field", "value", "unit", "source_url", "retrieved", "status"):
                if f not in e: add("error", i, f"evidence missing '{f}'")
            if urlparse(e.get("source_url", "")).scheme not in ("http", "https"): add("error", i, f"{e.get('field')}: bad source_url")
            if not DATE.match(str(e.get("retrieved", ""))): add("error", i, f"{e.get('field')}: bad retrieved date")
            sp = specs.get(e.get("field"))
            if sp is None: add("error", i, f"evidence for unknown field {e.get('field')!r}")
            elif e.get("status") == "verified":
                if sp.get("value") != e.get("value") or sp.get("unit") != e.get("unit"): add("error", i, f"{e['field']}: evidence value/unit differs from specification")
                if not e.get("note"): add("warning", i, f"{e['field']}: verified evidence has no quotation/note")
        vf = cat.verified_fields(r)
        non_null = {k for k, s in specs.items() if isinstance(s, dict) and s.get("value") is not None}
        status = r.get("verification_status")
        if status == "verified" and non_null - vf: add("error", i, "status 'verified' but fields lack evidence: " + ", ".join(sorted(non_null - vf)))
        if status == "verified" and any(isinstance(s, dict) and s.get("value") is None for s in specs.values()): add("error", i, "status 'verified' but some fields are null")
        if status == "partially_verified" and not vf: add("error", i, "'partially_verified' without any verified field")
        if status == "unverified" and vf: add("warning", i, "has verified evidence but status is 'unverified'")
        if vf and not r.get("last_verified"): add("error", i, "evidence present but last_verified is empty")
        # ---- cross-field consistency ----
        g = lambda k: cat.spec_value(r, k)
        pairs = [("nominal_v", "full_charge_v", "battery nominal voltage must be below full-charge voltage"),
                 ("vin_min_v", "vin_max_v", "vin_min_v must be <= vin_max_v"), ("supply_min_v", "supply_max_v", "supply_min_v must be <= supply_max_v"),
                 ("rated_voltage_min_v", "rated_voltage_max_v", "motor min voltage must be <= max voltage")]
        for lo, hi, msg in pairs:
            a, b = g(lo), g(hi)
            num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
            if num(a) and num(b) and (a >= b if lo == "nominal_v" else a > b): add("error", i, msg)
        if r.get("category") == "battery":
            if g("capacity_mah") is not None and g("max_continuous_discharge_a") is None: add("warning", i, "capacity known but discharge limit unknown: do not assume one")
    return out

def report(records):
    issues = validate(records)
    cov = cat.coverage(records)
    from collections import Counter
    c = Counter(r["verification_status"] for r in records)
    return dict(n=len(records), status=dict(c), errors=[x for x in issues if x["level"] == "error"], warnings=[x for x in issues if x["level"] == "warning"],
                coverage=cov, missing_required={r["id"]: [k for k in REQUIRED.get(r["category"], []) if cat.spec_value(r, k) is None] for r in records})

if __name__ == "__main__":
    rep = report(cat.load())
    print(f"{rep['n']} components: {rep['status']}")
    for r in cat.load():
        v, t = rep["coverage"][r["id"]]; m = rep["missing_required"][r["id"]]
        print(f"  {r['id']:<24} {r['verification_status']:<19} {v}/{t} fields verified" + (f" | unknown required: {', '.join(m)}" if m else ""))
    for x in rep["errors"]: print("ERROR  ", x["id"], x["msg"])
    for x in rep["warnings"]: print("WARNING", x["id"], x["msg"])
    sys.exit(1 if rep["errors"] else 0)
