"""상품별 산정 규칙 테스트. 기대값은 약관 원문 산식으로 손계산 (주석에 과정).
가상 계약은 tests/fixtures/targets_all.json 의 insurance_id 1001~1033 (보장 특약 모두 가입)."""
from decimal import Decimal as D

import pytest


def est(client, iid, peril, date="2026-10-15", **kw):
    r = client.post("/claims/estimate", json=dict(insurance_id=iid, mapping_id=iid, accident_date=date, peril=peril, **kw))
    return r


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def pay(j):
    return D(str(j["result"]["payout"]))


# ---- 1 넙치: 표준형Ⅰ, kg당 ----
def test_01_flatfish(client):
    # 1.0kg 이상 1~11권역 18,142원/kg. 가액 10,000kg=181,420,000 손해 2,000kg=36,284,000, 가입 200M ≥ 가액 → 36,284,000
    # 자기부담 max(×0.2=7,256,800, 200M×2%=4,000,000) → 29,027,200
    j = ok(est(client, 1001, "태풍", aquatic={"avg_weight_g": 1000, "held_kg": 10000, "damaged_kg": 2000}))
    assert D(str(j["result"]["calculated"])) == 36284000 and pay(j) == 29027200
    assert j["rule"]["deductible"] == "PLAN_TABLE"


def test_01_remaining_coverage_after_prior_payout(client):
    # 제9조④ 잔존가입금액 200M-180M=20M < 가액 → 36,284,000×20M/181,420,000=4,000,000, 최저한도는 증권 가입금액 기준 4,000,000 → 0
    j = ok(est(client, 1001, "태풍", aquatic={"avg_weight_g": 1000, "held_kg": 10000, "damaged_kg": 2000},
               prior_paid_in_period=180000000))
    assert D(str(j["result"]["calculated"])) == 4000000 and pay(j) == 0


# ---- 2 전복: 보급형, 시설물 특약 2종 ----
def test_02_budget_plan(client):
    # 보급형Ⅰ: 적용가격 50% → 100g 이상 14,425 × 0.5 = 7,212.5원/kg
    # 가액 5,000kg=36,062,500 손해 1,000kg=7,212,500, 가입 30M < 가액 → 7,212,500×30M/36,062,500=6,000,000
    # 자기부담 = 가입금액×10% = 3,000,000 (매 사고당, 최저한도 없음) → 3,000,000
    j = ok(est(client, 2002, "태풍", aquatic={"avg_weight_g": 100, "held_kg": 5000, "damaged_kg": 1000}))
    assert D(str(j["result"]["calculated"])) == 6000000 and pay(j) == 3000000


def test_02_facility_riders_differ(client):
    fac = {"replacement_cost": 10000000, "restoration_cost": 8000000}
    # 양식시설물손해담보(C005): 9M ≥ 10M×80% → 8,000,000, 자기부담 max(800,000, 50만) → 7,200,000
    j = ok(est(client, 2001, "태풍", object="시설물", facility=fac))
    assert j["rule"]["coverage_key"] == "C005" and pay(j) == 7200000
    # 화재원인 시설물손해담보(C008): 매 사고당 50만원 → 7,500,000
    j = ok(est(client, 2001, "화재", object="시설물", facility=fac))
    assert j["rule"]["coverage_key"] == "C008" and pay(j) == 7500000


# ---- 3 해상가두리: 보급형은 조피볼락·참돔·감성돔만 ----
def test_03_budget_not_for_filefish(client):
    r = est(client, 3003, "태풍", aquatic={"avg_weight_g": 300, "held_count": 1000, "damaged_count": 100})
    assert r.status_code == 422 and "보급형" in r.json()["detail"]


# ---- 4 김(황백화): 비율×산정액, 최저 50만원 ----
def test_04_laver_yellowing(client):
    # 8권역 10~12월 1,481원/kg. 가액 100,000kg=148,100,000 손해 10,000kg=14,810,000 → 자기부담 1,481,000 → 13,329,000
    j = ok(est(client, 1004, "황백화", aquatic={"held_kg": 100000, "damaged_kg": 10000}))
    assert pay(j) == 13329000 and j["rule"]["deductible"] == "RATE_MIN_AMOUNT"


# ---- 5 김(즉시보상형): 7권역 공시 없음 ----
def test_05_no_price_in_region7(client):
    r = est(client, 1005, "태풍", aquatic={"held_kg": 1000, "damaged_kg": 100})
    assert r.status_code == 422 and "공시가 없습니다" in r.json()["detail"]


# ---- 6 굴: 가격 구분 필요, 양식불능보험금 ----
def test_06_oyster_variant_and_unfarmable(client):
    r = est(client, 1006, "태풍", aquatic={"held_kg": 10000, "damaged_kg": 1000})
    assert r.status_code == 422 and len(r.json()["price_variants"]) == 2
    # 상품화기간 8권역 10월 3,951원/kg → 가액 39,510,000 손해 3,951,000 → 자기부담 max(790,200, 50M×2%=1,000,000) → 2,951,000
    j = ok(est(client, 1006, "태풍", aquatic={"held_kg": 10000, "damaged_kg": 1000,
                                             "price_variant": "상품화기간(수하 후 60일 이상)"}))
    assert pay(j) == 2951000
    # 양식불능: 재난지원단가 1,000,000 × 10줄 × 피해율 0.7 = 7,000,000, 자기부담 없음, 계약 소멸
    j = ok(est(client, 1006, "태풍", benefit="양식불능", damage={"damage_rate": 0.7},
               unfarmable={"disaster_unit_price": 1000000, "lines": 10, "days_since_main_hanging": 30}))
    assert pay(j) == 7000000 and j["result"]["deductible"] == 0 and j["result"]["contract_ends"]
    r = est(client, 1006, "태풍", benefit="양식불능", damage={"damage_rate": 0.5},
            unfarmable={"disaster_unit_price": 1000000, "lines": 10})
    assert r.status_code == 422 and "60%" in r.json()["detail"]


# ---- 7 김: 수확감소(피해율 - 자기부담비율), 양식불능 ----
def test_07_laver_harvest_and_unfarmable(client):
    # 피해율 (10,000-6,000-500)/10,000 = 0.35 → 100M × (0.35-0.2) = 15,000,000
    j = ok(est(client, 1007, "태풍", damage={"normal_yield": 10000, "total_yield": 6000, "unindemnified": 500}))
    assert pay(j) == 15000000 and D(str(j["result"]["deductible"])) == 20000000
    # 양식불능: 100M × 20% × 45/90 = 10,000,000 / 10일이면 2,222,222 < 5% → 5,000,000
    assert pay(ok(est(client, 1007, "태풍", benefit="양식불능", unfarmable={"elapsed_days": 45}))) == 10000000
    assert pay(ok(est(client, 1007, "태풍", benefit="양식불능", unfarmable={"elapsed_days": 10}))) == 5000000


# ---- 8 멍게: 비수확기 산식 가격 ----
def test_08_sea_squirt_offseason_formula(client):
    # 10/15 → 12/31 잔여 77일: 3,105 × (1 - 77×10%/30) = 2,308.05 → 2,308
    # 가액 20,000kg=46,160,000 손해 5,000kg=11,540,000 → 자기부담 max(2,308,000, 2,000,000) → 9,232,000
    j = ok(est(client, 1008, "태풍", aquatic={"held_kg": 20000, "damaged_kg": 5000}))
    assert j["applied_price"]["price"] == 2308 and pay(j) == 9232000


# ---- 9 미역: 공시 만료, 조수 특약 시설물 ----
def test_09_seaweed(client):
    r = est(client, 1009, "태풍", aquatic={"held_kg": 1000, "damaged_kg": 100})
    assert r.status_code == 422          # 미역 공시 적용기간 2026.04.30 만료
    # 2026-01-15: 7,8권역 1월 조기산 593원/kg → 가액 59,300,000 손해 11,860,000 → 자기부담 2,372,000 → 9,488,000
    j = ok(est(client, 1009, "태풍", date="2026-01-15", aquatic={"held_kg": 100000, "damaged_kg": 20000}))
    assert pay(j) == 9488000 and any("비수확기" in w for w in j["warnings"])
    # 조수 특약 시설물: 80%, 비율·최저 50만원 → 5M - max(1M, 50만) = 4,000,000
    j = ok(est(client, 1009, "조수", object="시설물", facility={"replacement_cost": 20000000, "restoration_cost": 5000000}))
    assert pay(j) == 4000000 and "조수" in j["rule"]["source"]


# ---- 10 뱀장어: 8권역 공시 없음, 시설물 매 사고당 50만원 ----
def test_10_eel(client):
    assert est(client, 1010, "태풍", aquatic={"avg_weight_g": 200, "held_count": 100, "damaged_count": 10}).status_code == 422
    j = ok(est(client, 1010, "화재", object="시설물", facility={"replacement_cost": 30000000, "restoration_cost": 10000000}))
    assert pay(j) == 9500000 and j["rule"]["deductible"] == "FIXED"


# ---- 13 다시마: 먹이용 자동 선택 경고, 식용 비수확기 산식 ----
def test_13_kelp(client):
    j = ok(est(client, 1013, "태풍", aquatic={"held_kg": 1000, "damaged_kg": 100}))
    assert j["applied_price"]["variant"] == "먹이용" and any("식용_비수확기" in w for w in j["warnings"])
    # 식용 비수확기: 8권역 6월 771 × (1 - 228일×10%/30) = 185.04 → 185
    # 가액 100,000kg=18,500,000 손해 50,000kg=9,250,000 → 자기부담 max(1,850,000, 400,000) → 7,400,000
    j = ok(est(client, 1013, "태풍", aquatic={"held_kg": 100000, "damaged_kg": 50000, "price_variant": "식용_비수확기"}))
    assert j["applied_price"]["price"] == 185 and pay(j) == 7400000


# ---- 14 송어: 내수면(권역 미매핑) → 수동 가격 ----
def test_14_trout_inland(client):
    assert est(client, 1014, "태풍", aquatic={"avg_weight_g": 300, "held_count": 1000, "damaged_count": 100}).status_code == 422
    j = ok(est(client, 1014, "태풍", aquatic={"avg_weight_g": 300, "held_count": 10000, "damaged_count": 1000,
                                             "applied_price_override": 3600, "applied_price_unit": "KRW_PER_FISH"}))
    # 가액 36,000,000 손해 3,600,000 → 자기부담 max(720,000, 1,000,000) → 2,600,000
    assert pay(j) == 2600000


# ---- 16 가리비: 생산비보장 특약 ----
def test_16_scallop_production_cost(client):
    r = est(client, 1016, "태풍", damage={"remaining": 300, "estimated_holding": 1000})
    assert r.status_code == 422 and r.json()["coverage_options"]
    # 피해율 1 - 300/1000 = 0.7 → 50M × 0.7 = 35,000,000, 자기부담 max(7,000,000, 50M×1%) → 28,000,000
    j = ok(est(client, 1016, "태풍", coverage_key="C005", damage={"remaining": 300, "estimated_holding": 1000}))
    assert pay(j) == 28000000


# ---- 19 미더덕: 비수확기 산식 + 종묘가격 최저한도 경고 ----
def test_19_midoduk(client):
    # 10/15 → 1/31 잔여 108일: 12,307 × (1 - 0.36) = 7,876.48 → 7,876
    # 가액 5,000kg=39,380,000 손해 1,000kg=7,876,000 → 자기부담 max(1,575,200, 2,000,000) → 5,876,000
    j = ok(est(client, 1019, "태풍", aquatic={"held_kg": 5000, "damaged_kg": 1000}))
    assert j["applied_price"]["price"] == 7876 and pay(j) == 5876000
    assert any("종묘가격" in w for w in j["warnings"])


# ---- 21 터봇: 12권역만 공시 ----
def test_21_turbot(client):
    assert est(client, 1021, "태풍", aquatic={"avg_weight_g": 1000, "held_kg": 100, "damaged_kg": 10}).status_code == 422


# ---- 24 전복종자: 양식불능(경과일수) ----
def test_24_abalone_seed_unfarmable(client):
    # 20M × 20% × 30/90 = 1,333,333 ≥ 5%(1,000,000)
    assert pay(ok(est(client, 1024, "태풍", benefit="양식불능", unfarmable={"elapsed_days": 30}))) == 1333333


# ---- 25 흰다리새우: 가입금액 × 경과비율 × 피해율, 최저한도 1%/2% 미기재 → 대안 ----
def test_25_shrimp(client):
    # 경과비율 0.1562 + 0.8438×45/90 = 0.5781, 피해율 1-4,000/10,000 = 0.6
    # 99,949,000 × 0.5781 × 0.6 = 34,668,310 → 자기부담 max(6,933,662, 1,998,980) → 27,734,648
    j = ok(est(client, 1025, "태풍", damage={"remaining": 4000, "estimated_holding": 10000, "growth_days": 45}))
    assert D(str(j["result"]["calculated"])) == 34668310 and pay(j) == 27734648
    assert j["result"]["alternative"]["payout"] == 27734648


# ---- 26 방어: 비율, 최저 1%/2% 선택 ----
def test_26_yellowtail(client):
    # 10월 18,259원/kg: 가액 91,295,000 손해 18,259,000 → 자기부담 max(3,651,800, 1,000,000) → 14,607,200
    assert pay(ok(est(client, 1026, "태풍", aquatic={"held_kg": 5000, "damaged_kg": 1000}))) == 14607200


# ---- 28 미꾸라지: 10월 가격 없음(동면기 이후 추후 공시) ----
def test_28_loach_no_price(client):
    assert est(client, 1028, "태풍", aquatic={"held_kg": 100, "damaged_kg": 10}).status_code == 422


# ---- 29·33 육상 시설물: 매 사고당 50만원 ----
@pytest.mark.parametrize("iid", [1029, 1033])
def test_29_33_land_facility(client, iid):
    j = ok(est(client, iid, "태풍", facility={"replacement_cost": 40000000, "restoration_cost": 10000000}))
    assert pay(j) == 9500000


# ---- 31 시설물전용: 시설 종류별 ----
def test_31_facility_types(client):
    fac = {"replacement_cost": 50000000, "restoration_cost": 10000000}
    r = est(client, 1031, "태풍", facility=fac)
    assert r.status_code == 422 and {o["coverage_key"] for o in r.json()["coverage_options"]} >= {"C001", "C003"}
    assert pay(ok(est(client, 1031, "태풍", coverage_key="C001", facility=fac))) == 9500000   # 육상시설 50만원
    assert pay(ok(est(client, 1031, "태풍", coverage_key="C003", facility=fac))) == 9000000   # 수하식 10%


# ---- 32 해조류 시설물: 가이식 수산물(책) / 주계약 시설물 ----
def test_32_seaweed_facility(client):
    # 가이식 김 12,198원/책: 가액 2,000책=24,396,000 손해 500책=6,099,000 → 매 사고당 50만원 → 5,599,000
    j = ok(est(client, 1032, "태풍", object="수산물", aquatic={"held_units": 2000, "damaged_units": 500}))
    assert pay(j) == 5599000 and j["rule"]["coverage_key"] == "C003"
    # 시설물: 6M - max(600,000, 50만) = 5,400,000 (주계약 우선)
    j = ok(est(client, 1032, "태풍", facility={"replacement_cost": 30000000, "restoration_cost": 6000000}))
    assert pay(j) == 5400000 and j["rule"]["coverage_key"] == "C001"


# ---- 규칙 카탈로그: 33개 상품 모든 '보장추가' 보장에 규칙이 있어야 한다 ----
def test_every_coverage_has_rule():
    import json
    from pathlib import Path
    from app.rules import MAIN, resolve
    cov = json.loads((Path(__file__).parent / "fixtures" / "coverages_all.json").read_text(encoding="utf-8"))
    assert set(MAIN) == set(range(1, 34))
    missing = []
    for c in cov:
        if c["effect"] != "보장추가":
            continue
        if not any(resolve(c["product_id"], c["coverage_key"], c["name"], c["contract_type"], o) for o in ("수산물", "시설물")):
            missing.append((c["product_id"], c["coverage_key"], c["name"]))
    assert not missing, missing
