"""
동네 엑스레이 — 상단 탭 네비게이션 + 사이드바 AI 에이전트
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(
    page_title="동네 엑스레이",
    page_icon="🏙️",
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

# ── 상단 탭 네비게이션 ──
tab_feed, tab_analysis, tab_profile, tab_twin, tab_compare = st.tabs([
    "🏠 인사이트", "📊 전체 분석", "🔍 동네 프로파일", "🌆 디지털 트윈", "⚖️ 동네 비교"
])

with tab_feed:
    try:
        from views.인사이트_피드 import render
        render()
    except Exception as e:
        st.error(f"인사이트 피드 로드 오류: {e}")

with tab_analysis:
    try:
        from views.전체_분석 import render
        render()
    except Exception as e:
        st.error(f"전체 분석 로드 오류: {e}")

with tab_profile:
    try:
        from views.동네_프로파일 import render
        render()
    except Exception as e:
        st.error(f"동네 프로파일 로드 오류: {e}")

with tab_twin:
    try:
        from views.디지털_트윈 import render
        render()
    except Exception as e:
        st.error(f"디지털 트윈 로드 오류: {e}")

with tab_compare:
    try:
        from views.동네_비교 import render
        render()
    except Exception as e:
        st.error(f"동네 비교 로드 오류: {e}")
