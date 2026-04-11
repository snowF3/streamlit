"""
AI 에이전트 — 오른쪽 사이드바 채팅 (Streamlit 1.22.0 호환)
CSS로 사이드바를 오른쪽으로 이동 + 채팅 전용으로 사용
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
    ctx=f"[현재화면]{pctx}" if pctx else ""
    prompt=f"""서울 동네 데이터 분석 전문가입니다.
{ctx}
[조회된 실제 데이터]
{data}
[이전 대화]
{hist}
[규칙]
- 실제 데이터 기반 답변. 없으면 추측 명시.
- 절대 되묻지 마세요.
- 숫자 읽기 쉽게 (1,234명, 3.5억원)
- 한국어 답변
질문: {q}"""
    return {"answer":_cortex(prompt,intent in("simulate","compare","recommend")),"intent":intent}


def _do_ask(q, pctx, sel_d):
    st.session_state.chat_messages.append({"role":"user","content":q})
    r = _answer(q, st.session_state.chat_messages[:-1], pctx, sel_d)
    st.session_state.chat_messages.append({"role":"assistant","content":r["answer"],"intent":r["intent"]})
    _safe_rerun()


# ═══════════════════════════════════════════
# 메인 함수 — 각 페이지 끝에서 호출
# ═══════════════════════════════════════════

def render_sidebar_chat():
    """
    사이드바 전용 AI 채팅 — main.py에서 1회 호출.
    사이드바가 AI 전용이므로 네비게이션 없이 깔끔.
    """
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    with st.sidebar:
        # 헤더
        st.markdown("""<div style="background:linear-gradient(135deg,#6366F1,#8B5CF6);
            padding:14px 18px;border-radius:12px;margin-bottom:14px;">
            <div style="color:white;font-size:16px;font-weight:700;">🤖 AI 에이전트</div>
            <div style="color:rgba(255,255,255,0.5);font-size:10px;margin-top:2px;">
                Snowflake Cortex · 실제 데이터 조회
            </div>
        </div>""", unsafe_allow_html=True)

        # 추천 질문 (대화 없을 때)
        if not st.session_state.chat_messages:
            st.markdown("**💡 추천 질문**")
            qs = {
                "🔍 유동인구 조회": "신당동 유동인구 알려줘",
                "🧪 카페 시뮬레이션": "서초동에 카페 차리면 매출이?",
                "🔥 핫플 예측": "다음 핫플은 어디야?",
                "⚖️ 동네 비교": "중구 vs 영등포구 비교",
                "💡 업종 추천": "잠원동에서 뭘 팔면 좋을까?",
                "📈 추이 분석": "신당동 최근 추이 보여줘",
            }
            for k, v in qs.items():
                if st.button(k, key=f"q_{k}", use_container_width=True):
                    _do_ask(v, "", "")

        # 대화 히스토리
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.markdown(f"**🧑 {msg['content']}**")
            else:
                badges = {"lookup":"🔍","compare":"⚖️","trend":"📈","simulate":"🧪","recommend":"💡","hotplace":"🔥"}
                b = badges.get(msg.get("intent",""), "")
                st.markdown(f"{b} {msg['content']}")
                st.markdown("---")

        # 입력
        inp = st.text_input("질문", key="ai_inp", label_visibility="collapsed", placeholder="무엇이든 물어보세요...")
        c1, c2 = st.columns([4, 1])
        with c1:
            if st.button("전송 →", key="ai_send", use_container_width=True):
                if inp:
                    _do_ask(inp, "", "")
        with c2:
            if st.button("↻", key="ai_clr"):
                st.session_state.chat_messages = []
                _safe_rerun()


# 하위 호환
def get_chat_layout(page_context="", selected_district=""):
    return st.container()

def render_chat_panel(current_tab="", selected_district="", selected_month="", page_context=""):
    pass
