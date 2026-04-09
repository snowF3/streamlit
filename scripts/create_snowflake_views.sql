-- ============================================================
-- 디지털 트윈 Layer 2 — Snowflake 뷰 3종
-- DB: SEOUL_DISTRICTLEVEL_DATA_FLOATING_POPULATION_CONSUMPTION_AND_ASSETS
-- Schema: GRANDATA
-- ============================================================

USE DATABASE SEOUL_DISTRICTLEVEL_DATA_FLOATING_POPULATION_CONSUMPTION_AND_ASSETS;
USE SCHEMA GRANDATA;

-- ────────────────────────────────────────
-- 1. V_DIM_DONG_PROFILE (동네 요약 프로파일)
-- ────────────────────────────────────────
CREATE OR REPLACE VIEW V_DIM_DONG_PROFILE AS
WITH pop AS (
    SELECT DISTRICT_CODE, STANDARD_YEAR_MONTH,
        SUM(RESIDENTIAL_POPULATION) AS res_pop,
        SUM(WORKING_POPULATION)     AS work_pop,
        SUM(VISITING_POPULATION)    AS visit_pop
    FROM FLOATING_POPULATION_INFO
    GROUP BY 1, 2
),
pop_time AS (
    SELECT DISTRICT_CODE, STANDARD_YEAR_MONTH,
        SUM(CASE WHEN TIME_SLOT IN ('T06','T09','T12')
            THEN RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION END) AS day_pop,
        SUM(CASE WHEN TIME_SLOT IN ('T18','T21','T24')
            THEN RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION END) AS night_pop
    FROM FLOATING_POPULATION_INFO
    GROUP BY 1, 2
),
sales AS (
    SELECT DISTRICT_CODE, STANDARD_YEAR_MONTH,
        SUM(TOTAL_SALES)  AS total_sales,
        SUM(TOTAL_COUNT)  AS total_count,
        SUM(COFFEE_SALES) AS coffee_sales,
        SUM(FOOD_SALES)   AS food_sales
    FROM CARD_SALES_INFO
    WHERE CARD_TYPE = '1'
    GROUP BY 1, 2
),
income AS (
    SELECT DISTRICT_CODE, STANDARD_YEAR_MONTH,
        SUM(CUSTOMER_COUNT) AS customers,
        SUM(CUSTOMER_COUNT * AVERAGE_INCOME)       / NULLIF(SUM(CUSTOMER_COUNT), 0) AS avg_income,
        SUM(CUSTOMER_COUNT * AVERAGE_ASSET_AMOUNT) / NULLIF(SUM(CUSTOMER_COUNT), 0) AS avg_asset
    FROM ASSET_INCOME_INFO
    WHERE INCOME_TYPE = 1
    GROUP BY 1, 2
)
SELECT
    m.DISTRICT_CODE,
    m.CITY_KOR_NAME,
    m.DISTRICT_KOR_NAME,
    p.STANDARD_YEAR_MONTH,
    -- 인구
    p.res_pop,
    p.work_pop,
    p.visit_pop,
    p.res_pop + p.work_pop + p.visit_pop                                        AS total_pop,
    pt.day_pop,
    pt.night_pop,
    -- 파생 지표
    ROUND(pt.day_pop / NULLIF(pt.night_pop, 0), 2)                              AS day_night_ratio,
    ROUND(p.visit_pop / NULLIF(p.res_pop + p.work_pop + p.visit_pop, 0), 4)     AS visit_ratio,
    -- 소비
    s.total_sales,
    s.total_count,
    ROUND(s.total_sales / NULLIF(p.res_pop + p.work_pop + p.visit_pop, 0), 0)   AS sales_per_capita,
    -- 소득/자산
    i.avg_income,
    i.avg_asset,
    i.customers
FROM M_SCCO_MST m
LEFT JOIN pop p       ON m.DISTRICT_CODE = p.DISTRICT_CODE
LEFT JOIN pop_time pt ON m.DISTRICT_CODE = pt.DISTRICT_CODE
                     AND p.STANDARD_YEAR_MONTH = pt.STANDARD_YEAR_MONTH
LEFT JOIN sales s     ON m.DISTRICT_CODE = s.DISTRICT_CODE
                     AND p.STANDARD_YEAR_MONTH = s.STANDARD_YEAR_MONTH
LEFT JOIN income i    ON m.DISTRICT_CODE = i.DISTRICT_CODE
                     AND p.STANDARD_YEAR_MONTH = i.STANDARD_YEAR_MONTH;


-- ────────────────────────────────────────
-- 2. V_FACT_HOURLY_FLOW (시간대별 유동인구 흐름)
-- ────────────────────────────────────────
CREATE OR REPLACE VIEW V_FACT_HOURLY_FLOW AS
SELECT
    DISTRICT_CODE,
    STANDARD_YEAR_MONTH,
    WEEKDAY_WEEKEND,
    TIME_SLOT,
    SUM(RESIDENTIAL_POPULATION)                                                  AS res_pop,
    SUM(WORKING_POPULATION)                                                      AS work_pop,
    SUM(VISITING_POPULATION)                                                     AS visit_pop,
    SUM(RESIDENTIAL_POPULATION + WORKING_POPULATION + VISITING_POPULATION)       AS total_pop
FROM FLOATING_POPULATION_INFO
GROUP BY 1, 2, 3, 4;


-- ────────────────────────────────────────
-- 3. V_FACT_CONSUMPTION_MATRIX (소비 DNA + HHI)
-- ────────────────────────────────────────
CREATE OR REPLACE VIEW V_FACT_CONSUMPTION_MATRIX AS
SELECT
    DISTRICT_CODE,
    STANDARD_YEAR_MONTH,
    SUM(TOTAL_SALES)                       AS total_sales,
    SUM(FOOD_SALES)                        AS food_sales,
    SUM(COFFEE_SALES)                      AS coffee_sales,
    SUM(ENTERTAINMENT_SALES)               AS entertainment_sales,
    SUM(DEPARTMENT_STORE_SALES)            AS department_store_sales,
    SUM(LARGE_DISCOUNT_STORE_SALES)        AS large_discount_store_sales,
    SUM(SMALL_RETAIL_STORE_SALES)          AS small_retail_store_sales,
    SUM(CLOTHING_ACCESSORIES_SALES)        AS clothing_accessories_sales,
    SUM(SPORTS_CULTURE_LEISURE_SALES)      AS sports_culture_leisure_sales,
    SUM(ACCOMMODATION_SALES)               AS accommodation_sales,
    SUM(TRAVEL_SALES)                      AS travel_sales,
    SUM(BEAUTY_SALES)                      AS beauty_sales,
    SUM(HOME_LIFE_SERVICE_SALES)           AS home_life_service_sales,
    SUM(EDUCATION_ACADEMY_SALES)           AS education_academy_sales,
    SUM(MEDICAL_SALES)                     AS medical_sales,
    SUM(ELECTRONICS_FURNITURE_SALES)       AS electronics_furniture_sales,
    SUM(CAR_SALES)                         AS car_sales,
    SUM(CAR_SERVICE_SUPPLIES_SALES)        AS car_service_supplies_sales,
    SUM(GAS_STATION_SALES)                 AS gas_station_sales,
    SUM(E_COMMERCE_SALES)                  AS e_commerce_sales,
    -- HHI (소비 집중도): 각 업종 비율^2의 합
    POWER(SUM(FOOD_SALES)                    / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(COFFEE_SALES)                / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(ENTERTAINMENT_SALES)         / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(DEPARTMENT_STORE_SALES)      / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(LARGE_DISCOUNT_STORE_SALES)  / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(SMALL_RETAIL_STORE_SALES)    / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(CLOTHING_ACCESSORIES_SALES)  / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(SPORTS_CULTURE_LEISURE_SALES)/ NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(ACCOMMODATION_SALES)         / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(TRAVEL_SALES)                / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(BEAUTY_SALES)                / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(HOME_LIFE_SERVICE_SALES)     / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(EDUCATION_ACADEMY_SALES)     / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(MEDICAL_SALES)               / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(ELECTRONICS_FURNITURE_SALES) / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(CAR_SALES)                   / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(CAR_SERVICE_SUPPLIES_SALES)  / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(GAS_STATION_SALES)           / NULLIF(SUM(TOTAL_SALES), 0), 2)
    + POWER(SUM(E_COMMERCE_SALES)            / NULLIF(SUM(TOTAL_SALES), 0), 2)
        AS consumption_hhi
FROM CARD_SALES_INFO
WHERE CARD_TYPE = '1'
GROUP BY 1, 2;
