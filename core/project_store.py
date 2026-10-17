"""Local project knowledge. NO network and NO AI in this file.

  dataset  = core/project_data/project_boms.json  (component lists for all 168 catalog projects, authored by the team)
  learned  = a JSON file that grows: every idea Gemini plans is saved here once, so the same idea never costs a second Gemini call
             (memoisation: ask once, remember the answer). Path: env FORGE_LEARNED_PATH, default core/project_data/learned_projects.json.
Learned plans are sanitised again on load (the file is treated as untrusted) and are never marked as reviewed or verified."""
import datetime as dt, json, os, re, tempfile, threading
from functools import lru_cache
from pathlib import Path

from . import part_specs

DATA = Path(__file__).with_name("project_data")
DATASET = DATA / "project_boms.json"
MAX_LEARNED = 500
AUTO_SCORE, SUGGEST_SCORE = 0.75, 0.4      # name similarity: auto-use above the first, offer as "did you mean" above the second
STOP = set("a an the my our your and or for to of with using use from that this want need make build create design diy project simple small new how can i me it is in on by".split())
_LOCK = threading.Lock()


def learned_path():
    return Path(os.getenv("FORGE_LEARNED_PATH") or DATA / "learned_projects.json")


@lru_cache(maxsize=1)
def dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def options():
    """Dropdown rows for ALL catalog projects: general by domain, then competition by event. Sorted, stable."""
    rows = []
    for p in dataset()["projects"].values():
        group = ("Competition · " + (p["competition_event"] or p["domain"])) if p["project_source"] == "competition" else p["domain"].replace("_", " ").title()
        rows.append(dict(key=p["key"], label=p["label"], group=group, source=p["project_source"]))
    return sorted(rows, key=lambda r: (r["source"] != "general", r["group"], r["label"].casefold()))


def _stem(w):
    for suf in ("ing", "ers", "er", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def tokens(text):
    """Lower-case content words, lightly stemmed ('follower' / 'following' / 'follows' all become 'follow'). Digits are kept: '4 motor' != 'motor'."""
    return {_stem(w) if not w.isdigit() else w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if w not in STOP and (len(w) >= 3 or w.isdigit())}


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def idea_key(idea):
    return "|".join(sorted(tokens(idea)))


def _plan_from_project(p):
    parts = [dict(id=x["id"], role=x["role"], name=x["name"], qty=x["qty"], query=x["query"], seed_price=None, kind=None, specs=part_specs.specs_for(x.get("part")), why="",
                  note=x.get("note", ""), custom=True, source="dataset") for x in p["parts"]]
    return dict(label=p["label"], parts=parts, notes=list(p["notes"]), origin="dataset", key=p["key"], description=p["description"],
                safety=p["safety"], competition_event=p["competition_event"], constraints=p["constraints"], catalog_cost_inr=p["catalog_cost_inr"],
                software_only=p["software_only"], bom_status=p["bom_status"])


def key_for_id(project_id):
    """'line_follower' -> 'general:line_follower' (ids are unique across both CSVs today; the composite key keeps it safe if that changes)."""
    return next((k for k in dataset()["projects"] if k.split(":", 1)[1] == project_id), None)


def get_plan(key):
    p = dataset()["projects"].get(key)
    return _plan_from_project(p) if p else None


def match_dataset(idea):
    """Offline match of free text to the 168 catalog names. Returns dict(auto=plan-or-None, suggestions=[(key,label,score)]).
    Ideas that contain a number (e.g. '4 motor') never auto-match: quantities must not be silently dropped."""
    t = tokens(idea)
    if not t:
        return dict(auto=None, suggestions=[])
    scored = sorted(((_jaccard(t, tokens(p["label"])), p["key"], p["label"]) for p in dataset()["projects"].values()), reverse=True)
    top = [(k, lab, round(s, 2)) for s, k, lab in scored[:3] if s >= SUGGEST_SCORE]
    has_digit = any(w.isdigit() for w in t)
    clear_win = len(top) == 1 or (len(top) > 1 and top[0][2] - top[1][2] >= 0.15)   # a tie between two projects is a question, not an answer
    auto = get_plan(top[0][0]) if top and top[0][2] >= AUTO_SCORE and clear_win and not has_digit else None
    return dict(auto=auto, suggestions=top)


# ---------------------------------------------------------------- learned store
def _read():
    try:
        d = json.loads(learned_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("entries"), dict) else dict(entries={})
    except (OSError, ValueError):
        return dict(entries={})


def find_learned(idea):
    """Exact (word-order independent) or near-exact (>= 0.8) hit in the learned store. Number tokens must match exactly."""
    entries = _read()["entries"]
    k = idea_key(idea)
    t = tokens(idea)
    e = entries.get(k)
    if e is None:
        digits = {w for w in t if w.isdigit()}
        best = max(((_jaccard(t, set(x["key"].split("|"))), x) for x in entries.values()
                    if {w for w in x["key"].split("|") if w.isdigit()} == digits), key=lambda z: z[0], default=(0, None))
        e = best[1] if best[0] >= 0.8 else None
    if not e:
        return None
    from . import custom_bom  # sanitise again: the file could have been edited by hand
    plan = custom_bom.clean_plan(e["plan"], e["idea"])
    if not plan["parts"]:
        return None
    for p in plan["parts"]:
        p["source"] = "learned"
    plan.update(origin="learned", key="learned:" + e["key"], learned_on=e["created"], source_idea=e["idea"], planned_budget=e.get("budget"))
    return plan


def save_learned(idea, plan, budget=None, bluetooth=False):
    """Remember a Gemini plan. Atomic write; oldest entries are dropped beyond MAX_LEARNED. Returns the stored key."""
    k = idea_key(idea)
    if not k:
        return None
    entry = dict(key=k, idea=" ".join(str(idea).split())[:300], created=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 budget=budget, bluetooth=bool(bluetooth), reviewed=False, source="gemini",
                 plan=dict(project_label=plan["label"], check_notes=plan.get("notes", []),
                           components=[dict(name=p["name"], role=p["role"], qty=p["qty"], search_query=p["query"], why=p.get("why", ""), specs=p.get("specs", {})) for p in plan["parts"]]))
    with _LOCK:
        data = _read()
        data["entries"][k] = entry
        while len(data["entries"]) > MAX_LEARNED:
            data["entries"].pop(min(data["entries"], key=lambda x: data["entries"][x]["created"]))
        path = learned_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    return k


def learned_count():
    return len(_read()["entries"])
