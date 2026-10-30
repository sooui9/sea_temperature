# 양식보험 보험금·자기부담금 계산 API

FastAPI + PostgreSQL. 어가·계약 정보는 DB에서, 사고 정보(사고일·재해·피해량)는 대시보드 입력으로 받아
**보장 판정 → 산정 규칙 선택 → 보험가액·손해액(또는 피해율) → 비례보상 → 자기부담금 → 지급 예상 보험금**을 계산한다.
33개 상품 전부 지원하며, 산정 규칙은 각 상품 보험약관 PDF 원문에서 확인한 것이다 (`app/rules.py`, `data/calc_rules.csv`).

## 설치·실행

```bash
pip install -r requirements.txt

# 적용가격 테이블 생성·적재 (insurance 스키마)
psql "$DATABASE_URL" -f sql/001_applied_price.sql
psql "$DATABASE_URL" -c "\copy insurance.insurance_applied_price (notice_month,section,product_id,species_id,variant,region_scheme,region_no,region_label,weight_min_g,size_label,month,price,unit,valid_from,valid_to,note,source) FROM 'data/applied_price_r7_r8.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"
psql "$DATABASE_URL" -c "\copy insurance.insurance_applied_price_formula (section,product_id,variant,applies,formula,base_price,period_end,floor,region_label,valid_from,valid_to,source) FROM 'data/applied_price_formula.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"

DATABASE_URL="postgresql://user:pw@host:5432/db" uvicorn app.main:app --reload   # 문서: /docs
```

## 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/households/{household_id}/insurance` | 계약·보험목적·가입금액·특약·자기부담비율·보험료(분납 2회/4회안) |
| POST | `/claims/estimate` | 사고 시뮬레이션 |
| GET | `/applied-prices?product_id&species_id&region_no&on_date&weight_g` | 적용가격 단건 조회 |

### POST /claims/estimate — 상품 방식별 입력

| 방식 | 상품 | 입력 |
|---|---|---|
| 보험가액·손해액 (수산물) | 1–6, 8–24, 26–28, 32 가이식 | `aquatic`: 가격 단위에 맞춰 `held_count/damaged_count`(마리) · `held_kg/damaged_kg` · `held_units/damaged_units`(수하연·책), 체중 구간 품목은 `avg_weight_g`, 가격 구분이 여럿이면 `price_variant` |
| 시설물 | 29–33, 각 상품 시설물 특약 (`object: "시설물"`) | `facility`: `replacement_cost`, `restoration_cost`, 감가상각 |
| 피해율 수확감소 | 7 김 | `damage`: `damage_rate` 또는 `normal_yield/total_yield/unindemnified` |
| 생산비 | 25 흰다리새우, 16 생산비보장 특약 | `damage`: `damage_rate` 또는 `remaining/estimated_holding(/harvested)`, 새우 수확기 전이면 `growth_days` |
| 양식불능보험금 (`benefit: "양식불능"`) | 6 굴, 12 홍합 / 7 김, 24 전복종자 | `unfarmable`: 굴·홍합은 `disaster_unit_price`, `lines`(+피해율) / 김·전복종자는 `elapsed_days` |

공통 선택값: `object`(수산물/시설물), `coverage_key`(보장이 여럿일 때, 예: 31 시설물전용 C001 육상시설),
`deductible_rate_override`, `min_deductible_rate_override`(0.01/0.02), `prior_paid_in_period`(이전 지급액 → 잔존가입금액),
`prior_calculated_in_period`(표준형Ⅱ 누적 공제), `applied_price_override` + `applied_price_unit`.

응답: `covered`, `rule`(적용 보장·방식·**약관 근거**·해석 여부), `not_covered_reasons`, `applied_price`,
`result`(보험가액·손해액·피해율·산정보험금·자기부담금·지급 예상 보험금·실제부담·계약소멸 여부·`alternative`), `result.steps`, `warnings`.
선택이 필요한 경우 422 응답에 `price_variants` / `formula_variants` / `coverage_options` 를 함께 준다.

## 산정 규칙 요약 (약관 원문 기준)

| 자기부담 방식 | 내용 | 상품·보장 |
|---|---|---|
| PLAN_TABLE (별표 '보험상품 유형') | 표준형Ⅰ: max(산정보험금×비율, 가입금액×1%/2%) 매 사고 / 표준형Ⅱ: 가입금액×비율을 보험기간 누적 공제(특약 포함·시설물 제외) / 보급형Ⅰ·Ⅱ: 가입금액×비율 매 사고, 적용가격 50%·75% | 1–3, 6, 8–24 수산물 (보급형은 2, 3[조피볼락·참돔·감성돔], 13) |
| RATE_MIN_AMOUNT | max(산정보험금×비율, 50만원) | 4, 5 / 30, 32 / 수산물 상품의 시설물 특약(2, 6, 8, 9, 12, 13, 16, 17, 19, 20) / 31 육상시설 외 |
| RATE_MIN_PCT | max(산정보험금×비율, 가입금액×1%/2% 중 선택) | 25, 26, 27, 28, 16 생산비보장 |
| FIXED | 매 사고당 50만원 | 29, 33, 31 육상시설, 2 화재 시설물, 10·14·22·23·24 시설물 특약, 32 가이식 수산물 |
| DAMAGE_RATE_SUBTRACT | 가입금액 × (피해율 − 자기부담비율) | 7 김 |

비례보상 기준: 수산물 보험가액의 100%, 시설물 80% (손해액 × 가입금액 ÷ 보험가액의 80%).

## 검증필요·해석 항목

- **화재원인 수산물 특약**: 대부분 상품에서 자기부담금 조항이 없어 준용규정에 따라 주계약 규칙 적용 (23 향어는 명시).
- **24 전복종자 양식불능보험금**: 최저 5% 보장 산식이라 자기부담금 미차감으로 해석.
- 표준형Ⅰ·RATE_MIN_PCT 최저한도 1%/2%는 증권 기재사항 → `rider_details.min_deductible_rate` 가 없으면 2%로 계산하고 1% 결과를 `alternative` 로 제공.
- `plan_type: "표준형"`은 Ⅰ/Ⅱ 구분이 없어 Ⅰ로 가정.
- **21 터봇**: PDF에는 특약 4개(전기적장치·고수온·이상수질·화재)가 있으나 DB `insurance_coverages` 에 주계약만 있어 특약 재해는 '보장 없음'으로 나온다.
- 미역 공시 적용기간(2026.04.30) 만료, 미꾸라지 10월 가격 '추후 공시', 송어·메기·향어·뱀장어·터봇은 7·8권역 공시 없음 → `applied_price_override`.
- 비수확기 산식의 '종묘가격 최저한도'는 금액 미공시로 미반영(경고). 전복종자 비출하기 산식은 자동 계산하지 않음.
- 비용손해(잔존물 제거비 등), 추정보유수량 방식, 다른 계약과의 분담은 미구현.

## 테스트

```bash
pytest                                        # 메모리 저장소: 제공 샘플 20행 + 상품별 가상 계약 24건
TEST_DATABASE_URL="postgresql://..." pytest   # 같은 테스트를 실제 PostgreSQL 저장소로
```
`tests/test_products.py` 의 기대값은 약관 산식으로 손계산한 값이며 과정을 주석에 적었다.
`test_every_coverage_has_rule` 은 33개 상품의 모든 '보장추가' 보장에 규칙이 있는지 확인한다.

## 도구

- `tools/hwp2json.py`, `tools/normalize.py`: 수협 적용가격 공시 HWP → CSV (매월)
- `tools/export_rules.py`: 규칙 카탈로그 → `data/calc_rules.csv` (검토·DB 적재용)
