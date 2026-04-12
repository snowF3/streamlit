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
    """2단계 분류: 키워드 매칭(0초) → 실패 시 LLM 폴백"""

    # ── 1단계: 키워드 매칭 (즉시) ──
    intent = None

    if any(w in q for w in ["출점", "차리", "열면", "오픈", "창업", "시뮬", "매출 예상", "상권 분석"]):
        intent = "simulate"
    elif any(w in q for w in ["비교", "vs", "차이", "어디가 더", "둘 중"]):
        intent = "compare"
    elif any(w in q for w in ["핫플", "뜨는", "Top", "인기", "순위", "랭킹"]):
        intent = "hotplace"
    elif any(w in q for w in ["예측", "전망", "미래", "앞으로", "3개월"]):
        intent = "forecast"
    elif any(w in q for w in ["추이", "변화", "최근", "트렌드", "월별"]):
        intent = "trend"
    elif any(w in q for w in ["마케팅", "채널", "ROI", "광고", "유입"]):
        intent = "marketing"
    elif any(w in q for w in ["렌탈", "정수기", "가전", "에어컨"]):
        intent = "rental"
    elif any(w in q for w in ["부동산", "매매", "전세", "시세", "집값"]):
        intent = "realestate"
    elif any(w in q for w in ["추천", "뭘 팔", "업종", "유망", "어떤 사업"]):
        intent = "recommend"
    elif any(w in q for w in ["화면", "보이는", "요약", "지금 보고"]):
        intent = "screen"

    # 동네명 추출 (정규식)
    district = None
    d_match = re.findall(r'(\w{1,4}[동가])\b', q)
    if d_match:
        district = d_match[0]

    # 업종 추출
    category = None
    for cat in ["카페", "음식점", "미용실", "편의점", "의류", "병원", "약국", "학원"]:
        if cat in q:
            category = cat
            break

    # 키워드로 intent 잡혔으면 바로 반환
    if intent:
        return {"intent": intent, "district": district, "category": category}

    # ── 2단계: LLM 폴백 (키워드 미매칭 시만) ──
    p = f"""질문을 분류. JSON만.
이전:{h[:200]}
질문:{q}
{{"intent":"lookup|simulate|compare|trend|forecast|recommend|hotplace|marketing|rental|realestate|screen","district":"동명|null","category":"업종|null"}}"""
    resp = _cortex(p)
    try:
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        if m:
            result = json.loads(m.group())
            # LLM 결과에 키워드로 찾은 district/category 보충
            if not result.get("district") and district:
                result["district"] = district
            if not result.get("category") and category:
                result["category"] = category
            return result
    except: pass
    return {"intent": "lookup", "district": district, "category": category}


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
        data = f"[{d} 유동인구]\n{_qpop(d)}\n\n[{d} 카드매출 (업종별)]\n{_qsales(d)}\n\n[{d} 소득/자산]\n{_qincome(d)}\n\n[{d} 부동산 시세]\n{_qrealestate(d)}"
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
    elif intent == "screen":
        data = f"[현재 화면 정보]\n{pctx}" if pctx else "현재 화면 정보가 전달되지 않았습니다."
    elif d:
        data = f"[{d} 유동인구]\n{_qpop(d)}\n\n[{d} 카드매출]\n{_qsales(d)}\n\n[{d} 소득]\n{_qincome(d)}"
    else:
        # district 없으면 핫플 랭킹이라도 제공
        data = f"[전체 핫플 랭킹]\n{_qhot(5)}\n\n[현재 화면]\n{pctx}" if pctx else f"[전체 핫플 랭킹]\n{_qhot(5)}"

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
- AVG_INCOME_KRW: 평균 소득 (원 단위)
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
    """질문 → 답변 (동기 처리, rerun 분리 없음)"""
    st.session_state.chat_messages.append({"role": "user", "content": q})
    r = _answer(q, st.session_state.chat_messages[:-1], pctx, sel_d)
    st.session_state.chat_messages.append({
        "role": "assistant", "content": r["answer"],
        "intent": r["intent"], "district": r.get("district", ""),
    })
    _safe_rerun()


def _get_followup(intent, district):
    d = district or "해당 동네"
    followups = {
        "simulate": [
            (f"{d} 3개월 후 상권 전망은?", f"{d} 3개월 전망"),
            (f"{d}과 비슷한 상권의 동네 비교해줘", f"{d} 유사 상권 비교"),
        ] if district else [],
        "lookup": [
            (f"{d}에서 어떤 업종이 유망할까?", f"{d} 유망 업종 추천"),
            (f"{d} 부동산 시세는 어때?", f"{d} 부동산 시세"),
        ] if district else [],
        "hotplace": [
            ("1위 동네에 카페 출점하면 매출은?", "1위 동네 카페 출점 시뮬"),
            ("핫플 동네들의 3개월 전망은?", "핫플 동네 전망 분석"),
        ],
        "forecast": [
            (f"{d} 상권을 더 자세히 분석해줘", f"{d} 상권 심층 분석"),
        ] if district else [],
        "compare": [
            ("비교한 동네 중 출점하기 더 좋은 곳은?", "출점 추천"),
        ],
        "marketing": [
            ("가장 효과적인 채널에 예산을 집중하면?", "채널 최적화 전략"),
        ],
    }
    return followups.get(intent, [])


import random
_PLACEHOLDERS = [
    "잠원동에 카페 출점하면?",
    "핫플 동네 Top 5는?",
    "신당동 vs 여의도 비교",
    "서초동 3개월 전망",
    "어디서 뭘 팔면 좋을까?",
    "영등포구 상권 분석해줘",
]


def render_sidebar_chat():
    """사이드바 AI 채팅 — 단순 구조"""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "pending_q" not in st.session_state:
        st.session_state.pending_q = None

    with st.sidebar:
        # CSS
        st.markdown("""<style>
        [data-testid="stSidebar"] table { font-size: 11px !important; }
        [data-testid="stSidebar"] .stMarkdown { overflow-x: auto; }
        [data-testid="stSidebar"] { min-width: 320px; }
        [data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem !important; }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { padding-left: 0 !important; padding-right: 0 !important; }
        [data-testid="stSidebar"] .stTextInput > div { width: 100% !important; }
        [data-testid="stSidebar"] .stButton > button { width: 100% !important; }
        </style>""", unsafe_allow_html=True)

        # ── 대화 없을 때 ──
        if not st.session_state.chat_messages:
            st.markdown("""
            <div style="text-align:center;padding:8px 8px 4px;">
                <div style="font-size:18px;font-weight:800;letter-spacing:-0.5px;">XR-AI</div>
                <div style="font-size:10px;color:#777;margin-top:2px;">상권 분석 에이전트</div>
            </div>
            <div style="background:rgba(99,102,241,0.06);padding:10px 12px;border-radius:8px;
                margin:8px 0 12px;border:1px solid rgba(99,102,241,0.1);">
                <div style="font-size:11px;color:#999;line-height:1.7;">
                    서울 118개 법정동의 유동인구, 카드매출, 소득,
                    부동산 데이터를 실시간 분석합니다.
                </div>
                <div style="font-size:9px;color:#555;margin-top:4px;">
                    SPH · 리치고 · 아정당 3개 데이터 소스 통합
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.caption("출점 분석")
            if st.button("잠원동 카페 출점 상권 분석", key="q_0", use_container_width=True):
                st.session_state.pending_q = "잠원동에 카페 출점하려는데 유동인구, 매출, 소득, 부동산 데이터로 상권 분석해줘"
            if st.button("서초구 프랜차이즈 추천 동네·업종", key="q_1", use_container_width=True):
                st.session_state.pending_q = "서초구에서 프랜차이즈 출점하기 좋은 동네와 업종은?"

            st.caption("예측 · 비교")
            if st.button("방문인구 증가율 Top 5 팝업 후보", key="q_2", use_container_width=True):
                st.session_state.pending_q = "방문인구 증가율 Top 5 동네는? 팝업 후보지 추천해줘"
            if st.button("신당동 3개월 후 상권 전망", key="q_3", use_container_width=True):
                st.session_state.pending_q = "신당동 3개월 후 상권 전망 예측해줘"

            st.caption("데이터 분석")
            if st.button("신당동 vs 여의도동 상권 비교", key="q_4", use_container_width=True):
                st.session_state.pending_q = "신당동과 여의도동의 유동인구와 매출을 비교 분석해줘"
            if st.button("마케팅 채널별 고객 유입 효과", key="q_5", use_container_width=True):
                st.session_state.pending_q = "최근 어떤 마케팅 채널의 고객 유입이 효과적인지 분석해줘"

            if st.session_state.pending_q:
                q = st.session_state.pending_q
                st.session_state.pending_q = None
                _do_ask(q, "", "")

        # ── 대화 있을 때 ──
        else:
            st.markdown("""<div style="padding:2px 0;">
                <span style="font-size:13px;font-weight:700;">XR-AI</span>
                <span style="font-size:9px;color:#555;margin-left:4px;">상권 분석</span>
            </div>""", unsafe_allow_html=True)
            st.markdown("---")

            for msg in st.session_state.chat_messages:
                if msg["role"] == "user":
                    st.markdown(f"""<div style="text-align:right;margin:8px 0 4px;">
                        <span style="background:#6366F1;color:white;padding:6px 10px;
                        border-radius:10px 10px 3px 10px;font-size:12px;display:inline-block;max-width:90%;">
                        {msg['content']}</span></div>""", unsafe_allow_html=True)
                else:
                    st.markdown(msg['content'])

            # 후속 질문
            last_msg = st.session_state.chat_messages[-1] if st.session_state.chat_messages else None
            if last_msg and last_msg["role"] == "assistant":
                followups = _get_followup(last_msg.get("intent", ""), last_msg.get("district", ""))
                if followups:
                    st.markdown("---")
                    st.markdown('<div style="font-size:10px;color:#777;margin-bottom:4px;">관련 분석</div>', unsafe_allow_html=True)
                    for i, (fq, fl) in enumerate(followups[:2]):
                        if st.button(fl, key=f"fw_{i}", use_container_width=True):
                            st.session_state.pending_q = fq
                    if st.session_state.pending_q:
                        q = st.session_state.pending_q
                        st.session_state.pending_q = None
                        _do_ask(q, "", "")

        # ── 입력 (1개만) ──
        st.markdown("---")
        placeholder = random.choice(_PLACEHOLDERS)
        inp = st.text_input("", key="ai_inp", placeholder=placeholder)
        c1, c2 = st.columns([4, 1])
        with c1:
            if st.button("전송", key="ai_send", use_container_width=True):
                if inp:
                    _do_ask(inp, "", "")
        with c2:
            if st.button("↻", key="ai_clr"):
                st.session_state.chat_messages = []
                _safe_rerun()
