"""
ML 예측 테스트 앱
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="ML 예측 테스트", layout="wide")
st.write("### ML FORECAST 테스트")

from data_loader import run_query, SPH

# 테스트 1: 시계열 데이터 준비
st.write("**1. 시계열 데이터 확인**")
try:
    df = run_query(f"""
        SELECT STANDARD_YEAR_MONTH as ts,
               ROUND(SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION)) as total_pop
        FROM {SPH}.FLOATING_POPULATION_INFO
        WHERE DISTRICT_CODE = '11140167'
        GROUP BY 1 ORDER BY 1
    """)
    st.write(f"행 수: {len(df)}")
    st.dataframe(df)
except Exception as e:
    st.error(f"시계열 데이터 오류: {e}")

# 테스트 2: ML FORECAST 시도
st.write("**2. SNOWFLAKE.ML.FORECAST 테스트**")
try:
    result = run_query(f"""
        CALL SNOWFLAKE.ML.FORECAST(
            INPUT_DATA => SYSTEM$QUERY_REFERENCE('
                SELECT STANDARD_YEAR_MONTH::TIMESTAMP_NTZ as ts,
                       SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION)::FLOAT as total_pop
                FROM {SPH}.FLOATING_POPULATION_INFO
                WHERE DISTRICT_CODE = ''11140167''
                GROUP BY 1 ORDER BY 1
            '),
            TIMESTAMP_COLNAME => 'TS',
            TARGET_COLNAME => 'TOTAL_POP',
            CONFIG_OBJECT => {{'prediction_interval': 0.95, 'on_error': 'skip'}}
        )
    """)
    st.write("ML FORECAST 성공!")
    st.dataframe(result)
except Exception as e:
    st.error(f"ML FORECAST 오류: {e}")

# 테스트 3: 대안 - Cortex로 예측
st.write("**3. Cortex 기반 예측 (대안)**")
try:
    from chat_ui import _cortex
    ts_data = df.to_string(index=False) if 'df' in dir() and not df.empty else "데이터 없음"
    prompt = f"""아래 월별 유동인구 데이터를 보고 향후 3개월을 예측하세요.

{ts_data}

규칙:
- 트렌드(상승/하락/정체)를 분석하세요
- 계절성이 있으면 반영하세요
- 향후 3개월 예측값을 표로 제시하세요
- 예측 근거를 설명하세요"""

    result = _cortex(prompt)
    st.write(result)
except Exception as e:
    st.error(f"Cortex 예측 오류: {e}")

st.write("테스트 완료")
