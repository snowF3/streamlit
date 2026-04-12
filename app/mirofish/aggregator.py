"""
MiroFish Lite v2 — 예측 집계
LLM이 직접 동네별 예측을 반환하므로 단순 구조화만 수행
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PredictionOutput:
    """전체 시뮬레이션 결과"""
    n_rounds: int
    n_districts: int
    cluster_labels: list[str] = field(default_factory=list)
    # 라운드별 원본 (dc → prediction dict)
    rounds: list[dict] = field(default_factory=list)
    # 동네별 집계
    surge_rankings: list[dict] = field(default_factory=list)
    decline_rankings: list[dict] = field(default_factory=list)
    industry_trends: list[dict] = field(default_factory=list)
    population_flows: list[dict] = field(default_factory=list)


def compile_predictions(
    sim_result: dict,
    profiles: list[dict],
) -> PredictionOutput:
    """시뮬레이션 결과 → PredictionOutput 구조화"""
    rounds = sim_result["rounds"]
    n_rounds = sim_result["n_rounds"]
    name_map = {p["district_code"]: p["name"] for p in profiles}

    all_dcs = set()
    for rnd in rounds:
        all_dcs.update(rnd.keys())

    # 동네별 트렌드 집계
    district_scores = []
    industry_hot = {}
    industry_decline = {}

    for dc in all_dcs:
        visit_changes = [rnd.get(dc, {}).get("visit_change_pct", 0) for rnd in rounds]
        spend_changes = [rnd.get(dc, {}).get("spending_change_pct", 0) for rnd in rounds]
        migrations = [rnd.get(dc, {}).get("net_migration", 0) for rnd in rounds]
        last_pred = rounds[-1].get(dc, {}) if rounds else {}

        avg_visit = sum(visit_changes) / max(len(visit_changes), 1)
        avg_spend = sum(spend_changes) / max(len(spend_changes), 1)
        total_migration = sum(migrations)
        score = avg_visit * 0.5 + avg_spend * 0.3 + min(max(total_migration / 100, -20), 20) * 0.2

        district_scores.append({
            "district_code": dc,
            "name": name_map.get(dc, dc),
            "score": round(score, 2),
            "visit_growth": round(avg_visit, 1),
            "spending_growth": round(avg_spend, 1),
            "net_migration": round(total_migration, 0),
            "hot_industry": last_pred.get("hot_industry", ""),
            "declining_industry": last_pred.get("declining_industry", ""),
            "risk": last_pred.get("risk", ""),
            "signal": last_pred.get("signal", "안정"),
        })

        # 업종 카운팅
        hi = last_pred.get("hot_industry", "")
        di = last_pred.get("declining_industry", "")
        if hi:
            industry_hot[hi] = industry_hot.get(hi, 0) + 1
        if di:
            industry_decline[di] = industry_decline.get(di, 0) + 1

    # 정렬
    district_scores.sort(key=lambda x: x["score"], reverse=True)
    surge = [d for d in district_scores if d["score"] > 0]
    decline = [d for d in reversed(district_scores) if d["score"] <= 0]

    # 업종 트렌드
    ind_trends = []
    all_inds = set(industry_hot.keys()) | set(industry_decline.keys())
    for ind in all_inds:
        h = industry_hot.get(ind, 0)
        d = industry_decline.get(ind, 0)
        ind_trends.append({
            "industry": ind,
            "hot_count": h,
            "decline_count": d,
            "net": h - d,
            "direction": "상승" if h > d else ("하락" if d > h else "보합"),
        })
    ind_trends.sort(key=lambda x: x["net"], reverse=True)

    # 인구 이동
    pop_flows = [
        {
            "district_code": d["district_code"],
            "name": d["name"],
            "net_migration": d["net_migration"],
            "direction": "유입" if d["net_migration"] > 0 else "유출",
        }
        for d in district_scores if d["net_migration"] != 0
    ]
    pop_flows.sort(key=lambda x: abs(x["net_migration"]), reverse=True)

    return PredictionOutput(
        n_rounds=n_rounds,
        n_districts=len(all_dcs),
        cluster_labels=sim_result.get("cluster_labels", []),
        rounds=rounds,
        surge_rankings=surge[:15],
        decline_rankings=decline[:10],
        industry_trends=ind_trends[:15],
        population_flows=pop_flows[:15],
    )
