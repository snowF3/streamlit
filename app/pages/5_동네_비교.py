"""
탭 5: 동네 비교 — 2~3개 동네 나란히 비교
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_region_master, load_card_sales_agg, load_population_agg,
    load_income_agg
)
from charts import CATEGORY_KOR
from chat_ui import get_chat_layout

st.set_page_config(page_title="동네 비교", page_icon="⚖️", layout="wide")
st.title("⚖️ 동네 비교")

content_col = get_chat_layout(page_context="동네 비교")

with content_col:

    # ── 데이터 로드 ──
    try:
        region_master = load_region_master()
        card_agg = load_card_sales_agg()
        pop_agg = load_population_agg()
        income_agg = load_income_agg()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    # 데이터 있는 법정동만
    data_districts = set(pop_agg["DISTRICT_CODE"].unique())
    region_with_data = region_master[region_master["district_code"].isin(data_districts)].copy()
    region_with_data["label"] = region_with_data["city_kor"] + " " + region_with_data["district_kor"]
    options = region_with_data.sort_values("label")["label"].tolist()

    # ── 기준 년월 선택 ──
    all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
    month_labels = [f"{str(m)[:4]}년 {str(m)[4:6]}월" for m in all_months]
    selected_month_label = st.sidebar.selectbox("기준 년월", month_labels, index=0)
    selected_month = all_months[month_labels.index(selected_month_label)]

    # ── 동네 선택 (최대 3개) ──
    selected = st.multiselect("비교할 동네 선택 (최대 3개)", options, max_selections=3)

    if len(selected) < 2:
        st.info("2~3개 동네를 선택해주세요.")
        st.stop()

    st.caption(f"기준: {selected_month_label}")

    # 선택된 동네 코드
    selected_codes = []
    for s in selected:
        row = region_with_data[region_with_data["label"] == s].iloc[0]
        selected_codes.append(row["district_code"])

    # 선택된 년월 기준 데이터
    latest_card = selected_month
    latest_pop = selected_month
    latest_income = selected_month

    # ── 비교 테이블 ──
    st.subheader("📊 핵심 지표 비교")

    compare_data = []
    for i, dc in enumerate(selected_codes):
        row = {"동네": selected[i]}

        # 유동인구
        pop = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == latest_pop)]
        if not pop.empty:
            row["거주인구"] = int(pop["RESIDENTIAL_POPULATION"].values[0])
            row["직장인구"] = int(pop["WORKING_POPULATION"].values[0])
            row["방문인구"] = int(pop["VISITING_POPULATION"].values[0])
            row["총 유동인구"] = row["거주인구"] + row["직장인구"] + row["방문인구"]

        # 카드매출
        card = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == latest_card)]
        if not card.empty and "TOTAL_SALES" in card.columns:
            row["월 카드매출(억)"] = round(card["TOTAL_SALES"].values[0] / 1e8, 1)

        # 소득
        inc = income_agg[(income_agg["DISTRICT_CODE"] == dc) & (income_agg["STANDARD_YEAR_MONTH"] == latest_income)]
        if not inc.empty:
            if "AVERAGE_INCOME" in inc.columns and pd.notna(inc["AVERAGE_INCOME"].values[0]):
                row["평균소득(만원)"] = int(inc["AVERAGE_INCOME"].values[0] / 1e4)
            if "AVERAGE_SCORE" in inc.columns and pd.notna(inc["AVERAGE_SCORE"].values[0]):
                row["신용점수"] = int(inc["AVERAGE_SCORE"].values[0])
            if "total_customers" in inc.columns:
                row["고객수"] = int(inc["total_customers"].values[0])

        compare_data.append(row)

    compare_df = pd.DataFrame(compare_data).set_index("동네").T
    st.dataframe(compare_df, use_container_width=True)

    # ── 소비 패턴 비교 레이더 ──
    st.divider()
    st.subheader("🛒 소비 패턴 비교")

    categories = [k for k in CATEGORY_KOR.keys() if k != "TOTAL"]
    labels = [CATEGORY_KOR[k] for k in categories]

    fig = go.Figure()
    colors = ["#636EFA", "#EF553B", "#00CC96"]

    for i, dc in enumerate(selected_codes):
        card = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == latest_card)]
        if card.empty:
            continue

        values = []
        for cat in categories:
            col = f"{cat}_SALES"
            if col in card.columns:
                values.append(float(card[col].values[0]) if pd.notna(card[col].values[0]) else 0)
            else:
                values.append(0)

        total = sum(values)
        ratios = [v / total * 100 if total > 0 else 0 for v in values]

        fig.add_trace(go.Scatterpolar(
            r=ratios + [ratios[0]],
            theta=labels + [labels[0]],
            fill='toself',
            name=selected[i],
            fillcolor=f"rgba({int(colors[i][1:3], 16)},{int(colors[i][3:5], 16)},{int(colors[i][5:7], 16)},0.15)",
            line=dict(color=colors[i])
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, showticklabels=False)),
        height=500,
        title="업종별 매출 비중 비교 (%)"
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 유동인구 비교 바 차트 ──
    st.divider()
    st.subheader("🚶 유동인구 구성 비교")

    pop_compare = []
    for i, dc in enumerate(selected_codes):
        pop = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == latest_pop)]
        if not pop.empty:
            pop_compare.append({
                "동네": selected[i],
                "거주인구": pop["RESIDENTIAL_POPULATION"].values[0],
                "직장인구": pop["WORKING_POPULATION"].values[0],
                "방문인구": pop["VISITING_POPULATION"].values[0],
            })

    if pop_compare:
        pop_df = pd.DataFrame(pop_compare)
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=pop_df["동네"], y=pop_df["거주인구"], name="거주인구", marker_color="#636EFA"))
        fig2.add_trace(go.Bar(x=pop_df["동네"], y=pop_df["직장인구"], name="직장인구", marker_color="#EF553B"))
        fig2.add_trace(go.Bar(x=pop_df["동네"], y=pop_df["방문인구"], name="방문인구", marker_color="#00CC96"))
        fig2.update_layout(barmode="group", height=400, title="유동인구 구성 비교")
        st.plotly_chart(fig2, use_container_width=True)

