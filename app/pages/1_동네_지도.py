"""
탭 1: 동네 지도 — 서울 법정동 pydeck 맵
데이터 범위: 중구, 영등포구, 서초구 (118개 법정동)
"""
import streamlit as st
import pydeck as pdk
import pandas as pd
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_geojson, load_region_master, load_population_agg,
    load_card_sales_agg, load_income_agg
)
from scoring import calc_hotplace_score, normalize_series, calc_purchasing_power
from chat_ui import render_chat_panel

st.set_page_config(page_title="동네 지도", page_icon="🗺️", layout="wide")
st.title("🗺️ 동네 지도")
st.caption("데이터 범위: 서울 중구 · 영등포구 · 서초구 (118개 법정동)")

# ── 데이터 로드 ──
try:
    geojson_full = load_geojson()
    region_master = load_region_master()
    pop_agg = load_population_agg()
    card_agg = load_card_sales_agg()
    income_agg = load_income_agg()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# ── 데이터가 있는 법정동만 필터 ──
data_districts = set(pop_agg["DISTRICT_CODE"].unique())
region_with_data = region_master[region_master["district_code"].isin(data_districts)].copy()

geojson = {
    "type": "FeatureCollection",
    "features": [
        f for f in geojson_full["features"]
        if f["properties"]["district_code"] in data_districts
    ]
}

st.sidebar.header("지표 선택")
metric = st.sidebar.selectbox("색상 기준", [
    "종합 핫플 스코어",
    "유동인구 (총합)",
    "카드매출 (총합)",
    "구매력 스코어",
    "방문인구 증가율",
])

# ── 기준 년월 선택 ──
all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
month_labels = [f"{str(m)[:4]}년 {str(m)[4:6]}월" for m in all_months]
selected_month_label = st.sidebar.selectbox("기준 년월", month_labels, index=0)
selected_month = all_months[month_labels.index(selected_month_label)]
st.caption(f"기준: {selected_month_label}")

# ── 지표 계산 ──
pop_latest = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == selected_month].copy()
card_latest = card_agg[card_agg["STANDARD_YEAR_MONTH"] == selected_month].copy()

district_metrics = region_with_data[["district_code", "city_kor", "district_kor"]].copy()
district_metrics["name"] = district_metrics["city_kor"] + " " + district_metrics["district_kor"]

pop_total = pop_latest.copy()
pop_total["total_pop"] = (pop_total["RESIDENTIAL_POPULATION"]
                          + pop_total["WORKING_POPULATION"]
                          + pop_total["VISITING_POPULATION"])
pop_merged = pop_total.set_index("DISTRICT_CODE")["total_pop"]

if "TOTAL_SALES" in card_latest.columns:
    card_merged = card_latest.set_index("DISTRICT_CODE")["TOTAL_SALES"]
else:
    sales_cols = [c for c in card_latest.columns if c.endswith("_SALES")]
    card_latest["TOTAL_SALES"] = card_latest[sales_cols].sum(axis=1)
    card_merged = card_latest.set_index("DISTRICT_CODE")["TOTAL_SALES"]

purchasing = calc_purchasing_power(income_agg)

try:
    from data_loader import load_realestate, load_ajd_new_install
    realestate = load_realestate()
    install = load_ajd_new_install()
except Exception:
    realestate = pd.DataFrame()
    install = pd.DataFrame()

hotplace_df = calc_hotplace_score(pop_agg, card_agg, realestate, install, region_with_data)

district_metrics = district_metrics.merge(
    hotplace_df[["DISTRICT_CODE", "hotplace_score", "visiting_growth"]],
    left_on="district_code", right_on="DISTRICT_CODE", how="left"
)
district_metrics["total_pop"] = district_metrics["district_code"].map(pop_merged)
district_metrics["total_sales"] = district_metrics["district_code"].map(card_merged)
district_metrics["purchasing_power"] = district_metrics["district_code"].map(purchasing)
district_metrics = district_metrics.fillna(0)

metric_col_map = {
    "종합 핫플 스코어": "hotplace_score",
    "유동인구 (총합)": "total_pop",
    "카드매출 (총합)": "total_sales",
    "구매력 스코어": "purchasing_power",
    "방문인구 증가율": "visiting_growth",
}
color_col = metric_col_map[metric]

# ── GeoJSON에 지표 주입 + 색상 계산 ──
district_dict = district_metrics.set_index("district_code")[color_col].to_dict()
name_dict = district_metrics.set_index("district_code")["name"].to_dict()

# 값 범위로 색상 매핑 (0~100 정규화 → 빨간 그라데이션)
vals = list(district_dict.values())
min_v, max_v = min(vals) if vals else 0, max(vals) if vals else 1
rng = max_v - min_v if max_v != min_v else 1

for feature in geojson["features"]:
    dc = feature["properties"]["district_code"]
    val = district_dict.get(dc, 0)
    norm = (val - min_v) / rng  # 0~1
    # YlOrRd 색상: 노란→주황→빨강
    r = int(255)
    g = int(255 * (1 - norm * 0.8))
    b = int(255 * (1 - norm))
    feature["properties"]["fill_color"] = [r, g, b, int(160 + norm * 60)]
    feature["properties"]["metric_value"] = round(float(val), 1)
    feature["properties"]["display_name"] = name_dict.get(dc, dc)

# ── Pydeck 지도 ──
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader(f"서울 법정동 — {metric}")

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        get_fill_color="properties.fill_color",
        get_line_color=[80, 80, 80, 100],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 0, 80],
    )

    view = pdk.ViewState(latitude=37.51, longitude=126.95, zoom=11.5, pitch=0)

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip={"text": "{properties.display_name}\n{properties.metric_value}"},
        map_provider="carto",
        map_style="light",
    )
    st.pydeck_chart(deck)

with col2:
    st.subheader("📊 Top 10")
    top10 = district_metrics.nlargest(10, color_col)[["name", color_col]].reset_index(drop=True)
    top10.index = top10.index + 1
    top10.columns = ["동네", metric]
    st.dataframe(top10, use_container_width=True)

    st.subheader("📉 Bottom 10")
    has_value = district_metrics[district_metrics[color_col] > 0]
    if not has_value.empty:
        bottom10 = has_value.nsmallest(10, color_col)[["name", color_col]].reset_index(drop=True)
        bottom10.index = bottom10.index + 1
        bottom10.columns = ["동네", metric]
        st.dataframe(bottom10, use_container_width=True)

# Build page context for chat panel
_top3 = district_metrics.nlargest(3, color_col)["name"].tolist()
_top3_names = ", ".join(_top3)
page_context = f"동네 지도 - 지표: {metric}, 기준: {selected_month_label}, 상위 동네: {_top3_names}"
render_chat_panel(current_tab="동네 지도", selected_district=None, selected_month=None, page_context=page_context)
