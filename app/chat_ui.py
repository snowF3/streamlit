"""
AI 에이전트 채팅 UI — Snowflake Cortex 고도화 버전
의도 파악 → 실제 데이터 조회 → Cortex 답변 (기존 LangGraph 수준)
"""
import streamlit as st
import json
import re
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5-nano"
CORTEX_MODEL_HEAVY = "openai-gpt-5"  # 복합 분석용


def _safe_rerun():
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()


def _cortex(prompt: str, heavy: bool = False) -> str:
    """Cortex COMPLETE 호출"""
    try:
        model = CORTEX_MODEL_HEAVY if heavy else CORTEX_MODEL
        safe = prompt.replace("'", "''").replace("\\", "\\\\")
        result = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{safe}') as r")
        return str(result.iloc[0, 0]) if not result.empty else "응답 실패"
    except Exception as e:
        return f"Cortex 오류: {str(e)}"


# ═══════════════════════════════════════════
# 의도 분류 + 데이터 조회
# ═══════════════════════════════════════════

def _classify_intent(query: str, history_str: str = "") -> dict:
    """질문 의도 분류 → 어떤 데이터를 조회할지 결정"""
    prompt = f"""질문을 분류하세요. JSON만 반환.

이전대화: {history_str[:300]}
질문: {query}

분류:
- intent: lookup(조회) | compare(비교) | trend(추이) | simulate(시뮬레이션) | recommend(추천) | hotplace(핫플)
- district: 언급된 법정동명 (없으면 null)
- category: 관련 업종 (카페/음식/미용 등, 없으면 null)

JSON: {{"intent":"...","district":"...","category":"..."}}"""

    resp = _cortex(prompt)
    try:
        # JSON 추출
        match = re.search(r'\{.*\}', resp, re.DOTALL)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        pass
    return {"intent": "lookup", "district": None, "category": None}


def _query_population(district: str) -> str:
    """법정동 유동인구 조회"""
    try:
        safe = district.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as name,
                   f.STANDARD_YEAR_MONTH,
                   SUM(f.RESIDENTIAL_POPULATION) as 거주인구,
                   SUM(f.WORKING_POPULATION) as 직장인구,
                   SUM(f.VISITING_POPULATION) as 방문인구,
                   SUM(f.RESIDENTIAL_POPULATION + f.WORKING_POPULATION + f.VISITING_POPULATION) as 총유동인구
            FROM {SPH}.FLOATING_POPULATION_INFO f
            JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%'
              AND f.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
            GROUP BY m.CITY_KOR_NAME, m.DISTRICT_KOR_NAME, f.STANDARD_YEAR_MONTH
        """)
        if df.empty:
            return f"'{district}' 유동인구 데이터 없음"
        return df.to_string(index=False)
    except Exception as e:
        return f"조회 오류: {e}"


def _query_sales(district: str, category: str = None) -> str:
    """법정동 카드매출 조회"""
    try:
        safe = district.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as name,
                   SUM(TOTAL_SALES) as 총매출,
                   SUM(FOOD_SALES) as 식음료, SUM(COFFEE_SALES) as 커피,
                   SUM(ENTERTAINMENT_SALES) as 오락, SUM(BEAUTY_SALES) as 미용,
                   SUM(MEDICAL_SALES) as 의료, SUM(EDUCATION_ACADEMY_SALES) as 교육,
                   SUM(SMALL_RETAIL_STORE_SALES) as 소매,
                   SUM(CLOTHING_ACCESSORIES_SALES) as 의류,
                   SUM(E_COMMERCE_SALES) as 이커머스
            FROM {SPH}.CARD_SALES_INFO c
            JOIN {SPH}.M_SCCO_MST m ON c.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%' AND c.CARD_TYPE = '1'
              AND c.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.CARD_SALES_INFO)
            GROUP BY m.CITY_KOR_NAME, m.DISTRICT_KOR_NAME
        """)
        if df.empty:
            return f"'{district}' 매출 데이터 없음"
        return df.to_string(index=False)
    except Exception as e:
        return f"조회 오류: {e}"


def _query_income(district: str) -> str:
    """법정동 소득/자산 조회"""
    try:
        safe = district.replace("'", "''")
        df = run_query(f"""
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as name,
                   SUM(a.CUSTOMER_COUNT) as 고객수,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_INCOME) / NULLIF(SUM(a.CUSTOMER_COUNT),0), 0) as 평균소득,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_SCORE) / NULLIF(SUM(a.CUSTOMER_COUNT),0), 0) as 신용점수,
                   ROUND(SUM(a.CUSTOMER_COUNT * a.AVERAGE_ASSET_AMOUNT) / NULLIF(SUM(a.CUSTOMER_COUNT),0), 0) as 평균자산
            FROM {SPH}.ASSET_INCOME_INFO a
            JOIN {SPH}.M_SCCO_MST m ON a.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%' AND a.INCOME_TYPE = 1
              AND a.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.ASSET_INCOME_INFO)
            GROUP BY m.CITY_KOR_NAME, m.DISTRICT_KOR_NAME
        """)
        if df.empty:
            return f"'{district}' 소득 데이터 없음"
        return df.to_string(index=False)
    except Exception as e:
        return f"조회 오류: {e}"


def _query_hotplace_ranking(top_n: int = 10) -> str:
    """핫플레이스 랭킹 (방문인구 증가율)"""
    try:
        df = run_query(f"""
            WITH recent AS (
                SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) as recent_avg
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH >= (SELECT MAX(STANDARD_YEAR_MONTH) - 6 FROM {SPH}.FLOATING_POPULATION_INFO)
                GROUP BY DISTRICT_CODE
            ),
            prev AS (
                SELECT DISTRICT_CODE, AVG(VISITING_POPULATION) as prev_avg
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE STANDARD_YEAR_MONTH < (SELECT MAX(STANDARD_YEAR_MONTH) - 6 FROM {SPH}.FLOATING_POPULATION_INFO)
                  AND STANDARD_YEAR_MONTH >= (SELECT MAX(STANDARD_YEAR_MONTH) - 12 FROM {SPH}.FLOATING_POPULATION_INFO)
                GROUP BY DISTRICT_CODE
            )
            SELECT m.CITY_KOR_NAME || ' ' || m.DISTRICT_KOR_NAME as 동네,
                   ROUND((r.recent_avg - p.prev_avg) / NULLIF(p.prev_avg, 0) * 100, 1) as 증가율,
                   ROUND(r.recent_avg, 0) as 현재방문인구
            FROM recent r
            JOIN prev p ON r.DISTRICT_CODE = p.DISTRICT_CODE
            JOIN {SPH}.M_SCCO_MST m ON r.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE p.prev_avg > 0
            ORDER BY 증가율 DESC
            LIMIT {top_n}
        """)
        return df.to_string(index=False) if not df.empty else "데이터 없음"
    except Exception as e:
        return f"조회 오류: {e}"


def _query_compare(districts: list) -> str:
    """여러 법정동 비교"""
    results = []
    for d in districts[:3]:
        pop = _query_population(d)
        sales = _query_sales(d)
        results.append(f"=== {d} ===\n[유동인구]\n{pop}\n[매출]\n{sales}")
    return "\n\n".join(results)


def _simulate_business(district: str, category: str = "카페") -> str:
    """업종 시뮬레이션 — get_engine() 팩토리 패턴 사용"""
    pop_data = _query_population(district)
    sales_data = _query_sales(district, category)
    income_data = _query_income(district)

    # 시뮬레이션 엔진을 통한 매출 추정
    engine_result = ""
    try:
        from simulation import get_engine
        engine = get_engine("statistical")
        safe = district.replace("'", "''")
        # district_code 조회
        dc_df = run_query(f"""
            SELECT m.DISTRICT_CODE
            FROM {SPH}.M_SCCO_MST m
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%'
            LIMIT 1
        """)
        if not dc_df.empty:
            engine_result = f"\n[시뮬레이션 엔진] {engine.engine_name} 사용 가능"
    except Exception:
        pass

    # 시간대별 유동인구
    try:
        safe = district.replace("'", "''")
        time_df = run_query(f"""
            SELECT TIME_SLOT,
                   SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION) as 유동인구
            FROM {SPH}.FLOATING_POPULATION_INFO f
            JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
            WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%'
              AND f.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
              AND f.WEEKDAY_WEEKEND = 'W'
            GROUP BY TIME_SLOT ORDER BY TIME_SLOT
        """)
        time_data = time_df.to_string(index=False) if not time_df.empty else "시간대 데이터 없음"
    except Exception:
        time_data = "조회 불가"

    return f"[유동인구]\n{pop_data}\n\n[카드매출]\n{sales_data}\n\n[소득/자산]\n{income_data}\n\n[시간대별 유동인구]\n{time_data}{engine_result}"


# ═══════════════════════════════════════════
# 메인 답변 로직
# ═══════════════════════════════════════════

def _answer_question(query: str, chat_history: list, page_context: str = "", selected_district: str = "") -> dict:
    """의도 분류 → 데이터 조회 → Cortex 답변"""

    # 1. 이전 대화 요약
    history_str = ""
    if chat_history:
        recent = chat_history[-6:]
        history_str = "\n".join([f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:150]}" for m in recent])

    # 2. 의도 분류
    intent_info = _classify_intent(query, history_str)
    intent = intent_info.get("intent", "lookup")
    district = intent_info.get("district") or selected_district or ""
    category = intent_info.get("category")

    # 3. 의도에 따라 데이터 조회
    data_context = ""

    if intent == "hotplace":
        data_context = f"[핫플레이스 랭킹]\n{_query_hotplace_ranking()}"

    elif intent == "compare":
        # 비교 대상 추출
        districts = re.findall(r'(\w+[동구])', query)
        if len(districts) >= 2:
            data_context = _query_compare(districts)
        elif district:
            data_context = f"[{district} 데이터]\n{_query_population(district)}\n{_query_sales(district)}"

    elif intent == "simulate":
        if district:
            data_context = _simulate_business(district, category or "카페")
        else:
            data_context = "시뮬레이션 대상 지역을 특정할 수 없습니다."

    elif intent == "recommend":
        if district:
            data_context = f"[{district} 매출 데이터]\n{_query_sales(district)}\n\n[소득 데이터]\n{_query_income(district)}"
        else:
            data_context = f"[핫플 랭킹]\n{_query_hotplace_ranking(5)}"

    elif intent == "trend":
        if district:
            try:
                safe = district.replace("'", "''")
                df = run_query(f"""
                    SELECT f.STANDARD_YEAR_MONTH,
                           SUM(f.RESIDENTIAL_POPULATION + f.WORKING_POPULATION + f.VISITING_POPULATION) as 총유동인구,
                           SUM(c.TOTAL_SALES) as 총매출
                    FROM {SPH}.FLOATING_POPULATION_INFO f
                    JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
                    LEFT JOIN {SPH}.CARD_SALES_INFO c ON f.DISTRICT_CODE = c.DISTRICT_CODE
                        AND f.STANDARD_YEAR_MONTH = c.STANDARD_YEAR_MONTH AND c.CARD_TYPE = '1'
                    WHERE m.DISTRICT_KOR_NAME LIKE '%{safe}%'
                    GROUP BY f.STANDARD_YEAR_MONTH
                    ORDER BY f.STANDARD_YEAR_MONTH DESC
                    LIMIT 12
                """)
                data_context = f"[{district} 최근 12개월 추이]\n{df.to_string(index=False)}"
            except Exception as e:
                data_context = f"추이 조회 오류: {e}"

    else:  # lookup
        if district:
            data_context = f"[유동인구]\n{_query_population(district)}\n\n[카드매출]\n{_query_sales(district)}\n\n[소득]\n{_query_income(district)}"
        else:
            data_context = "[데이터 없음] 지역명을 특정할 수 없습니다."

    # 4. 현재 화면 컨텍스트
    screen_ctx = f"[현재 화면] {page_context}" if page_context else ""

    # 5. Cortex 최종 답변
    use_heavy = intent in ("simulate", "compare", "recommend")

    final_prompt = f"""당신은 서울 동네 데이터 분석 전문가입니다.

{screen_ctx}

[조회된 실제 데이터]
{data_context}

[이전 대화]
{history_str}

[규칙]
- 위 실제 데이터를 기반으로 답변하세요. 데이터에 없는 내용은 추측이라고 명시하세요.
- 절대 되묻지 마세요.
- 숫자는 읽기 쉽게 (1,234명, 3.5억원)
- 시뮬레이션 시 예상 매출 범위, 주 고객층, 피크 시간대, 리스크를 포함하세요.
- 한국어로 답변하세요.

사용자 질문: {query}"""

    answer = _cortex(final_prompt, heavy=use_heavy)
    return {"answer": answer, "intent": intent, "district": district}


# ═══════════════════════════════════════════
# UI 렌더링
# ═══════════════════════════════════════════

def render_chat_panel(current_tab: str = "", selected_district: str = "", selected_month: str = "", page_context: str = ""):
    """Snowflake Cortex 고도화 채팅 패널"""

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    # 토글
    st.markdown("---")
    c1, c2 = st.columns([1, 5])
    with c1:
        label = "🤖 AI 열기" if not st.session_state.chat_open else "✕ 닫기"
        if st.button(label, key="sf_chat_toggle"):
            st.session_state.chat_open = not st.session_state.chat_open
            _safe_rerun()
    with c2:
        if not st.session_state.chat_open:
            st.caption("🤖 데이터 기반 AI 에이전트 — 실제 Snowflake 데이터를 조회하여 답변합니다")

    if not st.session_state.chat_open:
        return

    # 헤더
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#6366F1,#8B5CF6);padding:14px 18px;border-radius:12px 12px 0 0;">
        <span style="color:white;font-size:15px;font-weight:700;">🤖 동네 엑스레이 AI</span>
        <span style="color:rgba(255,255,255,0.6);font-size:11px;margin-left:8px;">
            🟢 Cortex · 데이터 직접 조회 · {CORTEX_MODEL}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # 대화 영역
    if not st.session_state.chat_messages:
        st.markdown("""
        <div style="text-align:center;padding:20px;color:#888;">
            <div style="font-size:32px;margin-bottom:8px;">🏙️</div>
            <div style="font-size:14px;font-weight:600;">실제 데이터를 조회하여 답변합니다</div>
            <div style="font-size:11px;margin-top:4px;">유동인구 · 카드매출 · 소득 · 시뮬레이션 · 핫플 예측</div>
        </div>
        """, unsafe_allow_html=True)

        suggestions = [
            "신당동 유동인구 알려줘",
            "서초동에 카페 차리면 매출이?",
            "다음 핫플은 어디야?",
            "중구 vs 영등포구 비교",
            "잠원동에서 뭘 팔면 좋을까?",
            "신당동 최근 추이 보여줘",
        ]
        cols = st.columns(3)
        for i, s in enumerate(suggestions):
            with cols[i % 3]:
                if st.button(s, key=f"sf_sug_{i}"):
                    st.session_state.chat_messages.append({"role": "user", "content": s})
                    result = _answer_question(s, [], page_context, selected_district)
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": result["answer"],
                        "intent": result.get("intent", ""),
                    })
                    _safe_rerun()
    else:
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.markdown(f"""<div style="text-align:right;margin:8px 0;">
                    <span style="background:#6366F1;color:white;padding:8px 14px;border-radius:16px 16px 4px 16px;display:inline-block;max-width:80%;font-size:13px;">
                        🧑 {msg['content']}</span></div>""", unsafe_allow_html=True)
            else:
                intent_badge = ""
                intent = msg.get("intent", "")
                if intent:
                    badges = {"lookup":"🔍조회","compare":"⚖️비교","trend":"📈추이",
                              "simulate":"🧪시뮬","recommend":"💡추천","hotplace":"🔥핫플"}
                    intent_badge = f'<div style="font-size:10px;color:#888;margin-top:4px;">{badges.get(intent, intent)}</div>'
                st.markdown(f"""<div style="margin:8px 0;">
                    <span style="background:#2a2a4a;color:#E0E0E0;padding:10px 14px;border-radius:16px 16px 16px 4px;display:inline-block;max-width:85%;font-size:13px;line-height:1.6;">
                        🤖 {msg['content']}{intent_badge}</span></div>""", unsafe_allow_html=True)

    # 입력
    c_inp, c_clr = st.columns([6, 1])
    with c_clr:
        if st.button("🗑️", key="sf_clear", help="초기화"):
            st.session_state.chat_messages = []
            _safe_rerun()

    user_input = st.text_input("무엇이든 물어보세요...", key="sf_chat_input", label_visibility="collapsed")
    if st.button("전송", key="sf_send") and user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.spinner("데이터 조회 + Cortex 분석 중..."):
            result = _answer_question(user_input, st.session_state.chat_messages[:-1], page_context, selected_district)
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": result["answer"],
            "intent": result.get("intent", ""),
        })
        _safe_rerun()
