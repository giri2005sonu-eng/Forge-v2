import os

import streamlit as st
from dotenv import load_dotenv

from ui import bom, competition, recommendation, research_tools

load_dotenv()
st.set_page_config(page_title="FORGE", page_icon="⚡", layout="wide")
st.markdown("""<style>
/* ─────────────────────────────────────────────────────────────────────────
   FORGE  ·  Premium Production UI
   Palette:  Obsidian #0A0F1E  |  Midnight #0D1528  |  Ink #111827
             Electric Violet #7C3AED  |  Neon Cyan #06B6D4
             Emerald #10B981  |  Amber #F59E0B  |  Rose #F43F5E
             Slate Text #94A3B8  |  Cloud #E2E8F0
───────────────────────────────────────────────────────────────────────── */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  background: #0A0F1E;
  color: #E2E8F0;
}

/* ── App Shell ── */
.stApp {
  background: linear-gradient(135deg, #0A0F1E 0%, #0D1528 50%, #0A0F1E 100%);
  min-height: 100vh;
}

.block-container {
  padding: 2rem 2.5rem 4rem !important;
  max-width: 1160px !important;
}

#MainMenu, footer, header { visibility: hidden !important; }

/* ── Typography ── */
h1, h2, h3 {
  font-family: 'Inter', sans-serif !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em;
}

h1 { font-size: 2.4rem !important; }
h2 { font-size: 1.7rem !important; }
h3 { font-size: 1.2rem !important; }

/* Title gradient */
.stApp > div > div > div > div:first-child h1 {
  background: linear-gradient(135deg, #7C3AED, #06B6D4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* ── Buttons ── */
.stButton > button {
  border-radius: 10px !important;
  padding: 0.55rem 1.4rem !important;
  border: 1px solid rgba(124,58,237,0.4) !important;
  background: linear-gradient(135deg, #7C3AED 0%, #6D28D9 100%) !important;
  color: #fff !important;
  font-weight: 600 !important;
  font-size: 0.875rem !important;
  letter-spacing: 0.01em;
  box-shadow: 0 4px 16px rgba(124,58,237,0.3), 0 1px 0 rgba(255,255,255,0.06) inset !important;
  transition: all 0.2s cubic-bezier(0.4,0,0.2,1) !important;
  position: relative;
  overflow: hidden;
}

.stButton > button:hover {
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 24px rgba(124,58,237,0.45), 0 1px 0 rgba(255,255,255,0.1) inset !important;
  border-color: rgba(124,58,237,0.7) !important;
}

.stButton > button:active {
  transform: translateY(0px) !important;
  box-shadow: 0 2px 8px rgba(124,58,237,0.25) !important;
}

/* Primary button override */
button[kind="primary"] {
  background: linear-gradient(135deg, #06B6D4, #0891B2) !important;
  border-color: rgba(6,182,212,0.4) !important;
  box-shadow: 0 4px 16px rgba(6,182,212,0.3) !important;
}

button[kind="primary"]:hover {
  box-shadow: 0 8px 24px rgba(6,182,212,0.45) !important;
}

/* Disabled buttons */
.stButton > button:disabled {
  background: rgba(30,41,59,0.6) !important;
  border-color: rgba(51,65,85,0.5) !important;
  color: #475569 !important;
  box-shadow: none !important;
  transform: none !important;
}

/* ── Containers & Cards ── */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 16px !important;
  border: 1px solid rgba(124,58,237,0.15) !important;
  background: rgba(13,21,40,0.8) !important;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 24px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.04) inset !important;
  transition: border-color 0.2s ease !important;
}

[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color: rgba(124,58,237,0.3) !important;
}

/* ── Expanders ── */
.streamlit-expanderHeader {
  background: rgba(15,23,42,0.6) !important;
  border-radius: 12px !important;
  border: 1px solid rgba(51,65,85,0.4) !important;
  padding: 0.75rem 1rem !important;
  font-weight: 600 !important;
  color: #CBD5E1 !important;
  transition: all 0.15s ease !important;
}

.streamlit-expanderHeader:hover {
  border-color: rgba(124,58,237,0.4) !important;
  color: #E2E8F0 !important;
}

.streamlit-expanderContent {
  background: rgba(10,15,30,0.4) !important;
  border: 1px solid rgba(51,65,85,0.25) !important;
  border-top: none !important;
  border-radius: 0 0 12px 12px !important;
  padding: 1rem !important;
}

/* ── Inputs ── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
  background: rgba(15,23,42,0.8) !important;
  border: 1px solid rgba(51,65,85,0.6) !important;
  border-radius: 10px !important;
  color: #E2E8F0 !important;
  font-family: 'Inter', sans-serif !important;
  padding: 0.6rem 0.9rem !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
  border-color: #7C3AED !important;
  box-shadow: 0 0 0 3px rgba(124,58,237,0.15) !important;
  outline: none !important;
}

.stTextInput > div > div > input::placeholder { color: #475569 !important; }

/* ── Selectbox ── */
.stSelectbox > div > div {
  background: rgba(15,23,42,0.8) !important;
  border: 1px solid rgba(51,65,85,0.6) !important;
  border-radius: 10px !important;
  color: #E2E8F0 !important;
}

/* ── Toggle ── */
.stToggle > label > div {
  background: rgba(30,41,59,0.8) !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
  background: rgba(13,21,40,0.6) !important;
  border: 1px solid rgba(51,65,85,0.4) !important;
  border-radius: 12px !important;
  padding: 1rem 1.25rem !important;
  transition: border-color 0.2s ease !important;
}

[data-testid="stMetric"]:hover {
  border-color: rgba(124,58,237,0.35) !important;
}

[data-testid="stMetricLabel"] {
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
  color: #64748B !important;
}

[data-testid="stMetricValue"] {
  font-size: 1.5rem !important;
  font-weight: 700 !important;
  color: #E2E8F0 !important;
}

/* ── Status / Spinner ── */
[data-testid="stStatus"] {
  background: rgba(13,21,40,0.9) !important;
  border: 1px solid rgba(6,182,212,0.25) !important;
  border-radius: 12px !important;
}

/* ── Info / Warning / Error / Success ── */
[data-testid="stInfo"] {
  background: rgba(6,182,212,0.08) !important;
  border: 1px solid rgba(6,182,212,0.25) !important;
  border-radius: 10px !important;
  color: #BAE6FD !important;
}

[data-testid="stWarning"] {
  background: rgba(245,158,11,0.08) !important;
  border: 1px solid rgba(245,158,11,0.25) !important;
  border-radius: 10px !important;
  color: #FDE68A !important;
}

[data-testid="stError"] {
  background: rgba(244,63,94,0.08) !important;
  border: 1px solid rgba(244,63,94,0.25) !important;
  border-radius: 10px !important;
  color: #FECDD3 !important;
}

[data-testid="stSuccess"] {
  background: rgba(16,185,129,0.08) !important;
  border: 1px solid rgba(16,185,129,0.25) !important;
  border-radius: 10px !important;
  color: #A7F3D0 !important;
}

/* ── Caption / Labels ── */
.stCaption, [data-testid="stCaptionContainer"] {
  color: #64748B !important;
  font-size: 0.78rem !important;
}

label, .stWidgetLabel {
  color: #94A3B8 !important;
  font-weight: 500 !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.01em;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
  border: 1px solid rgba(51,65,85,0.4) !important;
  border-radius: 10px !important;
  overflow: hidden;
}

/* ── Divider ── */
hr {
  border: none !important;
  border-top: 1px solid rgba(51,65,85,0.4) !important;
  margin: 1.5rem 0 !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0A0F1E; }
::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.4); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(124,58,237,0.7); }

/* ── Badge System ── */
.b {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #fff;
}

.PASS  { background: linear-gradient(135deg,#059669,#10B981); box-shadow: 0 2px 8px rgba(16,185,129,0.3); }
.FAIL  { background: linear-gradient(135deg,#DC2626,#F43F5E); box-shadow: 0 2px 8px rgba(244,63,94,0.3); }
.UNKNOWN { background: linear-gradient(135deg,#B45309,#F59E0B); box-shadow: 0 2px 8px rgba(245,158,11,0.3); }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: rgba(10,15,30,0.95) !important;
  border-right: 1px solid rgba(51,65,85,0.35) !important;
}

/* ── Download Button ── */
[data-testid="stDownloadButton"] > button {
  background: linear-gradient(135deg, #1E3A5F, #1E40AF) !important;
  border-color: rgba(30,64,175,0.5) !important;
  box-shadow: 0 4px 16px rgba(30,64,175,0.25) !important;
}

/* ── Checkbox ── */
.stCheckbox > label > div:first-child {
  border-color: rgba(124,58,237,0.5) !important;
  border-radius: 4px !important;
}

/* ── Spinner ── */
.stSpinner > div { border-top-color: #7C3AED !important; }

/* ── Section headers ── */
.stMarkdown h4 {
  color: #94A3B8 !important;
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  margin-bottom: 0.75rem !important;
  padding-bottom: 0.5rem !important;
  border-bottom: 1px solid rgba(51,65,85,0.4) !important;
}

</style>""", unsafe_allow_html=True)

S = st.session_state
for k, v in dict(live={}, res=None, log=[], stage="pick", A={}, pick=None, project="line_follower", budget=3500,
                 idea=None, examples=None, custom=None, custom_error=None, research={}, specs={}, agent={}, choice={}, manual={}, resume=None, resume_n=0,
                 survey_step=0, survey_answers={}, career_research=None, survey_answer_count=0).items():
    S.setdefault(k, v)
tf_key, gem_key = bool(os.getenv("TINYFISH_API_KEY")), bool(os.getenv("GEMINI_API_KEY"))

st.markdown("""
<div style="display:flex;align-items:center;gap:16px;margin:0.5rem 0 1.5rem">
  <div style="background:linear-gradient(135deg,#7C3AED,#06B6D4);border-radius:14px;width:48px;height:48px;
              display:flex;align-items:center;justify-content:center;font-size:24px;
              box-shadow:0 4px 20px rgba(124,58,237,.4);flex-shrink:0">⚡</div>
  <div>
    <div style="background:linear-gradient(135deg,#7C3AED,#06B6D4);-webkit-background-clip:text;
                -webkit-text-fill-color:transparent;background-clip:text;
                font-size:2rem;font-weight:800;letter-spacing:-.03em;line-height:1.1;font-family:Inter,sans-serif">FORGE</div>
    <div style="color:#475569;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;font-weight:600;margin-top:2px">
      Robot BOM Intelligence &nbsp;·&nbsp; Live Pricing &nbsp;·&nbsp; Compatibility Engine</div>
  </div>
</div>
""", unsafe_allow_html=True)

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
