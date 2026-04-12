"""
MiroFish Lite v2 — 예측 파이프라인 (클러스터 분석가 구조)
"""
from __future__ import annotations

from . import config
from .simulator import run_simulation
from .aggregator import compile_predictions, PredictionOutput


def run_prediction(
    profiles: list[dict],
    cluster_data: dict,
    n_rounds: int = config.DEFAULT_N_ROUNDS,
    progress_callback=None,
) -> dict:
    """
    MiroFish Lite v2 전체 파이프라인

    Returns: {
        "output": PredictionOutput,
        "raw": dict (시뮬레이션 원본),
    }
    """
    raw = run_simulation(
        profiles=profiles,
        cluster_data=cluster_data,
        n_rounds=n_rounds,
        progress_callback=progress_callback,
    )

    output = compile_predictions(raw, profiles)

    return {
        "output": output,
        "raw": raw,
    }
