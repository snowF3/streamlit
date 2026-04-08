"""
AI 에이전트 — 오른쪽 패널 (각 페이지 콘텐츠 옆에 표시)
"""
import streamlit as st
import json, re
from data_loader import run_query, SPH, RICHGO, AJD

CORTEX_MODEL = "openai-gpt-5-nano"
CORTEX_MODEL_HEAVY = "openai-gpt-5"

def _safe_rerun():
    if hasattr(st,'rerun'): st.rerun()
    elif hasattr(st,'experimental_rerun'): st.experimental_rerun()

def _cortex(prompt, heavy=False):
    try:
        model = CORTEX_MODEL_HEAVY if heavy else CORTEX_MODEL
        safe = prompt.replace("'","''").replace("\\","\\\\")
        r = run_query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}','{safe}') as r")
        return str(r.iloc[0,0]) if not r.empty else "응답 실패"
    except Exception as e: return f"오류: {e}"

def _classify(q, h=""):
    p = f'질문분류.JSON만.이전:{h[:200]}질문:{q}{{"intent":"lookup|compare|trend|simulate|recommend|hotplace","district":"동명|null","category":"업종|null"}}'
    resp = _cortex(p)
    try:
        m = re.search(r'\{.*\}',resp,re.DOTALL)
        if m: return json.loads(m.group())
    except: pass
    return {"intent":"lookup","district":None,"category":None}

def _qpop(d):
    try:
        s=d.replace("'","''")
        df=run_query(f"SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME n,SUM(f.RESIDENTIAL_POPULATION)r,SUM(f.WORKING_POPULATION)w,SUM(f.VISITING_POPULATION)v,SUM(f.RESIDENTIAL_POPULATION+f.WORKING_POPULATION+f.VISITING_POPULATION)t FROM {SPH}.FLOATING_POPULATION_INFO f JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE=m.DISTRICT_CODE WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND f.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.FLOATING_POPULATION_INFO) GROUP BY 1")
        return df.to_string(index=False) if not df.empty else f"'{d}' 없음"
    except Exception as e: return str(e)

def _qsales(d):
    try:
        s=d.replace("'","''")
        df=run_query(f"SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME n,SUM(TOTAL_SALES)t,SUM(FOOD_SALES)f,SUM(COFFEE_SALES)c,SUM(BEAUTY_SALES)b FROM {SPH}.CARD_SALES_INFO c2 JOIN {SPH}.M_SCCO_MST m ON c2.DISTRICT_CODE=m.DISTRICT_CODE WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND c2.CARD_TYPE='1' AND c2.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.CARD_SALES_INFO) GROUP BY 1")
        return df.to_string(index=False) if not df.empty else f"'{d}' 없음"
    except Exception as e: return str(e)

def _qincome(d):
    try:
        s=d.replace("'","''")
        df=run_query(f"SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME n,SUM(a.CUSTOMER_COUNT)cnt,ROUND(SUM(a.CUSTOMER_COUNT*a.AVERAGE_INCOME)/NULLIF(SUM(a.CUSTOMER_COUNT),0),0)inc FROM {SPH}.ASSET_INCOME_INFO a JOIN {SPH}.M_SCCO_MST m ON a.DISTRICT_CODE=m.DISTRICT_CODE WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' AND a.INCOME_TYPE=1 AND a.STANDARD_YEAR_MONTH=(SELECT MAX(STANDARD_YEAR_MONTH) FROM {SPH}.ASSET_INCOME_INFO) GROUP BY 1")
        return df.to_string(index=False) if not df.empty else f"'{d}' 없음"
    except Exception as e: return str(e)

def _qhot(n=10):
    try:
        df=run_query(f"WITH r AS(SELECT DISTRICT_CODE,AVG(VISITING_POPULATION)a FROM {SPH}.FLOATING_POPULATION_INFO WHERE STANDARD_YEAR_MONTH>=(SELECT MAX(STANDARD_YEAR_MONTH)-6 FROM {SPH}.FLOATING_POPULATION_INFO)GROUP BY 1),p AS(SELECT DISTRICT_CODE,AVG(VISITING_POPULATION)a FROM {SPH}.FLOATING_POPULATION_INFO WHERE STANDARD_YEAR_MONTH<(SELECT MAX(STANDARD_YEAR_MONTH)-6 FROM {SPH}.FLOATING_POPULATION_INFO)AND STANDARD_YEAR_MONTH>=(SELECT MAX(STANDARD_YEAR_MONTH)-12 FROM {SPH}.FLOATING_POPULATION_INFO)GROUP BY 1)SELECT m.CITY_KOR_NAME||' '||m.DISTRICT_KOR_NAME d,ROUND((r.a-p.a)/NULLIF(p.a,0)*100,1)g FROM r JOIN p ON r.DISTRICT_CODE=p.DISTRICT_CODE JOIN {SPH}.M_SCCO_MST m ON r.DISTRICT_CODE=m.DISTRICT_CODE WHERE p.a>0 ORDER BY 2 DESC LIMIT {n}")
        return df.to_string(index=False) if not df.empty else "없음"
    except Exception as e: return str(e)

def _answer(q, hist_list, pctx="", sel_d=""):
    hist = "\n".join([f"{'U' if m['role']=='user' else 'A'}: {m['content'][:100]}" for m in hist_list[-4:]]) if hist_list else ""
    info = _classify(q, hist)
    intent,d,cat = info.get("intent","lookup"), info.get("district") or sel_d or "", info.get("category")
    data = ""
    if intent=="hotplace": data=_qhot()
    elif intent=="compare":
        ds=re.findall(r'(\w+[동구])',q)
        data="\n".join([f"={x}=\n{_qpop(x)}\n{_qsales(x)}" for x in (ds[:3] if len(ds)>=2 else [d] if d else [])]) or "비교대상없음"
    elif intent=="simulate" and d: data=f"{_qpop(d)}\n{_qsales(d)}\n{_qincome(d)}"
    elif intent=="recommend": data=(_qsales(d)+"\n"+_qincome(d)) if d else _qhot(5)
    elif intent=="trend" and d:
        try:
            s=d.replace("'","''")
            df=run_query(f"SELECT STANDARD_YEAR_MONTH,SUM(RESIDENTIAL_POPULATION+WORKING_POPULATION+VISITING_POPULATION)t FROM {SPH}.FLOATING_POPULATION_INFO f JOIN {SPH}.M_SCCO_MST m ON f.DISTRICT_CODE=m.DISTRICT_CODE WHERE m.DISTRICT_KOR_NAME LIKE '%{s}%' GROUP BY 1 ORDER BY 1 DESC LIMIT 12")
            data=df.to_string(index=False)
        except: pass
    elif d: data=f"{_qpop(d)}\n{_qsales(d)}\n{_qincome(d)}"
    ctx=f"[화면]{pctx}" if pctx else ""
    prompt=f"서울동네데이터분석전문가.{ctx}\n[데이터]{data}\n[이전대화]{hist}\n규칙:되묻지마.숫자읽기쉽게.한국어.데이터기반답변.\n질문:{q}"
    return {"answer":_cortex(prompt,intent in("simulate","compare","recommend")),"intent":intent}


# ═══════════════════════════════════════════
# 오른쪽 채팅 패널
# ═══════════════════════════════════════════

def get_chat_layout(page_context="", selected_district=""):
    """
    페이지 시작 시 호출. 채팅 열림 여부에 따라 레이아웃 반환.

    사용법 (각 페이지에서):
        from chat_ui import get_chat_layout
        content_col = get_chat_layout(page_context="동네 지도 - ...")
        with content_col:
            # 기존 페이지 콘텐츠 전부
    """
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    # 채팅 닫혀있으면: 오른쪽에 작은 버튼만
    if not st.session_state.chat_open:
        content_col, btn_col = st.columns([20, 1])
        with btn_col:
            if st.button("🤖", key="chat_open_btn", help="AI 에이전트 열기"):
                st.session_state.chat_open = True
                _safe_rerun()
        return content_col

    # 채팅 열려있으면: [콘텐츠 | 채팅] 레이아웃
    content_col, chat_col = st.columns([3, 1])

    with chat_col:
        # 닫기 버튼
        if st.button("✕", key="chat_close_btn", help="닫기"):
            st.session_state.chat_open = False
            _safe_rerun()

        # 헤더
        st.markdown("""<div style="background:linear-gradient(135deg,#6366F1,#8B5CF6);
            padding:10px 12px;border-radius:8px;margin-bottom:8px;">
            <span style="color:white;font-size:12px;font-weight:700;">🤖 AI</span>
            <span style="color:rgba(255,255,255,0.5);font-size:9px;float:right;">Cortex</span>
        </div>""", unsafe_allow_html=True)

        # 컨텍스트
        if page_context:
            st.caption(f"📍 {page_context[:30]}")

        # 추천 질문
        if not st.session_state.chat_messages:
            if st.button("🔍 유동인구", key="q_0"): _do_ask("신당동 유동인구 알려줘", page_context, selected_district)
            if st.button("🧪 시뮬", key="q_1"): _do_ask("서초동 카페 매출?", page_context, selected_district)
            if st.button("🔥 핫플", key="q_2"): _do_ask("다음 핫플은?", page_context, selected_district)
            if st.button("⚖️ 비교", key="q_3"): _do_ask("중구 vs 영등포구", page_context, selected_district)

        # 대화
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.markdown(f"**🧑 {msg['content']}**")
            else:
                badges = {"lookup":"🔍","compare":"⚖️","trend":"📈","simulate":"🧪","recommend":"💡","hotplace":"🔥"}
                b = badges.get(msg.get("intent",""),"")
                st.markdown(f"{b} {msg['content']}")
                st.markdown("---")

        # 입력
        inp = st.text_input("질문", key="ai_in", label_visibility="collapsed", placeholder="물어보세요...")
        c1, c2 = st.columns([3, 1])
        with c1:
            if st.button("→", key="ai_send"):
                if inp:
                    _do_ask(inp, page_context, selected_district)
        with c2:
            if st.button("↻", key="ai_clr"):
                st.session_state.chat_messages = []
                _safe_rerun()

    return content_col


def _do_ask(q, pctx, sel_d):
    st.session_state.chat_messages.append({"role":"user","content":q})
    r = _answer(q, st.session_state.chat_messages[:-1], pctx, sel_d)
    st.session_state.chat_messages.append({"role":"assistant","content":r["answer"],"intent":r["intent"]})
    _safe_rerun()


def render_chat_panel(current_tab="", selected_district="", selected_month="", page_context=""):
    """하위 호환용 — 기존 페이지에서 호출 시 아무것도 안 함 (get_chat_layout으로 대체)"""
    pass
