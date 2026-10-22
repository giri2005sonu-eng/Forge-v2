"""Evidence ledger: every number in the BOM with where it came from.

verified = read from a shop page; the quote is a verbatim slice of that page, with URL, time and method.
seed     = typed in by the team (typical datasheet value or rough estimate), NOT checked against any page.
Pure functions, so everything is testable offline.
"""
import csv, io
from . import part_specs
from .data import QTY

FIELDS = ["part_id", "part", "role", "field", "value", "unit", "status", "source", "source_url", "retrieved_at", "method", "quote", "note"]
SEED_NOTE = "Typical datasheet value entered by the team (common hobby board); not verified on a page"
UNITS = {"vin_min_v": "V", "vin_max_v": "V", "logic_v": "V", "supply_min_v": "V", "supply_max_v": "V", "drop_v": "V", "max_a": "A",
         "min_v": "V", "max_v": "V", "stall_a": "A", "nominal_v": "V"}


def _host(url):
    from urllib.parse import urlparse
    return (urlparse(url or "").netloc or "").removeprefix("www.")


def rows(parts, live, choice=None, manual=None):
    """Ledger rows for the chosen parts. `live` = {part_id: [offer, ...]} as stored by the app; `choice` = {part_id: url}."""
    from . import bill
    out = []
    for key, p in parts.items():
        if p.get("none"): continue
        role = p.get("role", key)
        base = dict(part_id=p["id"], part=p["name"], role=role)
        man = bill.manual_pick(p["id"], manual)
        chosen = None if man else bill.chosen_url(p["id"], live, choice or {})
        verified = bill.offers_for(p["id"], live)
        if man:
            out.append(dict(base, field="price_inr", value=man["price"], unit="INR", status="user-entered", source=_host(man["url"]), source_url=man["url"],
                            retrieved_at="", method="typed by the user", quote="", note="Listing chosen by the user; price typed by the user, NOT read from the page"))
        for o in verified:
            ev = dict(base, status="verified", source=_host(o["url"]), source_url=o["url"], retrieved_at=o.get("checked_at") or "",
                      method=o.get("method") or "read before ledger existed", quote=o.get("quote") or "")
            used = " (used in BOM)" if o["url"] == chosen else ""
            out.append(dict(ev, field="price_inr", value=o["price"], unit="INR", note=("Chosen listing" if used else "Alternative listing")))
            if o.get("name"): out.append(dict(ev, field="listing_name", value=o["name"], unit="", note="Copied from the page"))
        if not verified and not man and p.get("seed_price") is None:
            out.append(dict(base, field="price_inr", value="", unit="INR", status="unverified", source="", source_url="", retrieved_at="",
                            method="", quote="", note="No verified shop price found; part is not in the total"))
        elif not verified and not man:
            out.append(dict(base, field="price_inr", value=p["seed_price"], unit="INR", status="seed", source="FORGE seed catalog",
                            source_url="", retrieved_at="", method="team estimate", quote="", note="Rough estimate; no verified shop price yet"))
        for o in bill.unverified_for(p["id"], live):
            out.append(dict(base, field="listing", value="price not verified", unit="", status="unverified", source=_host(o["url"]),
                            source_url=o["url"], retrieved_at=o.get("checked_at") or "", method="", quote="", note=o.get("note") or "No verifiable price on the page"))
        for k, v in (p.get("specs") or {}).items():
            out.append(dict(base, field=k, value=v, unit=UNITS.get(k) or part_specs.unit(k), status="seed", source="FORGE seed catalog", source_url="",
                            retrieved_at="", method="typical datasheet value", quote="", note=SEED_NOTE))
    return out


def summary(rs):
    n = lambda s: sum(r["status"] == s for r in rs)
    return dict(verified=n("verified"), manual=n("user-entered"), seed=n("seed"), unverified=n("unverified"), total=len(rs))


def _safe(v):
    """CSV cells come partly from web pages. A leading = + - @ would run as a formula in Excel, so neutralise it."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(rs):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rs: w.writerow({k: _safe(r.get(k)) for k in FIELDS})
    return buf.getvalue()
