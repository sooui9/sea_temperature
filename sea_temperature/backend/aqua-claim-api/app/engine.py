"""계산 엔진: DB와 무관한 순수 함수. 금액은 Decimal, 원 단위 절사."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal as D, ROUND_DOWN
from typing import Iterable

from .rules import Rule

PRICE_FACTOR = {"표준형Ⅰ": D("1"), "표준형Ⅱ": D("1"), "보급형Ⅰ": D("0.5"), "보급형Ⅱ": D("0.75")}  # 약관 제10조


def won(x: D) -> D:
    return x.quantize(D("1"), rounding=ROUND_DOWN)


def f(x) -> str:
    """표시용 숫자: 6192.00 → '6,192', 0.20 → '0.2'."""
    x = D(str(x))
    if x == x.to_integral_value():
        return format(int(x), ",")
    return format(x.normalize(), ",")


# ---------- rider_details 정규화 ----------

_PLAN_ALIASES = {
    "표준형Ⅰ": ("Ⅰ형", "I형", "1형", "표준형Ⅰ", "표준형I", "표준형Ⅰ형", "표준형I형", "표준형1형"),
    "표준형Ⅱ": ("Ⅱ형", "II형", "2형", "표준형Ⅱ", "표준형II", "표준형Ⅱ형", "표준형II형", "표준형2형"),
    "보급형Ⅰ": ("보급형Ⅰ", "보급형I", "보급형Ⅰ형", "보급형I형"),
    "보급형Ⅱ": ("보급형Ⅱ", "보급형II", "보급형Ⅱ형", "보급형II형"),
}


def normalize_plan(plan: str | None) -> tuple[str | None, list[str]]:
    if not plan:
        return None, []
    p = plan.replace(" ", "")
    for norm, aliases in _PLAN_ALIASES.items():
        if p in aliases:
            return norm, []
    if p == "표준형":
        return "표준형Ⅰ", ["plan_type '표준형'은 Ⅰ/Ⅱ형 구분이 없어 표준형Ⅰ로 가정함 (증권 확인 필요)"]
    return "표준형Ⅰ", [f"알 수 없는 plan_type '{plan}': 표준형Ⅰ로 가정"]


def parse_rate(value) -> D | None:
    """0.2 / '0.2' / '20%' / '자기부담비율 10%' / 20 → Decimal 비율."""
    if value is None:
        return None
    if isinstance(value, (int, float, D)):
        v = D(str(value))
        return v / 100 if v > 1 else v
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", str(value))
    if m:
        return D(m.group(1)) / 100
    try:
        v = D(str(value).strip())
        return v / 100 if v > 1 else v
    except Exception:
        return None


@dataclass
class RiderInfo:
    riders: list[str]
    plan: str | None
    deductible_rate: D | None
    min_deductible_rate: D | None
    installment: bool
    warnings: list[str] = field(default_factory=list)


def parse_rider_details(rd: dict | None) -> RiderInfo:
    rd = rd or {}
    plan, w = normalize_plan(rd.get("plan_type"))
    return RiderInfo(
        riders=list(rd.get("riders") or []),
        plan=plan,
        deductible_rate=parse_rate(rd.get("deductible_rate", rd.get("deductible"))),
        min_deductible_rate=parse_rate(rd.get("min_deductible_rate")),
        installment=bool(rd.get("installment", False)),
        warnings=w,
    )


# ---------- 보장 판정 ----------

def _peril_in(peril: str, risk_types: Iterable[str]) -> bool:
    p = peril.replace(" ", "")
    for r in risk_types:
        r2 = r.replace(" ", "")
        if r2 == p or r2.startswith(p + "(") or p in r2.split("(")[0].split("/") or p in r2.split("·"):
            return True
    return False


@dataclass
class CoverageMatch:
    covering: list[dict]    # 이 재해를 보장하는 (가입) 보장들
    excluded_by: list[dict]  # 이 재해를 보장제외하는 가입 특약들


def match_coverages(peril: str, coverages: list[dict], riders: list[str]) -> CoverageMatch:
    """주계약 + 가입 특약 중 peril 을 보장추가/보장제외하는 보장."""
    rider_set = {r.replace(" ", "") for r in riders}
    covering, excluded = [], []
    for c in coverages:
        joined = c["contract_type"] == "주계약" or c["name"].replace(" ", "") in rider_set
        if not joined or not _peril_in(peril, c.get("risk_types") or []):
            continue
        if c["effect"] == "보장추가":
            covering.append(c)
        elif c["effect"] == "보장제외":
            excluded.append(c)
    return CoverageMatch(covering, excluded)


# ---------- 결과 ----------

@dataclass
class ClaimResult:
    coverage_amount: D           # 보험가입금액 (증권)
    coverage_remaining: D        # 잔존보험가입금액 (이전 지급액 차감)
    insured_value: D | None      # 보험가액
    loss: D | None               # 손해액
    damage_rate: D | None        # 피해율
    proportional: bool
    calculated: D                # 자기부담금 차감 전 보험금
    deductible: D
    payout: D
    farmer_burden: D | None      # 손해액 - 지급보험금
    contract_ends: bool = False  # 양식불능보험금 지급 시 계약 소멸
    alternative: dict | None = None
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------- 산정 단계 ----------

def base_amount(loss: D, value: D, limit: D, full_ratio: D, steps: list[str]) -> tuple[D, bool]:
    """약관 '보험금 지급의 계산'. limit = 잔존보험가입금액."""
    if value <= 0:
        raise ValueError("보험가액이 0 이하입니다")
    if limit >= value * full_ratio:
        amt = won(min(loss, limit, value))
        steps.append(f"가입금액 {f(limit)} ≥ 보험가액 {f(value)} × {f(full_ratio)} → 손해액 전액 인정(가입금액·보험가액 한도): {f(amt)}")
        return amt, False
    amt = won(min(loss * limit / (value * full_ratio), limit))
    denom = "보험가액" if full_ratio == 1 else f"(보험가액 × {f(full_ratio)})"
    steps.append(f"가입금액 {f(limit)} < 보험가액 {f(value)} × {f(full_ratio)} → 비례보상 손해액 {f(loss)} × 가입금액 / {denom} = {f(amt)}")
    return amt, True


def _min_pct_or_assume(min_rate: D | None, label: str, warnings: list[str]) -> tuple[D, D | None]:
    """최저한도율(가입금액의 1% 또는 2%)이 없으면 2%(보수적)로 계산하고 1% 대안을 함께 낸다."""
    if min_rate is not None:
        return min_rate, None
    warnings.append(f"{label} 최저한도(가입금액의 1% 또는 2%)가 계약정보에 없어 2%로 계산하고 1% 결과를 alternative 로 함께 제공 "
                    "(rider_details.min_deductible_rate 로 지정 가능)")
    return D("0.02"), D("0.01")


def apply_deductible(*, rule: Rule, plan: str | None, calculated: D, coverage: D, rate: D | None,
                     min_rate: D | None, prior_calculated: D, steps: list[str], warnings: list[str]
                     ) -> tuple[D, D, dict | None]:
    """→ (자기부담금, 지급보험금, alternative)."""
    alt = None
    mode = rule.deductible

    def need_rate():
        if rate is None:
            raise ValueError("자기부담비율이 필요합니다 (계약정보에 없으면 deductible_rate_override)")
        return rate

    if mode == "FIXED":
        ded = min(rule.fixed_amount, calculated)
        steps.append(f"자기부담금 = 매 사고당 {f(rule.fixed_amount)} → {f(ded)}")
    elif mode == "RATE_MIN_AMOUNT":
        r = need_rate()
        ded = min(max(won(calculated * r), rule.min_amount), calculated)
        steps.append(f"자기부담금 = max({f(calculated)} × {f(r)}, {f(rule.min_amount)}) → {f(ded)}")
    elif mode == "RATE_MIN_PCT" or (mode == "PLAN_TABLE" and plan in (None, "표준형Ⅰ")):
        r = need_rate()
        if mode == "PLAN_TABLE" and plan is None:
            warnings.append("plan_type 이 없어 표준형Ⅰ로 계산")
        mr, alt_mr = _min_pct_or_assume(min_rate, "표준형Ⅰ" if mode == "PLAN_TABLE" else "", warnings)

        def calc(m):
            return min(max(won(calculated * r), won(coverage * m)), calculated)
        ded = calc(mr)
        steps.append(f"자기부담금 = max({f(calculated)} × {f(r)}, 가입금액 {f(coverage)} × {f(mr)}) → {f(ded)}")
        if alt_mr is not None:
            d2 = calc(alt_mr)
            alt = {"min_deductible_rate": alt_mr, "deductible": d2, "payout": calculated - d2}
    elif mode == "PLAN_TABLE" and plan == "표준형Ⅱ":
        r = need_rate()
        agg = won(coverage * r)
        before = max(prior_calculated - agg, D(0))
        after = max(prior_calculated + calculated - agg, D(0))
        payout = won(after - before)
        ded = calculated - payout
        steps.append(f"표준형Ⅱ: 자기부담금 = 가입금액 × {f(r)} = {f(agg)} (보험기간 누적, 특약 포함·시설물 제외). "
                     f"이전 산정보험금 {f(prior_calculated)} + 이번 {f(calculated)} 중 초과분 {f(payout)} 지급")
        return ded, payout, None
    elif mode == "PLAN_TABLE" and plan in ("보급형Ⅰ", "보급형Ⅱ"):
        r = need_rate()
        ded = min(won(coverage * r), calculated)
        steps.append(f"{plan}: 자기부담금 = 가입금액 {f(coverage)} × {f(r)} (매 사고당) → {f(ded)}")
    else:
        raise ValueError(f"알 수 없는 자기부담 방식 {mode}/{plan}")
    return ded, calculated - ded, alt


def damage_rate_of(*, damage_rate: D | None = None, normal_yield: D | None = None, total_yield: D | None = None,
                   unindemnified: D = D(0), remaining: D | None = None, estimated_holding: D | None = None,
                   harvested: D = D(0), steps: list[str]) -> D:
    if damage_rate is not None:
        steps.append(f"피해율(입력) = {f(damage_rate)}")
        return damage_rate
    if normal_yield is not None and total_yield is not None:
        dr = (normal_yield - total_yield - unindemnified) / normal_yield
        steps.append(f"피해율 = (평년수확량 {f(normal_yield)} - 총수확량 {f(total_yield)} - 미보상 {f(unindemnified)}) ÷ 평년수확량 = {f(round(dr, 4))}")
        return max(min(dr, D(1)), D(0))
    if remaining is not None and estimated_holding:
        dr = 1 - (remaining + harvested) / estimated_holding
        extra = f" + 수확량 {f(harvested)}" if harvested else ""
        steps.append(f"피해율 = 1 - (잔존량 {f(remaining)}{extra}) ÷ 추정보유량 {f(estimated_holding)} = {f(round(dr, 4))}")
        return max(min(dr, D(1)), D(0))
    raise ValueError("피해율 또는 피해율 산출 요소가 필요합니다")


def shrimp_elapsed_ratio(growth_days: int, steps: list[str]) -> D:
    """흰다리새우 제10조③: 0.1562 + (1-0.1562) × min(생장일수/90, 1)."""
    k = D("0.1562")
    r = k + (1 - k) * min(D(growth_days) / D(90), D(1))
    steps.append(f"경과비율 = 0.1562 + 0.8438 × min({growth_days}/90, 1) = {f(round(r, 6))}")
    return r


def unfarmable_elapsed(coverage: D, elapsed_days: int, steps: list[str]) -> D:
    """김 제10조② / 전복종자 제10조⑤: 가입금액 × 20% × (경과일수/90), 최저 가입금액 5%."""
    d = min(elapsed_days, 90)
    amt = won(coverage * D("0.2") * D(d) / D(90))
    floor = won(coverage * D("0.05"))
    out = max(amt, floor)
    steps.append(f"양식불능보험금 = max(가입금액 {f(coverage)} × 20% × {d}/90 = {f(amt)}, 가입금액 × 5% = {f(floor)}) = {f(out)}")
    return out


def unfarmable_unit_price(unit_price: D, lines: D, damage_rate: D, steps: list[str]) -> D:
    """굴·홍합 제10조⑦: 재난지원단가 × 가입줄수(100m) × 피해율(60~100%)."""
    amt = won(unit_price * lines * damage_rate)
    steps.append(f"양식불능보험금 = 재난지원단가 {f(unit_price)} × 가입줄수 {f(lines)} × 피해율 {f(round(damage_rate, 4))} = {f(amt)}")
    return amt
