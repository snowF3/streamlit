"""
마케팅 분석 탭 — 아정당 데이터 집중 활용
채널 성과, 퍼널 전환, 렌탈 트렌드, 콜센터 효율
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_loader import (
    load_ajd_channel, load_ajd_funnel, load_ajd_rental, load_ajd_ga4,
    load_ajd_new_install, run_query, AJD
)


def render():
    st.markdown("### 📢 마케팅 분석")
    st.caption("아정당 데이터 기반 — 채널 성과 · 퍼널 전환 · 렌탈 트렌드 · 콜센터")

    tab_channel, tab_funnel, tab_rental, tab_call = st.tabs([
        "📊 채널 성과", "🔄 퍼널 전환", "📦 렌탈 트렌드", "📞 콜센터"
    ])

    # ══════════════════════════════
    # 탭 1: 채널 성과 (V04 + V07)
    # ══════════════════════════════
    with tab_channel:
        st.markdown("#### 채널별 계약 성과")

        try:
            # GA4 마케팅 데이터
            ga4 = run_query(f"""
                SELECT UTM_SOURCE, UTM_MEDIUM,
                       SUM(TOTAL_SESSIONS) as SESSIONS,
                       SUM(TOTAL_USERS) as USERS,
                       SUM(TOTAL_CONTRACTS) as CONTRACTS,
                       SUM(TOTAL_REVENUE) as REVENUE,
                       ROUND(AVG(CONTRACT_CVR), 2) as AVG_CVR
                FROM {AJD}.V07_GA4_MARKETING_ATTRIBUTION
                WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V07_GA4_MARKETING_ATTRIBUTION)
                GROUP BY 1, 2
                ORDER BY REVENUE DESC
                LIMIT 15
            """)

            if not ga4.empty:
                # 매출 Top 채널 바 차트
                fig = go.Figure(go.Bar(
                    x=ga4["REVENUE"] / 1e8,
                    y=ga4["UTM_SOURCE"] + " / " + ga4["UTM_MEDIUM"],
                    orientation='h',
                    marker_color='#6366F1'
                ))
                fig.update_layout(title="채널별 매출 Top 15 (억원)", height=400,
                                  xaxis_title="매출 (억원)", yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True, key="ga4_revenue")

                # 전환율 Top 채널
                ga4_cvr = ga4[ga4["SESSIONS"] > 100].nlargest(10, "AVG_CVR")
                if not ga4_cvr.empty:
                    fig2 = go.Figure(go.Bar(
                        x=ga4_cvr["AVG_CVR"],
                        y=ga4_cvr["UTM_SOURCE"] + " / " + ga4_cvr["UTM_MEDIUM"],
                        orientation='h',
                        marker_color='#10B981'
                    ))
                    fig2.update_layout(title="전환율 Top 10 (%)", height=350,
                                       xaxis_title="계약 전환율 (%)", yaxis=dict(autorange="reversed"))
                    st.plotly_chart(fig2, use_container_width=True, key="ga4_cvr")
            else:
                st.info("GA4 데이터 없음")

        except Exception as e:
            st.error(f"채널 데이터 로드 오류: {e}")

        # 채널별 계약 성과 (V04)
        st.markdown("---")
        st.markdown("#### 유입 경로별 성과")
        try:
            channel = run_query(f"""
                SELECT RECEIVE_PATH_NAME as PATH,
                       SUM(CONTRACT_COUNT) as CONTRACTS,
                       SUM(PAYEND_COUNT) as PAID,
                       ROUND(AVG(PAYEND_CVR), 1) as PAID_CVR,
                       ROUND(SUM(TOTAL_NET_SALES) / 1e8, 1) as REVENUE_BILLION
                FROM {AJD}.V04_CHANNEL_CONTRACT_PERFORMANCE
                WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V04_CHANNEL_CONTRACT_PERFORMANCE)
                GROUP BY 1
                ORDER BY CONTRACTS DESC
                LIMIT 10
            """)
            if not channel.empty:
                st.dataframe(channel, use_container_width=True)
            else:
                st.info("채널 성과 데이터 없음")
        except Exception as e:
            st.error(f"채널 성과 로드 오류: {e}")

    # ══════════════════════════════
    # 탭 2: 퍼널 전환 (V03)
    # ══════════════════════════════
    with tab_funnel:
        st.markdown("#### 카테고리별 퍼널 전환율")

        try:
            funnel = run_query(f"""
                SELECT MAIN_CATEGORY_NAME as CATEGORY,
                       SUM(TOTAL_COUNT) as TOTAL,
                       SUM(CONSULT_REQUEST_COUNT) as CONSULT,
                       SUM(REGISTEND_COUNT) as REGISTERED,
                       SUM(OPEN_COUNT) as OPENED,
                       SUM(PAYEND_COUNT) as PAID,
                       ROUND(AVG(OVERALL_CVR), 1) as OVERALL_CVR
                FROM {AJD}.V03_CONTRACT_FUNNEL_CONVERSION
                WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V03_CONTRACT_FUNNEL_CONVERSION)
                GROUP BY 1
                ORDER BY TOTAL DESC
            """)

            if not funnel.empty:
                # 퍼널 바 차트
                for _, row in funnel.iterrows():
                    cat = row["CATEGORY"]
                    stages = ["유입", "상담", "접수", "개통", "결제"]
                    values = [row["TOTAL"], row["CONSULT"], row["REGISTERED"], row["OPENED"], row["PAID"]]
                    values = [int(v) if pd.notna(v) else 0 for v in values]

                    if values[0] > 0:
                        st.markdown(f"**{cat}** (전체 전환율: {row['OVERALL_CVR']}%)")
                        fig = go.Figure(go.Funnel(
                            y=stages, x=values,
                            textinfo="value+percent initial"
                        ))
                        fig.update_layout(height=200, margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig, use_container_width=True, key=f"funnel_{cat}")
            else:
                st.info("퍼널 데이터 없음")

        except Exception as e:
            st.error(f"퍼널 데이터 로드 오류: {e}")

    # ══════════════════════════════
    # 탭 3: 렌탈 트렌드 (V06)
    # ══════════════════════════════
    with tab_rental:
        st.markdown("#### 렌탈 카테고리별 트렌드")

        try:
            rental = run_query(f"""
                SELECT RENTAL_SUB_CATEGORY as CATEGORY,
                       SUM(CONTRACT_COUNT) as CONTRACTS,
                       SUM(OPEN_COUNT) as OPENED,
                       ROUND(AVG(OPEN_CVR), 1) as OPEN_CVR,
                       ROUND(AVG(AVG_NET_SALES)) as AVG_SALES
                FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS
                WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS)
                GROUP BY 1
                ORDER BY CONTRACTS DESC
                LIMIT 15
            """)

            if not rental.empty:
                fig = go.Figure(go.Bar(
                    x=rental["CONTRACTS"],
                    y=rental["CATEGORY"],
                    orientation='h',
                    marker_color='#F59E0B'
                ))
                fig.update_layout(title="렌탈 품목별 계약 건수", height=400,
                                  xaxis_title="계약 건수", yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True, key="rental_bar")

                # 월별 트렌드 (Top 5 품목)
                st.markdown("---")
                st.markdown("#### 월별 추이 (Top 5)")
                top5 = rental.nlargest(5, "CONTRACTS")["CATEGORY"].tolist()

                trend = run_query(f"""
                    SELECT YEAR_MONTH, RENTAL_SUB_CATEGORY as CATEGORY,
                           SUM(CONTRACT_COUNT) as CONTRACTS
                    FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS
                    WHERE RENTAL_SUB_CATEGORY IN ({','.join([f"'{c}'" for c in top5])})
                    GROUP BY 1, 2
                    ORDER BY 1
                """)

                if not trend.empty:
                    fig2 = px.line(trend, x="YEAR_MONTH", y="CONTRACTS", color="CATEGORY",
                                  title="월별 렌탈 계약 추이")
                    fig2.update_layout(height=350)
                    st.plotly_chart(fig2, use_container_width=True, key="rental_trend")
            else:
                st.info("렌탈 데이터 없음")

        except Exception as e:
            st.error(f"렌탈 데이터 로드 오류: {e}")

    # ══════════════════════════════
    # 탭 4: 콜센터 (V09 + V10 + V11)
    # ══════════════════════════════
    with tab_call:
        st.markdown("#### 콜센터 효율 분석")

        try:
            # 월별 콜 통계
            calls = run_query(f"""
                SELECT YEAR_MONTH,
                       SUM(CALL_COUNT) as TOTAL_CALLS,
                       SUM(CONNECTED_COUNT) as CONNECTED,
                       ROUND(AVG(CONNECTION_RATE), 1) as AVG_CONNECT_RATE,
                       ROUND(AVG(AVG_BILL_MINUTE), 1) as AVG_DURATION_MIN
                FROM {AJD}.V09_MONTHLY_CALL_STATS
                GROUP BY 1
                ORDER BY 1 DESC
                LIMIT 12
            """)

            if not calls.empty:
                c1, c2 = st.columns(2)
                with c1:
                    latest = calls.iloc[0]
                    st.metric("이번 달 총 콜", f"{int(latest['TOTAL_CALLS']):,}건")
                    st.metric("연결률", f"{latest['AVG_CONNECT_RATE']}%")
                with c2:
                    st.metric("평균 통화시간", f"{latest['AVG_DURATION_MIN']}분")
                    if len(calls) > 1:
                        prev = calls.iloc[1]
                        delta = latest['AVG_CONNECT_RATE'] - prev['AVG_CONNECT_RATE']
                        st.metric("연결률 변화", f"{delta:+.1f}%p")

                # 연결률 추이
                calls_sorted = calls.sort_values("YEAR_MONTH")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=calls_sorted["YEAR_MONTH"].astype(str),
                    y=calls_sorted["AVG_CONNECT_RATE"],
                    mode='lines+markers',
                    line=dict(color='#6366F1', width=2),
                    name='연결률'
                ))
                fig.update_layout(title="월별 연결률 추이 (%)", height=300,
                                  yaxis_title="%")
                st.plotly_chart(fig, use_container_width=True, key="call_rate")

            # 콜→계약 전환
            st.markdown("---")
            st.markdown("#### 콜 → 계약 전환")
            conv = run_query(f"""
                SELECT MAIN_CATEGORY_NAME as CATEGORY,
                       DIVISION_NAME as TYPE,
                       ROUND(AVG(CALL_TO_CONTRACT_CVR), 1) as CVR,
                       ROUND(AVG(CALLS_PER_CONTRACT), 1) as CALLS_PER_CONTRACT
                FROM {AJD}.V11_CALL_TO_CONTRACT_CONVERSION
                WHERE YEAR_MONTH = (SELECT MAX(YEAR_MONTH) FROM {AJD}.V11_CALL_TO_CONTRACT_CONVERSION)
                GROUP BY 1, 2
                ORDER BY CVR DESC
            """)
            if not conv.empty:
                st.dataframe(conv, use_container_width=True)

        except Exception as e:
            st.error(f"콜센터 데이터 로드 오류: {e}")
