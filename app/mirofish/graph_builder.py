"""
MiroFish Lite — 지식그래프 (순수 dict 기반, NetworkX 불필요)
"""
from __future__ import annotations

from . import config


def build_district_graph(
    profiles: list[dict],
    cluster_data: dict,
) -> dict:
    """
    프로파일 + 클러스터 → dict 기반 그래프

    Returns: {
        "districts": {dc: profile_dict, ...},
        "similar": {dc: [(dc2, score), ...], ...},
        "clusters": {dc: {"id": int, "label": str}, ...},
        "industries": {dc: [업종1, 업종2, ...], ...},
    }
    """
    districts = {}
    industries = {}

    for prof in profiles:
        dc = prof["district_code"]
        districts[dc] = prof
        industries[dc] = prof.get("consumption", {}).get("top3_categories", [])

    similar = cluster_data.get("similar_map", {})
    clusters = cluster_data.get("district_cluster", {})

    return {
        "districts": districts,
        "similar": similar,
        "clusters": clusters,
        "industries": industries,
    }


def graph_stats(graph: dict) -> dict:
    return {
        "districts": len(graph["districts"]),
        "similar_edges": sum(len(v) for v in graph["similar"].values()),
        "clustered": len(graph["clusters"]),
    }
