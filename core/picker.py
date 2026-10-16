"""Recommendation helper: plain scoring (no AI). Same answers (and same resume) always give the same result."""
import math
from . import resume as resume_mod
from .data import PROJECTS
from .recommendation_catalog import PROJECT_FACTOR_CATALOG, RECOMMENDATION_PROJECT_KEYS

QUESTIONS = [
 ("career", "What is your career direction?", {"Embedded systems": "embedded", "Robotics": "robotics", "ML / vision": "vision", "IoT": "iot", "Undecided": "undecided"}),
 ("experience", "Which have you done?", {"Read a sensor in code": "sensor_read", "Soldered": "soldering", "Used a motor driver": "motor_driver", "Built a breadboard circuit": "breadboard", "Used a Raspberry Pi": "raspberry_pi", "Trained a model": "trained_model"}),
 ("languages", "Which programming languages do you use?", {"C / C++": "c_cpp", "Python": "python", "None yet": "none"}),
 ("schedule", "How much time do you have?", {}),
 ("budget", "What is your project budget?", {}),
 ("tools", "What tools or lab access do you have?", {"Soldering iron": "soldering_iron", "Multimeter": "multimeter", "3D printer": "3d_printer", "College lab": "college_lab", "Laptop only": "laptop_only"}),
 ("hardware", "Which hardware do you already own?", {"Arduino": "arduino", "ESP32": "esp32", "Raspberry Pi": "raspberry_pi", "STM32": "stm32"}),
 ("goal", "What is your goal, and are you working solo or in a team?", {"Learn": "learn", "Portfolio": "portfolio", "Internship": "internship", "Competition": "competition", "Final-year project": "final_year"}),
 ("interests", "Pick up to three areas that interest you.", {"Sensors": "sensing", "Robotics": "robotics", "Embedded": "embedded", "ML / vision": "vision", "Wireless / IoT": "iot", "Mechanics": "mechanics"}),
]
AXES = [("Difficulty", "difficulty"), ("Electronics", "electronics"), ("Programming", "programming"),
    ("Fabrication", "fabrication"), ("Control math", "control_math"), ("AI / vision", "ai_vision"),
    ("Wireless / IoT", "wireless_iot"), ("Portfolio impact", "portfolio_impact")]
OPTION_MAP = {key: options for key, _, options in QUESTIONS if options}


def normalize_survey_answers(answers):
    """Convert visible survey labels into the compact, deterministic scorer profile."""
    profile = {}
    for key, options in OPTION_MAP.items():
        labels = answers.get(key, [])
        if isinstance(labels, str):
            labels = [labels]
        values = [options.get(label, label) for label in labels if label]
        if key == "languages" and "none" in values and len(values) > 1:
            values.remove("none")
        profile[key] = values
    schedule = answers.get("schedule", {})
    if not isinstance(schedule, dict):
        schedule = {}
    profile["schedule"] = dict(
        hours_per_week=schedule.get("hours_per_week", answers.get("hours_per_week")) or None,
        deadline_weeks=schedule.get("deadline_weeks", answers.get("deadline_weeks")) or None,
    )
    profile["budget_inr"] = answers.get("budget_inr") or None
    profile["dream_job"] = str(answers.get("dream_job", "")).strip()[:160]
    profile["team"] = answers.get("team", "")
    return profile

def _mx(A, k, d):
    v = [x for x in A.get(k, []) if isinstance(x, (int, float))]
    return max(v) if v else d

def _c(x): return max(0, min(100, x))

def effective(A, R=None):
    """Survey answers win. A resume only fills the questions the user left blank (skill level, interests)."""
    E = {k: list(v) for k, v in A.items()}
    if R:
        if not E.get("skill") and R.get("level"): E["skill"] = [R["level"]]
        if not E.get("int") and R.get("interests"): E["int"] = list(R["interests"])
    return E

def fits(key, A, R=None):
    A = effective(A, R)
    p, cap = PROJECTS[key], {1: 4, 2: 7, 3: 10}[_mx(A, "skill", 2)]
    T, B = _mx(A, "time", 14), _mx(A, "budget", 5000)
    want = 8 if "ai" in A.get("int", []) or "ai" in A.get("course", []) else 4
    f = dict(diff=100 - max(0, cap - p["diff"] - 3) * 5 if p["diff"] <= cap else 100 - (p["diff"] - cap) * 25,
             time=100 if p["days"] <= T else 100 - (p["days"] - T) / T * 100,
             cost=100 if p["cost"] <= B else 100 - (p["cost"] - B) / B * 100,
             ai=100 - abs(p["ai"] - want) * 12, parts=p["parts"] * 10, demo=p["demo"] * 10, hack=p["hack"] * 10)
    return {k: round(_c(v)) for k, v in f.items()}

def score(key, A, R=None):
    A = effective(A, R)
    f, win = fits(key, A), "win" in A.get("goal", [])
    w = dict(diff=1.5, time=1.5, cost=1.5, ai=1, parts=1, demo=1.6 if win else 1, hack=1.6 if win else 1)
    base = sum(f[k] * w[k] for k in f) / sum(w.values())
    it = set(A.get("int", [])) | {{"mech": "mechanics", "ai": "ai"}.get(c) for c in A.get("course", [])}
    x = _c(base + min(8, len(set(PROJECTS[key]["tags"]) & it) * 4))
    # The resume closes up to half of the remaining gap to 100, so strong matches stay ordered instead of all hitting the ceiling.
    return round(x + (100 - x) * 0.5 * resume_mod.affinity(key, R))

def rank(A, R=None):
    return sorted(((k, score(k, A, R)) for k in PROJECTS), key=lambda x: -x[1])


def _date_weeks(value):
    if not value:
        return None
    from datetime import date, datetime
    try:
        deadline = value if isinstance(value, date) else date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return max(0.0, (deadline - datetime.now().date()).days / 7)


def _available_weeks(schedule):
    if schedule.get("deadline_weeks"):
        return float(schedule["deadline_weeks"])
    return _date_weeks(schedule.get("finish_by"))


def _profile_skills(profile):
    skills = set(profile.get("experience", []))
    for item in (profile.get("resume") or {}).get("skills", []):
        if isinstance(item, dict) and item.get("confirmed"):
            skills.add(item.get("id", ""))
    return skills


def _student_level(profile):
    skills = _profile_skills(profile)
    languages = set(profile.get("languages", []))
    hardware = set(profile.get("hardware", []))
    signal = len(skills) * 0.45 + len(languages - {"none"}) * 0.3 + len(hardware) * 0.2
    return min(5.0, 1.0 + signal)


def _targets(profile):
    targets = dict(electronics=2.5, programming=2.5, fabrication=2.5,
                   control_math=2.5, ai_vision=2.5, wireless_iot=2.5, portfolio_impact=3.0)
    mappings = {
        "embedded": {"electronics": 5, "programming": 4},
        "robotics": {"electronics": 4, "fabrication": 4, "control_math": 4},
        "vision": {"ai_vision": 5, "programming": 4},
        "iot": {"wireless_iot": 5, "programming": 4},
        "sensing": {"electronics": 4, "control_math": 4},
        "mechanics": {"fabrication": 5, "control_math": 3},
    }
    focus = set(profile.get("career", [])) | set(profile.get("interests", []))
    research = profile.get("career_research") or {}
    focus |= set(research.get("signals", []))
    for item in (profile.get("resume") or {}).get("projects", []):
        if item.get("confirmed") and item.get("domain") in mappings:
            focus.add(item["domain"])
    for tag in focus:
        for factor, value in mappings.get(tag, {}).items():
            targets[factor] = max(targets[factor], value)
    if "portfolio" in profile.get("goal", []) or "internship" in profile.get("goal", []):
        targets["portfolio_impact"] = 5
    elif "learn" in profile.get("goal", []):
        targets["portfolio_impact"] = 3
    return targets, focus


def eligibility(project_key, profile):
    """Return hard-limit eligibility and reasons; missing limits remain unknown, not assumed."""
    project = PROJECT_FACTOR_CATALOG[project_key]
    reasons = []
    budget = profile.get("budget_inr")
    cost = project["cost_inr"]
    owned = set(profile.get("hardware", []))
    controller_credit = 450 if project_key != "bluetooth_car" and "arduino" in owned else 0
    controller_credit = max(controller_credit, 500 if project_key == "bluetooth_car" and "esp32" in owned else 0)
    cost -= min(cost, controller_credit)
    if budget is not None and cost > float(budget):
        reasons.append(f"Estimated cost ₹{cost:,} exceeds your ₹{float(budget):,.0f} budget")

    schedule = profile.get("schedule") or {}
    weeks = _available_weeks(schedule)
    hours_per_week = schedule.get("hours_per_week")
    if weeks is not None and hours_per_week:
        available = max(0.0, weeks * float(hours_per_week))
        if project["build_hours"] > available:
            reasons.append(f"Needs about {project['build_hours']} hours; your deadline allows about {available:.0f}")

    selected_tools = set(profile.get("tools", []))
    if "laptop_only" in selected_tools:
        available_tools = {"laptop"}
    elif selected_tools:
        available_tools = selected_tools | {"laptop"}
        if "college_lab" in selected_tools:
            available_tools |= {"soldering_iron", "multimeter", "3d_printer"}
    else:
        available_tools = None
    missing_tools = project["tools_required"] - available_tools if available_tools is not None else set()
    if missing_tools:
        names = {"soldering_iron": "soldering iron", "multimeter": "multimeter", "3d_printer": "3D printer", "laptop": "laptop"}
        reasons.append("Missing required tools: " + ", ".join(sorted(names.get(x, x) for x in missing_tools)))
    return dict(eligible=not reasons, reasons=reasons, estimated_cost_inr=cost, missing_tools=missing_tools)


def factor_breakdown(project_key, profile):
    """Fit scores for all 12 declared project factors, each normalized to 0-100."""
    project = PROJECT_FACTOR_CATALOG[project_key]
    targets, focus = _targets(profile)
    current_level = _student_level(profile)
    ideal_difficulty = min(5.0, current_level + 0.8)
    difficulty_delta = project["difficulty"] - ideal_difficulty
    difficulty_fit = 100 - (34 * difficulty_delta if difficulty_delta > 0 else 9 * abs(difficulty_delta))
    missing_skills = project["required_skills"] - _profile_skills(profile)
    if profile.get("experience") or (profile.get("resume") or {}).get("skills"):
        difficulty_fit = min(difficulty_fit, 100 - min(80, 18 * len(missing_skills)))
    result = {"difficulty": round(_c(difficulty_fit))}
    for factor in ("electronics", "programming", "fabrication", "control_math", "ai_vision", "wireless_iot", "portfolio_impact"):
        delta = abs(project[factor] - targets[factor])
        result[factor] = round(_c(100 - delta * 18))

    schedule = profile.get("schedule") or {}
    weeks = _available_weeks(schedule)
    available = weeks * float(schedule["hours_per_week"]) if weeks is not None and schedule.get("hours_per_week") else None
    result["build_hours"] = round(_c(100 - (project["build_hours"] / available * 25))) if available and available > 0 else 75
    budget = profile.get("budget_inr")
    cost = eligibility(project_key, profile)["estimated_cost_inr"]
    result["cost_inr"] = round(_c(100 - cost / float(budget) * 25)) if budget and float(budget) > 0 else 75
    result["parts_availability_india"] = project["parts_availability_india"] * 20
    result["tools_required"] = 100 if eligibility(project_key, profile)["eligible"] else 0
    return result


def _factor_weights(profile):
    weights = dict(difficulty=1.7, electronics=1.0, programming=1.0, fabrication=0.8,
                   control_math=0.9, ai_vision=0.8, wireless_iot=0.8, portfolio_impact=1.0,
                   build_hours=0.8, cost_inr=1.0, parts_availability_india=0.8, tools_required=0.7)
    _, focus = _targets(profile)
    boosts = {"embedded": {"electronics": 0.4, "programming": 0.3},
              "robotics": {"fabrication": 0.3, "control_math": 0.3},
              "vision": {"ai_vision": 0.5, "programming": 0.3},
              "iot": {"wireless_iot": 0.5, "programming": 0.2},
              "sensing": {"electronics": 0.3, "control_math": 0.2},
              "mechanics": {"fabrication": 0.4}}
    for tag in focus:
        for factor, value in boosts.get(tag, {}).items():
            weights[factor] += value
    if "competition" in profile.get("goal", []):
        weights["portfolio_impact"] += 0.6
    if profile.get("team") == "Team":
        weights["portfolio_impact"] += 0.25
    return weights


def factor_score(project_key, profile):
    fit = factor_breakdown(project_key, profile)
    weights = _factor_weights(profile)
    return round(sum(fit[key] * weights[key] for key in weights) / sum(weights.values()))


def rank_factor_projects(profile, limit=5):
    """Filter hard constraints, then deterministically rank and diversify by project domain."""
    candidates = [(key, factor_score(key, profile)) for key in RECOMMENDATION_PROJECT_KEYS
                  if eligibility(key, profile)["eligible"]]
    candidates.sort(key=lambda item: (-item[1], item[0]))
    selected, domain_counts = [], {}
    for item in candidates:
        domain = PROJECT_FACTOR_CATALOG[item[0]]["domain"]
        if domain_counts.get(domain, 0) >= 2:
            continue
        selected.append(item)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if len(selected) >= limit:
            break
    return selected

def chart_html(f):
    """Radial chart: one triangle per attribute pointing at its label; size and colour show how well it fits."""
    C, R0, K, n = 210, 34, 104, len(AXES)
    s = '<svg viewBox="0 0 420 420" width="100%">'
    for r in (.33, .66, 1): s += f'<circle cx="{C}" cy="{C}" r="{R0 + K * r}" fill="none" stroke="#27385A" stroke-dasharray="{"3 5" if r < 1 else "0"}"/>'
    for i, (name, k) in enumerate(AXES):
        v, ang = f[k], -math.pi / 2 + i * 2 * math.pi / n
        ux, uy = math.cos(ang), math.sin(ang); px, py = -uy, ux
        ln, hw = 14 + v / 100 * (K - 14), 9 + v / 100 * 9
        col = "#2FA36B" if v >= 70 else "#E0A030" if v >= 45 else "#D8505B"
        s += f'<line x1="{C}" y1="{C}" x2="{C + ux * (R0 + K + 6):.1f}" y2="{C + uy * (R0 + K + 6):.1f}" stroke="#27385A"/>'
        s += (f'<g transform="translate({C + ux * R0:.1f},{C + uy * R0:.1f})"><polygon class="t" style="animation-delay:{i * 70}ms" '
              f'points="{px * hw:.1f},{py * hw:.1f} {-px * hw:.1f},{-py * hw:.1f} {ux * ln:.1f},{uy * ln:.1f}" fill="{col}" fill-opacity=".88"/></g>')
        lx, ly = C + ux * (R0 + K + 22), C + uy * (R0 + K + 22)
        an = "start" if ux > .3 else "end" if ux < -.3 else "middle"
        s += (f'<text x="{lx:.1f}" y="{ly + (10 if uy > .3 else -2 if uy < -.3 else 4):.1f}" text-anchor="{an}" fill="#E6ECF5" font-size="12.5">{name}</text>'
              f'<text x="{lx:.1f}" y="{ly + (24 if uy > .3 else 12 if uy < -.3 else 18):.1f}" text-anchor="{an}" fill="#93A1BA" font-size="11.5">{v}% fit</text>')
    s += f'<circle cx="{C}" cy="{C}" r="26" fill="#12374A"/><text x="{C}" y="{C + 4}" text-anchor="middle" fill="#E6ECF5" font-weight="700" font-size="13">You</text></svg>'
    return ('<style>body{margin:0;font-family:sans-serif}.t{transform-origin:0 0;animation:g .7s cubic-bezier(.2,.8,.2,1) both}'
            '@keyframes g{from{transform:scale(0)}to{transform:scale(1)}}</style>' + s)
