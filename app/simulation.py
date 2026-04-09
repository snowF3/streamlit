"""
What-if 시뮬레이션 엔진 — Phase 1: 통계 기반
핵심 수식: 예상매출 = 유동인구 × capture_rate × avg_ticket × 30 × 소득보정
"""
from dataclasses import dataclass, field
import pandas as pd
import numpy as np


INDUSTRY_PARAMS = {
    "카페":   {"capture_rate": 0.015, "avg_ticket": 5500,  "visit_freq": 2.5},
    "음식점": {"capture_rate": 0.012, "avg_ticket": 12000, "visit_freq": 1.8},
    "미용실": {"capture_rate": 0.005, "avg_ticket": 25000, "visit_freq": 0.8},
}


@dataclass
class SimulationResult:
    monthly_revenue_low: float    # 만원
    monthly_revenue_mid: float
    monthly_revenue_high: float
    peak_hours: list = field(default_factory=list)
    main_customer: str = ""
    risk_factors: list = field(default_factory=list)


class StatisticalEngine:
    """Phase 1: 통계 기반 시뮬레이션 (유동인구 × 전환율 × 객단가)"""

    def simulate(
        self,
        district_code: str,
        industry: str,
        pop_time_df: pd.DataFrame,
        pop_agg_df: pd.DataFrame,
        income_agg_df: pd.DataFrame,
        derived_metrics: pd.DataFrame,
        year_month=None,
        rent: float = 0,
    ) -> SimulationResult:
        params = INDUSTRY_PARAMS.get(industry, INDUSTRY_PARAMS["카페"])

        # ── 해당 동 파생지표 ──
        if district_code in derived_metrics.index:
            dm = derived_metrics.loc[district_code]
        else:
            return SimulationResult(0, 0, 0, [], "데이터 없음", ["해당 동네 데이터가 없습니다"])

        footfall = dm.get("total_pop", 0)
        day_night = dm.get("day_night_ratio", 1.0)
        hhi = dm.get("consumption_hhi", 0)
        visit_ratio = dm.get("visit_ratio", 0)
        district_income = dm.get("avg_income", 0)

        # ── 소득 보정 ──
        overall_income = derived_metrics["avg_income"].mean()
        if overall_income > 0 and district_income > 0:
            income_correction = min(district_income / overall_income, 1.5)
        else:
            income_correction = 1.0

        # ── 핵심 수식 ──
        mid = footfall * params["capture_rate"] * params["avg_ticket"] * 30 * income_correction
        mid_man = round(mid / 10000)  # 만원 단위
        low = round(mid_man * 0.7)
        high = round(mid_man * 1.3)

        # ── 피크 시간대 (해당 동) ──
        peak_hours = []
        if pop_time_df is not None and not pop_time_df.empty:
            dc_time = pop_time_df[pop_time_df["DISTRICT_CODE"] == district_code].copy()
            if year_month is not None:
                dc_time = dc_time[dc_time["STANDARD_YEAR_MONTH"] == year_month]
            if not dc_time.empty:
                dc_time["total"] = (dc_time["RESIDENTIAL_POPULATION"]
                                    + dc_time["WORKING_POPULATION"]
                                    + dc_time["VISITING_POPULATION"])
                top3 = dc_time.groupby("TIME_SLOT")["total"].sum().nlargest(3)
                from charts import TIME_SLOT_KOR
                peak_hours = [TIME_SLOT_KOR.get(ts, ts) for ts in top3.index]

        # ── 주 고객층 ──
        if day_night > 1.5:
            main_customer = "직장인 (주간 유동인구 우세)"
        elif visit_ratio > 0.4:
            main_customer = "방문객 (관광/상업 지역)"
        else:
            main_customer = "지역 주민 (주거 중심)"

        # ── 리스크 ──
        risks = []
        if day_night > 3:
            risks.append("야간 매출 기대 낮음 (주간 편중 지역)")
        if hhi > 0.15:
            risks.append("특정 업종 편중 (신규 진입 경쟁 주의)")
        if visit_ratio < 0.2:
            risks.append("방문 유동인구 적음 (로컬 고객 의존)")
        if rent > 0 and mid_man > 0 and rent > mid_man * 0.3:
            risks.append(f"임대료 비중 {round(rent/mid_man*100)}% (30% 초과, 수익성 주의)")
        if not risks:
            risks.append("특별한 리스크 요인 없음")

        return SimulationResult(
            monthly_revenue_low=low,
            monthly_revenue_mid=mid_man,
            monthly_revenue_high=high,
            peak_hours=peak_hours,
            main_customer=main_customer,
            risk_factors=risks,
        )
