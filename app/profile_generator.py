"""
법정동 프로파일 생성기 — Layer 2 → Layer 3 변환
- generate_profile_json(): 파생지표 DataFrame → MiroFish용 JSON 스키마
- generate_profile_text(): JSON → GraphRAG 시드 텍스트 (자연어 설명)
"""
import pandas as pd
import numpy as np

# 업종별 한글 라벨 매핑 (CARD_SALES_INFO 컬럼명 → 한글)
SALES_CATEGORY_KOR = {
    "FOOD_SALES": "식음료",
    "COFFEE_SALES": "커피",
    "ENTERTAINMENT_SALES": "유흥",
    "DEPARTMENT_STORE_SALES": "백화점",
    "LARGE_DISCOUNT_STORE_SALES": "대형마트",
    "SMALL_RETAIL_STORE_SALES": "소매",
    "CLOTHING_ACCESSORIES_SALES": "의류/잡화",
    "SPORTS_CULTURE_LEISURE_SALES": "스포츠/문화/레저",
    "ACCOMMODATION_SALES": "숙박",
    "TRAVEL_SALES": "여행",
    "BEAUTY_SALES": "뷰티",
    "HOME_LIFE_SERVICE_SALES": "생활서비스",
    "EDUCATION_ACADEMY_SALES": "교육/학원",
    "MEDICAL_SALES": "의료",
    "ELECTRONICS_FURNITURE_SALES": "가전/가구",
    "CAR_SALES": "자동차",
    "CAR_SERVICE_SUPPLIES_SALES": "자동차서비스",
    "GAS_STATION_SALES": "주유",
    "E_COMMERCE_SALES": "이커머스",
}

TIME_SLOT_KOR = {
    "T06": "아침(6~9)", "T09": "오전(9~12)", "T12": "점심(12~15)",
    "T15": "오후(15~18)", "T18": "저녁(18~21)", "T21": "심야(21~24)",
    "T24": "기타",
}


def _get_top3_categories(card_row: pd.Series) -> list[str]:
    """카드매출 row에서 상위 3개 업종 한글명 반환"""
    cat_values = {}
    for col, kor in SALES_CATEGORY_KOR.items():
        val = card_row.get(col, 0)
        if pd.notna(val) and val > 0:
            cat_values[kor] = val
    sorted_cats = sorted(cat_values.items(), key=lambda x: x[1], reverse=True)
    return [c[0] for c in sorted_cats[:3]]


def _get_peak_hour(pop_time_dc: pd.DataFrame) -> str:
    """시간대별 데이터에서 피크 시간대 반환"""
    if pop_time_dc.empty:
        return "T12"
    total_col = "total_pop" if "total_pop" in pop_time_dc.columns else "total"
    if total_col not in pop_time_dc.columns:
        pop_time_dc = pop_time_dc.copy()
        pop_time_dc["total"] = (
            pop_time_dc.get("RESIDENTIAL_POPULATION", 0)
            + pop_time_dc.get("WORKING_POPULATION", 0)
            + pop_time_dc.get("VISITING_POPULATION", 0)
        )
        total_col = "total"
    by_slot = pop_time_dc.groupby("TIME_SLOT")[total_col].sum()
    return by_slot.idxmax() if not by_slot.empty else "T12"


def _calc_weekend_reversal(pop_time_dc: pd.DataFrame) -> float:
    """주말 반전 지수: 주말 방문인구 / 주중 방문인구"""
    if pop_time_dc.empty:
        return 1.0
    visit_col = "VISITING_POPULATION"
    if visit_col not in pop_time_dc.columns:
        return 1.0
    weekday = pop_time_dc[pop_time_dc["WEEKDAY_WEEKEND"] == "W"][visit_col].sum()
    weekend = pop_time_dc[pop_time_dc["WEEKDAY_WEEKEND"] == "H"][visit_col].sum()
    if weekday == 0:
        return 1.0
    return round(weekend / weekday, 2)


def _classify_tags(profile: dict) -> list[str]:
    """프로파일에서 특성 태그 자동 생성"""
    tags = []
    flow = profile.get("flow", {})
    consumption = profile.get("consumption", {})
    population = profile.get("population", {})

    dn_ratio = flow.get("day_night_ratio", 1.0)
    if dn_ratio > 1.5:
        tags.append("직장인 상권")
    elif dn_ratio < 0.8:
        tags.append("베드타운")

    weekend_rev = flow.get("weekend_reversal", 1.0)
    if weekend_rev > 1.2:
        tags.append("여가/관광형")
    elif weekend_rev < 0.8:
        tags.append("비즈니스형")

    hhi = consumption.get("hhi", 0)
    if hhi < 0.05:
        tags.append("소비다양")
    elif hhi > 0.15:
        tags.append("소비특화")

    top3 = consumption.get("top3_categories", [])
    if "커피" in top3[:2] or "식음료" in top3[:2]:
        tags.append("점심특화")

    total = population.get("total", 0)
    visitor = population.get("visitor", 0)
    if total > 0 and visitor / total > 0.4:
        tags.append("방문객 중심")

    return tags if tags else ["일반"]


def generate_profile_json(
    district_code: str,
    name: str,
    snapshot_month: int,
    derived_metrics: pd.DataFrame,
    card_agg_df: pd.DataFrame,
    pop_time_df: pd.DataFrame,
    income_agg_df: pd.DataFrame,
) -> dict:
    """
    Layer 2 데이터 → Layer 3 MiroFish용 JSON 프로파일 변환

    Parameters
    ----------
    district_code : str  법정동 코드
    name : str           "구 동" 형태의 이름
    snapshot_month : int  기준 년월 (예: 202412)
    derived_metrics : DataFrame  calc_derived_metrics() 결과 (index=DISTRICT_CODE)
    card_agg_df : DataFrame  load_card_sales_agg() 결과
    pop_time_df : DataFrame  load_population_time() 결과
    income_agg_df : DataFrame  load_income_agg() 결과

    Returns
    -------
    dict  기획안 Layer 3 JSON 스키마
    """
    # 파생지표
    if district_code in derived_metrics.index:
        dm = derived_metrics.loc[district_code]
    else:
        dm = pd.Series(dtype=float)

    total_pop = int(dm.get("total_pop", 0))
    visit_ratio = float(dm.get("visit_ratio", 0))
    day_night_ratio = float(dm.get("day_night_ratio", 1.0))
    sales_per_capita = int(dm.get("sales_per_capita", 0))
    hhi = float(dm.get("consumption_hhi", 0))
    avg_income = float(dm.get("avg_income", 0))

    # 인구 구성 역산 (visit_ratio로부터)
    visitor = int(total_pop * visit_ratio) if total_pop > 0 else 0
    non_visitor = total_pop - visitor
    # 거주:직장 비율 — day_night_ratio로 추정
    if day_night_ratio > 1:
        worker = int(non_visitor * min(day_night_ratio / (1 + day_night_ratio), 0.8))
    else:
        worker = int(non_visitor * 0.3)
    resident = non_visitor - worker

    # 카드매출 — 상위 3 업종
    card_m = card_agg_df[
        (card_agg_df["DISTRICT_CODE"] == district_code)
        & (card_agg_df["STANDARD_YEAR_MONTH"] == snapshot_month)
    ]
    top3_categories = _get_top3_categories(card_m.iloc[0]) if not card_m.empty else []
    total_sales = int(card_m["TOTAL_SALES"].sum()) if not card_m.empty else 0

    # 시간대별 — 피크 시간 + 주말 반전 지수
    pt_dc = pop_time_df[
        (pop_time_df["DISTRICT_CODE"] == district_code)
        & (pop_time_df["STANDARD_YEAR_MONTH"] == snapshot_month)
    ]
    peak_hour = _get_peak_hour(
        pt_dc[pt_dc["WEEKDAY_WEEKEND"] == "W"] if not pt_dc.empty else pt_dc
    )
    weekend_reversal = _calc_weekend_reversal(pt_dc)

    # 소득-소비 갭 (소득 백분위 - 소비 백분위 근사)
    if avg_income > 0 and sales_per_capita > 0:
        overall_income = derived_metrics["avg_income"].mean()
        overall_spc = derived_metrics["sales_per_capita"].mean()
        income_pct = avg_income / overall_income if overall_income > 0 else 1.0
        consumption_pct = sales_per_capita / overall_spc if overall_spc > 0 else 1.0
        income_consumption_gap = round(income_pct / consumption_pct, 2) if consumption_pct > 0 else 1.0
    else:
        income_consumption_gap = 1.0

    # 신용점수 (income_agg에서)
    inc_m = income_agg_df[
        (income_agg_df["DISTRICT_CODE"] == district_code)
        & (income_agg_df["STANDARD_YEAR_MONTH"] == snapshot_month)
    ]
    credit_score = int(inc_m["AVERAGE_SCORE"].iloc[0]) if (not inc_m.empty and "AVERAGE_SCORE" in inc_m.columns) else 0

    profile = {
        "district_code": district_code,
        "name": name,
        "snapshot_month": snapshot_month,
        "population": {
            "total": total_pop,
            "resident": resident,
            "worker": worker,
            "visitor": visitor,
        },
        "flow": {
            "day_night_ratio": day_night_ratio,
            "peak_hour": peak_hour,
            "weekend_reversal": weekend_reversal,
        },
        "consumption": {
            "total_sales": total_sales,
            "top3_categories": top3_categories,
            "hhi": round(hhi, 4),
            "sales_per_capita": sales_per_capita,
        },
        "finance": {
            "avg_income": int(avg_income),
            "income_consumption_gap": income_consumption_gap,
            "credit_score": credit_score,
        },
        "tags": [],  # placeholder, filled below
    }
    profile["tags"] = _classify_tags(profile)
    return profile


def generate_profile_text(profile: dict) -> str:
    """
    Layer 3 JSON → GraphRAG 시드 텍스트 변환

    Parameters
    ----------
    profile : dict  generate_profile_json()의 반환값

    Returns
    -------
    str  법정동을 자연어로 설명하는 프로파일 텍스트
    """
    name = profile["name"]
    pop = profile["population"]
    flow = profile["flow"]
    cons = profile["consumption"]
    fin = profile["finance"]
    tags = profile.get("tags", [])

    # 인구 구성 설명
    total = pop["total"]
    resident = pop["resident"]
    worker = pop["worker"]
    visitor = pop["visitor"]

    # 동네 유형 판별
    dn_ratio = flow["day_night_ratio"]
    if dn_ratio > 1.5:
        district_type = "직장인구가 거주인구보다 많은 전형적 오피스 상권"
    elif dn_ratio < 0.8:
        district_type = "야간 인구가 주간보다 많은 주거 중심 지역(베드타운)"
    else:
        district_type = "주거와 상업이 균형을 이루는 복합 지역"

    # 피크 시간대
    peak_kor = TIME_SLOT_KOR.get(flow["peak_hour"], flow["peak_hour"])

    # 소비 구성
    top3 = cons["top3_categories"]
    top3_str = ", ".join(top3) if top3 else "정보 없음"
    hhi = cons["hhi"]
    if hhi < 0.05:
        hhi_desc = "매우 다양한 소비 구조"
    elif hhi < 0.1:
        hhi_desc = "비교적 다양한 소비 구조"
    elif hhi < 0.15:
        hhi_desc = "보통 수준의 소비 집중도"
    else:
        hhi_desc = "특정 업종에 편중된 소비 구조"

    # 주말 반전
    wr = flow["weekend_reversal"]
    if wr > 1.2:
        weekend_desc = f"주말 방문인구가 주중 대비 {wr}배로 여가/관광 수요가 강하다"
    elif wr < 0.8:
        weekend_desc = f"주말 방문인구가 주중의 {wr}배로 전형적 비즈니스 지역이다"
    else:
        weekend_desc = "주중과 주말 방문인구가 비슷한 수준이다"

    # 소득-소비 관계
    gap = fin["income_consumption_gap"]
    if gap > 1.2:
        gap_desc = "소득 대비 지역 내 소비가 적어 소비유출이 발생하는 편이다"
    elif gap < 0.8:
        gap_desc = "소득 대비 지역 내 소비가 활발하여 외부 소비유입이 있는 편이다"
    else:
        gap_desc = "소득과 소비 수준이 균형을 이루고 있다"

    # 태그
    tags_str = ", ".join(tags) if tags else ""

    # 텍스트 조립
    lines = [
        f"{name}은(는) {district_type}이다.",
        f"총 유동인구 {total:,}명 중 거주인구 {resident:,}명, "
        f"직장인구 {worker:,}명, 방문인구 {visitor:,}명으로 구성된다.",
        f"낮밤 인구비는 {dn_ratio}이며, {peak_kor} 시간대에 유동인구가 피크를 찍는다.",
        f"{weekend_desc}.",
        f"주요 소비 업종은 {top3_str}이며, {hhi_desc}(HHI {hhi:.3f})를 보인다.",
        f"1인당 소비액은 {cons['sales_per_capita']:,}원이다.",
    ]

    if fin["avg_income"] > 0:
        lines.append(
            f"평균 소득은 {fin['avg_income']:,}원이며, {gap_desc}."
        )

    if tags_str:
        lines.append(f"핵심 특성: {tags_str}.")

    return " ".join(lines)


def generate_all_profiles(
    derived_metrics: pd.DataFrame,
    card_agg_df: pd.DataFrame,
    pop_time_df: pd.DataFrame,
    income_agg_df: pd.DataFrame,
    centroids_df: pd.DataFrame,
    snapshot_month: int,
) -> list[dict]:
    """
    전체 법정동에 대해 프로파일 JSON 일괄 생성

    Returns
    -------
    list[dict]  각 법정동별 profile JSON 리스트
    """
    profiles = []
    for _, row in centroids_df.iterrows():
        dc = row["district_code"]
        name = row["name"]
        profile = generate_profile_json(
            district_code=dc,
            name=name,
            snapshot_month=snapshot_month,
            derived_metrics=derived_metrics,
            card_agg_df=card_agg_df,
            pop_time_df=pop_time_df,
            income_agg_df=income_agg_df,
        )
        profiles.append(profile)
    return profiles
