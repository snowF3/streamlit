"""
AI 에이전트 — 탭 기반 채팅 (컬럼 중첩 에러 완전 해결)
st.tabs(["📊 대시보드", "🤖 AI"]) 방식
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
- 위 데이터를 기반으로 답변. 없으면 추측이라고 명시.
- 절대 되묻지 마세요.
- 숫자는 읽기 쉽게 (1,234명, 3.5억원)
- 시뮬레이션: 매출 범위, 고객층, 피크, 리스크 포함
- 한국어로 답변

질문: {q}"""
    return {"answer":_cortex(prompt,intent in("simulate","compare","recommend")),"intent":intent}


def _do_ask(q, pctx, sel_d):
    st.session_state.chat_messages.append({"role":"user","content":q})
    r = _answer(q, st.session_state.chat_messages[:-1], pctx, sel_d)
    st.session_state.chat_messages.append({"role":"assistant","content":r["answer"],"intent":r["intent"]})
    _safe_rerun()


# ═══════════════════════════════════════════
# 탭 기반 레이아웃 (컬럼 중첩 에러 없음)
# ═══════════════════════════════════════════

def get_chat_layout(page_context="", selected_district=""):
    """
    탭 기반 AI 채팅 레이아웃. 컬럼 중첩 에러 없음.

    사용법:
        content_tab, ai_tab = get_chat_layout(page_context="동네 프로파일 - 신당동")
        with content_tab:
            # 기존 페이지 콘텐츠 (st.columns 자유롭게 사용 가능)
        # ai_tab은 자동으로 채팅 UI가 렌더링됨
    """
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    tab_content, tab_ai = st.tabs(["📊 대시보드", "🤖 AI 에이전트"])

    with tab_ai:
        # 헤더
        st.markdown(f"""<div style="background:linear-gradient(135deg,#6366F1,#8B5CF6);
            padding:14px 20px;border-radius:12px;margin-bottom:16px;">
            <span style="color:white;font-size:16px;font-weight:700;">🤖 AI 에이전트</span>
            <span style="color:rgba(255,255,255,0.5);font-size:11px;margin-left:8px;">
                Snowflake Cortex · 실제 데이터 조회
            </span>
            <div style="color:rgba(255,255,255,0.4);font-size:10px;margin-top:4px;">
                📍 {page_context if page_context else '메인'}
            </div>
        </div>""", unsafe_allow_html=True)

        # 추천 질문 (대화 없을 때)
        if not st.session_state.chat_messages:
            st.markdown("**💡 이런 질문을 해보세요**")
            suggestions = {
                "🔍 신당동 유동인구": "신당동 유동인구 알려줘",
                "🧪 서초동 카페 시뮬": "서초동에 카페 차리면 매출이?",
                "🔥 핫플 예측": "다음 핫플은 어디야?",
                "⚖️ 중구 vs 영등포구": "중구 vs 영등포구 비교",
                "💡 잠원동 추천": "잠원동에서 뭘 팔면 좋을까?",
                "📈 신당동 추이": "신당동 최근 추이 보여줘",
            }
            cols = st.columns(3)
            for i, (label, q) in enumerate(suggestions.items()):
                with cols[i % 3]:
                    if st.button(label, key=f"sug_{i}", use_container_width=True):
                        _do_ask(q, page_context, selected_district)

        # 대화 히스토리
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.markdown(f"""<div style="text-align:right;margin:10px 0;">
                    <span style="background:linear-gradient(135deg,#6366F1,#8B5CF6);color:white;
                    padding:10px 16px;border-radius:18px 18px 4px 18px;display:inline-block;
                    max-width:70%;font-size:14px;">
                    {msg['content']}</span></div>""", unsafe_allow_html=True)
            else:
                badges = {"lookup":"🔍 조회","compare":"⚖️ 비교","trend":"📈 추이",
                          "simulate":"🧪 시뮬","recommend":"💡 추천","hotplace":"🔥 핫플"}
                intent = msg.get("intent","")
                badge = badges.get(intent, "")
                st.markdown(f"""<div style="margin:10px 0;">
                    <span style="background:rgba(255,255,255,0.05);color:#E0E0E0;
                    padding:12px 16px;border-radius:18px 18px 18px 4px;display:inline-block;
                    max-width:80%;font-size:14px;line-height:1.6;border:1px solid rgba(255,255,255,0.08);">
                    {msg['content']}
                    <span style="display:block;font-size:10px;color:#888;margin-top:6px;">{badge}</span>
                    </span></div>""", unsafe_allow_html=True)

        # 입력
        st.markdown("---")
        c1, c2, c3 = st.columns([6, 1, 1])
        with c1:
            inp = st.text_input("질문", key="ai_input", label_visibility="collapsed", placeholder="무엇이든 물어보세요...")
        with c2:
            send = st.button("전송", key="ai_send", use_container_width=True)
        with c3:
            if st.button("↻", key="ai_clear", use_container_width=True):
                st.session_state.chat_messages = []
                _safe_rerun()

        if send and inp:
            _do_ask(inp, page_context, selected_district)

    return tab_content


def render_chat_panel(current_tab="", selected_district="", selected_month="", page_context=""):
    """하위 호환용 — 사용하지 않음"""
    pass
