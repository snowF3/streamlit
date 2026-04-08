"""
동네 엑스레이 — 앱 진입점
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(
    page_title="동네 엑스레이",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 페이지 정의 (pages/ 폴더) ──
page_feed = st.Page("pages/0_피드.py", title="피드", default=True)
page_map = st.Page("pages/1_동네_지도.py", title="지도")
page_profile = st.Page("pages/2_동네_프로파일.py", title="프로파일")
page_hot = st.Page("pages/3_넥스트_핫플.py", title="핫플")
page_twin = st.Page("pages/4_디지털_트윈.py", title="트윈")
page_compare = st.Page("pages/5_동네_비교.py", title="비교")

all_pages = [page_feed, page_map, page_profile, page_hot, page_twin, page_compare]

# ── 글로벌 스타일 ──
st.markdown("""<style>
.block-container { padding-top: 3.5rem !important; }
html, body, [data-testid="stAppViewContainer"] { font-size: 14px !important; }
[data-testid="stMetricValue"] { font-size: 20px !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; }
[data-testid="stMetricDelta"] { font-size: 11px !important; }
h1 { font-size: 22px !important; }
h2 { font-size: 18px !important; }
h3 { font-size: 15px !important; }
p, li, span, div { font-size: inherit; }

[data-testid="stHeader"] {
    background: transparent !important;
    pointer-events: none;
}
[data-testid="stHeader"] > * { pointer-events: auto; }

.header-row [data-testid="stPageLink-NavLink"] a {
    font-size: 14px !important; font-weight: 500 !important;
    color: inherit !important; opacity: 0.5;
    text-decoration: none !important; padding: 4px 0 !important;
}
.header-row [data-testid="stPageLink-NavLink"] a:hover { opacity: 1; }
.header-row [data-testid="stPageLink-NavLink"][aria-current="page"] a {
    opacity: 1; font-weight: 700 !important;
}
</style>""", unsafe_allow_html=True)

# ── 헤더 ──
st.markdown('<div class="header-row">', unsafe_allow_html=True)
cols = st.columns([1.5, 0.6, 0.6, 0.8, 0.6, 0.6, 0.6, 6])

with cols[0]:
    st.markdown(
        '<div style="font-size:15px; font-weight:800; letter-spacing:-0.5px; padding:4px 0;">'
        '🏙️ <span style="background:linear-gradient(135deg,#6366F1,#8B5CF6);'
        '-webkit-background-clip:text; -webkit-text-fill-color:transparent;">'
        '동네 엑스레이</span></div>',
        unsafe_allow_html=True,
    )

for i, page in enumerate(all_pages):
    with cols[i + 1]:
        st.page_link(page, label=page.title)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('<div style="border-bottom:1px solid rgba(128,128,128,0.1); margin-bottom:8px;"></div>', unsafe_allow_html=True)

# ── 네비게이션 ──
try:
    nav = st.navigation(all_pages, position="hidden")
except TypeError:
    nav = st.navigation(all_pages)

nav.run()
