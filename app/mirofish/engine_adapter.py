"""
MiroFish Lite — SimulationEngine 어댑터 (Snowflake 환경)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simulation import SimulationEngine, SimulationResult, INDUSTRY_PARAMS

from . import config
from .persona import PersonaPool
from .graph_builder import build_district_graph
from .graph_query import GraphContextRetriever
from .agent import Agent, batch_decide
from .memory import RoundMemory
from .aggregator import RoundAggregator


class MiroFishLiteEngine(SimulationEngine):
    """Streamlit에서 get_engine('mirofish')로 사용"""

    @property
    def engine_name(self) -> str:
        return "MiroFish Lite AI 엔진"

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
        # 미니 프로파일/페르소나/클러스터 생성
        profiles, similar_dcs = self._build_profiles(district_code, derived_metrics, year_month)
        if not profiles:
            return SimulationResult(0, 0, 0, [], "데이터 없음", ["해당 동네 데이터 없음"])

        personas = self._build_personas(district_code, similar_dcs, derived_metrics)
        cluster_data = self._build_cluster(district_code, similar_dcs)

        # 50 에이전트 x 3 라운드 시뮬레이션
        pool = PersonaPool(personas)
        sampled = pool.sample_agents(n_agents=50, district_codes=[district_code] + similar_dcs)
        graph = build_district_graph(profiles, cluster_data)
        ctx = GraphContextRetriever(graph)
        agg = RoundAggregator()

        agents = [Agent(p, p.district_code) for p in sampled]
        round_results = []

        for rnd in range(1, 4):
            decisions = batch_decide(agents, rnd, 3, ctx)
            dc_map = {a.persona.persona_id: a.current_district for a in agents}
            for d in decisions:
                if d.action == config.ACTION_STAY and not d.target_district:
                    d.target_district = dc_map.get(d.persona_id, "")
            rr = agg.aggregate_round(decisions, rnd)
            round_results.append(rr)

        # 결과 변환
        visits = [rr.visits.get(district_code, 0) for rr in round_results]
        spending = [rr.spending.get(district_code, 0) for rr in round_results]

        params = INDUSTRY_PARAMS.get(industry, INDUSTRY_PARAMS.get("카페", {}))
        ticket = params.get("avg_ticket", 8000)
        avg_spend = sum(spending) / max(len(spending), 1)
        mid = int(avg_spend / 10000) if avg_spend > 0 else 0
        low, high = int(mid * 0.7), int(mid * 1.3)

        prof = profiles[0] if profiles else {}
        dn = prof.get("flow", {}).get("day_night_ratio", 1.0)
        peak = prof.get("flow", {}).get("peak_hour", "T12")
        vr = prof.get("population", {}).get("visitor", 0) / max(prof.get("population", {}).get("total", 1), 1)

        if dn > 1.5:
            cust = "직장인 (AI 에이전트 분석)"
        elif vr > 0.4:
            cust = "방문객 (AI 에이전트 분석)"
        else:
            cust = "지역 주민 (AI 에이전트 분석)"

        risks = []
        if dn > 3: risks.append("야간 매출 기대 낮음")
        if visits and visits[0] > 0:
            vc = (visits[-1] - visits[0]) / visits[0] * 100
            if vc < -10: risks.append(f"방문 감소 추세 ({vc:.1f}%)")
        if not risks: risks.append("특이 리스크 없음")

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
        # 유사 동네 5개 (파생지표 거리 기반)
        similar_dcs = []
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
                similar_dcs.append(sdc)
        except Exception:
            pass
        return profiles, similar_dcs

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

    def _build_personas(self, dc, similar_dcs, dm):
        personas = []
        archetypes = [
            ("M", "30대", "대기업", "4~5천만"),
            ("F", "20대", "일반직장", "3~4천만"),
            ("M", "40대", "자영업", "5~6천만"),
            ("F", "30대", "전문직", "5~6천만"),
            ("M", "50대", "기타", "3~4천만"),
            ("F", "40대", "일반직장", "4~5천만"),
        ]
        for target in [dc] + similar_dcs:
            if target not in dm.index: continue
            pop = dm.loc[target].get("total_pop", 1000)
            inc = dm.loc[target].get("avg_income", 40_000_000)
            for g, a, j, b in archetypes:
                personas.append({
                    "persona_id": f"{target}:{g}_{a}_{j}",
                    "district_code": target, "gender": g, "age_group": a,
                    "job_type": j, "income_bracket": b,
                    "weight": max(1, int(pop / 6)), "avg_income": int(inc),
                })
        return personas

    def _build_cluster(self, dc, similar_dcs):
        sim_map = {dc: [(s, 0.8) for s in similar_dcs]}
        for s in similar_dcs: sim_map[s] = [(dc, 0.8)]
        cl = {d: {"cluster_id": 0, "cluster_label": "분석 대상"} for d in [dc] + similar_dcs}
        return {"similar_map": sim_map, "district_cluster": cl, "type_map": {0: "분석 대상"}}
