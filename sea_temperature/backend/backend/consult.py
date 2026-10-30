"""Consultation dashboard API: customer list, consultation history, saving a consultation.

Coverage is derived from contracts and riders, never stored.
No staff authentication exists yet: run only on a trusted local network.
"""
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from psycopg import Connection
from pydantic import BaseModel, Field, model_validator

from backend.customer_api import request_protection
from backend.db import get_customer_db, get_db

SEASON = "2026-고수온"
STATUS = Literal["미연락", "부재·재연락", "문자 발송", "상담 예약", "가입 완료", "안내 완료", "보류·거절"]
# Products whose base policy already covers high temperature (상품요약서 2026.5.13: 해상 전복, 오만둥이).
# Interim: insurance.insurance_products has no coverage-type column yet.
BASE_HEAT_PRODUCTS = [2, 20]
HEAT_RIDER = "고수온원인 수산물손해담보 특별약관"
HEAT_EXCLUSION = "이상수온원인 수산물손해부담보 특별약관"
# 저수온 모드(?mode=cold): 저수온 특약이 있거나, 주계약에 저수온이 들어 있는 상품(insurance_coverages 에서 찾음)이면 보장
COLD_RIDER = "저수온원인 수산물손해담보 특별약관"
COLD_BASE_SQL = """SELECT DISTINCT product_id FROM insurance.insurance_coverages
                   WHERE contract_type = '주계약' AND effect = '보장추가' AND risk_types::text LIKE '%%저수온%%'"""
REGION_SHORT = "regexp_replace(r.sigungu_name, '(시|군)$', '')"


def mask_phone(phone: str | None) -> str | None:
    return None if phone is None else f"{phone[:3]}-****-{phone[-4:]}"


def contracts_by_household(db: Connection, household_ids: list[int], mode: str = "heat") -> dict[int, list[dict]]:
    if mode == "cold":
        rider, riders_short = COLD_RIDER, "저수온"
        base = [r["product_id"] for r in db.execute(COLD_BASE_SQL).fetchall()]
    else:
        rider, riders_short, base = HEAT_RIDER, HEAT_RIDER, BASE_HEAT_PRODUCTS
    rows = db.execute("""
        SELECT m.household_id, m.mapping_id, s.standard_name AS species,
               CASE
                 WHEN bool_or(c.insurance_id IS NOT NULL AND (
                        COALESCE(t.rider_details->'riders' ?| ARRAY[%(rider)s, %(short)s], false)
                        OR (c.product_id = ANY(%(base)s)
                            AND NOT COALESCE(t.rider_details->'riders' ? %(exclusion)s, false))))
                   THEN 'covered'
                 WHEN bool_or(c.insurance_id IS NOT NULL) THEN 'no_rider'
                 ELSE 'none'
               END AS coverage
        FROM customer_service.household_species m
        JOIN customer_service.fish_species s ON s.species_id = m.species_id
        LEFT JOIN customer_service.insurance_targets t ON t.mapping_id = m.mapping_id
        -- Only valid aquatic-product contracts for this species count; facility policies do not.
        LEFT JOIN customer_service.insurance_contracts c
               ON c.insurance_id = t.insurance_id AND c.contract_status = '유효'
              AND EXISTS (SELECT 1 FROM insurance.insurance_map im
                          WHERE im.product_id = c.product_id AND im.species_id = m.species_id
                            AND im.coverage_target = '수산물')
        WHERE m.household_id = ANY(%(ids)s) AND m.status <> '폐업'
        GROUP BY m.household_id, m.mapping_id, s.standard_name, m.is_primary
        ORDER BY m.household_id, m.is_primary DESC, m.mapping_id
    """, {"rider": rider, "short": riders_short, "base": base, "exclusion": HEAT_EXCLUSION,
          "ids": household_ids}).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["household_id"], []).append(
            {"mapping_id": row["mapping_id"], "species": row["species"],
             "coverage": row["coverage"], "sale_text": None})
    return grouped


def list_customers(db: Connection, season: str, mode: str = "heat") -> list[dict]:
    rows = db.execute(f"""
        SELECT h.household_id, h.owner_name AS name, h.phone_number, h.sms_consent,
               {REGION_SHORT} AS region, COALESCE(cs.status, '미연락') AS status,
               lg.last_contact, COALESCE(lg.consult_count, 0) AS consult_count, q.risk_stage
        FROM customer_service.fishery_households h
        LEFT JOIN public.sigungu_area_coordinates r ON r.region_id = h.region_code
        LEFT JOIN customer_service.consult_cases cs ON cs.household_id = h.household_id AND cs.season = %s
        LEFT JOIN (SELECT household_id, max(contacted_at AT TIME ZONE 'Asia/Seoul')::date AS last_contact,
                          count(*) AS consult_count
                   FROM customer_service.consult_logs GROUP BY household_id) lg ON lg.household_id = h.household_id
        LEFT JOIN LATERAL (SELECT risk_stage FROM customer_service.contact_queue q
                           WHERE q.household_id = h.household_id ORDER BY q.base_date DESC LIMIT 1) q ON true
        ORDER BY h.household_id
    """, (season,)).fetchall()
    contracts = contracts_by_household(db, [r["household_id"] for r in rows], mode)
    return [{"code": str(r["household_id"]), "name": r["name"], "phone_masked": mask_phone(r["phone_number"]),
             "sms_consent": r["sms_consent"], "region": r["region"],
             "contracts": contracts.get(r["household_id"], []), "risk_stage": r["risk_stage"],
             "status": r["status"], "last_contact": r["last_contact"], "consult_count": r["consult_count"]}
            for r in rows]


def list_history(db: Connection, household_id: int | None = None) -> list[dict]:
    rows = db.execute(f"""
        SELECT l.log_id, l.household_id, h.owner_name AS name, {REGION_SHORT} AS region, l.channel, l.staff_name,
               (l.contacted_at AT TIME ZONE 'Asia/Seoul')::date AS date, l.result_status, l.memo,
               ARRAY(SELECT s.standard_name FROM customer_service.household_species m
                     JOIN customer_service.fish_species s ON s.species_id = m.species_id
                     WHERE m.household_id = l.household_id ORDER BY m.is_primary DESC, m.mapping_id) AS species
        FROM customer_service.consult_logs l
        JOIN customer_service.fishery_households h ON h.household_id = l.household_id
        LEFT JOIN public.sigungu_area_coordinates r ON r.region_id = h.region_code
        WHERE %(hid)s::integer IS NULL OR l.household_id = %(hid)s
        ORDER BY l.contacted_at DESC, l.log_id DESC
    """, {"hid": household_id}).fetchall()
    return [{"log_id": r["log_id"], "code": str(r["household_id"]), "name": r["name"], "region": r["region"],
             "species": r["species"], "date": r["date"], "result": r["result_status"], "memo": r["memo"] or "–",
             "channel": r["channel"], "staff_name": r["staff_name"]} for r in rows]


def save_consultation(db: Connection, household_id: int, season: str, status: str, channel: str,
                      memo: str | None, next_contact_at, items: list[dict], staff_name: str | None = None) -> int:
    """Upsert the case, append one log and its per-species results; runs in the caller's transaction."""
    if db.execute("SELECT 1 FROM customer_service.fishery_households WHERE household_id = %s",
                  (household_id,)).fetchone() is None:
        raise ValueError("존재하지 않는 어가입니다.")
    mapping_ids = [i["mapping_id"] for i in items]
    owned = db.execute("""
        SELECT count(*) AS n FROM customer_service.household_species
        WHERE household_id = %s AND mapping_id = ANY(%s)
    """, (household_id, mapping_ids)).fetchone()["n"]
    if owned != len(set(mapping_ids)):
        raise ValueError("다른 어가의 어종이 포함되어 있습니다.")
    insurance_ids = [i["insurance_id"] for i in items if i.get("insurance_id") is not None]
    if insurance_ids:
        own_contracts = db.execute("""
            SELECT count(*) AS n FROM customer_service.insurance_contracts
            WHERE household_id = %s AND insurance_id = ANY(%s)
        """, (household_id, insurance_ids)).fetchone()["n"]
        if own_contracts != len(set(insurance_ids)):
            raise ValueError("다른 어가의 보험 계약이 포함되어 있습니다.")
    case_id = db.execute("""
        INSERT INTO customer_service.consult_cases (household_id, season, status, next_contact_at, last_contact_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (household_id, season) DO UPDATE
           SET status = EXCLUDED.status, next_contact_at = EXCLUDED.next_contact_at,
               last_contact_at = EXCLUDED.last_contact_at, updated_at = now()
        RETURNING case_id
    """, (household_id, season, status, next_contact_at)).fetchone()["case_id"]
    log_id = db.execute("""
        INSERT INTO customer_service.consult_logs
            (case_id, household_id, channel, result_status, memo, next_contact_at, staff_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING log_id
    """, (case_id, household_id, channel, status, memo, next_contact_at, staff_name)).fetchone()["log_id"]
    for item in items:
        db.execute("""
            INSERT INTO customer_service.consult_log_items (log_id, mapping_id, result, insurance_id)
            VALUES (%s, %s, %s, %s)
        """, (log_id, item["mapping_id"], item["result"], item.get("insurance_id")))
    return log_id


def delete_consultation(db: Connection, log_id: int) -> dict:
    """Delete one log and its per-species results, then re-derive the case from the logs that remain.

    consult_cases holds the latest state of a household for a season, so after a deletion it must
    match the newest remaining log; with no logs left the case row is removed (the household reads
    as '미연락' again). Runs in the caller's transaction.
    """
    log = db.execute("""
        SELECT log_id, case_id, household_id FROM customer_service.consult_logs WHERE log_id = %s
    """, (log_id,)).fetchone()
    if log is None:
        raise LookupError("이미 지워졌거나 없는 상담 기록입니다.")
    # Lock the case so a concurrent save or delete for the same household cannot interleave.
    db.execute("SELECT 1 FROM customer_service.consult_cases WHERE case_id = %s FOR UPDATE", (log["case_id"],))
    db.execute("DELETE FROM customer_service.consult_log_items WHERE log_id = %s", (log_id,))
    db.execute("DELETE FROM customer_service.consult_logs WHERE log_id = %s", (log_id,))
    latest = db.execute("""
        SELECT result_status, next_contact_at, contacted_at FROM customer_service.consult_logs
        WHERE case_id = %s ORDER BY contacted_at DESC, log_id DESC LIMIT 1
    """, (log["case_id"],)).fetchone()
    if latest is None:
        db.execute("DELETE FROM customer_service.consult_cases WHERE case_id = %s", (log["case_id"],))
        status = "미연락"
    else:
        db.execute("""
            UPDATE customer_service.consult_cases
               SET status = %s, next_contact_at = %s, last_contact_at = %s, updated_at = now()
             WHERE case_id = %s
        """, (latest["result_status"], latest["next_contact_at"], latest["contacted_at"], log["case_id"]))
        status = latest["result_status"]
    return {"log_id": log_id, "household_id": log["household_id"], "status": status}


class ConsultItem(BaseModel):
    mapping_id: int = Field(gt=0)
    result: Literal["가입", "보류", "안내", "타 기관 가입"]
    insurance_id: int | None = Field(default=None, gt=0)


class ConsultInput(BaseModel):
    household_id: int = Field(gt=0)
    season: str = Field(default=SEASON, min_length=1, max_length=20)
    status: STATUS
    channel: Literal["전화", "문자", "방문", "창구"]
    memo: str | None = Field(default=None, max_length=1000)
    next_contact_at: datetime | None = None
    staff_name: str | None = Field(default=None, max_length=50)
    items: list[ConsultItem] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def next_contact_required(self):
        # Mirrors the consult_cases CHECK so clients get 422 instead of a generic DB error.
        if self.status in ("부재·재연락", "상담 예약") and self.next_contact_at is None:
            raise ValueError("부재·재연락, 상담 예약은 다음 연락 일시가 필요합니다.")
        return self


router = APIRouter(prefix="/api/consult", tags=["상담 대시보드"], dependencies=[Depends(request_protection)])
ReadDB = Annotated[Connection, Depends(get_db)]
WriteDB = Annotated[Connection, Depends(get_customer_db, scope="function")]


@router.get("/customers")
def customers(db: ReadDB, season: Annotated[str, Query(min_length=1, max_length=20)] = SEASON,
              mode: Literal["heat", "cold"] = "heat"):
    """mode=cold 면 계약별 보장(coverage)을 저수온 기준으로 판정해요."""
    return list_customers(db, season, mode)


@router.get("/history")
def history(db: ReadDB, household_id: Annotated[int | None, Query(gt=0)] = None):
    return list_history(db, household_id)


@router.post("/logs", status_code=201)
def create_log(data: ConsultInput, db: WriteDB):
    try:
        log_id = save_consultation(db, data.household_id, data.season, data.status, data.channel, data.memo,
                                   data.next_contact_at, [i.model_dump() for i in data.items], data.staff_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"log_id": log_id}


@router.delete("/logs/{log_id}")
def remove_log(log_id: Annotated[int, Path(gt=0)], db: WriteDB):
    """Delete one consultation record (the screen asks the user to confirm first)."""
    try:
        return delete_consultation(db, log_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
