"""Tables for the BOM and the evidence ledger."""
from __future__ import annotations

import pandas as pd

from .selector import Build

CAT_LABEL = {"controller": "Controller", "driver": "Motor driver", "motor": "Motors",
             "battery": "Battery", "sensor": "Sensors", "chassis": "Chassis"}


def bom_table(build: Build) -> pd.DataFrame:
    rows = []
    for cat, p in build.parts.items():
        q = build.qty[cat]
        unit = float(p.price.value)
        rows.append({
            "Category": CAT_LABEL.get(cat, cat), "Part": p.name, "Vendor": p.vendor, "Qty": q,
            "Unit price (INR)": unit, "Line total (INR)": unit * q,
            "In stock": ("yes" if p.in_stock.value else "no") if (p.in_stock and p.in_stock.value is not None) else "unknown",
            "Price source": p.price.evidence.source_url or "seed catalog (unverified)",
            "Price retrieved (UTC)": p.price.evidence.retrieved_at,
            "Price method": p.price.evidence.method,
        })
    return pd.DataFrame(rows)


def ledger_table(build: Build, spec_defs: dict) -> pd.DataFrame:
    """One row per value used in the build. Missing specs appear as NOT FOUND, never guessed."""
    rows = []
    for cat, p in build.parts.items():
        pe = p.price.evidence
        rows.append({"Part": p.name, "Field": "price_inr", "Value": p.price.value, "Unit": "INR",
                     "Source URL": pe.source_url or "", "Retrieved (UTC)": pe.retrieved_at,
                     "Method": pe.method, "Quote / note": pe.quote or pe.note or ""})
        for key, d in spec_defs[cat].items():
            s = p.specs.get(key)
            if s is None or s.value is None:
                rows.append({"Part": p.name, "Field": key, "Value": "NOT FOUND", "Unit": d.get("unit") or "",
                             "Source URL": "", "Retrieved (UTC)": "", "Method": "", "Quote / note": "unknown - never guessed"})
            else:
                e = s.evidence
                rows.append({"Part": p.name, "Field": key, "Value": s.value, "Unit": s.unit or "",
                             "Source URL": e.source_url or "", "Retrieved (UTC)": e.retrieved_at,
                             "Method": e.method, "Quote / note": e.quote or e.note or ""})
    df = pd.DataFrame(rows)
    df["Value"] = df["Value"].astype(str)   # mixed numbers/text -> keep Arrow happy
    return df


def checks_table(build: Build) -> pd.DataFrame:
    icon = {"pass": "PASS", "fail": "FAIL", "unknown": "UNKNOWN"}
    rows = []
    for c in build.checks:
        ev = "; ".join(f"{e.field}={e.value}{(' ' + e.unit) if e.unit else ''} [{e.method}]" for e in c.evidence)
        rows.append({"Status": icon[c.status], "Category": c.category, "Check": c.title,
                     "Result": c.message, "Evidence used": ev})
    return pd.DataFrame(rows)
