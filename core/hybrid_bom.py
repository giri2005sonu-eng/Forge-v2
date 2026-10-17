"""Hybrid planner: use what we already know before paying for Gemini.

  1. learned store   (ideas Gemini already planned once)      -> 0 Gemini calls
  2. 168-project dataset, near-identical name                 -> 0 Gemini calls
  3. otherwise ONE Gemini call (custom_bom.plan_components), and the answer is saved to the learned store.
Dropdown projects never come here: they read the dataset directly. TinyFish prices are fetched by the caller in every case."""
import os
from . import custom_bom, pipeline, project_store
from .data import PROJECTS


def gemini_cap():
    try:
        return max(0, int(os.getenv("FORGE_GEMINI_PLANS_PER_SESSION", "5")))
    except ValueError:
        return 5


def resolve(idea, budget=None, needs_bt=False, counter=None, skip_local=False):
    """Returns dict(plan, origin, gemini_calls, suggestions). plan is None only when suggestions are offered first.
    counter: {"n": int} shared per session so one visitor cannot spend unlimited Gemini calls. Raises ValueError with a user-readable message."""
    text = custom_bom._txt(idea, 300)
    if not text:
        raise ValueError("Type what you want to build first.")
    if not skip_local:
        hit = project_store.find_learned(text)
        if hit:
            return dict(plan=hit, origin="learned", gemini_calls=0, suggestions=[])
        local = project_store.match_dataset(text)       # exact catalog names beat loose keywords ("camera-based line follower" is not the plain line follower)
        if local["auto"]:
            pid = local["auto"]["key"].split(":", 1)[1]
            if local["auto"]["key"].startswith("general:") and pid in PROJECTS:   # one of the three rule-checked builds
                return dict(plan=None, origin="rule", project=pid, reason="Exact catalog match to a rule-checked build.", gemini_calls=0, suggestions=[])
            return dict(plan=local["auto"], origin="dataset", gemini_calls=0, suggestions=[])
        rule = pipeline._keyword_idea(text)   # free keyword rules for the three rule-checked builds
        if rule:
            return dict(plan=None, origin="rule", project=rule["project"], reason=rule["reason"], gemini_calls=0, suggestions=[])
        if local["suggestions"]:
            return dict(plan=None, origin=None, gemini_calls=0, suggestions=local["suggestions"])
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("Nothing in the catalog or in earlier plans matches this idea. Add GEMINI_API_KEY to plan new ideas (each is saved so it only costs one call).")
    counter = counter if counter is not None else {"n": 0}
    if counter["n"] >= gemini_cap():
        raise ValueError(f"This session has used its {gemini_cap()} Gemini plans. Pick a project from the catalog list, or try an idea you planned before.")
    counter["n"] += 1
    plan = custom_bom.plan_components(text, budget, needs_bt)     # raises ValueError (no key, quota, bad reply); nothing is saved then
    for p in plan["parts"]:
        p["source"] = "gemini"
    plan.update(origin="gemini")
    project_store.save_learned(text, plan, budget, needs_bt)
    return dict(plan=plan, origin="gemini", gemini_calls=1, suggestions=[])
