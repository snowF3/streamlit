"""
동네 엑스레이 + 디지털 트윈 — 메인 앱 (뉴스 타임라인)
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(
    page_title="동네 엑스레이",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

from news_engine import generate_news_items, render_news_card, render_detail_panel
from chat_ui import get_chat_layout

# ── 뉴스 생성 ──
news_items = generate_news_items()

# ── 사이드바: 뉴스 타임라인 ──
with st.sidebar:
    st.markdown("## 📰 실시간 인사이트")
    st.caption(f"{len(news_items)}건의 데이터 변화 감지")

    # 필터
    all_tags = sorted(set(item["tag"] for item in news_items))
    selected_tags = st.multiselect("필터", all_tags, default=all_tags, key="news_filter")

    filtered_news = [item for item in news_items if item["tag"] in selected_tags]

    st.divider()

    # 뉴스 카드 렌더링
    if "selected_news" not in st.session_state:
        st.session_state.selected_news = 0

    for i, item in enumerate(filtered_news):
        card_html = render_news_card(item, i)
        st.markdown(card_html, unsafe_allow_html=True)
        if st.button(
            "상세 보기",
            key=f"news_btn_{i}",
            use_container_width=True,
            type="secondary" if st.session_state.selected_news != i else "primary",
        ):
            st.session_state.selected_news = i
            st.rerun()

    if not filtered_news:
        st.info("선택된 카테고리에 해당하는 뉴스가 없습니다.")

# ── 메인 영역: 선택된 뉴스 상세 ──
st.title("🏙️ 동네 엑스레이")

content_col = get_chat_layout(page_context="메인")

with content_col:

    if filtered_news:
        idx = min(st.session_state.selected_news, len(filtered_news) - 1)
        selected_item = filtered_news[idx]

        # 상단: 카드 요약
        severity_colors = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        sev_icon = severity_colors.get(selected_item.get("severity", "low"), "⚪")

        col_header, col_meta = st.columns([3, 1])
        with col_header:
            st.markdown(f"## {selected_item['icon']} {selected_item['title']}")
        with col_meta:
            st.markdown(f"**{selected_item['month']}** {sev_icon} {selected_item.get('severity', '').upper()}")

        # 상세 패널
        render_detail_panel(selected_item)

        # 하단: 관련 뉴스
        st.divider()
        st.markdown("### 📌 관련 인사이트")
        related = [item for item in filtered_news
                   if item.get("district_code") == selected_item.get("district_code")
                   and item != selected_item]

        if related:
            cols = st.columns(min(len(related), 3))
            for j, rel in enumerate(related[:3]):
                with cols[j]:
                    st.markdown(f"""
                    <div style="
                        border: 1px solid #333;
                        padding: 12px;
                        border-radius: 8px;
                        background: #1a1a1a;
                    ">
                        <div style="font-size:12px; color:{rel['tag_color']}; font-weight:600;">{rel['tag']}</div>
                        <div style="font-size:14px; font-weight:600; margin:4px 0;">{rel['icon']} {rel['title']}</div>
                        <div style="font-size:12px; color:#888;">{rel['summary']}</div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.caption("같은 지역의 다른 인사이트가 없습니다.")

    else:
        st.info("👈 왼쪽 사이드바에서 인사이트 뉴스를 선택하세요.")
        st.markdown("""
        ---
        **다른 분석 도구:**

        | 탭 | 기능 |
        |---|---|
        | **동네 지도** | 서울 법정동별 지표 코로플레스 맵 |
        | **동네 프로파일** | 선택한 동네의 소비·인구·부동산·소득 엑스레이 |
        | **넥스트 핫플** | 5개 선행지표 기반 핫플 예측 |
        | **디지털 트윈** | 합성 시민이 움직이는 살아있는 지도 + 시뮬레이션 |
        | **동네 비교** | 2~3개 동네 나란히 비교 |
        """)

