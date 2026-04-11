"""
AI 에이전트 전용 앱 — 디버그용
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="AI 에이전트 디버그", layout="wide")

st.write("1. 앱 시작됨")

try:
    from chat_ui import render_sidebar_chat
    st.write("2. chat_ui import 성공")
except Exception as e:
    st.error(f"2. chat_ui import 실패: {e}")

try:
    from chat_ui import _cortex
    st.write("3. _cortex import 성공")
    # Cortex 테스트
    result = _cortex("안녕")
    st.write(f"4. Cortex 응답: {result[:100]}")
except Exception as e:
    st.error(f"3-4. Cortex 테스트 실패: {e}")

try:
    from data_loader import run_query
    st.write("5. data_loader import 성공")
    df = run_query("SELECT 1 as test")
    st.write(f"6. Snowflake 쿼리 성공: {df}")
except Exception as e:
    st.error(f"5-6. data_loader 실패: {e}")

st.write("7. 디버그 완료")
