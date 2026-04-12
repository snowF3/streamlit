"""
탭 4: 디지털 트윈 — Phase 2 완전 구현
- Sprint 1: 클러스터링 색상 레이어 + 유사 동네
- Sprint 2: MiroFish Lite 페르소나 선택/행동 패턴
- Sprint 3: 시뮬레이션 고도화 (히스토리, 비교, gauge chart)

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
    load_population_demo, load_card_sales_agg, load_income_agg,
    load_income_detail, load_district_centroids,
    load_geojson, get_latest_year_month,
)
from scoring import calc_derived_metrics, normalize_series
from simulation import get_engine, INDUSTRY_PARAMS, SimulationResult, TIME_WEIGHTS
from clustering import (
    build_feature_matrix, run_clustering, classify_district_type,
    find_similar_districts, get_cluster_color, FEATURE_COLS,
)
from profile_generator import (
    generate_persona_seeds, generate_persona_text, get_persona_summary,
)
from charts import TIME_SLOT_KOR, spending_radar_chart
from chat_ui import render_sidebar_chat

st.title("🏙️ 디지털 트윈")
st.caption("서울 법정동 시간대별 도시 흐름 시뮬레이션 · 데이터 범위: 중구 · 영등포구 · 서초구")

# ══════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════
try:
    region_master = load_region_master()
    pop_agg = load_population_agg()
    pop_time = load_population_time()
    pop_demo = load_population_demo()
    card_agg = load_card_sales_agg()
    income_agg = load_income_agg()
    centroids = load_district_centroids()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# income_detail은 페르소나에서만 사용 — 실패해도 계속 진행
try:
    income_detail = load_income_detail()
except Exception:
    income_detail = pd.DataFrame()

# 사용 가능한 법정동
data_districts = set(pop_agg["DISTRICT_CODE"].unique())
centroids = centroids[centroids["district_code"].isin(data_districts)].copy()

# 기준 년월
all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
selected_month = all_months[0]

# 파생지표 계산 (캐싱)
@st.cache_data(ttl=3600)
def _calc_derived(_pop_time, _card_agg, _pop_agg, _income_agg, year_month):
    return calc_derived_metrics(_pop_time, _card_agg, _pop_agg, _income_agg, year_month)

derived = _calc_derived(pop_time, card_agg, pop_agg, income_agg, selected_month)

# 클러스터링 (캐싱)
@st.cache_data(ttl=3600)
def _compute_clusters(_pop_time, _card_agg, _pop_demo, _derived, _year_month):
    fm = build_feature_matrix(_derived, _card_agg, _pop_demo, _pop_time, _year_month)
    labels, model, scaler = run_clustering(fm)
    type_map = classify_district_type(fm, labels)
    return fm, labels, type_map

try:
    feature_matrix, cluster_labels, cluster_type_map = _compute_clusters(
        pop_time, card_agg, pop_demo, derived, selected_month
    )
except Exception:
    feature_matrix, cluster_labels, cluster_type_map = pd.DataFrame(), pd.Series(dtype=int), {}

# 이름 매핑 (전역)
name_map = centroids.set_index("district_code")["name"].to_dict()

# ══════════════════════════════════════
# [A] 컨트롤 바
# ══════════════════════════════════════
time_slots = list(TIME_SLOT_KOR.keys())
time_labels = list(TIME_SLOT_KOR.values())

ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])
with ctrl1:
    selected_time_label = st.select_slider(
        "시간대", options=time_labels, value="점심(12~15)")
    selected_time = time_slots[time_labels.index(selected_time_label)]
with ctrl2:
    weekday_label = st.radio("주중/주말", ["주중", "주말"], horizontal=True)
    weekday_code = "W" if weekday_label == "주중" else "H"
with ctrl3:
    metric_options = ["총유동인구", "방문인구", "1인당매출", "낮밤인구비", "클러스터"]
    selected_metric = st.selectbox("지표 선택", metric_options)

# ══════════════════════════════════════
# 시간대별 데이터 필터링 (캐싱)
# ══════════════════════════════════════
@st.cache_data(ttl=3600)
def _filter_pop_time(_pop_time, year_month, weekday_code, time_slot):
    pt = _pop_time[
        (_pop_time["STANDARD_YEAR_MONTH"] == year_month)
        & (_pop_time["WEEKDAY_WEEKEND"] == weekday_code)
        & (_pop_time["TIME_SLOT"] == time_slot)
    ].copy()
    pt["total_pop"] = (pt["RESIDENTIAL_POPULATION"]
                       + pt["WORKING_POPULATION"]
                       + pt["VISITING_POPULATION"])
    return pt.set_index("DISTRICT_CODE")

time_by_dc = _filter_pop_time(pop_time, selected_month, weekday_code, selected_time)

# 지표별 값 매핑
metric_col_map = {
    "총유동인구": "total_pop",
    "방문인구": "VISITING_POPULATION",
    "1인당매출": "sales_per_capita",
    "낮밤인구비": "day_night_ratio",
    "클러스터": "cluster",
}
sel_col = metric_col_map[selected_metric]

# 지표별 DataFrame 구성
column_df = centroids.copy()

if sel_col == "cluster":
    if not cluster_labels.empty:
        cl_df = cluster_labels.reset_index()
        cl_df.columns = ["DISTRICT_CODE", "cluster"]
        column_df = column_df.merge(cl_df, left_on="district_code", right_on="DISTRICT_CODE", how="left")
        column_df.drop(columns=["DISTRICT_CODE"], errors="ignore", inplace=True)
        column_df["cluster"] = column_df["cluster"].fillna(0).astype(int)
        column_df["fill_color"] = [get_cluster_color(c) + [200] for c in column_df["cluster"]]
        column_df["metric_value"] = column_df["cluster"].map(
            lambda c: cluster_type_map.get(c, f"유형 {c}")
        )
        column_df["norm"] = 0.5
    else:
        column_df["cluster"] = 0
        column_df["fill_color"] = [[128, 128, 128, 160]] * len(column_df)
        column_df["metric_value"] = "분류 불가"
        column_df["norm"] = 0.5
elif sel_col in ("total_pop", "VISITING_POPULATION"):
    column_df = column_df.merge(
        time_by_dc[[sel_col]].reset_index(),
        left_on="district_code", right_on="DISTRICT_CODE", how="left"
    ).drop(columns=["DISTRICT_CODE"], errors="ignore")
    column_df[sel_col] = column_df[sel_col].fillna(0)
else:
    column_df = column_df.merge(
        derived[[sel_col]].reset_index(),
        left_on="district_code", right_on="DISTRICT_CODE", how="left"
    ).drop(columns=["DISTRICT_CODE"], errors="ignore")
    column_df[sel_col] = column_df[sel_col].fillna(0)

if sel_col != "cluster":
    vals = column_df[sel_col]
    log_vals = np.log1p(vals.clip(lower=0))
    min_v, max_v = log_vals.min(), log_vals.max()
    rng = max_v - min_v if max_v != min_v else 1
    norm_vals = ((log_vals - min_v) / rng).fillna(0)

    column_df["metric_value"] = vals.round(1)
    column_df["norm"] = norm_vals

    column_df["fill_color"] = [
        [255, int(255 * (1 - n * 0.8)), int(255 * (1 - n)), int(160 + n * 60)]
        for n in norm_vals
    ]

# ══════════════════════════════════════
# [B] 메인 시각화: 3D 맵 + 퀵 프로파일
# ══════════════════════════════════════
map_col, profile_col = st.columns([3, 1])

with map_col:
    st.subheader(f"서울 법정동 — {selected_metric} ({selected_time_label}, {weekday_label})")

    geojson_data = load_geojson()
    if sel_col == "cluster":
        cl_color_map = {}
        for _, row in column_df.iterrows():
            cl_color_map[row["district_code"]] = {
                "fill_color": row["fill_color"],
                "metric_value": row["metric_value"],
            }
        for feat in geojson_data["features"]:
            dc = feat["properties"]["district_code"]
            info = cl_color_map.get(dc, {"fill_color": [128, 128, 128, 120], "metric_value": "미분류"})
            feat["properties"]["fill_color"] = info["fill_color"]
            feat["properties"]["metric_value"] = info["metric_value"]
    else:
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

    # 클러스터 범례
    if sel_col == "cluster" and cluster_type_map:
        legend_cols = st.columns(min(len(cluster_type_map), 4))
        for i, (cid, label) in enumerate(sorted(cluster_type_map.items())):
            color = get_cluster_color(cid)
            with legend_cols[i % len(legend_cols)]:
                st.markdown(
                    f'<span style="display:inline-block;width:12px;height:12px;'
                    f'background:rgb({color[0]},{color[1]},{color[2]});'
                    f'border-radius:2px;margin-right:4px;vertical-align:middle;"></span>'
                    f'<span style="font-size:12px;">{label}</span>',
                    unsafe_allow_html=True,
                )

with profile_col:
    st.subheader("📊 퀵 프로파일")
    if not column_df.empty and sel_col != "cluster":
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

        # 클러스터 태그 표시
        if top_code in cluster_labels.index:
            cid = cluster_labels[top_code]
            cl_label = cluster_type_map.get(cid, f"유형 {cid}")
            cl_color = get_cluster_color(cid)
            st.markdown(
                f'<span style="background:rgb({cl_color[0]},{cl_color[1]},{cl_color[2]});'
                f'color:white;padding:3px 10px;border-radius:12px;font-size:12px;">'
                f'{cl_label}</span>',
                unsafe_allow_html=True,
            )

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

    elif sel_col == "cluster" and not column_df.empty:
        # 클러스터 모드: 각 클러스터별 동네 수 표시
        st.markdown("**클러스터 분포**")
        if not cluster_labels.empty:
            cluster_counts = cluster_labels.value_counts().sort_index()
            for cid, cnt in cluster_counts.items():
                label = cluster_type_map.get(cid, f"유형 {cid}")
                color = get_cluster_color(cid)
                st.markdown(
                    f'<span style="display:inline-block;width:10px;height:10px;'
                    f'background:rgb({color[0]},{color[1]},{color[2]});'
                    f'border-radius:2px;margin-right:6px;vertical-align:middle;"></span>'
                    f'{label}: **{cnt}개** 동네',
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════
# [C] 분석 패널: 히트맵 + 주중/주말 비교
# ══════════════════════════════════════
st.divider()
anal_col1, anal_col2 = st.columns(2)

with anal_col1:
    st.subheader("🔥 시간대별 유동인구 히트맵")

    @st.cache_data(ttl=3600)
    def _heatmap_pivot(_pop_time, year_month, wk_code, slot_order):
        pt = _pop_time[
            (_pop_time["STANDARD_YEAR_MONTH"] == year_month)
            & (_pop_time["WEEKDAY_WEEKEND"] == wk_code)
        ].copy()
        pt["total"] = pt["RESIDENTIAL_POPULATION"] + pt["WORKING_POPULATION"] + pt["VISITING_POPULATION"]
        dc_total = pt.groupby("DISTRICT_CODE")["total"].sum().nlargest(20)
        top20 = dc_total.index.tolist()
        pv = pt[pt["DISTRICT_CODE"].isin(top20)].pivot_table(
            index="DISTRICT_CODE", columns="TIME_SLOT", values="total", aggfunc="sum"
        )
        ordered = [s for s in slot_order if s in pv.columns]
        return pv.reindex(columns=ordered).fillna(0).reindex(top20), top20

    pivot, top20_codes = _heatmap_pivot(pop_time, selected_month, weekday_code, tuple(time_slots))

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

    @st.cache_data(ttl=3600)
    def _weekday_weekend_compare(_pop_time, year_month):
        pt = _pop_time[_pop_time["STANDARD_YEAR_MONTH"] == year_month].copy()
        pt["total"] = pt["RESIDENTIAL_POPULATION"] + pt["WORKING_POPULATION"] + pt["VISITING_POPULATION"]
        return pt.groupby(["DISTRICT_CODE", "WEEKDAY_WEEKEND"])["total"].sum().unstack(fill_value=0)

    wk_vs_we = _weekday_weekend_compare(pop_time, selected_month)

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
tab_insight, tab_sim, tab_persona, tab_ai = st.tabs([
    "📈 현황 인사이트", "🧪 What-if 시뮬레이션",
    "👤 페르소나", "🤖 AI 예측 (Coming Soon)"
])

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

# ── 탭2: What-if 시뮬레이션 (Phase 2 고도화) ──
with tab_sim:
    st.markdown("**동네에 가게를 열면?** 유동인구 · 소득 · 경쟁 데이터 기반 예상 매출을 시뮬레이션합니다.")

    # 시뮬레이션 히스토리 초기화
    if "sim_history" not in st.session_state:
        st.session_state.sim_history = []

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
        engine = get_engine("statistical")
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

        # 히스토리에 저장 (최대 10개)
        st.session_state.sim_history.append({
            "district": sim_district_label,
            "district_code": sim_dc,
            "industry": sim_industry,
            "rent": sim_rent,
            "result": result,
        })
        if len(st.session_state.sim_history) > 10:
            st.session_state.sim_history = st.session_state.sim_history[-10:]

    # 최신 결과 표시
    if st.session_state.sim_history:
        latest = st.session_state.sim_history[-1]
        result = latest["result"]

        st.markdown("---")
        st.markdown(f"##### {latest['district']} · {latest['industry']} · 임대료 {latest['rent']:,}만원")

        r1, r2, r3 = st.columns(3)

        with r1:
            st.markdown("##### 💰 예상 월매출")
            # Gauge chart
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=result.monthly_revenue_mid,
                number={"suffix": "만원"},
                delta={"reference": latest["rent"], "relative": False, "valueformat": ","},
                gauge={
                    "axis": {"range": [0, max(result.monthly_revenue_high * 1.5, 1)]},
                    "bar": {"color": "#6366F1"},
                    "steps": [
                        {"range": [0, result.monthly_revenue_low], "color": "#fef3c7"},
                        {"range": [result.monthly_revenue_low, result.monthly_revenue_high], "color": "#d9f99d"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 3},
                        "thickness": 0.75,
                        "value": latest["rent"],
                    },
                },
                title={"text": "중간 추정"},
            ))
            fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=10))
            st.plotly_chart(fig_gauge, use_container_width=True)
            st.caption(f"범위: {result.monthly_revenue_low:,} ~ {result.monthly_revenue_high:,}만원")

        with r2:
            st.markdown("##### ⏰ 피크 시간대 & 고객층")
            if result.peak_hours:
                for i, ph in enumerate(result.peak_hours, 1):
                    st.markdown(f"{i}. {ph}")
            st.markdown(f"**주 고객층:** {result.main_customer}")
            if result.competition_index > 0:
                ci = result.competition_index
                ci_label = "낮음" if ci < 0.3 else ("보통" if ci < 0.6 else "높음")
                st.metric("경쟁 강도", f"{ci:.2f} ({ci_label})")

            # 시간대별 매출 비중 미니 차트
            if result.time_revenue_dist:
                td = result.time_revenue_dist
                slots_sorted = sorted(td.keys())
                fig_td = go.Figure(go.Bar(
                    x=[TIME_SLOT_KOR.get(s, s) for s in slots_sorted],
                    y=[td[s] for s in slots_sorted],
                    marker_color="#6366F1",
                ))
                fig_td.update_layout(
                    height=150, margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(tickfont=dict(size=8)),
                    yaxis=dict(title="만원", tickfont=dict(size=8)),
                )
                st.plotly_chart(fig_td, use_container_width=True)

        with r3:
            st.markdown("##### ⚠️ 리스크 요인")
            for risk in result.risk_factors:
                st.markdown(f"- {risk}")

        st.caption("⚠️ 통계 기반 추정치이며, 실제 매출과 차이가 있을 수 있습니다.")

        # ── 시뮬레이션 히스토리 비교 ──
        if len(st.session_state.sim_history) >= 2:
            st.markdown("---")
            st.markdown("##### 📊 시뮬레이션 비교")

            # 최근 2개 비교
            hist = st.session_state.sim_history
            compare_options = [f"{h['district']} · {h['industry']}" for h in hist]

            cmp_col1, cmp_col2 = st.columns(2)
            with cmp_col1:
                cmp_idx1 = st.selectbox("비교 A", range(len(hist)),
                                        format_func=lambda i: compare_options[i],
                                        index=len(hist) - 2, key="cmp_a")
            with cmp_col2:
                cmp_idx2 = st.selectbox("비교 B", range(len(hist)),
                                        format_func=lambda i: compare_options[i],
                                        index=len(hist) - 1, key="cmp_b")

            h1, h2 = hist[cmp_idx1], hist[cmp_idx2]
            r1, r2 = h1["result"], h2["result"]

            compare_data = pd.DataFrame({
                "지표": ["예상 월매출(만원)", "임대료(만원)", "수익(만원)", "경쟁 강도"],
                h1["district"] + " " + h1["industry"]: [
                    r1.monthly_revenue_mid, h1["rent"],
                    r1.monthly_revenue_mid - h1["rent"], r1.competition_index,
                ],
                h2["district"] + " " + h2["industry"]: [
                    r2.monthly_revenue_mid, h2["rent"],
                    r2.monthly_revenue_mid - h2["rent"], r2.competition_index,
                ],
            })
            st.dataframe(compare_data.set_index("지표"), use_container_width=True)

# ── 탭3: 페르소나 (Phase 2 Sprint 2) ──
with tab_persona:
    st.markdown("**법정동 대표 페르소나** — 성별×연령대×직업군 교차 분석으로 생성된 가상 거주자 프로파일")

    # 동네 선택
    persona_district_label = st.selectbox(
        "동네 선택", district_labels, key="persona_district"
    )
    persona_dc = district_codes[district_labels.index(persona_district_label)]

    if not income_detail.empty:
        personas = generate_persona_seeds(
            income_detail, income_agg, persona_dc, selected_month
        )
    else:
        personas = []

    if personas:
        # 페르소나 요약 테이블
        summary = get_persona_summary(personas)
        p_col1, p_col2 = st.columns([1, 1])

        with p_col1:
            st.markdown(f"**{persona_district_label}** — 총 {len(personas)}개 페르소나 유형")
            if not summary.empty:
                st.dataframe(summary, use_container_width=True)

        with p_col2:
            # 직업군별 분포 파이차트
            df_p = pd.DataFrame(personas)
            job_dist = df_p.groupby("job_type")["weight"].sum().sort_values(ascending=False)
            fig_job = go.Figure(go.Pie(
                labels=job_dist.index.tolist(),
                values=job_dist.values.tolist(),
                hole=0.4,
                textinfo="label+percent",
                textposition="outside",
            ))
            fig_job.update_layout(
                title="직업군 분포", height=300,
                margin=dict(l=20, r=20, t=40, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig_job, use_container_width=True)

        # 시간대별 페르소나 행동 패턴 (직업군별 시간대 활동 추정)
        st.markdown("---")
        st.markdown("##### 시간대별 행동 패턴 (추정)")

        # 직업군별 시간대 가중치 (근사 모델)
        JOB_TIME_PATTERN = {
            "대기업":     {"T06": 0.3, "T09": 1.0, "T12": 0.9, "T15": 1.0, "T18": 0.6, "T21": 0.2, "T24": 0.05},
            "일반직장":   {"T06": 0.3, "T09": 1.0, "T12": 0.9, "T15": 1.0, "T18": 0.5, "T21": 0.2, "T24": 0.05},
            "전문직":     {"T06": 0.2, "T09": 0.8, "T12": 0.9, "T15": 1.0, "T18": 0.7, "T21": 0.3, "T24": 0.1},
            "임원":       {"T06": 0.2, "T09": 0.9, "T12": 1.0, "T15": 0.9, "T18": 0.8, "T21": 0.4, "T24": 0.1},
            "자영업":     {"T06": 0.2, "T09": 0.7, "T12": 1.0, "T15": 1.0, "T18": 1.0, "T21": 0.6, "T24": 0.2},
            "전문자영":   {"T06": 0.2, "T09": 0.8, "T12": 0.9, "T15": 1.0, "T18": 0.8, "T21": 0.4, "T24": 0.1},
            "기타":       {"T06": 0.3, "T09": 0.5, "T12": 0.7, "T15": 0.6, "T18": 0.5, "T21": 0.3, "T24": 0.1},
        }

        pattern_data = {}
        for job, pattern in JOB_TIME_PATTERN.items():
            job_weight = job_dist.get(job, 0)
            if job_weight > 0:
                for slot, activity in pattern.items():
                    if slot not in pattern_data:
                        pattern_data[slot] = {}
                    pattern_data[slot][job] = activity * job_weight

        if pattern_data:
            fig_pattern = go.Figure()
            for job in JOB_TIME_PATTERN:
                if job in job_dist.index:
                    y_vals = [pattern_data.get(s, {}).get(job, 0) for s in time_slots]
                    fig_pattern.add_trace(go.Scatter(
                        x=[TIME_SLOT_KOR.get(s, s) for s in time_slots],
                        y=y_vals,
                        mode="lines+markers",
                        name=job,
                        stackgroup="one",
                    ))
            fig_pattern.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="시간대",
                yaxis_title="활동 지수 (가중)",
                legend=dict(orientation="h", y=-0.2),
            )
            st.plotly_chart(fig_pattern, use_container_width=True)

        # 개별 페르소나 샘플
        st.markdown("---")
        st.markdown("##### 대표 페르소나 샘플")
        top_personas = sorted(personas, key=lambda p: p["weight"], reverse=True)[:5]
        for p in top_personas:
            text = generate_persona_text(p, persona_district_label)
            st.markdown(f"- {text}")
    else:
        st.info("이 동네의 소득/직업 상세 데이터가 없어 페르소나를 생성할 수 없습니다.")

# ── 탭4: AI 예측 (Coming Soon) ──
with tab_ai:
    st.info(
        "🤖 **AI 에이전트 기반 예측 (Phase 3 예정)**\n\n"
        "MiroFish AI 에이전트가 수천 개의 가상 페르소나를 시뮬레이션하여 "
        "미래 상권 변화를 예측합니다.\n\n"
        "- 법정동별 AI 페르소나 생성 ✅ (Phase 2 완료)\n"
        "- 클러스터 기반 유사 동네 매칭 ✅ (Phase 2 완료)\n"
        "- 에이전트 간 상호작용 시뮬레이션 (Phase 3)\n"
        "- 상권 변화 예측 보고서 자동 생성 (Phase 3)"
    )

# ══════════════════════════════════════
# [E] AI 채팅
# ══════════════════════════════════════
render_sidebar_chat()
