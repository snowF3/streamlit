"""
공통 차트 컴포넌트 (Plotly 기반)
"""
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np


# 업종 한글 매핑
CATEGORY_KOR = {
    "FOOD": "식음료", "COFFEE": "커피", "ENTERTAINMENT": "오락/유흥",
    "DEPARTMENT_STORE": "백화점", "LARGE_DISCOUNT_STORE": "대형마트",
    "SMALL_RETAIL_STORE": "소매점", "CLOTHING_ACCESSORIES": "의류/잡화",
    "SPORTS_CULTURE_LEISURE": "스포츠/문화", "ACCOMMODATION": "숙박",
    "TRAVEL": "여행", "BEAUTY": "미용", "HOME_LIFE_SERVICE": "생활서비스",
    "EDUCATION_ACADEMY": "교육/학원", "MEDICAL": "의료",
    "ELECTRONICS_FURNITURE": "가전/가구", "CAR": "자동차",
    "CAR_SERVICE_SUPPLIES": "자동차서비스", "GAS_STATION": "주유소",
    "E_COMMERCE": "이커머스", "TOTAL": "합계"
}

TIME_SLOT_KOR = {
    "T06": "아침(6~9)", "T09": "오전(9~12)", "T12": "점심(12~15)",
    "T15": "오후(15~18)", "T18": "저녁(18~21)", "T21": "심야(21~24)",
    "T24": "기타"
}

LIFESTYLE_KOR = {
    "L01": "싱글", "L02": "신혼부부", "L03": "영유아가족",
    "L04": "청소년가족", "L05": "성인자녀가족", "L06": "실버"
}


def spending_radar_chart(card_row: pd.Series, title="소비 DNA"):
    """20개 업종별 매출 비중 레이더 차트"""
    categories = [k for k in CATEGORY_KOR.keys() if k != "TOTAL"]
    sales_cols = [f"{cat}_SALES" for cat in categories]

    available = [c for c in sales_cols if c in card_row.index]
    if not available:
        return go.Figure().update_layout(title="데이터 없음")

    values = []
    labels = []
    for cat in categories:
        col = f"{cat}_SALES"
        if col in card_row.index:
            values.append(float(card_row[col]) if pd.notna(card_row[col]) else 0)
            labels.append(CATEGORY_KOR[cat])

    total = sum(values)
    if total > 0:
        ratios = [v / total * 100 for v in values]
    else:
        ratios = values

    fig = go.Figure(data=go.Scatterpolar(
        r=ratios + [ratios[0]],
        theta=labels + [labels[0]],
        fill='toself',
        fillcolor='rgba(99, 110, 250, 0.2)',
        line=dict(color='rgb(99, 110, 250)')
    ))
    fig.update_layout(
        title=title,
        polar=dict(radialaxis=dict(visible=True, showticklabels=False)),
        showlegend=False,
        height=400,
        margin=dict(l=60, r=60, t=60, b=60)
    )
    return fig


def population_flow_chart(pop_time_df, title="시간대별 유동인구"):
    """시간대별 거주/직장/방문 영역 차트"""
    time_order = ["T06", "T09", "T12", "T15", "T18", "T21", "T24"]
    pop_time_df = pop_time_df.copy()

    if "TIME_SLOT" not in pop_time_df.columns:
        return go.Figure().update_layout(title="데이터 없음")

    agg = pop_time_df.groupby("TIME_SLOT")[
        ["RESIDENTIAL_POPULATION", "WORKING_POPULATION", "VISITING_POPULATION"]
    ].sum().reindex(time_order).fillna(0)

    labels = [TIME_SLOT_KOR.get(t, t) for t in agg.index]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=agg["RESIDENTIAL_POPULATION"].tolist(),
        mode='lines', stackgroup='one', name='거주인구',
        line=dict(color='#636EFA'), fillcolor='rgba(99, 110, 250, 0.4)',
        hovertemplate='%{x}<br>거주: %{y:,.0f}명<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=agg["WORKING_POPULATION"].tolist(),
        mode='lines', stackgroup='one', name='직장인구',
        line=dict(color='#EF553B'), fillcolor='rgba(239, 85, 59, 0.4)',
        hovertemplate='%{x}<br>직장: %{y:,.0f}명<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=agg["VISITING_POPULATION"].tolist(),
        mode='lines', stackgroup='one', name='방문인구',
        line=dict(color='#00CC96'), fillcolor='rgba(0, 204, 150, 0.4)',
        hovertemplate='%{x}<br>방문: %{y:,.0f}명<extra></extra>',
    ))
    fig.update_layout(title=title, xaxis_title="시간대", yaxis_title="인구(명)", height=350)
    return fig


def population_pyramid(pop_demo_df, title="인구 피라미드", pop_type="전체"):
    """성별×연령대 인구 피라미드. pop_type: 전체/거주/직장/방문"""
    if pop_demo_df.empty:
        return go.Figure().update_layout(title="데이터 없음")

    df = pop_demo_df.copy()

    type_col_map = {
        "전체": None,  # 합산
        "거주": "RESIDENTIAL_POPULATION",
        "직장": "WORKING_POPULATION",
        "방문": "VISITING_POPULATION",
    }

    if pop_type in type_col_map and type_col_map[pop_type]:
        col = type_col_map[pop_type]
        df["TOTAL_POP"] = df[col]
    else:
        df["TOTAL_POP"] = df["RESIDENTIAL_POPULATION"] + df["WORKING_POPULATION"] + df["VISITING_POPULATION"]

    male = df[df["GENDER"] == "M"].groupby("AGE_GROUP")["TOTAL_POP"].sum()
    female = df[df["GENDER"] == "F"].groupby("AGE_GROUP")["TOTAL_POP"].sum()

    age_order = sorted(male.index.union(female.index), key=lambda x: int(x) if str(x).isdigit() else 0)
    age_labels = [f"{int(a)}~{int(a)+4}세" for a in age_order]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=age_labels,
        x=[-male.get(a, 0) for a in age_order],
        name='남성', orientation='h',
        marker_color='#636EFA'
    ))
    fig.add_trace(go.Bar(
        y=age_labels,
        x=[female.get(a, 0) for a in age_order],
        name='여성', orientation='h',
        marker_color='#EF553B'
    ))
    fig.update_layout(
        title=title, barmode='overlay',
        xaxis=dict(title="인구(명)", tickvals=[]),
        yaxis=dict(title="연령대"),
        height=400
    )
    return fig


def realestate_trend_chart(re_df, title="매매/전세 시세 추이"):
    """매매가/전세가 라인 차트"""
    if re_df.empty:
        return go.Figure().update_layout(title="데이터 없음")

    df = re_df.sort_values("YYYYMMDD").copy().reset_index(drop=True)

    # YYYYMMDD → 날짜 라벨 (카테고리로 사용)
    def _parse_date(x):
        s = str(x)
        if "-" in s:
            parts = s.split("-")
            return f"{parts[0]}-{parts[1]}"
        elif len(s) >= 6:
            return f"{s[:4]}-{s[4:6]}"
        return s
    df["date_label"] = df["YYYYMMDD"].apply(_parse_date)

    fig = go.Figure()

    if "MEME_PRICE_PER_SUPPLY_PYEONG" in df.columns:
        meme = df[df["MEME_PRICE_PER_SUPPLY_PYEONG"].notna() & (df["MEME_PRICE_PER_SUPPLY_PYEONG"] > 0)]
        if not meme.empty:
            fig.add_trace(go.Scatter(
                x=meme["date_label"].tolist(),
                y=meme["MEME_PRICE_PER_SUPPLY_PYEONG"].tolist(),
                mode='lines', name='매매 평단가',
                line=dict(color='#EF553B', width=2),
                hovertemplate='%{x}<br>매매: %{y:,.0f}만원/평<extra></extra>',
            ))

    if "JEONSE_PRICE_PER_SUPPLY_PYEONG" in df.columns:
        jeonse = df[df["JEONSE_PRICE_PER_SUPPLY_PYEONG"].notna() & (df["JEONSE_PRICE_PER_SUPPLY_PYEONG"] > 0)]
        if not jeonse.empty:
            fig.add_trace(go.Scatter(
                x=jeonse["date_label"].tolist(),
                y=jeonse["JEONSE_PRICE_PER_SUPPLY_PYEONG"].tolist(),
                mode='lines', name='전세 평단가',
                line=dict(color='#636EFA', width=2),
                hovertemplate='%{x}<br>전세: %{y:,.0f}만원/평<extra></extra>',
            ))

    if len(fig.data) == 0:
        return go.Figure().update_layout(title=f"{title} — 데이터 없음")

    fig.update_layout(
        title=title,
        xaxis=dict(title="", type="category", tickangle=-45, dtick=12),
        yaxis=dict(title="만원/평"),
        height=300,
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
    )
    return fig


def income_distribution_chart(income_row, title="소득 분포"):
    """소득 구간별 비율 바 차트"""
    income_cols = {
        "RATE_INCOME_UNDER_20M": "~2천만",
        "RATE_INCOME_20M_TO_30M": "2~3천만",
        "RATE_INCOME_30M_TO_40M": "3~4천만",
        "RATE_INCOME_40M_TO_50M": "4~5천만",
        "RATE_INCOME_50M_TO_60M": "5~6천만",
        "RATE_INCOME_60M_TO_70M": "6~7천만",
        "RATE_INCOME_OVER_70M": "7천만~",
    }

    labels = []
    values = []
    for col, label in income_cols.items():
        if col in income_row.index and pd.notna(income_row[col]):
            v = float(income_row[col])
            labels.append(label)
            # 이미 비율(0~1)이면 *100, 이미 %면 그대로
            values.append(v * 100 if v <= 1 else v)

    if not labels:
        return go.Figure().update_layout(title="데이터 없음")

    fig = go.Figure(go.Bar(x=labels, y=values, marker_color='#636EFA',
                           text=[f"{v:.1f}%" for v in values], textposition="outside"))
    fig.update_layout(title=title, xaxis_title="소득 구간 (연소득)",
                      yaxis_title="비율 (%)", yaxis_range=[0, max(values)*1.3 if values else 100],
                      height=300)
    return fig


def job_donut_chart(income_row, title="직업군 분포"):
    """직업군 비율 도넛 차트"""
    job_cols = {
        "RATE_MODEL_GROUP_LARGE_COMPANY_EMPLOYEE": "대기업",
        "RATE_MODEL_GROUP_GENERAL_EMPLOYEE": "일반직원",
        "RATE_MODEL_GROUP_PROFESSIONAL_EMPLOYEE": "전문직",
        "RATE_MODEL_GROUP_EXECUTIVES": "임원",
        "RATE_MODEL_GROUP_GENERAL_SELF_EMPLOYED": "일반자영업",
        "RATE_MODEL_GROUP_PROFESSIONAL_SELF_EMPLOYED": "전문자영업",
        "RATE_MODEL_GROUP_OTHERS": "기타",
    }

    labels = []
    values = []
    for col, label in job_cols.items():
        if col in income_row.index and pd.notna(income_row[col]):
            labels.append(label)
            values.append(float(income_row[col]) * 100)

    if not labels:
        return go.Figure().update_layout(title="데이터 없음")

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.4,
        textinfo='label+percent', textposition='outside'
    ))
    fig.update_layout(title=title, height=350, showlegend=False)
    return fig


def hotplace_score_bar(scores_df, top_n=20, title="핫플 스코어 Top 20"):
    """핫플 스코어 상위 N개 바 차트"""
    top = scores_df.nlargest(top_n, "hotplace_score")

    fig = go.Figure(go.Bar(
        x=top["hotplace_score"],
        y=top.get("name", top["DISTRICT_CODE"]),
        orientation='h',
        marker_color=px.colors.sequential.YlOrRd[::-1][:top_n],
        text=top["hotplace_score"].round(1),
        textposition='outside'
    ))
    fig.update_layout(
        title=title, xaxis_title="핫플 스코어",
        yaxis=dict(autorange="reversed"),
        height=max(400, top_n * 25)
    )
    return fig
