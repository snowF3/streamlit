"""
AI 에이전트 채팅 UI — 채널톡 스타일 플로팅 위젯
components.html iframe 내부에서 parent document에 inject
"""
import os
import streamlit as st
import requests
import streamlit.components.v1 as components

# AGENT_URL 결정: st.secrets > 환경변수 > 기본값
AGENT_URL = "http://localhost:8000"
try:
    if "AGENT_URL" in st.secrets:
        AGENT_URL = st.secrets["AGENT_URL"]
except Exception:
    pass
if AGENT_URL == "http://localhost:8000":
    AGENT_URL = os.environ.get("AGENT_URL", AGENT_URL)


def _check_health() -> bool:
    try:
        return requests.get(f"{AGENT_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


def _get_cost_summary() -> dict | None:
    try:
        resp = requests.get(f"{AGENT_URL}/costs", timeout=3)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def render_chat_panel(current_tab: str = "", selected_district: str = "", selected_month: str = "", page_context: str = ""):
    """
    page_context: 현재 페이지에서 사용자가 보고 있는 상세 정보.
    예: "동네 프로파일 - 중구 신당동, 유동인구 45,935명, 카드매출 35.9억, 평균소득 4,999만원"
    """
    agent_online = _check_health()

    # 사이드바 비용
    cost_summary = _get_cost_summary()
    if cost_summary and cost_summary.get("total_queries", 0) > 0:
        with st.sidebar:
            st.divider()
            st.markdown("### 💰 AI 비용")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("총 비용", f"${cost_summary['total_cost']:.4f}")
            with col2:
                st.metric("질의 수", f"{cost_summary['total_queries']}건")

    inject_html = f"""
    <script>
    (function() {{
        // 부모 document 접근
        var doc = window.parent.document;

        // 이미 있으면 스킵
        if (doc.getElementById('xray-chat-fab')) return;

        var AGENT_URL = "{AGENT_URL}";
        var CTX = {{
            district: "{selected_district}",
            month: "{selected_month}",
            tab: "{current_tab}",
            page_context: {repr(page_context)}
        }};

        // 대화 복원
        var hist = JSON.parse(localStorage.getItem('xray_hist') || '[]');
        var wasOpen = localStorage.getItem('xray_open') === '1';

        // CSS
        var css = doc.createElement('style');
        css.textContent = `
            #xray-chat-fab {{
                position:fixed; bottom:28px; right:28px; z-index:999999;
                width:56px; height:56px; border-radius:50%;
                background:linear-gradient(135deg,#6366F1,#8B5CF6);
                border:none; cursor:pointer;
                box-shadow:0 4px 16px rgba(99,102,241,0.5);
                display:flex; align-items:center; justify-content:center;
                transition:all 0.3s;
            }}
            #xray-chat-fab:hover {{ transform:scale(1.08); box-shadow:0 6px 24px rgba(99,102,241,0.7); }}
            #xray-chat-fab svg {{ width:26px; height:26px; fill:white; }}
            .xray-dot {{
                position:absolute; top:2px; right:2px;
                width:12px; height:12px; border-radius:50%;
                background:{"#4CAF50" if agent_online else "#f44336"};
                border:2px solid white;
            }}
            #xray-popup {{
                position:fixed; bottom:96px; right:28px; z-index:999998;
                width:380px; height:520px; background:#1a1a2e;
                border-radius:16px; box-shadow:0 8px 40px rgba(0,0,0,0.4);
                display:none; flex-direction:column; overflow:hidden;
                border:1px solid #2a2a4a;
                font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            }}
            #xray-popup.xopen {{ display:flex; animation:xup 0.25s ease-out; }}
            @keyframes xup {{ from{{opacity:0;transform:translateY(16px)}} to{{opacity:1;transform:translateY(0)}} }}

            .xhd {{ background:linear-gradient(135deg,#6366F1,#8B5CF6); padding:14px 16px; display:flex; justify-content:space-between; align-items:center; flex-shrink:0; }}
            .xhd-t {{ color:white; font-size:15px; font-weight:700; }}
            .xhd-s {{ color:rgba(255,255,255,0.6); font-size:11px; margin-top:2px; }}
            .xhd-x {{ background:none; border:none; color:rgba(255,255,255,0.7); font-size:20px; cursor:pointer; }}
            .xhd-x:hover {{ color:white; }}

            #xmsgs {{ flex:1; overflow-y:auto; padding:14px; display:flex; flex-direction:column; gap:8px; }}
            #xmsgs::-webkit-scrollbar {{ width:4px; }}
            #xmsgs::-webkit-scrollbar-thumb {{ background:#444; border-radius:2px; }}
            .xu {{ align-self:flex-end; background:#6366F1; color:white; padding:8px 14px; border-radius:16px 16px 4px 16px; max-width:80%; font-size:13px; line-height:1.5; word-break:break-word; }}
            .xb {{ align-self:flex-start; background:#2a2a4a; color:#E0E0E0; padding:10px 14px; border-radius:16px 16px 16px 4px; max-width:85%; font-size:13px; line-height:1.6; word-break:break-word; }}
            .xc {{ font-size:10px; color:#888; margin-top:4px; }}
            .xt {{ align-self:flex-start; color:#888; font-size:12px; padding:8px; }}
            .xt .xd {{ animation:xbl 1.4s infinite; display:inline-block; }}
            .xt .xd:nth-child(2) {{ animation-delay:0.2s; }}
            .xt .xd:nth-child(3) {{ animation-delay:0.4s; }}
            @keyframes xbl {{ 0%,80%,100%{{opacity:0}} 40%{{opacity:1}} }}

            .xwel {{ text-align:center; padding:50px 20px; color:#888; }}
            .xwel b {{ font-size:36px; display:block; margin-bottom:8px; }}
            .xwel strong {{ font-size:14px; color:#ccc; }}
            .xwel small {{ font-size:11px; display:block; margin-top:6px; line-height:1.5; }}

            #xsug {{ padding:8px 14px 4px; display:flex; flex-wrap:wrap; gap:6px; flex-shrink:0; }}
            .xs {{ background:#2a2a4a; border:1px solid #3a3a5a; color:#B0B0D0; padding:6px 12px; border-radius:20px; font-size:11px; cursor:pointer; transition:all 0.2s; }}
            .xs:hover {{ background:#6366F1; color:white; border-color:#6366F1; }}

            .xin {{ padding:10px 12px; border-top:1px solid #2a2a4a; display:flex; gap:8px; flex-shrink:0; background:#16162a; }}
            #xinp {{ flex:1; background:#2a2a4a; border:1px solid #3a3a5a; border-radius:20px; padding:8px 16px; color:#E0E0E0; font-size:13px; outline:none; }}
            #xinp:focus {{ border-color:#6366F1; }}
            #xinp::placeholder {{ color:#555; }}
            #xsnd {{ background:#6366F1; border:none; border-radius:50%; width:36px; height:36px; cursor:pointer; display:flex; align-items:center; justify-content:center; }}
            #xsnd:hover {{ background:#5355D4; }}
            #xsnd svg {{ width:16px; height:16px; fill:white; }}
            #xsnd:disabled {{ opacity:0.4; cursor:not-allowed; }}
        `;
        doc.head.appendChild(css);

        // FAB
        var fab = doc.createElement('button');
        fab.id = 'xray-chat-fab';
        fab.innerHTML = '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/></svg><div class="xray-dot"></div>';
        fab.onclick = function() {{
            var p = doc.getElementById('xray-popup');
            var o = !p.classList.contains('xopen');
            p.classList.toggle('xopen', o);
            localStorage.setItem('xray_open', o ? '1' : '0');
            if (o) doc.getElementById('xinp').focus();
        }};
        doc.body.appendChild(fab);

        // POPUP
        var popup = doc.createElement('div');
        popup.id = 'xray-popup';
        popup.innerHTML = '<div class="xhd"><div><div class="xhd-t">🤖 동네 엑스레이 AI</div><div class="xhd-s" id="xhd-st">{"🟢 온라인" if agent_online else "🔴 오프라인"}</div></div><button class="xhd-x" id="xray-close">✕</button></div><div id="xmsgs"><div class="xwel"><b>🏙️</b><strong>동네 데이터, 무엇이든 물어보세요</strong><small>유동인구 · 카드매출 · 소득 · 부동산<br>시뮬레이션 · 핫플 예측 · 동네 비교</small></div></div><div id="xsug"></div><div class="xin"><input id="xinp" placeholder="메시지를 입력하세요..."/><button id="xsnd"><svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></button></div>';
        doc.body.appendChild(popup);

        // 닫기
        doc.getElementById('xray-close').onclick = function() {{
            doc.getElementById('xray-popup').classList.remove('xopen');
            localStorage.setItem('xray_open', '0');
        }};

        // 추천 질문
        var sugEl = doc.getElementById('xsug');
        var sugs = ['신당동 유동인구 알려줘','서초동에 카페 차리면?','다음 핫플은 어디야?','중구 vs 영등포구'];
        var sugLabels = ['신당동 유동인구','카페 시뮬레이션','넥스트 핫플','동네 비교'];
        sugs.forEach(function(s, i) {{
            var b = doc.createElement('button');
            b.className = 'xs';
            b.textContent = sugLabels[i];
            b.onclick = function() {{ xSend(s); }};
            sugEl.appendChild(b);
        }});

        // 엔터키
        doc.getElementById('xinp').onkeydown = function(e) {{ if (e.key === 'Enter') xSendInput(); }};
        doc.getElementById('xsnd').onclick = function() {{ xSendInput(); }};

        // 대화 복원
        if (hist.length > 0) {{
            sugEl.style.display = 'none';
            var m = doc.getElementById('xmsgs');
            m.innerHTML = '';
            hist.forEach(function(h) {{ addMsg(h.role === 'user' ? 'u' : 'b', h.content, h.cost, h.tier); }});
        }}
        if (wasOpen) popup.classList.add('xopen');

        function addMsg(type, content, cost, tier) {{
            var m = doc.getElementById('xmsgs');
            var w = m.querySelector('.xwel'); if (w) w.remove();
            var d = doc.createElement('div');
            d.className = type === 'u' ? 'xu' : 'xb';
            var h = content.replace(/\\n/g, '<br>');
            if (cost && cost > 0) {{
                var e = {{"simple":"🟢","analysis":"🟡","complex":"🔴"}}[tier] || "⚪";
                h += '<div class="xc">💰 $' + cost.toFixed(4) + ' ' + e + '</div>';
            }}
            d.innerHTML = h;
            m.appendChild(d);
            m.scrollTop = m.scrollHeight;
            if (hist.length > 0) doc.getElementById('xsug').style.display = 'none';
        }}

        function save() {{ localStorage.setItem('xray_hist', JSON.stringify(hist)); }}

        window.xSendInput = function() {{
            var inp = doc.getElementById('xinp');
            var t = inp.value.trim(); if (!t) return;
            inp.value = ''; xSend(t);
        }};

        window.xSend = async function(text) {{
            addMsg('u', text);
            hist.push({{role:'user', content:text}});
            save();
            doc.getElementById('xsnd').disabled = true;

            var m = doc.getElementById('xmsgs');
            var td = doc.createElement('div');
            td.className = 'xt'; td.id = 'xtyp';
            td.innerHTML = '<span class="xd">●</span> <span class="xd">●</span> <span class="xd">●</span> 분석 중...';
            m.appendChild(td); m.scrollTop = m.scrollHeight;

            try {{
                var r = await fetch(AGENT_URL + '/chat', {{
                    method:'POST', headers:{{'Content-Type':'application/json'}},
                    body: JSON.stringify({{
                        query:text, chat_history:hist.slice(0,-1),
                        selected_district:CTX.district, selected_month:CTX.month, current_tab:CTX.tab, page_context:CTX.page_context
                    }})
                }});
                var ty = doc.getElementById('xtyp'); if (ty) ty.remove();
                if (r.ok) {{
                    var d = await r.json();
                    addMsg('b', d.answer||'응답 없음', d.total_cost, d.query_type);
                    hist.push({{role:'assistant', content:d.answer, cost:d.total_cost, tier:d.query_type}});
                    save();
                    var st = doc.getElementById('xhd-st');
                    if (st) st.innerHTML = '🟢 온라인 · 💰 $' + (d.session_total_cost||0).toFixed(4);
                }} else {{ addMsg('b', '❌ 오류: ' + r.status); }}
            }} catch(e) {{
                var ty = doc.getElementById('xtyp'); if (ty) ty.remove();
                addMsg('b', '❌ 연결 실패: ' + e.message);
            }}
            doc.getElementById('xsnd').disabled = false;
            doc.getElementById('xinp').focus();
        }};
    }})();
    </script>
    """

    components.html(inject_html, height=0, scrolling=False)
