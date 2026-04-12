"""
AI 에이전트 — 사이드바 채팅 (Streamlit 1.22.0 + Snowflake 호환)
"""
import streamlit as st
import json, re
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5.4"


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
{{"intent":"lookup|compare|trend|simulate|recommend|hotplace|marketing|rental|forecast|realestate","district":"district_name|null","category":"business_type|null"}}"""
    resp = _cortex(p)
    try:
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        if m: return json.loads(m.group())
    except: pass
    return {"intent": "lookup", "district": None, "category": None}


# intent에 marketing, rental, forecast 추가


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


def _qrental():
    """렌탈 트렌드 조회"""
    try:
        df = run_query(f"""
            SELECT RENTAL_SUB_CATEGORY as CATEGORY,
                   SUM(CONTRACT_COUNT) as CONTRACTS,
                   ROUND(AVG(OPEN_CVR), 1) as OPEN_RATE,
                   ROUND(AVG(AVG_NET_SALES)) as AVG_SALES_KRW
            FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS
            WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS)
            GROUP BY 1 ORDER BY CONTRACTS DESC LIMIT 10
        """)
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _qmarketing():
    """마케팅 채널 성과 조회"""
    try:
        df = run_query(f"""
            SELECT UTM_SOURCE as SOURCE, UTM_MEDIUM as MEDIUM,
                   SUM(TOTAL_SESSIONS) as SESSIONS,
                   SUM(TOTAL_CONTRACTS) as CONTRACTS,
                   ROUND(AVG(CONTRACT_CVR), 2) as CVR_PCT,
                   ROUND(SUM(TOTAL_REVENUE) / 1e8, 1) as REVENUE_BILLION
            FROM {AJD}.V07_GA4_MARKETING_ATTRIBUTION
            WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V07_GA4_MARKETING_ATTRIBUTION)
            GROUP BY 1, 2 ORDER BY REVENUE_BILLION DESC LIMIT 10
        """)
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _qfunnel():
    """퍼널 전환율 조회"""
    try:
        df = run_query(f"""
            SELECT MAIN_CATEGORY_NAME as CATEGORY,
                   SUM(TOTAL_COUNT) as TOTAL,
                   SUM(PAYEND_COUNT) as PAID,
                   ROUND(AVG(OVERALL_CVR), 1) as OVERALL_CVR_PCT
            FROM {AJD}.V03_CONTRACT_FUNNEL_CONVERSION
            WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V03_CONTRACT_FUNNEL_CONVERSION)
            GROUP BY 1 ORDER BY TOTAL DESC
        """)
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e:
        return f"조회오류: {e}"


def _qrealestate(d):
    """부동산 시세 조회"""
    try:
        from data_loader import RICHGO
        s = d.replace("'", "''")
        df = run_query(f"""
            SELECT SGG, EMD, YYYYMMDD as DATE,
                   MEME_PRICE_PER_SUPPLY_PYEONG as SALE_PRICE_PER_PYEONG,
                   JEONSE_PRICE_PER_SUPPLY_PYEONG as JEONSE_PRICE_PER_PYEONG,
                   TOTAL_HOUSEHOLDS
            FROM {RICHGO}.REGION_APT_RICHGO_MARKET_PRICE_M_H
            WHERE EMD LIKE '%{s}%' AND REGION_LEVEL = 'emd'
            ORDER BY YYYYMMDD DESC LIMIT 12
        """)
        return df.to_string(index=False) if not df.empty else f"'{d}' 부동산 데이터 없음"
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
        data = (f"[카드매출]\n{_qsales(d)}\n\n[소득]\n{_qincome(d)}\n\n[렌탈 트렌드]\n{_qrental()}") if d else f"[핫플]\n{_qhot(5)}\n\n[렌탈 트렌드]\n{_qrental()}"
    elif intent == "marketing":
        data = f"[마케팅 채널 성과]\n{_qmarketing()}\n\n[퍼널 전환율]\n{_qfunnel()}"
    elif intent == "rental":
        data = f"[렌탈 트렌드]\n{_qrental()}\n\n[퍼널 전환율]\n{_qfunnel()}"
    elif intent == "forecast" and d:
        # 전체 추이 데이터 (60개월) → Cortex가 계절성+트렌드 분석
        s = d.replace("'", "''")
        data = f"[{d} 유동인구 전체 추이 (월별)]\n"
        try:
            df = run_query(f"""
                SELECT STANDARD_YEAR_MONTH,
                       ROUND(SUM(RESIDENTIAL_POPULATION)) as RESIDENTIAL,
                       ROUND(SUM(WORKING_POPULATION)) as WORKING,
                       ROUND(SUM(VISITING_POPULATION)) as VISITING,
                       ROUND(SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION)) as TOTAL_POP
                FROM {SPH}.FLOATING_POPULATION_INFO f
                JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%'
                GROUP BY 1 ORDER BY 1
            """)
            data += df.to_string(index=False)
        except: pass
        data += f"\n\n[{d} 카드매출 전체 추이]\n"
        try:
            df2 = run_query(f"""
                SELECT STANDARD_YEAR_MONTH,
                       ROUND(SUM(TOTAL_SALES)) as TOTAL_SALES,
                       ROUND(SUM(COFFEE_SALES)) as COFFEE_SALES,
                       ROUND(SUM(FOOD_SALES)) as FOOD_SALES
                FROM {SPH}.CARD_SALES_INFO c
                JOIN {SPH}.M_SCCO_MST m ON c.DISTRICT_CODE = m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND c.CARD_TYPE = '1'
                GROUP BY 1 ORDER BY 1
            """)
            data += df2.to_string(index=False)
        except: pass
        data += f"\n\n[부동산 시세]\n{_qrealestate(d)}"
    elif intent == "realestate" and d:
        data = f"[{d} 부동산 시세 추이]\n{_qrealestate(d)}"
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

    prompt = f"""당신은 XR-AI 상권 분석 전문가입니다.
타겟 사용자: 소상공인, 프랜차이즈 출점 담당자, 팝업 위치 기획자.
목적: 출점 의사결정을 데이터 기반으로 도와주는 것입니다.

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
- AVG_INCOME_KRW: 평균 연소득 (천원 단위, 예: 30000 = 3,000만원)
- GROWTH_PCT: 방문인구 증가율 (%)
- CONTRACTS: 계약 건수 (아정당 렌탈/인터넷)
- CVR_PCT: 전환율 (%)
- REVENUE_BILLION: 매출 (억원)
- SALE_PRICE_PER_PYEONG: 매매 평단가 (만원/평)
- JEONSE_PRICE_PER_PYEONG: 전세 평단가 (만원/평)

[이전 대화]
{hist}

[규칙]
- 위 데이터를 기반으로 정확하게 답변하세요.
- 금액은 억원/만원 단위로 변환 (예: 3591366832원 → 약 35.9억원)
- 인구는 천 단위 구분 (예: 45935 → 45,935명)
- 데이터에 없으면 "추정"이라고 명시
- 절대 되묻지 마세요
- 예측 요청 시: 트렌드 분석 + 계절성 패턴 + 향후 3개월 예측값(표) + 근거 + 리스크
- 한국어로 답변

[답변 형식 — 반드시 지켜주세요]
- 핵심 요약을 먼저 2~3줄로 작성
- 수치가 있으면 반드시 마크다운 표(|)로 정리
- 표 예시:
| 항목 | 수치 | 비중 |
|------|------|------|
| 식음료 | 130.2억원 | 16.7% |
- 글씨 크기를 통일 (제목은 ###, 소제목은 ####)
- 시사점/인사이트는 별도 섹션으로 분리
- 추천이 있으면 우선순위를 번호로 매기기
- 불필요한 반복 설명 없이 핵심만 간결하게

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
        st.markdown("""<div style="padding:6px 0 2px;">
            <span style="font-size:14px;font-weight:700;">XR-AI</span>
            <span style="font-size:10px;color:#888;margin-left:4px;">상권 분석 에이전트</span>
        </div>""", unsafe_allow_html=True)
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
                    # 마크다운 표/제목 지원을 위해 st.markdown 직접 사용
                    st.markdown(msg['content'])
            st.markdown("---")

        # 추천 질문 (대화 없을 때만)
        if not st.session_state.chat_messages:
            st.caption("💡 추천 질문")
            qs = [
                ("잠원동에 카페 출점하려는데 상권 분석해줘", "☕ 출점 분석"),
                ("방문인구 증가율 Top 5 동네는? 팝업 후보지 추천", "📍 팝업 후보지"),
                ("신당동 3개월 후 상권 전망 예측해줘", "🔮 미래 예측"),
                ("신당동과 여의도동 상권 비교해줘", "⚖️ 상권 비교"),
                ("서초구에서 프랜차이즈 출점하기 좋은 동네와 업종은?", "🏪 출점 추천"),
                ("최근 어떤 마케팅 채널의 고객 유입이 효과적이야?", "📢 마케팅 분석"),
            ]

            # session_state로 버튼 클릭 추적 (연쇄 방지)
            if "pending_q" not in st.session_state:
                st.session_state.pending_q = None

            for i, (query, label) in enumerate(qs):
                if st.button(label, key=f"q_{i}", use_container_width=True):
                    st.session_state.pending_q = query

            # 클릭된 질문 처리
            if st.session_state.pending_q:
                q = st.session_state.pending_q
                st.session_state.pending_q = None
                _do_ask(q, "", "")

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
