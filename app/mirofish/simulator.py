"""
MiroFish Lite — 멀티라운드 시뮬레이터 (Snowflake 환경)
"""
from __future__ import annotations

from . import config
from .graph_builder import build_district_graph
from .graph_query import GraphContextRetriever
from .persona import PersonaPool, Persona
from .agent import Agent, batch_decide
from .memory import RoundMemory
from .aggregator import RoundAggregator, PredictionOutput


class MultiRoundSimulator:

    def __init__(self, n_rounds=config.DEFAULT_N_ROUNDS, n_agents=config.DEFAULT_N_AGENTS):
        self.n_rounds = n_rounds
        self.n_agents = n_agents
        self.aggregator = RoundAggregator()

    def run(
        self,
        profiles: list[dict],
        personas: list[dict],
        cluster_data: dict,
        base_month: int = 202412,
        district_codes: list[str] | None = None,
        progress_callback=None,
    ) -> PredictionOutput:
        """
        전체 시뮬레이션

        progress_callback: (round_num, total_rounds, message) → None
            Streamlit progress bar 연결용
        """
        pool = PersonaPool(personas)
        sampled = pool.sample_agents(n_agents=self.n_agents, district_codes=district_codes)

        graph = build_district_graph(profiles, cluster_data)
        ctx = GraphContextRetriever(graph)

        agents = [Agent(persona=p, current_district=p.district_code) for p in sampled]

        round_results = []
        prev = None

        for rnd in range(1, self.n_rounds + 1):
            if progress_callback:
                progress_callback(rnd, self.n_rounds, f"라운드 {rnd}/{self.n_rounds} 시뮬레이션 중...")

            signals = self._calc_signals(prev)

            decisions = batch_decide(agents, rnd, self.n_rounds, ctx, signals)

            # stay 결정에 현재 동네 보강
            dc_map = {a.persona.persona_id: a.current_district for a in agents}
            for d in decisions:
                if d.action == config.ACTION_STAY and not d.target_district:
                    d.target_district = dc_map.get(d.persona_id, "")

            rr = self.aggregator.aggregate_round(decisions, rnd)
            round_results.append(rr)

            # 메모리 업데이트
            dmap = {d.persona_id: d for d in decisions}
            for agent in agents:
                d = dmap.get(agent.persona.persona_id)
                if d:
                    agent.memory.record(RoundMemory(
                        round_num=rnd, action=d.action,
                        target_district=d.target_district,
                        spending=d.monthly_spending,
                        industry=d.preferred_industry,
                        reasoning=d.reasoning,
                        district_visit_delta=rr.net_migration.get(agent.current_district, 0),
                    ))

            prev = rr

        return self.aggregator.compile_predictions(round_results, len(agents), base_month)

    def _calc_signals(self, prev) -> dict[str, dict] | None:
        if prev is None:
            return None
        signals = {}
        for dc in set(prev.visits.keys()) | set(prev.spending.keys()):
            v = prev.visits.get(dc, 0)
            m = prev.net_migration.get(dc, 0)
            signals[dc] = {
                "visit_delta": min(max(m / max(v, 1) * 100, -50), 50),
                "spending_delta": 0,
            }
        return signals
