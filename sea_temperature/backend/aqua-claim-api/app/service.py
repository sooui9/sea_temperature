"""DB 조회값 + 대시보드 입력 → 규칙 선택 → 계산 엔진."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal as D

from . import engine
from .engine import f, won
from .regions import sea_region_of
from .repository import Repository
from .rules import MAIN, Rule, resolve
from .schemas import EstimateRequest

INSTALLMENT_MIN_PREMIUM = D("1000000")   # 계약자부담보험료 100만원 이상 분납 가능 (각 상품 분납 특약)
INSTALLMENT_PLANS = {2: [D("0.75"), D("0.25")], 4: [D("0.40"), D("0.40"), D("0.10"), D("0.10")]}
INSTALLMENT_DUE_MONTHS = {2: [0, 2], 4: [0, 2, 4, 6]}


class ServiceError(Exception):
    def __init__(self, status: int, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra or {}


# ---------- 보험료 ----------

def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError


def premium_info(total_premium, start: date, installment: bool) -> dict:
    if total_premium is None:
        return {"total_premium": None, "installment": installment, "plans": []}
    tp = D(str(total_premium))
    info = {"total_premium": tp, "installment": installment, "plans": [],
            "note": "total_premium 이 계약자부담분인지 국비·지방비 포함 총액인지 확인 필요"}
    if installment:
        if tp < INSTALLMENT_MIN_PREMIUM:
            info["note"] += "; 분납 표시가 있으나 100만원 미만"
        for n, ratios in INSTALLMENT_PLANS.items():
            amts = [won(tp * r) for r in ratios]
            amts[0] += tp - sum(amts)
            info["plans"].append({"times": n, "schedule": [
                {"no": i + 1, "due_by": _add_months(start, mo), "ratio": r, "amount": a}
                for i, (mo, r, a) in enumerate(zip(INSTALLMENT_DUE_MONTHS[n], ratios, amts))]})
        info["note"] += "; 2회/4회 중 어느 쪽인지는 계약정보에 없어 두 안을 모두 표시"
    return info


def household_overview(repo: Repository, household_id: int) -> dict:
    rows = repo.list_household_targets(household_id)
    if not rows:
        raise ServiceError(404, "가입 계약이 없는 어가입니다")
    contracts: dict[int, dict] = {}
    for r in rows:
        ri = engine.parse_rider_details(r["rider_details"])
        c = contracts.setdefault(r["insurance_id"], {
            "insurance_id": r["insurance_id"], "policy_number": r.get("policy_number"),
            "product_id": r["product_id"], "product_name": r.get("product_name"),
            "start_date": r["start_date"], "end_date": r["end_date"], "status": r["contract_status"],
            "calc_supported": r["product_id"] in MAIN, "premium": None, "targets": []})
        c["targets"].append({
            "mapping_id": r["mapping_id"], "species_id": r["species_id"], "species": r["standard_name"],
            "coverage_amount": r["coverage_amount"], "production_ratio": r.get("production_ratio"),
            "plan": ri.plan, "deductible_rate": ri.deductible_rate, "min_deductible_rate": ri.min_deductible_rate,
            "riders": ri.riders, "installment": ri.installment, "warnings": ri.warnings})
        c["premium"] = premium_info(r["total_premium"], r["start_date"], any(t["installment"] for t in c["targets"]))
    first = rows[0]
    return {"household_id": household_id, "household_name": first.get("household_name"),
            "sigungu": first.get("sigungu_name"), "area": first.get("area_name"),
            "sea_region": sea_region_of(first.get("sigungu_name")), "contracts": list(contracts.values())}


# ---------- 적용가격 ----------

def _region_matches(label: str | None, region: int) -> bool:
    if not label or "모든" in label or "권역별" in label:
        return True
    import re
    nums = set()
    for part in re.sub(r"[제권역\s]", "", label).split(","):
        if "~" in part:
            a, b = part.split("~")
            nums |= set(range(int(a), int(b) + 1))
        elif part.isdigit():
            nums.add(int(part))
    return region in nums


def _period_end(on: date, mmdd: str) -> date:
    m, d = int(mmdd[:2]), int(mmdd[3:5])
    for y in (on.year, on.year + 1):
        try:
            e = date(y, m, d)
        except ValueError:
            e = date(y, m, 28)
        if e >= on:
            return e
    raise ValueError


def lookup_price(repo: Repository, *, product_id: int, species_id: int, region: int | None, on: date,
                 a, warnings: list[str], steps: list[str]) -> dict:
    if a.applied_price_override:
        unit = a.applied_price_unit or ("KRW_PER_FISH" if a.held_count is not None and a.held_kg is None else
                                        "KRW_PER_KG" if a.held_kg is not None or a.avg_weight_g else "KRW_PER_LINE")
        warnings.append("공시 적용가격 대신 수동 입력 가격으로 계산")
        return {"price": a.applied_price_override, "unit": unit, "source": "요청값(수동 입력)"}
    if region is None:
        raise ServiceError(422, "어가 시군의 권역을 알 수 없습니다 (현재 7·8권역만 매핑). applied_price_override 를 사용하세요")
    rows = repo.list_prices(product_id, species_id, str(region), on)
    month_rows = [r for r in rows if r["month"] is None or int(r["month"]) == on.month]
    variants = sorted({r["variant"] for r in month_rows if r["variant"]})
    variant = a.price_variant
    formulas = [x for x in repo.list_formulas(product_id, on) if _region_matches(x.get("region_label"), region)]
    if variant is None and len(variants) > 1:
        raise ServiceError(422, "가격 구분이 여러 개입니다. aquatic.price_variant 를 지정하세요",
                           {"price_variants": variants, "formula_variants": sorted({x["variant"] for x in formulas})})
    if variant is None and len(variants) == 1:
        variant = variants[0]
        others = sorted({r["variant"] for r in rows if r["variant"] and r["variant"] != variant}
                        | {x["variant"] for x in formulas})
        if others:
            warnings.append(f"가격 구분을 '{variant}'(사고월 공시)로 자동 선택함. 다른 구분이면 price_variant 지정: {', '.join(others)}")
    weights = [D(str(r["weight_min_g"])) for r in rows if r["weight_min_g"] is not None]
    if weights and a.avg_weight_g is None and (variant is None or any(r["variant"] == variant and r["weight_min_g"] for r in rows)):
        raise ServiceError(422, "체중 구간 가격 품목입니다. aquatic.avg_weight_g 가 필요합니다")
    wg = a.avg_weight_g if weights else None
    if wg is not None and wg < min(weights):
        raise ServiceError(422, f"평균체중 {f(wg)}g 은 공시 최소 구간 {f(min(weights))}g 미만입니다")
    p = repo.find_price(product_id=product_id, species_id=species_id, region_no=str(region), on_date=on,
                        weight_g=wg, variant=variant)
    if p:
        return {k: p.get(k) for k in ("price", "unit", "weight_min_g", "month", "variant", "region_no",
                                      "valid_from", "valid_to", "notice_month", "source")}

    # 공시표에 없으면 산식(비수확기 등) 시도
    fx = [x for x in formulas if variant is None or x["variant"] == variant or x["variant"].startswith(variant)]
    if len(fx) > 1 and variant is None:
        raise ServiceError(422, "이 시점 가격은 산식으로 공시됩니다. aquatic.price_variant 로 산식을 지정하세요",
                           {"formula_variants": [x["variant"] for x in fx]})
    if fx:
        x = fx[0]
        base = D(str(x["base_price"])) if x.get("base_price") is not None else None
        if base is None:   # 다시마 식용 비수확기: 6월 수확기 권역 가격
            hp = repo.find_price(product_id=product_id, species_id=species_id, region_no=str(region), on_date=on,
                                 weight_g=None, variant="식용_수확기", month=6)
            if hp is None:
                raise ServiceError(422, f"{region}권역 수확기 가격이 공시되지 않아 비수확기 산식을 계산할 수 없습니다")
            base = D(str(hp["price"]))
        if not x.get("period_end") or "잔여일수" not in x["formula"]:
            raise ServiceError(422, f"'{x['variant']}' 산식은 추가 입력이 필요해 자동 계산하지 않습니다: {x['formula']}. "
                                    "applied_price_override 를 사용하세요")
        end = _period_end(on, x["period_end"][:5])
        remain = (end - on).days
        price = max(won(base * (1 - D(remain) * D("0.1") / 30)), D(0))
        steps.append(f"비수확기 적용가격 = {f(base)} × (1 - 잔여일수 {remain} × 10%/30) = {f(price)} (종료일 {end})")
        if x.get("floor"):
            warnings.append(f"산식 최저한도 '{x['floor']}' 은 금액이 공시되지 않아 반영하지 못함")
        return {"price": price, "unit": "KRW_PER_KG", "variant": x["variant"], "formula": x["formula"],
                "source": x.get("source")}
    raise ServiceError(422, f"{on} 기준 {region}권역 적용가격 공시가 없습니다 (공시 미적재 기간이면 applied_price_override)")


def _qty(a, unit: str, warnings: list[str]) -> tuple[D, D, str]:
    if unit == "KRW_PER_FISH":
        if a.held_count is None:
            raise ServiceError(422, "적용가격이 마리당입니다. held_count/damaged_count 를 보내주세요")
        return a.held_count, a.damaged_count, "마리"
    if unit == "KRW_PER_KG":
        if a.held_kg is not None:
            return a.held_kg, a.damaged_kg, "kg"
        if a.held_count is not None and a.avg_weight_g:
            warnings.append("kg 단위 가격이라 마릿수 × 평균체중으로 중량 환산")
            return a.held_count * a.avg_weight_g / 1000, a.damaged_count * a.avg_weight_g / 1000, "kg"
        raise ServiceError(422, "적용가격이 kg당입니다. held_kg/damaged_kg 를 보내주세요")
    if unit in ("KRW_PER_LINE", "KRW_PER_BOOK"):
        if a.held_units is None:
            raise ServiceError(422, "적용가격이 수하연/책 단위입니다. held_units/damaged_units 를 보내주세요")
        return a.held_units, a.damaged_units, "수하연" if unit == "KRW_PER_LINE" else "책"
    raise ServiceError(422, f"보험가액 방식에 쓸 수 없는 적용가격 단위 {unit}")


# ---------- 보장·규칙 선택 ----------

def choose_rule(repo, t, req: EstimateRequest, riders: list[str]) -> tuple[Rule | None, dict | None, list[str]]:
    pid = t["product_id"]
    main = MAIN[pid]
    obj = req.object or main.object
    m = engine.match_coverages(req.peril, repo.get_coverages(pid), riders)
    reasons = []
    excl = [c for c in m.excluded_by if obj == "수산물"]   # 부담보 특약은 모두 수산물 대상
    if excl:
        return None, None, [f'{c["coverage_key"]} {c["name"]} 가입으로 {req.peril} 손해는 보상하지 않음' for c in excl]
    cands = []
    for c in m.covering:
        if req.coverage_key and c["coverage_key"] != req.coverage_key:
            continue
        r = resolve(pid, c["coverage_key"], c["name"], c["contract_type"], obj, t["species_id"])
        if r is not None and r.object == obj:
            cands.append((c, r))
    if not cands:
        reasons.append(f"{req.peril}로 인한 {obj} 손해를 보장하는 주계약/가입 특약이 없음")
        return None, None, reasons
    rules = {(r.method, r.deductible, r.full_cover_ratio, r.fixed_amount, r.min_amount) for _, r in cands}
    if len(rules) > 1:
        raise ServiceError(422, "해당 재해에 계산 방식이 다른 보장이 여러 개입니다. coverage_key 를 지정하세요",
                           {"coverage_options": [{"coverage_key": c["coverage_key"], "name": c["name"]} for c, _ in cands]})
    cands.sort(key=lambda cr: (cr[0]["contract_type"] != "주계약", cr[0]["coverage_key"]))
    c, r = cands[0]
    return r, c, []


# ---------- 메인 ----------

def estimate(repo: Repository, req: EstimateRequest) -> dict:
    t = repo.get_target(req.insurance_id, req.mapping_id)
    if t is None:
        raise ServiceError(404, "계약 또는 보험목적(mapping_id)을 찾을 수 없습니다")
    pid = t["product_id"]
    if pid not in MAIN:
        raise ServiceError(422, f"product_id {pid} 의 산정 규칙이 없습니다")

    ri = engine.parse_rider_details(t["rider_details"])
    warnings: list[str] = []
    steps: list[str] = []
    rate = req.deductible_rate_override or ri.deductible_rate
    if req.deductible_rate_override and ri.deductible_rate and req.deductible_rate_override != ri.deductible_rate:
        warnings.append(f"자기부담비율을 계약값 {f(ri.deductible_rate)} 대신 요청값 {f(req.deductible_rate_override)}로 계산")
    min_rate = req.min_deductible_rate_override or ri.min_deductible_rate
    region = sea_region_of(t.get("sigungu_name"))
    coverage = D(str(t["coverage_amount"]))
    remaining = coverage - req.prior_paid_in_period

    contract = {"insurance_id": t["insurance_id"], "product_id": pid, "product_name": t.get("product_name"),
                "species_id": t["species_id"], "species": t["standard_name"], "sigungu": t.get("sigungu_name"),
                "sea_region": region, "coverage_amount": coverage, "plan": ri.plan, "deductible_rate": rate,
                "riders": ri.riders, "period": [t["start_date"], t["end_date"]], "status": t["contract_status"]}

    not_covered = []
    if t["contract_status"] != "유효":
        not_covered.append(f"계약 상태가 '{t['contract_status']}'입니다")
    if not (t["start_date"] <= req.accident_date <= t["end_date"]):
        not_covered.append("사고일이 보험기간 밖입니다")
    rule, cov, reasons = choose_rule(repo, t, req, ri.riders)
    not_covered += reasons
    if remaining <= 0 and not not_covered:
        not_covered.append("이전 지급으로 잔존보험가입금액이 없습니다")
    rule_info = None
    if rule:
        rule_info = {"coverage_key": cov["coverage_key"], "coverage_name": cov["name"], "object": rule.object,
                     "method": rule.method, "deductible": rule.deductible, "source": rule.source,
                     "interpretation": rule.interpretation}
        if rule.interpretation:
            warnings.append("해석 적용: " + rule.interpretation)
    if not_covered:
        return {"contract": contract, "covered": False, "rule": rule_info, "not_covered_reasons": not_covered,
                "result": {"payout": D(0)}, "warnings": warnings}

    plan = ri.plan
    if rule.deductible == "PLAN_TABLE":
        warnings += ri.warnings
        if plan in ("보급형Ⅰ", "보급형Ⅱ"):
            if not rule.budget_plans or (rule.budget_species and t["species_id"] not in rule.budget_species):
                raise ServiceError(422, f"이 상품/품목에는 {plan}이 없습니다 (약관 별표 '보험상품 유형')")
    if remaining < coverage:
        steps.append(f"잔존보험가입금액 = {f(coverage)} - 이전 지급 {f(req.prior_paid_in_period)} = {f(remaining)}")

    price_info = None
    value = loss = dr = None
    proportional = False
    contract_ends = False
    alt = None

    try:
        # ---- 양식불능보험금 ----
        if req.benefit == "양식불능":
            if rule.unfarmable is None:
                raise ServiceError(422, "이 상품에는 양식불능보험금이 없습니다")
            u = req.unfarmable
            if rule.unfarmable == "ELAPSED":
                if u is None or u.elapsed_days is None:
                    raise ServiceError(422, "unfarmable.elapsed_days 가 필요합니다")
                calculated = min(engine.unfarmable_elapsed(coverage, u.elapsed_days, steps), remaining)
            else:  # UNIT_PRICE (굴·홍합)
                if u is None or u.disaster_unit_price is None or u.lines is None:
                    raise ServiceError(422, "unfarmable.disaster_unit_price, lines 가 필요합니다")
                if req.damage and req.damage.damage_rate is not None:
                    dr = req.damage.damage_rate
                elif req.aquatic:
                    price_info = lookup_price(repo, product_id=pid, species_id=t["species_id"], region=region,
                                              on=req.accident_date, a=req.aquatic, warnings=warnings, steps=steps)
                    held, dmg, _ = _qty(req.aquatic, price_info["unit"], warnings)
                    dr = dmg / held if held else D(0)
                    steps.append(f"피해율 = 손해액 ÷ 보험가액 = {f(dmg)} ÷ {f(held)} = {f(round(dr, 4))}")
                else:
                    raise ServiceError(422, "피해율(damage.damage_rate) 또는 aquatic 입력이 필요합니다")
                if dr < D("0.6"):
                    raise ServiceError(422, f"피해율 {f(round(dr, 4))} 이 60% 미만이라 양식불능보험금 대상이 아닙니다")
                if u.days_since_main_hanging is not None and u.days_since_main_hanging > 90:
                    raise ServiceError(422, "본수하일부터 90일이 지나 양식불능보험금 대상이 아닙니다")
                calculated = min(engine.unfarmable_unit_price(u.disaster_unit_price, u.lines, dr, steps), remaining)
            deductible, payout, contract_ends = D(0), calculated, True
            steps.append("양식불능보험금은 자기부담금을 차감하지 않으며, 지급 시 계약이 소멸합니다")

        # ---- 보험가액·손해액 (수산물) ----
        elif rule.method == "VALUE_LOSS":
            a = req.aquatic
            if a is None:
                raise ServiceError(422, "수산물 손해는 aquatic 입력이 필요합니다")
            price_info = lookup_price(repo, product_id=pid, species_id=t["species_id"], region=region,
                                      on=req.accident_date, a=a, warnings=warnings, steps=steps)
            unit_price = D(str(price_info["price"]))
            held, dmg, ul = _qty(a, price_info["unit"], warnings)
            if rule.deductible == "PLAN_TABLE" and plan in engine.PRICE_FACTOR and engine.PRICE_FACTOR[plan] != 1:
                fac = engine.PRICE_FACTOR[plan]
                steps.append(f"상품유형 {plan} 적용가격 = {f(unit_price)} × {f(fac)}")
                unit_price = unit_price * fac
            value, loss = won(held * unit_price), won(dmg * unit_price)
            steps.append(f"보험가액 = {f(held)}{ul} × {f(unit_price)} = {f(value)}")
            steps.append(f"손해액 = {f(dmg)}{ul} × {f(unit_price)} = {f(loss)}")
            calculated, proportional = engine.base_amount(loss, value, remaining, rule.full_cover_ratio, steps)
            deductible, payout, alt = engine.apply_deductible(rule=rule, plan=plan, calculated=calculated, coverage=coverage,
                                                              rate=rate, min_rate=min_rate,
                                                              prior_calculated=req.prior_calculated_in_period,
                                                              steps=steps, warnings=warnings)

        # ---- 시설물 ----
        elif rule.method == "FACILITY":
            fi = req.facility
            if fi is None:
                raise ServiceError(422, "시설물 손해는 facility 입력이 필요합니다")
            value = won(fi.replacement_cost - fi.depreciation_value)
            loss = won(fi.restoration_cost - fi.depreciation_loss)
            steps.append(f"보험가액 = 재조달가액 {f(fi.replacement_cost)} - 감가상각 {f(fi.depreciation_value)} = {f(value)}")
            steps.append(f"손해액 = 원상복구비 {f(fi.restoration_cost)} - 감가상각 {f(fi.depreciation_loss)} = {f(loss)}")
            calculated, proportional = engine.base_amount(loss, value, remaining, rule.full_cover_ratio, steps)
            deductible, payout, alt = engine.apply_deductible(rule=rule, plan=None, calculated=calculated, coverage=coverage,
                                                              rate=rate, min_rate=min_rate, prior_calculated=D(0),
                                                              steps=steps, warnings=warnings)

        # ---- 김 수확감소 ----
        elif rule.method == "HARVEST_DAMAGE_RATE":
            if req.damage is None:
                raise ServiceError(422, "김 수확감소보험금은 damage 입력(피해율 또는 평년·총수확량)이 필요합니다")
            if rate is None:
                raise ServiceError(422, "자기부담비율이 필요합니다")
            d = req.damage
            dr = engine.damage_rate_of(damage_rate=d.damage_rate, normal_yield=d.normal_yield, total_yield=d.total_yield,
                                       unindemnified=d.unindemnified, steps=steps)
            calculated = min(won(coverage * dr), remaining)
            payout = min(won(coverage * max(dr - rate, D(0))), remaining)
            deductible = calculated - payout
            steps.append(f"수확감소보험금 = 가입금액 {f(coverage)} × (피해율 {f(round(dr, 4))} - 자기부담비율 {f(rate)}) = {f(payout)}")

        # ---- 생산비 (흰다리새우 / 가리비 생산비보장 특약) ----
        elif rule.method in ("PRODUCTION_COST_ELAPSED", "PRODUCTION_COST"):
            d = req.damage
            if d is None:
                raise ServiceError(422, "생산비 방식은 damage 입력(피해율 또는 잔존량·추정보유량)이 필요합니다")
            dr = engine.damage_rate_of(damage_rate=d.damage_rate, remaining=d.remaining,
                                       estimated_holding=d.estimated_holding, harvested=d.harvested, steps=steps)
            ratio = D(1)
            if rule.method == "PRODUCTION_COST_ELAPSED" and not d.in_harvest:
                if d.growth_days is None:
                    raise ServiceError(422, "수확기 이전 사고는 damage.growth_days(생장일수)가 필요합니다")
                ratio = engine.shrimp_elapsed_ratio(d.growth_days, steps)
            calculated = min(won(coverage * ratio * dr), remaining)
            steps.append(f"산정보험금 = 가입금액 {f(coverage)}" + (f" × 경과비율 {f(round(ratio, 6))}" if ratio != 1 else "")
                         + f" × 피해율 {f(round(dr, 4))} = {f(calculated)}")
            deductible, payout, alt = engine.apply_deductible(rule=rule, plan=None, calculated=calculated, coverage=coverage,
                                                              rate=rate, min_rate=min_rate, prior_calculated=D(0),
                                                              steps=steps, warnings=warnings)
        else:  # pragma: no cover
            raise ServiceError(500, f"알 수 없는 산정 방식 {rule.method}")
    except ValueError as e:
        raise ServiceError(422, str(e))

    steps.append(f"지급 예상 보험금 = {f(payout)}")
    result = engine.ClaimResult(coverage_amount=coverage, coverage_remaining=remaining, insured_value=value, loss=loss,
                                damage_rate=dr, proportional=proportional, calculated=calculated, deductible=deductible,
                                payout=payout, farmer_burden=(loss - payout) if loss is not None else None,
                                contract_ends=contract_ends, alternative=alt, steps=steps)
    out = asdict(result)
    out.pop("warnings")
    return {"contract": contract, "covered": True, "rule": rule_info, "applied_price": price_info,
            "result": out, "warnings": warnings}
