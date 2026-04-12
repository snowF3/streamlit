"""
MiroFish Lite v2 — 그래프 컨텍스트 (클러스터 단위)
"""
from __future__ import annotations

from . import config


class GraphContextRetriever:
    """클러스터 단위로 동네 데이터 테이블을 조립"""

    def __init__(self, graph: dict):
        self.G = graph

    def get_cluster_groups(self) -> dict[str, list[str]]:
        """클러스터 라벨 → 동네 코드 리스트"""
        groups: dict[str, list[str]] = {}
        for dc, info in self.G["clusters"].items():
            label = info.get("cluster_label", "기타")
            groups.setdefault(label, []).append(dc)
        return groups

    def build_cluster_prompt(
        self,
        cluster_label: str,
        district_codes: list[str],
        round_num: int,
        total_rounds: int,
        prev_results: dict[str, dict] | None = None,
    ) -> str:
        """클러스터 분석가용 프롬프트 조립"""
        parts = []

        # 담당 동네 테이블
        parts.append(f"## 담당 동네 ({len(district_codes)}개, 유형: {cluster_label})")
        header = "| 동네 | 유동인구 | 1인당매출 | 낮밤비 | HHI | 소득 | 방문비중 | 주요업종 |"
        sep = "|---|---|---|---|---|---|---|---|"
        rows = [header, sep]
        for dc in district_codes:
            prof = self.G["districts"].get(dc)
            if not prof:
                continue
            name = prof.get("name", dc)
            pop = prof.get("population", {})
            flow = prof.get("flow", {})
            cons = prof.get("consumption", {})
            fin = prof.get("finance", {})

            total = pop.get("total", 0)
            spc = cons.get("sales_per_capita", 0)
            dn = flow.get("day_night_ratio", 1.0)
            hhi = cons.get("hhi", 0)
            income = fin.get("avg_income", 0)
            vr = pop.get("visitor", 0) / max(total, 1)
            top_inds = ", ".join(cons.get("top3_categories", [])[:2])

            inc_str = f"{income/10:.0f}만" if income > 0 else "-"  # 천원→만원
            rows.append(
                f"| {name} | {total:,.0f} | {spc:,.0f}원 | {dn:.1f} | "
                f"{hhi:.3f} | {inc_str} | {vr:.0%} | {top_inds} |"
            )
        parts.append("\n".join(rows))

        # 이전 라운드 결과
        if prev_results:
            parts.append("\n## 이전 라운드 예측 결과")
            for dc in district_codes:
                pr = prev_results.get(dc)
                if pr:
                    name = self.G["districts"].get(dc, {}).get("name", dc)
                    parts.append(
                        f"- {name}: 방문자 {pr.get('visit_change_pct', 0):+.1f}%, "
                        f"매출 {pr.get('spending_change_pct', 0):+.1f}%, "
                        f"시그널: {pr.get('signal', '-')}"
                    )

        # 예측 요청
        dc_names = []
        for dc in district_codes:
            name = self.G["districts"].get(dc, {}).get("name", dc)
            dc_names.append(f'{{"district":"{name}","district_code":"{dc}",...}}')

        parts.append(
            f"\n## 예측 요청 (라운드 {round_num}/{total_rounds}, +{round_num}개월 후)\n"
            "각 동네의 다음 달 변화를 JSON 배열로 예측하세요.\n"
            '반드시 이 형식을 지키세요:\n'
            '{"predictions":[\n'
            '  {"district_code":"동네코드","visit_change_pct":숫자,'
            '"spending_change_pct":숫자,"net_migration":숫자,'
            '"hot_industry":"업종","declining_industry":"업종",'
            '"risk":"위험요소","signal":"급등|상승|안정|하락|급락"}\n'
            "]}"
        )

        return "\n\n".join(parts)
