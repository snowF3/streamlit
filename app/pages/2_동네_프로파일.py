"""
동네 프로파일 — 토스 스타일
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_region_master, load_card_sales_agg, load_card_sales_time,
    load_population_agg, load_population_time, load_population_demo,
    load_income_agg, load_realestate, load_hotplace_monthly,
)
from charts import (
    spending_radar_chart, population_flow_chart, population_pyramid,
    realestate_trend_chart, income_distribution_chart, job_donut_chart,
    TIME_SLOT_KOR,
)
from chat_ui import render_chat_panel

# ── CSS ──
st.markdown("""<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 14px !important; }
[data-testid="stMetricValue"] { font-size: 20px !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; }
[data-testid="stMetricDelta"] { font-size: 11px !important; }
h2, h3 { font-size: 15px !important; }
</style>""", unsafe_allow_html=True)

# ── 데이터 로드 ──
try:
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
region_with_data["label"] = region_with_data["city_kor"] + " " + region_with_data["district_kor"]
options = region_with_data.sort_values("label")["label"].tolist()

if not options:
    st.error("데이터가 있는 법정동이 없습니다.")
    st.stop()

# 피드에서 선택한 동네 자동 반영
default_idx = 0
if "my_neighborhood" in st.session_state and st.session_state.my_neighborhood in options:
    default_idx = options.index(st.session_state.my_neighborhood)

all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
ym_labels = [f"{str(m)[:4]}년 {int(str(m)[4:6])}월" for m in all_months]

if "profile_ym_idx" not in st.session_state:
    st.session_state.profile_ym_idx = 0
if "p_ym_sel" not in st.session_state:
    st.session_state.p_ym_sel = ym_labels[0]

# ── 헤더 ──
h_nb, h_prev, h_ym, h_next = st.columns([4, 0.5, 2, 0.5])
with h_nb:
    selected = st.selectbox("동네", options, index=default_idx, label_visibility="collapsed")
with h_prev:
    if st.button("◀", key="p_prev", use_container_width=True, disabled=st.session_state.profile_ym_idx >= len(all_months) - 1):
        st.session_state.profile_ym_idx += 1
        st.session_state.p_ym_sel = ym_labels[st.session_state.profile_ym_idx]
        st.rerun()
with h_ym:
    def _on_p_ym():
        st.session_state.profile_ym_idx = ym_labels.index(st.session_state.p_ym_sel)
    st.selectbox("년월", ym_labels, key="p_ym_sel", label_visibility="collapsed", on_change=_on_p_ym)
    st.session_state.profile_ym_idx = ym_labels.index(st.session_state.p_ym_sel)
with h_next:
    if st.button("▶", key="p_next", use_container_width=True, disabled=st.session_state.profile_ym_idx <= 0):
        st.session_state.profile_ym_idx -= 1
        st.session_state.p_ym_sel = ym_labels[st.session_state.profile_ym_idx]
        st.rerun()

selected_month = all_months[st.session_state.profile_ym_idx]

sel_row = region_with_data[region_with_data["label"] == selected].iloc[0]
dc = sel_row["district_code"]
city = sel_row["city_kor"]
district = sel_row["district_kor"]

# ── 구 평균 계산 ──
city_dcs = region_with_data[region_with_data["city_kor"] == city]["district_code"].tolist()
pop_city = pop_agg[(pop_agg["DISTRICT_CODE"].isin(city_dcs)) & (pop_agg["STANDARD_YEAR_MONTH"] == selected_month)]
card_city = card_agg[(card_agg["DISTRICT_CODE"].isin(city_dcs)) & (card_agg["STANDARD_YEAR_MONTH"] == selected_month)]

# ── 데이터 필터 ──
pop_d = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == selected_month)]
card_d = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == selected_month)]
prev_month = all_months[st.session_state.profile_ym_idx + 1] if st.session_state.profile_ym_idx + 1 < len(all_months) else None
pop_prev = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == prev_month)] if prev_month else pd.DataFrame()
card_prev = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == prev_month)] if prev_month else pd.DataFrame()

try:
    income_d = income_agg[(income_agg["DISTRICT_CODE"] == dc) & (income_agg["STANDARD_YEAR_MONTH"] == selected_month)]
except Exception:
    income_d = pd.DataFrame()

# ═══════════════════════════════════════
# 핫플 점수 + 추이
# ═══════════════════════════════════════
hp_all = hp[(hp["DISTRICT_CODE"] == dc)].sort_values("STANDARD_YEAR_MONTH")
hp_until = hp_all[hp_all["STANDARD_YEAR_MONTH"] <= selected_month]

if not hp_until.empty:
    hp_until = hp_until.copy()
    hp_until["cum_score"] = 100 + hp_until["hotplace_score"].cumsum()
    cum_score = round(hp_until["cum_score"].iloc[-1], 1)
    month_chg = hp_until["hotplace_score"].iloc[-1]
    prev_sc = round(cum_score - month_chg, 1)

    # 순위
    m_all = hp[hp["STANDARD_YEAR_MONTH"] == selected_month].copy()
    m_all["cum"] = m_all["DISTRICT_CODE"].apply(
        lambda d: round(100 + hp[(hp["DISTRICT_CODE"] == d) & (hp["STANDARD_YEAR_MONTH"] <= selected_month)]["hotplace_score"].sum(), 1)
    )
    rank = int((m_all["cum"] > cum_score).sum() + 1)
    total_d = len(m_all)

    sc_color = "#f04452" if month_chg > 0 else "#3182f6"
    sc_pre = "+" if month_chg > 0 else ""

    col_score, col_chart = st.columns([1, 2])
    with col_score:
        st.markdown(
            f'<div style="padding:4px 0;">'
            f'  <div style="display:flex; justify-content:space-between;">'
            f'    <span style="font-size:20px; font-weight:800;">{city} {district}</span>'
            f'    <span style="font-size:11px; opacity:0.4;">{total_d}개 중 {rank}위</span></div>'
            f'  <div style="font-size:28px; font-weight:800; margin:4px 0;">{cum_score}점</div>'
            f'  <div style="font-size:11px; color:{sc_color};">'
            f'    전월대비 {sc_pre}{month_chg}점 ({prev_sc}점 → {cum_score}점)</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        WEIGHTS = {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15}
        cur_hp = hp_until.iloc[-1]
        with st.expander("점수 구성"):
            for lb, cn, wk in [
                ("방문인구", "visiting_chg", "visiting"), ("카페·식음료", "cafe_chg", "cafe"),
                ("유동인구", "pop_chg", "young"), ("매매가", "price_chg", "price"),
                ("신규설치", "install_chg", "install"),
            ]:
                chg = cur_hp[cn]; w = WEIGHTS[wk]; s = round(chg * w, 1)
                bc = "#f04452" if s > 0 else "#3182f6"
                bw = min(abs(s) / max(abs(month_chg), 1) * 100, 100)
                st.markdown(
                    f'<div style="padding:2px 0;">'
                    f'  <div style="display:flex; justify-content:space-between; font-size:11px;">'
                    f'    <span>{lb} ({int(w*100)}%)</span>'
                    f'    <span style="font-weight:700; color:{bc};">{"+" if s>0 else ""}{s}점</span></div>'
                    f'  <div style="height:3px; border-radius:2px; background:rgba(128,128,128,0.1);">'
                    f'    <div style="width:{bw}%; height:100%; border-radius:2px; background:{bc};"></div></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with col_chart:
        trend = hp_all.copy()
        trend["cum_score"] = 100 + trend["hotplace_score"].cumsum()
        trend["label"] = trend["STANDARD_YEAR_MONTH"].astype(str).apply(lambda x: f"{x[2:4]}.{x[4:6]}")
        curr_label = f"{str(selected_month)[2:4]}.{str(selected_month)[4:6]}"
        fig = go.Figure(go.Scatter(
            x=trend["label"], y=trend["cum_score"],
            mode="lines", line=dict(color="#6366F1", width=2),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.06)",
        ))
        cr = trend[trend["label"] == curr_label]
        if not cr.empty:
            fig.add_trace(go.Scatter(x=[curr_label], y=[cr["cum_score"].values[0]],
                mode="markers", marker=dict(size=10, color="#f04452"), showlegend=False))
            fig.add_vline(x=curr_label, line_dash="dot", line_color="rgba(240,68,82,0.3)")
        fig.update_layout(height=200, margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, tickfont=dict(size=8)),
            yaxis=dict(showgrid=False, tickfont=dict(size=9)), showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key="hp_trend")

# ═══════════════════════════════════════
# 요약 지표 (전월대비 + 구 평균 대비)
# ═══════════════════════════════════════
with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if not pop_d.empty:
            tp = pop_d["RESIDENTIAL_POPULATION"].values[0] + pop_d["WORKING_POPULATION"].values[0] + pop_d["VISITING_POPULATION"].values[0]
            d = None
            if not pop_prev.empty:
                pp = pop_prev["RESIDENTIAL_POPULATION"].values[0] + pop_prev["WORKING_POPULATION"].values[0] + pop_prev["VISITING_POPULATION"].values[0]
                if pp > 0: d = f"{(tp-pp)/pp*100:+.1f}%"
            st.metric("유동인구", f"{tp:,.0f}", d)
            if not pop_city.empty:
                city_avg = (pop_city["RESIDENTIAL_POPULATION"] + pop_city["WORKING_POPULATION"] + pop_city["VISITING_POPULATION"]).mean()
                if city_avg > 0:
                    vs = (tp - city_avg) / city_avg * 100
                    vc = "#f04452" if vs > 0 else "#3182f6"
                    st.markdown(f'<div style="font-size:10px; color:{vc};">{city} 평균 대비 {vs:+.0f}%</div>', unsafe_allow_html=True)
    with c2:
        if not card_d.empty and "TOTAL_SALES" in card_d.columns:
            v = card_d["TOTAL_SALES"].values[0]
            disp = f"{v/1e8:,.1f}억" if v > 1e8 else f"{v/1e4:,.0f}만"
            d = None
            if not card_prev.empty and "TOTAL_SALES" in card_prev.columns:
                pv = card_prev["TOTAL_SALES"].values[0]
                if pv > 0: d = f"{(v-pv)/pv*100:+.1f}%"
            st.metric("카드매출", disp, d)
            if not card_city.empty and "TOTAL_SALES" in card_city.columns:
                ca = card_city["TOTAL_SALES"].mean()
                if ca > 0:
                    vs = (v - ca) / ca * 100
                    vc = "#f04452" if vs > 0 else "#3182f6"
                    st.markdown(f'<div style="font-size:10px; color:{vc};">{city} 평균 대비 {vs:+.0f}%</div>', unsafe_allow_html=True)
    with c3:
        if not income_d.empty and "AVERAGE_INCOME" in income_d.columns:
            avg = income_d["AVERAGE_INCOME"].values[0]
            if pd.notna(avg) and avg > 0:
                st.metric("평균소득", f"{avg/1e4:,.0f}만")
    with c4:
        if not income_d.empty and "total_customers" in income_d.columns:
            st.metric("고객수", f"{income_d['total_customers'].values[0]:,.0f}")

# ═══════════════════════════════════════
# 소비 DNA
# ═══════════════════════════════════════
with st.container(border=True):
    st.markdown('<div style="font-size:15px; font-weight:700; margin-bottom:4px;">소비 DNA</div>', unsafe_allow_html=True)
    ca1, ca2 = st.columns(2)
    with ca1:
        if not card_d.empty:
            fig = spending_radar_chart(card_d.iloc[0], f"{district} 업종별 매출")
            fig.update_layout(height=280, margin=dict(l=30, r=30, t=30, b=30))
            st.plotly_chart(fig, use_container_width=True, key="radar")
    with ca2:
        try:
            ct = load_card_sales_time()
            ct_d = ct[(ct["DISTRICT_CODE"] == dc) & (ct["STANDARD_YEAR_MONTH"] == selected_month)]
            if not ct_d.empty and "TIME_SLOT" in ct_d.columns:
                time_order = ["T06", "T09", "T12", "T15", "T18", "T21", "T24"]
                agg = ct_d.groupby("TIME_SLOT")[["FOOD_SALES", "COFFEE_SALES", "TOTAL_SALES"]].sum()
                agg = agg.reindex([t for t in time_order if t in agg.index]).fillna(0)
                labels = [TIME_SLOT_KOR.get(t, t) for t in agg.index]
                fig = go.Figure()
                fig.add_trace(go.Bar(x=labels, y=agg["TOTAL_SALES"], name="전체", marker_color="#6366F1"))
                if "FOOD_SALES" in agg.columns:
                    fig.add_trace(go.Bar(x=labels, y=agg["FOOD_SALES"], name="식음료", marker_color="#EF553B"))
                if "COFFEE_SALES" in agg.columns:
                    fig.add_trace(go.Bar(x=labels, y=agg["COFFEE_SALES"], name="커피", marker_color="#00CC96"))
                fig.update_layout(title="시간대별 매출", barmode="group", height=280, margin=dict(l=30, r=10, t=30, b=30))
                st.plotly_chart(fig, use_container_width=True, key="sales_time")
        except Exception:
            pass

# ═══════════════════════════════════════
# 사람 흐름
# ═══════════════════════════════════════
with st.container(border=True):
    st.markdown('<div style="font-size:15px; font-weight:700; margin-bottom:4px;">사람 흐름</div>', unsafe_allow_html=True)
    cb1, cb2 = st.columns(2)
    with cb1:
        try:
            pt = load_population_time()
            pt_d = pt[(pt["DISTRICT_CODE"] == dc) & (pt["STANDARD_YEAR_MONTH"] == selected_month)]
            if not pt_d.empty:
                fig = population_flow_chart(pt_d, f"{district} 시간대별 유동인구")
                fig.update_layout(height=280)
                st.plotly_chart(fig, use_container_width=True, key="pop_flow")
        except Exception:
            st.info("데이터 없음")
    with cb2:
        try:
            pd_data = load_population_demo()
            pd_d = pd_data[(pd_data["DISTRICT_CODE"] == dc) & (pd_data["STANDARD_YEAR_MONTH"] == selected_month)]
            if not pd_d.empty:
                fig = population_pyramid(pd_d, f"{district} 인구 피라미드")
                fig.update_layout(height=280)
                st.plotly_chart(fig, use_container_width=True, key="pop_pyramid")
        except Exception:
            pass

# ═══════════════════════════════════════
# 부동산 트렌드
# ═══════════════════════════════════════
with st.container(border=True):
    st.markdown('<div style="font-size:15px; font-weight:700; margin-bottom:4px;">부동산 트렌드</div>', unsafe_allow_html=True)
    try:
        re = load_realestate()
        re_d = re[(re["BJD_CODE"].astype(str).str[:8] == dc) & (re["REGION_LEVEL"] == "emd")]
        if not re_d.empty:
            fig = realestate_trend_chart(re_d, f"{district} 매매/전세 평단가 추이")
            fig.update_layout(height=280)
            st.plotly_chart(fig, use_container_width=True, key="re_trend")
        else:
            re_sgg = re[(re["SGG"] == city) & (re["REGION_LEVEL"] == "sgg")]
            if not re_sgg.empty:
                fig = realestate_trend_chart(re_sgg, f"{city} (시군구) 매매/전세 추이")
                fig.update_layout(height=280)
                st.plotly_chart(fig, use_container_width=True, key="re_sgg")
            else:
                st.info("부동산 데이터 없음")
    except Exception:
        st.info("부동산 데이터 로드 실패")

# ═══════════════════════════════════════
# 금융 건전성
# ═══════════════════════════════════════
with st.container(border=True):
    st.markdown('<div style="font-size:15px; font-weight:700; margin-bottom:4px;">금융 건전성</div>', unsafe_allow_html=True)
    if not income_d.empty:
        cd1, cd2 = st.columns(2)
        with cd1:
            fig = income_distribution_chart(income_d.iloc[0], f"{district} 소득 분포")
            fig.update_layout(height=280)
            st.plotly_chart(fig, use_container_width=True, key="income")
        with cd2:
            fig = job_donut_chart(income_d.iloc[0], f"{district} 직업군 분포")
            fig.update_layout(height=280)
            st.plotly_chart(fig, use_container_width=True, key="job")
    else:
        st.info("소득 데이터 없음")

# ── 채팅 ──
page_context = f"동네 프로파일 - {city} {district}"
render_chat_panel(current_tab="동네 프로파일", selected_district=district, selected_month=str(selected_month), page_context=page_context)
