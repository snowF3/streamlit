"""
MiroFish Lite — LLM 에이전트 (Snowflake Cortex)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import config
from .persona import Persona
from .memory import AgentMemory, RoundMemory
from .graph_query import GraphContextRetriever
from . import llm_client


@dataclass
class AgentDecision:
    """에이전트 1회 의사결정"""
    persona_id: str
    action: str
    target_district: str | None = None
    monthly_spending: int = 0
    preferred_industry: str = ""
    reasoning: str = ""
    weight: int = 1


class Agent:
    """Cortex 기반 시뮬레이션 에이전트"""

    def __init__(self, persona: Persona, current_district: str):
        self.persona = persona
        self.current_district = current_district
        self.memory = AgentMemory()

    def decide(
        self,
        round_num: int,
        total_rounds: int,
        ctx_retriever: GraphContextRetriever,
        market_signals: dict | None = None,
    ) -> AgentDecision:
        prompt = self._build_prompt(round_num, total_rounds, ctx_retriever, market_signals)
        response = llm_client.cortex_complete(prompt, system=config.SYSTEM_PROMPT_AGENT)
        return self._parse_response(response)

    def _build_prompt(self, round_num, total_rounds, ctx, signals):
        parts = [
            f"## 프로필\n{self.persona.description_kor()}",
            ctx.get_context_text(self.current_district),
            f"## 최근 기억\n{self.memory.summarize_for_prompt()}",
        ]

        if signals:
            sig_lines = []
            vd = signals.get("visit_delta", 0)
            sd = signals.get("spending_delta", 0)
            if vd != 0: sig_lines.append(f"- 방문자 추세: {vd:+.1f}%")
            if sd != 0: sig_lines.append(f"- 매출 추세: {sd:+.1f}%")
            if sig_lines:
                parts.append("## 시장 시그널\n" + "\n".join(sig_lines))

        parts.append(
            f"## 라운드 {round_num}/{total_rounds}\n"
            "4가지 중 선택: stay_and_spend / visit_neighbor / reduce_spending / relocate\n"
            'JSON 반환: {{"action":"...","target_district":"코드 or null",'
            '"monthly_spending":숫자,"preferred_industry":"업종","reasoning":"이유"}}'
        )
        return "\n\n".join(parts)

    def _parse_response(self, response: str) -> AgentDecision:
        try:
            m = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            data = json.loads(m.group()) if m else json.loads(response)
            action = data.get("action", config.ACTION_STAY)
            if action not in config.VALID_ACTIONS:
                action = config.ACTION_STAY
            return AgentDecision(
                persona_id=self.persona.persona_id,
                action=action,
                target_district=data.get("target_district"),
                monthly_spending=int(data.get("monthly_spending", 0)),
                preferred_industry=data.get("preferred_industry", ""),
                reasoning=data.get("reasoning", ""),
                weight=self.persona.weight,
            )
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            return AgentDecision(
                persona_id=self.persona.persona_id,
                action=config.ACTION_STAY,
                monthly_spending=max(200_000, self.persona.avg_income // 12),
                preferred_industry="식음료",
                reasoning="[기본값]",
                weight=self.persona.weight,
            )


def batch_decide(
    agents: list[Agent],
    round_num: int,
    total_rounds: int,
    ctx_retriever: GraphContextRetriever,
    market_signals_by_district: dict[str, dict] | None = None,
) -> list[AgentDecision]:
    """배치 의사결정 — 동일 아키타입+동네는 1회만 호출"""
    batches: dict[str, list[Agent]] = {}
    for agent in agents:
        key = f"{agent.current_district}:{agent.persona.archetype_key}"
        batches.setdefault(key, []).append(agent)

    all_decisions = []
    for batch_agents in batches.values():
        rep = batch_agents[0]
        signals = (market_signals_by_district or {}).get(rep.current_district)
        decision = rep.decide(round_num, total_rounds, ctx_retriever, signals)

        all_decisions.append(decision)
        for agent in batch_agents[1:]:
            clone = AgentDecision(
                persona_id=agent.persona.persona_id,
                action=decision.action,
                target_district=decision.target_district,
                monthly_spending=decision.monthly_spending,
                preferred_industry=decision.preferred_industry,
                reasoning=decision.reasoning,
                weight=agent.persona.weight,
            )
            if clone.action == config.ACTION_RELOCATE and clone.target_district:
                agent.current_district = clone.target_district
            all_decisions.append(clone)

    return all_decisions
