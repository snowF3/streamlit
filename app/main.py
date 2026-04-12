"""
동네 엑스레이 — 인사이트 피드 + AI 에이전트 + 디지털 트윈
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
/* 탭 스타일 */
[data-testid="stTab"] button { font-size: 14px !important; font-weight: 600 !important; }
</style>""", unsafe_allow_html=True)

# ── 사이드바: AI 에이전트 ──
from chat_ui import render_sidebar_chat
render_sidebar_chat()

# ── 상단 탭 (3개) ──
tab_feed, tab_agent, tab_twin = st.tabs([
    "인사이트 피드", "AI 에이전트", "디지털 트윈"
])

with tab_feed:
    try:
        from views.인사이트_피드 import render
        render()
    except Exception as e:
        st.error(f"인사이트 피드 로드 오류: {e}")

with tab_agent:
    st.markdown(
        '<div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">'
        '<span style="color:#6366F1; font-weight:700; font-size:16px;">✦</span>'
        '<span style="font-size:14px; font-weight:600; opacity:0.5;">'
        'AI에게 동네에 대해 무엇이든 물어보세요</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="font-size:13px; opacity:0.6; margin-bottom:16px;">'
        '"서초구 반포동 카페 매출 추이 알려줘", "중구에서 가장 유동인구 많은 동네는?", '
        '"영등포구 핫플 점수 비교해줘"</div>',
        unsafe_allow_html=True,
    )
    st.info("👈 왼쪽 사이드바에서 AI 에이전트와 대화하세요. 사이드바가 닫혀있다면 왼쪽 상단 '>' 버튼을 눌러주세요.")

with tab_twin:
    try:
        from views.디지털_트윈 import render
        render()
    except Exception as e:
        st.error(f"디지털 트윈 로드 오류: {e}")
