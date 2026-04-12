"""
MiroFish Lite — 보고서 생성 (Cortex LLM)
"""
from __future__ import annotations

from . import config
from . import llm_client
from .predictor import DistrictSurgePrediction, TrendReport
from .aggregator import PredictionOutput


def generate_surge_text(
    surge_predictions: list[DistrictSurgePrediction],
    trend_report: TrendReport,
    sim_output: PredictionOutput,
) -> str:
    """급등 예측 자연어 보고서"""
    surge_table = ""
    for i, sp in enumerate(surge_predictions[:10]):
        surge_table += (
            f"  {i+1}. {sp.name} ({sp.signal}) — "
            f"방문자 {sp.visit_growth:+.1f}%, 매출 {sp.spending_growth:+.1f}%, "
            f"인구이동 {sp.net_migration:+.0f}명, 주력: {sp.top_industry}\n"
        )

    industry_lines = ""
    for s in trend_report.industry_shifts[:5]:
        industry_lines += f"  - {s['industry']}: {s['growth']:+.1f}%\n"

    flow_lines = ""
    for f in trend_report.population_flow[:5]:
        flow_lines += f"  - {f['name']}: {f['direction']} {abs(f['net_migration']):.0f}명\n"

    prompt = (
        f"## 시뮬레이션 개요\n"
        f"- {sim_output.n_agents}명 AI 에이전트, {sim_output.n_rounds}개월 예측\n"
        f"- 기준월: {sim_output.base_month}\n\n"
        f"## 급등 예측 순위\n{surge_table}\n"
        f"## 업종 수요 변화\n{industry_lines}\n"
        f"## 인구 이동\n{flow_lines}\n\n"
        "위 데이터 기반 한국어 예측 보고서를 작성하세요:\n"
        "1. 핵심 요약 (3줄)\n"
        "2. 뜨는 동네 TOP 5 분석\n"
        "3. 주의 필요 동네\n"
        "4. 업종별 기회\n"
        "5. 인구 흐름 전망"
    )
    return llm_client.cortex_complete(prompt, system=config.SYSTEM_PROMPT_REPORT)


def generate_viability_text(viability_data: dict) -> str:
    """사업성 분석 자연어 보고서"""
    j = viability_data
    prompt = (
        f"## 사업성 데이터\n"
        f"- 동네: {j['district_name']}, 업종: {j['industry']}\n"
        f"- 예상 월 고객: {j['expected_monthly_customers']:,}명\n"
        f"- 예상 월 매출: {j['expected_monthly_revenue']:,}원 "
        f"({j['revenue_range'][0]:,} ~ {j['revenue_range'][1]:,}원)\n"
        f"- 피크: {', '.join(j['peak_hours'])}\n"
        f"- 고객층: {j['main_customer']}\n"
        f"- 경쟁: {j['competition_level']}\n"
        f"- 리스크: {', '.join(j['risk_factors'])}\n"
        f"- 추천 점수: {j['recommendation_score']}/5\n\n"
        "한국어 사업성 분석:\n1. 종합 판단\n2. 매출 전망\n3. 고객 분석\n4. 시간대 전략\n5. 리스크"
    )
    return llm_client.cortex_complete(prompt, system=config.SYSTEM_PROMPT_REPORT)
