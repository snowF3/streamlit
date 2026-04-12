"""
MiroFish Lite — LLM 클라이언트 (Snowflake Cortex)
"""
from __future__ import annotations

import hashlib
from typing import Optional

from . import config

# 프롬프트 캐시 (session 내 메모리)
_cache: dict[str, str] = {}


def cortex_complete(prompt: str, system: Optional[str] = None) -> str:
    """Snowflake Cortex LLM 호출"""
    from data_loader import run_query

    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    # 캐시 확인
    key = hashlib.md5(full_prompt.encode()).hexdigest()
    if key in _cache:
        return _cache[key]

    try:
        safe = full_prompt.replace("'", "''").replace("\\", "\\\\")
        r = run_query(
            f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{config.CORTEX_MODEL}','{safe}') as r"
        )
        result = str(r.iloc[0, 0]) if not r.empty else ""
    except Exception as e:
        result = f'{{"action":"stay_and_spend","target_district":null,"monthly_spending":200000,"preferred_industry":"식음료","reasoning":"LLM 오류: {e}"}}'

    _cache[key] = result
    return result


def batch_complete(prompts: list[str], system: Optional[str] = None) -> list[str]:
    """배치 Cortex 호출"""
    return [cortex_complete(p, system) for p in prompts]


def cache_stats() -> dict:
    return {"entries": len(_cache)}


def clear_cache():
    _cache.clear()
