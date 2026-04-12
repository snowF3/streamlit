"""
XR-AI(엑스레이) — AI 기반 상권 분석 & 출점 의사결정 플랫폼
타겟: 소상공인 · 프랜차이즈 출점 · 팝업 위치 기획
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(
    page_title="XR-AI | 상권 분석 플랫폼",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──
st.markdown("""<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 14px !important; }
[data-testid="stMetricValue"] { font-size: 20px !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; }
h2, h3 { font-size: 15px !important; }
</style>""", unsafe_allow_html=True)

# ── 사이드바: AI 에이전트 ──
from chat_ui import render_sidebar_chat
render_sidebar_chat()

# ── 상단 탭 (2탭) ──
tab_insight, tab_future = st.tabs([
    "인사이트", "미래 예측"
])

with tab_insight:
    try:
        from views.인사이트_피드 import render as render_feed
        render_feed()
    except Exception as e:
        st.error(f"인사이트 로드 오류: {e}")

with tab_future:
    try:
        from views.디지털_트윈 import render as render_twin
        render_twin()
    except Exception as e:
        st.error(f"미래 예측 로드 오류: {e}")
