"""
인사이트 피드 — 토스증권 스타일 3컬럼 시그널 대시보드
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import (
    load_region_master, load_population_agg, load_card_sales_agg,
    load_card_sales_time, load_population_time, load_population_demo,
    load_income_agg, load_realestate, load_hotplace_monthly,
)
from charts import (
    spending_radar_chart, realestate_trend_chart,
    population_flow_chart, population_pyramid,
    income_distribution_chart, job_donut_chart,
    TIME_SLOT_KOR,
)
from chat_ui import render_chat_panel

# ── CSS ──
st.markdown("""<style>
/* 전체 패딩 축소 */
.block-container { padding-top: 3.5rem !important; padding-bottom: 0 !important; }
[data-testid="stVerticalBlock"] { gap: 0.4rem !important; }
[data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
/* 왼쪽 컬럼 간격 제거 */
[data-testid="stColumn"]:first-child [data-testid="stVerticalBlock"] { gap: 0 !important; }
/* 투명 버튼 */
[data-testid="stBaseButton-tertiary"] {
    margin: 0 !important; position: relative; z-index: 1;
    margin-top: -36px !important; height: 36px !important;
}
[data-testid="stBaseButton-tertiary"] button {
    min-height: 36px !important; height: 36px !important;
    padding: 0 !important; opacity: 0 !important; cursor: pointer !important;
}
/* 시그널 카드 hover */
.sig-card { transition: background 0.15s; border-radius: 0 6px 6px 0; }
.sig-card:hover { background: rgba(128,128,128,0.06) !important; }
.signal-header {
    font-size: 12px; font-weight: 700; padding: 8px 0 6px;
    border-bottom: 1px solid rgba(128,128,128,0.12); margin-bottom: 14px;
}
.kw-tag {
    display: inline-block; padding: 4px 10px; border-radius: 16px;
    font-size: 11px; font-weight: 500; margin: 2px 3px 2px 0;
    border: 1px solid rgba(128,128,128,0.2); background: rgba(128,128,128,0.06);
}
.detail-title-sub { font-size: 12px; opacity: 0.5; margin-bottom: 1px; }
.detail-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.detail-title .name { font-size: 18px; font-weight: 800; }
.detail-title .change { font-size: 18px; font-weight: 800; }
.detail-title .change.up { color: #f04452; }
.detail-title .change.down { color: #3182f6; }
.detail-title .date { font-size: 12px; opacity: 0.4; }
/* 오른쪽 내 동네 글씨 축소 */
[data-testid="stColumn"]:last-child [data-testid="stMetricValue"] { font-size: 18px !important; }
[data-testid="stColumn"]:last-child [data-testid="stMetricLabel"] { font-size: 10px !important; }
[data-testid="stColumn"]:last-child [data-testid="stMetricDelta"] { font-size: 10px !important; }
/* expander 컴팩트 */
[data-testid="stExpander"] summary { font-size: 12px !important; padding: 4px 0 !important; }
/* divider 간격 축소 */
hr { margin: 10px 0 !important; }
/* 탭 글씨 */
[data-testid="stTab"] button { font-size: 12px !important; padding: 4px 8px !important; }
</style>""", unsafe_allow_html=True)

# ── 데이터 로드 ──
region_master = load_region_master()
pop_agg = load_population_agg()
card_agg = load_card_sales_agg()
hp = load_hotplace_monthly()

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

# ── 년월 선택 (좌우 화살표) ──
all_ym = sorted(hp["STANDARD_YEAR_MONTH"].unique(), reverse=True)

if "ym_idx" not in st.session_state:
    st.session_state.ym_idx = 0

total_records = len(hp)
h1, h2, h3, h4, h5 = st.columns([4, 0.5, 2, 0.5, 4])
with h1:
    st.markdown(
        f'<div style="display:flex; align-items:center; gap:8px;">'
        f'<span style="color:#6366F1; font-weight:700; font-size:16px;">✦</span>'
        f'<span style="font-size:13px; font-weight:600; opacity:0.5;">'
        f'데이터 {total_records:,}건을 분석한 시그널</span></div>',
        unsafe_allow_html=True,
    )
ym_labels = [f"{str(m)[:4]}년 {int(str(m)[4:6])}월" for m in all_ym]

# 드롭다운 키 초기화
if "ym_sel" not in st.session_state:
    st.session_state.ym_sel = ym_labels[0]

with h2:
    if st.button("◀", key="ym_prev", use_container_width=True, disabled=st.session_state.ym_idx >= len(all_ym) - 1):
        st.session_state.ym_idx = min(st.session_state.ym_idx + 1, len(all_ym) - 1)
        st.session_state.ym_sel = ym_labels[st.session_state.ym_idx]
        st.rerun()
with h3:
    def _on_ym_change():
        st.session_state.ym_idx = ym_labels.index(st.session_state.ym_sel)
    st.selectbox("년월", ym_labels, key="ym_sel", label_visibility="collapsed", on_change=_on_ym_change)
    st.session_state.ym_idx = ym_labels.index(st.session_state.ym_sel)
with h4:
    if st.button("▶", key="ym_next", use_container_width=True, disabled=st.session_state.ym_idx <= 0):
        st.session_state.ym_idx = max(st.session_state.ym_idx - 1, 0)
        st.session_state.ym_sel = ym_labels[st.session_state.ym_idx]
        st.rerun()

selected_ym = all_ym[st.session_state.ym_idx]

# 선택된 월 + 이전 3개월 시그널
selected_months = [m for m in all_ym if m <= selected_ym][:4]
signals = []
for ym in selected_months:
    signals.extend(get_signals_for_month(hp, ym))

if not signals:
    st.info("감지된 시그널이 없습니다.")
    st.stop()

# ═══════════════════════════════════════
col_left, col_mid, col_right = st.columns([3, 5, 4])

# ─────────────────────────────────────
# LEFT: 시그널 리스트
# ─────────────────────────────────────
with col_left:
    filter_val = st.radio("필터", ["전체", "상승", "하락"], horizontal=True, label_visibility="collapsed")
    if filter_val == "상승":
        filtered = [s for s in signals if s["direction"] == "up"]
    elif filter_val == "하락":
        filtered = [s for s in signals if s["direction"] == "down"]
    else:
        filtered = list(signals)

    month_groups: dict[str, list] = {}
    for s in filtered:
        month_groups.setdefault(s["month_label"], []).append(s)

    signal_scroll = st.container(height=380)
    with signal_scroll:
      for month_label, month_sigs in month_groups.items():
        year = month_label[:4]
        mon = month_label[5:]
        st.markdown(f'<div class="signal-header">{year}년 {int(mon)}월</div>', unsafe_allow_html=True)

        # 해당 월 전체 순위 계산
        m_ym = month_sigs[0]["month"] if month_sigs else None
        m_all = hp[hp["STANDARD_YEAR_MONTH"] == m_ym].sort_values("hotplace_score", ascending=False) if m_ym else pd.DataFrame()
        rank_map = {row["DISTRICT_CODE"]: i + 1 for i, (_, row) in enumerate(m_all.iterrows())} if not m_all.empty else {}
        total_d = len(m_all)

        for sig_item in month_sigs:
            global_idx = signals.index(sig_item) if sig_item in signals else 0
            is_selected = global_idx == st.session_state.selected_signal_idx
            chg_prefix = "+" if sig_item["direction"] == "up" else ""
            color = "#f04452" if sig_item["direction"] == "up" else "#3182f6"
            dir_label = "상승" if sig_item["direction"] == "up" else "하락"
            kw = sig_item["keywords"][0] if sig_item["keywords"] else ""
            rank = rank_map.get(sig_item["dc"], 0)
            if rank and total_d:
                if rank <= 3:
                    rank_str = f"상위 {rank}"
                elif rank > total_d - 3:
                    rank_str = f"하위 {total_d - rank + 1}"
                else:
                    rank_str = f"{rank}/{total_d}"
            else:
                rank_str = ""

            bg = "rgba(99,102,241,0.10)" if is_selected else "transparent"
            bl = "3px solid #6366F1" if is_selected else "3px solid transparent"

            st.markdown(
                f'<div class="sig-card" style="padding:6px 6px; background:{bg}; border-left:{bl};">'
                f'  <div style="display:flex; justify-content:space-between;">'
                f'    <span style="font-size:13px; font-weight:700;">{sig_item["name"]}</span>'
                f'    <span style="font-size:9px; opacity:0.3;">{rank_str}</span></div>'
                f'  <div style="font-size:11px; margin-top:1px;">'
                f'    <span style="color:{color};">{chg_prefix}{sig_item["composite"]}점 {dir_label}</span>'
                f'    <span style="opacity:0.35;"> · {kw}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("ㅤ", key=f"sig_{global_idx}", use_container_width=True, type="tertiary"):
                st.session_state.selected_signal_idx = global_idx
                st.rerun()

    # ── 근처 시그널 (parquet에서 직접 조회) ──
    # ── 근처 시그널 (별도 컨테이너) ──
    my_nb = st.session_state.my_neighborhood
    my_city = my_nb.split(" ")[0] if my_nb else ""
    my_short = my_nb.split(" ")[-1] if my_nb else ""
    my_dc = rm[rm["label"] == my_nb]["district_code"].values[0] if my_nb in rm["label"].values else ""
    same_city_hp = hp[(hp["city"] == my_city) & (hp["STANDARD_YEAR_MONTH"] == selected_ym)].sort_values("hotplace_score", ascending=False)
    my_row = same_city_hp[same_city_hp["DISTRICT_CODE"] == my_dc]
    others_rows = same_city_hp[same_city_hp["DISTRICT_CODE"] != my_dc].head(3)
    nearby_rows = pd.concat([my_row, others_rows])
    nearby = [_hp_to_signal(row) for _, row in nearby_rows.iterrows()]
    if nearby:
        with st.container(border=True):
            st.markdown(f'<div style="font-size:13px; font-weight:800; margin-bottom:4px;">{my_short} 근처 시그널</div>', unsafe_allow_html=True)
            for ni, r in enumerate(nearby):
                rcolor = "#f04452" if r["direction"] == "up" else "#3182f6"
                rp = "+" if r["direction"] == "up" else ""
                rk = r["keywords"][0] if r["keywords"] else ""
                st.markdown(
                    f'<div style="padding:6px 0; border-bottom:1px solid rgba(128,128,128,0.06);">'
                    f'  <div style="font-size:12px; font-weight:600;">{r["name"]}</div>'
                    f'  <div style="font-size:11px; margin-top:2px;">'
                    f'    <span style="color:{rcolor};">{rp}{r["composite"]}점</span>'
                    f'    <span style="opacity:0.35;"> · {rk}</span></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

# ─────────────────────────────────────
# MIDDLE: 상세 패널
# ─────────────────────────────────────
with col_mid:
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
    with st.container(border=True):
        st.markdown(f"**{why_title}**")
        reasons_html = "".join(
            f'<li style="font-size:13px; line-height:1.7; opacity:0.75; margin-bottom:4px;">{r}</li>'
            for r in sig["reasons"]
        )
        st.markdown(f'<ul style="padding-left:18px; margin:6px 0 0;">{reasons_html}</ul>', unsafe_allow_html=True)

    kw_html = "".join(f'<span class="kw-tag">{kw}</span>' for kw in sig["keywords"])
    st.markdown(kw_html, unsafe_allow_html=True)

    # 출처 (접힌 상태)
    with st.expander(f"{len(sig['sources'])}개 출처", expanded=False):
        for src in sig["sources"]:
            st.markdown(f'<div style="font-size:12px; padding:2px 0;">{src} · {m_year}년 {int(m_mon)}월</div>', unsafe_allow_html=True)

    # 점수 breakdown (접힌 상태) — 핫플 5개 지표
    w = sig.get("weights", {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15})
    with st.expander("점수 구성 보기", expanded=False):
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
                f'<div style="padding:5px 0;">'
                f'  <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:2px;">'
                f'    <span>{label} <span style="opacity:0.35;">({weight}%)</span></span>'
                f'    <span style="font-weight:700; color:{bar_color};">{sp}{score:.1f}점</span>'
                f'  </div>'
                f'  <div style="display:flex; align-items:center; gap:6px;">'
                f'    <div style="flex:1; height:5px; border-radius:3px; background:rgba(128,128,128,0.1);">'
                f'      <div style="width:{bar_width}%; height:100%; border-radius:3px; background:{bar_color};"></div></div>'
                f'    <span style="font-size:10px; opacity:0.35;">{cp}{chg}%</span>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        sig_hp_all = hp[(hp["DISTRICT_CODE"] == sig["dc"]) & (hp["STANDARD_YEAR_MONTH"] <= sig["month"])].sort_values("STANDARD_YEAR_MONTH")
        mid_current = round(100 + sig_hp_all["hotplace_score"].sum(), 1)
        mid_prev = round(mid_current - sig["composite"], 1)
        total_color = "#f04452" if sig["composite"] > 0 else "#3182f6"
        total_prefix = "+" if sig["composite"] > 0 else ""
        st.markdown(
            f'<div style="padding:6px 0 2px; border-top:1px solid rgba(128,128,128,0.12); margin-top:4px;">'
            f'  <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:800;">'
            f'    <span>종합</span>'
            f'    <span style="color:{total_color};">{mid_current}점</span>'
            f'  </div>'
            f'  <div style="text-align:right; font-size:10px; opacity:0.35;">{mid_prev}점 → {mid_current}점 ({total_prefix}{sig["composite"]}점)</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # 연관 동네 (클릭 가능)
    st.markdown('<div style="font-size:13px; font-weight:800; margin-bottom:4px;">연관 동네</div>', unsafe_allow_html=True)
    same_city = [s for s in signals if s["city"] == sig["city"] and s["dc"] != sig["dc"]]
    if same_city:
        for ri, rel in enumerate(same_city[:5]):
            rc = "#f04452" if rel["direction"] == "up" else "#3182f6"
            rp = "+" if rel["direction"] == "up" else ""
            rk = rel["keywords"][0] if rel["keywords"] else ""
            rel_hp_all = hp[(hp["DISTRICT_CODE"] == rel["dc"]) & (hp["STANDARD_YEAR_MONTH"] <= rel["month"])]
            rel_curr = round(100 + rel_hp_all["hotplace_score"].sum(), 1)
            st.markdown(
                f'<div class="sig-card" style="display:flex; justify-content:space-between; align-items:center;'
                f'  padding:4px 0; border-bottom:1px solid rgba(128,128,128,0.06); cursor:pointer;">'
                f'  <div style="display:flex; align-items:center; gap:5px;">'
                f'    <span style="font-size:11px; font-weight:600;">{rel["name"]}</span>'
                f'    <span style="font-size:11px; font-weight:700;">{rel_curr}점</span>'
                f'    <span style="font-size:10px; color:{rc}; font-weight:600;">{rp}{rel["composite"]}점</span>'
                f'  </div>'
                f'  <span style="font-size:9px; opacity:0.3;">{rk}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("ㅤ", key=f"rel_{ri}", use_container_width=True, type="tertiary"):
                idx = signals.index(rel) if rel in signals else None
                if idx is not None:
                    st.session_state.selected_signal_idx = idx
                    st.rerun()
    else:
        st.caption("같은 구의 다른 시그널이 없습니다.")

# ─────────────────────────────────────
# RIGHT: 내 동네 프로파일
# ─────────────────────────────────────
with col_right:
    st.markdown("")
    st.markdown('<div style="font-size:14px; font-weight:700; margin-bottom:8px;">내 동네</div>', unsafe_allow_html=True)
    current_idx = district_options.index(st.session_state.my_neighborhood) if st.session_state.my_neighborhood in district_options else 0
    new_nb = st.selectbox("동네 변경", district_options, index=current_idx, label_visibility="collapsed", key="my_nb_select")
    if new_nb != st.session_state.my_neighborhood:
        st.session_state.my_neighborhood = new_nb
        st.rerun()

    sel_row = rm[rm["label"] == new_nb].iloc[0]
    dc = sel_row["district_code"]
    city = sel_row["city_kor"]
    district = sel_row["district_kor"]

    all_months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique(), reverse=True)
    # 선택된 년월 기준
    latest_month = selected_ym if selected_ym in all_months else (all_months[0] if all_months else None)
    ym_idx = all_months.index(latest_month) if latest_month in all_months else 0
    prev_month = all_months[ym_idx + 1] if ym_idx + 1 < len(all_months) else None
    ml_str = f"{str(latest_month)[:4]}년 {int(str(latest_month)[4:6])}월" if latest_month else ""
    st.caption(f"{city} {district} · {ml_str}")
    st.page_link("pages/2_동네_프로파일.py", label=f"프로파일 상세 보기 →", use_container_width=True)

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
    tab_summary, tab_spend, tab_people, tab_estate, tab_finance = st.tabs(
        ["요약", "소비", "인구", "부동산", "금융"]
    )

    with tab_summary:
        # 프로파일 점수 — 누적 계산 (100 + 전월들 합산)
        my_hp_all = hp[(hp["DISTRICT_CODE"] == dc) & (hp["STANDARD_YEAR_MONTH"] <= selected_ym)].sort_values("STANDARD_YEAR_MONTH")
        my_hp_curr = hp[(hp["DISTRICT_CODE"] == dc) & (hp["STANDARD_YEAR_MONTH"] == selected_ym)]
        my_sig = [_hp_to_signal(row) for _, row in my_hp_curr.iterrows()] if not my_hp_curr.empty else []

        if my_sig:
            ls = my_sig[0]
            cumulative_score = round(100 + my_hp_all["hotplace_score"].sum(), 1)
            prev_score = round(cumulative_score - ls["composite"], 1)
            month_chg = ls["composite"]
            score_color = "#f04452" if month_chg > 0 else "#3182f6"
            score_prefix = "+" if month_chg > 0 else ""

            # 순위 계산
            month_all = hp[hp["STANDARD_YEAR_MONTH"] == selected_ym].copy()
            month_all["cum"] = month_all["DISTRICT_CODE"].apply(
                lambda d: 100 + hp[(hp["DISTRICT_CODE"] == d) & (hp["STANDARD_YEAR_MONTH"] <= selected_ym)]["hotplace_score"].sum()
            )
            rank = int((month_all["cum"] > cumulative_score).sum() + 1)
            total_districts = len(month_all)

            st.markdown(
                f'<div style="padding:4px 0;">'
                f'  <div style="display:flex; justify-content:space-between; align-items:center;">'
                f'    <span style="font-size:11px; opacity:0.5;">핫플 점수</span>'
                f'    <span style="font-size:11px; opacity:0.5;">{total_districts}개 동네 중 {rank}위</span>'
                f'  </div>'
                f'  <div style="font-size:22px; font-weight:800;">{cumulative_score}점</div>'
                f'  <div style="font-size:11px; color:{score_color};">'
                f'    전월대비 {score_prefix}{month_chg}점 ({prev_score}점 → {cumulative_score}점)</div>'
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
                curr_label = f"{str(selected_ym)[2:4]}.{str(selected_ym)[4:6]}"

                fig_trend = go.Figure(go.Scatter(
                    x=trend["label"], y=trend["cum_score"],
                    mode="lines", line=dict(color="#6366F1", width=2),
                    fill="tozeroy", fillcolor="rgba(99,102,241,0.08)",
                ))
                # 현재 월 포인트
                curr_row = trend[trend["label"] == curr_label]
                if not curr_row.empty:
                    fig_trend.add_trace(go.Scatter(
                        x=[curr_label], y=[curr_row["cum_score"].values[0]],
                        mode="markers", marker=dict(size=10, color="#f04452"),
                        showlegend=False,
                    ))
                    fig_trend.add_vline(x=curr_label, line_dash="dot", line_color="rgba(240,68,82,0.3)")
                fig_trend.update_layout(
                    height=100, margin=dict(l=0, r=0, t=3, b=3),
                    xaxis=dict(showgrid=False, tickfont=dict(size=8)),
                    yaxis=dict(showgrid=False, showticklabels=False),
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
                    st.metric("평균소득", f"{avg/1e4:,.0f}만")
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
                fig_ct.update_layout(title="시간대별 매출", barmode="group", height=230, margin=dict(l=25, r=10, t=30, b=25))
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
        except Exception:
            st.info("데이터 없음")
        try:
            pop_demo = load_population_demo()
            pd_d = pop_demo[(pop_demo["DISTRICT_CODE"] == dc) & (pop_demo["STANDARD_YEAR_MONTH"] == latest_month)]
            if not pd_d.empty:
                fig = population_pyramid(pd_d, f"{district} 인구 피라미드")
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
                    st.info("부동산 데이터 없음")
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

# ── 채팅 ──
page_context = f"인사이트 피드 - {sig['name']} {chg_prefix}{sig['composite']}점" if signals else "인사이트 피드"
render_chat_panel(current_tab="메인", selected_district=None, selected_month=None, page_context=page_context)
