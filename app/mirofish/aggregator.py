"""
MiroFish Lite — 라운드별 결과 집계
에이전트 의사결정 → 동네별 예측 지표 (방문자, 매출, 인구이동)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

from . import config
from .agent import AgentDecision


@dataclass
class RoundResult:
    """단일 라운드 집계 결과"""
    round_num: int
    # 동네별 지표 (DISTRICT_CODE → 값)
    visits: dict[str, float] = field(default_factory=dict)         # 가중 방문자 수
    spending: dict[str, float] = field(default_factory=dict)       # 가중 매출 (원)
    net_migration: dict[str, float] = field(default_factory=dict)  # 순 인구이동
    industry_demand: dict[str, dict[str, float]] = field(default_factory=dict)  # 동네×업종 수요
    # 전체 통계
    total_decisions: int = 0
    action_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class PredictionOutput:
    """전체 시뮬레이션 예측 결과"""
    n_rounds: int
    n_agents: int
    base_month: int
    round_results: list[RoundResult] = field(default_factory=list)
    # 동네별 집계
    surge_scores: dict[str, float] = field(default_factory=dict)
    decline_scores: dict[str, float] = field(default_factory=dict)
    visit_trends: dict[str, list[float]] = field(default_factory=dict)
    spending_trends: dict[str, list[float]] = field(default_factory=dict)
    migration_trends: dict[str, list[float]] = field(default_factory=dict)
    # 업종별
    industry_trends: dict[str, dict[str, list[float]]] = field(default_factory=dict)


class RoundAggregator:
    """라운드별 에이전트 결정 → 동네별 지표 집계"""

    def aggregate_round(
        self, decisions: list[AgentDecision], round_num: int,
    ) -> RoundResult:
        visits: dict[str, float] = defaultdict(float)
        spending: dict[str, float] = defaultdict(float)
        move_in: dict[str, float] = defaultdict(float)
        move_out: dict[str, float] = defaultdict(float)
        industry_demand: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        action_counts: dict[str, int] = defaultdict(int)

        for d in decisions:
            w = d.weight
            action_counts[d.action] += 1

            if d.action == config.ACTION_STAY:
                # 현재 동네에 머무르며 소비
                # target_district가 없으면 persona_id에서 동네 추출 불가 → skip
                # decisions에는 target이 없으므로, agent.current_district를 알아야 함
                # → 여기서는 target_district를 현재 동네로 간주
                dc = d.target_district or d.persona_id.split(":")[0]
                visits[dc] += w
                spending[dc] += d.monthly_spending * w
                if d.preferred_industry:
                    industry_demand[dc][d.preferred_industry] += w

            elif d.action == config.ACTION_VISIT:
                # 다른 동네 방문
                if d.target_district:
                    visits[d.target_district] += w
                    spending[d.target_district] += d.monthly_spending * w
                    if d.preferred_industry:
                        industry_demand[d.target_district][d.preferred_industry] += w

            elif d.action == config.ACTION_REDUCE:
                # 소비 감소 (현재 동네에 머무르지만 매출 감소)
                dc = d.target_district or d.persona_id.split(":")[0]
                visits[dc] += w
                spending[dc] += d.monthly_spending * w * 0.5  # 50% 감소

            elif d.action == config.ACTION_RELOCATE:
                # 이사: 출발지 인구 감소, 도착지 인구 증가
                from_dc = d.persona_id.split(":")[0] if ":" in d.persona_id else ""
                to_dc = d.target_district
                if from_dc:
                    move_out[from_dc] += w
                if to_dc:
                    move_in[to_dc] += w
                    visits[to_dc] += w
                    spending[to_dc] += d.monthly_spending * w

        # 순 인구이동
        all_dcs = set(move_in.keys()) | set(move_out.keys())
        net_migration = {dc: move_in[dc] - move_out[dc] for dc in all_dcs}

        return RoundResult(
            round_num=round_num,
            visits=dict(visits),
            spending=dict(spending),
            net_migration=net_migration,
            industry_demand={dc: dict(ind) for dc, ind in industry_demand.items()},
            total_decisions=len(decisions),
            action_counts=dict(action_counts),
        )

    def compile_predictions(
        self,
        round_results: list[RoundResult],
        n_agents: int,
        base_month: int,
    ) -> PredictionOutput:
        """전체 라운드 결과 → 예측 출력 컴파일"""
        n_rounds = len(round_results)
        all_districts = set()
        for rr in round_results:
            all_districts.update(rr.visits.keys())
            all_districts.update(rr.spending.keys())
            all_districts.update(rr.net_migration.keys())

        visit_trends: dict[str, list[float]] = {}
        spending_trends: dict[str, list[float]] = {}
        migration_trends: dict[str, list[float]] = {}
        industry_trends: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

        for dc in all_districts:
            visit_trends[dc] = [rr.visits.get(dc, 0) for rr in round_results]
            spending_trends[dc] = [rr.spending.get(dc, 0) for rr in round_results]
            migration_trends[dc] = [rr.net_migration.get(dc, 0) for rr in round_results]
            for rr in round_results:
                for ind, demand in rr.industry_demand.get(dc, {}).items():
                    industry_trends[dc][ind].append(demand)

        # 급등 점수: 방문자 증가 기울기 (0.5) + 매출 증가 기울기 (0.3) + 순이동 (0.2)
        surge_scores = {}
        decline_scores = {}
        for dc in all_districts:
            v_slope = self._trend_slope(visit_trends[dc])
            s_slope = self._trend_slope(spending_trends[dc])
            m_last = migration_trends[dc][-1] if migration_trends[dc] else 0
            score = v_slope * 0.5 + s_slope * 0.3 + (m_last / max(n_agents, 1)) * 0.2
            if score > 0:
                surge_scores[dc] = round(score, 4)
            else:
                decline_scores[dc] = round(abs(score), 4)

        return PredictionOutput(
            n_rounds=n_rounds,
            n_agents=n_agents,
            base_month=base_month,
            round_results=round_results,
            surge_scores=surge_scores,
            decline_scores=decline_scores,
            visit_trends=visit_trends,
            spending_trends=spending_trends,
            migration_trends=migration_trends,
            industry_trends=dict(industry_trends),
        )

    @staticmethod
    def _trend_slope(values: list[float]) -> float:
        """단순 선형회귀 기울기 (정규화)"""
        if len(values) < 2:
            return 0.0
        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)
        mean_y = y.mean()
        if mean_y == 0:
            return 0.0
        # 정규화된 기울기 (평균 대비 %)
        x_mean = x.mean()
        slope = np.sum((x - x_mean) * (y - mean_y)) / max(np.sum((x - x_mean) ** 2), 1e-10)
        return slope / mean_y * 100
