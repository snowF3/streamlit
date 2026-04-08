"""
AI 에이전트 채팅 UI — Snowflake Cortex 네이티브 버전
Snowflake SiS 구버전 호환 (st.rerun, st.chat_message 없음)
"""
import streamlit as st
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5-nano"


def _safe_rerun():
    """Streamlit 버전 호환 rerun"""
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()


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
    return "\n".join(ctx_parts)


def _answer_question(query: str, chat_history: list, page_context: str = "", district: str = "") -> dict:
    context = _build_context(district, page_context)
    history_str = ""
    if chat_history:
        recent = chat_history[-6:]
        history_str = "\n".join([f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:200]}" for m in recent])

    system_prompt = f"""당신은 서울 동네 데이터 분석 전문가 AI입니다.
사용 가능한 데이터: 서울 118개 법정동(중구/영등포구/서초구)의 유동인구, 카드매출(20개 업종), 소득/자산, 부동산 시세

{context}

[이전 대화]
{history_str}

[규칙]
- 절대 되묻지 말고 이전 대화에서 파악하세요
- 숫자는 읽기 쉽게 (1,234명, 3.5억원)
- 한국어로 답변

사용자 질문: {query}"""

    response = _cortex_complete(system_prompt)
    return {"answer": response}


def render_chat_panel(current_tab: str = "", selected_district: str = "", selected_month: str = "", page_context: str = ""):
    """Snowflake SiS 구버전 호환 채팅 패널"""

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    # ── 토글 버튼 ──
    st.markdown("---")
    c1, c2 = st.columns([1, 5])
    with c1:
        btn_label = "🤖 AI 열기" if not st.session_state.chat_open else "✕ 닫기"
        if st.button(btn_label, key="sf_chat_toggle"):
            st.session_state.chat_open = not st.session_state.chat_open
            _safe_rerun()
    with c2:
        if not st.session_state.chat_open:
            st.caption("🤖 AI 에이전트에게 데이터를 물어보세요")

    if not st.session_state.chat_open:
        return

    # ── 헤더 ──
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#6366F1,#8B5CF6);padding:14px 18px;border-radius:12px 12px 0 0;">
        <span style="color:white;font-size:15px;font-weight:700;">🤖 동네 엑스레이 AI</span>
        <span style="color:rgba(255,255,255,0.6);font-size:11px;margin-left:8px;">
            🟢 Cortex · {CORTEX_MODEL}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # ── 대화 영역 (st.chat_message 대신 markdown 사용) ──
    if not st.session_state.chat_messages:
        st.markdown("""
        <div style="text-align:center;padding:30px 20px;color:#888;">
            <div style="font-size:36px;margin-bottom:8px;">🏙️</div>
            <div style="font-size:14px;font-weight:600;">동네 데이터, 무엇이든 물어보세요</div>
        </div>
        """, unsafe_allow_html=True)

        suggestions = ["신당동 유동인구 알려줘", "서초동에 카페 차리면?", "다음 핫플은 어디야?", "중구 vs 영등포구 비교"]
        cols_s = st.columns(2)
        for i, s in enumerate(suggestions):
            with cols_s[i % 2]:
                if st.button(s, key=f"sf_sug_{i}"):
                    st.session_state.chat_messages.append({"role": "user", "content": s})
                    result = _answer_question(s, [], page_context, selected_district)
                    st.session_state.chat_messages.append({"role": "assistant", "content": result["answer"]})
                    _safe_rerun()
    else:
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.markdown(f"""
                <div style="text-align:right;margin:8px 0;">
                    <span style="background:#6366F1;color:white;padding:8px 14px;border-radius:16px 16px 4px 16px;display:inline-block;max-width:80%;font-size:13px;">
                        🧑 {msg['content']}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="margin:8px 0;">
                    <span style="background:#2a2a4a;color:#E0E0E0;padding:10px 14px;border-radius:16px 16px 16px 4px;display:inline-block;max-width:85%;font-size:13px;line-height:1.6;">
                        🤖 {msg['content']}
                    </span>
                </div>
                """, unsafe_allow_html=True)

    # ── 입력 ──
    c_inp, c_clr = st.columns([6, 1])
    with c_clr:
        if st.button("🗑️", key="sf_clear", help="초기화"):
            st.session_state.chat_messages = []
            _safe_rerun()

    user_input = st.text_input("무엇이든 물어보세요...", key="sf_chat_input", label_visibility="collapsed")
    if st.button("전송", key="sf_send") and user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.spinner("Cortex 분석 중..."):
            result = _answer_question(user_input, st.session_state.chat_messages[:-1], page_context, selected_district)
        st.session_state.chat_messages.append({"role": "assistant", "content": result["answer"]})
        _safe_rerun()
