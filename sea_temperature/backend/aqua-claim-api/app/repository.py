"""DB 접근. 서비스는 Repository 프로토콜만 알고, 실제 구현은 PostgreSQL 또는 메모리(테스트용)."""
from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal as D
from typing import Protocol

TARGET_SQL = """
SELECT c.insurance_id, c.household_id, c.product_id, c.policy_number, c.total_premium,
       c.start_date, c.end_date, c.contract_status,
       t.mapping_id, t.coverage_amount, t.rider_details,
       hs.species_id, hs.production_ratio, hs.status AS species_status,
       fs.standard_name, fs.common_name, fs.farming_method,
       h.household_name, s.sigungu_name, s.area_name,
       p.product_name
FROM customer_service.insurance_contracts c
JOIN customer_service.insurance_targets t   ON t.insurance_id = c.insurance_id
JOIN customer_service.household_species hs  ON hs.mapping_id = t.mapping_id
JOIN customer_service.fish_species fs       ON fs.species_id = hs.species_id
JOIN customer_service.fishery_households h  ON h.household_id = c.household_id
LEFT JOIN public.sigungu_area_coordinates s ON s.region_id = h.region_code
LEFT JOIN insurance.insurance_products p    ON p.product_id = c.product_id
"""

PRICE_SQL = """
SELECT price, unit, weight_min_g, month, variant, region_no, valid_from, valid_to, notice_month, section, source, note
FROM insurance.insurance_applied_price
WHERE product_id = %(product_id)s AND species_id = %(species_id)s
  AND region_no IN (%(region_no)s, '전권역')
  AND (valid_from IS NULL OR valid_from <= %(on_date)s)
  AND (valid_to   IS NULL OR valid_to   >= %(on_date)s)
  AND (month IS NULL OR month = %(month)s)
  AND (%(variant)s::text IS NULL OR variant = %(variant)s)
  AND (CASE WHEN %(weight_g)s::numeric IS NULL THEN weight_min_g IS NULL
            ELSE weight_min_g IS NULL OR weight_min_g <= %(weight_g)s::numeric END)
ORDER BY weight_min_g DESC NULLS LAST, notice_month DESC
LIMIT 1
"""


class Repository(Protocol):
    def get_target(self, insurance_id: int, mapping_id: int) -> dict | None: ...
    def list_household_targets(self, household_id: int) -> list[dict]: ...
    def get_coverages(self, product_id: int) -> list[dict]: ...
    def find_price(self, *, product_id: int, species_id: int, region_no: str, on_date: date,
                   weight_g: D | None, variant: str | None, month: int | None = None) -> dict | None: ...
    def list_prices(self, product_id: int, species_id: int, region_no: str, on_date: date) -> list[dict]: ...
    def list_formulas(self, product_id: int, on_date: date) -> list[dict]: ...


def _rd(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


class PgRepository:
    def __init__(self, pool):
        self.pool = pool

    def _all(self, sql: str, params) -> list[dict]:
        from psycopg.rows import dict_row
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def get_target(self, insurance_id, mapping_id):
        rows = self._all(TARGET_SQL + " WHERE c.insurance_id = %s AND t.mapping_id = %s", (insurance_id, mapping_id))
        if not rows:
            return None
        r = rows[0]
        r["rider_details"] = _rd(r["rider_details"])
        return r

    def list_household_targets(self, household_id):
        rows = self._all(TARGET_SQL + " WHERE c.household_id = %s ORDER BY c.start_date DESC, t.mapping_id",
                         (household_id,))
        for r in rows:
            r["rider_details"] = _rd(r["rider_details"])
        return rows

    def get_coverages(self, product_id):
        rows = self._all("SELECT coverage_id, coverage_key, contract_type, name, risk_types, effect "
                         "FROM insurance.insurance_coverages WHERE product_id = %s ORDER BY coverage_key",
                         (product_id,))
        for r in rows:
            if isinstance(r["risk_types"], str):
                r["risk_types"] = json.loads(r["risk_types"])
        return rows

    def find_price(self, *, product_id, species_id, region_no, on_date, weight_g, variant, month=None):
        rows = self._all(PRICE_SQL, dict(product_id=product_id, species_id=species_id, region_no=region_no,
                                         on_date=on_date, month=month or on_date.month, variant=variant, weight_g=weight_g))
        return rows[0] if rows else None

    def list_prices(self, product_id, species_id, region_no, on_date):
        return self._all("SELECT price, unit, weight_min_g, month, variant, region_no, size_label, valid_from, valid_to "
                         "FROM insurance.insurance_applied_price "
                         "WHERE product_id=%s AND species_id=%s AND region_no IN (%s,'전권역') "
                         "AND (valid_from IS NULL OR valid_from <= %s) AND (valid_to IS NULL OR valid_to >= %s)",
                         (product_id, species_id, region_no, on_date, on_date))

    def list_formulas(self, product_id, on_date):
        return self._all("SELECT section, product_id, variant, applies, formula, base_price, period_end, floor, region_label, "
                         "valid_from, valid_to, source FROM insurance.insurance_applied_price_formula "
                         "WHERE product_id=%s AND (valid_from IS NULL OR valid_from <= %s) "
                         "AND (valid_to IS NULL OR valid_to >= %s)", (product_id, on_date, on_date))


class MemoryRepository:
    """테스트·로컬 시연용. targets/coverages 는 dict 리스트, 가격은 applied_price CSV."""

    def __init__(self, targets: list[dict], coverages: list[dict], price_csv: str, formula_csv: str | None = None):
        self.targets = targets
        self.coverages = coverages
        self.formulas = []
        if formula_csv:
            with open(formula_csv, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    self.formulas.append({**r, "product_id": int(r["product_id"]),
                                          "base_price": D(r["base_price"]) if r["base_price"] else None,
                                          "valid_from": date.fromisoformat(r["valid_from"]) if r["valid_from"] else None,
                                          "valid_to": date.fromisoformat(r["valid_to"]) if r["valid_to"] else None})
        self.prices = []
        with open(price_csv, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                self.prices.append({
                    **r,
                    "product_id": int(r["product_id"]), "species_id": int(r["species_id"]),
                    "price": D(r["price"]), "weight_min_g": D(r["weight_min_g"]) if r["weight_min_g"] else None,
                    "month": int(r["month"]) if r["month"] else None, "variant": r["variant"] or None,
                    "valid_from": date.fromisoformat(r["valid_from"]) if r["valid_from"] else None,
                    "valid_to": date.fromisoformat(r["valid_to"]) if r["valid_to"] else None,
                })

    def get_target(self, insurance_id, mapping_id):
        return next((t for t in self.targets if t["insurance_id"] == insurance_id and t["mapping_id"] == mapping_id), None)

    def list_household_targets(self, household_id):
        return [t for t in self.targets if t["household_id"] == household_id]

    def get_coverages(self, product_id):
        return [c for c in self.coverages if c["product_id"] == product_id]

    def _candidates(self, product_id, species_id, region_no, on_date):
        return [p for p in self.prices
                if p["product_id"] == product_id and p["species_id"] == species_id
                and p["region_no"] in (region_no, "전권역")
                and (p["valid_from"] is None or p["valid_from"] <= on_date)
                and (p["valid_to"] is None or p["valid_to"] >= on_date)]

    def find_price(self, *, product_id, species_id, region_no, on_date, weight_g, variant, month=None):
        m = month or on_date.month
        c = [p for p in self._candidates(product_id, species_id, region_no, on_date)
             if (p["month"] is None or p["month"] == m)
             and (variant is None or p["variant"] == variant)
             and ((p["weight_min_g"] is None) if weight_g is None
                  else (p["weight_min_g"] is None or p["weight_min_g"] <= weight_g))]
        c.sort(key=lambda p: (p["weight_min_g"] is not None, p["weight_min_g"] or 0, p["notice_month"]), reverse=True)
        return c[0] if c else None

    def list_prices(self, product_id, species_id, region_no, on_date):
        return self._candidates(product_id, species_id, region_no, on_date)

    def list_formulas(self, product_id, on_date):
        return [x for x in self.formulas if x["product_id"] == product_id
                and (x["valid_from"] is None or x["valid_from"] <= on_date)
                and (x["valid_to"] is None or x["valid_to"] >= on_date)]
