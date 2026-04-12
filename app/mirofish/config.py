"""
MiroFish Lite v2 — 설정 (클러스터 분석가 구조)
"""

# ── Cortex LLM ──
CORTEX_MODEL = "openai-gpt-5.4"

# ── 시뮬레이션 ──
DEFAULT_N_ROUNDS = 3

# ── 프롬프트 ──
SYSTEM_PROMPT_ANALYST = (
    '당신은 서울 상권 분석 전문가입니다. "{cluster_label}" 유형에 속하는 동네들의 '
    "미래를 예측합니다. 각 동네의 유동인구, 매출, 소비 구조 데이터를 분석하여 "
    "다음 달 변화를 예측하세요. 반드시 유효한 JSON만 반환하세요. 뻔한 분석이 아닌 심도 깊은 분석으로 미래를 예측해야해."
)

SYSTEM_PROMPT_REPORT = (
    "당신은 서울 상권 분석 전문가입니다. AI 에이전트 시뮬레이션 결과를 바탕으로 "
    "한국어로 예측 보고서를 작성합니다. 데이터에 근거한 구체적 분석을 제공하세요."
)

# ── 업종 ──
INDUSTRY_KOR = {
    "FOOD_SALES": "식음료", "COFFEE_SALES": "커피",
    "ENTERTAINMENT_SALES": "유흥", "DEPARTMENT_STORE_SALES": "백화점",
    "LARGE_DISCOUNT_STORE_SALES": "대형마트", "SMALL_RETAIL_STORE_SALES": "소매",
    "CLOTHING_ACCESSORIES_SALES": "의류/잡화",
    "SPORTS_CULTURE_LEISURE_SALES": "스포츠/문화/레저",
    "ACCOMMODATION_SALES": "숙박", "TRAVEL_SALES": "여행",
    "BEAUTY_SALES": "뷰티", "HOME_LIFE_SERVICE_SALES": "생활서비스",
    "EDUCATION_ACADEMY_SALES": "교육/학원", "MEDICAL_SALES": "의료",
    "ELECTRONICS_FURNITURE_SALES": "가전/가구", "CAR_SALES": "자동차",
    "CAR_SERVICE_SUPPLIES_SALES": "자동차서비스",
    "GAS_STATION_SALES": "주유", "E_COMMERCE_SALES": "이커머스",
}

TIME_SLOT_KOR = {
    "T06": "아침(6~9)", "T09": "오전(9~12)", "T12": "점심(12~15)",
    "T15": "오후(15~18)", "T18": "저녁(18~21)", "T21": "심야(21~24)",
    "T24": "기타",
}
