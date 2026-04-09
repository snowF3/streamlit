"""
전체 분석 — 동네 지도 + 핫플 순위 (탭)
"""
import streamlit as st
import pydeck as pdk
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_geojson, load_region_master, load_population_agg,
    load_card_sales_agg, load_income_agg, load_hotplace_monthly,
)
from scoring import calc_hotplace_score, calc_purchasing_power
from charts import hotplace_score_bar
from chat_ui import render_chat_panel

# ── CSS ──
st.markdown("""<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 14px !important; }
[data-testid="stMetricValue"] { font-size: 20px !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; }
h2, h3 { font-size: 15px !important; }
</style>""", unsafe_allow_html=True)

# ── 데이터 로드 ──
try:
    geojson_full = load_geojson()
    region_master = load_region_master()
    pop_agg = load_population_agg()
    card_agg = load_card_sales_agg()
    income_agg = load_income_agg()
    hp = load_hotplace_monthly()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

data_districts = set(pop_agg["DISTRICT_CODE"].unique())
region_with_data = region_master[region_master["district_code"].isin(data_districts)].copy()

geojson = {
    "type": "FeatureCollection",
    "features": [f for f in geojson_full["features"] if f["properties"]["district_code"] in data_districts]
}

# ── 년월 선택 ──
all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
ym_labels = [f"{str(m)[:4]}년 {int(str(m)[4:6])}월" for m in all_months]

h1, h2 = st.columns([5, 2])
with h1:
    st.markdown('<span style="font-size:18px; font-weight:800;">전체 분석</span>', unsafe_allow_html=True)
with h2:
    sel_ym_label = st.selectbox("기준 년월", ym_labels, index=0, label_visibility="collapsed")
selected_month = all_months[ym_labels.index(sel_ym_label)]

# ── 탭 ──
tab_map, tab_hotplace = st.tabs(["지도", "넥스트 핫플"])

# ═══════════════════
# 탭 1: 동네 지도
# ═══════════════════
with tab_map:
    st.markdown(
        f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">'
        f'<span style="color:#6366F1; font-weight:700;">✦</span>'
        f'<span style="font-size:13px; opacity:0.5;">'
        f'118개 법정동의 지표를 한눈에</span></div>',
        unsafe_allow_html=True,
    )
    metric = st.selectbox("색상 기준", [
        "종합 핫플 스코어", "유동인구 (총합)", "카드매출 (총합)",
        "구매력 스코어", "방문인구 증가율",
    ], label_visibility="collapsed")

    pop_latest = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == selected_month].copy()
    card_latest = card_agg[card_agg["STANDARD_YEAR_MONTH"] == selected_month].copy()

    district_metrics = region_with_data[["district_code", "city_kor", "district_kor"]].copy()
    district_metrics["name"] = district_metrics["city_kor"] + " " + district_metrics["district_kor"]

    pop_latest["total_pop"] = pop_latest["RESIDENTIAL_POPULATION"] + pop_latest["WORKING_POPULATION"] + pop_latest["VISITING_POPULATION"]
    pop_merged = pop_latest.set_index("DISTRICT_CODE")["total_pop"]

    if "TOTAL_SALES" not in card_latest.columns:
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

    district_dict = district_metrics.set_index("district_code")[color_col].to_dict()
    name_dict = district_metrics.set_index("district_code")["name"].to_dict()
    vals = list(district_dict.values())
    min_v, max_v = min(vals) if vals else 0, max(vals) if vals else 1
    rng = max_v - min_v if max_v != min_v else 1

    for feature in geojson["features"]:
        dc = feature["properties"]["district_code"]
        val = district_dict.get(dc, 0)
        norm = (val - min_v) / rng
        r, g, b = 255, int(255*(1-norm*0.8)), int(255*(1-norm))
        feature["properties"]["fill_color"] = [r, g, b, int(160+norm*60)]
        feature["properties"]["metric_value"] = round(float(val), 1)
        feature["properties"]["display_name"] = name_dict.get(dc, dc)

    col_map, col_rank = st.columns([3, 1])
    with col_map:
        layer = pdk.Layer(
            "GeoJsonLayer", data=geojson,
            get_fill_color="properties.fill_color",
            get_line_color=[80, 80, 80, 100], line_width_min_pixels=1,
            pickable=True, auto_highlight=True, highlight_color=[255, 255, 0, 80],
        )
        view = pdk.ViewState(latitude=37.51, longitude=126.95, zoom=11.5, pitch=0)
        deck = pdk.Deck(
            layers=[layer], initial_view_state=view,
            tooltip={"text": "{properties.display_name}\n{properties.metric_value}"},
            map_provider="carto", map_style="light",
        )
        st.pydeck_chart(deck)
    with col_rank:
        st.markdown('<div style="font-size:13px; font-weight:700;">상위 10</div>', unsafe_allow_html=True)
        top10 = district_metrics.nlargest(10, color_col)[["name", color_col]].reset_index(drop=True)
        top10.index = top10.index + 1
        top10.columns = ["동네", metric]
        st.dataframe(top10, use_container_width=True, height=250)

        st.markdown('<div style="font-size:13px; font-weight:700; margin-top:8px;">하위 10</div>', unsafe_allow_html=True)
        has_val = district_metrics[district_metrics[color_col] > 0]
        if not has_val.empty:
            bot10 = has_val.nsmallest(10, color_col)[["name", color_col]].reset_index(drop=True)
            bot10.index = bot10.index + 1
            bot10.columns = ["동네", metric]
            st.dataframe(bot10, use_container_width=True, height=250)

# ═══════════════════
# 탭 2: 핫플 순위
# ═══════════════════
with tab_hotplace:
    st.markdown(
        '<div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">'
        '<span style="color:#6366F1; font-weight:700;">✦</span>'
        '<span style="font-size:13px; opacity:0.5;">'
        '5개 선행지표(방문인구·카페매출·유동인구·매매가·신규설치)를 종합하여 다음에 뜰 동네를 예측합니다</span></div>',
        unsafe_allow_html=True,
    )
    if not hp.empty:
        month_hp = hp[hp["STANDARD_YEAR_MONTH"] == selected_month].copy()
        if not month_hp.empty:
            month_hp["cum_score"] = month_hp["DISTRICT_CODE"].apply(
                lambda d: round(100 + hp[(hp["DISTRICT_CODE"] == d) & (hp["STANDARD_YEAR_MONTH"] <= selected_month)]["hotplace_score"].sum(), 1)
            )
            month_hp = month_hp.sort_values("cum_score", ascending=False).reset_index(drop=True)

            col_chart, col_table = st.columns([3, 2])
            with col_chart:
                st.markdown('<div style="font-size:13px; font-weight:700;">핫플 점수 순위</div>', unsafe_allow_html=True)
                import plotly.graph_objects as go
                top20 = month_hp.head(20)
                fig = go.Figure(go.Bar(
                    x=top20["cum_score"], y=top20["name"],
                    orientation="h", marker_color="#6366F1",
                    text=top20["cum_score"], textposition="outside",
                ))
                fig.update_layout(
                    height=500, margin=dict(l=10, r=10, t=10, b=10),
                    yaxis=dict(autorange="reversed"), xaxis_title="핫플 점수",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col_table:
                st.markdown('<div style="font-size:13px; font-weight:700;">전체 동네 상세</div>', unsafe_allow_html=True)
                display = month_hp[["name", "cum_score", "hotplace_score", "visiting_chg", "cafe_chg", "pop_chg"]].copy()
                display.columns = ["동네", "누적점수", "이번달", "방문인구%", "카페매출%", "유동인구%"]
                display.index = range(1, len(display) + 1)
                st.dataframe(display, use_container_width=True, height=500)
        else:
            st.info("해당 월 데이터가 없습니다.")
    else:
        st.info("핫플 점수 데이터가 없습니다.")

# ── 채팅 ──
page_context = f"전체 분석 - 기준: {sel_ym_label}"
render_chat_panel(current_tab="전체 분석", selected_district=None, selected_month=str(selected_month), page_context=page_context)
