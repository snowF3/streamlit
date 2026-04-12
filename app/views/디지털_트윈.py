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
    generate_all_profiles, generate_persona_seeds,
    generate_persona_text, get_persona_summary,
)
from charts import TIME_SLOT_KOR, spending_radar_chart
try:
    from mirofish import run_prediction, generate_report
    MIROFISH_AVAILABLE = True
except ImportError:
    MIROFISH_AVAILABLE = False


def render():

    st.markdown('<span style="font-size:18px; font-weight:800;">🔮 미래 예측</span>', unsafe_allow_html=True)
    st.caption("상권 시뮬레이션 · AI 예측 · 페르소나 분석 · 데이터 범위: 중구 · 영등포구 · 서초구")

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
    except Exception as e:
        st.caption(f"ℹ️ 소득 상세 데이터 미사용: {e}")
        income_detail = pd.DataFrame()

    # 사용 가능한 법정동
    data_districts = set(pop_agg["DISTRICT_CODE"].unique())
    centroids = centroids[centroids["district_code"].isin(data_districts)].copy()

    # 기준 년월 (컨트롤 바에서 선택, 여기서는 목록만 준비)
    all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)

    # 파생지표 계산 함수 (캐싱) — 컨트롤 바에서 기준 년월 선택 후 호출
    @st.cache_data(ttl=3600)
    def _calc_derived(_pop_time, _card_agg, _pop_agg, _income_agg, year_month):
        return calc_derived_metrics(_pop_time, _card_agg, _pop_agg, _income_agg, year_month)

    # ── 3개월 전망 카드 (제목 + ❓ 가이드 통합) ──
    st.markdown("""
    <style>
    .forecast-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .forecast-header h3 { margin: 0; padding: 0; font-size: 1.2em; }
    .score-help-wrap { position: relative; display: inline-block; }
    .score-help-btn {
        font-size: 14px; cursor: help; opacity: 0.4;
        transition: opacity 0.2s;
    }
    .score-help-btn:hover { opacity: 1; }
    .score-help-popup {
        visibility: hidden; opacity: 0;
        position: absolute; left: 0; top: 100%; margin-top: 6px; z-index: 9999;
        width: 420px; padding: 16px 18px;
        background: white; border: 1px solid #e0e0e0; border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        font-size: 12px; line-height: 1.7; color: #333;
        transition: opacity 0.2s, visibility 0.2s;
    }
    .score-help-wrap:hover .score-help-popup { visibility: visible; opacity: 1; }
    .score-help-popup h4 { font-size: 13px; font-weight: 700; margin: 0 0 8px; color: #333; }
    .score-help-popup .formula {
        background: #f8f7ff; border: 1px solid #e8e6ff; border-radius: 6px;
        padding: 6px 10px; font-family: monospace; font-size: 11px; color: #6366F1;
        margin-bottom: 10px;
    }
    .score-help-popup table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
    .score-help-popup th {
        text-align: left; font-size: 11px; font-weight: 600; color: #666;
        border-bottom: 1px solid #eee; padding: 4px 6px;
    }
    .score-help-popup td { font-size: 11px; padding: 4px 6px; border-bottom: 1px solid #f5f5f5; }
    .score-help-popup .warn {
        background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px;
        padding: 6px 10px; font-size: 11px; color: #92400e; margin-top: 8px;
    }
    </style>
    <div class="forecast-header">
        <h3>🔮 3개월 전망</h3>
        <div class="score-help-wrap">
            <span class="score-help-btn">❓</span>
            <div class="score-help-popup">
                <h4>3개월 전망 점수 산정</h4>
                <div class="formula">전망 점수 = 방문인구 변화율 × 60% + 카드매출 변화율 × 40%</div>
                <table>
                    <tr><th>지표</th><th>가중치</th><th>소스</th></tr>
                    <tr><td>방문인구 변화율</td><td><b>60%</b></td><td>SPH 유동인구</td></tr>
                    <tr><td>카드매출 변화율</td><td><b>40%</b></td><td>SPH 카드매출</td></tr>
                </table>
                <div style="font-size:11px; color:#555;">
                    📅 <b>비교 기간</b>: 최근 3개월 평균 vs 이전 3개월 평균<br>
                    📊 <b>분류</b>: +3점↑ 🔥상승 &nbsp;│&nbsp; ±3점 ⚡관찰 &nbsp;│&nbsp; -3점↓ 📉하락
                </div>
                <div class="warn">
                    ⚠️ 인사이트 탭의 <b>핫플 점수</b>와는 다른 간소화 지표입니다.<br>
                    핫플 점수는 5개 지표(방문인구·카페매출·유동인구·매매가·신규설치)를 사용합니다.
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        from views.인사이트_피드 import _render_forecast_cards
        _render_forecast_cards(pop_agg, card_agg, region_master, show_title=False)
    except Exception:
        pass

    st.markdown("---")

    # 클러스터링 함수 (캐싱) — 컨트롤 바에서 기준 년월 선택 후 호출
    @st.cache_data(ttl=3600)
    def _compute_clusters(_pop_time, _card_agg, _pop_demo, _derived, _year_month):
        fm = build_feature_matrix(_derived, _card_agg, _pop_demo, _pop_time, _year_month)
        labels, model, scaler = run_clustering(fm)
        type_map = classify_district_type(fm, labels)
        return fm, labels, type_map

    # 이름 매핑 (전역)
    name_map = centroids.set_index("district_code")["name"].to_dict()

    # ══════════════════════════════════════
    # [A] 컨트롤 바
    # ══════════════════════════════════════
    time_slots = list(TIME_SLOT_KOR.keys())
    time_labels = list(TIME_SLOT_KOR.values())

    ctrl0, ctrl1, ctrl2, ctrl3 = st.columns([1, 2, 1, 1])
    with ctrl0:
        _month_fmt = {m: f"{str(m)[:4]}.{str(m)[4:]}" for m in all_months}
        selected_month = st.selectbox(
            "기준 년월", all_months,
            format_func=lambda m: _month_fmt[m],
            index=0, key="twin_month_sel",
        )
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

    # ── 파생지표 & 클러스터링 계산 (기준 년월에 따라) ──
    derived = _calc_derived(pop_time, card_agg, pop_agg, income_agg, selected_month)

    try:
        feature_matrix, cluster_labels, cluster_type_map = _compute_clusters(
            pop_time, card_agg, pop_demo, derived, selected_month
        )
    except Exception:
        feature_matrix, cluster_labels, cluster_type_map = pd.DataFrame(), pd.Series(dtype=int), {}

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
        active_dc_set = set(data_districts)

        if sel_col == "cluster":
            cl_color_map = {}
            for _, row in column_df.iterrows():
                cl_color_map[row["district_code"]] = {
                    "fill_color": row["fill_color"],
                    "metric_value": row["metric_value"],
                }
            active_features = []
            for feat in geojson_data["features"]:
                dc = feat["properties"]["district_code"]
                if dc not in active_dc_set:
                    continue  # 비활성 법정동 제거
                info = cl_color_map.get(dc, {"fill_color": [128, 128, 128, 160], "metric_value": "데이터 없음"})
                feat["properties"]["fill_color"] = info["fill_color"]
                feat["properties"]["metric_value"] = info["metric_value"]
                # pydeck tooltip은 top-level 속성만 참조 → 복사
                feat["name"] = feat["properties"]["name"]
                feat["metric_value"] = str(info["metric_value"])
                active_features.append(feat)
        else:
            norm_map = column_df.set_index("district_code")[["norm", "metric_value"]].to_dict("index")
            active_features = []
            for feat in geojson_data["features"]:
                dc = feat["properties"]["district_code"]
                if dc not in active_dc_set:
                    continue  # 비활성 법정동 제거
                info = norm_map.get(dc, None)
                if info is None:
                    continue  # 데이터 없는 법정동도 제거
                n = info["norm"]
                feat["properties"]["metric_value"] = info["metric_value"]
                r, g, b = 255, int(255 * (1 - n * 0.8)), int(255 * (1 - n))
                a = int(120 + n * 100)
                feat["properties"]["fill_color"] = [r, g, b, a]
                # pydeck tooltip은 top-level 속성만 참조 → 복사
                feat["name"] = feat["properties"]["name"]
                feat["metric_value"] = str(info["metric_value"])
                active_features.append(feat)

        geojson_data["features"] = active_features

        # 활성 법정동 bounds 계산 → ViewState 자동 맞춤
        _all_lons, _all_lats = [], []
        for feat in active_features:
            coords = feat["geometry"].get("coordinates", [])
            gtype = feat["geometry"]["type"]
            if gtype == "MultiPolygon":
                for poly in coords:
                    if poly:
                        for pt in poly[0]:
                            _all_lons.append(pt[0])
                            _all_lats.append(pt[1])
            elif gtype == "Polygon":
                if coords:
                    for pt in coords[0]:
                        _all_lons.append(pt[0])
                        _all_lats.append(pt[1])

        if _all_lons and _all_lats:
            _center_lat = (min(_all_lats) + max(_all_lats)) / 2
            _center_lon = (min(_all_lons) + max(_all_lons)) / 2
            # 범위에 따라 줌 레벨 자동 계산
            _lat_range = max(_all_lats) - min(_all_lats)
            _lon_range = max(_all_lons) - min(_all_lons)
            _max_range = max(_lat_range, _lon_range)
            if _max_range > 0.3:
                _auto_zoom = 10.5
            elif _max_range > 0.15:
                _auto_zoom = 11.5
            elif _max_range > 0.05:
                _auto_zoom = 12.5
            else:
                _auto_zoom = 13.5
        else:
            _center_lat, _center_lon, _auto_zoom = 37.51, 126.95, 11.5

        layer = pdk.Layer(
            "GeoJsonLayer",
            data=geojson_data,
            get_fill_color="properties.fill_color",
            get_line_color=[60, 60, 60, 200],
            line_width_min_pixels=1,
            pickable=True,
            auto_highlight=True,
            highlight_color=[255, 200, 0, 120],
            stroked=True,
        )
        view = pdk.ViewState(
            latitude=_center_lat,
            longitude=_center_lon,
            zoom=_auto_zoom,
            min_zoom=max(_auto_zoom - 2, 9),
            max_zoom=min(_auto_zoom + 3, 16),
            pitch=0,
            bearing=0,
        )
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip={
                "html": '<div style="padding:6px 10px;font-family:sans-serif;">'
                        '<div style="font-size:14px;font-weight:700;margin-bottom:4px;">'
                        '{name}</div>'
                        '<div style="font-size:12px;color:#555;">'
                        f'{selected_metric}: '
                        '<b>{metric_value}</b></div></div>',
                "style": {
                    "backgroundColor": "white",
                    "color": "#333",
                    "borderRadius": "8px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.15)",
                    "border": "1px solid #e0e0e0",
                },
            },
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
                st.markdown("""
                <div class="score-help-wrap" style="margin-top:-6px;">
                    <span class="score-help-btn">❓</span>
                    <div class="score-help-popup" style="width:340px;">
                        <h4>HHI (허핀달-허쉬만 지수)</h4>
                        <div style="font-size:11px;color:#555;margin-bottom:8px;">
                            업종별 카드매출 집중도를 측정합니다.<br>
                            각 업종 매출 비중의 <b>제곱합</b>으로 계산됩니다.
                        </div>
                        <div class="formula">HHI = Σ (업종별 매출 / 전체 매출)²</div>
                        <table>
                            <tr><th>HHI 값</th><th>판정</th><th>의미</th></tr>
                            <tr><td>&lt; 0.05</td><td><b>다양</b></td><td>매출이 여러 업종에 골고루 분산</td></tr>
                            <tr><td>0.05 ~ 0.15</td><td><b>보통</b></td><td>일반적인 수준</td></tr>
                            <tr><td>&gt; 0.15</td><td><b>편중</b></td><td>특정 업종에 매출 쏠림</td></tr>
                        </table>
                        <div style="font-size:10px;color:#888;">데이터: SPH 카드매출 19개 업종 기준</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

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
    # [D] 하단 탭
    # ══════════════════════════════════════
    st.divider()
    tab_insight, tab_sim, tab_persona, tab_ai, tab_cortex = st.tabs([
        "📈 현황 인사이트", "🧪 what-if",
        "👤 페르소나", "🤖 AI 예측", "🔮 Cortex 전망"
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
            st.caption("HHI 높음 = 특정 업종에 매출 집중 (전문 상권)")
            if "consumption_hhi" in derived.columns:
                top5_hhi = derived.nlargest(5, "consumption_hhi")[["consumption_hhi"]].copy()
                top5_hhi.index = [name_map.get(dc, dc) for dc in top5_hhi.index]
                top5_hhi.columns = ["소비집중도"]
                st.dataframe(top5_hhi, use_container_width=True)

    # ── 탭2: What-if 시뮬레이션 ──
    with tab_sim:
        # ── 사용 가이드 ──
        st.markdown("""
        <div style="background:linear-gradient(135deg,#f8f7ff,#eef2ff);border:1px solid #e0e7ff;
                    border-radius:12px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:15px;font-weight:700;color:#4338CA;margin-bottom:10px;">
                🧪 What-if 시뮬레이션
            </div>
            <div style="font-size:12px;color:#555;line-height:1.8;">
                특정 동네에 가게를 열었을 때 <b>예상 월매출</b>을 추정합니다.<br>
                유동인구·소득수준·업종경쟁도 등 실제 데이터를 기반으로 계산됩니다.
            </div>
            <div style="display:flex;gap:16px;margin-top:12px;">
                <div style="flex:1;background:white;border-radius:8px;padding:10px 12px;text-align:center;border:1px solid #e8e6ff;">
                    <div style="font-size:18px;">①</div>
                    <div style="font-size:11px;color:#666;margin-top:2px;">구·동 선택</div>
                </div>
                <div style="flex:1;background:white;border-radius:8px;padding:10px 12px;text-align:center;border:1px solid #e8e6ff;">
                    <div style="font-size:18px;">②</div>
                    <div style="font-size:11px;color:#666;margin-top:2px;">업종·임대료 설정</div>
                </div>
                <div style="flex:1;background:white;border-radius:8px;padding:10px 12px;text-align:center;border:1px solid #e8e6ff;">
                    <div style="font-size:18px;">③</div>
                    <div style="font-size:11px;color:#666;margin-top:2px;">결과 확인·비교</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 시뮬레이션 히스토리 초기화
        if "sim_history" not in st.session_state:
            st.session_state.sim_history = []

        # 동네 리스트 구성
        district_list = centroids[["district_code", "name"]].sort_values("name")
        district_labels = district_list["name"].tolist()
        district_codes = district_list["district_code"].tolist()

        # ── 구/동 분리 선택 (form 바깥 → 동적 필터링) ──
        loc_col, opt_col = st.columns(2)
        with loc_col:
            gu_list = sorted(set(n.split(" ")[0] for n in district_labels))
            sim_gu = st.selectbox("📍 구 선택", gu_list, key="sim_gu")
            dong_in_gu = [n for n in district_labels if n.startswith(sim_gu)]
            sim_district_label = st.selectbox(
                "📍 동 선택",
                dong_in_gu,
                key="sim_dong",
                help="선택한 구에 포함된 법정동만 표시됩니다."
            )
        with opt_col:
            sim_industry = st.selectbox("🏪 업종", list(INDUSTRY_PARAMS.keys()))
            sim_rent = st.slider("💳 예상 월 임대료 (만원)", 100, 2000, 500, step=50)

        if st.button("🚀 시뮬레이션 실행", use_container_width=True, type="primary"):
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

            # ── 한국 원화 포맷 헬퍼 ──
            def _fmt_krw(val_man):
                """만원 단위 값을 한국식으로 포맷 (예: 56900 → '5억 6,900만원')"""
                if val_man >= 10000:
                    eok = val_man // 10000
                    remainder = val_man % 10000
                    if remainder > 0:
                        return f"{eok}억 {remainder:,}만원"
                    return f"{eok}억원"
                return f"{val_man:,}만원"

            r1, r2, r3 = st.columns(3)

            with r1:
                st.markdown("##### 💰 예상 월매출")
                st.markdown(
                    f'<div style="text-align:center;padding:12px 0;">'
                    f'<div style="font-size:28px;font-weight:700;color:#6366F1;">'
                    f'{_fmt_krw(result.monthly_revenue_mid)}</div>'
                    f'<div style="font-size:12px;color:#888;margin-top:4px;">중간 추정</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                # Gauge chart
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+delta",
                    value=result.monthly_revenue_mid,
                    delta={"reference": latest["rent"], "relative": False, "valueformat": ",", "suffix": "만원"},
                    gauge={
                        "axis": {"range": [0, max(result.monthly_revenue_high * 1.5, 1)], "tickformat": ","},
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
                ))
                fig_gauge.update_layout(height=200, margin=dict(l=20, r=20, t=20, b=10))
                st.plotly_chart(fig_gauge, use_container_width=True)
                st.caption(f"범위: {_fmt_krw(result.monthly_revenue_low)} ~ {_fmt_krw(result.monthly_revenue_high)}")

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

            # ── 디버그: 수식 투입값 확인 ──
            if result.debug_info:
                with st.expander("🔍 계산 과정 상세 (디버그)", expanded=False):
                    st.markdown(f"**수식**: `{result.debug_info.get('수식', '')}`")
                    st.markdown("---")
                    debug_left, debug_right = st.columns(2)
                    with debug_left:
                        st.markdown("**📊 투입 데이터**")
                        st.markdown(f"- **유동인구 (footfall)**: `{result.debug_info.get('footfall(total_pop)', '?')}`")
                        st.markdown(f"- **capture_rate**: `{result.debug_info.get('capture_rate', '?')}`")
                        st.markdown(f"- **객단가 (avg_ticket)**: `{result.debug_info.get('avg_ticket', '?')}`")
                        st.markdown(f"- **동네 소득**: `{result.debug_info.get('district_income', '?')}`")
                        st.markdown(f"- **전체 평균 소득**: `{result.debug_info.get('overall_income_avg', '?')}`")
                    with debug_right:
                        st.markdown("**⚙️ 보정 계수**")
                        st.markdown(f"- **소득 보정**: `{result.debug_info.get('income_correction', '?')}`")
                        st.markdown(f"- **경쟁 보정**: `{result.debug_info.get('competition_correction', '?')}`")
                        st.markdown(f"- **낮밤 비율**: `{result.debug_info.get('day_night_ratio', '?')}`")
                        st.markdown(f"- **HHI**: `{result.debug_info.get('hhi', '?')}`")
                        st.markdown(f"- **방문 비율**: `{result.debug_info.get('visit_ratio', '?')}`")
                    st.markdown("---")
                    st.markdown(f"**결과**: `{result.debug_info.get('mid_raw(원)', '?')}원` → `{result.debug_info.get('mid_man(만원)', '?')}만원`")
                    st.warning("⚠️ **footfall이 수만 이상**이면 pop_agg에서 주중/주말 × 시간대 × 성별 × 연령 등으로 중복 집계된 값일 수 있습니다. 일일 유동인구(수천~1만)가 정상적입니다.")

            # ══════════════════════════════════════
            # 시뮬레이션 비교 (자연스럽고 직관적인 UX)
            # ══════════════════════════════════════
            hist_count = len(st.session_state.sim_history)
            if hist_count == 1:
                # 첫 시뮬레이션 → 비교 유도 넛지
                st.markdown("""
                <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
                            padding:12px 16px;margin-top:8px;display:flex;align-items:center;gap:10px;">
                    <div style="font-size:24px;">💡</div>
                    <div style="font-size:12px;color:#166534;line-height:1.6;">
                        <b>다른 동네나 업종</b>으로 한 번 더 실행해보세요!<br>
                        자동으로 <b>비교 분석</b>이 나타나서 한눈에 비교할 수 있습니다.
                    </div>
                </div>
                """, unsafe_allow_html=True)

            elif hist_count >= 2:
                st.markdown("---")
                st.markdown("##### 📊 시뮬레이션 비교")
                st.caption("실행한 시뮬레이션 결과를 나란히 비교합니다. 드롭다운으로 비교 대상을 변경할 수 있습니다.")

                hist = st.session_state.sim_history
                compare_options = [f"{h['district']} · {h['industry']} (임대료 {h['rent']:,}만원)" for h in hist]

                cmp_col1, cmp_col2 = st.columns(2)
                with cmp_col1:
                    cmp_idx1 = st.selectbox("🅰️ 비교 대상 A", range(len(hist)),
                                            format_func=lambda i: compare_options[i],
                                            index=len(hist) - 2, key="cmp_a")
                with cmp_col2:
                    cmp_idx2 = st.selectbox("🅱️ 비교 대상 B", range(len(hist)),
                                            format_func=lambda i: compare_options[i],
                                            index=len(hist) - 1, key="cmp_b")

                h1, h2 = hist[cmp_idx1], hist[cmp_idx2]
                res1, res2 = h1["result"], h2["result"]

                # 비교 카드 UI
                card1, card2 = st.columns(2)
                with card1:
                    profit1 = res1.monthly_revenue_mid - h1["rent"]
                    profit_color1 = "#16a34a" if profit1 > 0 else "#dc2626"
                    st.markdown(f"""
                    <div style="border:2px solid #6366F1;border-radius:12px;padding:16px;background:#fafafe;">
                        <div style="font-size:13px;font-weight:700;color:#6366F1;margin-bottom:8px;">
                            🅰️ {h1['district']} · {h1['industry']}
                        </div>
                        <div style="font-size:11px;color:#888;margin-bottom:12px;">임대료 {h1['rent']:,}만원</div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="font-size:11px;color:#666;">예상 월매출</span>
                            <span style="font-size:13px;font-weight:700;">{_fmt_krw(res1.monthly_revenue_mid)}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="font-size:11px;color:#666;">예상 수익</span>
                            <span style="font-size:13px;font-weight:700;color:{profit_color1};">{_fmt_krw(profit1)}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="font-size:11px;color:#666;">경쟁 강도</span>
                            <span style="font-size:13px;">{res1.competition_index:.2f}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with card2:
                    profit2 = res2.monthly_revenue_mid - h2["rent"]
                    profit_color2 = "#16a34a" if profit2 > 0 else "#dc2626"
                    st.markdown(f"""
                    <div style="border:2px solid #F59E0B;border-radius:12px;padding:16px;background:#fffefb;">
                        <div style="font-size:13px;font-weight:700;color:#d97706;margin-bottom:8px;">
                            🅱️ {h2['district']} · {h2['industry']}
                        </div>
                        <div style="font-size:11px;color:#888;margin-bottom:12px;">임대료 {h2['rent']:,}만원</div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="font-size:11px;color:#666;">예상 월매출</span>
                            <span style="font-size:13px;font-weight:700;">{_fmt_krw(res2.monthly_revenue_mid)}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                            <span style="font-size:11px;color:#666;">예상 수익</span>
                            <span style="font-size:13px;font-weight:700;color:{profit_color2};">{_fmt_krw(profit2)}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;">
                            <span style="font-size:11px;color:#666;">경쟁 강도</span>
                            <span style="font-size:13px;">{res2.competition_index:.2f}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # 승자 표시
                if profit1 != profit2:
                    winner = h1 if profit1 > profit2 else h2
                    st.markdown(f"""
                    <div style="text-align:center;margin-top:8px;padding:8px;
                                background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;">
                        <span style="font-size:13px;color:#166534;">
                            🏆 수익 기준 <b>{winner['district']} · {winner['industry']}</b>이(가) 더 유리합니다.
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

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
                    textposition="inside",
                ))
                fig_job.update_layout(
                    title="직업군 분포", height=250,
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

    # ── 탭4: AI 예측 (MiroFish Lite v2) ──
    with tab_ai:
        if not MIROFISH_AVAILABLE:
            st.warning("MiroFish 모듈을 로드할 수 없습니다.")
            st.stop()

        st.markdown(
            "**MiroFish Lite v2** — 클러스터별 AI 분석가가 동네의 미래 상권 변화를 예측합니다."
        )

        # ── 설정: 범위 + 기간 ──
        _ai_c1, _ai_c2 = st.columns([2, 1])
        with _ai_c2:
            ai_n_rounds = st.selectbox("예측 기간 (개월)", [2, 3, 4, 5], index=1, key="ai_rounds")
        with _ai_c1:
            ai_scope = st.radio("범위", ["전체 동네", "구 선택", "동 선택"], horizontal=True, key="ai_scope")

        # ── 동네 선택 ──
        _ai_target_dcs = None  # None이면 전체

        # region_master에서 구/동 매핑 구성
        _rm = region_master[region_master["district_code"].isin(data_districts)].copy()
        _cities = sorted(_rm["city_kor"].unique())

        if ai_scope == "구 선택":
            _sel_cities = st.multiselect("구 선택", options=_cities, key="ai_city")
            if _sel_cities:
                _ai_target_dcs = _rm[_rm["city_kor"].isin(_sel_cities)]["district_code"].tolist()

        elif ai_scope == "동 선택":
            _sel_city_for_dong = st.selectbox("구 먼저 선택", options=_cities, key="ai_city_for_dong")
            if _sel_city_for_dong:
                _dongs_in_city = _rm[_rm["city_kor"] == _sel_city_for_dong].sort_values("district_kor")
                _dong_options = _dongs_in_city["district_code"].tolist()
                _dong_labels = {row["district_code"]: row["district_kor"] for _, row in _dongs_in_city.iterrows()}
                _sel_dongs = st.multiselect(
                    f"{_sel_city_for_dong} 동 선택",
                    options=_dong_options,
                    format_func=lambda dc: _dong_labels.get(dc, dc),
                    key="ai_dong",
                )
                if _sel_dongs:
                    _ai_target_dcs = _sel_dongs

        # 선택 결과 표시
        if _ai_target_dcs:
            st.caption(f"선택된 동네: {len(_ai_target_dcs)}개")
        elif ai_scope != "전체 동네":
            st.caption("동네를 선택하세요.")

        if st.button("AI 예측 실행", type="primary", use_container_width=True, key="ai_run"):
            # 선택 동네 모드인데 선택 안 했으면 경고
            if ai_scope != "전체 동네" and not _ai_target_dcs:
                st.warning("동네를 선택하세요.")
                st.stop()

            with st.spinner("데이터 준비 중..."):
                try:
                    _all_profiles = generate_all_profiles(
                        derived_metrics=derived, card_agg_df=card_agg,
                        pop_time_df=pop_time, income_agg_df=income_agg,
                        centroids_df=centroids, snapshot_month=int(selected_month),
                    )

                    # 선택된 동네만 필터링
                    if _ai_target_dcs:
                        _target_set = set(_ai_target_dcs)
                        _profiles = [p for p in _all_profiles if p["district_code"] in _target_set]
                    else:
                        _profiles = _all_profiles

                    # 대상 동네 기준으로 클러스터 데이터 구성
                    _target_codes = {p["district_code"] for p in _profiles}
                    _sim_map = {}
                    if not feature_matrix.empty:
                        for _dc in feature_matrix.index:
                            if _dc in _target_codes:
                                _sim_df = find_similar_districts(feature_matrix, _dc, top_n=5)
                                _sim_map[_dc] = list(zip(
                                    _sim_df["district_code"].tolist(),
                                    [round(float(s), 3) for s in _sim_df["similarity"].tolist()],
                                ))
                    _dc_cluster = {}
                    if not cluster_labels.empty:
                        for _dc, _cid in cluster_labels.items():
                            if _dc in _target_codes:
                                _dc_cluster[_dc] = {
                                    "cluster_id": int(_cid),
                                    "cluster_label": cluster_type_map.get(int(_cid), f"유형 {_cid}"),
                                }
                    _cluster_data = {
                        "similar_map": _sim_map,
                        "district_cluster": _dc_cluster,
                        "type_map": {int(k): v for k, v in cluster_type_map.items()},
                    }
                except Exception as e:
                    st.error(f"데이터 준비 실패: {e}")
                    st.stop()

            _n_clusters = len(cluster_type_map) if cluster_type_map else 1
            _total_steps = _n_clusters * ai_n_rounds
            _prog = st.progress(0, text="시뮬레이션 시작...")

            def _on_progress(step, total, msg):
                _prog.progress(min(step / max(total, 1), 1.0), text=msg)

            try:
                _result = run_prediction(
                    profiles=_profiles,
                    cluster_data=_cluster_data,
                    n_rounds=ai_n_rounds,
                    progress_callback=_on_progress,
                )
                _prog.progress(1.0, text="완료!")
                st.session_state["mirofish_result"] = _result
            except Exception as e:
                _prog.empty()
                st.error(f"시뮬레이션 실패: {e}")

        # ── 결과 표시 ──
        if "mirofish_result" in st.session_state:
            _out = st.session_state["mirofish_result"]["output"]

            st.markdown("---")
            st.markdown(
                f"##### 예측 결과 — {_out.n_districts}개 동네, {_out.n_rounds}개월, "
                f"클러스터 {len(_out.cluster_labels)}개"
            )

            if _out.surge_rankings:
                st.markdown("**급등 예측 순위**")
                _rows = []
                for _i, _d in enumerate(_out.surge_rankings[:15]):
                    _rows.append({
                        "순위": _i + 1, "동네": _d["name"], "시그널": _d["signal"],
                        "방문자": f"{_d['visit_growth']:+.1f}%",
                        "매출": f"{_d['spending_growth']:+.1f}%",
                        "인구이동": f"{_d['net_migration']:+.0f}명",
                        "주력 업종": _d["hot_industry"],
                        "리스크": _d["risk"],
                    })
                st.dataframe(pd.DataFrame(_rows).set_index("순위"), use_container_width=True)

            _rc1, _rc2 = st.columns(2)
            with _rc1:
                if _out.industry_trends:
                    st.markdown("**업종별 수요 변화**")
                    for _t in _out.industry_trends[:7]:
                        _icon = "📈" if _t["net"] > 0 else ("📉" if _t["net"] < 0 else "➡️")
                        st.markdown(
                            f"{_icon} {_t['industry']}: **{_t['direction']}** "
                            f"(상승 {_t['hot_count']} / 하락 {_t['decline_count']})"
                        )
            with _rc2:
                if _out.population_flows:
                    st.markdown("**인구 이동**")
                    for _f in _out.population_flows[:7]:
                        _icon2 = "🟢" if _f["direction"] == "유입" else "🔴"
                        st.markdown(f"{_icon2} {_f['name']}: {_f['direction']} **{abs(_f['net_migration']):.0f}명**")

            if _out.decline_rankings:
                st.markdown("---")
                st.markdown("**주의 필요 동네**")
                for _d in _out.decline_rankings[:5]:
                    st.markdown(f"- {_d['name']} ({_d['signal']}): {_d['risk']}")

            st.markdown("---")
            if st.button("AI 분석 보고서 생성", key="ai_report"):
                with st.spinner("Cortex AI가 보고서 작성 중..."):
                    try:
                        _report = generate_report(_out)
                        st.markdown(_report)
                    except Exception as e:
                        st.error(f"보고서 생성 실패: {e}")


    # ── 탭5: Cortex 전망 (신규) ──
    with tab_cortex:
        st.markdown("**🔮 Cortex AI 3개월 상권 전망**")
        st.caption("60개월 유동인구·매출 추이를 Cortex AI가 분석하여 향후 3개월을 예측합니다.")

        # 동네 선택
        cortex_district = st.selectbox(
            "분석할 동네", district_labels, index=0, key="cortex_district"
        )

        if st.button("🔮 전망 분석 시작", key="cortex_start", use_container_width=True):
            cortex_dc = district_codes[district_labels.index(cortex_district)]

            with st.spinner("Cortex AI가 60개월 데이터를 분석 중..."):
                try:
                    from chat_ui import _cortex
                    from data_loader import run_query, SPH

                    # 유동인구 추이
                    pop_ts = run_query(f"""
                        SELECT STANDARD_YEAR_MONTH as MONTH,
                               ROUND(SUM(RESIDENTIAL_POPULATION)) as RESIDENTIAL,
                               ROUND(SUM(WORKING_POPULATION)) as WORKING,
                               ROUND(SUM(VISITING_POPULATION)) as VISITING,
                               ROUND(SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION)) as TOTAL
                        FROM {SPH}.FLOATING_POPULATION_INFO
                        WHERE DISTRICT_CODE = '{cortex_dc}'
                        GROUP BY 1 ORDER BY 1
                    """)

                    # 카드매출 추이
                    sales_ts = run_query(f"""
                        SELECT STANDARD_YEAR_MONTH as MONTH,
                               ROUND(SUM(TOTAL_SALES)) as TOTAL_SALES,
                               ROUND(SUM(COFFEE_SALES)) as COFFEE,
                               ROUND(SUM(FOOD_SALES)) as FOOD
                        FROM {SPH}.CARD_SALES_INFO
                        WHERE DISTRICT_CODE = '{cortex_dc}' AND CARD_TYPE = '1'
                        GROUP BY 1 ORDER BY 1
                    """)

                    prompt = f"""{cortex_district}의 상권 데이터입니다.

[유동인구 월별 추이 ({len(pop_ts)}개월)]
{pop_ts.to_string(index=False)}

[카드매출 월별 추이 ({len(sales_ts)}개월)]
{sales_ts.to_string(index=False)}

위 데이터를 분석하여 다음을 제공하세요:

### 트렌드 분석
- 상승/하락/정체 판단

### 계절성 패턴
- 월별 반복 패턴

### 향후 3개월 예측
| 월 | 예상 유동인구 | 예상 매출 | 근거 |
|---|---|---|---|

### 출점 추천
- 이 동네에 가게를 연다면 적합한 업종과 이유

### 리스크
- 주의해야 할 요인

간결하게 표 위주로 답변하세요. 한국어."""

                    result = _cortex(prompt)
                    st.markdown(result)

                except Exception as e:
                    st.error(f"Cortex 전망 오류: {e}")
