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

AJD_DB = "SOUTH_KOREA_TELECOM_SUBSCRIPTION_ANALYTICS"
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
    import json
    df = run_query(f"""
        SELECT DISTRICT_CODE, CITY_KOR_NAME, DISTRICT_KOR_NAME, DISTRICT_GEOM
        FROM {SPH}.M_SCCO_MST
        WHERE DISTRICT_GEOM IS NOT NULL AND DISTRICT_GEOM != ''
    """)
    features = []
    for _, row in df.iterrows():
        try:
            geom_str = str(row["DISTRICT_GEOM"]).replace('""', '"').strip('"')
            geom = json.loads(geom_str)
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
               SUM(CUSTOMER_COUNT * RATE_INCOME_20M_30M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_20M_30M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_30M_40M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_30M_40M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_40M_50M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_40M_50M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_50M_60M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_50M_60M,
               SUM(CUSTOMER_COUNT * RATE_INCOME_60M_70M) / NULLIF(SUM(CUSTOMER_COUNT),0) as RATE_INCOME_60M_70M,
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
