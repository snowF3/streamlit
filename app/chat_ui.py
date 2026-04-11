"""
AI 에이전트 — 사이드바 채팅 (Streamlit 1.22.0 호환)
- 명확한 컬럼명으로 SQL 조회
- gpt-5-mini 기본 모델
- 채팅앱 순서 (대화 위, 입력 아래)
"""
import streamlit as st
import json, re
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5-mini"


def _safe_rerun():
    if hasattr(st,'rerun'): st.rerun()
    elif hasattr(st,'experimental_rerun'): st.experimental_rerun()


def _cortex(prompt):
    try:
        safe = prompt.replace("'","''").replace("\\","\\\\")
        r = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{CORTEX_MODEL}','{safe}') as r")
        return str(r.iloc[0,0]) if not r.empty else "응답 실패"
    except Exception as e:
        return f"오류: {e}"


def _classify(q, h=""):
    p = f"""아래 질문을 분류하세요. JSON만 반환.
이전대화: {h[:200]}
질문: {q}
{{"intent":"lookup|compare|trend|simulate|recommend|hotplace","district":"법정동명|null","category":"업종|null"}}"""
    resp = _cortex(p)
    try:
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        if m: return json.loads(m.group())
    except: pass
    return {"intent":"lookup","district":None,"category":None}


def _qpop(d):
    """유동인구 조회 — 명확한 컬럼명"""
    try:
        s = d.replace("'","''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as 동네,
                   f.STANDARD_YEAR_MONTH as 기준월,
                   SUM(f.RESIDENTIAL_POPULATION) as 거주인구,
                   SUM(f.WORKING_POPULATION) as 직장인구,
                   SUM(f.VISITING_POPULATION) as 방문인구,
                   SUM(f.RESIDENTIAL_POPULATION + f.WORKING_POPULATION + f.VISITING_POPULATION) as 총유동인구
            FROM {SPH}.FLOATING_POPULATION_INFO f
            JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%'
              AND f.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
            GROUP BY 1, 2
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 유동인구 데이터 없음"
    except Exception as e:
        return f"조회 오류: {e}"


def _qsales(d):
    """카드매출 조회 — 명확한 컬럼명"""
    try:
        s = d.replace("'","''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as 동네,
                   SUM(TOTAL_SALES) as 총매출_원,
                   SUM(FOOD_SALES) as 식음료매출_원,
                   SUM(COFFEE_SALES) as 커피매출_원,
                   SUM(BEAUTY_SALES) as 미용매출_원,
                   SUM(MEDICAL_SALES) as 의료매출_원,
                   SUM(EDUCATION_ACADEMY_SALES) as 교육매출_원,
                   SUM(SMALL_RETAIL_STORE_SALES) as 소매매출_원,
                   SUM(E_COMMERCE_SALES) as 이커머스매출_원
            FROM {SPH}.CARD_SALES_INFO c
            JOIN {SPH}.M_SCCO_MST m ON c.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND c.CARD_TYPE = '1'
              AND c.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.CARD_SALES_INFO)
            GROUP BY 1
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 매출 데이터 없음"
    except Exception as e:
        return f"조회 오류: {e}"


def _qincome(d):
    """소득 조회 — 명확한 컬럼명"""
    try:
        s = d.replace("'","''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as 동네,
                   SUM(a.CUSTOMER_COUNT) as 고객수_명,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_INCOME) / NULLIF(SUM(a.CUSTOMER_COUNT),0), 0) as 평균소득_원,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_SCORE) / NULLIF(SUM(a.CUSTOMER_COUNT),0), 0) as 평균신용점수
            FROM {SPH}.ASSET_INCOME_INFO a
            JOIN {SPH}.M_SCCO_MST m ON a.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND a.INCOME_TYPE = 1
              AND a.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.ASSET_INCOME_INFO)
            GROUP BY 1
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 소득 데이터 없음"
    except Exception as e:
        return f"조회 오류: {e}"


def _qhot(n=10):
    """핫플레이스 랭킹"""
    try:
        df = run_query(f"""
            WITH recent AS (
                SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) as avg_visit
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH >= (SELECT MAX(STANDARD_YEAR_MONTH) - 6 FROM {SPH}.FLOATING_POPULATION_INFO)
                GROUP BY 1
            ),
            prev AS (
                SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) as avg_visit
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH < (SELECT MAX(STANDARD_YEAR_MONTH) - 6 FROM {SPH}.FLOATING_POPULATION_INFO)
                  AND STANDARD_YEAR_MONTH >= (SELECT MAX(STANDARD_YEAR_MONTH) - 12 FROM {SPH}.FLOATING_POPULATION_INFO)
                GROUP BY 1
            )
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as 동네,
                   ROUND((r.avg_visit - p.avg_visit) / NULLIF(p.avg_visit, 0) * 100, 1) as 방문인구증가율_퍼센트,
                   ROUND(r.avg_visit, 0) as 현재평균방문인구_명
            FROM recent r
            JOIN prev p ON r.DISTRICT_CODE = p.DISTRICT_CODE
            JOIN {SPH}.M_SCCO_MST m ON r.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE p.avg_visit > 0
            ORDER BY 2 DESC
            LIMIT {n}
        """)
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e:
        return f"조회 오류: {e}"


def _answer(q, hist_list, pctx="", sel_d=""):
    hist = "\n".join([f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:150]}" for m in hist_list[-4:]]) if hist_list else ""
    info = _classify(q, hist)
    intent = info.get("intent", "lookup")
    d = info.get("district") or sel_d or ""
    cat = info.get("category")

    data = ""
    if intent == "hotplace":
        data = f"[핫플레이스 랭킹 - 방문인구 증가율 기준]\n{_qhot()}"
    elif intent == "compare":
        ds = re.findall(r'(\w+[동구])', q)
        parts = []
        for x in (ds[:3] if len(ds) >= 2 else [d] if d else []):
            parts.append(f"=== {x} ===\n[유동인구]\n{_qpop(x)}\n[카드매출]\n{_qsales(x)}")
        data = "\n\n".join(parts) if parts else "비교 대상 없음"
    elif intent == "simulate" and d:
        data = f"[{d} 유동인구]\n{_qpop(d)}\n\n[{d} 카드매출]\n{_qsales(d)}\n\n[{d} 소득/자산]\n{_qincome(d)}"
    elif intent == "recommend":
        data = (f"[{d} 카드매출]\n{_qsales(d)}\n\n[{d} 소득]\n{_qincome(d)}") if d else f"[핫플 랭킹]\n{_qhot(5)}"
    elif intent == "trend" and d:
        try:
            s = d.replace("'","''")
            df = run_query(f"""
                SELECT STANDARD_YEAR_MONTH as 년월,
                       SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION) as 총유동인구
                FROM {SPH}.FLOATING_POPULATION_INFO f
                JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%'
                GROUP BY 1 ORDER BY 1 DESC LIMIT 12
            """)
            data = f"[{d} 최근 12개월 유동인구 추이]\n{df.to_string(index=False)}"
        except Exception as e:
            data = f"추이 조회 오류: {e}"
    elif d:
        data = f"[{d} 유동인구]\n{_qpop(d)}\n\n[{d} 카드매출]\n{_qsales(d)}\n\n[{d} 소득]\n{_qincome(d)}"
    else:
        data = "[데이터 없음] 지역명을 특정할 수 없습니다."

    ctx = f"[현재 화면] {pctx}" if pctx else ""

    prompt = f"""당신은 서울 동네 데이터 분석 전문가입니다.

{ctx}

[조회된 실제 데이터]
{data}

[이전 대화]
{hist}

[규칙]
- 위 실제 데이터를 기반으로 정확하게 답변하세요.
- 컬럼명을 그대로 해석하세요: 거주인구=해당 동네에 사는 사람, 직장인구=출퇴근하는 사람, 방문인구=방문객, 총유동인구=세 가지 합계
- 매출 단위는 원(₩)입니다. 억 단위로 변환하여 답하세요.
- 소득 단위도 원입니다. 만원 단위로 변환하세요.
- 데이터에 없는 내용은 "추정"이라고 명시하세요.
- 절대 되묻지 마세요.
- 간결하게 핵심만 답변하세요.
- 한국어로 답변하세요.

사용자 질문: {q}"""

    return {"answer": _cortex(prompt), "intent": intent}


def _do_ask(q, pctx, sel_d):
    st.session_state.chat_messages.append({"role": "user", "content": q})
    r = _answer(q, st.session_state.chat_messages[:-1], pctx, sel_d)
    st.session_state.chat_messages.append({"role": "assistant", "content": r["answer"], "intent": r["intent"]})
    _safe_rerun()


# ═══════════════════════════════════════════
# 사이드바 채팅 UI
# ═══════════════════════════════════════════

def render_sidebar_chat():
    """사이드바 전용 AI 채팅 — 채팅앱 순서 (대화 위, 입력 아래)"""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    with st.sidebar:
        # ── 헤더 ──
        st.markdown("""
        <div style="text-align:center;padding:16px 10px 12px;">
            <div style="font-size:24px;margin-bottom:4px;">🤖</div>
            <div style="font-size:14px;font-weight:700;color:#E0E0E0;">AI 에이전트</div>
            <div style="font-size:9px;color:#666;margin-top:2px;">Snowflake Cortex · gpt-5-mini</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # ── 대화 히스토리 (위에 표시) ──
        if st.session_state.chat_messages:
            for msg in st.session_state.chat_messages:
                if msg["role"] == "user":
                    st.markdown(f"""<div style="text-align:right;margin:6px 0;">
                        <span style="background:#6366F1;color:white;padding:6px 10px;
                        border-radius:10px 10px 3px 10px;font-size:12px;display:inline-block;max-width:90%;">
                        {msg['content']}</span></div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div style="margin:6px 0;">
                        <span style="background:rgba(255,255,255,0.04);color:#ccc;padding:8px 10px;
                        border-radius:10px 10px 10px 3px;font-size:11px;line-height:1.5;
                        display:inline-block;max-width:95%;border:1px solid rgba(255,255,255,0.06);">
                        {msg['content']}</span></div>""", unsafe_allow_html=True)

            st.markdown("---")

        # ── 추천 질문 (대화 없을 때만) ──
        if not st.session_state.chat_messages:
            st.caption("💡 추천 질문")
            qs = [
                ("신당동의 거주인구, 직장인구, 방문인구 각각 알려줘", "🔍 신당동 유동인구 상세"),
                ("서초동에 30석 카페를 차린다면 예상 월매출과 주 고객층은?", "🧪 서초동 카페 시뮬레이션"),
                ("최근 6개월간 방문인구 증가율이 가장 높은 동네 Top 5는?", "🔥 핫플레이스 Top 5"),
                ("중구 신당동과 영등포구 여의도동의 유동인구와 매출 비교해줘", "⚖️ 신당동 vs 여의도동"),
                ("잠원동에서 소비 데이터 기반으로 어떤 업종이 유망할까?", "💡 잠원동 업종 추천"),
                ("신당동 최근 12개월 유동인구 추이 보여줘", "📈 신당동 추이 분석"),
            ]
            for query, label in qs:
                if st.button(label, key=f"q_{label}", use_container_width=True):
                    _do_ask(query, "", "")

        # ── 입력 (아래에 배치 — 채팅앱 순서) ──
        st.markdown("---")
        inp = st.text_input("", key="ai_inp", placeholder="질문을 입력하세요...")
        c1, c2 = st.columns([4, 1])
        with c1:
            if st.button("전송", key="ai_send", use_container_width=True):
                if inp:
                    _do_ask(inp, "", "")
        with c2:
            if st.button("↻", key="ai_clr"):
                st.session_state.chat_messages = []
                _safe_rerun()
