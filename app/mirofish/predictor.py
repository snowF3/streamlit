"""
MiroFish Lite — 예측 파이프라인 3종
1. predict_surge(): "다음 달 어디가 뜰까?"
2. predict_viability(): "여기에 가게를 열면?"
3. predict_trends(): "인구/소비 흐름은?"
+ run_prediction(): 전체 파이프라인 통합 실행
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .aggregator import PredictionOutput
from .simulator import MultiRoundSimulator
from . import config


# ── 예측 결과 데이터 클래스 ──

@dataclass
class DistrictSurgePrediction:
    """동네 급등/하락 예측"""
    district_code: str
    name: str
    surge_score: float          # 양수=급등, 음수=하락
    visit_growth: float         # 방문자 증가율 (%)
    spending_growth: float      # 매출 증가율 (%)
    net_migration: float        # 순 인구이동
    top_industry: str           # 가장 수요 높은 업종
    signal: str                 # "급등" / "상승" / "안정" / "하락" / "급락"


@dataclass
class BusinessViabilityReport:
    """사업성 분석 보고서"""
    district_code: str
    district_name: str
    industry: str
    expected_monthly_customers: int
    expected_monthly_revenue: int       # 원
    revenue_range: tuple[int, int]      # (하한, 상한) 원
    peak_hours: list[str]
    main_customer_segment: str
    competition_level: str              # "낮음" / "보통" / "높음"
    risk_factors: list[str]
    recommendation_score: int           # 1~5


@dataclass
class TrendReport:
    """인구/소비 트렌드 보고서"""
    surging_districts: list[dict]       # 상승 동네 top N
    declining_districts: list[dict]     # 하락 동네 top N
    industry_shifts: list[dict]         # 업종별 수요 변화
    population_flow: list[dict]         # 인구 이동 패턴


# ── 예측 함수 ──

def predict_surge(
    output: PredictionOutput,
    profiles: list[dict],
    top_n: int = 10,
) -> list[DistrictSurgePrediction]:
    """급등/하락 동네 예측"""
    name_map = {p["district_code"]: p["name"] for p in profiles}

    predictions = []
    all_districts = set(output.surge_scores.keys()) | set(output.decline_scores.keys())

    for dc in all_districts:
        surge = output.surge_scores.get(dc, 0)
        decline = output.decline_scores.get(dc, 0)
        score = surge - decline

        # 방문자/매출 추세
        v_trend = output.visit_trends.get(dc, [])
        s_trend = output.spending_trends.get(dc, [])
        m_trend = output.migration_trends.get(dc, [])

        v_growth = _pct_change(v_trend)
        s_growth = _pct_change(s_trend)
        net_mig = m_trend[-1] if m_trend else 0

        # 가장 수요 높은 업종
        top_ind = ""
        if dc in output.industry_trends:
            ind_totals = {
                ind: sum(vals)
                for ind, vals in output.industry_trends[dc].items()
            }
            if ind_totals:
                top_ind = max(ind_totals, key=ind_totals.get)

        # 시그널 분류
        if score > 0.5:
            signal = "급등"
        elif score > 0.1:
            signal = "상승"
        elif score > -0.1:
            signal = "안정"
        elif score > -0.5:
            signal = "하락"
        else:
            signal = "급락"

        predictions.append(DistrictSurgePrediction(
            district_code=dc,
            name=name_map.get(dc, dc),
            surge_score=round(score, 4),
            visit_growth=round(v_growth, 1),
            spending_growth=round(s_growth, 1),
            net_migration=round(net_mig, 1),
            top_industry=top_ind,
            signal=signal,
        ))

    predictions.sort(key=lambda x: x.surge_score, reverse=True)
    return predictions[:top_n]


def predict_viability(
    output: PredictionOutput,
    profiles: list[dict],
    target_district: str,
    industry: str,
) -> BusinessViabilityReport:
    """특정 동네+업종 사업성 분석"""
    name_map = {p["district_code"]: p["name"] for p in profiles}
    profile = next((p for p in profiles if p["district_code"] == target_district), {})

    # 해당 동네의 업종별 수요
    ind_trends = output.industry_trends.get(target_district, {})
    ind_demand = ind_trends.get(industry, [])
    avg_demand = sum(ind_demand) / len(ind_demand) if ind_demand else 0

    # 방문자 추세
    visit_trend = output.visit_trends.get(target_district, [])
    avg_visits = sum(visit_trend) / len(visit_trend) if visit_trend else 0

    # 매출 추세
    spend_trend = output.spending_trends.get(target_district, [])
    avg_spending = sum(spend_trend) / len(spend_trend) if spend_trend else 0

    # 예상 고객 수 (업종 수요 / 전체 방문자 비율로 추정)
    customers = int(avg_demand) if avg_demand > 0 else int(avg_visits * 0.02)

    # 예상 매출 (업종별 객단가 적용)
    ticket_map = {"카페": 5500, "음식점": 12000, "미용실": 25000, "소매점": 8000}
    ticket = ticket_map.get(industry, 8000)
    revenue = customers * ticket * 30
    rev_low = int(revenue * 0.7)
    rev_high = int(revenue * 1.3)

    # 피크 시간대
    flow = profile.get("flow", {})
    peak = flow.get("peak_hour", "T12")
    peak_kor = config.TIME_SLOT_KOR.get(peak, peak)
    peak_hours = [peak_kor]

    # 주 고객층
    pop = profile.get("population", {})
    dn = flow.get("day_night_ratio", 1.0)
    vr = pop.get("visitor", 0) / max(pop.get("total", 1), 1)
    if dn > 1.5:
        segment = "직장인 (주간 인구 우세)"
    elif vr > 0.4:
        segment = "방문객 (관광/상업 지역)"
    else:
        segment = "지역 주민 (주거 중심)"

    # 경쟁 수준
    hhi = profile.get("consumption", {}).get("hhi", 0)
    if hhi > 0.15:
        comp = "높음"
    elif hhi > 0.08:
        comp = "보통"
    else:
        comp = "낮음"

    # 리스크
    risks = []
    if dn > 3:
        risks.append("야간 매출 기대 낮음")
    if hhi > 0.15:
        risks.append("업종 경쟁 치열")
    if vr < 0.2:
        risks.append("외부 방문객 적음")
    v_growth = _pct_change(visit_trend)
    if v_growth < -5:
        risks.append(f"방문자 감소 추세 ({v_growth:.1f}%)")
    if not risks:
        risks.append("특별한 리스크 없음")

    # 추천 점수 (1~5)
    score = 3
    if avg_demand > 0:
        score += 1
    if v_growth > 5:
        score += 1
    if hhi > 0.15:
        score -= 1
    if v_growth < -5:
        score -= 1
    score = max(1, min(5, score))

    return BusinessViabilityReport(
        district_code=target_district,
        district_name=name_map.get(target_district, target_district),
        industry=industry,
        expected_monthly_customers=customers,
        expected_monthly_revenue=revenue,
        revenue_range=(rev_low, rev_high),
        peak_hours=peak_hours,
        main_customer_segment=segment,
        competition_level=comp,
        risk_factors=risks,
        recommendation_score=score,
    )


def predict_trends(
    output: PredictionOutput,
    profiles: list[dict],
    top_n: int = 5,
) -> TrendReport:
    """인구/소비 트렌드 분석"""
    name_map = {p["district_code"]: p["name"] for p in profiles}

    # 상승/하락 동네
    surge_list = sorted(output.surge_scores.items(), key=lambda x: x[1], reverse=True)
    decline_list = sorted(output.decline_scores.items(), key=lambda x: x[1], reverse=True)

    surging = [
        {"district_code": dc, "name": name_map.get(dc, dc), "score": round(s, 4),
         "visit_growth": round(_pct_change(output.visit_trends.get(dc, [])), 1)}
        for dc, s in surge_list[:top_n]
    ]
    declining = [
        {"district_code": dc, "name": name_map.get(dc, dc), "score": round(s, 4),
         "visit_growth": round(_pct_change(output.visit_trends.get(dc, [])), 1)}
        for dc, s in decline_list[:top_n]
    ]

    # 업종별 수요 변화 (전체 동네 합산)
    industry_totals: dict[str, list[float]] = {}
    for dc, ind_data in output.industry_trends.items():
        for ind, vals in ind_data.items():
            if ind not in industry_totals:
                industry_totals[ind] = [0.0] * output.n_rounds
            for i, v in enumerate(vals):
                if i < len(industry_totals[ind]):
                    industry_totals[ind][i] += v

    industry_shifts = [
        {"industry": ind, "growth": round(_pct_change(vals), 1), "total_demand": round(sum(vals), 0)}
        for ind, vals in industry_totals.items()
    ]
    industry_shifts.sort(key=lambda x: x["growth"], reverse=True)

    # 인구 이동 패턴
    population_flow = []
    for dc in output.migration_trends:
        m_trend = output.migration_trends[dc]
        total_migration = sum(m_trend)
        if abs(total_migration) > 0:
            population_flow.append({
                "district_code": dc,
                "name": name_map.get(dc, dc),
                "net_migration": round(total_migration, 0),
                "direction": "유입" if total_migration > 0 else "유출",
            })
    population_flow.sort(key=lambda x: abs(x["net_migration"]), reverse=True)

    return TrendReport(
        surging_districts=surging,
        declining_districts=declining,
        industry_shifts=industry_shifts[:10],
        population_flow=population_flow[:10],
    )


# ── 통합 실행 함수 ──

def run_prediction(
    profiles: list[dict],
    personas: list[dict],
    cluster_data: dict,
    n_rounds: int = config.DEFAULT_N_ROUNDS,
    n_agents: int = config.DEFAULT_N_AGENTS,
    base_month: int = 202412,
    district_codes: list[str] | None = None,
    progress_callback=None,
) -> dict:
    """
    MiroFish Lite 전체 예측 파이프라인

    Returns: {
        "simulation_output": PredictionOutput,
        "surge_predictions": list[DistrictSurgePrediction],
        "trend_report": TrendReport,
    }
    """
    sim = MultiRoundSimulator(n_rounds=n_rounds, n_agents=n_agents)
    sim_output = sim.run(
        profiles=profiles,
        personas=personas,
        cluster_data=cluster_data,
        base_month=base_month,
        district_codes=district_codes,
        progress_callback=progress_callback,
    )

    surge = predict_surge(sim_output, profiles)
    trends = predict_trends(sim_output, profiles)

    return {
        "simulation_output": sim_output,
        "surge_predictions": surge,
        "trend_report": trends,
    }


# ── 유틸리티 ──

def _pct_change(values: list[float]) -> float:
    """리스트의 첫 값 대비 마지막 값 변화율 (%)"""
    if len(values) < 2:
        return 0.0
    first = values[0]
    last = values[-1]
    if first == 0:
        return 0.0
    return (last - first) / first * 100
