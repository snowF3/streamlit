"""
탭 3: 넥스트 핫플 예측 — 5개 선행지표 기반 핫플 스코어
"""
import streamlit as st
import pandas as pd
import pydeck as pdk
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_geojson, load_region_master, load_population_agg,
    load_card_sales_agg, load_income_agg, load_realestate,
    load_ajd_new_install
)
from scoring import calc_hotplace_score
from charts import hotplace_score_bar
from chat_ui import render_chat_panel

st.set_page_config(page_title="넥스트 핫플", page_icon="🔥", layout="wide")
st.title("🔥 넥스트 핫플 예측")
st.markdown("5개 선행지표를 조합하여 **다음에 뜰 동네**를 예측합니다.")
st.caption("데이터 범위: 서울 중구 · 영등포구 · 서초구 (118개 법정동)")

# ── 데이터 로드 ──
try:
    geojson = load_geojson()
    region_master = load_region_master()
    pop_agg = load_population_agg()
    card_agg = load_card_sales_agg()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# ── 분석 기간 표시 ──
all_months_sorted = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique())
if len(all_months_sorted) >= 12:
    recent_start = all_months_sorted[-6]
    recent_end = all_months_sorted[-1]
    prev_start = all_months_sorted[-12]
    prev_end = all_months_sorted[-7]
    st.caption(
        f"증가율 산출 기간 — 최근 6개월: {str(recent_start)[:4]}.{str(recent_start)[4:6]}~{str(recent_end)[:4]}.{str(recent_end)[4:6]} "
        f"vs 이전 6개월: {str(prev_start)[:4]}.{str(prev_start)[4:6]}~{str(prev_end)[:4]}.{str(prev_end)[4:6]}"
    )
else:
    latest = all_months_sorted[-1]
    earliest = all_months_sorted[0]
    st.caption(
        f"분석 기간: {str(earliest)[:4]}.{str(earliest)[4:6]}~{str(latest)[:4]}.{str(latest)[4:6]} ({len(all_months_sorted)}개월)"
    )

try:
    realestate = load_realestate()
except Exception:
    realestate = pd.DataFrame()

try:
    install = load_ajd_new_install()
except Exception:
    install = pd.DataFrame()

# ── 가중치 슬라이더 ──
st.sidebar.header("가중치 조정")
w_visiting = st.sidebar.slider("방문인구 증가율", 0.0, 1.0, 0.25, 0.05)
w_cafe = st.sidebar.slider("카페·식음료 매출 증가율", 0.0, 1.0, 0.20, 0.05)
w_young = st.sidebar.slider("유동인구 증가율", 0.0, 1.0, 0.20, 0.05)
w_price = st.sidebar.slider("매매가 상승률", 0.0, 1.0, 0.20, 0.05)
w_install = st.sidebar.slider("신규설치 증가율", 0.0, 1.0, 0.15, 0.05)

total_w = w_visiting + w_cafe + w_young + w_price + w_install
if total_w > 0:
    weights = {
        "visiting": w_visiting / total_w,
        "cafe": w_cafe / total_w,
        "young": w_young / total_w,
        "price": w_price / total_w,
        "install": w_install / total_w,
    }
else:
    weights = {"visiting": 0.2, "cafe": 0.2, "young": 0.2, "price": 0.2, "install": 0.2}

# ── 데이터 있는 법정동만 ──
data_districts = set(pop_agg["DISTRICT_CODE"].unique())
region_with_data = region_master[region_master["district_code"].isin(data_districts)]

# GeoJSON도 필터
geojson = {
    "type": "FeatureCollection",
    "features": [
        f for f in geojson["features"]
        if f["properties"]["district_code"] in data_districts
    ]
}

# ── 스코어 계산 ──
scores = calc_hotplace_score(pop_agg, card_agg, realestate, install, region_with_data, weights)

# 이름 매핑
name_map = region_with_data.set_index("district_code").apply(
    lambda r: f"{r['city_kor']} {r['district_kor']}", axis=1
).to_dict()
scores["name"] = scores["DISTRICT_CODE"].map(name_map)

# ── 지도 + 차트 ──
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("🗺️ 핫플 스코어 히트맵")

    # GeoJSON에 스코어 + 색상 주입
    score_dict = scores.set_index("DISTRICT_CODE")["hotplace_score"].to_dict()
    name_dict2 = scores.set_index("DISTRICT_CODE")["name"].to_dict()
    vals = list(score_dict.values())
    min_v, max_v = min(vals) if vals else 0, max(vals) if vals else 1
    rng = max_v - min_v if max_v != min_v else 1

    for feature in geojson["features"]:
        dc = feature["properties"]["district_code"]
        val = score_dict.get(dc, 0)
        norm = (val - min_v) / rng
        r, g, b = 255, int(255*(1-norm*0.8)), int(255*(1-norm))
        feature["properties"]["fill_color"] = [r, g, b, int(160+norm*60)]
        feature["properties"]["hotplace_score"] = round(val, 1)
        feature["properties"]["display_name"] = name_dict2.get(dc, dc)

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        get_fill_color="properties.fill_color",
        get_line_color=[80, 80, 80, 100],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )
    view = pdk.ViewState(latitude=37.51, longitude=126.95, zoom=11.5, pitch=0)
    deck = pdk.Deck(
        layers=[layer], initial_view_state=view,
        tooltip={"text": "{properties.display_name}\n핫플 스코어: {properties.hotplace_score}"},
        map_provider="carto", map_style="light",
    )
    st.pydeck_chart(deck)

with col2:
    st.subheader("📊 Top 20 핫플 동네")
    st.plotly_chart(
        hotplace_score_bar(scores, top_n=20),
        use_container_width=True
    )

# ── 상세 테이블 ──
st.divider()
st.subheader("📋 전체 스코어 상세")

display_cols = ["name", "hotplace_score", "visiting_growth", "cafe_growth",
                "young_growth", "price_growth", "install_growth"]
display_names = {
    "name": "동네", "hotplace_score": "핫플 스코어",
    "visiting_growth": "방문인구 증가(%)", "cafe_growth": "카페매출 증가(%)",
    "young_growth": "유동인구 증가(%)", "price_growth": "매매가 상승(%)",
    "install_growth": "신규설치 증가(%)"
}

available_cols = [c for c in display_cols if c in scores.columns]
st.dataframe(
    scores[available_cols]
    .rename(columns=display_names)
    .sort_values("핫플 스코어", ascending=False)
    .reset_index(drop=True),
    use_container_width=True,
    height=400
)

# Build page context for chat panel
_top5 = scores.nlargest(5, "hotplace_score")[["name", "hotplace_score"]]
_top5_str = ", ".join(f"{r['name']}({r['hotplace_score']:.1f})" for _, r in _top5.iterrows())
page_context = f"넥스트 핫플 - 상위 5개: {_top5_str}"

render_chat_panel(current_tab="넥스트 핫플", selected_district=None, selected_month=None, page_context=page_context)
