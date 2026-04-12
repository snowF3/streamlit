"""
동네 클러스터링 엔진 — Phase 2 Sprint 1
8차원 피처 K-means + 코사인 유사도 기반 유사 동네 매칭

피처:
  1. day_night_ratio (낮밤인구비)
  2. visit_ratio (방문비중)
  3. consumption_hhi (소비집중도)
  4. sales_per_capita (1인당매출)
  5. avg_income (평균소득)
  6. top_category_ratio (1위 업종 비중)
  7. young_ratio (20~30대 비중)
  8. weekend_reversal (주말반전지수)
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

# 클러스터 라벨 (8개)
CLUSTER_LABELS = {
    0: "직장인 밀집",
    1: "주거 중심",
    2: "핫플 상권",
    3: "관광/유흥",
    4: "교육/주거",
    5: "복합 상업",
    6: "고소득 주거",
    7: "소매/생활",
}

CLUSTER_COLORS = {
    0: [99, 102, 241],    # indigo
    1: [34, 197, 94],     # green
    2: [239, 68, 68],     # red
    3: [245, 158, 11],    # amber
    4: [59, 130, 246],    # blue
    5: [168, 85, 247],    # purple
    6: [236, 72, 153],    # pink
    7: [20, 184, 166],    # teal
}

FEATURE_COLS = [
    "day_night_ratio", "visit_ratio", "consumption_hhi",
    "sales_per_capita", "avg_income", "top_category_ratio",
    "young_ratio", "weekend_reversal",
]


def _calc_top_category_ratio(card_agg_df: pd.DataFrame, year_month) -> pd.Series:
    """1위 업종 매출 비중 계산"""
    card_m = card_agg_df[card_agg_df["STANDARD_YEAR_MONTH"] == year_month].copy()
    sales_cols = [c for c in card_m.columns if c.endswith("_SALES") and c != "TOTAL_SALES"]
    result = {}
    for _, row in card_m.iterrows():
        dc = row["DISTRICT_CODE"]
        total = row["TOTAL_SALES"]
        if total and total > 0:
            max_cat = max(row[c] if pd.notna(row[c]) else 0 for c in sales_cols)
            result[dc] = max_cat / total
        else:
            result[dc] = 0
    s = pd.Series(result, name="top_category_ratio")
    s.index.name = "DISTRICT_CODE"
    return s


def _calc_young_ratio(pop_demo_df: pd.DataFrame, year_month) -> pd.Series:
    """20~30대 비중 계산"""
    demo_m = pop_demo_df[pop_demo_df["STANDARD_YEAR_MONTH"] == year_month].copy()
    demo_m["total"] = (demo_m["RESIDENTIAL_POPULATION"]
                       + demo_m["WORKING_POPULATION"]
                       + demo_m["VISITING_POPULATION"])

    total_by_dc = demo_m.groupby("DISTRICT_CODE")["total"].sum()
    young_ages = [a for a in demo_m["AGE_GROUP"].unique()
                  if str(a).isdigit() and 20 <= int(a) < 40]
    young_by_dc = demo_m[demo_m["AGE_GROUP"].isin(young_ages)].groupby("DISTRICT_CODE")["total"].sum()

    ratio = (young_by_dc / total_by_dc.replace(0, np.nan)).fillna(0)
    ratio.name = "young_ratio"
    return ratio


def _calc_weekend_reversal(pop_time_df: pd.DataFrame, year_month) -> pd.Series:
    """주말 반전 지수: 주말 방문인구 / 주중 방문인구"""
    pt_m = pop_time_df[pop_time_df["STANDARD_YEAR_MONTH"] == year_month].copy()
    weekday_visit = pt_m[pt_m["WEEKDAY_WEEKEND"] == "W"].groupby("DISTRICT_CODE")["VISITING_POPULATION"].sum()
    weekend_visit = pt_m[pt_m["WEEKDAY_WEEKEND"] == "H"].groupby("DISTRICT_CODE")["VISITING_POPULATION"].sum()
    reversal = (weekend_visit / weekday_visit.replace(0, np.nan)).fillna(1.0).round(2)
    reversal.name = "weekend_reversal"
    return reversal


def build_feature_matrix(
    derived_metrics: pd.DataFrame,
    card_agg_df: pd.DataFrame,
    pop_demo_df: pd.DataFrame,
    pop_time_df: pd.DataFrame,
    year_month,
) -> pd.DataFrame:
    """
    8차원 피처 매트릭스 구축

    Parameters
    ----------
    derived_metrics : DataFrame  calc_derived_metrics() 결과 (index=DISTRICT_CODE)
    card_agg_df : DataFrame  load_card_sales_agg()
    pop_demo_df : DataFrame  load_population_demo()
    pop_time_df : DataFrame  load_population_time()
    year_month : int  기준 년월

    Returns
    -------
    DataFrame  index=DISTRICT_CODE, columns=FEATURE_COLS
    """
    features = derived_metrics[["day_night_ratio", "visit_ratio",
                                 "consumption_hhi", "sales_per_capita",
                                 "avg_income"]].copy()

    top_cat = _calc_top_category_ratio(card_agg_df, year_month)
    young = _calc_young_ratio(pop_demo_df, year_month)
    weekend = _calc_weekend_reversal(pop_time_df, year_month)

    features = features.join(top_cat, how="left")
    features = features.join(young, how="left")
    features = features.join(weekend, how="left")
    features = features.fillna(0)

    return features[FEATURE_COLS]


def run_clustering(
    feature_matrix: pd.DataFrame,
    n_clusters: int = 8,
    random_state: int = 42,
) -> tuple[pd.Series, KMeans, StandardScaler]:
    """
    K-means 클러스터링 수행

    Returns
    -------
    (cluster_labels: Series, kmeans_model, scaler)
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(feature_matrix.values)

    # 클러스터 수를 데이터 수에 맞게 조정
    actual_k = min(n_clusters, len(feature_matrix))
    kmeans = KMeans(n_clusters=actual_k, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(X_scaled)

    cluster_series = pd.Series(labels, index=feature_matrix.index, name="cluster")
    return cluster_series, kmeans, scaler


def classify_district_type(
    feature_matrix: pd.DataFrame,
    cluster_labels: pd.Series,
) -> dict[int, str]:
    """
    클러스터 중심 특성 분석 → 사람이 읽을 수 있는 라벨 자동 부여

    Returns
    -------
    dict  {cluster_id: label_string}
    """
    labeled = feature_matrix.copy()
    labeled["cluster"] = cluster_labels

    cluster_means = labeled.groupby("cluster")[FEATURE_COLS].mean()

    # 각 피처를 전체 평균 대비 z-score로 변환
    overall_mean = feature_matrix[FEATURE_COLS].mean()
    overall_std = feature_matrix[FEATURE_COLS].std().replace(0, 1)

    label_map = {}
    for cid in cluster_means.index:
        row = cluster_means.loc[cid]
        z = (row - overall_mean) / overall_std

        # 특성 기반 라벨 결정 (가장 두드러진 특성)
        if z["day_night_ratio"] > 1.0 and z["visit_ratio"] < 0:
            label = "직장인 밀집"
        elif z["visit_ratio"] > 1.0 and z["consumption_hhi"] < 0:
            label = "핫플 상권"
        elif z["visit_ratio"] > 0.8 and z["weekend_reversal"] > 0.5:
            label = "관광/유흥"
        elif z["avg_income"] > 1.0 and z["day_night_ratio"] < 0:
            label = "고소득 주거"
        elif z["young_ratio"] > 0.8:
            label = "MZ 핫스팟"
        elif z["day_night_ratio"] < -0.5 and z["visit_ratio"] < -0.5:
            label = "주거 중심"
        elif z["consumption_hhi"] > 0.8:
            label = "소매/생활"
        elif z["sales_per_capita"] > 0.5:
            label = "복합 상업"
        else:
            # fallback: CLUSTER_LABELS에서 가져오기
            label = CLUSTER_LABELS.get(cid, f"유형 {cid+1}")

        label_map[cid] = label

    return label_map


def find_similar_districts(
    feature_matrix: pd.DataFrame,
    target_district_code: str,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    코사인 유사도 기반 유사 동네 Top N 매칭

    Parameters
    ----------
    feature_matrix : DataFrame  build_feature_matrix() 결과
    target_district_code : str  대상 법정동 코드
    top_n : int  반환할 유사 동네 수

    Returns
    -------
    DataFrame  columns=[district_code, similarity] 유사도 내림차순
    """
    if target_district_code not in feature_matrix.index:
        return pd.DataFrame(columns=["district_code", "similarity"])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(feature_matrix.values)

    target_idx = feature_matrix.index.get_loc(target_district_code)
    target_vec = X_scaled[target_idx].reshape(1, -1)

    sim_scores = cosine_similarity(target_vec, X_scaled)[0]
    sim_series = pd.Series(sim_scores, index=feature_matrix.index, name="similarity")

    # 자기 자신 제외 + 상위 N개
    sim_series = sim_series.drop(target_district_code, errors="ignore")
    top = sim_series.nlargest(top_n)

    result = pd.DataFrame({
        "district_code": top.index,
        "similarity": top.values,
    }).reset_index(drop=True)

    return result


def get_cluster_color(cluster_id: int) -> list:
    """클러스터 ID → RGB 색상"""
    return CLUSTER_COLORS.get(cluster_id, [128, 128, 128])
