"""Validated prerequisite graph and readiness helpers for project recommendations."""
from collections import defaultdict

from .recommendation_catalog import PROJECT_FACTOR_CATALOG
from .recommender_config import MAX_PREREQUISITE_CHAIN


class PrerequisiteGraph:
    def __init__(self, factors):
        self.factors = factors
        self.edges = {
            key: set(project.get("prerequisites", set()))
            for key, project in factors.items()
        }
        missing = {
            prerequisite
            for prerequisites in self.edges.values()
            for prerequisite in prerequisites
            if prerequisite not in self.edges
        }
        if missing:
            raise ValueError(f"Unknown prerequisite project IDs: {sorted(missing)}")
        self._depths = {}
        self._validate_and_measure_depths()
        unlock_map = defaultdict(set)
        for project, prerequisites in self.edges.items():
            for prerequisite in prerequisites:
                unlock_map[prerequisite].add(project)
        self._unlocks = {key: tuple(sorted(value)) for key, value in unlock_map.items()}

    def _validate_and_measure_depths(self):
        visiting = set()

        def measure(key):
            if key in visiting:
                raise ValueError(f"Prerequisite graph contains a cycle at {key}")
            if key in self._depths:
                return self._depths[key]
            visiting.add(key)
            depth = 0
            if self.edges[key]:
                depth = 1 + max(measure(prereq) for prereq in self.edges[key])
            visiting.remove(key)
            self._depths[key] = depth
            return depth

        for key in self.edges:
            measure(key)

    def skill_coverage(self, key, user_skills):
        required = set(self.factors[key].get("required_skills", set()))
        return len(required & set(user_skills)) / len(required) if required else 0.0

    def readiness(self, key, done=(), user_skills=()):
        prerequisites = self.edges[key]
        if not prerequisites:
            return 1.0
        values = [
            1.0 if prerequisite in done else min(
                0.6, 0.6 * self.skill_coverage(prerequisite, user_skills)
            )
            for prerequisite in prerequisites
        ]
        return sum(values) / len(values)

    def unmet_chain(self, key, done=(), max_len=MAX_PREREQUISITE_CHAIN):
        done = set(done)
        queue = [(prerequisite, 1) for prerequisite in sorted(self.edges[key])]
        distance = {}
        while queue:
            project, depth = queue.pop(0)
            if project in done or project in distance:
                continue
            distance[project] = depth
            queue.extend(
                (prerequisite, depth + 1)
                for prerequisite in sorted(self.edges[project])
            )
        ordered = sorted(distance, key=lambda project: (distance[project], project))
        return ordered[:max_len]

    def next_step(self, key, done=(), user_skills=()):
        for project in self.unmet_chain(key, done):
            if self.readiness(project, done, user_skills) >= 0.6:
                return project
        return None

    def unlocks(self, key):
        return list(self._unlocks.get(key, ()))


GRAPH = PrerequisiteGraph(PROJECT_FACTOR_CATALOG)


def readiness(key, done=(), user_skills=()):
    return GRAPH.readiness(key, done, user_skills)


def unmet_chain(key, done=(), max_len=MAX_PREREQUISITE_CHAIN):
    return GRAPH.unmet_chain(key, done, max_len)


def next_step(key, done=(), user_skills=()):
    return GRAPH.next_step(key, done, user_skills)


def unlocks(key):
    return GRAPH.unlocks(key)
