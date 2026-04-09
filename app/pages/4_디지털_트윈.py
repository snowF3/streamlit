"""
탭 4: 디지털 트윈 — 시간대별 도시 흐름 시각화 + What-if 시뮬레이션
데이터 범위: 중구, 영등포구, 서초구 (118개 법정동)
"""
import streamlit as st
import pydeck as pdk
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_region_master, load_population_agg, load_population_time,
    load_card_sales_agg, load_income_agg, load_district_centroids,
    load_geojson, get_latest_year_month,
)
from scoring import calc_derived_metrics, normalize_series
from simulation import StatisticalEngine, INDUSTRY_PARAMS, SimulationResult
from charts import TIME_SLOT_KOR
from chat_ui import render_chat_panel

st.set_page_config(page_title="디지털 트윈", page_icon="🏙️", layout="wide")
st.title("🏙️ 디지털 트윈")
st.caption("서울 법정동 시간대별 도시 흐름 시뮬레이션 · 데이터 범위: 중구 · 영등포구 · 서초구")

# ══════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════
try:
    region_master = load_region_master()
    pop_agg = load_population_agg()
    pop_time = load_population_time()
    card_agg = load_card_sales_agg()
    income_agg = load_income_agg()
    centroids = load_district_centroids()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# 사용 가능한 법정동
data_districts = set(pop_agg["DISTRICT_CODE"].unique())
centroids = centroids[centroids["district_code"].isin(data_districts)].copy()

# 기준 년월
all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
selected_month = all_months[0]

# 파생지표 계산
derived = calc_derived_metrics(pop_time, card_agg, pop_agg, income_agg, selected_month)

# ══════════════════════════════════════
# [A] 컨트롤 바
# ══════════════════════════════════════
time_slots = list(TIME_SLOT_KOR.keys())
time_labels = list(TIME_SLOT_KOR.values())

ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 1, 1, 1])
with ctrl1:
    selected_time_label = st.select_slider(
        "시간대", options=time_labels, value="점심(12~15)")
    selected_time = time_slots[time_labels.index(selected_time_label)]
with ctrl2:
    weekday_label = st.radio("주중/주말", ["주중", "주말"], horizontal=True)
    weekday_code = "W" if weekday_label == "주중" else "H"
with ctrl3:
    metric_options = ["총유동인구", "방문인구", "1인당매출", "낮밤인구비"]
    selected_metric = st.selectbox("지표 선택", metric_options)
with ctrl4:
    is_3d = st.checkbox("3D 보기", value=True)

# ══════════════════════════════════════
# 시간대별 데이터 필터링
# ══════════════════════════════════════
pt_filtered = pop_time[
    (pop_time["STANDARD_YEAR_MONTH"] == selected_month)
    & (pop_time["WEEKDAY_WEEKEND"] == weekday_code)
    & (pop_time["TIME_SLOT"] == selected_time)
].copy()
pt_filtered["total_pop"] = (pt_filtered["RESIDENTIAL_POPULATION"]
                            + pt_filtered["WORKING_POPULATION"]
                            + pt_filtered["VISITING_POPULATION"])
time_by_dc = pt_filtered.set_index("DISTRICT_CODE")

# 지표별 값 매핑
metric_col_map = {
    "총유동인구": "total_pop",
    "방문인구": "VISITING_POPULATION",
    "1인당매출": "sales_per_capita",
    "낮밤인구비": "day_night_ratio",
}
sel_col = metric_col_map[selected_metric]

# ColumnLayer용 DataFrame 구성
column_df = centroids.copy()

if sel_col in ("total_pop", "VISITING_POPULATION"):
    # 시간대별 데이터에서 가져옴
    column_df = column_df.merge(
        time_by_dc[[sel_col]].reset_index(),
        left_on="district_code", right_on="DISTRICT_CODE", how="left"
    ).drop(columns=["DISTRICT_CODE"], errors="ignore")
    column_df[sel_col] = column_df[sel_col].fillna(0)
else:
    # 파생지표에서 가져옴
    column_df = column_df.merge(
        derived[[sel_col]].reset_index(),
        left_on="district_code", right_on="DISTRICT_CODE", how="left"
    ).drop(columns=["DISTRICT_CODE"], errors="ignore")
    column_df[sel_col] = column_df[sel_col].fillna(0)

# 정규화 — 로그 스케일로 이상치 완화
vals = column_df[sel_col]
log_vals = np.log1p(vals.clip(lower=0))
min_v, max_v = log_vals.min(), log_vals.max()
rng = max_v - min_v if max_v != min_v else 1
norm_vals = ((log_vals - min_v) / rng).fillna(0)

column_df["elevation"] = (norm_vals * 3000).fillna(0)
column_df["metric_value"] = vals.round(1)
column_df["norm"] = norm_vals

# 색상 (YlOrRd)
colors = []
for n in norm_vals:
    r = 255
    g = int(255 * (1 - n * 0.8))
    b = int(255 * (1 - n))
    colors.append([r, g, b, int(160 + n * 60)])
column_df["fill_color"] = colors

# ══════════════════════════════════════
# [B] 메인 시각화: 3D 맵 + 퀵 프로파일
# ══════════════════════════════════════
map_col, profile_col = st.columns([3, 1])

with map_col:
    st.subheader(f"서울 법정동 — {selected_metric} ({selected_time_label}, {weekday_label})")

    if is_3d:
        # ── 3D: ColumnLayer ──
        layer = pdk.Layer(
            "ColumnLayer",
            data=column_df,
            get_position=["lon", "lat"],
            get_elevation="elevation",
            elevation_scale=30,
            get_fill_color="fill_color",
            radius=200,
            pickable=True,
            auto_highlight=True,
            extruded=True,
        )
        view = pdk.ViewState(
            latitude=37.51, longitude=126.95, zoom=11.5,
            pitch=45, bearing=-27,
        )
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip={"text": "{name}\n" + f"{selected_metric}: " + "{metric_value}"},
            map_provider="carto",
            map_style="light",
        )
    else:
        # ── 2D: GeoJsonLayer 코로플레스 (동 영역 전체 채색) ──
        import json
        geojson_data = load_geojson()
        # 각 feature에 metric 값 + 색상 주입
        norm_map = column_df.set_index("district_code")[["norm", "metric_value"]].to_dict("index")
        for feat in geojson_data["features"]:
            dc = feat["properties"]["district_code"]
            info = norm_map.get(dc, {"norm": 0, "metric_value": 0})
            n = info["norm"]
            feat["properties"]["metric_value"] = info["metric_value"]
            r, g, b = 255, int(255 * (1 - n * 0.8)), int(255 * (1 - n))
            a = int(120 + n * 100)
            feat["properties"]["fill_color"] = [r, g, b, a]

        layer = pdk.Layer(
            "GeoJsonLayer",
            data=geojson_data,
            get_fill_color="properties.fill_color",
            get_line_color=[80, 80, 80, 160],
            line_width_min_pixels=1,
            pickable=True,
            auto_highlight=True,
            stroked=True,
        )
        view = pdk.ViewState(
            latitude=37.51, longitude=126.95, zoom=11.5,
            pitch=0, bearing=0,
        )
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip={"text": "{name}\n" + f"{selected_metric}: " + "{metric_value}"},
            map_provider="carto",
            map_style="light",
        )
    st.pydeck_chart(deck)

with profile_col:
    st.subheader("📊 퀵 프로파일")
    # 상위 1위 동네 표시
    if not column_df.empty:
        top_dc = column_df.nlargest(1, sel_col).iloc[0]
        top_code = top_dc["district_code"]
        st.markdown(f"**{top_dc['name']}** (최고값)")

        if top_code in derived.index:
            dm = derived.loc[top_code]
            st.metric("총유동인구", f"{dm['total_pop']:,.0f}명")
            st.metric("1인당매출", f"{dm['sales_per_capita']:,.0f}원")
            st.metric("낮밤인구비", f"{dm['day_night_ratio']:.2f}")
            hhi_val = dm['consumption_hhi']
            hhi_label = "다양" if hhi_val < 0.05 else ("보통" if hhi_val < 0.15 else "편중")
            st.metric("소비집중도(HHI)", f"{hhi_val:.3f} ({hhi_label})")

        # 미니 시간대별 차트
        dc_time_all = pop_time[
            (pop_time["STANDARD_YEAR_MONTH"] == selected_month)
            & (pop_time["WEEKDAY_WEEKEND"] == weekday_code)
            & (pop_time["DISTRICT_CODE"] == top_code)
        ].copy()
        if not dc_time_all.empty:
            dc_time_all["total"] = (dc_time_all["RESIDENTIAL_POPULATION"]
                                    + dc_time_all["WORKING_POPULATION"]
                                    + dc_time_all["VISITING_POPULATION"])
            dc_chart = dc_time_all.set_index("TIME_SLOT").reindex(time_slots)
            dc_chart["시간대"] = [TIME_SLOT_KOR.get(t, t) for t in dc_chart.index]
            fig_mini = go.Figure()
            fig_mini.add_trace(go.Scatter(
                x=dc_chart["시간대"], y=dc_chart["RESIDENTIAL_POPULATION"],
                name="거주", fill="tozeroy", line=dict(width=1),
            ))
            fig_mini.add_trace(go.Scatter(
                x=dc_chart["시간대"], y=dc_chart["WORKING_POPULATION"],
                name="직장", fill="tonexty", line=dict(width=1),
            ))
            fig_mini.add_trace(go.Scatter(
                x=dc_chart["시간대"], y=dc_chart["VISITING_POPULATION"],
                name="방문", fill="tonexty", line=dict(width=1),
            ))
            fig_mini.update_layout(
                height=200, margin=dict(l=0, r=0, t=20, b=0),
                showlegend=True, legend=dict(orientation="h", y=-0.3),
                xaxis=dict(tickfont=dict(size=9)),
                yaxis=dict(tickfont=dict(size=9)),
            )
            st.plotly_chart(fig_mini, use_container_width=True)

# ══════════════════════════════════════
# [C] 분석 패널: 히트맵 + 주중/주말 비교
# ══════════════════════════════════════
st.divider()
anal_col1, anal_col2 = st.columns(2)

with anal_col1:
    st.subheader("🔥 시간대별 유동인구 히트맵")
    # 해당 월+주중/주말 전체 시간대 데이터
    pt_heatmap = pop_time[
        (pop_time["STANDARD_YEAR_MONTH"] == selected_month)
        & (pop_time["WEEKDAY_WEEKEND"] == weekday_code)
    ].copy()
    pt_heatmap["total"] = (pt_heatmap["RESIDENTIAL_POPULATION"]
                           + pt_heatmap["WORKING_POPULATION"]
                           + pt_heatmap["VISITING_POPULATION"])

    # Top 20 동네 (전체 시간대 합)
    dc_total = pt_heatmap.groupby("DISTRICT_CODE")["total"].sum().nlargest(20)
    top20_codes = dc_total.index.tolist()

    # 이름 매핑
    name_map = centroids.set_index("district_code")["name"].to_dict()

    pivot = pt_heatmap[pt_heatmap["DISTRICT_CODE"].isin(top20_codes)].pivot_table(
        index="DISTRICT_CODE", columns="TIME_SLOT", values="total", aggfunc="sum"
    )
    # 시간대 순서 정렬
    ordered_slots = [s for s in time_slots if s in pivot.columns]
    pivot = pivot.reindex(columns=ordered_slots).fillna(0)
    # Top 20 순서 유지
    pivot = pivot.reindex(top20_codes)

    pivot.index = [name_map.get(dc, dc) for dc in pivot.index]
    pivot.columns = [TIME_SLOT_KOR.get(s, s) for s in pivot.columns]

    fig_heat = px.imshow(
        pivot, aspect="auto",
        color_continuous_scale="YlOrRd",
        labels=dict(x="시간대", y="동네", color="유동인구"),
    )
    fig_heat.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig_heat, use_container_width=True)

with anal_col2:
    st.subheader("📊 주중 vs 주말 비교 (Top 10)")
    # 주중/주말 전체 시간대 합산
    pt_compare = pop_time[pop_time["STANDARD_YEAR_MONTH"] == selected_month].copy()
    pt_compare["total"] = (pt_compare["RESIDENTIAL_POPULATION"]
                           + pt_compare["WORKING_POPULATION"]
                           + pt_compare["VISITING_POPULATION"])
    wk_vs_we = pt_compare.groupby(["DISTRICT_CODE", "WEEKDAY_WEEKEND"])["total"].sum().unstack(fill_value=0)

    if "W" in wk_vs_we.columns and "H" in wk_vs_we.columns:
        wk_vs_we["합계"] = wk_vs_we["W"] + wk_vs_we["H"]
        top10_codes = wk_vs_we.nlargest(10, "합계").index.tolist()
        top10_data = wk_vs_we.loc[top10_codes].copy()
        top10_data["name"] = [name_map.get(dc, dc) for dc in top10_data.index]

        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            name="주중", x=top10_data["name"], y=top10_data["W"],
            marker_color="#6366F1",
        ))
        fig_comp.add_trace(go.Bar(
            name="주말", x=top10_data["name"], y=top10_data["H"],
            marker_color="#F59E0B",
        ))
        fig_comp.update_layout(
            barmode="group", height=450,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=1.05),
            xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
        )
        st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.info("주중/주말 비교 데이터가 부족합니다.")

# ══════════════════════════════════════
# [D] 하단 탭
# ══════════════════════════════════════
st.divider()
tab_insight, tab_sim, tab_ai = st.tabs(["📈 현황 인사이트", "🧪 What-if 시뮬레이션", "🤖 AI 예측 (Coming Soon)"])

# ── 탭1: 현황 인사이트 ──
with tab_insight:
    ins1, ins2, ins3 = st.columns(3)

    with ins1:
        st.markdown("**🏢 오피스가 (낮밤인구비 Top 5)**")
        if "day_night_ratio" in derived.columns:
            top5_dn = derived.nlargest(5, "day_night_ratio")[["day_night_ratio"]].copy()
            top5_dn.index = [name_map.get(dc, dc) for dc in top5_dn.index]
            top5_dn.columns = ["낮밤인구비"]
            st.dataframe(top5_dn, use_container_width=True)

    with ins2:
        st.markdown("**🛍️ 상업/관광 (방문비중 Top 5)**")
        if "visit_ratio" in derived.columns:
            top5_vr = derived.nlargest(5, "visit_ratio")[["visit_ratio"]].copy()
            top5_vr.index = [name_map.get(dc, dc) for dc in top5_vr.index]
            top5_vr["visit_ratio"] = (top5_vr["visit_ratio"] * 100).round(1)
            top5_vr.columns = ["방문비중(%)"]
            st.dataframe(top5_vr, use_container_width=True)

    with ins3:
        st.markdown("**🎯 소비특화 (HHI Top 5)**")
        if "consumption_hhi" in derived.columns:
            top5_hhi = derived.nlargest(5, "consumption_hhi")[["consumption_hhi"]].copy()
            top5_hhi.index = [name_map.get(dc, dc) for dc in top5_hhi.index]
            top5_hhi.columns = ["소비집중도"]
            st.dataframe(top5_hhi, use_container_width=True)

# ── 탭2: What-if 시뮬레이션 ──
with tab_sim:
    st.markdown("**동네에 가게를 열면?** 유동인구 · 소득 · 경쟁 데이터 기반 예상 매출을 시뮬레이션합니다.")

    # 동네 리스트 구성
    district_list = centroids[["district_code", "name"]].sort_values("name")
    district_labels = district_list["name"].tolist()
    district_codes = district_list["district_code"].tolist()

    with st.form("sim_form"):
        sf1, sf2, sf3 = st.columns(3)
        with sf1:
            sim_district_label = st.selectbox("동네 선택", district_labels)
        with sf2:
            sim_industry = st.selectbox("업종", list(INDUSTRY_PARAMS.keys()))
        with sf3:
            sim_rent = st.slider("예상 월 임대료(만원)", 100, 2000, 500, step=50)
        submitted = st.form_submit_button("🚀 시뮬레이션 실행", use_container_width=True)

    if submitted:
        sim_dc = district_codes[district_labels.index(sim_district_label)]
        engine = StatisticalEngine()
        result = engine.simulate(
            district_code=sim_dc,
            industry=sim_industry,
            pop_time_df=pop_time,
            pop_agg_df=pop_agg,
            income_agg_df=income_agg,
            derived_metrics=derived,
            year_month=selected_month,
            rent=sim_rent,
        )

        st.markdown("---")
        r1, r2, r3 = st.columns(3)

        with r1:
            st.markdown("##### 💰 예상 월매출")
            st.metric("중간 추정", f"{result.monthly_revenue_mid:,}만원")
            st.caption(f"범위: {result.monthly_revenue_low:,} ~ {result.monthly_revenue_high:,}만원")
            if result.monthly_revenue_mid > 0:
                profit = result.monthly_revenue_mid - sim_rent
                delta_color = "normal" if profit > 0 else "inverse"
                st.metric("임대료 차감 후", f"{profit:,}만원",
                          delta=f"임대료 {sim_rent:,}만원", delta_color=delta_color)

        with r2:
            st.markdown("##### ⏰ 피크 시간대 & 고객층")
            if result.peak_hours:
                for i, ph in enumerate(result.peak_hours, 1):
                    st.markdown(f"{i}. {ph}")
            st.markdown(f"**주 고객층:** {result.main_customer}")

        with r3:
            st.markdown("##### ⚠️ 리스크 요인")
            for risk in result.risk_factors:
                st.markdown(f"- {risk}")

        st.caption("⚠️ 통계 기반 추정치이며, 실제 매출과 차이가 있을 수 있습니다.")

# ── 탭3: AI 예측 (Coming Soon) ──
with tab_ai:
    st.info(
        "🤖 **AI 에이전트 기반 예측 (Phase 2 예정)**\n\n"
        "MiroFish AI 에이전트가 수천 개의 가상 페르소나를 시뮬레이션하여 "
        "미래 상권 변화를 예측합니다.\n\n"
        "- 법정동별 AI 페르소나 생성\n"
        "- 에이전트 간 상호작용 시뮬레이션\n"
        "- 상권 변화 예측 보고서 자동 생성"
    )

# ══════════════════════════════════════
# [E] AI 채팅
# ══════════════════════════════════════
_top3 = column_df.nlargest(3, sel_col)["name"].tolist()
_top3_names = ", ".join(_top3)
month_label = f"{str(selected_month)[:4]}년 {str(selected_month)[4:6]}월"
page_context = (
    f"디지털 트윈 - 시간대: {selected_time_label}, "
    f"{weekday_label}, 지표: {selected_metric}, "
    f"기준: {month_label}, 상위 동네: {_top3_names}"
)
render_chat_panel(
    current_tab="디지털 트윈",
    selected_district=None,
    selected_month=selected_month,
    page_context=page_context,
)
