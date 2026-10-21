"""Reproducible recommender evaluation: python -m tests.eval.run_eval --version v1."""
import argparse
import json
import random
from pathlib import Path

from core import picker
from core.recommendation_catalog import (
    PROJECT_CATALOG,
    PROJECT_FACTOR_CATALOG,
    RECOMMENDATION_PROJECT_KEYS,
)
from tests.eval.personas import PERSONAS

ROOT = Path(__file__).resolve().parents[2]
BASELINES = Path(__file__).with_name("baselines")
EXPERIENCE = ["sensor_read", "soldering", "motor_driver", "breadboard", "raspberry_pi", "trained_model"]
CAREERS = ["embedded", "robotics", "vision", "iot", "undecided"]
INTERESTS = ["sensing", "robotics", "embedded", "vision", "iot", "mechanics"]
TOOLS = ["soldering_iron", "multimeter", "3d_printer", "college_lab", "laptop_only"]
BUDGETS = [1000, 2000, 5000, 10000, 20000, 50000, None]


def rank(profile, limit=5):
    return picker.rank_factor_projects(profile, limit=limit)


def synthetic_profiles(count=300, seed=20261022):
    rng = random.Random(seed)
    profiles = []
    for _ in range(count):
        career = rng.sample(CAREERS, rng.randint(0, 2))
        interests = rng.sample(INTERESTS, rng.randint(0, 3))
        experience = rng.sample(EXPERIENCE, rng.randint(0, len(EXPERIENCE)))
        tools = rng.sample(TOOLS, rng.randint(0, 3))
        profile = {
            "career": career,
            "interests": interests,
            "experience": experience,
            "languages": rng.sample(["python", "c_cpp"], rng.randint(0, 2)),
            "tools": tools,
            "budget_inr": rng.choice(BUDGETS),
        }
        if rng.random() < 0.35:
            profile["schedule"] = {
                "hours_per_week": rng.choice([3, 5, 8, 12, 20]),
                "deadline_weeks": rng.choice([4, 8, 12, 16, 24]),
            }
        profiles.append(profile)
    return profiles


def evaluate_expectations(personas):
    failures = []
    for persona in personas:
        results = rank(persona["profile"])
        keys = [key for key, _ in results]
        expect = persona["expect"]
        if "max_cost_inr" in expect and any(
            PROJECT_FACTOR_CATALOG[key]["cost_inr"] > expect["max_cost_inr"] for key in keys
        ):
            failures.append({"persona": persona["name"], "expectation": "max_cost_inr"})
        if "max_difficulty" in expect and any(
            PROJECT_FACTOR_CATALOG[key]["difficulty"] > expect["max_difficulty"] for key in keys
        ):
            failures.append({"persona": persona["name"], "expectation": "max_difficulty"})
        if "must_include_one_of" in expect and not set(expect["must_include_one_of"]) & set(keys):
            failures.append({"persona": persona["name"], "expectation": "must_include_one_of"})
        if "not_only_tags" in expect and keys and all(
            set(PROJECT_FACTOR_CATALOG[key]["required_skills"]) <= set(expect["not_only_tags"])
            for key in keys
        ):
            failures.append({"persona": persona["name"], "expectation": "not_only_tags"})
    return failures


def _jaccard(left, right):
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a | b else 1.0


def run():
    profiles = [persona["profile"] for persona in PERSONAS] + synthetic_profiles()
    candidate_appearances = set()
    distinct_counts, score_gaps, stability = [], [], []
    level_violations = 0
    all_equal = 0
    result_count = 0

    for profile in profiles:
        results = rank(profile)
        scores = [score for _, score in results]
        keys = [key for key, _ in results]
        candidate_appearances.update(keys)
        result_count += len(keys)
        distinct_counts.append(len(set(scores)))
        score_gaps.append(scores[0] - scores[-1] if len(scores) > 1 else 0)
        if len(scores) == 5 and len(set(scores)) == 1:
            all_equal += 1
        level = picker._student_level(profile)
        level_violations += sum(
            PROJECT_FACTOR_CATALOG[key]["difficulty"] > level + 1.5 for key in keys
        )

        budget = profile.get("budget_inr")
        if budget:
            lower = dict(profile, budget_inr=budget * 0.9)
            upper = dict(profile, budget_inr=budget * 1.1)
            low_keys = [key for key, _ in rank(lower)]
            high_keys = [key for key, _ in rank(upper)]
            stability.append(_jaccard(low_keys, high_keys))
        else:
            stability.append(1.0)

    deterministic = all(
        rank(profile) == rank(dict(profile)) for profile in profiles
    )
    persona_results = []
    for persona in PERSONAS:
        ranked = rank(persona["profile"])
        persona_results.append({
            "name": persona["name"],
            "results": [{"key": key, "score": score} for key, score in ranked],
        })
    return {
        "version": "v1",
        "persona_count": len(PERSONAS),
        "synthetic_profile_count": len(profiles) - len(PERSONAS),
        "candidate_count": len(RECOMMENDATION_PROJECT_KEYS),
        "coverage_percent": round(100 * len(candidate_appearances) / len(RECOMMENDATION_PROJECT_KEYS), 2),
        "never_appearing": sorted(RECOMMENDATION_PROJECT_KEYS - candidate_appearances),
        "mean_distinct_top5_scores": round(sum(distinct_counts) / len(distinct_counts), 3),
        "mean_top1_top5_gap": round(sum(score_gaps) / len(score_gaps), 3),
        "all_equal_top5_percent": round(100 * all_equal / len(profiles), 2),
        "budget_perturbation_mean_jaccard": round(sum(stability) / len(stability), 3),
        "level_violation_percent": round(100 * level_violations / result_count, 2) if result_count else 0.0,
        "deterministic": deterministic,
        "persona_expectation_failures": evaluate_expectations(PERSONAS),
        "persona_results": persona_results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["v1"], default="v1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run()
    output = args.output or BASELINES / f"{args.version}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("metric                             value")
    print("---------------------------------- ------")
    for key, value in report.items():
        if key in {"persona_results", "never_appearing", "persona_expectation_failures"}:
            continue
        print(f"{key:34} {value}")
    print(f"persona expectation failures: {len(report['persona_expectation_failures'])}")
    print(f"baseline: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
