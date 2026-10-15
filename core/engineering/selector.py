"""Pick the cheapest build that passes validation.

Combinations are enumerated in ascending cost order (heap-based k-way merge), so we can stop
as soon as we have what we need instead of brute-forcing everything.
Ranking among valid builds: fewest UNKNOWN checks first, then lowest total cost.
"""
from __future__ import annotations

import heapq
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .rules import Rule
from core.schemas import CheckResult, Part
from .validator import evaluate_build, quick_eval


@dataclass
class Candidate:
    part: Part
    qty: int
    line_cost: float


@dataclass
class Build:
    parts: dict[str, Part]
    qty: dict[str, int]
    parts_cost: float
    shipping_rows: list[dict]
    shipping_total: float
    total: float
    checks: list[CheckResult]
    counts: dict
    status: str
    derived: dict

    @property
    def fail_ids(self) -> list[str]:
        return [c.rule_id for c in self.checks if c.status == "fail"]


@dataclass
class Selection:
    chosen: Optional[Build] = None
    within_budget: bool = False
    alternatives: list[Build] = field(default_factory=list)
    rejected: list[Build] = field(default_factory=list)
    naive: Optional[Build] = None
    fail_stats: Counter = field(default_factory=Counter)
    evaluated: int = 0
    truncated: bool = False
    excluded: list[dict] = field(default_factory=list)
    message: str = ""


def qty_for(category: str, part: Part, ctx: dict) -> int:
    if category == "motor":
        return int(ctx["motor_count"])
    if category == "sensor":
        ch = part.spec_value("channels")
        return max(1, math.ceil(ctx["sensor_channels"] / ch)) if ch else 1
    return 1


def shipping_breakdown(parts: dict[str, Part], qty: dict[str, int], config: dict) -> tuple[list[dict], float]:
    by_vendor: dict[str, float] = {}
    for cat, p in parts.items():
        by_vendor[p.vendor] = by_vendor.get(p.vendor, 0.0) + qty[cat] * float(p.price.value)
    ship_cfg = config.get("shipping", {})
    default = float(ship_cfg.get("default_flat_inr", 0))
    rows, total = [], 0.0
    for vendor, subtotal in by_vendor.items():
        rule = (ship_cfg.get("per_vendor") or {}).get(vendor, {})
        flat = float(rule.get("flat_inr", default))
        free_above = rule.get("free_above_inr")
        ship = 0.0 if (free_above is not None and subtotal >= float(free_above)) else flat
        rows.append({"vendor": vendor, "subtotal": subtotal, "shipping": ship})
        total += ship
    return rows, total


def _make_build(parts: dict[str, Part], qty: dict[str, int], ctx: dict, config: dict, rules: list[Rule]) -> Build:
    parts_cost = sum(qty[c] * float(p.price.value) for c, p in parts.items())
    rows, ship_total = shipping_breakdown(parts, qty, config)
    checks, counts, status, derived = evaluate_build(parts, ctx, rules, config["assumptions"])
    return Build(parts=dict(parts), qty=dict(qty), parts_cost=parts_cost, shipping_rows=rows,
                 shipping_total=ship_total, total=parts_cost + ship_total, checks=checks,
                 counts=counts, status=status, derived=derived)


def _enumerate_by_cost(lists: list[list[Candidate]]):
    n = len(lists)
    start = (0,) * n

    def cost(idx):
        return sum(lists[i][idx[i]].line_cost for i in range(n))

    heap = [(cost(start), start)]
    seen = {start}
    while heap:
        c, idx = heapq.heappop(heap)
        yield c, idx
        for i in range(n):
            if idx[i] + 1 < len(lists[i]):
                nxt = idx[:i] + (idx[i] + 1,) + idx[i + 1:]
                if nxt not in seen:
                    seen.add(nxt)
                    heapq.heappush(heap, (cost(nxt), nxt))


def select_build(catalog: dict[str, Part], ctx: dict, config: dict, rules: list[Rule],
                 max_evals: int = 20000) -> Selection:
    rt = config["robot_types"][ctx["robot_type"]]
    cats: list[str] = rt["categories"]
    sel = Selection()

    cands: dict[str, list[Candidate]] = {}
    for cat in cats:
        lst: list[Candidate] = []
        for p in catalog.values():
            if p.category != cat:
                continue
            if cat == "sensor" and rt.get("sensor_kind") and (p.kind or "").lower() != rt["sensor_kind"]:
                continue
            if p.price is None or p.price.value is None:
                sel.excluded.append({"part": p.name, "reason": "no price found"})
                continue
            if p.in_stock is not None and p.in_stock.value is False:
                sel.excluded.append({"part": p.name, "reason": "out of stock"})
                continue
            q = qty_for(cat, p, ctx)
            lst.append(Candidate(p, q, q * float(p.price.value)))
        lst.sort(key=lambda c: (c.line_cost, c.part.id))
        cands[cat] = lst

    empty = [c for c in cats if not cands[c]]
    if empty:
        sel.message = f"No usable parts for: {', '.join(empty)}. Add parts or refresh data in the Parts tab."
        return sel

    lists = [cands[c] for c in cats]
    budget = ctx["budget_inr"]
    valid: list[dict] = []
    rejected: list[dict] = []
    first: Optional[dict] = None

    for parts_cost, idx in _enumerate_by_cost(lists):
        if sel.evaluated >= max_evals:
            sel.truncated = True
            break
        picked = {cats[i]: lists[i][idx[i]] for i in range(len(cats))}
        parts = {c: x.part for c, x in picked.items()}
        qty = {c: x.qty for c, x in picked.items()}
        fails, unknowns = quick_eval(parts, ctx, rules, config["assumptions"])
        sel.evaluated += 1
        rec = {"parts": parts, "qty": qty, "cost": parts_cost, "fails": fails, "unknowns": unknowns}
        if first is None:
            first = rec
        if fails:
            sel.fail_stats.update(fails)
            if len(rejected) < 6:
                rejected.append(rec)
        else:
            rec["total"] = parts_cost + shipping_breakdown(parts, qty, config)[1]
            valid.append(rec)

        if parts_cost > budget and valid:
            # Past the budget: stop once we hold an in-budget build, or a fully verified fallback.
            if any(v["total"] <= budget for v in valid) or any(not v["unknowns"] for v in valid):
                break
        verified_in_budget = any((not v["unknowns"]) and v["total"] <= budget for v in valid)
        if verified_in_budget and len(valid) >= 5:
            break

    if first is not None:
        sel.naive = _make_build(first["parts"], first["qty"], ctx, config, rules)
    sel.rejected = [_make_build(r["parts"], r["qty"], ctx, config, rules) for r in rejected]

    if not valid:
        sel.message = ("No compatible build exists in the current catalog. "
                       "Check the rejected builds below, add parts, or relax the requirements.")
        return sel

    in_budget = [v for v in valid if v["total"] <= budget]
    if in_budget:
        ranked = sorted(in_budget, key=lambda v: (len(v["unknowns"]), v["total"]))
        sel.within_budget = True
    else:
        ranked = sorted(valid, key=lambda v: (len(v["unknowns"]), v["total"]))
        sel.within_budget = False
        sel.message = (f"The best compatible build is over your budget "
                       f"(budget {budget:,.0f}, this build {ranked[0]['total']:,.0f}).")
    best = ranked[0]
    sel.chosen = _make_build(best["parts"], best["qty"], ctx, config, rules)
    others = [v for v in sorted(valid, key=lambda v: (len(v["unknowns"]), v["total"])) if v is not best][:4]
    sel.alternatives = [_make_build(v["parts"], v["qty"], ctx, config, rules) for v in others]
    return sel
