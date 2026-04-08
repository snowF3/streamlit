"""
탭 4: 디지털 트윈 — 합성 시민이 움직이는 살아있는 지도 + 시뮬레이션
데이터 범위: 중구, 영등포구, 서초구 (118개 법정동)
"""
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_geojson, load_region_master, load_population_time,
    load_card_sales_time, load_income_agg, load_income_detail,
    load_card_sales_agg, load_population_agg
)
from charts import TIME_SLOT_KOR, LIFESTYLE_KOR, CATEGORY_KOR
from chat_ui import render_chat_panel

st.set_page_config(page_title="디지털 트윈", page_icon="🌆", layout="wide")
st.title("🌆 디지털 트윈 — 살아있는 서울")
st.caption("데이터 범위: 서울 중구 · 영등포구 · 서초구 (118개 법정동)")

# ── 색상 팔레트 (라이프스타일별) ──
LIFESTYLE_COLORS = {
    "L01": [99, 110, 250, 180],     # 싱글 - 파란
    "L02": [0, 204, 150, 180],      # 신혼 - 초록
    "L03": [255, 215, 0, 180],      # 영유아가족 - 노란
    "L04": [255, 127, 14, 180],     # 청소년가족 - 주황
    "L05": [148, 103, 189, 180],    # 성인자녀 - 보라
    "L06": [239, 85, 59, 180],      # 실버 - 빨간
}

# ── 사이드바: 기준 년월 ──
pop_agg_all = load_population_agg()
all_months = sorted(pop_agg_all["STANDARD_YEAR_MONTH"].unique(), reverse=True)
month_labels = [f"{str(m)[:4]}년 {str(m)[4:6]}월" for m in all_months]
selected_month_label = st.sidebar.selectbox("기준 년월", month_labels, index=0)
selected_month = all_months[month_labels.index(selected_month_label)]
st.sidebar.caption(f"선택: {selected_month_label}")


# ── 법정동 중심좌표 계산 (데이터 있는 법정동만) ──
@st.cache_data
def get_district_centers():
    """GeoJSON에서 데이터 있는 법정동의 중심좌표 추출"""
    geojson = load_geojson()
    pop_agg = load_population_agg()
    data_districts = set(pop_agg["DISTRICT_CODE"].unique())

    centers = {}
    for feature in geojson["features"]:
        dc = feature["properties"]["district_code"]
        if dc not in data_districts:
            continue
        geom = feature["geometry"]
        if "coordinates" not in geom:
            continue
        coords = []
        if geom["type"] == "MultiPolygon":
            for polygon in geom["coordinates"]:
                for ring in polygon:
                    coords.extend(ring)
        elif geom["type"] == "Polygon":
            for ring in geom["coordinates"]:
                coords.extend(ring)

        if coords:
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            centers[dc] = {
                "lon": sum(lons) / len(lons),
                "lat": sum(lats) / len(lats),
                "lon_min": min(lons), "lon_max": max(lons),
                "lat_min": min(lats), "lat_max": max(lats),
            }
    return centers


@st.cache_data
def generate_synthetic_population(_selected_month, sample_rate=0.05, max_agents=15000):
    """합성 인구 생성 — 자산소득 CUSTOMER_COUNT 기반"""
    income_detail = load_income_detail()
    centers = get_district_centers()

    # 선택된 년월 (없으면 최신)
    available = income_detail["STANDARD_YEAR_MONTH"].unique()
    if _selected_month in available:
        use_month = _selected_month
    else:
        use_month = max(available)

    df = income_detail[income_detail["STANDARD_YEAR_MONTH"] == use_month].copy()

    agents = []
    np.random.seed(42)
    lifestyles = ["L01", "L02", "L03", "L04", "L05", "L06"]

    for _, row in df.iterrows():
        dc = str(row["DISTRICT_CODE"])
        if dc not in centers:
            continue

        customer_count = int(row.get("CUSTOMER_COUNT", 0))
        if customer_count <= 0:
            continue

        n_agents = max(1, int(customer_count * sample_rate))
        center = centers[dc]
        gender = row["GENDER"]
        age_group = int(row["AGE_GROUP"]) if pd.notna(row["AGE_GROUP"]) else 30

        # 연령 기반 라이프스타일 확률
        if age_group < 25:
            ls_prob = [0.60, 0.05, 0.02, 0.05, 0.25, 0.03]
        elif age_group < 35:
            ls_prob = [0.35, 0.25, 0.20, 0.05, 0.10, 0.05]
        elif age_group < 45:
            ls_prob = [0.10, 0.10, 0.25, 0.30, 0.15, 0.10]
        elif age_group < 55:
            ls_prob = [0.08, 0.05, 0.10, 0.25, 0.35, 0.17]
        else:
            ls_prob = [0.10, 0.02, 0.03, 0.05, 0.30, 0.50]

        for i in range(n_agents):
            lon = np.random.uniform(center["lon_min"], center["lon_max"])
            lat = np.random.uniform(center["lat_min"], center["lat_max"])
            age = np.random.randint(age_group, min(age_group + 5, 90))
            lifestyle = np.random.choice(lifestyles, p=ls_prob)

            agents.append({
                "district_code": dc,
                "home_lon": lon,
                "home_lat": lat,
                "lon": lon,
                "lat": lat,
                "gender": gender,
                "age": age,
                "lifestyle": lifestyle,
            })

        if len(agents) >= max_agents:
            break

    return pd.DataFrame(agents)


@st.cache_data
def simulate_movement_cached(agents_json, time_slot):
    """시간대에 따른 에이전트 위치 업데이트 (벡터화)"""
    import io
    df = pd.read_json(io.StringIO(agents_json))
    n = len(df)
    np.random.seed(hash(time_slot) % 2**31)

    centers = get_district_centers()

    # 직장 밀집 법정동 상위 (3개 구 내에서)
    pop_agg = load_population_agg()
    latest = pop_agg["STANDARD_YEAR_MONTH"].max()
    pop_latest = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == latest]
    work_top = pop_latest.nlargest(15, "WORKING_POPULATION")["DISTRICT_CODE"].tolist()
    work_centers_list = [centers[dc] for dc in work_top if dc in centers]

    if not work_centers_list:
        work_centers_list = [list(centers.values())[0]]

    if time_slot in ["T06", "T24", "T21"]:
        # 집 근처
        df["lon"] = df["home_lon"] + np.random.normal(0, 0.0008, n)
        df["lat"] = df["home_lat"] + np.random.normal(0, 0.0008, n)

    elif time_slot in ["T09", "T15"]:
        # 직장인 이동
        is_worker = (df["age"] >= 25) & (df["age"] <= 60) & (np.random.random(n) < 0.65)
        # 비직장인 → 집 근처
        df.loc[~is_worker, "lon"] = df.loc[~is_worker, "home_lon"] + np.random.normal(0, 0.001, (~is_worker).sum())
        df.loc[~is_worker, "lat"] = df.loc[~is_worker, "home_lat"] + np.random.normal(0, 0.001, (~is_worker).sum())
        # 직장인 → 직장 밀집 지역
        worker_count = is_worker.sum()
        if worker_count > 0:
            wc_indices = np.random.randint(0, len(work_centers_list), worker_count)
            for i, (idx, _) in enumerate(df[is_worker].iterrows()):
                wc = work_centers_list[wc_indices[i]]
                df.loc[idx, "lon"] = np.random.uniform(wc["lon_min"], wc["lon_max"])
                df.loc[idx, "lat"] = np.random.uniform(wc["lat_min"], wc["lat_max"])

    elif time_slot == "T12":
        # 점심 — 직장 주변 약간 분산
        is_worker = (df["age"] >= 25) & (df["age"] <= 60) & (np.random.random(n) < 0.55)
        df.loc[~is_worker, "lon"] = df.loc[~is_worker, "home_lon"] + np.random.normal(0, 0.002, (~is_worker).sum())
        df.loc[~is_worker, "lat"] = df.loc[~is_worker, "home_lat"] + np.random.normal(0, 0.002, (~is_worker).sum())
        worker_count = is_worker.sum()
        if worker_count > 0:
            wc_indices = np.random.randint(0, len(work_centers_list), worker_count)
            for i, (idx, _) in enumerate(df[is_worker].iterrows()):
                wc = work_centers_list[wc_indices[i]]
                df.loc[idx, "lon"] = np.random.uniform(wc["lon_min"], wc["lon_max"])
                df.loc[idx, "lat"] = np.random.uniform(wc["lat_min"], wc["lat_max"])

    elif time_slot == "T18":
        # 저녁 — 귀가 + 일부 외출
        going_home = np.random.random(n) < 0.7
        df.loc[going_home, "lon"] = df.loc[going_home, "home_lon"] + np.random.normal(0, 0.001, going_home.sum())
        df.loc[going_home, "lat"] = df.loc[going_home, "home_lat"] + np.random.normal(0, 0.001, going_home.sum())
        out_count = (~going_home).sum()
        if out_count > 0:
            wc_indices = np.random.randint(0, len(work_centers_list), out_count)
            for i, (idx, _) in enumerate(df[~going_home].iterrows()):
                wc = work_centers_list[wc_indices[i]]
                df.loc[idx, "lon"] = np.random.uniform(wc["lon_min"], wc["lon_max"])
                df.loc[idx, "lat"] = np.random.uniform(wc["lat_min"], wc["lat_max"])

    # 색상 추가
    df["r"] = df["lifestyle"].map(lambda ls: LIFESTYLE_COLORS.get(ls, [128,128,128,180])[0])
    df["g"] = df["lifestyle"].map(lambda ls: LIFESTYLE_COLORS.get(ls, [128,128,128,180])[1])
    df["b"] = df["lifestyle"].map(lambda ls: LIFESTYLE_COLORS.get(ls, [128,128,128,180])[2])

    return df


# ══════════════════════════════════════════════
# 메인 UI
# ══════════════════════════════════════════════

tab_twin, tab_sim = st.tabs(["🌆 살아있는 지도", "🧪 시뮬레이션"])

# ── 탭 1: 살아있는 지도 ──
with tab_twin:
    st.subheader("시간대 슬라이더로 시민의 움직임을 관찰하세요")

    time_slots = ["T06", "T09", "T12", "T15", "T18", "T21", "T24"]
    time_labels = [TIME_SLOT_KOR[t] for t in time_slots]

    col_slider, col_legend = st.columns([4, 1])
    with col_slider:
        time_idx = st.select_slider(
            "시간대",
            options=list(range(len(time_slots))),
            format_func=lambda x: time_labels[x],
            value=2
        )
    with col_legend:
        st.markdown("**라이프스타일 범례**")
        for ls, color in LIFESTYLE_COLORS.items():
            name = LIFESTYLE_KOR.get(ls, ls)
            r, g, b, _ = color
            st.markdown(f'<span style="color:rgb({r},{g},{b})">●</span> {name}', unsafe_allow_html=True)

    selected_time = time_slots[time_idx]

    with st.spinner("합성 인구 생성 중... (최초 1회)"):
        agents_df = generate_synthetic_population(selected_month)

    with st.spinner(f"{TIME_SLOT_KOR[selected_time]} 시뮬레이션 중..."):
        moved = simulate_movement_cached(agents_df.to_json(), selected_time)

    # ── Pydeck 지도 (Carto 베이스맵 — 토큰 불필요) ──
    # 3개 구 중심으로 뷰 설정
    centers = get_district_centers()
    all_lats = [c["lat"] for c in centers.values()]
    all_lons = [c["lon"] for c in centers.values()]
    center_lat = sum(all_lats) / len(all_lats) if all_lats else 37.51
    center_lon = sum(all_lons) / len(all_lons) if all_lons else 126.95

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=moved[["lon", "lat", "r", "g", "b", "age", "gender", "lifestyle"]],
        get_position=["lon", "lat"],
        get_fill_color=["r", "g", "b", 180],
        get_radius=40,
        radius_min_pixels=2,
        radius_max_pixels=6,
        pickable=True,
        opacity=0.7,
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=12.5,
        pitch=0,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "나이: {age}세 | 성별: {gender} | 라이프스타일: {lifestyle}"},
        map_provider="carto",
        map_style="dark",
    )

    st.pydeck_chart(deck)

    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.metric("합성 시민 수", f"{len(moved):,}명")
    with col_info2:
        st.metric("시간대", TIME_SLOT_KOR[selected_time])
    with col_info3:
        st.metric("기준 월", selected_month_label)

# ── 탭 2: 시뮬레이션 ──
with tab_sim:
    st.subheader("🧪 '만약에' 시뮬레이션")
    st.markdown("법정동을 선택하고, 업종을 지정하면 예상 매출을 시뮬레이션합니다.")
    st.caption(f"기준: {selected_month_label}")

    region_master = load_region_master()
    pop_agg_sim = load_population_agg()
    data_districts_sim = set(pop_agg_sim["DISTRICT_CODE"].unique())
    region_with_data = region_master[region_master["district_code"].isin(data_districts_sim)].copy()
    region_with_data["label"] = region_with_data["city_kor"] + " " + region_with_data["district_kor"]

    col_sim1, col_sim2 = st.columns(2)
    with col_sim1:
        selected_area = st.selectbox(
            "📍 위치 선택 (중구/영등포구/서초구)",
            region_with_data.sort_values("label")["label"].tolist()
        )
    with col_sim2:
        business_type = st.selectbox(
            "🏪 업종 선택",
            ["카페", "음식점", "미용실", "편의점", "의류매장"]
        )

    sel_row = region_with_data[region_with_data["label"] == selected_area].iloc[0]
    sim_dc = sel_row["district_code"]

    if st.button("🚀 시뮬레이션 실행", type="primary"):
        with st.spinner("시뮬레이션 중..."):
            pop_time = load_population_time()
            card_time = load_card_sales_time()

            # 업종별 매출 비중으로 소비율 추정
            business_sales_col = {
                "카페": "COFFEE", "음식점": "FOOD", "미용실": "BEAUTY",
                "편의점": "SMALL_RETAIL_STORE", "의류매장": "CLOTHING_ACCESSORIES",
            }
            biz_key = business_sales_col.get(business_type, "COFFEE")

            # 해당 법정동 유동인구 (선택된 월)
            pop_district = pop_time[
                (pop_time["DISTRICT_CODE"] == sim_dc) &
                (pop_time["STANDARD_YEAR_MONTH"] == selected_month) &
                (pop_time["WEEKDAY_WEEKEND"] == "W")
            ]

            # 카드매출
            card_district = card_time[
                (card_time["DISTRICT_CODE"] == sim_dc) &
                (card_time["STANDARD_YEAR_MONTH"] == selected_month)
            ]

            # 카드매출 기반 소비율
            card_agg_district = load_card_sales_agg()
            card_agg_d = card_agg_district[
                (card_agg_district["DISTRICT_CODE"] == sim_dc) &
                (card_agg_district["STANDARD_YEAR_MONTH"] == selected_month)
            ]
            biz_ratio = 0.05
            if not card_agg_d.empty:
                biz_col = f"{biz_key}_SALES"
                if biz_col in card_agg_d.columns and "TOTAL_SALES" in card_agg_d.columns:
                    total_s = card_agg_d["TOTAL_SALES"].values[0]
                    if total_s > 0:
                        biz_ratio = card_agg_d[biz_col].values[0] / total_s

            avg_price = {"카페": 5000, "음식점": 12000, "미용실": 25000,
                         "편의점": 8000, "의류매장": 50000}
            price = avg_price.get(business_type, 5000)
            capture_rate = 0.05

            time_slots_sim = ["T06", "T09", "T12", "T15", "T18", "T21"]
            results = []
            for ts in time_slots_sim:
                ts_pop = pop_district[pop_district["TIME_SLOT"] == ts]
                if ts_pop.empty:
                    results.append({"시간대": TIME_SLOT_KOR.get(ts, ts), "유동인구": 0,
                                    "소비율": f"{biz_ratio*100:.1f}%", "예상고객": 0, "예상매출(원)": 0})
                    continue
                total_pop = (ts_pop["RESIDENTIAL_POPULATION"].values[0]
                             + ts_pop["WORKING_POPULATION"].values[0]
                             + ts_pop["VISITING_POPULATION"].values[0])
                est_customers = int(total_pop * biz_ratio * capture_rate)
                results.append({
                    "시간대": TIME_SLOT_KOR.get(ts, ts),
                    "유동인구": int(total_pop),
                    "소비율": f"{biz_ratio*100:.1f}%",
                    "예상고객": est_customers,
                    "예상매출(원)": est_customers * price,
                })

            results_df = pd.DataFrame(results)
            daily_revenue = results_df["예상매출(원)"].sum()

            # 주말 보정
            pop_weekend = pop_time[
                (pop_time["DISTRICT_CODE"] == sim_dc) &
                (pop_time["STANDARD_YEAR_MONTH"] == selected_month) &
                (pop_time["WEEKDAY_WEEKEND"] == "H")
            ]
            if not pop_weekend.empty and not pop_district.empty:
                wk_total = pop_weekend[["RESIDENTIAL_POPULATION", "WORKING_POPULATION", "VISITING_POPULATION"]].sum().sum()
                wd_total = pop_district[["RESIDENTIAL_POPULATION", "WORKING_POPULATION", "VISITING_POPULATION"]].sum().sum()
                weekend_ratio = wk_total / max(wd_total, 1)
            else:
                weekend_ratio = 0.6

            monthly_revenue = int(daily_revenue * 22 + daily_revenue * weekend_ratio * 8)

        # 결과 표시
        st.divider()
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.metric("📅 월 예상 매출", f"{monthly_revenue/1e4:,.0f}만원")
        with col_r2:
            st.metric("📊 평일 일 매출", f"{daily_revenue/1e4:,.0f}만원")
        with col_r3:
            st.metric("🏖️ 주말 비율", f"평일 대비 {weekend_ratio*100:.0f}%")

        st.subheader("⏰ 시간대별 상세")
        st.dataframe(results_df.reset_index(drop=True), use_container_width=True)

        # 인사이트
        st.subheader("💡 AI 인사이트")
        peak = results_df.nlargest(1, "예상고객")
        peak_time = peak["시간대"].values[0] if not peak.empty else "-"

        insights = [f"**피크 시간대**: {peak_time}"]
        if weekend_ratio < 0.5:
            insights.append("⚠️ 주말 유동인구가 평일의 50% 미만 — 주말 집객 전략 필요")
        if monthly_revenue > 50_000_000:
            insights.append(f"🟢 월 {monthly_revenue/1e4:,.0f}만원 — 높은 매출 잠재력")
        elif monthly_revenue > 30_000_000:
            insights.append(f"🟡 월 {monthly_revenue/1e4:,.0f}만원 — 차별화 전략 필요")
        else:
            insights.append(f"🔴 월 {monthly_revenue/1e4:,.0f}만원 — 유동인구 부족 주의")

        for ins in insights:
            st.markdown(f"- {ins}")

# Build page context for chat panel
_num_agents = len(agents_df) if 'agents_df' in dir() else 0
page_context = f"디지털 트윈 - 기준: {selected_month_label}, 시간대: {TIME_SLOT_KOR.get(selected_time, selected_time)}, 합성 시민 수: {_num_agents:,}명"

render_chat_panel(current_tab="디지털 트윈", selected_district=None, selected_month=str(selected_month), page_context=page_context)
