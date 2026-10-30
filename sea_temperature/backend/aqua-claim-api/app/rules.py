"""33개 상품의 보험금 산정·자기부담금 규칙 (보장 단위).

모든 값은 상품별 보험약관 PDF 원문에서 확인한 것이다. 근거는 각 Rule.source 에 적었다.
'interpretation' 이 있는 규칙은 약관이 직접 정하지 않고 준용규정 등으로 해석한 부분이다.

용어
- VALUE_LOSS : 보험가액 = 보유수량 × 적용가격, 손해액 = 손해수량 × 적용가격 (수산물)
- FACILITY   : 보험가액 = 재조달가액 - 감가상각, 손해액 = 원상복구비 - 감가상각 (시설물)
- full_cover_ratio : 가입금액 ≥ 보험가액 × 비율이면 손해액 전액, 미만이면 손해액 × 가입금액 / (보험가액 × 비율)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal as D


@dataclass(frozen=True)
class Rule:
    object: str                       # 수산물 | 시설물
    method: str                       # VALUE_LOSS | FACILITY | HARVEST_DAMAGE_RATE | PRODUCTION_COST_ELAPSED | PRODUCTION_COST
    deductible: str                   # PLAN_TABLE | RATE_MIN_AMOUNT | RATE_MIN_PCT | FIXED | DAMAGE_RATE_SUBTRACT
    source: str
    full_cover_ratio: D = D("1.0")
    min_amount: D = D("0")            # RATE_MIN_AMOUNT 최저한도
    fixed_amount: D = D("0")          # FIXED 매 사고당 금액
    budget_plans: bool = False        # 보급형Ⅰ·Ⅱ 존재
    budget_species: frozenset | None = None   # 보급형 대상 품목 제한 (species_id)
    unfarmable: str | None = None     # UNIT_PRICE (굴·홍합) | ELAPSED (김·전복종자)
    interpretation: str | None = None


W50 = D("500000")

# ---------- 공통 규칙 템플릿 ----------

def _type_table(pid: int, src: str, **kw) -> Rule:
    """【별표】 '보험상품 유형' : 표준형Ⅰ(산정보험금×비율, 최저 가입금액 1%/2%, 매 사고당)
    표준형Ⅱ(가입금액×비율, 기간 누적 공제·특약 포함·시설물 제외), 보급형Ⅰ·Ⅱ(가입금액×비율, 매 사고당)."""
    return Rule("수산물", "VALUE_LOSS", "PLAN_TABLE", src, **kw)


def _fac_min50(src: str, **kw) -> Rule:
    return Rule("시설물", "FACILITY", "RATE_MIN_AMOUNT", src, full_cover_ratio=D("0.8"), min_amount=W50, **kw)


def _fac_fix50(src: str, **kw) -> Rule:
    return Rule("시설물", "FACILITY", "FIXED", src, full_cover_ratio=D("0.8"), fixed_amount=W50, **kw)


def _aq_min50(src: str) -> Rule:
    return Rule("수산물", "VALUE_LOSS", "RATE_MIN_AMOUNT", src, min_amount=W50)


def _aq_minpct(src: str) -> Rule:
    return Rule("수산물", "VALUE_LOSS", "RATE_MIN_PCT", src)


# 상품별 주계약(수산물 또는 시설물) 규칙
MAIN: dict[int, Rule] = {}
TYPE_PRODUCTS = {
    1: "넙치", 2: "전복", 3: "해상가두리어류", 6: "굴", 8: "멍게", 9: "미역", 10: "뱀장어", 11: "강도다리",
    12: "홍합", 13: "다시마", 14: "송어", 15: "육상수조식돌돔", 16: "가리비", 17: "톳", 18: "육상수조식전복",
    19: "미더덕", 20: "오만둥이", 21: "터봇", 22: "메기", 23: "향어", 24: "전복종자",
}
for _pid, _nm in TYPE_PRODUCTS.items():
    MAIN[_pid] = _type_table(_pid, f"{_pid:02d} {_nm} 보험약관 제11조(보험금 지급의 계산)·제12조(자기부담금)·별표 '보험상품 유형'")

MAIN[2] = replace(MAIN[2], budget_plans=True)
MAIN[3] = replace(MAIN[3], budget_plans=True, budget_species=frozenset({11, 13, 15}))   # 조피볼락·참돔·감성돔 (별표2 주)
MAIN[13] = replace(MAIN[13], budget_plans=True)
MAIN[6] = replace(MAIN[6], unfarmable="UNIT_PRICE")     # 제10조 ⑦, 제12조 ③ 양식불능보험금은 자기부담금 미차감
MAIN[12] = replace(MAIN[12], unfarmable="UNIT_PRICE")
MAIN[24] = replace(MAIN[24], unfarmable="ELAPSED",
                   interpretation="1차 선별 이전 양식불능보험금(제10조⑤)은 산식상 최저 5% 보장이 있어 자기부담금 미차감으로 해석")

MAIN[4] = _aq_min50("04 김(황백화) 보험약관 제11조·제12조: 산정보험금×자기부담비율, 최저 50만원")
MAIN[5] = _aq_min50("05 김(즉시보상형) 보험약관 제11조·제12조: 산정보험금×자기부담비율, 최저 50만원")
MAIN[7] = Rule("수산물", "HARVEST_DAMAGE_RATE", "DAMAGE_RATE_SUBTRACT",
               "07 김 보험약관 제10조(담보조항) ②양식불능 ④수확감소: 가입금액×(피해율-자기부담비율)", unfarmable="ELAPSED")
MAIN[25] = Rule("수산물", "PRODUCTION_COST_ELAPSED", "RATE_MIN_PCT",
                "25 흰다리새우 보험약관 제10조(보험금 지급의 계산)·제11조(자기부담금, 최저 가입금액 1%/2% 중 선택)")
MAIN[26] = _aq_minpct("26 방어 보험약관 제11조·제12조: 산정보험금×비율, 최저 가입금액 1%/2% 중 선택")
MAIN[27] = _aq_minpct("27 왕우렁이 보험약관 제11조·제12조: 산정보험금×비율, 최저 가입금액 1%/2% 중 선택")
MAIN[28] = _aq_minpct("28 미꾸라지 보험약관 제11조·제12조: 산정보험금×비율, 최저 가입금액 1%/2% 중 선택")
MAIN[29] = _fac_fix50("29 육상수조식 시설물 보험약관 제11조(80%)·제12조(매 사고당 50만원)")
MAIN[30] = _fac_min50("30 해상가두리어류 시설물 보험약관 제11조(80%)·제12조(비율, 최저 50만원)")
MAIN[32] = _fac_min50("32 해조류양식시설물 보험약관 제11조(80%)·제12조(비율, 최저 50만원)")
MAIN[33] = _fac_fix50("33 육상수조식종자 시설물 보험약관 제11조(80%)·제12조(매 사고당 50만원)")
_SRC31 = "31 양식시설물(시설물전용) 보험약관 제11조(80%)·제12조"
MAIN[31] = _fac_min50(_SRC31 + ": 비율, 최저 50만원 (육상시설 제외)")
RULE_31_LAND = _fac_fix50(_SRC31 + " 단서: 제3조 제1호 육상시설은 매 사고당 50만원")

# 수산물 상품 안의 시설물 특약: 매 사고당 50만원 상품 / 비율·최저 50만원 상품
FAC_FIX50_PRODUCTS = {10, 14, 22, 23, 24}
FAC_MIN50_PRODUCTS = {2, 6, 8, 9, 12, 13, 16, 17, 19, 20}


def resolve(product_id: int, coverage_key: str, coverage_name: str, contract_type: str, obj: str,
            species_id: int | None = None) -> Rule | None:
    """보장 하나에 적용할 규칙. 해당 없으면 None."""
    name = coverage_name.replace(" ", "")
    main = MAIN.get(product_id)
    if main is None:
        return None

    if product_id == 31:
        return RULE_31_LAND if coverage_key == "C001" else main

    if contract_type == "주계약":
        return main if main.object == obj or obj is None else None

    # ---- 특약 ----
    if "조수" in name:  # 미역·다시마·톳: 수산물은 보험상품 유형, 시설물은 80%·최저 50만원 (조수 특약 제4·5조)
        if obj == "시설물":
            return _fac_min50(f"{product_id:02d} 조수(潮水)손해담보 특별약관 제4조②·제5조②: 시설물 80%, 최저 50만원")
        return replace(main, source=f"{product_id:02d} 조수(潮水)손해담보 특별약관 제5조①: 별표 '보험상품 유형'")

    if "가이식" in name:  # 해조류 시설물 상품의 가이식 특약 제4·5조
        if obj == "수산물":
            return Rule("수산물", "VALUE_LOSS", "FIXED", "32 가이식 손해담보 특별약관 제4조①1·제5조①1: 수산물 매 사고당 50만원 (책수×적용가격)",
                        fixed_amount=W50)
        return _fac_min50("32 가이식 손해담보 특별약관 제4조①2·제5조①2: 시설물 80%, 최저 50만원")

    if "생산비보장" in name:  # 가리비 생산비보장 특약 제5·6조
        return Rule("수산물", "PRODUCTION_COST", "RATE_MIN_PCT",
                    "16 생산비보장 특별약관 제5조(가입금액×피해율)·제6조(비율, 최저 가입금액 1%/2%)")

    if "시설물" in name:
        if obj != "시설물":
            return None
        if main.object == "시설물":   # 시설물 상품의 화재·유빙 특약 → 주계약 준용
            return replace(main, interpretation="특약에 자기부담금 조항이 없거나 주계약과 동일 → 주계약 준용")
        if product_id in FAC_FIX50_PRODUCTS:
            return _fac_fix50(f"{product_id:02d} {coverage_name} 제4조(80%)·제5조(매 사고당 50만원)")
        if product_id == 2 and "화재" in name:
            return _fac_fix50("02 화재원인 시설물손해담보 특별약관 제4조(80%)·제5조(매 사고당 50만원)")
        if product_id in FAC_MIN50_PRODUCTS:
            return _fac_min50(f"{product_id:02d} {coverage_name} 제4조(80%)·제5조(비율, 최저 50만원)")
        return None

    # 그 밖의 수산물 특약 (고수온·저수온·이상수질·전기적장치·괭생이모자반·유빙·화재 수산물 등)
    if obj not in (None, "수산물") or main.object != "수산물":
        return None
    if "화재" in name:
        return replace(main, interpretation="화재원인 수산물 특약에 자기부담금 조항 없음 → 준용규정('정하지 않은 사항은 주계약')에 따라 주계약 규칙 적용")
    return replace(main, source=main.source + f" / {coverage_name}: 자기부담비율은 주계약과 동일")
