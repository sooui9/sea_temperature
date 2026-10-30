from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AquaticInput(BaseModel):
    """수산물 피해 입력 (보험가액·손해액 방식). 적용가격 단위에 맞는 수량을 보낸다.
    - 원/마리: held_count, damaged_count
    - 원/kg: held_kg, damaged_kg (또는 마릿수 + avg_weight_g 로 환산)
    - 원/수하연(굴 양성기간), 원/책(가이식 김): held_units, damaged_units
    """
    avg_weight_g: Decimal | None = Field(None, gt=0, description="평균 체중(g). 체중 구간 가격 품목에 필요")
    held_count: Decimal | None = Field(None, ge=0)
    damaged_count: Decimal | None = Field(None, ge=0)
    held_kg: Decimal | None = Field(None, ge=0)
    damaged_kg: Decimal | None = Field(None, ge=0)
    held_units: Decimal | None = Field(None, ge=0)
    damaged_units: Decimal | None = Field(None, ge=0)
    price_variant: str | None = Field(None, description="가격 구분(식용_수확기, 먹이용, 비수확기 등). 여러 개면 필수")
    applied_price_override: Decimal | None = Field(None, gt=0, description="공시가 없을 때 수동 적용가격")
    applied_price_unit: Literal["KRW_PER_FISH", "KRW_PER_KG", "KRW_PER_LINE", "KRW_PER_BOOK"] | None = None

    @model_validator(mode="after")
    def _check(self):
        pairs = [(self.held_count, self.damaged_count), (self.held_kg, self.damaged_kg), (self.held_units, self.damaged_units)]
        if not any(h is not None and d is not None for h, d in pairs):
            raise ValueError("보유량·피해량을 한 쌍(마리, kg, 단위 중 하나) 보내야 합니다")
        for h, d in pairs:
            if h is not None and d is not None and d > h:
                raise ValueError("피해량이 보유량보다 클 수 없습니다")
        return self


class FacilityInput(BaseModel):
    replacement_cost: Decimal = Field(gt=0, description="재조달가액")
    restoration_cost: Decimal = Field(ge=0, description="원상복구비")
    depreciation_value: Decimal = Field(Decimal(0), ge=0, description="보험가액 산정 감가상각액")
    depreciation_loss: Decimal = Field(Decimal(0), ge=0, description="손해액 산정 감가상각액")


class DamageInput(BaseModel):
    """피해율 방식(김 수확감소, 흰다리새우·가리비 생산비, 양식불능). damage_rate 를 직접 주거나 요소를 준다."""
    damage_rate: Decimal | None = Field(None, ge=0, le=1)
    normal_yield: Decimal | None = Field(None, gt=0, description="평년수확량 (김)")
    total_yield: Decimal | None = Field(None, ge=0, description="총 수확량 (김)")
    unindemnified: Decimal = Field(Decimal(0), ge=0, description="미보상피해량 (김)")
    remaining: Decimal | None = Field(None, ge=0, description="사고 시 잔존량 (새우·가리비)")
    estimated_holding: Decimal | None = Field(None, gt=0, description="추정 보유량 (새우·가리비)")
    harvested: Decimal = Field(Decimal(0), ge=0, description="수확기 중 수확량 (새우)")
    growth_days: int | None = Field(None, ge=0, description="흰다리새우 입식일~사고일 생장일수")
    in_harvest: bool = Field(False, description="흰다리새우 수확기 중 사고 여부")


class UnfarmableInput(BaseModel):
    """양식불능보험금. 김·전복종자는 elapsed_days, 굴·홍합은 단가·줄수·피해율(또는 aquatic 입력으로 산출)."""
    elapsed_days: int | None = Field(None, ge=0, description="김: 보장개시~사고 경과일수 / 전복종자: 5월1일~사고 경과일수")
    disaster_unit_price: Decimal | None = Field(None, gt=0, description="굴·홍합: 해수부 고시 재난지원단가(100m 줄당)")
    lines: Decimal | None = Field(None, gt=0, description="굴·홍합: 가입줄수(100m 기준)")
    days_since_main_hanging: int | None = Field(None, ge=0, description="굴·홍합: 본수하일부터 경과일 (90일 이내만)")


class EstimateRequest(BaseModel):
    insurance_id: int
    mapping_id: int
    accident_date: date
    peril: str = Field(description="재해: 태풍, 해일, 풍랑, 호우, 홍수, 대설, 한파, 가뭄, 적조, 고수온, 저수온, 이상수온, 이상수질, "
                                   "용존산소, 염분, 화재, 조수, 유빙, 괭생이모자반, 황백화 등")
    object: Literal["수산물", "시설물"] | None = Field(None, description="피해 대상. 생략하면 상품 주계약 대상")
    benefit: Literal["손해", "양식불능"] = "손해"
    coverage_key: str | None = Field(None, description="보장이 여러 개 해당될 때 지정 (예: 시설물전용 상품 C001 육상시설)")
    aquatic: AquaticInput | None = None
    facility: FacilityInput | None = None
    damage: DamageInput | None = None
    unfarmable: UnfarmableInput | None = None
    deductible_rate_override: Decimal | None = Field(None, gt=0, lt=1)
    min_deductible_rate_override: Decimal | None = Field(None, description="최저한도율 0.01 또는 0.02")
    prior_calculated_in_period: Decimal = Field(Decimal(0), ge=0,
        description="표준형Ⅱ: 같은 보험기간 이전 사고의 자기부담금 차감 전 산정보험금 합계 (특약 포함·시설물 제외)")
    prior_paid_in_period: Decimal = Field(Decimal(0), ge=0,
        description="같은 보험기간 이전 지급보험금 합계 → 잔존보험가입금액 = 가입금액 - 이 값")
