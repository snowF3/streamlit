"""
MiroFish Lite — 페르소나 관리
아키타입 중복 제거 + 계층적 샘플링으로 대표 에이전트 풀 구성
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from collections import defaultdict

from . import config


@dataclass
class Persona:
    """개별 페르소나 (에이전트 시드)"""
    persona_id: str
    district_code: str
    gender: str             # M / F
    age_group: str          # 20대, 30대 등
    job_type: str           # 대기업, 자영업 등
    income_bracket: str     # ~2천만, 3~4천만 등
    weight: int             # 대표하는 실제 인구 수
    avg_income: int = 0

    @property
    def archetype_key(self) -> str:
        """아키타입 식별 키 (동네 무관, 인구통계 기준)"""
        return f"{self.gender}_{self.age_group}_{self.job_type}_{self.income_bracket}"

    @property
    def batch_key(self) -> str:
        """배치 그룹핑 키 (동네 + 아키타입)"""
        return f"{self.district_code}:{self.archetype_key}"

    def description_kor(self) -> str:
        """한글 설명 (프롬프트용)"""
        gender_kor = "남성" if self.gender == "M" else "여성"
        income_str = f"{self.avg_income:,}원" if self.avg_income > 0 else self.income_bracket
        return (
            f"{self.age_group} {gender_kor}, 직업: {self.job_type}, "
            f"소득: {income_str}, 대표 인구: {self.weight:,}명"
        )


class PersonaPool:
    """
    페르소나 풀 — 아키타입 중복 제거 + 계층 샘플링

    raw 페르소나 (~5,000개) → 아키타입 병합 → 대표 에이전트 샘플링 (~200개)
    """

    def __init__(self, raw_personas: list[dict]):
        self._raw = [self._to_persona(p) for p in raw_personas]
        self._archetypes: dict[str, Persona] = {}
        self._by_district: dict[str, list[Persona]] = defaultdict(list)
        self._merge_archetypes()

    @staticmethod
    def _to_persona(d: dict) -> Persona:
        return Persona(
            persona_id=d.get("persona_id", ""),
            district_code=d.get("district_code", ""),
            gender=d.get("gender", "M"),
            age_group=d.get("age_group", "30대"),
            job_type=d.get("job_type", "기타"),
            income_bracket=d.get("income_bracket", "미상"),
            weight=d.get("weight", 1),
            avg_income=d.get("avg_income", 0),
        )

    def _merge_archetypes(self):
        """동일 아키타입(동네+인구통계) 병합, weight 합산"""
        merged: dict[str, Persona] = {}
        for p in self._raw:
            key = p.batch_key
            if key in merged:
                merged[key].weight += p.weight
            else:
                merged[key] = Persona(
                    persona_id=key,
                    district_code=p.district_code,
                    gender=p.gender,
                    age_group=p.age_group,
                    job_type=p.job_type,
                    income_bracket=p.income_bracket,
                    weight=p.weight,
                    avg_income=p.avg_income,
                )
        self._archetypes = merged
        for p in merged.values():
            self._by_district[p.district_code].append(p)

    @property
    def all_archetypes(self) -> list[Persona]:
        return list(self._archetypes.values())

    @property
    def district_codes(self) -> list[str]:
        return list(self._by_district.keys())

    def get_by_district(self, district_code: str) -> list[Persona]:
        return self._by_district.get(district_code, [])

    def sample_agents(
        self,
        n_agents: int = config.DEFAULT_N_AGENTS,
        district_codes: list[str] | None = None,
        seed: int = 42,
    ) -> list[Persona]:
        """
        계층적 샘플링으로 대표 에이전트 선택

        각 동네에서 weight 비례 확률로 페르소나를 샘플링.
        전체 인구 분포를 유지하면서 에이전트 수를 제한.
        """
        rng = random.Random(seed)

        # 대상 동네 필터링
        if district_codes:
            pool = []
            for dc in district_codes:
                pool.extend(self.get_by_district(dc))
        else:
            pool = self.all_archetypes

        if not pool:
            return []

        # weight 기반 비례 샘플링
        total_weight = sum(p.weight for p in pool)
        if total_weight == 0:
            return pool[:n_agents]

        # 각 페르소나의 할당 에이전트 수 (최소 1)
        sampled = []
        for p in pool:
            proportion = p.weight / total_weight
            count = max(1, round(proportion * n_agents))
            # 원본 weight를 보존한 채 샘플 추가
            sampled.append(Persona(
                persona_id=p.persona_id,
                district_code=p.district_code,
                gender=p.gender,
                age_group=p.age_group,
                job_type=p.job_type,
                income_bracket=p.income_bracket,
                weight=p.weight,  # 원래 대표 인구 수 유지
                avg_income=p.avg_income,
            ))

        # 초과 시 weight 기준 상위만 유지
        if len(sampled) > n_agents:
            sampled.sort(key=lambda x: x.weight, reverse=True)
            sampled = sampled[:n_agents]

        rng.shuffle(sampled)
        return sampled

    def stats(self) -> dict:
        return {
            "raw_count": len(self._raw),
            "archetype_count": len(self._archetypes),
            "district_count": len(self._by_district),
            "total_weight": sum(p.weight for p in self._archetypes.values()),
        }
