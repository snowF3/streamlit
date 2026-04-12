"""
MiroFish Lite v2 — 보고서 생성 (Cortex)
"""
from __future__ import annotations

from . import config
from . import llm_client
from .aggregator import PredictionOutput


def generate_report(output: PredictionOutput) -> str:
    """예측 결과 → 자연어 보고서"""
    surge_lines = ""
    for i, d in enumerate(output.surge_rankings[:10]):
        surge_lines += (
            f"  {i+1}. {d['name']} ({d['signal']}) — "
            f"방문자 {d['visit_growth']:+.1f}%, 매출 {d['spending_growth']:+.1f}%, "
            f"인구 {d['net_migration']:+.0f}명, 주력: {d['hot_industry']}, "
            f"리스크: {d['risk']}\n"
        )

    decline_lines = ""
    for d in output.decline_rankings[:5]:
        decline_lines += f"  - {d['name']} ({d['signal']}): {d['risk']}\n"

    ind_lines = ""
    for t in output.industry_trends[:7]:
        ind_lines += f"  - {t['industry']}: {t['direction']} (상승 {t['hot_count']}개 동네 / 하락 {t['decline_count']}개 동네)\n"

    flow_lines = ""
    for f in output.population_flows[:5]:
        flow_lines += f"  - {f['name']}: {f['direction']} {abs(f['net_migration']):.0f}명\n"

    prompt = (
        f"## 시뮬레이션 개요\n"
        f"- {output.n_districts}개 동네, {output.n_rounds}개월 예측\n"
        f"- 클러스터 유형: {', '.join(output.cluster_labels)}\n\n"
        f"## 급등 예측 TOP 10\n{surge_lines}\n"
        f"## 주의 필요 동네\n{decline_lines}\n"
        f"## 업종 수요 변화\n{ind_lines}\n"
        f"## 인구 이동\n{flow_lines}\n\n"
        "위 데이터 기반 한국어 예측 보고서:\n"
        "1. 핵심 요약 (3줄)\n"
        "2. 뜨는 동네 TOP 5 분석 (구체적 이유)\n"
        "3. 주의 필요 동네\n"
        "4. 업종별 기회\n"
        "5. 인구 흐름 전망\n"
        "6. 투자/영업 추천"
    )
    return llm_client.cortex_complete(prompt, system=config.SYSTEM_PROMPT_REPORT)
