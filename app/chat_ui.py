"""
AI 에이전트 — 사이드바 채팅 (Streamlit 1.22.0 + Snowflake 호환)
"""
import streamlit as st
import json, re
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5-mini"


def _safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    elif hasattr(st, 'experimental_rerun'): st.experimental_rerun()


def _cortex(prompt):
    try:
        safe = prompt.replace("'", "''").replace("\\", "\\\\")
        r = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{CORTEX_MODEL}','{safe}') as r")
        return str(r.iloc[0, 0]) if not r.empty else "응답 실패"
    except Exception as e:
        return f"오류: {e}"


def _classify(q, h=""):
    p = f"""Classify this question. Return JSON only.
Previous: {h[:200]}
Question: {q}
{{"intent":"lookup|compare|trend|simulate|recommend|hotplace","district":"district_name|null","category":"business_type|null"}}"""
    resp = _cortex(p)
    try:
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        if m: return json.loads(m.group())
    except: pass
    return {"intent": "lookup", "district": None, "category": None}


def _qpop(d):
    try:
        s = d.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as DISTRICT_NAME,
                   f.STANDARD_YEAR_MONTH as YEAR_MONTH,
                   ROUND(SUM(f.RESIDENTIAL_POPULATION)) as RESIDENTIAL_POP,
                   ROUND(SUM(f.WORKING_POPULATION)) as WORKING_POP,
                   ROUND(SUM(f.VISITING_POPULATION)) as VISITING_POP,
                   ROUND(SUM(f.RESIDENTIAL_POPULATION + f.WORKING_POPULATION + f.VISITING_POPULATION)) as TOTAL_POP
            FROM {SPH}.FLOATING_POPULATION_INFO f
            JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%'
              AND f.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
            GROUP BY 1, 2
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _qsales(d):
    try:
        s = d.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as DISTRICT_NAME,
                   ROUND(SUM(TOTAL_SALES)) as TOTAL_SALES_KRW,
                   ROUND(SUM(FOOD_SALES)) as FOOD_SALES_KRW,
                   ROUND(SUM(COFFEE_SALES)) as COFFEE_SALES_KRW,
                   ROUND(SUM(BEAUTY_SALES)) as BEAUTY_SALES_KRW,
                   ROUND(SUM(MEDICAL_SALES)) as MEDICAL_SALES_KRW,
                   ROUND(SUM(SMALL_RETAIL_STORE_SALES)) as RETAIL_SALES_KRW
            FROM {SPH}.CARD_SALES_INFO c
            JOIN {SPH}.M_SCCO_MST m ON c.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND c.CARD_TYPE = '1'
              AND c.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.CARD_SALES_INFO)
            GROUP BY 1
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _qincome(d):
    try:
        s = d.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as DISTRICT_NAME,
                   SUM(a.CUSTOMER_COUNT) as CUSTOMER_COUNT,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_INCOME) / NULLIF(SUM(a.CUSTOMER_COUNT), 0)) as AVG_INCOME_KRW,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_SCORE) / NULLIF(SUM(a.CUSTOMER_COUNT), 0)) as AVG_CREDIT_SCORE
            FROM {SPH}.ASSET_INCOME_INFO a
            JOIN {SPH}.M_SCCO_MST m ON a.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND a.INCOME_TYPE = 1
              AND a.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.ASSET_INCOME_INFO)
            GROUP BY 1
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _qhot(n=10):
    try:
        df = run_query(f"""
            WITH recent AS (
                SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) as AVG_VISIT
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH >= (SELECT MAX(STANDARD_YEAR_MONTH) - 6 FROM {SPH}.FLOATING_POPULATION_INFO)
                GROUP BY 1
            ),
            prev AS (
                SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) as AVG_VISIT
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH < (SELECT MAX(STANDARD_YEAR_MONTH) - 6 FROM {SPH}.FLOATING_POPULATION_INFO)
                  AND STANDARD_YEAR_MONTH >= (SELECT MAX(STANDARD_YEAR_MONTH) - 12 FROM {SPH}.FLOATING_POPULATION_INFO)
                GROUP BY 1
            )
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as DISTRICT_NAME,
                   ROUND((r.AVG_VISIT - p.AVG_VISIT) / NULLIF(p.AVG_VISIT, 0) * 100, 1) as GROWTH_PCT,
                   ROUND(r.AVG_VISIT) as CURRENT_VISITORS
            FROM recent r
            JOIN prev p ON r.DISTRICT_CODE = p.DISTRICT_CODE
            JOIN {SPH}.M_SCCO_MST m ON r.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE p.AVG_VISIT > 0
            ORDER BY GROWTH_PCT DESC
            LIMIT {n}
        """)
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _answer(q, hist_list, pctx="", sel_d=""):
    hist = "\n".join([f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:150]}" for m in hist_list[-4:]]) if hist_list else ""
    info = _classify(q, hist)
    intent = info.get("intent", "lookup")
    d = info.get("district") or sel_d or ""

    data = ""
    if intent == "hotplace":
        data = f"[핫플레이스 랭킹]\n{_qhot()}"
    elif intent == "compare":
        ds = re.findall(r'(\w+[동구])', q)
        parts = []
        for x in (ds[:3] if len(ds) >= 2 else [d] if d else []):
            parts.append(f"=== {x} ===\n[유동인구]\n{_qpop(x)}\n[카드매출]\n{_qsales(x)}")
        data = "\n\n".join(parts) if parts else "비교 대상 없음"
    elif intent == "simulate" and d:
        data = f"[유동인구]\n{_qpop(d)}\n\n[카드매출]\n{_qsales(d)}\n\n[소득]\n{_qincome(d)}"
    elif intent == "recommend":
        data = (f"[카드매출]\n{_qsales(d)}\n\n[소득]\n{_qincome(d)}") if d else f"[핫플]\n{_qhot(5)}"
    elif intent == "trend" and d:
        try:
            s = d.replace("'", "''")
            df = run_query(f"""
                SELECT STANDARD_YEAR_MONTH,
                       ROUND(SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION)) as TOTAL_POP
                FROM {SPH}.FLOATING_POPULATION_INFO f
                JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%'
                GROUP BY 1 ORDER BY 1 DESC LIMIT 12
            """)
            data = f"[{d} 12개월 추이]\n{df.to_string(index=False)}"
        except Exception as e:
            data = f"추이 조회 오류: {e}"
    elif d:
        data = f"[유동인구]\n{_qpop(d)}\n\n[카드매출]\n{_qsales(d)}\n\n[소득]\n{_qincome(d)}"
    else:
        data = "지역명을 특정할 수 없습니다."

    ctx = f"[현재 화면] {pctx}" if pctx else ""

    prompt = f"""당신은 서울 동네 데이터 분석 전문가입니다.

{ctx}

[조회된 데이터]
{data}

[컬럼 설명]
- DISTRICT_NAME: 동네 이름 (시군구 + 법정동)
- RESIDENTIAL_POP: 거주인구 (해당 동네에 사는 사람 수)
- WORKING_POP: 직장인구 (해당 동네에서 일하는 사람 수)
- VISITING_POP: 방문인구 (방문객 수)
- TOTAL_POP: 총 유동인구 (거주+직장+방문)
- TOTAL_SALES_KRW: 총 카드매출 (원 단위)
- FOOD_SALES_KRW: 식음료 매출
- COFFEE_SALES_KRW: 커피/카페 매출
- AVG_INCOME_KRW: 평균 소득 (원 단위)
- GROWTH_PCT: 방문인구 증가율 (%)

[이전 대화]
{hist}

[규칙]
- 위 데이터를 기반으로 정확하게 답변하세요.
- 금액은 억원/만원 단위로 변환 (예: 3591366832원 → 약 35.9억원)
- 인구는 천 단위 구분 (예: 45935 → 45,935명)
- 데이터에 없으면 "추정"이라고 명시
- 절대 되묻지 마세요
- 간결하게 핵심만 답변
- 한국어로 답변

질문: {q}"""

    return {"answer": _cortex(prompt), "intent": intent}


def _do_ask(q, pctx, sel_d):
    st.session_state.chat_messages.append({"role": "user", "content": q})
    r = _answer(q, st.session_state.chat_messages[:-1], pctx, sel_d)
    st.session_state.chat_messages.append({"role": "assistant", "content": r["answer"], "intent": r["intent"]})
    _safe_rerun()


def render_sidebar_chat():
    """사이드바 AI 채팅 — 대화 위, 입력 아래"""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    with st.sidebar:
        # 헤더
        st.markdown("""
        <div style="padding:8px 0 4px;font-size:13px;font-weight:600;">AI 에이전트</div>
        """, unsafe_allow_html=True)
        st.markdown("---")

        # 대화 히스토리 (위에)
        if st.session_state.chat_messages:
            for msg in st.session_state.chat_messages:
                if msg["role"] == "user":
                    st.markdown(f"""<div style="text-align:right;margin:6px 0;">
                        <span style="background:#6366F1;color:white;padding:6px 10px;
                        border-radius:10px 10px 3px 10px;font-size:12px;display:inline-block;max-width:90%;">
                        {msg['content']}</span></div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div style="margin:6px 0;">
                        <span style="background:#1e1e2e;color:#e0e0e0;padding:8px 10px;
                        border-radius:10px 10px 10px 3px;font-size:12px;line-height:1.5;
                        display:inline-block;max-width:95%;">
                        {msg['content']}</span></div>""", unsafe_allow_html=True)
            st.markdown("---")

        # 추천 질문 (대화 없을 때만)
        if not st.session_state.chat_messages:
            st.caption("💡 추천 질문")
            qs = [
                ("신당동 거주/직장/방문 인구 알려줘", "🔍 신당동 유동인구"),
                ("방문인구 증가율 Top 5 동네는?", "🔥 핫플 Top 5"),
                ("신당동 vs 여의도동 매출 비교", "⚖️ 매출 비교"),
                ("잠원동에서 어떤 업종이 유망해?", "💡 업종 추천"),
            ]
            for query, label in qs:
                if st.button(label, key=f"q_{label}", use_container_width=True):
                    _do_ask(query, "", "")

        # 입력 (아래)
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
