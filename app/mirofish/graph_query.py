"""
MiroFish Lite — 그래프 컨텍스트 조회 (dict 기반)
"""
from __future__ import annotations

from . import config


class GraphContextRetriever:
    """dict 그래프에서 에이전트용 컨텍스트 추출"""

    def __init__(self, graph: dict):
        self.G = graph

    def get_context_text(self, district_code: str) -> str:
        """동네 컨텍스트 → 프롬프트 텍스트"""
        lines = []
        lines.append(f"## 현재 동네\n{self._district_summary(district_code)}")

        similars = self._similar_districts(district_code, top_k=3)
        if similars:
            lines.append("\n## 주변 옵션 (유사 동네)")
            for s in similars:
                lines.append(f"- **{s['name']}** (유사도 {s['similarity']:.0%}): {s['summary']}")

        inds = self.G["industries"].get(district_code, [])
        if inds:
            lines.append(f"\n## 주요 업종: {', '.join(inds)}")

        cl = self.G["clusters"].get(district_code, {})
        if cl:
            lines.append(f"## 동네 유형: {cl.get('cluster_label', '')}")

        return "\n".join(lines)

    def _district_summary(self, dc: str) -> str:
        prof = self.G["districts"].get(dc)
        if not prof:
            return "데이터 없음"

        name = prof.get("name", dc)
        pop = prof.get("population", {})
        flow = prof.get("flow", {})
        cons = prof.get("consumption", {})
        fin = prof.get("finance", {})

        total = pop.get("total", 0)
        dn = flow.get("day_night_ratio", 1.0)
        vr = pop.get("visitor", 0) / max(total, 1)
        spc = cons.get("sales_per_capita", 0)
        hhi = cons.get("hhi", 0)
        income = fin.get("avg_income", 0)
        tags = prof.get("tags", [])

        if dn > 1.5:
            char = "직장인구 우세의 오피스 상권"
        elif dn < 0.8:
            char = "야간 인구가 많은 주거 중심 지역"
        else:
            char = "주거와 상업이 균형 잡힌 복합 지역"

        parts = [
            f"{name}은(는) {char}이다.",
            f"총 유동인구 {total:,}명, 낮밤인구비 {dn:.1f}, 방문비중 {vr:.0%}.",
            f"1인당 매출 {spc:,}원, 소비집중도(HHI) {hhi:.3f}.",
        ]
        if income > 0:
            parts.append(f"평균소득 {income:,}원.")
        if tags:
            parts.append(f"특성: {', '.join(tags)}.")
        return " ".join(parts)

    def _similar_districts(self, dc: str, top_k: int = 3) -> list[dict]:
        pairs = self.G["similar"].get(dc, [])
        results = []
        for sim_dc, score in pairs[:top_k]:
            prof = self.G["districts"].get(sim_dc)
            if not prof:
                continue
            pop = prof.get("population", {})
            cons = prof.get("consumption", {})
            fl = prof.get("flow", {})
            results.append({
                "district_code": sim_dc,
                "name": prof.get("name", sim_dc),
                "similarity": score,
                "summary": (
                    f"유동인구 {pop.get('total', 0):,}명, "
                    f"1인당매출 {cons.get('sales_per_capita', 0):,}원, "
                    f"낮밤비 {fl.get('day_night_ratio', 1.0):.1f}"
                ),
            })
        return results
