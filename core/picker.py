"""Recommendation helper: plain scoring (no AI). Same answers always give the same result."""
import math
from .data import PROJECTS

QUESTIONS = [
 ("course", "What are you studying?", {"AI / ML": "ai", "CSE / IT": "sw", "ECE / EEE": "hw", "Mechanical": "mech", "Something else": "x"}),
 ("time", "How much time do you have to build?", {"1–2 days": 2, "About a week": 7, "2–4 weeks": 21, "More than a month": 45}),
 ("skill", "How comfortable are you with electronics?", {"Complete beginner": 1, "Have used Arduino": 2, "Comfortable": 3}),
 ("goal", "What do you want out of it?", {"Learn something": "learn", "Portfolio piece": "port", "Win a hackathon": "win", "Course credit": "credit"}),
 ("budget", "What is your budget?", {"Under ₹2,000": 2000, "₹2,000–4,000": 4000, "₹4,000–8,000": 8000, "Above ₹8,000": 12000}),
 ("int", "What interests you most?", {"Sensors": "sensors", "Wireless": "wireless", "AI / ML": "ai", "Mechanics": "mechanics"}),
]
AXES = [("Difficulty", "diff"), ("Time needed", "time"), ("Cost", "cost"), ("AI/ML depth", "ai"), ("Parts availability", "parts"), ("Demo impact", "demo"), ("Hackathon fit", "hack")]

def _mx(A, k, d):
    v = [x for x in A.get(k, []) if isinstance(x, (int, float))]
    return max(v) if v else d

def _c(x): return max(0, min(100, x))

def fits(key, A):
    p, cap = PROJECTS[key], {1: 4, 2: 7, 3: 10}[_mx(A, "skill", 2)]
    T, B = _mx(A, "time", 14), _mx(A, "budget", 5000)
    want = 8 if "ai" in A.get("int", []) or "ai" in A.get("course", []) else 4
    f = dict(diff=100 - max(0, cap - p["diff"] - 3) * 5 if p["diff"] <= cap else 100 - (p["diff"] - cap) * 25,
             time=100 if p["days"] <= T else 100 - (p["days"] - T) / T * 100,
             cost=100 if p["cost"] <= B else 100 - (p["cost"] - B) / B * 100,
             ai=100 - abs(p["ai"] - want) * 12, parts=p["parts"] * 10, demo=p["demo"] * 10, hack=p["hack"] * 10)
    return {k: round(_c(v)) for k, v in f.items()}

def score(key, A):
    f, win = fits(key, A), "win" in A.get("goal", [])
    w = dict(diff=1.5, time=1.5, cost=1.5, ai=1, parts=1, demo=1.6 if win else 1, hack=1.6 if win else 1)
    base = sum(f[k] * w[k] for k in f) / sum(w.values())
    it = set(A.get("int", [])) | {{"mech": "mechanics", "ai": "ai"}.get(c) for c in A.get("course", [])}
    return round(_c(base + min(8, len(set(PROJECTS[key]["tags"]) & it) * 4)))

def rank(A):
    return sorted(((k, score(k, A)) for k in PROJECTS), key=lambda x: -x[1])

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
