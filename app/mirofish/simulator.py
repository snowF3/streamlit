"""
MiroFish Lite v2 — 클러스터 분석가 시뮬레이터
8개 클러스터 전문가 × N 라운드 = ~24 Cortex 호출로 118개 동네 예측
"""
from __future__ import annotations

import json
import re

from . import config
from . import llm_client
from .graph_builder import build_district_graph
from .graph_query import GraphContextRetriever


def run_simulation(
    profiles: list[dict],
    cluster_data: dict,
    n_rounds: int = config.DEFAULT_N_ROUNDS,
    progress_callback=None,
) -> dict:
    """
    클러스터 분석가 시뮬레이션 실행

    Returns: {
        "rounds": [
            {dc: {"visit_change_pct":..., "spending_change_pct":..., ...}, ...},  # 라운드1
            {...},  # 라운드2
            {...},  # 라운드3
        ],
        "n_rounds": int,
        "n_districts": int,
        "cluster_labels": list[str],
    }
    """
    graph = build_district_graph(profiles, cluster_data)
    ctx = GraphContextRetriever(graph)
    cluster_groups = ctx.get_cluster_groups()

    total_steps = len(cluster_groups) * n_rounds
    step = 0
    all_rounds = []
    prev_results = None

    for rnd in range(1, n_rounds + 1):
        round_predictions = {}

        for cluster_label, district_codes in cluster_groups.items():
            step += 1
            if progress_callback:
                progress_callback(
                    step, total_steps,
                    f"라운드 {rnd}/{n_rounds} — {cluster_label} 분석 중 ({len(district_codes)}개 동네)..."
                )

            # 프롬프트 조립
            system = config.SYSTEM_PROMPT_ANALYST.format(cluster_label=cluster_label)
            prompt = ctx.build_cluster_prompt(
                cluster_label=cluster_label,
                district_codes=district_codes,
                round_num=rnd,
                total_rounds=n_rounds,
                prev_results=prev_results,
            )

            # Cortex 호출
            response = llm_client.cortex_complete(prompt, system=system)

            # JSON 파싱
            parsed = _parse_predictions(response, district_codes)
            round_predictions.update(parsed)

        all_rounds.append(round_predictions)
        prev_results = round_predictions

    return {
        "rounds": all_rounds,
        "n_rounds": n_rounds,
        "n_districts": len(graph["districts"]),
        "cluster_labels": list(cluster_groups.keys()),
    }


def _parse_predictions(response: str, expected_dcs: list[str]) -> dict[str, dict]:
    """LLM 응답에서 동네별 예측 JSON 파싱"""
    result = {}

    try:
        # JSON 블록 추출
        json_match = re.search(r'\{[\s\S]*"predictions"[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(response)

        predictions = data.get("predictions", [])
        for pred in predictions:
            dc = pred.get("district_code", "")
            if dc:
                result[dc] = {
                    "visit_change_pct": float(pred.get("visit_change_pct", 0)),
                    "spending_change_pct": float(pred.get("spending_change_pct", 0)),
                    "net_migration": float(pred.get("net_migration", 0)),
                    "hot_industry": pred.get("hot_industry", ""),
                    "declining_industry": pred.get("declining_industry", ""),
                    "risk": pred.get("risk", ""),
                    "signal": pred.get("signal", "안정"),
                }
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        pass

    # 파싱 실패한 동네는 기본값
    for dc in expected_dcs:
        if dc not in result:
            result[dc] = {
                "visit_change_pct": 0, "spending_change_pct": 0,
                "net_migration": 0, "hot_industry": "", "declining_industry": "",
                "risk": "예측 데이터 부족", "signal": "안정",
            }

    return result
