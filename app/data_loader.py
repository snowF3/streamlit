"""
데이터 로딩 모듈 — Snowflake 네이티브 버전
Streamlit in Snowflake에서 get_active_session()으로 직접 쿼리
"""
import pandas as pd
import streamlit as st

# ── Snowflake DB/스키마 경로 ──
SPH_DB = "SEOUL_DISTRICTLEVEL_DATA_FLOATING_POPULATION_CONSUMPTION_AND_ASSETS"
SPH_SCHEMA = "GRANDATA"
SPH = f"{SPH_DB}.{SPH_SCHEMA}"

RICHGO_DB = "KOREAN_POPULATION__APARTMENT_MARKET_PRICE_DATA"
RICHGO_SCHEMA = "HACKATHON_2025Q2"
RICHGO = f"{RICHGO_DB}.{RICHGO_SCHEMA}"

AJD_DB = "SOUTH_KOREA_TELECOM_SUBSCRIPTION_ANALYTICS__CONTRACTS_MARKETING_AND_CALL_CENTER_INSIGHTS_BY_REGION"
AJD_SCHEMA = "TELECOM_INSIGHTS"
AJD = f"{AJD_DB}.{AJD_SCHEMA}"


def get_session():
    """Snowflake 세션 획득"""
    try:
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    except Exception:
        import snowflake.connector, os
        return snowflake.connector.connect(
            account=os.environ.get("SNOWFLAKE_ACCOUNT", ""),
            user=os.environ.get("SNOWFLAKE_USER", ""),
            password=os.environ.get("SNOWFLAKE_PASSWORD", ""),
            warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        )


def run_query(sql: str) -> pd.DataFrame:
    """SQL 실행 → DataFrame"""
    session = get_session()
    if hasattr(session, 'sql'):
        return session.sql(sql).to_pandas()
    else:
        cursor = session.cursor()
        cursor.execute(sql)
        df = cursor.fetch_pandas_all()
        cursor.close()
        return df


# ═══════════════════════════════════════════
# SPH 데이터
# ═══════════════════════════════════════════

@st.cache_data(ttl=3600)
def load_region_master():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE,
               PROVINCE_KOR_NAME as province_kor,
               CITY_KOR_NAME as city_kor,
               DISTRICT_KOR_NAME as district_kor,
               REPLACE(REPLACE(REPLACE(PROVINCE_KOR_NAME,'특별시',''),'광역시',''),'특별자치시','') as province_short
        FROM {SPH}.M_SCCO_MST
    """)
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=3600)
def load_geojson():
    """법정동 GeoJSON — GEOGRAPHY 타입을 ST_ASGEOJSON으로 변환"""
    import json
    df = run_query(f"""
        SELECT DISTRICT_CODE, CITY_KOR_NAME, DISTRICT_KOR_NAME,
               ST_ASGEOJSON(DISTRICT_GEOM) as GEOM_JSON
        FROM {SPH}.M_SCCO_MST
        WHERE DISTRICT_GEOM IS NOT NULL
    """)
    features = []
    for _, row in df.iterrows():
        try:
            geom = json.loads(row["GEOM_JSON"])
            if "coordinates" in geom:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "district_code": str(row["DISTRICT_CODE"]),
                        "name": f"{row['CITY_KOR_NAME']} {row['DISTRICT_KOR_NAME']}",
                        "city_kor": row["CITY_KOR_NAME"],
                        "district_kor": row["DISTRICT_KOR_NAME"],
                    },
                    "geometry": geom
                })
        except (json.JSONDecodeError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


@st.cache_data(ttl=3600)
def load_population_agg():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               SUM(RESIDENTIAL_POPULATION) as RESIDENTIAL_POPULATION,
               SUM(WORKING_POPULATION) as WORKING_POPULATION,
               SUM(VISITING_POPULATION) as VISITING_POPULATION
        FROM {SPH}.FLOATING_POPULATION_INFO
        GROUP BY PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH
    """)
    df.columns = [c.upper() for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_population_time():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               WEEKDAY_WEEKEND, TIME_SLOT,
               SUM(RESIDENTIAL_POPULATION) as RESIDENTIAL_POPULATION,
               SUM(WORKING_POPULATION) as WORKING_POPULATION,
               SUM(VISITING_POPULATION) as VISITING_POPULATION
        FROM {SPH}.FLOATING_POPULATION_INFO
        GROUP BY PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
                 WEEKDAY_WEEKEND, TIME_SLOT
    """)
    df.columns = [c.upper() for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_population_demo():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               GENDER, AGE_GROUP,
               SUM(RESIDENTIAL_POPULATION) as RESIDENTIAL_POPULATION,
               SUM(WORKING_POPULATION) as WORKING_POPULATION,
               SUM(VISITING_POPULATION) as VISITING_POPULATION
        FROM {SPH}.FLOATING_POPULATION_INFO
        GROUP BY PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
                 GENDER, AGE_GROUP
    """)
    df.columns = [c.upper() for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_card_sales_agg():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               SUM(TOTAL_SALES) as TOTAL_SALES, SUM(FOOD_SALES) as FOOD_SALES,
               SUM(COFFEE_SALES) as COFFEE_SALES, SUM(ENTERTAINMENT_SALES) as ENTERTAINMENT_SALES,
               SUM(DEPARTMENT_STORE_SALES) as DEPARTMENT_STORE_SALES,
               SUM(LARGE_DISCOUNT_STORE_SALES) as LARGE_DISCOUNT_STORE_SALES,
               SUM(SMALL_RETAIL_STORE_SALES) as SMALL_RETAIL_STORE_SALES,
               SUM(CLOTHING_ACCESSORIES_SALES) as CLOTHING_ACCESSORIES_SALES,
               SUM(SPORTS_CULTURE_LEISURE_SALES) as SPORTS_CULTURE_LEISURE_SALES,
               SUM(ACCOMMODATION_SALES) as ACCOMMODATION_SALES,
               SUM(TRAVEL_SALES) as TRAVEL_SALES, SUM(BEAUTY_SALES) as BEAUTY_SALES,
               SUM(HOME_LIFE_SERVICE_SALES) as HOME_LIFE_SERVICE_SALES,
               SUM(EDUCATION_ACADEMY_SALES) as EDUCATION_ACADEMY_SALES,
               SUM(MEDICAL_SALES) as MEDICAL_SALES,
               SUM(ELECTRONICS_FURNITURE_SALES) as ELECTRONICS_FURNITURE_SALES,
               SUM(CAR_SALES) as CAR_SALES,
               SUM(CAR_SERVICE_SUPPLIES_SALES) as CAR_SERVICE_SUPPLIES_SALES,
               SUM(GAS_STATION_SALES) as GAS_STATION_SALES,
               SUM(E_COMMERCE_SALES) as E_COMMERCE_SALES,
               SUM(TOTAL_COUNT) as TOTAL_COUNT
        FROM {SPH}.CARD_SALES_INFO
        WHERE CARD_TYPE = '1'
        GROUP BY PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH
    """)
    df.columns = [c.upper() for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_card_sales_time():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               WEEKDAY_WEEKEND, TIME_SLOT,
               SUM(TOTAL_SALES) as TOTAL_SALES, SUM(FOOD_SALES) as FOOD_SALES,
               SUM(COFFEE_SALES) as COFFEE_SALES, SUM(ENTERTAINMENT_SALES) as ENTERTAINMENT_SALES
        FROM {SPH}.CARD_SALES_INFO
        WHERE CARD_TYPE = '1'
        GROUP BY PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
                 WEEKDAY_WEEKEND, TIME_SLOT
    """)
    df.columns = [c.upper() for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_income_agg():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               SUM(CUSTOMER_COUNT) as total_customers,
               SUM(CUSTOMER_COUNT * AVERAGE_INCOME) / NULLIF(SUM(CUSTOMER_COUNT),0) as AVERAGE_INCOME,
               SUM(CUSTOMER_COUNT * MEDIAN_INCOME) / NULLIF(SUM(CUSTOMER_COUNT),0) as MEDIAN_INCOME,
               SUM(CUSTOMER_COUNT * AVERAGE_SCORE) / NULLIF(SUM(CUSTOMER_COUNT),0) as AVERAGE_SCORE,
               SUM(CUSTOMER_COUNT * AVERAGE_ASSET_AMOUNT) / NULLIF(SUM(CUSTOMER_COUNT),0) as AVERAGE_ASSET_AMOUNT,
               SUM(CUSTOMER_COUNT * RATE_HIGHEND) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_HIGHEND,
               SUM(CUSTOMER_COUNT * RATE_INCOME_UNDER_20M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_UNDER_20M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_20M_TO_30M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_20M_TO_30M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_30M_TO_40M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_30M_TO_40M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_40M_TO_50M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_40M_TO_50M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_50M_TO_60M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_50M_TO_60M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_60M_TO_70M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_60M_TO_70M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_OVER_70M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_OVER_70M,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_LARGE_COMPANY_EMPLOYEE) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_LARGE_COMPANY_EMPLOYEE,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_GENERAL_EMPLOYEE) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_GENERAL_EMPLOYEE,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_PROFESSIONAL_EMPLOYEE) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_PROFESSIONAL_EMPLOYEE,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_EXECUTIVES) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_EXECUTIVES,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_GENERAL_SELF_EMPLOYED) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_GENERAL_SELF_EMPLOYED,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_PROFESSIONAL_SELF_EMPLOYED) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_PROFESSIONAL_SELF_EMPLOYED,
               SUM(CUSTOMER_COUNT * RATE_MODEL_GROUP_OTHERS) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_MODEL_GROUP_OTHERS
        FROM {SPH}.ASSET_INCOME_INFO
        WHERE INCOME_TYPE = 1
        GROUP BY PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH
    """)
    df.columns = [c.upper() if c.upper() != "TOTAL_CUSTOMERS" else "total_customers" for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        if c in df.columns:
            df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_income_detail():
    df = run_query(f"""
        SELECT PROVINCE_CODE, CITY_CODE, DISTRICT_CODE, STANDARD_YEAR_MONTH,
               GENDER, AGE_GROUP, CUSTOMER_COUNT, AVERAGE_INCOME
        FROM {SPH}.ASSET_INCOME_INFO
        WHERE INCOME_TYPE = 1
    """)
    df.columns = [c.upper() for c in df.columns]
    for c in ["PROVINCE_CODE", "CITY_CODE", "DISTRICT_CODE"]:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_code_master():
    return run_query(f"SELECT * FROM {SPH}.CODE_MASTER")


# ═══════════════════════════════════════════
# 리치고
# ═══════════════════════════════════════════

@st.cache_data(ttl=3600)
def load_realestate():
    df = run_query(f"SELECT * FROM {RICHGO}.REGION_APT_RICHGO_MARKET_PRICE_M_H")
    if "BJD_CODE" in df.columns:
        df["BJD_CODE"] = df["BJD_CODE"].astype(str)
    return df

@st.cache_data(ttl=3600)
def load_richgo_population():
    df = run_query(f"SELECT * FROM {RICHGO}.REGION_MOIS_POPULATION_GENDER_AGE_M_H")
    if "BJD_CODE" in df.columns:
        df["BJD_CODE"] = df["BJD_CODE"].astype(str)
    return df

@st.cache_data(ttl=3600)
def load_richgo_fertility():
    df = run_query(f"SELECT * FROM {RICHGO}.REGION_MOIS_POPULATION_AGE_UNDER5_PER_FEMALE_20TO40_M_H")
    if "BJD_CODE" in df.columns:
        df["BJD_CODE"] = df["BJD_CODE"].astype(str)
    return df


# ═══════════════════════════════════════════
# 아정당
# ═══════════════════════════════════════════

@st.cache_data(ttl=3600)
def load_ajd_new_install():
    return run_query(f"SELECT * FROM {AJD}.V05_REGIONAL_NEW_INSTALL")

@st.cache_data(ttl=3600)
def load_ajd_funnel():
    return run_query(f"SELECT * FROM {AJD}.V03_CONTRACT_FUNNEL_CONVERSION")

@st.cache_data(ttl=3600)
def load_ajd_channel():
    return run_query(f"SELECT * FROM {AJD}.V04_CHANNEL_CONTRACT_PERFORMANCE")

@st.cache_data(ttl=3600)
def load_ajd_rental():
    return run_query(f"SELECT * FROM {AJD}.V06_RENTAL_CATEGORY_TRENDS")

@st.cache_data(ttl=3600)
def load_ajd_ga4():
    return run_query(f"SELECT * FROM {AJD}.V07_GA4_MARKETING_ATTRIBUTION")


# ═══════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════

@st.cache_data(ttl=3600)
def load_hotplace_monthly():
    """월별 핫플 점수 — Snowflake에서 실시간 계산 (parquet 불필요)"""
    return _calc_hotplace_from_data()


def _calc_hotplace_from_data():
    """Snowflake 데이터로 핫플 점수 실시간 계산"""
    import numpy as np
    WEIGHTS = {"visiting": 0.25, "cafe": 0.20, "young": 0.20, "price": 0.20, "install": 0.15}

    try:
        pop_agg = load_population_agg()
        card_agg = load_card_sales_agg()
        rm = load_region_master()
    except Exception:
        return pd.DataFrame()

    name_map = rm.set_index("district_code").apply(
        lambda r: f"{r['city_kor']} {r['district_kor']}", axis=1
    ).to_dict()
    city_map = rm.set_index("district_code")["city_kor"].to_dict()

    months = sorted(pop_agg["STANDARD_YEAR_MONTH"].unique())
    if len(months) < 2:
        return pd.DataFrame()

    # 부동산/설치 변동률 (간단 버전)
    price_chg_map = {}
    install_chg_map = {}
    try:
        re = load_realestate()
        re_emd = re[re["REGION_LEVEL"] == "emd"].copy() if "REGION_LEVEL" in re.columns else pd.DataFrame()
        if not re_emd.empty and "BJD_CODE" in re_emd.columns:
            re_emd["DISTRICT_CODE"] = re_emd["BJD_CODE"].astype(str).str[:8]
            re_ms = sorted(re_emd["YYYYMMDD"].unique())
            if len(re_ms) >= 2:
                rp = re_emd[re_emd["YYYYMMDD"] == re_ms[-2]].groupby("DISTRICT_CODE")["MEME_PRICE_PER_SUPPLY_PYEONG"].mean()
                rc = re_emd[re_emd["YYYYMMDD"] == re_ms[-1]].groupby("DISTRICT_CODE")["MEME_PRICE_PER_SUPPLY_PYEONG"].mean()
                for dc in rc.index:
                    if dc in rp.index and rp[dc] > 0:
                        price_chg_map[dc] = round((rc[dc] - rp[dc]) / rp[dc] * 100, 2)
    except Exception:
        pass
    try:
        inst = load_ajd_new_install()
        ims = sorted(inst["YEAR_MONTH"].unique())
        if len(ims) >= 2:
            ic = inst[inst["YEAR_MONTH"] == ims[-1]].groupby("INSTALL_CITY")["OPEN_COUNT"].sum()
            ip = inst[inst["YEAR_MONTH"] == ims[-2]].groupby("INSTALL_CITY")["OPEN_COUNT"].sum()
            c2d = rm.groupby("city_kor")["district_code"].apply(list).to_dict()
            for cn in ic.index:
                if cn in ip.index and ip[cn] > 0:
                    chg = round((ic[cn] - ip[cn]) / ip[cn] * 100, 2)
                    for dc in c2d.get(cn, []):
                        install_chg_map[dc] = chg
    except Exception:
        pass

    rows = []
    for i in range(1, len(months)):
        prev_m, curr_m = months[i - 1], months[i]
        pc = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == curr_m].copy()
        pp = pop_agg[pop_agg["STANDARD_YEAR_MONTH"] == prev_m].copy()
        pc["total"] = pc["RESIDENTIAL_POPULATION"] + pc["WORKING_POPULATION"] + pc["VISITING_POPULATION"]
        pp["total"] = pp["RESIDENTIAL_POPULATION"] + pp["WORKING_POPULATION"] + pp["VISITING_POPULATION"]
        pop_c = pc.groupby("DISTRICT_CODE").agg({"total": "sum", "RESIDENTIAL_POPULATION": "sum", "WORKING_POPULATION": "sum", "VISITING_POPULATION": "sum"})
        pop_p = pp.groupby("DISTRICT_CODE").agg({"total": "sum", "RESIDENTIAL_POPULATION": "sum", "WORKING_POPULATION": "sum", "VISITING_POPULATION": "sum"})
        cc = card_agg[card_agg["STANDARD_YEAR_MONTH"] == curr_m]
        cp = card_agg[card_agg["STANDARD_YEAR_MONTH"] == prev_m]

        for dc in set(pop_c.index) & set(pop_p.index):
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

            sales_chg = coffee_chg = food_chg = cafe_chg = 0
            total_sales = 0
            if "TOTAL_SALES" in cc.columns:
                sc = cc[cc["DISTRICT_CODE"] == dc]
                sp = cp[cp["DISTRICT_CODE"] == dc]
                if not sc.empty and not sp.empty:
                    sv, pv = sc["TOTAL_SALES"].values[0], sp["TOTAL_SALES"].values[0]
                    total_sales = sv
                    if pv > 0:
                        sales_chg = round((sv - pv) / pv * 100, 2)
                    cc_sum, cp_sum = 0, 0
                    for col in ["COFFEE_SALES", "FOOD_SALES"]:
                        if col in sc.columns:
                            cc_sum += sc[col].values[0]
                            cp_sum += sp[col].values[0]
                            if col == "COFFEE_SALES" and sp[col].values[0] > 0:
                                coffee_chg = round((sc[col].values[0] - sp[col].values[0]) / sp[col].values[0] * 100, 2)
                            if col == "FOOD_SALES" and sp[col].values[0] > 0:
                                food_chg = round((sc[col].values[0] - sp[col].values[0]) / sp[col].values[0] * 100, 2)
                    if cp_sum > 0:
                        cafe_chg = round((cc_sum - cp_sum) / cp_sum * 100, 2)

            price_chg = price_chg_map.get(dc, 0)
            install_chg = install_chg_map.get(dc, 0)
            composite = round(visiting_chg * WEIGHTS["visiting"] + cafe_chg * WEIGHTS["cafe"] + pop_chg * WEIGHTS["young"] + price_chg * WEIGHTS["price"] + install_chg * WEIGHTS["install"], 2)

            rows.append({
                "DISTRICT_CODE": dc, "STANDARD_YEAR_MONTH": curr_m,
                "name": name_map.get(dc, dc), "city": city_map.get(dc, ""),
                "hotplace_score": composite, "current_score": round(100 + composite, 1),
                "direction": "up" if composite >= 0 else "down",
                "visiting_chg": visiting_chg, "cafe_chg": cafe_chg, "pop_chg": pop_chg,
                "price_chg": price_chg, "install_chg": install_chg,
                "sales_chg": sales_chg, "coffee_chg": coffee_chg, "food_chg": food_chg,
                "res_chg": res_chg, "work_chg": work_chg, "visit_ratio": visit_ratio,
                "total_pop": ct, "total_sales": total_sales,
            })
    return pd.DataFrame(rows)


def get_district_list():
    rm = load_region_master()
    rm["label"] = rm["city_kor"] + " " + rm["district_kor"]
    return rm.sort_values(["city_kor", "district_kor"])

def get_latest_year_month(df, col="STANDARD_YEAR_MONTH"):
    return df[col].max()

def filter_by_district(df, district_code, col="DISTRICT_CODE"):
    return df[df[col] == str(district_code)]

def filter_by_year_month(df, year_month, col="STANDARD_YEAR_MONTH"):
    return df[df[col] == year_month]


@st.cache_data(ttl=3600)
def load_district_centroids():
    """GeoJSON에서 법정동 중심점 좌표 추출 (산술 평균)"""
    geojson = load_geojson()
    rows = []
    for feature in geojson["features"]:
        props = feature["properties"]
        geom = feature["geometry"]
        coords = geom.get("coordinates", [])
        all_points = []
        if geom["type"] == "MultiPolygon":
            for polygon in coords:
                if polygon:
                    all_points.extend(polygon[0])
        elif geom["type"] == "Polygon":
            if coords:
                all_points.extend(coords[0])
        if all_points:
            lons = [p[0] for p in all_points]
            lats = [p[1] for p in all_points]
            rows.append({
                "district_code": props["district_code"],
                "name": props["name"],
                "lat": sum(lats) / len(lats),
                "lon": sum(lons) / len(lons),
            })
    return pd.DataFrame(rows)
