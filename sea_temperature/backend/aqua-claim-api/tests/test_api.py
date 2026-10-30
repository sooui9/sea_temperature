"""기대값은 약관 산식으로 손계산한 값 (주석 참고)."""
from decimal import Decimal as D

from app.regions import sea_region_of, normalize_sigungu
from app.engine import parse_rate, normalize_plan


def post(client, **body):
    return client.post("/claims/estimate", json=body)


# ---------- 단위 ----------

def test_region_mapping():
    assert sea_region_of("거제시") == 8 and sea_region_of("창원시") == 8 and sea_region_of("부산광역시") == 8
    assert sea_region_of("통영시") == 7 and sea_region_of("고성군") == 7 and sea_region_of("남해군") == 7
    assert sea_region_of("완도군") is None
    assert normalize_sigungu("부산광역시 기장군") == "부산"


def test_rate_and_plan_parsing():
    assert parse_rate(0.2) == D("0.2") and parse_rate("자기부담비율 10%") == D("0.1") and parse_rate(30) == D("0.3")
    assert normalize_plan("Ⅱ형")[0] == "표준형Ⅱ"
    plan, w = normalize_plan("표준형")
    assert plan == "표준형Ⅰ" and w


# ---------- 수산물 (product 3) ----------

def test_type1_proportional(client):
    # 계약6 / 조피볼락 / 거제(8권역) / 가입 418,000,000 / 표준형(→Ⅰ 가정) 20%
    # 400g 이상 7~11권역 6,192원/마리. 보험가액 80,000×6,192=495,360,000, 손해액 20,000×6,192=123,840,000
    # 비례보상 123,840,000×418/495.36 = 104,500,000, 자기부담 max(20,900,000, 8,360,000) → 지급 83,600,000
    r = post(client, insurance_id=6, mapping_id=10, accident_date="2026-10-15", peril="태풍",
             aquatic={"avg_weight_g": 400, "held_count": 80000, "damaged_count": 20000})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["covered"] and j["applied_price"]["price"] == 6192
    res = j["result"]
    assert D(res["insured_value"]) == 495360000 and D(res["loss"]) == 123840000
    assert res["proportional"] and D(res["calculated"]) == 104500000
    assert D(res["deductible"]) == 20900000 and D(res["payout"]) == 83600000
    assert D(res["farmer_burden"]) == 40240000
    assert any("표준형Ⅰ로 가정" in w for w in j["warnings"])


def test_type1_minimum_deductible(client):
    # 손해가 작으면 최저한도(가입금액 2% = 8,360,000)가 적용
    # 손해 1,000마리×6,192=6,192,000 → 비례 6,192,000×418/495.36=5,225,000 → 자기부담 min(8,360,000, 산정액)=5,225,000 → 0원
    r = post(client, insurance_id=6, mapping_id=10, accident_date="2026-10-15", peril="태풍",
             aquatic={"avg_weight_g": 400, "held_count": 80000, "damaged_count": 1000})
    res = r.json()["result"]
    assert D(res["calculated"]) == 5225000 and D(res["payout"]) == 0


def test_type2_aggregate(client):
    # 계약9 / 말쥐치 / 창원(8권역) / 가입 137,000,000 / Ⅱ형 30%
    # 쥐치 300g 이상 4,864. 보험가액 30,000×4,864=145,920,000, 손해 10,000×4,864=48,640,000
    # 비례 48,640,000×137/145.92=45,666,666 (절사). 연간 자기부담 41,100,000 → 첫 사고 4,566,666
    body = dict(insurance_id=9, mapping_id=14, accident_date="2026-10-10", peril="태풍",
                aquatic={"avg_weight_g": 320, "held_count": 30000, "damaged_count": 10000})
    res = post(client, **body).json()["result"]
    assert D(res["calculated"]) == 45666666 and D(res["payout"]) == 4566666
    res2 = post(client, **body, prior_calculated_in_period=50000000).json()["result"]
    assert D(res2["payout"]) == 45666666 and D(res2["deductible"]) == 0


def test_red_tide_excluded_by_rider(client):
    # 계약3 은 '적조원인 수산물손해부담보 특별약관' 가입 → 주계약의 적조 보장 제외
    r = post(client, insurance_id=3, mapping_id=3, accident_date="2026-10-01", peril="적조",
             aquatic={"avg_weight_g": 300, "held_count": 1000, "damaged_count": 100}).json()
    assert r["covered"] is False and "부담보" in " ".join(r["not_covered_reasons"])


def test_high_temp_needs_rider(client):
    no = post(client, insurance_id=6, mapping_id=10, accident_date="2026-10-15", peril="고수온",
              aquatic={"avg_weight_g": 400, "held_count": 1000, "damaged_count": 100}).json()
    assert no["covered"] is False
    yes = post(client, insurance_id=1, mapping_id=1, accident_date="2026-10-15", peril="고수온",
               aquatic={"avg_weight_g": 400, "held_count": 1000, "damaged_count": 100}).json()
    assert yes["covered"] is True and yes["rule"]["coverage_key"] == "C002"


def test_expired_contract(client):
    r = post(client, insurance_id=4, mapping_id=9, accident_date="2026-10-15", peril="태풍",
             aquatic={"avg_weight_g": 400, "held_count": 1000, "damaged_count": 100}).json()
    assert r["covered"] is False and any("만료" in x for x in r["not_covered_reasons"])


def test_no_price_outside_notice(client):
    r = post(client, insurance_id=6, mapping_id=10, accident_date="2026-11-02", peril="태풍",
             aquatic={"avg_weight_g": 400, "held_count": 1000, "damaged_count": 100})
    assert r.status_code == 422 and "공시가 없습니다" in r.json()["detail"]
    r2 = post(client, insurance_id=6, mapping_id=10, accident_date="2026-11-02", peril="태풍",
              aquatic={"avg_weight_g": 400, "held_count": 1000, "damaged_count": 100, "applied_price_override": 6000})
    assert r2.status_code == 200


def test_below_min_weight(client):
    r = post(client, insurance_id=6, mapping_id=10, accident_date="2026-10-15", peril="태풍",
             aquatic={"avg_weight_g": 10, "held_count": 1000, "damaged_count": 100})
    assert r.status_code == 422 and "최소 구간" in r.json()["detail"]


def test_validation_damaged_gt_held(client):
    r = post(client, insurance_id=6, mapping_id=10, accident_date="2026-10-15", peril="태풍",
             aquatic={"avg_weight_g": 400, "held_count": 100, "damaged_count": 1000})
    assert r.status_code == 422


# ---------- 시설물 (product 30) ----------

def test_facility_fire(client):
    # 계약2 / 가입 69,000,000 / '자기부담비율 10%' / 화재 특약 가입
    # 보험가액 80,000,000 → 69M ≥ 64M(80%) → 손해액 전액 20,000,000, 자기부담 2,000,000 → 18,000,000
    r = post(client, insurance_id=2, mapping_id=1, accident_date="2026-10-15", peril="화재",
             facility={"replacement_cost": 80000000, "restoration_cost": 20000000}).json()
    assert r["covered"] and D(r["result"]["payout"]) == 18000000 and not r["result"]["proportional"]
    # 소손해: 3,000,000 → 최저 50만원 적용 → 2,500,000
    r = post(client, insurance_id=2, mapping_id=1, accident_date="2026-10-15", peril="화재",
             facility={"replacement_cost": 80000000, "restoration_cost": 3000000}).json()
    assert D(r["result"]["deductible"]) == 500000 and D(r["result"]["payout"]) == 2500000


def test_facility_underinsured(client):
    # 30 약관 제11조 2호: 손해액 × 가입금액 ÷ (보험가액의 80% 해당액)
    # 보험가액 100,000,000 → 69M < 80M → 20,000,000 × 69M/80M = 17,250,000, 자기부담 max(1,725,000, 50만) → 15,525,000
    r = post(client, insurance_id=2, mapping_id=1, accident_date="2026-10-15", peril="태풍",
             facility={"replacement_cost": 100000000, "restoration_cost": 20000000}).json()
    assert r["result"]["proportional"] and D(r["result"]["calculated"]) == 17250000 and D(r["result"]["payout"]) == 15525000


# ---------- 어가 조회 ----------

def test_household_overview(client):
    j = client.get("/households/1/insurance").json()
    assert j["sea_region"] == 8 and len(j["contracts"]) == 2
    c1 = next(c for c in j["contracts"] if c["insurance_id"] == 1)
    two = next(p for p in c1["premium"]["plans"] if p["times"] == 2)
    assert [D(s["amount"]) for s in two["schedule"]] == [D("21910500"), D("7303500")]
    assert two["schedule"][1]["due_by"] == "2026-03-01"


