"""Runs the known-good / known-bad builds so the validator can prove it catches real problems."""
from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR
from .schemas import Part, Requirements
from core.engineering.validator import evaluate_build


def load_cases(data_dir: Path = DATA_DIR) -> list[dict]:
    with open(data_dir / "test_builds.json", encoding="utf-8") as f:
        return json.load(f)


def run_case(case: dict, seed_catalog: dict[str, Part], rules, config: dict) -> dict:
    ctx = Requirements(**case["req"]).to_ctx(config)
    parts = {role: seed_catalog[pid] for role, pid in case["parts"].items()}
    checks, counts, status, _ = evaluate_build(parts, ctx, rules, config["assumptions"])
    fails = sorted(c.rule_id for c in checks if c.status == "fail")
    unknowns = sorted(c.rule_id for c in checks if c.status == "unknown")
    ok = (status == case["expect_status"] and fails == sorted(case["expect_fail"])
          and unknowns == sorted(case["expect_unknown"]))
    return {"name": case["name"], "expected": case["expect_status"], "actual": status,
            "fails": fails, "unknowns": unknowns, "counts": counts, "ok": ok}
