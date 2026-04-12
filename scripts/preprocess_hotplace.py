"""
월별 핫플 점수 전처리 — 모든 동네 × 모든 월의 핫플 점수를 미리 계산하여 parquet로 저장
실행: python scripts/preprocess_hotplace.py
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "app"))

import pandas as pd
import numpy as np
from data_loader import (
    load_population_agg, load_card_sales_agg, load_region_master,
    load_realestate, load_ajd_new_install,
)

OUT_DIR = BASE_DIR / "processed_data"

WEIGHTS = {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15}


def main():
    print("데이터 로딩...")
    pop_agg = load_population_agg()
    card_agg = load_card_sales_agg()
    rm = load_region_master()

    try:
        realestate = load_realestate()
    except Exception:
        realestate = None

    try:
        install_agg = load_ajd_new_install()
    except Exception:
        install_agg = None

    name_map = rm.set_index("district_code").apply(
        lambda r: f"{r['city_kor']} {r['district_kor']}", axis=1
    ).to_dict()
    city_map = rm.set_index("district_code")["city_kor"].to_dict()

    months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique())
    print(f"총 {len(months)}개월 데이터: {months[0]} ~ {months[-1]}")

    # ── 부동산 가격 변동률 (마지막 2개 시점) ──
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
                        price_chg_map[dc] = round((re_curr[dc] - re_prev[dc]) / re_prev[dc] * 100, 2)

    # ── 신규설치 변동률 ──
    install_chg_map = {}
    if install_agg is not None and len(install_agg) > 0:
        inst_months = sorted(install_agg["YEAR_MONTH"].unique())
        if len(inst_months) >= 2:
            ic = install_agg[install_agg["YEAR_MONTH"] == inst_months[-1]].groupby("INSTALL_CITY")["OPEN_COUNT"].sum()
            ip = install_agg[install_agg["YEAR_MONTH"] == inst_months[-2]].groupby("INSTALL_CITY")["OPEN_COUNT"].sum()
            city_to_dcs = rm.groupby("city_kor")["district_code"].apply(list).to_dict()
            for city_name in ic.index:
                if city_name in ip.index and ip[city_name] > 0:
                    chg = round((ic[city_name] - ip[city_name]) / ip[city_name] * 100, 2)
                    for dc in city_to_dcs.get(city_name, []):
                        install_chg_map[dc] = chg

    # ── 월별 계산 ──
    all_rows = []

    for i in range(1, len(months)):
        prev_m, curr_m = months[i - 1], months[i]
        print(f"  {curr_m} 처리 중...")

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

        cc = card_agg[card_agg["STANDARD_YEAR_MONTH"] == curr_m]
        cp_df = card_agg[card_agg["STANDARD_YEAR_MONTH"] == prev_m]

        common = set(pop_c.index) & set(pop_p.index)

        for dc in common:
            pt = pop_p.loc[dc, "total"]
            if pt == 0:
                continue
            ct = pop_c.loc[dc, "total"]

            vc = pop_c.loc[dc, "VISITING_POPULATION"]
            vp = pop_p.loc[dc, "VISITING_POPULATION"]
            visiting_chg = round((vc - vp) / vp * 100, 2) if vp > 0 else 0
            pop_chg = round((ct - pt) / pt * 100, 2)
            visit_ratio = round(vc / ct * 100, 2) if ct > 0 else 0

            res_chg = round((pop_c.loc[dc, "RESIDENTIAL_POPULATION"] - pop_p.loc[dc, "RESIDENTIAL_POPULATION"]) / pop_p.loc[dc, "RESIDENTIAL_POPULATION"] * 100, 2) if pop_p.loc[dc, "RESIDENTIAL_POPULATION"] > 0 else 0
            work_chg = round((pop_c.loc[dc, "WORKING_POPULATION"] - pop_p.loc[dc, "WORKING_POPULATION"]) / pop_p.loc[dc, "WORKING_POPULATION"] * 100, 2) if pop_p.loc[dc, "WORKING_POPULATION"] > 0 else 0

            # 카드매출
            sales_chg = 0
            total_sales = 0
            cafe_chg = 0
            coffee_chg = 0
            food_chg = 0

            if "TOTAL_SALES" in cc.columns:
                sc = cc[cc["DISTRICT_CODE"] == dc]
                sp = cp_df[cp_df["DISTRICT_CODE"] == dc]
                if not sc.empty and not sp.empty:
                    sv = sc["TOTAL_SALES"].values[0]
                    pv = sp["TOTAL_SALES"].values[0]
                    total_sales = sv
                    if pv > 0:
                        sales_chg = round((sv - pv) / pv * 100, 2)

                    cafe_c, cafe_p = 0, 0
                    for col in ["COFFEE_SALES", "FOOD_SALES"]:
                        if col in sc.columns:
                            cafe_c += sc[col].values[0]
                            cafe_p += sp[col].values[0]
                            if col == "COFFEE_SALES" and sp[col].values[0] > 0:
                                coffee_chg = round((sc[col].values[0] - sp[col].values[0]) / sp[col].values[0] * 100, 2)
                            if col == "FOOD_SALES" and sp[col].values[0] > 0:
                                food_chg = round((sc[col].values[0] - sp[col].values[0]) / sp[col].values[0] * 100, 2)
                    if cafe_p > 0:
                        cafe_chg = round((cafe_c - cafe_p) / cafe_p * 100, 2)

            price_chg = price_chg_map.get(dc, 0)
            install_chg = install_chg_map.get(dc, 0)

            composite = round(
                visiting_chg * WEIGHTS["visiting"]
                + cafe_chg * WEIGHTS["cafe"]
                + pop_chg * WEIGHTS["young"]
                + price_chg * WEIGHTS["price"]
                + install_chg * WEIGHTS["install"],
                2,
            )

            all_rows.append({
                "DISTRICT_CODE": dc,
                "STANDARD_YEAR_MONTH": curr_m,
                "name": name_map.get(dc, dc),
                "city": city_map.get(dc, ""),
                "hotplace_score": composite,
                "current_score": round(100 + composite, 1),
                "direction": "up" if composite >= 0 else "down",
                # 5개 지표
                "visiting_chg": visiting_chg,
                "cafe_chg": cafe_chg,
                "pop_chg": pop_chg,
                "price_chg": price_chg,
                "install_chg": install_chg,
                # 추가 정보
                "sales_chg": sales_chg,
                "coffee_chg": coffee_chg,
                "food_chg": food_chg,
                "res_chg": res_chg,
                "work_chg": work_chg,
                "visit_ratio": visit_ratio,
                "total_pop": ct,
                "total_sales": total_sales,
            })

    df = pd.DataFrame(all_rows)
    out_path = OUT_DIR / "hotplace_monthly.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\n저장 완료: {out_path}")
    print(f"  {len(df)}행 × {len(df.columns)}열")
    print(f"  동네 수: {df['DISTRICT_CODE'].nunique()}")
    print(f"  월 수: {df['STANDARD_YEAR_MONTH'].nunique()}")
    print(f"\n점수 범위: {df['hotplace_score'].min():.1f} ~ {df['hotplace_score'].max():.1f}")
    print(df.groupby("STANDARD_YEAR_MONTH")["hotplace_score"].agg(["mean", "min", "max"]).to_string())


if __name__ == "__main__":
    main()
