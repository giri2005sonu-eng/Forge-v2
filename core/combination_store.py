"""Hybrid persistent combination evaluator.
Evaluates the compatibility and feasibility of any combination of components.
1) Checks local learned_combinations.json first (dataset hit -> 0 Gemini calls).
2) If new combination -> calls Gemini for hardware compatibility assessment,
   validates the result, and writes dynamically to learned_combinations.json.
3) Subsequent evaluations of the same combination are read from data without calling Gemini.
"""
import datetime as dt, hashlib, json, os, pathlib, tempfile, threading
from . import compatibility_engine as ce, engineering_calculations as calc, pipeline

DATA = pathlib.Path(__file__).resolve().parent / "project_data"
STORE_PATH = DATA / "learned_combinations.json"
_LOCK = threading.RLock()
MAX_ENTRIES = 500

def _read():
    try:
        if STORE_PATH.exists():
            d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("combinations"), dict):
                return d
    except (OSError, ValueError):
        pass
    return {"combinations": {}}

def combo_key(parts):
    """Stable hash key representing a specific combination of components."""
    items = []
    if isinstance(parts, dict):
        parts_list = list(parts.values())
    elif isinstance(parts, list):
        parts_list = parts
    else:
        parts_list = []
    for p in parts_list:
        if not isinstance(p, dict) or p.get("none"): continue
        role = str(p.get("role", "")).strip().lower()
        name = str(p.get("name", "")).strip().lower()
        items.append(f"{role}:{name}")
    items.sort()
    raw = "|".join(items)
    return "combo_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

def get_combination(key):
    """Retrieve saved combination review if it exists in local dataset."""
    with _LOCK:
        data = _read()
        return data["combinations"].get(key)

def save_combination(key, review):
    """Dynamically write combination assessment to disk so no repeated Gemini calls are needed."""
    if not key or not review:
        return
    with _LOCK:
        data = _read()
        data["combinations"][key] = dict(
            review,
            updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        )
        # Cap store size
        while len(data["combinations"]) > MAX_ENTRIES:
            oldest = min(data["combinations"], key=lambda k: data["combinations"][k].get("updated", ""))
            data["combinations"].pop(oldest)
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=STORE_PATH.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, STORE_PATH)

def evaluate_combination_hybrid(parts, project_label="Build", budget=None, live=None, allow_gemini=True):
    """Hybrid evaluator:
    - Returns saved review from dataset if present (0 Gemini calls).
    - If new combination and Gemini is available: calls Gemini, saves to dataset dynamically, and returns.
    - Otherwise falls back to deterministic rule summary.
    """
    key = combo_key(parts)
    cached = get_combination(key)
    if cached:
        return dict(cached, source="dataset", cached=True)

    # 1. Deterministic rule evaluation first
    co = ce.check(parts)
    sm = ce.summary(co)
    fails = [c for c in co if c["status"] == "FAIL"]
    warns = [c for c in co if c["status"] == "WARN"]
    unknowns = [c for c in co if c["status"] == "UNKNOWN"]

    # If all rules pass cleanly with no unknowns, we already have a strong deterministic verdict
    if sm["ready"] and not unknowns and not warns:
        record = dict(
            status="compatible",
            state="PASS",
            summary="All electrical and logic compatibility rules verified.",
            notes=[c["explanation"] for c in co if c["status"] == "PASS"],
            source="rules",
            fails=0,
            warns=0
        )
        save_combination(key, record)
        return record

    # 2. Hybrid Gemini evaluation for new or incomplete combinations
    gemini_key = os.getenv("GEMINI_API_KEY")
    if allow_gemini and gemini_key and not pipeline.quota_off():
        try:
            from google.genai import types
            comp_lines = []
            parts_dict = parts if isinstance(parts, dict) else {p.get("role", "part"): p for p in parts}
            for role, p in parts_dict.items():
                if not isinstance(p, dict) or p.get("none"): continue
                sp = ", ".join(f"{k}={v}" for k, v in (p.get("specs") or {}).items())
                comp_lines.append(f"- {role.capitalize()}: {p.get('name')} ({sp})")
            prompt = (
                f"Engineering hardware compatibility assessment for: {project_label}.\n"
                "Evaluate whether these electronic and robotic components will physically and electrically work together safely:\n"
                + "\n".join(comp_lines) + "\n\n"
                "Check voltage supply matching, logic levels (3.3V vs 5V), driver current capacity, power source sufficiency.\n"
                'Reply JSON only with: {"status": "compatible"|"caution"|"incompatible", "summary": "1-2 sentences overall assessment", '
                '"notes": ["up to 3 concise technical points to verify or be careful of"]}'
            )
            raw = pipeline._generate(prompt, types.GenerateContentConfig(response_mime_type="application/json"), gemini_key).text
            parsed = json.loads(raw)
            if isinstance(parsed, list): parsed = parsed[0]
            status = parsed.get("status") if parsed.get("status") in ("compatible", "caution", "incompatible") else sm["state"]
            record = dict(
                status=status,
                state="PASS" if status == "compatible" else "WARN" if status == "caution" else "FAIL",
                summary=str(parsed.get("summary", "")).strip()[:240],
                notes=[str(n)[:180] for n in parsed.get("notes", []) if isinstance(n, str)][:4],
                source="gemini_learned",
                fails=len(fails),
                warns=len(warns)
            )
            save_combination(key, record)
            return record
        except Exception:
            pass

    # 3. Fallback when Gemini is unavailable
    record = dict(
        status=sm["state"],
        state="PASS" if sm["ready"] else "FAIL" if sm["fail"] else "WARN",
        summary=f"Rule check: {sm['passed']} pass, {sm['warn']} warnings, {sm['fail']} failures.",
        notes=[c["explanation"] for c in fails + warns],
        source="rules",
        fails=len(fails),
        warns=len(warns)
    )
    save_combination(key, record)
    return record
