"""
탭 2: 동네 프로파일 — 선택한 법정동의 소비·인구·부동산·소득 엑스레이
데이터 범위: 중구, 영등포구, 서초구 (118개 법정동)
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_region_master, load_card_sales_agg, load_card_sales_time,
    load_population_agg, load_population_time, load_population_demo,
    load_income_agg, load_district_centroids, load_realestate, load_richgo_population
)
from scoring import calc_derived_metrics
from charts import (
    spending_radar_chart, population_flow_chart, population_pyramid,
    realestate_trend_chart, income_distribution_chart, job_donut_chart
)
from clustering import (
    build_feature_matrix, run_clustering, classify_district_type,
    find_similar_districts, get_cluster_color, FEATURE_COLS,
)
from chat_ui import render_chat_panel

st.set_page_config(page_title="동네 프로파일", page_icon="🔍", layout="wide")
st.title("🔍 동네 프로파일")

# ── 데이터 로드 ──
try:
    region_master = load_region_master()
    pop_agg = load_population_agg()
    card_agg = load_card_sales_agg()
    income_agg = load_income_agg()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# ── 데이터가 있는 법정동만 목록에 표시 ──
data_districts = set(pop_agg["DISTRICT_CODE"].unique())
region_with_data = region_master[region_master["district_code"].isin(data_districts)].copy()
region_with_data["label"] = region_with_data["city_kor"] + " " + region_with_data["district_kor"]
options = region_with_data.sort_values("label")["label"].tolist()

if not options:
    st.error("데이터가 있는 법정동이 없습니다.")
    st.stop()

selected = st.sidebar.selectbox("동네 선택", options, index=0)

# ── 기준 년월 선택 ──
all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
month_labels = [f"{str(m)[:4]}년 {str(m)[4:6]}월" for m in all_months]
selected_month_label = st.sidebar.selectbox("기준 년월", month_labels, index=0)
selected_month = all_months[month_labels.index(selected_month_label)]

# 선택된 동네의 코드
sel_row = region_with_data[region_with_data["label"] == selected].iloc[0]
dc = sel_row["district_code"]
city = sel_row["city_kor"]
district = sel_row["district_kor"]

st.header(f"📍 {city} {district}")
st.caption(f"기준: {selected_month_label}")

# ── 추가 데이터 로드 ──
try:
    card_time = load_card_sales_time()
except Exception:
    card_time = pd.DataFrame()

try:
    pop_time = load_population_time()
except Exception:
    pop_time = pd.DataFrame()

try:
    pop_demo = load_population_demo()
except Exception:
    pop_demo = pd.DataFrame()

# 해당 동네 필터 (선택된 년월 기준)
card_district = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == selected_month)]
pop_district = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == selected_month)]
income_district = income_agg[(income_agg["DISTRICT_CODE"] == dc) & (income_agg["STANDARD_YEAR_MONTH"] == selected_month)]

card_time_district = pd.DataFrame()
if not card_time.empty:
    card_time_district = card_time[(card_time["DISTRICT_CODE"] == dc) & (card_time["STANDARD_YEAR_MONTH"] == selected_month)]

pop_time_district = pd.DataFrame()
if not pop_time.empty:
    pop_time_district = pop_time[(pop_time["DISTRICT_CODE"] == dc) & (pop_time["STANDARD_YEAR_MONTH"] == selected_month)]

pop_demo_district = pd.DataFrame()
if not pop_demo.empty:
    pop_demo_district = pop_demo[(pop_demo["DISTRICT_CODE"] == dc) & (pop_demo["STANDARD_YEAR_MONTH"] == selected_month)]

# ── 요약 지표 ──
col1, col2, col3, col4 = st.columns(4)

with col1:
    if not pop_district.empty:
        total_pop = (pop_district["RESIDENTIAL_POPULATION"].values[0]
                     + pop_district["WORKING_POPULATION"].values[0]
                     + pop_district["VISITING_POPULATION"].values[0])
        st.metric("총 유동인구", f"{total_pop:,.0f}명")
    else:
        st.metric("총 유동인구", "N/A")

with col2:
    if not card_district.empty and "TOTAL_SALES" in card_district.columns:
        val = card_district["TOTAL_SALES"].values[0]
        if val > 1e8:
            st.metric("월 카드매출", f"{val/1e8:,.1f}억원")
        else:
            st.metric("월 카드매출", f"{val/1e4:,.0f}만원")
    else:
        st.metric("월 카드매출", "N/A")

with col3:
    if not income_district.empty and "AVERAGE_INCOME" in income_district.columns:
        avg_income = income_district["AVERAGE_INCOME"].values[0]
        if pd.notna(avg_income) and avg_income > 0:
            st.metric("평균소득", f"{avg_income/1e4:,.0f}만원")
        else:
            st.metric("평균소득", "N/A")
    else:
        st.metric("평균소득", "N/A")

with col4:
    if not income_district.empty and "total_customers" in income_district.columns:
        customers = income_district["total_customers"].values[0]
        st.metric("고객 수", f"{customers:,.0f}명")
    else:
        st.metric("고객 수", "N/A")

# ── 클러스터 태그 + 유사 동네 ──
try:
    centroids = load_district_centroids()
    derived = calc_derived_metrics(pop_time, card_agg, pop_agg, income_agg, selected_month)
    fm = build_feature_matrix(derived, card_agg, pop_demo, pop_time, selected_month)
    cl_labels, _, _ = run_clustering(fm)
    cl_type_map = classify_district_type(fm, cl_labels)

    if dc in cl_labels.index:
        cid = cl_labels[dc]
        cl_label = cl_type_map.get(cid, f"유형 {cid}")
        cl_color = get_cluster_color(cid)
        st.markdown(
            f'<span style="background:rgb({cl_color[0]},{cl_color[1]},{cl_color[2]});'
            f'color:white;padding:4px 14px;border-radius:14px;font-size:13px;font-weight:600;">'
            f'{cl_label}</span>',
            unsafe_allow_html=True,
        )

        # 유사 동네 Top 5
        similar = find_similar_districts(fm, dc, top_n=5)
        if not similar.empty:
            st.markdown("##### 🔗 유사 동네 Top 5")
            name_map = centroids.set_index("district_code")["name"].to_dict()

            sim_cols = st.columns(min(5, len(similar)))
            for i, (_, sim_row) in enumerate(similar.iterrows()):
                sim_dc = sim_row["district_code"]
                sim_name = name_map.get(sim_dc, sim_dc)
                sim_score = sim_row["similarity"]
                sim_cid = cl_labels.get(sim_dc, 0)
                sim_cl_label = cl_type_map.get(sim_cid, "")
                sim_color = get_cluster_color(sim_cid)

                with sim_cols[i]:
                    st.markdown(f"**{sim_name}**")
                    st.caption(f"유사도: {sim_score:.2f}")
                    st.markdown(
                        f'<span style="background:rgb({sim_color[0]},{sim_color[1]},{sim_color[2]});'
                        f'color:white;padding:2px 8px;border-radius:10px;font-size:10px;">'
                        f'{sim_cl_label}</span>',
                        unsafe_allow_html=True,
                    )

                    # 미니 레이더 차트
                    if sim_dc in fm.index and dc in fm.index:
                        target_vals = fm.loc[dc].values.tolist()
                        sim_vals = fm.loc[sim_dc].values.tolist()

                        # 정규화 (0~1)
                        fm_min = fm.min()
                        fm_max = fm.max()
                        fm_range = (fm_max - fm_min).replace(0, 1)
                        t_norm = ((fm.loc[dc] - fm_min) / fm_range).values.tolist()
                        s_norm = ((fm.loc[sim_dc] - fm_min) / fm_range).values.tolist()

                        short_labels = ["낮밤비", "방문", "HHI", "매출", "소득", "1위업종", "청년", "주말"]
                        fig_radar = go.Figure()
                        fig_radar.add_trace(go.Scatterpolar(
                            r=t_norm + [t_norm[0]],
                            theta=short_labels + [short_labels[0]],
                            fill="toself", name=f"{city} {district}",
                            line=dict(color="#6366F1", width=1),
                            fillcolor="rgba(99,102,241,0.15)",
                        ))
                        fig_radar.add_trace(go.Scatterpolar(
                            r=s_norm + [s_norm[0]],
                            theta=short_labels + [short_labels[0]],
                            fill="toself", name=sim_name,
                            line=dict(color="#EF553B", width=1),
                            fillcolor="rgba(239,85,59,0.15)",
                        ))
                        fig_radar.update_layout(
                            height=180,
                            margin=dict(l=20, r=20, t=10, b=10),
                            polar=dict(radialaxis=dict(visible=False, range=[0, 1])),
                            showlegend=False,
                        )
                        st.plotly_chart(fig_radar, use_container_width=True,
                                        key=f"sim_radar_{i}")
except Exception:
    pass  # 클러스터링 실패 시 기존 페이지 그대로 표시

st.divider()

# ── A. 소비 DNA ──
st.subheader("🛒 소비 DNA")
col_a1, col_a2 = st.columns(2)

with col_a1:
    if not card_district.empty:
        st.plotly_chart(
            spending_radar_chart(card_district.iloc[0], f"{district} 업종별 매출 비중"),
            use_container_width=True
        )
    else:
        st.info("카드매출 데이터 없음")

with col_a2:
    # 시간대별 매출 추이
    if not card_time_district.empty and "TIME_SLOT" in card_time_district.columns:
        import plotly.graph_objects as go
        from charts import TIME_SLOT_KOR
        time_order = ["T06", "T09", "T12", "T15", "T18", "T21", "T24"]
        ct = card_time_district.groupby("TIME_SLOT")[["FOOD_SALES", "COFFEE_SALES", "TOTAL_SALES"]].sum()
        ct = ct.reindex([t for t in time_order if t in ct.index]).fillna(0)
        labels = [TIME_SLOT_KOR.get(t, t) for t in ct.index]
        fig_sales = go.Figure()
        if "TOTAL_SALES" in ct.columns:
            fig_sales.add_trace(go.Bar(x=labels, y=ct["TOTAL_SALES"], name="전체", marker_color="#636EFA"))
        if "FOOD_SALES" in ct.columns:
            fig_sales.add_trace(go.Bar(x=labels, y=ct["FOOD_SALES"], name="식음료", marker_color="#EF553B"))
        if "COFFEE_SALES" in ct.columns:
            fig_sales.add_trace(go.Bar(x=labels, y=ct["COFFEE_SALES"], name="커피", marker_color="#00CC96"))
        fig_sales.update_layout(title=f"{district} 시간대별 매출", barmode="group", height=400)
        st.plotly_chart(fig_sales, use_container_width=True, key="sales_by_time")
    else:
        st.info("시간대별 매출 데이터 없음")

st.divider()

# ── B. 사람 흐름 ──
st.subheader("🚶 사람 흐름")
col_b1, col_b2 = st.columns(2)

with col_b1:
    if not pop_time_district.empty:
        st.plotly_chart(
            population_flow_chart(pop_time_district, f"{district} 시간대별 유동인구"),
            use_container_width=True, key="pop_flow"
        )
    else:
        st.info("유동인구 데이터 없음")

with col_b2:
    if not pop_demo_district.empty:
        st.plotly_chart(
            population_pyramid(pop_demo_district, f"{district} 인구 피라미드"),
            use_container_width=True, key="pop_pyramid"
        )
    else:
        st.info("인구 데이터 없음")

st.divider()

# ── C. 부동산 트렌드 ──
st.subheader("🏠 부동산 트렌드")
try:
    realestate = load_realestate()
    # BJD_CODE 앞 8자리로 매핑
    re_district = realestate[
        (realestate["BJD_CODE"].astype(str).str[:8] == dc) &
        (realestate["REGION_LEVEL"] == "emd")
    ]
    if not re_district.empty:
        st.plotly_chart(
            realestate_trend_chart(re_district, f"{district} 매매/전세 평단가 추이 (13년)"),
            use_container_width=True
        )
    else:
        # 시군구 레벨로 시도
        re_sgg = realestate[
            (realestate["SGG"] == city) &
            (realestate["REGION_LEVEL"] == "sgg")
        ]
        if not re_sgg.empty:
            st.plotly_chart(
                realestate_trend_chart(re_sgg, f"{city} (시군구 평균) 매매/전세 추이"),
                use_container_width=True
            )
        else:
            st.info(f"리치고 부동산 데이터 범위: 중구, 영등포구, 서초구 (이 동네의 아파트 시세 데이터 없음)")
except Exception:
    st.info("부동산 데이터를 로드할 수 없습니다.")

st.divider()

# ── D. 금융 건전성 ──
st.subheader("💰 금융 건전성")
col_d1, col_d2 = st.columns(2)

with col_d1:
    if not income_district.empty:
        st.plotly_chart(
            income_distribution_chart(income_district.iloc[0], f"{district} 소득 분포"),
            use_container_width=True
        )
    else:
        st.info("소득 데이터 없음")

with col_d2:
    if not income_district.empty:
        st.plotly_chart(
            job_donut_chart(income_district.iloc[0], f"{district} 직업군 분포"),
            use_container_width=True
        )
    else:
        st.info("직업 데이터 없음")

# Build page context for chat panel
try:
    _ctx_parts = [f"동네 프로파일 - {city} {district}, 기준: {selected_month_label}"]
    if not pop_district.empty:
        _ctx_total_pop = (pop_district["RESIDENTIAL_POPULATION"].values[0]
                          + pop_district["WORKING_POPULATION"].values[0]
                          + pop_district["VISITING_POPULATION"].values[0])
        _ctx_parts.append(f"총 유동인구: {_ctx_total_pop:,.0f}명")
    if not card_district.empty and "TOTAL_SALES" in card_district.columns:
        _ctx_sales = card_district["TOTAL_SALES"].values[0]
        if _ctx_sales > 1e8:
            _ctx_parts.append(f"월 카드매출: {_ctx_sales/1e8:,.1f}억원")
        else:
            _ctx_parts.append(f"월 카드매출: {_ctx_sales/1e4:,.0f}만원")
    if not income_district.empty and "AVERAGE_INCOME" in income_district.columns:
        _ctx_avg_income = income_district["AVERAGE_INCOME"].values[0]
        if pd.notna(_ctx_avg_income) and _ctx_avg_income > 0:
            _ctx_parts.append(f"평균소득: {_ctx_avg_income/1e4:,.0f}만원")
    if not income_district.empty and "total_customers" in income_district.columns:
        _ctx_customers = income_district["total_customers"].values[0]
        _ctx_parts.append(f"고객 수: {_ctx_customers:,.0f}명")
    page_context = ", ".join(_ctx_parts)
except Exception:
    page_context = f"동네 프로파일 - {city} {district}"

render_chat_panel(current_tab="동네 프로파일", selected_district=district, selected_month=str(selected_month), page_context=page_context)
