"""Portfolio checklist coverage and project redundancy estimates."""
from .recommender_config import (
    COVERAGE_REDUNDANCY_MULTIPLIER,
    COVERAGE_REDUNDANCY_PROJECT_COUNT,
    COVERAGE_REDUNDANCY_SIMILARITY,
    LOW_INFORMATION_NEUTRAL,
    RESUME_EVIDENCE_STRENGTH,
)
from .recommendation_catalog import PROJECT_FACTOR_CATALOG
from .role_checklists import ROLE_CHECKLISTS


def _jaccard(left, right):
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def coverage_gain(project_key, roles, done=(), user_skills=()):
    roles = set(roles) & set(ROLE_CHECKLISTS)
    done = set(done)
    user_skills = set(user_skills)
    project_skills = set(PROJECT_FACTOR_CATALOG[project_key].get("required_skills", set()))
    if not done and not user_skills:
        return LOW_INFORMATION_NEUTRAL, []
    if not roles:
        return LOW_INFORMATION_NEUTRAL, []

    weighted_gain, total_weight = 0.0, 0.0
    for role in sorted(roles):
        for item in ROLE_CHECKLISTS[role]:
            tags = set(item["tags"])
            weight = item["weight"]
            total_weight += weight
            completed = any(
                (PROJECT_FACTOR_CATALOG.get(done_key, {}).get("required_skills", set()) & tags)
                or done_key in item.get("project_ids", set())
                for done_key in done
            )
            resume_evidence = bool(user_skills & tags)
            strength = 1.0 if completed else RESUME_EVIDENCE_STRENGTH if resume_evidence else 0.0
            if project_skills & tags:
                weighted_gain += weight * (1 - strength)

    score = max(0.0, min(1.0, weighted_gain / total_weight)) if total_weight else LOW_INFORMATION_NEUTRAL
    similar_done = sum(
        _jaccard(project_skills, set(PROJECT_FACTOR_CATALOG.get(done_key, {}).get("required_skills", set())))
        >= COVERAGE_REDUNDANCY_SIMILARITY
        for done_key in done
    )
    flags = []
    if similar_done >= COVERAGE_REDUNDANCY_PROJECT_COUNT:
        score *= COVERAGE_REDUNDANCY_MULTIPLIER
        flags.append("similar_to_existing")
    return score, flags
