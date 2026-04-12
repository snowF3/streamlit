"""
MiroFish Lite v2 — SimulationEngine 어댑터
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simulation import SimulationEngine, SimulationResult, INDUSTRY_PARAMS

from . import config
from .simulator import run_simulation


class MiroFishLiteEngine(SimulationEngine):
    """get_engine('mirofish')로 사용"""

    @property
    def engine_name(self) -> str:
        return "MiroFish Lite v2"

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
        # 미니 프로파일 + 클러스터 구성
        profiles, sim_dcs = self._build_profiles(district_code, derived_metrics, year_month)
        if not profiles:
            return SimulationResult(0, 0, 0, [], "데이터 없음", ["해당 동네 데이터 없음"])

        cluster_data = self._build_cluster(district_code, sim_dcs)

        # 2라운드 시뮬레이션 (단일 동네 분석은 가벼운 호출)
        raw = run_simulation(profiles=profiles, cluster_data=cluster_data, n_rounds=2)

        # 해당 동네 예측 추출
        last_round = raw["rounds"][-1] if raw["rounds"] else {}
        pred = last_round.get(district_code, {})

        params = INDUSTRY_PARAMS.get(industry, INDUSTRY_PARAMS.get("카페", {}))
        prof = profiles[0]
        total_pop = prof.get("population", {}).get("total", 0)
        spc = prof.get("consumption", {}).get("sales_per_capita", 0)

        # 매출 추정
        base_revenue = total_pop * params.get("capture_rate", 0.015) * params.get("avg_ticket", 5500) * 30
        change = 1 + pred.get("spending_change_pct", 0) / 100
        mid = int(base_revenue * change / 10000)
        low, high = int(mid * 0.7), int(mid * 1.3)

        flow = prof.get("flow", {})
        dn = flow.get("day_night_ratio", 1.0)
        peak = flow.get("peak_hour", "T12")

        if dn > 1.5:
            cust = "직장인 (AI 분석)"
        elif prof.get("population", {}).get("visitor", 0) / max(total_pop, 1) > 0.4:
            cust = "방문객 (AI 분석)"
        else:
            cust = "지역 주민 (AI 분석)"

        risks = []
        risk_text = pred.get("risk", "")
        if risk_text:
            risks.append(risk_text)
        if not risks:
            risks.append("특이 리스크 없음")

        return SimulationResult(
            monthly_revenue_low=low, monthly_revenue_mid=mid, monthly_revenue_high=high,
            peak_hours=[config.TIME_SLOT_KOR.get(peak, peak)],
            main_customer=cust, risk_factors=risks,
            competition_index=0.0, time_revenue_dist={},
        )

    def _build_profiles(self, dc, dm, ym):
        if dc not in dm.index:
            return [], []
        profiles = [self._make_profile(dc, dm, ym)]
        sim_dcs = []
        try:
            normed = dm.copy()
            for col in normed.columns:
                std = normed[col].std()
                if std > 0:
                    normed[col] = (normed[col] - normed[col].mean()) / std
            target = normed.loc[dc]
            dists = normed.drop(dc, errors="ignore").apply(lambda r: ((r - target) ** 2).sum(), axis=1)
            for sdc in dists.nsmallest(5).index:
                profiles.append(self._make_profile(sdc, dm, ym))
                sim_dcs.append(sdc)
        except Exception:
            pass
        return profiles, sim_dcs

    def _make_profile(self, dc, dm, ym):
        row = dm.loc[dc]
        total = row.get("total_pop", 0)
        vr = row.get("visit_ratio", 0)
        visitor = int(total * vr)
        worker = int((total - visitor) * 0.5)
        resident = int(total - visitor - worker)
        return {
            "district_code": dc, "name": dc, "snapshot_month": ym or 0,
            "population": {"total": int(total), "resident": resident, "worker": worker, "visitor": visitor},
            "flow": {"day_night_ratio": row.get("day_night_ratio", 1.0), "peak_hour": "T12", "weekend_reversal": 1.0},
            "consumption": {
                "total_sales": int(row.get("sales_per_capita", 0) * total),
                "top3_categories": ["식음료", "커피", "소매"],
                "hhi": row.get("consumption_hhi", 0.1),
                "sales_per_capita": int(row.get("sales_per_capita", 0)),
            },
            "finance": {"avg_income": int(row.get("avg_income", 0)), "income_consumption_gap": 1.0, "credit_score": 700},
            "tags": [],
        }

    def _build_cluster(self, dc, sim_dcs):
        all_dcs = [dc] + sim_dcs
        sim_map = {dc: [(s, 0.8) for s in sim_dcs]}
        for s in sim_dcs:
            sim_map[s] = [(dc, 0.8)]
        cl = {d: {"cluster_id": 0, "cluster_label": "분석 대상"} for d in all_dcs}
        return {"similar_map": sim_map, "district_cluster": cl, "type_map": {0: "분석 대상"}}
