"""
AI 에이전트 전용 앱 — 채팅만
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="AI 에이전트", layout="centered")

from chat_ui import render_sidebar_chat
render_sidebar_chat()
