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


def calc_monthly_signals(pop_agg, card_agg, region_master,
                         realestate=None, install_agg=None, top_n=3,
                         weights=None):
    """
    월별 핫플 점수 변동 TOP 시그널 생성
    calc_hotplace_score와 동일한 5개 지표를 월별로 적용:
    방문인구(25%) + 카페매출(20%) + 유동인구(20%) + 매매가(20%) + 신규설치(15%)
    """
    if weights is None:
        weights = {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15}

    rm = region_master.copy()
    name_map = rm.set_index("district_code").apply(
        lambda r: f"{r['city_kor']} {r['district_kor']}", axis=1
    ).to_dict()
    city_map = rm.set_index("district_code")["city_kor"].to_dict()

    months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique())
    if len(months) < 2:
        return []

    def fmt(m):
        s = str(m)
        return f"{s[:4]}.{s[4:6]}"

    # ── 부동산 가격 변동률 (전체 기간, dc별) ──
    price_chg_map = {}
    if realestate is not None and len(realestate) > 0:
        re_emd = realestate[realestate["REGION_LEVEL"] == "emd"].copy()
        if len(re_emd) > 0 and "BJD_CODE" in re_emd.columns:
            re_emd["DISTRICT_CODE"] = re_emd["BJD_CODE"].astype(str).str[:8]
            re_months = sorted(re_emd["YYYYMMDD"].unique())
            if len(re_months) >= 2:
                re_prev = re_emd[re_emd["YYYYMMDD"] == re_months[-2]].groupby("DISTRICT_CODE")["MEME_PRICE_PER_SUPPLY_PYEONG"].mean()
                re_curr = re_emd[re_emd["YYYYMMDD"] == re_months[-1]].groupby("DISTRICT_CODE")["MEME_PRICE_PER_SUPPLY_PYEONG"].mean()
                for dc in re_curr.index:
                    if dc in re_prev.index and re_prev[dc] > 0:
                        price_chg_map[dc] = (re_curr[dc] - re_prev[dc]) / re_prev[dc] * 100

    # ── 신규설치 변동률 (시군구→법정동 매핑) ──
    install_chg_map = {}
    if install_agg is not None and len(install_agg) > 0:
        inst_months = sorted(install_agg["YEAR_MONTH"].unique())
        if len(inst_months) >= 2:
            ic = install_agg[install_agg["YEAR_MONTH"] == inst_months[-1]].groupby("INSTALL_CITY")["OPEN_COUNT"].sum()
            ip = install_agg[install_agg["YEAR_MONTH"] == inst_months[-2]].groupby("INSTALL_CITY")["OPEN_COUNT"].sum()
            city_to_dcs = rm.groupby("city_kor")["district_code"].apply(list).to_dict()
            for city_name in ic.index:
                if city_name in ip.index and ip[city_name] > 0:
                    chg = (ic[city_name] - ip[city_name]) / ip[city_name] * 100
                    for dc in city_to_dcs.get(city_name, []):
                        install_chg_map[dc] = chg

    all_signals = []

    for i in range(1, len(months)):
        prev_m, curr_m = months[i - 1], months[i]
        months_ago = len(months) - 1 - i

        # ── 유동인구 ──
        pc = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == curr_m].copy()
        pp = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == prev_m].copy()
        pc["total"] = pc["RESIDENTIAL_POPULATION"] + pc["WORKING_POPULATION"] + pc["VISITING_POPULATION"]
        pp["total"] = pp["RESIDENTIAL_POPULATION"] + pp["WORKING_POPULATION"] + pp["VISITING_POPULATION"]

        pop_c = pc.groupby("DISTRICT_CODE").agg({
            "total": "sum", "RESIDENTIAL_POPULATION": "sum",
            "WORKING_POPULATION": "sum", "VISITING_POPULATION": "sum",
        })
        pop_p = pp.groupby("DISTRICT_CODE").agg({
            "total": "sum", "RESIDENTIAL_POPULATION": "sum",
            "WORKING_POPULATION": "sum", "VISITING_POPULATION": "sum",
        })

        # ── 카드매출 ──
        cc = card_agg[card_agg["STANDARD_YEAR_MONTH"] == curr_m]
        cp_df = card_agg[card_agg["STANDARD_YEAR_MONTH"] == prev_m]
        has_sales = "TOTAL_SALES" in cc.columns
        sales_c = cc.groupby("DISTRICT_CODE")["TOTAL_SALES"].sum() if has_sales else pd.Series(dtype=float)
        sales_p = cp_df.groupby("DISTRICT_CODE")["TOTAL_SALES"].sum() if has_sales else pd.Series(dtype=float)

        common = set(pop_c.index) & set(pop_p.index)
        items = []

        for dc in common:
            pt = pop_p.loc[dc, "total"]
            if pt == 0:
                continue
            ct = pop_c.loc[dc, "total"]

            # 5개 지표 변동률
            vc = pop_c.loc[dc, "VISITING_POPULATION"]
            vp = pop_p.loc[dc, "VISITING_POPULATION"]
            visiting_chg = (vc - vp) / vp * 100 if vp > 0 else 0
            visit_ratio = vc / ct * 100 if ct > 0 else 0

            pop_chg = (ct - pt) / pt * 100  # young (유동인구 총합)

            # 카페+식음료 매출
            cafe_chg = 0
            coffee_chg = 0
            food_chg = 0
            sales_chg = 0
            sv = 0
            if dc in sales_c.index and dc in sales_p.index and sales_p[dc] > 0:
                sales_chg = (sales_c[dc] - sales_p[dc]) / sales_p[dc] * 100
                sv = sales_c[dc]

            cc_row = cc[cc["DISTRICT_CODE"] == dc] if "DISTRICT_CODE" in cc.columns else pd.DataFrame()
            cp_row = cp_df[cp_df["DISTRICT_CODE"] == dc] if "DISTRICT_CODE" in cp_df.columns else pd.DataFrame()
            if not cc_row.empty and not cp_row.empty:
                cafe_sum_c, cafe_sum_p = 0, 0
                for col in ["COFFEE_SALES", "FOOD_SALES"]:
                    if col in cc_row.columns:
                        cafe_sum_c += cc_row[col].values[0]
                        cafe_sum_p += cp_row[col].values[0]
                        if col == "COFFEE_SALES" and cp_row[col].values[0] > 0:
                            coffee_chg = (cc_row[col].values[0] - cp_row[col].values[0]) / cp_row[col].values[0] * 100
                        if col == "FOOD_SALES" and cp_row[col].values[0] > 0:
                            food_chg = (cc_row[col].values[0] - cp_row[col].values[0]) / cp_row[col].values[0] * 100
                if cafe_sum_p > 0:
                    cafe_chg = (cafe_sum_c - cafe_sum_p) / cafe_sum_p * 100

            price_chg = price_chg_map.get(dc, 0)
            install_chg = install_chg_map.get(dc, 0)

            # ── 핫플 점수 (calc_hotplace_score와 동일 가중합) ──
            composite = (
                visiting_chg * weights["visiting"]
                + cafe_chg * weights["cafe"]
                + pop_chg * weights["young"]
                + price_chg * weights["price"]
                + install_chg * weights["install"]
            )

            # ── 거주/직장 세부 ──
            rc = pop_c.loc[dc, "RESIDENTIAL_POPULATION"]
            rp = pop_p.loc[dc, "RESIDENTIAL_POPULATION"]
            res_chg = (rc - rp) / rp * 100 if rp > 0 else 0
            wc = pop_c.loc[dc, "WORKING_POPULATION"]
            wp = pop_p.loc[dc, "WORKING_POPULATION"]
            work_chg = (wc - wp) / wp * 100 if wp > 0 else 0

            # ── 변동 원인 & 키워드 ──
            reasons = []
            keywords = []
            sources = ["SPH 유동인구", "SPH 카드매출"]

            if abs(pop_chg) > 2:
                d = "증가" if pop_chg > 0 else "감소"
                reasons.append(
                    f"총 유동인구가 전월 대비 {abs(pop_chg):.1f}% {d}했어요. "
                    f"({pt:,.0f}명 → {ct:,.0f}명, {abs(ct - pt):,.0f}명 {d})"
                )
                keywords.append(f"유동인구 {d}")

            sub_details = []
            if abs(res_chg) > 3:
                sub_details.append(f"거주인구 {res_chg:+.1f}%")
            if abs(work_chg) > 3:
                sub_details.append(f"직장인구 {work_chg:+.1f}%")
            if abs(visiting_chg) > 3:
                sub_details.append(f"방문인구 {visiting_chg:+.1f}%")
            if sub_details:
                reasons.append(f"세부적으로 {', '.join(sub_details)}의 변동이 있었어요.")

            if abs(sales_chg) > 2:
                d = "증가" if sales_chg > 0 else "감소"
                sv_disp = f"{sv/1e8:,.1f}억원" if sv > 1e8 else f"{sv/1e4:,.0f}만원"
                reasons.append(f"카드매출이 전월 대비 {abs(sales_chg):.1f}% {d}하여 월 {sv_disp} 규모예요.")
                keywords.append(f"소비 {d}")

            cafe_details = []
            if abs(coffee_chg) > 5:
                cafe_details.append(f"커피 매출 {coffee_chg:+.1f}%")
            if abs(food_chg) > 5:
                cafe_details.append(f"식음료 매출 {food_chg:+.1f}%")
            if cafe_details:
                reasons.append(f"특히 {', '.join(cafe_details)}로 상권 {'활성화' if cafe_chg > 0 else '위축'} 신호가 감지돼요.")
                if coffee_chg > 10:
                    keywords.append("카페 트렌드")

            if abs(price_chg) > 2:
                d = "상승" if price_chg > 0 else "하락"
                reasons.append(f"매매 평단가가 {abs(price_chg):.1f}% {d}하며 부동산 시장이 {'상승' if price_chg > 0 else '조정'} 국면이에요.")
                keywords.append(f"매매가 {d}")
                sources.append("리치고 부동산")

            if abs(install_chg) > 10:
                d = "증가" if install_chg > 0 else "감소"
                reasons.append(f"인터넷 신규설치가 {abs(install_chg):.0f}% {d}하며 전입 수요가 {'늘고' if install_chg > 0 else '줄고'} 있어요.")
                keywords.append(f"전입 {d}")
                sources.append("아정당 신규설치")

            if visit_ratio > 40:
                reasons.append(f"방문인구 비중이 {visit_ratio:.0f}%로 외부 유입이 활발한 상권이에요.")
                keywords.append("핫플 시그널")

            if not reasons:
                reasons.append("전반적인 지표가 소폭 변동했어요.")
                keywords.append("안정적")

            items.append({
                "dc": dc,
                "name": name_map.get(dc, dc),
                "city": city_map.get(dc, ""),
                "month": curr_m,
                "month_label": fmt(curr_m),
                "months_ago": months_ago,
                "direction": "up" if composite >= 0 else "down",
                "composite": round(composite, 1),
                # 5개 지표 (핫플 점수 구성)
                "visiting_chg": round(visiting_chg, 1),
                "cafe_chg": round(cafe_chg, 1),
                "pop_chg": round(pop_chg, 1),
                "price_chg": round(price_chg, 1),
                "install_chg": round(install_chg, 1),
                # 추가 정보
                "sales_chg": round(sales_chg, 1),
                "visit_ratio": round(visit_ratio, 1),
                "total_pop": ct,
                "total_sales": sv,
                "reasons": reasons,
                "keywords": keywords,
                "sources": list(dict.fromkeys(sources)),  # 중복 제거
                "weights": weights,
            })

        items.sort(key=lambda x: x["composite"], reverse=True)
        top = items[:top_n]
        bottom = items[-top_n:]
        # 중복 제거 (상위/하위 겹칠 수 있음)
        seen = set()
        selected = []
        for item in top + bottom:
            if item["dc"] not in seen:
                seen.add(item["dc"])
                selected.append(item)
        all_signals.extend(selected)

    all_signals.sort(key=lambda x: (-x["month"], -abs(x["composite"])))
    return all_signals
