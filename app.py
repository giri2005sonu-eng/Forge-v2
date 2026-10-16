import os

import streamlit as st
from dotenv import load_dotenv

from ui import bom, recommendation, research_tools

load_dotenv()
st.set_page_config(page_title="FORGE", page_icon="🤖", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;700&family=DM+Sans:wght@400;500&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif} h1,h2,h3{font-family:Sora,sans-serif!important}
.stButton>button{border-radius:14px;padding:.6rem 1.3rem;border:0;background:linear-gradient(135deg,#0F8F9A,#3CC4CF);color:#fff;font-weight:500;
 box-shadow:0 4px 14px rgba(60,196,207,.3);transition:transform .15s,box-shadow .15s}
.stButton>button:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(60,196,207,.4)}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:18px}
.block-container{padding-top:2rem;max-width:1100px} #MainMenu,footer{visibility:hidden}
.b{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700;color:#fff}
.PASS{background:#2FA36B}.FAIL{background:#D8505B}.UNKNOWN{background:#B08A1E}
</style>""", unsafe_allow_html=True)

S = st.session_state
for k, v in dict(live={}, res=None, log=[], stage="pick", A={}, pick=None, project="line_follower", budget=3500,
                 idea=None, examples=None, research={}, specs={}, agent={}, choice={}).items():
    S.setdefault(k, v)
tf_key, gem_key = bool(os.getenv("TINYFISH_API_KEY")), bool(os.getenv("GEMINI_API_KEY"))

st.title("FORGE")
st.caption("Robot BOM agent. TinyFish finds and reads live vendor pages, rules decide compatibility, every price carries its quote.")

if S.stage == "pick":
    recommendation.render_picker(S)
elif S.stage == "results":
    recommendation.render_results(S, tf_key)
else:
    build = bom.render(S, tf_key, gem_key)
    if build:
        research_tools.render(S, build, tf_key, gem_key)
