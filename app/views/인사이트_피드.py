"""
동네 엑스레이 — 인사이트 피드
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import (
    load_region_master, load_population_agg, load_card_sales_agg,
    load_card_sales_time, load_population_time, load_population_demo,
    load_income_agg, load_realestate, load_hotplace_monthly,
    run_query, AJD, SPH,
)
from charts import (
    spending_radar_chart, realestate_trend_chart,
    population_flow_chart, population_pyramid,
    income_distribution_chart, job_donut_chart,
    TIME_SLOT_KOR,
)
# chat_ui는 main.py에서 처리

def _container(**kwargs):
    try:
        return st.container(**kwargs)
    except TypeError:
        return st.container()

def _render_forecast_cards(pop_agg, card_agg, region_master):
    """🔮 3개월 전망 예측 카드"""
    import numpy as np

    st.markdown("### 🔮 3개월 전망")

    months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique())
    if len(months) < 3:
        st.caption("데이터 부족 (3개월 이상 필요)")
        return

    # 최근 3개월 vs 이전 3개월 방문인구 변화율로 성장/하락 예측
    recent_3 = months[-3:]
    prev_3 = months[-6:-3] if len(months) >= 6 else months[:3]

    pop_recent = pop_agg[pop_agg["STANDARD_YEAR_MONTH"].isin(recent_3)].groupby("DISTRICT_CODE").agg({
        "VISITING_POPULATION": "mean", "RESIDENTIAL_POPULATION": "mean",
        "WORKING_POPULATION": "mean"
    }).rename(columns={"VISITING_POPULATION": "visit_r", "RESIDENTIAL_POPULATION": "res_r", "WORKING_POPULATION": "work_r"})

    pop_prev = pop_agg[pop_agg["STANDARD_YEAR_MONTH"].isin(prev_3)].groupby("DISTRICT_CODE").agg({
        "VISITING_POPULATION": "mean"
    }).rename(columns={"VISITING_POPULATION": "visit_p"})

    merged = pop_recent.join(pop_prev, how="inner")
    merged["growth"] = ((merged["visit_r"] - merged["visit_p"]) / merged["visit_p"].replace(0, np.nan) * 100).fillna(0)

    # 카드매출 변화율
    card_recent = card_agg[card_agg["STANDARD_YEAR_MONTH"].isin(recent_3)]
    card_prev = card_agg[card_agg["STANDARD_YEAR_MONTH"].isin(prev_3)]
    if "TOTAL_SALES" in card_recent.columns:
        cr = card_recent.groupby("DISTRICT_CODE")["TOTAL_SALES"].mean()
        cp = card_prev.groupby("DISTRICT_CODE")["TOTAL_SALES"].mean()
        merged["sales_growth"] = ((cr - cp) / cp.replace(0, np.nan) * 100).fillna(0)
    else:
        merged["sales_growth"] = 0

    # 종합 점수
    merged["forecast_score"] = merged["growth"] * 0.6 + merged["sales_growth"] * 0.4

    # 이름 매핑
    name_map = region_master.set_index("district_code").apply(
        lambda r: f"{r['city_kor']} {r['district_kor']}", axis=1
    ).to_dict()
    merged["name"] = merged.index.map(name_map)

    # 상승 / 주의 / 하락 분류
    rising = merged[merged["forecast_score"] > 3].nlargest(5, "forecast_score")
    falling = merged[merged["forecast_score"] < -3].nsmallest(5, "forecast_score")
    neutral = merged[(merged["forecast_score"] >= -3) & (merged["forecast_score"] <= 3)].head(3)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**🔥 상승 예측**")
        for _, row in rising.iterrows():
            st.markdown(f"""<div style="background:rgba(239,68,68,0.1);padding:8px 12px;border-radius:8px;
                margin:4px 0;border-left:3px solid #EF4444;">
                <div style="font-size:13px;font-weight:600;">{row['name']}</div>
                <div style="font-size:11px;color:#EF4444;">+{row['forecast_score']:.1f}점 ↑</div>
                <div style="font-size:10px;color:#888;">방문 +{row['growth']:.1f}% · 매출 +{row['sales_growth']:.1f}%</div>
            </div>""", unsafe_allow_html=True)

    with c2:
        st.markdown("**⚡ 관찰 필요**")
        for _, row in neutral.iterrows():
            st.markdown(f"""<div style="background:rgba(245,158,11,0.1);padding:8px 12px;border-radius:8px;
                margin:4px 0;border-left:3px solid #F59E0B;">
                <div style="font-size:13px;font-weight:600;">{row['name']}</div>
                <div style="font-size:11px;color:#F59E0B;">{row['forecast_score']:+.1f}점</div>
                <div style="font-size:10px;color:#888;">방문 {row['growth']:+.1f}% · 매출 {row['sales_growth']:+.1f}%</div>
            </div>""", unsafe_allow_html=True)

    with c3:
        st.markdown("**📉 하락 예측**")
        for _, row in falling.iterrows():
            st.markdown(f"""<div style="background:rgba(59,130,246,0.1);padding:8px 12px;border-radius:8px;
                margin:4px 0;border-left:3px solid #3B82F6;">
                <div style="font-size:13px;font-weight:600;">{row['name']}</div>
                <div style="font-size:11px;color:#3B82F6;">{row['forecast_score']:.1f}점 ↓</div>
                <div style="font-size:10px;color:#888;">방문 {row['growth']:.1f}% · 매출 {row['sales_growth']:.1f}%</div>
            </div>""", unsafe_allow_html=True)

    # ── Cortex AI 심층 예측 (동네 선택) ──
    st.markdown("---")
    st.markdown("### 🧠 AI 심층 예측")
    if not rising.empty:
        _ai_options = {row["name"]: dc for dc, row in rising.iterrows()}
        _ai_selected = st.selectbox(
            "분석할 동네 선택", list(_ai_options.keys()), index=0, key="ai_deep_district"
        )
        top_dc = _ai_options[_ai_selected]
        top_name = _ai_selected

        try:
            from chat_ui import _cortex
            ts_df = pop_agg[pop_agg["DISTRICT_CODE"] == top_dc].groupby("STANDARD_YEAR_MONTH").agg({
                "RESIDENTIAL_POPULATION": "sum", "WORKING_POPULATION": "sum", "VISITING_POPULATION": "sum"
            }).reset_index()
            ts_df["TOTAL"] = ts_df["RESIDENTIAL_POPULATION"] + ts_df["WORKING_POPULATION"] + ts_df["VISITING_POPULATION"]
            ts_df = ts_df.sort_values("STANDARD_YEAR_MONTH")
            ts_str = ts_df[["STANDARD_YEAR_MONTH", "TOTAL"]].to_string(index=False)

            with st.expander(f"🔮 {top_name} — Cortex AI 3개월 예측 (클릭하여 보기)"):
                with st.spinner("Cortex 분석 중..."):
                    prompt = f"""{top_name}의 월별 총 유동인구 데이터입니다.

{ts_str}

위 데이터를 분석하여:
1. 트렌드 (상승/하락/정체)
2. 계절성 패턴
3. 향후 3개월 예측값 (표로)
4. 예측 근거
5. 리스크 요인

간결하게 표와 핵심만 답변하세요. 한국어로."""

                    ai_forecast = _cortex(prompt)
                    st.markdown(ai_forecast)
        except Exception as e:
            st.caption(f"AI 예측 오류: {e}")
    else:
        st.caption("상승 예측 동네가 없어 AI 심층 예측을 건너뜁니다.")

    # 렌탈 수요 예측
    st.markdown("---")
    st.markdown("### 📦 렌탈 수요 시그널")
    try:
        rental = run_query(f"""
            SELECT RENTAL_SUB_CATEGORY as ITEM,
                   SUM(CONTRACT_COUNT) as CONTRACTS
            FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS
            WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS)
            GROUP BY 1 ORDER BY CONTRACTS DESC LIMIT 5
        """)
        if not rental.empty:
            cols = st.columns(len(rental))
            for i, (_, row) in enumerate(rental.iterrows()):
                with cols[i]:
                    st.metric(row["ITEM"], f"{int(row['CONTRACTS']):,}건")
    except Exception:
        st.caption("렌탈 데이터 로드 오류")


def render():
    # ── CSS ──
    st.markdown("""<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 0 !important; }
    [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }
    .signal-header {
        font-size: 12px; font-weight: 700; padding: 8px 0 6px;
        border-bottom: 1px solid rgba(128,128,128,0.12); margin-bottom: 4px;
    }
    .kw-tag {
        display: inline-block; padding: 4px 10px; border-radius: 16px;
        font-size: 11px; font-weight: 500; margin: 2px 3px 8px 0;
        border: 1px solid rgba(128,128,128,0.2); background: rgba(128,128,128,0.06);
    }
    .detail-title-sub { font-size: 12px; opacity: 0.5; margin-bottom: 6px; }
    .detail-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    .detail-title .name { font-size: 18px; font-weight: 800; }
    .detail-title .change { font-size: 18px; font-weight: 800; }
    .detail-title .change.up { color: #f04452; }
    .detail-title .change.down { color: #3182f6; }
    .detail-title .date { font-size: 12px; opacity: 0.4; }
    </style>""", unsafe_allow_html=True)
    # ── 데이터 로드 ──
    region_master = load_region_master()
    pop_agg = load_population_agg()
    card_agg = load_card_sales_agg()
    hp = load_hotplace_monthly()

    # 예측 카드는 미래 예측 탭으로 이동됨

    data_districts = set(hp["DISTRICT_CODE"].unique())
    rm = region_master[region_master["district_code"].isin(data_districts)].copy()
    rm["label"] = rm["city_kor"] + " " + rm["district_kor"]
    district_options = rm.sort_values("label")["label"].tolist()

    if not district_options:
        st.error("데이터가 있는 법정동이 없습니다.")
        st.stop()

    WEIGHTS = {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15}

    def _hp_to_signal(row, months_ago=0):
        """parquet 행 → 기존 signal dict 형태로 변환"""
        m = str(row["STANDARD_YEAR_MONTH"])
        # 변동 원인 자동 생성
        reasons = []
        keywords = []
        sources = ["SPH 유동인구", "SPH 카드매출"]

        if abs(row["pop_chg"]) > 2:
            d = "증가" if row["pop_chg"] > 0 else "감소"
            reasons.append(f"총 유동인구가 전월 대비 {abs(row['pop_chg']):.1f}% {d}했어요.")
            keywords.append(f"유동인구 {d}")
        sub = []
        if abs(row.get("res_chg", 0)) > 3:
            sub.append(f"거주인구 {row['res_chg']:+.1f}%")
        if abs(row.get("work_chg", 0)) > 3:
            sub.append(f"직장인구 {row['work_chg']:+.1f}%")
        if abs(row["visiting_chg"]) > 3:
            sub.append(f"방문인구 {row['visiting_chg']:+.1f}%")
        if sub:
            reasons.append(f"세부적으로 {', '.join(sub)}의 변동이 있었어요.")
        if abs(row["sales_chg"]) > 2:
            d = "증가" if row["sales_chg"] > 0 else "감소"
            sv = row["total_sales"]
            sv_d = f"{sv/1e8:,.1f}억원" if sv > 1e8 else f"{sv/1e4:,.0f}만원"
            reasons.append(f"카드매출이 전월 대비 {abs(row['sales_chg']):.1f}% {d}하여 월 {sv_d} 규모예요.")
            keywords.append(f"소비 {d}")
        cafe_d = []
        if abs(row.get("coffee_chg", 0)) > 5:
            cafe_d.append(f"커피 매출 {row['coffee_chg']:+.1f}%")
        if abs(row.get("food_chg", 0)) > 5:
            cafe_d.append(f"식음료 매출 {row['food_chg']:+.1f}%")
        if cafe_d:
            reasons.append(f"특히 {', '.join(cafe_d)}로 상권 {'활성화' if row['cafe_chg'] > 0 else '위축'} 신호가 감지돼요.")
            if row.get("coffee_chg", 0) > 10:
                keywords.append("카페 트렌드")
        if abs(row["price_chg"]) > 2:
            d = "상승" if row["price_chg"] > 0 else "하락"
            reasons.append(f"매매 평단가가 {abs(row['price_chg']):.1f}% {d}하며 부동산 시장이 {'상승' if row['price_chg'] > 0 else '조정'} 국면이에요.")
            keywords.append(f"매매가 {d}")
            sources.append("리치고 부동산")
        if abs(row["install_chg"]) > 10:
            d = "증가" if row["install_chg"] > 0 else "감소"
            reasons.append(f"인터넷 신규설치가 {abs(row['install_chg']):.0f}% {d}하며 전입 수요가 변동하고 있어요.")
            keywords.append(f"전입 {d}")
            sources.append("아정당 신규설치")
        if row.get("visit_ratio", 0) > 40:
            reasons.append(f"방문인구 비중이 {row['visit_ratio']:.0f}%로 외부 유입이 활발한 상권이에요.")
            keywords.append("핫플 시그널")
        if not reasons:
            reasons.append("전반적인 지표가 소폭 변동했어요.")
            keywords.append("안정적")

        return {
            "dc": row["DISTRICT_CODE"],
            "name": row["name"],
            "city": row["city"],
            "month": row["STANDARD_YEAR_MONTH"],
            "month_label": f"{m[:4]}.{m[4:6]}",
            "months_ago": months_ago,
            "direction": row["direction"],
            "composite": row["hotplace_score"],
            "visiting_chg": row["visiting_chg"],
            "cafe_chg": row["cafe_chg"],
            "pop_chg": row["pop_chg"],
            "price_chg": row["price_chg"],
            "install_chg": row["install_chg"],
            "sales_chg": row["sales_chg"],
            "visit_ratio": row.get("visit_ratio", 0),
            "total_pop": row["total_pop"],
            "total_sales": row["total_sales"],
            "reasons": reasons,
            "keywords": keywords,
            "sources": list(dict.fromkeys(sources)),
            "weights": WEIGHTS,
        }

    def get_signals_for_month(hp_df, ym, top_n=3):
        """특정 월의 TOP/BOTTOM 시그널 추출"""
        month_data = hp_df[hp_df["STANDARD_YEAR_MONTH"] == ym].copy()
        if month_data.empty:
            return []
        month_data = month_data.sort_values("hotplace_score", ascending=False)
        top = month_data.head(top_n)
        bottom = month_data.tail(top_n)
        combined = pd.concat([top, bottom]).drop_duplicates(subset="DISTRICT_CODE")
        return [_hp_to_signal(row) for _, row in combined.iterrows()]

    if "selected_signal_idx" not in st.session_state:
        st.session_state.selected_signal_idx = 0
    if "my_neighborhood" not in st.session_state:
        st.session_state.my_neighborhood = district_options[0]

    # ── 데이터 준비 ──
    all_ym = sorted(hp["STANDARD_YEAR_MONTH"].unique(), reverse=True)
    ym_labels = [f"{str(m)[:4]}년 {int(str(m)[4:6])}월" for m in all_ym]
    total_records = len(hp)

    # 헤더 (날짜는 중간 패널로 이동)
    st.markdown(
        f'<div style="display:flex; align-items:center; gap:8px; padding:4px 0;">'
        f'<span style="color:#6366F1; font-weight:700; font-size:16px;">✦</span>'
        f'<span style="font-size:13px; font-weight:600; opacity:0.5;">'
        f'데이터 {total_records:,}건을 분석한 시그널</span></div>',
        unsafe_allow_html=True,
    )

    # ═══════════════════════════════════════
    col_left, col_mid, col_right = st.columns([3, 5, 4])

    # ─────────────────────────────────────
    # MIDDLE: 상세 패널 (1. 날짜 드롭다운 상단)
    # ─────────────────────────────────────
    with col_mid:
        # 동네 검색 + 날짜 같은 행
        mid_nb_col, mid_ym_col = st.columns([3, 2])
        with mid_ym_col:
            selected_ym_label = st.selectbox("기준 년월", ym_labels, index=0, label_visibility="collapsed")

    selected_ym = all_ym[ym_labels.index(selected_ym_label)]

    # 상위3+하위3 고정 상단 옵션
    month_hp_sorted = hp[hp["STANDARD_YEAR_MONTH"] == selected_ym].sort_values("hotplace_score", ascending=False)
    if not month_hp_sorted.empty:
        top3 = month_hp_sorted.head(3)
        bot3 = month_hp_sorted.tail(3)
        top_bot = pd.concat([top3, bot3]).drop_duplicates(subset="DISTRICT_CODE")
        top_bot_labels = [f"{r['name']}" for _, r in top_bot.iterrows()]
        rest_labels = [o for o in district_options if o not in top_bot_labels]
        mid_options = top_bot_labels + ["───────────"] + rest_labels
    else:
        mid_options = district_options

    with col_mid:
        with mid_nb_col:
            mid_district = st.selectbox("동네 검색", mid_options, index=0, label_visibility="collapsed", key="mid_district_sel")
            if mid_district == "───────────":
                mid_district = mid_options[0]

    # 선택된 월 시그널만 (해당 월만)
    signals = get_signals_for_month(hp, selected_ym)

    if not signals:
        with col_mid:
            st.info("해당 월에 시그널이 없습니다.")
        st.stop()

    # ─────────────────────────────────────
    # LEFT: 시그널 리스트 (2. 드롭다운 없이, 해당 월만)
    # ─────────────────────────────────────
    with col_left:
        filter_val = st.radio("필터", ["전체", "상승", "하락"], horizontal=True, label_visibility="collapsed")
        if filter_val == "상승":
            filtered = [s for s in signals if s["direction"] == "up"]
        elif filter_val == "하락":
            filtered = [s for s in signals if s["direction"] == "down"]
        else:
            filtered = list(signals)

        # 순위 계산
        for s in filtered:
            m_all = hp[hp["STANDARD_YEAR_MONTH"] == s["month"]].sort_values("hotplace_score", ascending=False)
            rank_list = list(m_all["DISTRICT_CODE"])
            total_d = len(rank_list)
            rank = rank_list.index(s["dc"]) + 1 if s["dc"] in rank_list else 0
            if rank <= 3:
                s["_rank"] = f"상위{rank}"
            elif rank > total_d - 3:
                s["_rank"] = f"하위{total_d - rank + 1}"
            else:
                s["_rank"] = f"{rank}/{total_d}"

        if "selected_signal_idx" not in st.session_state:
            st.session_state.selected_signal_idx = 0

        # HTML 카드 리스트 (컨테이너)
        for i, s in enumerate(filtered):
            is_sel = (i == st.session_state.selected_signal_idx)
            cp = "+" if s["direction"] == "up" else ""
            color = "#f04452" if s["direction"] == "up" else "#3182f6"
            dl = "상승" if s["direction"] == "up" else "하락"
            kw = s["keywords"][0] if s["keywords"] else ""
            bg = "rgba(99,102,241,0.12)" if is_sel else "transparent"
            bl = "3px solid #6366F1" if is_sel else "3px solid transparent"
            mark = "● " if is_sel else ""
            st.markdown(
                f'<div style="padding:6px 8px; background:{bg}; border-left:{bl}; border-radius:0 4px 4px 0; margin-bottom:3px;">'
                f'  <div style="display:flex; justify-content:space-between;">'
                f'    <span style="font-size:12px; font-weight:700;">{mark}{s["name"]}</span>'
                f'    <span style="font-size:9px; opacity:0.3;">{s["_rank"]}</span></div>'
                f'  <div style="font-size:11px; margin-top:2px;">'
                f'    <span style="color:{color};">{cp}{s["composite"]}점 {dl}</span>'
                f'    <span style="opacity:0.3;"> · {kw}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ─────────────────────────────────────
    # MIDDLE: 상세 패널 (계속)
    # ─────────────────────────────────────
    with col_mid:
        # 중간 동네 드롭다운에서 선택한 동네의 시그널 찾기
        mid_sel_row = rm[rm["label"] == mid_district].iloc[0] if mid_district in rm["label"].values else None
        mid_dc = mid_sel_row["district_code"] if mid_sel_row is not None else None

        # 선택 동네가 시그널에 있으면 해당 시그널, 없으면 전체 hp에서 조회
        sig = None
        if mid_dc:
            for s in signals:
                if s["dc"] == mid_dc:
                    sig = s
                    break
            if not sig:
                # 시그널 TOP에 없는 동네 → hp에서 직접 조회
                mid_hp = hp[(hp["DISTRICT_CODE"] == mid_dc) & (hp["STANDARD_YEAR_MONTH"] == selected_ym)]
                if not mid_hp.empty:
                    sig = _hp_to_signal(mid_hp.iloc[0])
        if not sig:
            sel_idx = min(st.session_state.selected_signal_idx, len(signals) - 1)
            sig = signals[sel_idx]
        chg_prefix = "+" if sig["direction"] == "up" else ""
        dir_text = "상승" if sig["direction"] == "up" else "하락"
        dir_cls = "up" if sig["direction"] == "up" else "down"
        short_name = sig["name"]
        main_kw = sig["keywords"][0] if sig["keywords"] else "지표 변동"
        m_year, m_mon = sig["month_label"][:4], sig["month_label"][5:]

        # 조사 처리
        last_char = main_kw[-1] if main_kw else ""
        has_batchim = last_char and (ord(last_char) - 0xAC00) % 28 > 0 if '\uAC00' <= last_char <= '\uD7A3' else False
        josa = "으로" if has_batchim else "로"
        st.markdown(f'<div class="detail-title-sub">{main_kw}{josa}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="detail-title">'
            f'  <span class="name">{short_name}</span>'
            f'  <span class="change {dir_cls}">{chg_prefix}{abs(sig["composite"])}점 {dir_text}</span>'
            f'  <span class="date">{m_year}년 {int(m_mon)}월</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 왜 올랐을까?
        why_title = "왜 올랐을까?" if sig["direction"] == "up" else "왜 떨어졌을까?"
        with _container(border=True):
            st.markdown(f"**{why_title}**")
            reasons_html = "".join(
                f'<li style="font-size:13px; line-height:1.7; opacity:0.75; margin-bottom:4px;">{r}</li>'
                for r in sig["reasons"]
            )
            st.markdown(f'<ul style="padding-left:18px; margin:6px 0 0;">{reasons_html}</ul>', unsafe_allow_html=True)

        st.markdown("")  # 불릿↔키워드 여백
        st.markdown("")
        st.markdown("")
        kw_html = "".join(f'<span class="kw-tag">{kw}</span>' for kw in sig["keywords"])
        st.markdown(kw_html, unsafe_allow_html=True)
        st.markdown("")  # 키워드 아래 여백

        # 상세 정보 (핫플 점수란? + 출처 + 점수 구성 통합)
        w = sig.get("weights", {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15})
        with st.expander("상세 정보", expanded=False):
            # 핫플 점수란?
            st.markdown(
                '<div style="font-size:11px; line-height:1.6; margin-bottom:8px;">'
                '<b style="color:#6366F1;">핫플 점수란?</b><br>'
                '5개 선행지표의 전월대비 변동률을 가중합하여 산출합니다.<br>'
                '공식: 방문인구(25%) + 카페매출(20%) + 유동인구(20%) + 매매가(20%) + 신규설치(15%)<br>'
                '누적 점수 = 100(기준) + 전체 월별 합산 | 연관 동네 = 같은 구 내 동네'
                '</div>',
                unsafe_allow_html=True,
            )
            # 출처
            st.markdown(f'<div style="font-size:11px; margin-bottom:8px;"><b style="color:#6366F1;">출처</b> ({len(sig["sources"])}개)<br>'
                + "<br>".join(f'{src} · {m_year}년 {int(m_mon)}월' for src in sig["sources"])
                + '</div>', unsafe_allow_html=True)
            # 점수 구성
            st.markdown('<div style="font-size:11px; margin-bottom:4px;"><b style="color:#6366F1;">점수 구성</b></div>', unsafe_allow_html=True)
            for label, chg, weight, score in [
                ("방문인구", sig["visiting_chg"], int(w["visiting"]*100), round(sig["visiting_chg"] * w["visiting"], 1)),
                ("카페·식음료", sig["cafe_chg"], int(w["cafe"]*100), round(sig["cafe_chg"] * w["cafe"], 1)),
                ("유동인구", sig["pop_chg"], int(w["young"]*100), round(sig["pop_chg"] * w["young"], 1)),
                ("매매가", sig["price_chg"], int(w["price"]*100), round(sig["price_chg"] * w["price"], 1)),
                ("신규설치", sig["install_chg"], int(w["install"]*100), round(sig["install_chg"] * w["install"], 1)),
            ]:
                bar_color = "#f04452" if score > 0 else "#3182f6"
                bar_width = min(abs(score) / max(abs(sig["composite"]), 1) * 100, 100)
                sp = "+" if score > 0 else ""
                cp = "+" if chg > 0 else ""
                st.markdown(
                    f'<div style="padding:3px 0;">'
                    f'  <div style="display:flex; justify-content:space-between; font-size:11px;">'
                    f'    <span>{label} ({weight}%)</span>'
                    f'    <span style="font-weight:700; color:{bar_color};">{sp}{score:.1f}점</span></div>'
                    f'  <div style="display:flex; align-items:center; gap:4px;">'
                    f'    <div style="flex:1; height:4px; border-radius:2px; background:rgba(128,128,128,0.1);">'
                    f'      <div style="width:{bar_width}%; height:100%; border-radius:2px; background:{bar_color};"></div></div>'
                    f'    <span style="font-size:9px; opacity:0.35;">{cp}{chg}%</span></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            sig_hp_all = hp[(hp["DISTRICT_CODE"] == sig["dc"]) & (hp["STANDARD_YEAR_MONTH"] <= sig["month"])].sort_values("STANDARD_YEAR_MONTH")
            mid_current = round(100 + sig_hp_all["hotplace_score"].sum(), 1)
            mid_prev = round(mid_current - sig["composite"], 1)
            total_color = "#f04452" if sig["composite"] > 0 else "#3182f6"
            total_prefix = "+" if sig["composite"] > 0 else ""
            st.markdown(
                f'<div style="padding:4px 0; border-top:1px solid rgba(128,128,128,0.1); margin-top:4px;">'
                f'  <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:800;">'
                f'    <span>종합</span><span style="color:{total_color};">{mid_current}점</span></div>'
                f'  <div style="font-size:9px; opacity:0.3; text-align:right;">{mid_prev}점 → {mid_current}점 ({total_prefix}{sig["composite"]}점)</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # 연관 동네 (같은 구 내 동네)
        st.markdown('<div style="font-size:13px; font-weight:800; margin-bottom:2px;">연관 동네</div>', unsafe_allow_html=True)
        st.markdown('<span style="font-size:10px; opacity:0.35;">같은 구 내 동네</span>', unsafe_allow_html=True)
        same_city = [s for s in signals if s["city"] == sig["city"] and s["dc"] != sig["dc"]]
        if same_city:
            for ri, rel in enumerate(same_city[:5]):
                rc = "#f04452" if rel["direction"] == "up" else "#3182f6"
                rp = "+" if rel["direction"] == "up" else ""
                rk = rel["keywords"][0] if rel["keywords"] else ""
                rel_hp_all = hp[(hp["DISTRICT_CODE"] == rel["dc"]) & (hp["STANDARD_YEAR_MONTH"] <= rel["month"])]
                rel_curr = round(100 + rel_hp_all["hotplace_score"].sum(), 1)
                st.markdown(
                    f'<div style="font-size:11px; padding:4px 0; border-bottom:1px solid rgba(128,128,128,0.06);">'
                    f'  <span style="font-weight:600;">{rel["name"]}</span>'
                    f'  <span style="font-weight:700;"> {rel_curr}점</span>'
                    f'  <span style="color:{rc}; font-weight:600;"> {rp}{rel["composite"]}점</span>'
                    f'  <span style="opacity:0.3;"> · {rk}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("같은 구의 다른 시그널이 없습니다.")

        # ── 내 동네 근처 시그널 ──
        st.divider()
        my_nb = st.session_state.my_neighborhood
        my_city = my_nb.split(" ")[0] if my_nb else ""
        my_short = my_nb.split(" ")[-1] if my_nb else ""
        my_dc = rm[rm["label"] == my_nb]["district_code"].values[0] if my_nb in rm["label"].values else ""
        # 근처 시그널은 중간 패널 기준월 사용 (내 동네 월은 아직 미정의)
        _nearby_ym = selected_ym
        same_city_hp = hp[(hp["city"] == my_city) & (hp["STANDARD_YEAR_MONTH"] == _nearby_ym)].sort_values("hotplace_score", ascending=False)
        my_row_hp = same_city_hp[same_city_hp["DISTRICT_CODE"] == my_dc]
        others_hp = same_city_hp[same_city_hp["DISTRICT_CODE"] != my_dc].head(3)
        nearby_rows = pd.concat([my_row_hp, others_hp])
        nearby = [_hp_to_signal(row) for _, row in nearby_rows.iterrows()]
        if nearby:
            st.markdown(f'<div style="font-size:13px; font-weight:800; margin-bottom:6px;">{my_short} 근처 시그널</div>', unsafe_allow_html=True)
            for r in nearby:
                rcolor = "#f04452" if r["direction"] == "up" else "#3182f6"
                rp = "+" if r["direction"] == "up" else ""
                rk = r["keywords"][0] if r["keywords"] else ""
                st.markdown(
                    f'<div style="font-size:11px; padding:4px 0; border-bottom:1px solid rgba(128,128,128,0.06);">'
                    f'  <span style="font-weight:600;">{r["name"]}</span>'
                    f'  <span style="color:{rcolor}; font-weight:600;"> {rp}{r["composite"]}점</span>'
                    f'  <span style="opacity:0.3;"> · {rk}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ─────────────────────────────────────
    # RIGHT: 내 동네 프로파일
    # ─────────────────────────────────────
    with col_right:
        st.markdown('<div style="font-size:14px; font-weight:700; margin-bottom:4px;">내 동네</div>', unsafe_allow_html=True)
        # 3. 동네 + 날짜 같은 행
        current_idx = district_options.index(st.session_state.my_neighborhood) if st.session_state.my_neighborhood in district_options else 0
        nb_col, ym_col = st.columns([3, 2])
        with nb_col:
            def _on_nb_change():
                st.session_state.my_neighborhood = st.session_state.my_nb_select
            st.selectbox("동네", district_options, index=current_idx, label_visibility="collapsed", key="my_nb_select", on_change=_on_nb_change)
        new_nb = st.session_state.my_nb_select if "my_nb_select" in st.session_state else st.session_state.my_neighborhood

        sel_row = rm[rm["label"] == new_nb].iloc[0]
        dc = sel_row["district_code"]
        city = sel_row["city_kor"]
        district = sel_row["district_kor"]

        all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
        my_ym_labels = [f"{str(m)[:4]}년 {int(str(m)[4:6])}월" for m in all_months]
        with ym_col:
            my_ym_label = st.selectbox("년월", my_ym_labels, index=0, label_visibility="collapsed", key="my_nb_month")
        latest_month = all_months[my_ym_labels.index(my_ym_label)]
        ym_idx = all_months.index(latest_month) if latest_month in all_months else 0
        prev_month = all_months[ym_idx + 1] if ym_idx + 1 < len(all_months) else None
        st.caption(f"{city} {district} · {my_ym_label}")
        st.caption("↑ 사이드바에서 '상권 분석'으로 이동")

        if not latest_month:
            st.stop()

        pop_d = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == latest_month)]
        card_d = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == latest_month)]
        pop_prev_d = pop_agg[(pop_agg["DISTRICT_CODE"] == dc) & (pop_agg["STANDARD_YEAR_MONTH"] == prev_month)] if prev_month else pd.DataFrame()
        card_prev_d = card_agg[(card_agg["DISTRICT_CODE"] == dc) & (card_agg["STANDARD_YEAR_MONTH"] == prev_month)] if prev_month else pd.DataFrame()

        try:
            income_agg_data = load_income_agg()
            income_d = income_agg_data[(income_agg_data["DISTRICT_CODE"] == dc) & (income_agg_data["STANDARD_YEAR_MONTH"] == latest_month)]
        except Exception:
            income_d = pd.DataFrame()

        # ── 탭 ──
        tab_summary, tab_spend, tab_people, tab_estate, tab_finance, tab_rental = st.tabs(
            ["요약", "소비", "인구", "부동산", "금융", "렌탈·인터넷"]
        )

        with tab_summary:
            # 프로파일 점수 — 누적 계산 (100 + 전월들 합산)
            my_hp_all = hp[(hp["DISTRICT_CODE"] == dc) & (hp["STANDARD_YEAR_MONTH"] <= latest_month)].sort_values("STANDARD_YEAR_MONTH")
            my_hp_curr = hp[(hp["DISTRICT_CODE"] == dc) & (hp["STANDARD_YEAR_MONTH"] == latest_month)]
            my_sig = [_hp_to_signal(row) for _, row in my_hp_curr.iterrows()] if not my_hp_curr.empty else []

            if my_sig:
                ls = my_sig[0]
                cumulative_score = round(100 + my_hp_all["hotplace_score"].sum(), 1)
                prev_score = round(cumulative_score - ls["composite"], 1)
                month_chg = ls["composite"]
                score_color = "#f04452" if month_chg > 0 else "#3182f6"
                score_prefix = "+" if month_chg > 0 else ""

                # 순위 계산
                month_all = hp[hp["STANDARD_YEAR_MONTH"] == latest_month].copy()
                month_all["cum"] = month_all["DISTRICT_CODE"].apply(
                    lambda d: 100 + hp[(hp["DISTRICT_CODE"] == d) & (hp["STANDARD_YEAR_MONTH"] <= latest_month)]["hotplace_score"].sum()
                )
                rank = int((month_all["cum"] > cumulative_score).sum() + 1)
                total_districts = len(month_all)

                chg_arrow = "▲" if month_chg > 0 else "▼" if month_chg < 0 else "―"
                st.markdown(
                    f'<div style="padding:4px 0;">'
                    f'  <div style="display:flex; justify-content:space-between; align-items:center;">'
                    f'    <span style="font-size:11px; opacity:0.5;">핫플 점수</span>'
                    f'    <span style="font-size:11px; opacity:0.5;">{total_districts}개 동네 중 {rank}위</span>'
                    f'  </div>'
                    f'  <div style="font-size:22px; font-weight:800;">{cumulative_score}점</div>'
                    f'  <div style="font-size:11px; color:{score_color};">'
                    f'    {chg_arrow} 전월대비 {score_prefix}{month_chg}점</div>'
                    f'  <div style="font-size:10px; opacity:0.35;">{prev_score}점 → {cumulative_score}점</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # 점수 추이 미니 차트
                # 전체 기간 추이 (x축 고정)
                all_hp_dc = hp[hp["DISTRICT_CODE"] == dc].sort_values("STANDARD_YEAR_MONTH")
                if len(all_hp_dc) > 1:
                    trend = all_hp_dc.copy()
                    trend["cum_score"] = 100 + trend["hotplace_score"].cumsum()
                    trend["label"] = trend["STANDARD_YEAR_MONTH"].astype(str).apply(lambda x: f"{x[2:4]}.{x[4:6]}")
                    curr_label = f"{str(latest_month)[2:4]}.{str(latest_month)[4:6]}"

                    fig_trend = go.Figure(go.Scatter(
                        x=trend["label"], y=trend["cum_score"],
                        mode="lines", line=dict(color="#6366F1", width=2),
                        fill="tozeroy", fillcolor="rgba(99,102,241,0.08)",
                        showlegend=False, name="",
                    ))
                    # 현재 월 포인트
                    curr_row = trend[trend["label"] == curr_label]
                    if not curr_row.empty:
                        fig_trend.add_trace(go.Scatter(
                            x=[curr_label], y=[curr_row["cum_score"].values[0]],
                            mode="markers", marker=dict(size=10, color="#f04452"),
                            showlegend=False, name="",
                        ))
                        fig_trend.add_vline(x=curr_label, line_dash="dot", line_color="rgba(240,68,82,0.3)")
                    fig_trend.update_layout(
                        height=130, margin=dict(l=0, r=0, t=5, b=5),
                        xaxis=dict(showgrid=False, tickfont=dict(size=7)),
                        yaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=7)),
                        hovermode="x unified", showlegend=False,
                    )
                    st.plotly_chart(fig_trend, use_container_width=True, key="my_trend")

                with st.expander("점수 구성 보기"):
                    lw = ls.get("weights", {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15})
                    for label, chg, weight, score in [
                        ("방문인구", ls["visiting_chg"], int(lw["visiting"]*100), round(ls["visiting_chg"] * lw["visiting"], 1)),
                        ("카페·식음료", ls["cafe_chg"], int(lw["cafe"]*100), round(ls["cafe_chg"] * lw["cafe"], 1)),
                        ("유동인구", ls["pop_chg"], int(lw["young"]*100), round(ls["pop_chg"] * lw["young"], 1)),
                        ("매매가", ls["price_chg"], int(lw["price"]*100), round(ls["price_chg"] * lw["price"], 1)),
                        ("신규설치", ls["install_chg"], int(lw["install"]*100), round(ls["install_chg"] * lw["install"], 1)),
                    ]:
                        bc = "#f04452" if score > 0 else "#3182f6"
                        bw = min(abs(score) / max(abs(ls["composite"]), 1) * 100, 100)
                        sp = "+" if score > 0 else ""
                        cp = "+" if chg > 0 else ""
                        st.markdown(
                            f'<div style="padding:3px 0;">'
                            f'  <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:2px;">'
                            f'    <span>{label} <span style="opacity:0.35;">({weight}%)</span></span>'
                            f'    <span style="font-weight:700; color:{bc};">{sp}{score}점</span></div>'
                            f'  <div style="display:flex; align-items:center; gap:4px;">'
                            f'    <div style="flex:1; height:3px; border-radius:2px; background:rgba(128,128,128,0.1);">'
                            f'      <div style="width:{bw}%; height:100%; border-radius:2px; background:{bc};"></div></div>'
                            f'    <span style="font-size:9px; opacity:0.35;">{cp}{chg}%</span></div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            if not pop_d.empty:
                total_curr = pop_d["RESIDENTIAL_POPULATION"].values[0] + pop_d["WORKING_POPULATION"].values[0] + pop_d["VISITING_POPULATION"].values[0]
                delta_str = None
                if not pop_prev_d.empty:
                    total_prev = pop_prev_d["RESIDENTIAL_POPULATION"].values[0] + pop_prev_d["WORKING_POPULATION"].values[0] + pop_prev_d["VISITING_POPULATION"].values[0]
                    if total_prev > 0:
                        delta_pct = (total_curr - total_prev) / total_prev * 100
                        delta_str = f"{total_curr - total_prev:+,.0f}명 ({delta_pct:+.1f}%)"
                st.metric("총 유동인구", f"{total_curr:,.0f}명", delta_str)

                st.caption("전월대비 변동률")
                r_cols = st.columns(3)
                for j, (lb, cn) in enumerate(zip(["거주", "직장", "방문"], ["RESIDENTIAL_POPULATION", "WORKING_POPULATION", "VISITING_POPULATION"])):
                    with r_cols[j]:
                        v = pop_d[cn].values[0]
                        d = None
                        if not pop_prev_d.empty:
                            pv = pop_prev_d[cn].values[0]
                            if pv > 0:
                                d = f"전월대비 {(v - pv) / pv * 100:+.1f}%"
                        st.metric(lb, f"{v:,.0f}", d)

            m_cols = st.columns(3)
            with m_cols[0]:
                if not card_d.empty and "TOTAL_SALES" in card_d.columns:
                    val = card_d["TOTAL_SALES"].values[0]
                    disp = f"{val/1e8:,.1f}억" if val > 1e8 else f"{val/1e4:,.0f}만"
                    d_s = None
                    if not card_prev_d.empty and "TOTAL_SALES" in card_prev_d.columns:
                        pv = card_prev_d["TOTAL_SALES"].values[0]
                        if pv > 0:
                            d_s = f"{(val - pv) / pv * 100:+.1f}%"
                    st.metric("카드매출", disp, d_s)
            with m_cols[1]:
                if not income_d.empty and "AVERAGE_INCOME" in income_d.columns:
                    avg = income_d["AVERAGE_INCOME"].values[0]
                    if pd.notna(avg) and avg > 0:
                        # 단위 자동 판별: 1억 이상이면 원 단위, 아니면 만원 단위
                        if avg > 100000000:  # 1억 이상 → 원 단위
                            st.metric("평균소득", f"{avg/1e4:,.0f}만원")
                        elif avg > 10000:  # 1만 이상 → 만원 단위
                            st.metric("평균소득", f"{avg:,.0f}만원")
                        else:  # 작은 값 → 원래 단위 그대로
                            st.metric("평균소득", f"{avg:,.0f}만원")
            with m_cols[2]:
                if not income_d.empty and "total_customers" in income_d.columns:
                    cust = income_d["total_customers"].values[0]
                    st.metric("고객수", f"{cust:,.0f}")

        with tab_spend:
            if not card_d.empty:
                fig = spending_radar_chart(card_d.iloc[0], f"{district} 소비 DNA")
                fig.update_layout(height=250, margin=dict(l=25, r=25, t=35, b=25))
                st.plotly_chart(fig, use_container_width=True, key="my_radar")
            try:
                card_time = load_card_sales_time()
                ct_d = card_time[(card_time["DISTRICT_CODE"] == dc) & (card_time["STANDARD_YEAR_MONTH"] == latest_month)]
                if not ct_d.empty and "TIME_SLOT" in ct_d.columns:
                    time_order = ["T06", "T09", "T12", "T15", "T18", "T21", "T24"]
                    ct_agg = ct_d.groupby("TIME_SLOT")[["FOOD_SALES", "COFFEE_SALES", "TOTAL_SALES"]].sum()
                    ct_agg = ct_agg.reindex([t for t in time_order if t in ct_agg.index]).fillna(0)
                    labels = [TIME_SLOT_KOR.get(t, t) for t in ct_agg.index]
                    fig_ct = go.Figure()
                    if "TOTAL_SALES" in ct_agg.columns:
                        fig_ct.add_trace(go.Bar(x=labels, y=ct_agg["TOTAL_SALES"], name="전체", marker_color="#636EFA"))
                    if "FOOD_SALES" in ct_agg.columns:
                        fig_ct.add_trace(go.Bar(x=labels, y=ct_agg["FOOD_SALES"], name="식음료", marker_color="#EF553B"))
                    if "COFFEE_SALES" in ct_agg.columns:
                        fig_ct.add_trace(go.Bar(x=labels, y=ct_agg["COFFEE_SALES"], name="커피", marker_color="#00CC96"))
                    fig_ct.update_layout(title="시간대별 카드매출", barmode="group", height=230,
                                        margin=dict(l=25, r=10, t=30, b=25),
                                        yaxis_title="매출(원)", xaxis_title="시간대")
                    st.caption("해당 동네의 시간대별 카드 결제 매출 분포 — 어떤 시간대에 소비가 활발한지 파악")
                    st.plotly_chart(fig_ct, use_container_width=True, key="my_sales_time")
            except Exception:
                pass

        with tab_people:
            try:
                pop_time = load_population_time()
                pt_d = pop_time[(pop_time["DISTRICT_CODE"] == dc) & (pop_time["STANDARD_YEAR_MONTH"] == latest_month)]
                if not pt_d.empty:
                    fig = population_flow_chart(pt_d, f"{district} 시간대별 유동인구")
                    fig.update_layout(height=250)
                    st.plotly_chart(fig, use_container_width=True, key="my_pop_flow")
                    st.caption("시간대별 거주·직장·방문 인구의 구성 변화 — 상권의 주요 활동 시간대 파악")
            except Exception:
                st.info("데이터 없음")
            try:
                pop_demo = load_population_demo()
                pd_d = pop_demo[(pop_demo["DISTRICT_CODE"] == dc) & (pop_demo["STANDARD_YEAR_MONTH"] == latest_month)]
                if not pd_d.empty:
                    pop_type = st.radio("인구 유형", ["전체", "거주", "직장", "방문"], horizontal=True, key="pyramid_type")
                    fig = population_pyramid(pd_d, f"{district} 인구 피라미드 ({pop_type})", pop_type=pop_type)
                    fig.update_layout(height=270)
                    st.plotly_chart(fig, use_container_width=True, key="my_pop_pyramid")
            except Exception:
                pass

        with tab_estate:
            try:
                re = load_realestate()
                re_d = re[(re["BJD_CODE"].astype(str).str[:8] == dc) & (re["REGION_LEVEL"] == "emd")]
                if not re_d.empty:
                    fig = realestate_trend_chart(re_d, f"{district} 매매/전세 추이")
                    fig.update_layout(height=270)
                    st.plotly_chart(fig, use_container_width=True, key="my_re")
                else:
                    re_sgg = re[(re["SGG"] == city) & (re["REGION_LEVEL"] == "sgg")]
                    if not re_sgg.empty:
                        fig = realestate_trend_chart(re_sgg, f"{city}(시군구) 추이")
                        fig.update_layout(height=270)
                        st.plotly_chart(fig, use_container_width=True, key="my_re_sgg")
                    else:
                        st.info(f"부동산 데이터 없음 (리치고: 중구·영등포구·서초구 아파트만 제공)")
            except Exception:
                st.info("부동산 데이터 로드 실패")

        with tab_finance:
            if not income_d.empty:
                fig = income_distribution_chart(income_d.iloc[0], f"{district} 소득 분포")
                fig.update_layout(height=250)
                st.plotly_chart(fig, use_container_width=True, key="my_income")
                fig = job_donut_chart(income_d.iloc[0], f"{district} 직업군 분포")
                fig.update_layout(height=250)
                st.plotly_chart(fig, use_container_width=True, key="my_job")
            else:
                st.info("소득 데이터 없음")

        with tab_rental:
            # 영유아/여성 비율
            try:
                from data_loader import load_richgo_fertility, load_ajd_new_install, AJD
                fertility = load_richgo_fertility()
                ft = fertility[fertility["SGG"] == city]
                if not ft.empty and "AGE_UNDER5_PER_FEMALE_20TO40" in ft.columns:
                    avg_ratio = ft["AGE_UNDER5_PER_FEMALE_20TO40"].mean()
                    st.metric("영유아/가임여성 비율", f"{avg_ratio:.3f}")
                    if avg_ratio > 0.15:
                        st.caption("💡 영유아 비율 높음 → 정수기/공기청정기 렌탈 수요 높을 가능성")
                    elif avg_ratio < 0.08:
                        st.caption("💡 영유아 비율 낮음 → 1인/2인 가구 중심")
                else:
                    st.caption("영유아 데이터: 중구·영등포구·서초구만 제공")
            except Exception:
                pass

            # 렌탈 트렌드
            try:
                rental = run_query(f"""
                    SELECT RENTAL_SUB_CATEGORY as ITEM,
                           SUM(CONTRACT_COUNT) as CONTRACTS
                    FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS
                    WHERE INSTALL_STATE LIKE '%서울%'
                      AND YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS)
                    GROUP BY 1 ORDER BY CONTRACTS DESC LIMIT 5
                """)
                if not rental.empty:
                    st.markdown("**서울 인기 렌탈 Top 5**")
                    for _, row in rental.iterrows():
                        st.markdown(f"- {row['ITEM']}: {int(row['CONTRACTS']):,}건")
                else:
                    st.caption("렌탈 데이터 없음")
            except Exception:
                st.caption("렌탈 데이터 로드 오류")

            # 인터넷 신규설치 추이
            try:
                install = run_query(f"""
                    SELECT YEAR_MONTH, SUM(OPEN_COUNT) as INSTALLS
                    FROM {AJD}.V05_REGIONAL_NEW_INSTALL
                    WHERE INSTALL_STATE LIKE '%서울%' AND INSTALL_CITY LIKE '%{city}%'
                    GROUP BY 1 ORDER BY 1 DESC LIMIT 6
                """)
                if not install.empty:
                    install_sorted = install.sort_values("YEAR_MONTH")
                    fig_inst = go.Figure(go.Scatter(
                        x=install_sorted["YEAR_MONTH"].astype(str),
                        y=install_sorted["INSTALLS"],
                        mode='lines+markers', line=dict(color='#6366F1', width=2),
                        fill='tozeroy', fillcolor='rgba(99,102,241,0.1)',
                        name='신규설치'
                    ))
                    fig_inst.update_layout(title=f"{city} 인터넷 신규설치 추이", height=220,
                                           yaxis_title="건수")
                    st.plotly_chart(fig_inst, use_container_width=True, key="my_install")
            except Exception:
                st.caption("인터넷 설치 데이터 오류")

