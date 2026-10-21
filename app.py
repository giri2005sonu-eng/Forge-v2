import os

import streamlit as st
from dotenv import load_dotenv

from ui import bom, competition, recommendation, research_tools

load_dotenv()
st.set_page_config(page_title="FORGE — Project Planning & Execution Copilot", page_icon="⚡", layout="wide")

# Inject Galaxy Black + Orange Theme from assets/forge.css
css_file = os.path.join(os.path.dirname(__file__), "assets", "forge.css")
if os.path.exists(css_file):
    with open(css_file, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

S = st.session_state
for k, v in dict(live={}, res=None, log=[], stage="pick", A={}, pick=None, project="line_follower", budget=3500,
                 idea=None, examples=None, custom=None, custom_error=None, research={}, specs={}, agent={}, choice={}, manual={}, resume=None, resume_n=0,
                 survey_step=0, survey_answers={}, career_research=None, survey_answer_count=0).items():
    S.setdefault(k, v)
tf_key, gem_key = bool(os.getenv("TINYFISH_API_KEY")), bool(os.getenv("GEMINI_API_KEY"))

# Brand Header: Glowing orange bolt, FORGE product title, tagline, and Copilot Active pill
st.markdown("""
<div class="fg-header-container">
  <div class="fg-header-brand">
    <div class="fg-header-logo">⚡</div>
    <div>
      <div class="fg-header-title">
        FORGE <span class="fg-header-subtitle">— Project Planning &amp; Execution Copilot</span>
      </div>
      <div class="fg-header-tagline">
        Autonomous Project Architecture &nbsp;·&nbsp; Live Market Sourcing &nbsp;·&nbsp; Hardware Verification &amp; Execution
      </div>
    </div>
  </div>
  <div>
    <span class="fg-copilot-badge">
      ⚡ COPILOT ACTIVE
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# Step Tracker (Discovery, Recommended, Competition, Planning)
stage_order = ["pick", "results", "competition", "bom"]
stage_labels = [
    ("pick", "Discovery"),
    ("results", "Recommended"),
    ("competition", "Competition"),
    ("bom", "Planning"),
]
curr_idx = stage_order.index(S.stage) if S.stage in stage_order else 0

pills_html = []
for idx, (s_key, s_label) in enumerate(stage_labels):
    if idx < curr_idx:
        status_cls = "completed"
        badge_sym = "✓"
    elif idx == curr_idx:
        status_cls = "active"
        badge_sym = str(idx + 1)
    else:
        status_cls = "pending"
        badge_sym = str(idx + 1)
    pills_html.append(
        f'<div class="fg-step-pill {status_cls}">'
        f'<span class="fg-step-num">{badge_sym}</span>'
        f'<span>{s_label}</span>'
        f'</div>'
    )

st.markdown(
    f'<div class="fg-tracker-wrap">'
    f'<div class="fg-tracker-line"></div>'
    f'{"".join(pills_html)}'
    f'</div>',
    unsafe_allow_html=True,
)


# 1. recommendation helper (skippable) -> 2. results -> optional competition shortlist -> 3. BOM agent
if S.stage == "pick":
    recommendation.render_picker(S, tf_key, gem_key)
elif S.stage == "results":
    recommendation.render_results(S, tf_key)
elif S.stage == "competition":
    competition.render(S)
else:
    build = bom.render(S, tf_key, gem_key)
    if build:
        research_tools.render(S, build, tf_key, gem_key)
