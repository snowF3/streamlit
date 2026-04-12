"""
MiroFish Lite — 에이전트 메모리
단기 (최근 2라운드 결정) + 장기 (관찰된 트렌드) 메모리 관리
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RoundMemory:
    """한 라운드의 의사결정 기록"""
    round_num: int
    action: str
    target_district: str | None = None
    spending: int = 0
    industry: str = ""
    reasoning: str = ""
    # 라운드 종료 후 관찰된 시장 시그널
    district_visit_delta: float = 0.0  # 방문자 변화율 (%)
    district_spending_delta: float = 0.0  # 매출 변화율 (%)


class AgentMemory:
    """에이전트 단기/장기 메모리"""

    def __init__(self, max_short_term: int = 2):
        self._short_term: list[RoundMemory] = []
        self._max_short = max_short_term
        # 장기: 관찰한 동네별 트렌드 (동네코드 → 누적 변화율)
        self._trend_observations: dict[str, float] = {}

    def record(self, memory: RoundMemory):
        """라운드 결정 기록"""
        self._short_term.append(memory)
        if len(self._short_term) > self._max_short:
            self._short_term = self._short_term[-self._max_short:]

    def update_trends(self, district_deltas: dict[str, float]):
        """라운드 결과에서 관찰된 동네별 트렌드 업데이트"""
        for dc, delta in district_deltas.items():
            prev = self._trend_observations.get(dc, 0)
            # 지수이동평균
            self._trend_observations[dc] = prev * 0.5 + delta * 0.5

    def summarize_for_prompt(self, max_chars: int = 400) -> str:
        """프롬프트용 메모리 요약"""
        if not self._short_term:
            return "아직 이전 결정이 없습니다."

        lines = []
        for m in self._short_term:
            action_kor = {
                "stay_and_spend": "현재 동네에서 소비",
                "visit_neighbor": "다른 동네 방문",
                "reduce_spending": "소비 줄임",
                "relocate": "이사",
            }.get(m.action, m.action)

            line = f"- 라운드 {m.round_num}: {action_kor}"
            if m.target_district:
                line += f" (→ {m.target_district})"
            if m.spending > 0:
                line += f", {m.spending:,}원 소비"
            if m.industry:
                line += f" ({m.industry})"
            lines.append(line)

            if m.district_visit_delta != 0:
                lines.append(
                    f"  → 동네 방문자 {m.district_visit_delta:+.1f}%, "
                    f"매출 {m.district_spending_delta:+.1f}%"
                )

        # 장기 트렌드
        if self._trend_observations:
            rising = [(dc, d) for dc, d in self._trend_observations.items() if d > 2]
            falling = [(dc, d) for dc, d in self._trend_observations.items() if d < -2]
            if rising:
                rising.sort(key=lambda x: x[1], reverse=True)
                top = rising[:2]
                lines.append(f"- 상승 트렌드: {', '.join(dc for dc, _ in top)}")
            if falling:
                falling.sort(key=lambda x: x[1])
                bottom = falling[:2]
                lines.append(f"- 하락 트렌드: {', '.join(dc for dc, _ in bottom)}")

        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars - 3] + "..."
        return text

    @property
    def last_action(self) -> str | None:
        if self._short_term:
            return self._short_term[-1].action
        return None

    @property
    def last_district(self) -> str | None:
        if self._short_term:
            return self._short_term[-1].target_district
        return None
