"""
AI 에이전트 채팅 UI — Apple 스타일 미니멀 디자인
오른쪽 패널에 깔끔한 채팅 인터페이스
"""
import streamlit as st
import json
import re
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5-nano"
CORTEX_MODEL_HEAVY = "openai-gpt-5"


def _safe_rerun():
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()


def _cortex(prompt: str, heavy: bool = False) -> str:
    try:
        model = CORTEX_MODEL_HEAVY if heavy else CORTEX_MODEL
        safe = prompt.replace("'", "''").replace("\\", "\\\\")
        result = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{safe}') as r")
        return str(result.iloc[0, 0]) if not result.empty else "응답 실패"
    except Exception as e:
        return f"Cortex 오류: {str(e)}"


def _classify_intent(query, history_str=""):
    prompt = f"""질문을 분류. JSON만.
이전: {history_str[:300]}
질문: {query}
{{"intent":"lookup|compare|trend|simulate|recommend|hotplace","district":"법정동명|null","category":"업종|null"}}"""
    resp = _cortex(prompt)
    try:
        match = re.search(r'\{.*\}', resp, re.DOTALL)
        if match: return json.loads(match.group())
    except: pass
    return {"intent": "lookup", "district": None, "category": None}


def _query_population(district):
    try:
        safe = district.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME as name, f.STANDARD_YEAR_MONTH,
                   SUM(f.RESIDENTIAL_POPULATION) as 거주, SUM(f.WORKING_POPULATION) as 직장,
                   SUM(f.VISITING_POPULATION) as 방문,
                   SUM(f.RESIDENTIAL_POPULATION+f.WORKING_POPULATION+f.VISITING_POPULATION) as 총인구
            FROM {SPH}.FLOATING_POPULATION_INFO f JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE=m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%'
              AND f.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
            GROUP BY 1,2""")
        return df.to_string(index=False) if not df.empty else f"'{district}' 데이터 없음"
    except Exception as e: return f"오류: {e}"


def _query_sales(district, category=None):
    try:
        safe = district.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME as name,
                   SUM(TOTAL_SALES) as 총매출, SUM(FOOD_SALES) as 식음료, SUM(COFFEE_SALES) as 커피,
                   SUM(BEAUTY_SALES) as 미용, SUM(MEDICAL_SALES) as 의료, SUM(SMALL_RETAIL_STORE_SALES) as 소매
            FROM {SPH}.CARD_SALES_INFO c JOIN {SPH}.M_SCCO_MST m ON c.DISTRICT_CODE=m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%' AND c.CARD_TYPE='1'
              AND c.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.CARD_SALES_INFO)
            GROUP BY 1""")
        return df.to_string(index=False) if not df.empty else f"'{district}' 데이터 없음"
    except Exception as e: return f"오류: {e}"


def _query_income(district):
    try:
        safe = district.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME as name,
                   SUM(a.CUSTOMER_COUNT) as 고객수,
                   ROUND(SUM(a.CUSTOMER_COUNT*a.AVERAGE_INCOME)/NULLIF(SUM(a.CUSTOMER_COUNT),0),0) as 평균소득,
                   ROUND(SUM(a.CUSTOMER_COUNT*a.AVERAGE_SCORE)/NULLIF(SUM(a.CUSTOMER_COUNT),0),0) as 신용점수
            FROM {SPH}.ASSET_INCOME_INFO a JOIN {SPH}.M_SCCO_MST m ON a.DISTRICT_CODE=m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%' AND a.INCOME_TYPE=1
              AND a.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.ASSET_INCOME_INFO)
            GROUP BY 1""")
        return df.to_string(index=False) if not df.empty else f"'{district}' 데이터 없음"
    except Exception as e: return f"오류: {e}"


def _query_hotplace(top_n=10):
    try:
        df = run_query(f"""
            WITH r AS (SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) a FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH>=(SELECT MAX(STANDARD_YEAR_MONTH)-6 FROM {SPH}.FLOATING_POPULATION_INFO) GROUP BY 1),
            p AS (SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) a FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH<(SELECT MAX(STANDARD_YEAR_MONTH)-6 FROM {SPH}.FLOATING_POPULATION_INFO)
                AND STANDARD_YEAR_MONTH>=(SELECT MAX(STANDARD_YEAR_MONTH)-12 FROM {SPH}.FLOATING_POPULATION_INFO) GROUP BY 1)
            SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME as 동네,
                ROUND((r.a-p.a)/NULLIF(p.a,0)*100,1) as 증가율, ROUND(r.a,0) as 방문인구
            FROM r JOIN p ON r.DISTRICT_CODE=p.DISTRICT_CODE
            JOIN {SPH}.M_SCCO_MST m ON r.DISTRICT_CODE=m.DISTRICT_CODE
            WHERE p.a>0 ORDER BY 2 DESC LIMIT {top_n}""")
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e: return f"오류: {e}"


def _simulate(district, category="카페"):
    pop = _query_population(district)
    sales = _query_sales(district)
    income = _query_income(district)
    try:
        safe = district.replace("'", "''")
        t = run_query(f"""
            SELECT TIME_SLOT, SUM(RESIDENTIAL_POPULATION+WORKING_POPULATION+VISITING_POPULATION) as 유동인구
            FROM {SPH}.FLOATING_POPULATION_INFO f JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE=m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%'
              AND f.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
              AND f.WEEKDAY_WEEKEND='W' GROUP BY 1 ORDER BY 1""")
        td = t.to_string(index=False) if not t.empty else "없음"
    except: td = "불가"
    return f"[유동인구]\n{pop}\n\n[매출]\n{sales}\n\n[소득]\n{income}\n\n[시간대별]\n{td}"


def _answer(query, chat_history, page_context="", selected_district=""):
    hist = ""
    if chat_history:
        hist = "\n".join([f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:150]}" for m in chat_history[-6:]])

    info = _classify_intent(query, hist)
    intent = info.get("intent", "lookup")
    district = info.get("district") or selected_district or ""
    category = info.get("category")

    data = ""
    if intent == "hotplace": data = _query_hotplace()
    elif intent == "compare":
        ds = re.findall(r'(\w+[동구])', query)
        if len(ds) >= 2: data = "\n\n".join([f"=== {d} ===\n{_query_population(d)}\n{_query_sales(d)}" for d in ds[:3]])
        elif district: data = f"{_query_population(district)}\n{_query_sales(district)}"
    elif intent == "simulate": data = _simulate(district, category or "카페") if district else "지역 불명"
    elif intent == "recommend":
        data = f"{_query_sales(district)}\n{_query_income(district)}" if district else _query_hotplace(5)
    elif intent == "trend" and district:
        try:
            safe = district.replace("'", "''")
            df = run_query(f"""SELECT f.STANDARD_YEAR_MONTH,
                SUM(f.RESIDENTIAL_POPULATION+f.WORKING_POPULATION+f.VISITING_POPULATION) as 유동인구
                FROM {SPH}.FLOATING_POPULATION_INFO f JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE=m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%' GROUP BY 1 ORDER BY 1 DESC LIMIT 12""")
            data = df.to_string(index=False)
        except Exception as e: data = str(e)
    else:
        if district: data = f"{_query_population(district)}\n{_query_sales(district)}\n{_query_income(district)}"

    ctx = f"[화면] {page_context}" if page_context else ""
    prompt = f"""서울 동네 데이터 분석 전문가.
{ctx}
[데이터]
{data}
[이전대화]
{hist}
[규칙] 되묻지마. 숫자 읽기쉽게. 한국어. 데이터 기반 답변.
질문: {query}"""

    return {"answer": _cortex(prompt, intent in ("simulate","compare","recommend")), "intent": intent}


# ═══════════════════════════════════════════
# Apple 스타일 UI
# ═══════════════════════════════════════════

def inject_chat_styles():
    """Apple 스타일 CSS 주입 — 각 페이지 상단에서 1회 호출"""
    st.markdown("""
    <style>
    .chat-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 16px 20px;
        border-radius: 16px 16px 0 0;
        border: 1px solid rgba(255,255,255,0.08);
        border-bottom: none;
    }
    .chat-header h3 {
        color: white; margin: 0; font-size: 16px; font-weight: 600;
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
    }
    .chat-header .sub {
        color: rgba(255,255,255,0.4); font-size: 11px; margin-top: 4px;
    }
    .chat-body {
        background: #0d1117;
        border: 1px solid rgba(255,255,255,0.06);
        border-top: none; border-bottom: none;
        padding: 16px;
        min-height: 200px;
    }
    .msg-user {
        text-align: right; margin: 10px 0;
    }
    .msg-user span {
        background: linear-gradient(135deg, #6366F1, #8B5CF6);
        color: white; padding: 10px 16px;
        border-radius: 20px 20px 6px 20px;
        display: inline-block; max-width: 85%;
        font-size: 14px; line-height: 1.5;
        font-family: -apple-system, sans-serif;
    }
    .msg-ai {
        margin: 10px 0;
    }
    .msg-ai span {
        background: rgba(255,255,255,0.05);
        color: #e0e0e0; padding: 12px 16px;
        border-radius: 20px 20px 20px 6px;
        display: inline-block; max-width: 85%;
        font-size: 14px; line-height: 1.6;
        border: 1px solid rgba(255,255,255,0.06);
        font-family: -apple-system, sans-serif;
    }
    .msg-ai .badge {
        font-size: 10px; color: #888; margin-top: 4px; display: block;
    }
    .chat-footer {
        background: #0d1117;
        padding: 12px 16px;
        border-radius: 0 0 16px 16px;
        border: 1px solid rgba(255,255,255,0.06);
        border-top: 1px solid rgba(255,255,255,0.04);
    }
    .chat-welcome {
        text-align: center; padding: 40px 20px; color: #555;
    }
    .chat-welcome .icon { font-size: 40px; margin-bottom: 8px; }
    .chat-welcome .title {
        font-size: 16px; font-weight: 600; color: #aaa;
        font-family: -apple-system, sans-serif;
    }
    .chat-welcome .desc {
        font-size: 12px; margin-top: 6px; color: #666; line-height: 1.5;
    }
    </style>
    """, unsafe_allow_html=True)


def render_chat_panel(current_tab="", selected_district="", selected_month="", page_context=""):
    """Apple 스타일 AI 채팅 패널"""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    # 토글 버튼 (오른쪽 정렬)
    cols = st.columns([7, 1])
    with cols[1]:
        label = "🤖" if not st.session_state.chat_open else "✕"
        if st.button(label, key="ai_toggle", help="AI 에이전트", use_container_width=True):
            st.session_state.chat_open = not st.session_state.chat_open
            _safe_rerun()

    if not st.session_state.chat_open:
        return

    inject_chat_styles()

    # 헤더
    screen = page_context[:50] if page_context else current_tab
    st.markdown(f"""
    <div class="chat-header">
        <h3>🤖 AI 에이전트</h3>
        <div class="sub">📍 {screen} · Snowflake Cortex</div>
    </div>
    """, unsafe_allow_html=True)

    # 대화 영역
    st.markdown('<div class="chat-body">', unsafe_allow_html=True)

    if not st.session_state.chat_messages:
        st.markdown("""
        <div class="chat-welcome">
            <div class="icon">🏙️</div>
            <div class="title">무엇이든 물어보세요</div>
            <div class="desc">실제 데이터를 조회하여 분석합니다</div>
        </div>
        """, unsafe_allow_html=True)

        suggestions = {"유동인구": "신당동 유동인구 알려줘", "시뮬레이션": "서초동 카페 매출은?",
                       "핫플 예측": "다음 핫플은?", "비교": "중구 vs 영등포구",
                       "추천": "잠원동에서 뭘 팔면?", "추이": "신당동 추이"}
        cols = st.columns(3)
        for i, (k, v) in enumerate(suggestions.items()):
            with cols[i % 3]:
                if st.button(k, key=f"s_{i}"):
                    st.session_state.chat_messages.append({"role": "user", "content": v})
                    r = _answer(v, [], page_context, selected_district)
                    st.session_state.chat_messages.append({"role": "assistant", "content": r["answer"], "intent": r["intent"]})
                    _safe_rerun()
    else:
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.markdown(f'<div class="msg-user"><span>{msg["content"]}</span></div>', unsafe_allow_html=True)
            else:
                badges = {"lookup":"🔍 조회","compare":"⚖️ 비교","trend":"📈 추이",
                          "simulate":"🧪 시뮬","recommend":"💡 추천","hotplace":"🔥 핫플"}
                b = badges.get(msg.get("intent",""), "")
                st.markdown(f'<div class="msg-ai"><span>{msg["content"]}<span class="badge">{b}</span></span></div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # 입력 영역
    st.markdown('<div class="chat-footer">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([6, 1, 1])
    with c1:
        inp = st.text_input("ai", key="ai_input", label_visibility="collapsed", placeholder="메시지 입력...")
    with c2:
        send = st.button("↑", key="ai_send")
    with c3:
        if st.button("↻", key="ai_clear"):
            st.session_state.chat_messages = []
            _safe_rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if send and inp:
        st.session_state.chat_messages.append({"role": "user", "content": inp})
        with st.spinner(""):
            r = _answer(inp, st.session_state.chat_messages[:-1], page_context, selected_district)
        st.session_state.chat_messages.append({"role": "assistant", "content": r["answer"], "intent": r["intent"]})
        _safe_rerun()
