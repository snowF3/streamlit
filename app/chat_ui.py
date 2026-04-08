"""
AI 에이전트 채팅 UI — Snowflake Cortex 네이티브 버전
Cortex COMPLETE로 직접 LLM 호출 (FastAPI 서버 불필요)
"""
import streamlit as st
from data_loader import run_query, SPH, RICHGO, AJD

# Snowflake에서 사용 가능한 가장 저렴한 모델
CORTEX_MODEL = "openai-gpt-5-nano"


def _cortex_complete(prompt: str) -> str:
    """Snowflake Cortex COMPLETE 호출"""
    try:
        safe_prompt = prompt.replace("'", "''").replace("\\", "\\\\")
        result = run_query(f"""
            SELECT SNOWFLAKE.CORTEX.COMPLETE(
                '{CORTEX_MODEL}',
                '{safe_prompt}'
            ) as response
        """)
        if not result.empty:
            return str(result.iloc[0, 0])
        return "응답을 생성하지 못했습니다."
    except Exception as e:
        return f"Cortex 호출 오류: {str(e)}"


def _build_context(district_name: str = "", page_context: str = "") -> str:
    """현재 화면 + 관련 데이터를 컨텍스트로 구성"""
    ctx_parts = []
    if page_context:
        ctx_parts.append(f"[현재 화면] {page_context}")

    if district_name:
        try:
            safe_name = district_name.replace("'", "''")
            pop = run_query(f"""
                SELECT SUM(RESIDENTIAL_POPULATION) as res, SUM(WORKING_POPULATION) as work,
                       SUM(VISITING_POPULATION) as visit
                FROM {SPH}.FLOATING_POPULATION_INFO f
                JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE = m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME = '{safe_name}'
                  AND f.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO)
            """)
            if not pop.empty and pop.iloc[0, 0] is not None:
                ctx_parts.append(f"[유동인구] 거주:{pop.iloc[0,0]:,.0f} 직장:{pop.iloc[0,1]:,.0f} 방문:{pop.iloc[0,2]:,.0f}")
        except Exception:
            pass

        try:
            safe_name = district_name.replace("'", "''")
            sales = run_query(f"""
                SELECT SUM(TOTAL_SALES) as total, SUM(COFFEE_SALES) as coffee, SUM(FOOD_SALES) as food
                FROM {SPH}.CARD_SALES_INFO c
                JOIN {SPH}.M_SCCO_MST m ON c.DISTRICT_CODE = m.DISTRICT_CODE
                WHERE m.DISTRICT_KOR_NAME = '{safe_name}' AND c.CARD_TYPE = '1'
                  AND c.STANDARD_YEAR_MONTH = (SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.CARD_SALES_INFO)
            """)
            if not sales.empty and sales.iloc[0, 0] is not None:
                ctx_parts.append(f"[카드매출] 총:{sales.iloc[0,0]/1e8:,.1f}억 커피:{sales.iloc[0,1]/1e4:,.0f}만 음식:{sales.iloc[0,2]/1e4:,.0f}만")
        except Exception:
            pass

    return "\n".join(ctx_parts)


def _answer_question(query: str, chat_history: list, page_context: str = "", district: str = "") -> dict:
    """사용자 질문에 대한 답변 생성"""
    context = _build_context(district, page_context)

    history_str = ""
    if chat_history:
        recent = chat_history[-6:]
        history_str = "\n".join([f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:200]}" for m in recent])

    system_prompt = f"""당신은 서울 동네 데이터 분석 전문가 AI입니다.

사용 가능한 데이터: 서울 118개 법정동(중구/영등포구/서초구)의 유동인구, 카드매출(20개 업종), 소득/자산, 부동산 시세, 인터넷/렌탈 계약 데이터

{context}

[이전 대화]
{history_str}

[규칙]
- 절대 사용자에게 지역이나 기준을 되묻지 마세요. 이전 대화나 현재 화면에서 파악하세요.
- 숫자는 읽기 쉽게 포맷하세요 (1,234명, 3.5억원)
- 데이터 근거를 명시하세요
- 한국어로 답변하세요

사용자 질문: {query}"""

    response = _cortex_complete(system_prompt)
    return {"answer": response, "cost": 0}


def render_chat_panel(current_tab: str = "", selected_district: str = "", selected_month: str = "", page_context: str = ""):
    """Snowflake Cortex 기반 채팅 패널 — Snowflake SiS 호환"""

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    # ── 토글 버튼 (항상 표시) ──
    st.divider()
    col_toggle, col_status = st.columns([1, 5])
    with col_toggle:
        btn_label = "🤖 AI 열기" if not st.session_state.chat_open else "✕ 닫기"
        if st.button(btn_label, key="sf_chat_toggle", use_container_width=True):
            st.session_state.chat_open = not st.session_state.chat_open
            st.rerun()
    with col_status:
        if not st.session_state.chat_open:
            st.caption("🤖 AI 에이전트에게 데이터를 물어보세요")

    if not st.session_state.chat_open:
        return

    # ── 헤더 ──
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#6366F1,#8B5CF6);padding:14px 18px;border-radius:12px 12px 0 0;">
        <span style="color:white;font-size:15px;font-weight:700;">🤖 동네 엑스레이 AI</span>
        <span style="color:rgba(255,255,255,0.6);font-size:11px;margin-left:8px;">
            🟢 Cortex 연결됨 · 모델: {CORTEX_MODEL}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # ── 대화 영역 ──
    if not st.session_state.chat_messages:
        st.markdown("""
        <div style="text-align:center;padding:30px 20px;color:#888;">
            <div style="font-size:36px;margin-bottom:8px;">🏙️</div>
            <div style="font-size:14px;font-weight:600;">동네 데이터, 무엇이든 물어보세요</div>
            <div style="font-size:11px;margin-top:6px;">Snowflake Cortex가 직접 분석합니다</div>
        </div>
        """, unsafe_allow_html=True)

        suggestions = ["신당동 유동인구 알려줘", "서초동에 카페 차리면?", "다음 핫플은 어디야?", "중구 vs 영등포구 비교"]
        cols_s = st.columns(2)
        for i, s in enumerate(suggestions):
            with cols_s[i % 2]:
                if st.button(s, key=f"sf_sug_{i}", use_container_width=True):
                    st.session_state.chat_messages.append({"role": "user", "content": s})
                    result = _answer_question(s, st.session_state.chat_messages[:-1], page_context, selected_district)
                    st.session_state.chat_messages.append({"role": "assistant", "content": result["answer"]})
                    st.rerun()
    else:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
                st.markdown(msg["content"])

    # ── 입력 ──
    col_inp, col_clr = st.columns([6, 1])
    with col_clr:
        if st.button("🗑️", key="sf_clear", help="대화 초기화"):
            st.session_state.chat_messages = []
            st.rerun()

    if prompt := st.chat_input("무엇이든 물어보세요...", key="sf_chat_input"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.spinner("Cortex 분석 중..."):
            result = _answer_question(prompt, st.session_state.chat_messages[:-1], page_context, selected_district)
        st.session_state.chat_messages.append({"role": "assistant", "content": result["answer"]})
        st.rerun()
