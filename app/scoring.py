"""
핫플 스코어 & 잠재력 스코어 계산 엔진
"""
import numpy as np
import pandas as pd


def normalize_series(s: pd.Series) -> pd.Series:
    """Min-Max 정규화 (0~100)"""
    min_val = s.min()
    max_val = s.max()
    if max_val == min_val:
        return pd.Series(50.0, index=s.index)
    return ((s - min_val) / (max_val - min_val)) * 100


def calc_growth_rate(df, value_col, group_col="DISTRICT_CODE", time_col="STANDARD_YEAR_MONTH", recent_months=6):
    """최근 N개월 vs 이전 N개월 증가율 계산"""
    months = sorted(df[time_col].unique())
    if len(months) < recent_months * 2:
        recent_months = len(months) // 2
    if recent_months == 0:
        return pd.Series(dtype=float)

    recent = months[-recent_months:]
    previous = months[-recent_months * 2:-recent_months]

    recent_avg = df[df[time_col].isin(recent)].groupby(group_col)[value_col].mean()
    prev_avg = df[df[time_col].isin(previous)].groupby(group_col)[value_col].mean()

    growth = ((recent_avg - prev_avg) / prev_avg.replace(0, np.nan)) * 100
    return growth.fillna(0)


def calc_hotplace_score(pop_agg, card_agg, realestate, install_agg,
                        region_master, weights=None):
    """
    핫플 스코어 계산 (5개 선행지표 조합)

    지표:
    1. 방문인구 증가율 (SPH 유동인구)
    2. 카페·식음료 매출 증가율 (SPH 카드매출)
    3. 20~30대 유입 비율 변화 — 여기서는 유동인구 총합 증가율로 대체
    4. 매매가 상승률 (리치고) — 3개 구만
    5. 신규설치 증가율 (아정당) — 시군구 단위

    Returns: DataFrame with district_code, score, 개별 지표
    """
    if weights is None:
        weights = {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15}

    scores = pd.DataFrame()
    scores.index.name = "DISTRICT_CODE"

    # 1. 방문인구 증가율
    visiting_growth = calc_growth_rate(pop_agg, "VISITING_POPULATION")
    scores["visiting_growth"] = visiting_growth

    # 2. 카페+식음료 매출 증가율
    if "COFFEE_SALES" in card_agg.columns and "FOOD_SALES" in card_agg.columns:
        card_agg = card_agg.copy()
        card_agg["CAFE_FOOD_SALES"] = card_agg["COFFEE_SALES"].fillna(0) + card_agg["FOOD_SALES"].fillna(0)
        cafe_growth = calc_growth_rate(card_agg, "CAFE_FOOD_SALES")
    else:
        cafe_growth = calc_growth_rate(card_agg, "TOTAL_SALES")
    scores["cafe_growth"] = cafe_growth

    # 3. 전체 유동인구 증가율 (20~30대 상세는 demo 데이터 필요)
    total_pop = pop_agg.copy()
    total_pop["TOTAL_POP"] = (total_pop["RESIDENTIAL_POPULATION"]
                              + total_pop["WORKING_POPULATION"]
                              + total_pop["VISITING_POPULATION"])
    young_growth = calc_growth_rate(total_pop, "TOTAL_POP")
    scores["young_growth"] = young_growth

    # 4. 매매가 상승률 (리치고 — 읍면동 단위, BJD_CODE 앞 8자리로 매핑)
    if realestate is not None and len(realestate) > 0:
        re_emd = realestate[realestate["REGION_LEVEL"] == "emd"].copy()
        if len(re_emd) > 0 and "BJD_CODE" in re_emd.columns:
            re_emd["DISTRICT_CODE"] = re_emd["BJD_CODE"].astype(str).str[:8]
            price_growth = calc_growth_rate(
                re_emd, "MEME_PRICE_PER_SUPPLY_PYEONG",
                group_col="DISTRICT_CODE", time_col="YYYYMMDD"
            )
            scores["price_growth"] = price_growth

    if "price_growth" not in scores.columns:
        scores["price_growth"] = 0

    # 5. 신규설치 증가율 (아정당 — 시군구 단위, region_master로 매핑)
    if install_agg is not None and len(install_agg) > 0:
        # 시군구 단위 → 해당 시군구의 모든 법정동에 동일 값 적용
        install_growth = calc_growth_rate(
            install_agg, "OPEN_COUNT" if "OPEN_COUNT" in install_agg.columns else "CONTRACT_COUNT",
            group_col="INSTALL_CITY", time_col="YEAR_MONTH"
        )
        # city_kor → district_code 매핑
        city_to_districts = region_master.groupby("city_kor")["district_code"].apply(list).to_dict()
        install_by_district = {}
        for city, growth_val in install_growth.items():
            for dc in city_to_districts.get(city, []):
                install_by_district[dc] = growth_val
        scores["install_growth"] = pd.Series(install_by_district)

    if "install_growth" not in scores.columns:
        scores["install_growth"] = 0

    # 결측값 처리
    scores = scores.fillna(0)

    # 정규화 + 가중합
    scores["visiting_norm"] = normalize_series(scores["visiting_growth"])
    scores["cafe_norm"] = normalize_series(scores["cafe_growth"])
    scores["young_norm"] = normalize_series(scores["young_growth"])
    scores["price_norm"] = normalize_series(scores["price_growth"])
    scores["install_norm"] = normalize_series(scores["install_growth"])

    scores["hotplace_score"] = (
        scores["visiting_norm"] * weights["visiting"]
        + scores["cafe_norm"] * weights["cafe"]
        + scores["young_norm"] * weights["young"]
        + scores["price_norm"] * weights["price"]
        + scores["install_norm"] * weights["install"]
    )

    scores = scores.reset_index()
    scores.rename(columns={"index": "DISTRICT_CODE"}, inplace=True)

    return scores


def calc_purchasing_power(income_agg):
    """구매력 스코어 (소득 + 카드이용 + 자산 기반)"""
    latest = income_agg[income_agg["STANDARD_YEAR_MONTH"] == income_agg["STANDARD_YEAR_MONTH"].max()].copy()

    scores = pd.DataFrame()
    scores["DISTRICT_CODE"] = latest["DISTRICT_CODE"]

    cols_for_score = []
    if "AVERAGE_INCOME" in latest.columns:
        scores["income_norm"] = normalize_series(latest["AVERAGE_INCOME"].values)
        cols_for_score.append("income_norm")
    if "AVERAGE_ASSET_AMOUNT" in latest.columns:
        scores["asset_norm"] = normalize_series(latest["AVERAGE_ASSET_AMOUNT"].values)
        cols_for_score.append("asset_norm")
    if "AVERAGE_SCORE" in latest.columns:
        scores["credit_norm"] = normalize_series(latest["AVERAGE_SCORE"].values)
        cols_for_score.append("credit_norm")

    if cols_for_score:
        scores["purchasing_power"] = scores[cols_for_score].mean(axis=1)
    else:
        scores["purchasing_power"] = 50.0

    return scores.set_index("DISTRICT_CODE")["purchasing_power"]


def calc_derived_metrics(pop_time_df, card_agg_df, pop_agg_df, income_agg_df, year_month):
    """
    디지털 트윈용 파생지표 계산

    Returns: DataFrame indexed by DISTRICT_CODE with columns:
        total_pop, visit_ratio, day_night_ratio, sales_per_capita, consumption_hhi, avg_income
    """
    ym = year_month

    # ── 총 유동인구 + 방문 비중 ──
    pop_m = pop_agg_df[pop_agg_df["STANDARD_YEAR_MONTH"] == ym].copy()
    pop_m["total_pop"] = (pop_m["RESIDENTIAL_POPULATION"]
                          + pop_m["WORKING_POPULATION"]
                          + pop_m["VISITING_POPULATION"])
    pop_m["visit_ratio"] = pop_m["VISITING_POPULATION"] / pop_m["total_pop"].replace(0, np.nan)
    pop_summary = pop_m.set_index("DISTRICT_CODE")[["total_pop", "visit_ratio", "VISITING_POPULATION"]]

    # ── 낮밤 인구비 ──
    pt = pop_time_df[(pop_time_df["STANDARD_YEAR_MONTH"] == ym)
                     & (pop_time_df["WEEKDAY_WEEKEND"] == "W")].copy()
    pt["total"] = pt["RESIDENTIAL_POPULATION"] + pt["WORKING_POPULATION"] + pt["VISITING_POPULATION"]
    day_slots = ["T06", "T09", "T12"]
    night_slots = ["T18", "T21", "T24"]
    day_pop = pt[pt["TIME_SLOT"].isin(day_slots)].groupby("DISTRICT_CODE")["total"].sum()
    night_pop = pt[pt["TIME_SLOT"].isin(night_slots)].groupby("DISTRICT_CODE")["total"].sum()
    day_night = (day_pop / night_pop.replace(0, np.nan)).round(2)
    day_night.name = "day_night_ratio"

    # ── 1인당 매출 ──
    card_m = card_agg_df[card_agg_df["STANDARD_YEAR_MONTH"] == ym].copy()
    card_by_dc = card_m.set_index("DISTRICT_CODE")
    sales_per_cap = (card_by_dc["TOTAL_SALES"] / pop_summary["total_pop"].replace(0, np.nan)).round(0)
    sales_per_cap.name = "sales_per_capita"

    # ── 소비 집중도 (HHI) ──
    sales_cols = [c for c in card_m.columns if c.endswith("_SALES") and c != "TOTAL_SALES"]
    hhi_rows = {}
    for _, row in card_m.iterrows():
        dc = row["DISTRICT_CODE"]
        total = row["TOTAL_SALES"]
        if total and total > 0:
            hhi = sum((row[c] / total) ** 2 for c in sales_cols if pd.notna(row[c]))
            hhi_rows[dc] = round(hhi, 4)
    hhi_series = pd.Series(hhi_rows, name="consumption_hhi")
    hhi_series.index.name = "DISTRICT_CODE"

    # ── 평균 소득 ──
    inc_m = income_agg_df[income_agg_df["STANDARD_YEAR_MONTH"] == ym].copy()
    avg_income = inc_m.set_index("DISTRICT_CODE")["AVERAGE_INCOME"] if "AVERAGE_INCOME" in inc_m.columns else pd.Series(dtype=float)
    avg_income.name = "avg_income"

    # ── 병합 ──
    result = pop_summary[["total_pop", "visit_ratio"]].copy()
    result = result.join(day_night, how="left")
    result = result.join(sales_per_cap, how="left")
    result = result.join(hhi_series, how="left")
    result = result.join(avg_income, how="left")
    result = result.fillna(0)
    return result
