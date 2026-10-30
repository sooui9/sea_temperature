"""
보험 데이터 API (insurance 스키마 → 대시보드) · 읽기만 함
  GET /api/insurance?species=조피볼락          → 어종에 맞는 보험 상품 + 고수온 보장 여부
  GET /api/insurance?species=전복&method=해상   → 같은 어종 상품이 여러 개면 양식 방식으로 좁히기
  GET /api/insurance/3                         → 상품 하나의 상세 (보장 항목 · 주요 면책)
"""
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException

load_dotenv(Path(__file__).parent / ".env", override=True)
router = APIRouter(prefix="/api/insurance", tags=["보험"])


def _db():
    opts = dict(sslmode=os.getenv("DB_SSLMODE", "require"), connect_timeout=10,
                cursor_factory=psycopg2.extras.RealDictCursor)
    if os.getenv("DATABASE_URL"):
        return psycopg2.connect(os.getenv("DATABASE_URL"), **opts)
    return psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
                            dbname=os.getenv("DB_NAME", "postgres"), user=os.getenv("DB_USER"),
                            password=os.getenv("DB_PASSWORD"), **opts)


# 고수온 보장 판정: 보장 항목의 위험 종류(risk_types)에 '고수온'이 들어간 것
HEAT_SQL = """
SELECT product_id,
       bool_or(contract_type = '주계약' AND coalesce(effect, '') <> '보장제외')   AS heat_base,
       bool_or(contract_type = '특약'   AND coalesce(effect, '') <> '보장제외')   AS heat_rider,
       bool_or(effect = '보장제외')                                             AS heat_excludable,
       json_agg(json_build_object('name', name, 'contract_type', contract_type,
                                  'effect', effect, 'is_optional', is_optional)
                ORDER BY contract_type, coverage_id)                            AS heat_items
FROM insurance.insurance_coverages
WHERE risk_types::text LIKE '%%고수온%%'
GROUP BY product_id
"""


def _heat_label(r):
    if r.get("heat_base"):
        return "기본 포함" + (" (부담보 특약으로 뺄 수 있음)" if r.get("heat_excludable") else "")
    if r.get("heat_rider"):
        return "특약 필요"
    return "확인 필요"


@router.get("")
def find_products(species: str, method: str = ""):
    species, method = species.strip(), method.strip()
    if not species:
        raise HTTPException(400, "species(어종)를 넣어 주세요. 예: ?species=조피볼락")
    with _db() as conn, conn.cursor() as cur:
        cur.execute(f"""
            WITH heat AS ({HEAT_SQL})
            SELECT p.product_id, p.product_name, p.species, p.sale_period, p.insurance_period,
                   p.government_subsidy, p.deductible, p.premium_payment_method, p.contacts,
                   p.document_version, h.heat_base, h.heat_rider, h.heat_excludable, h.heat_items
            FROM insurance.insurance_products p
            LEFT JOIN heat h ON h.product_id = p.product_id
            WHERE p.species ILIKE %s
              AND (%s = '' OR p.product_name ILIKE %s)
            ORDER BY p.product_id
        """, (f"%{species}%", method, f"%{method}%"))
        rows = cur.fetchall()
    for r in rows:
        r["heat_cover"] = _heat_label(r)
    return {"species": species, "method": method or None, "count": len(rows), "products": rows,
            "note": "보장 내용은 상품 문서(2026.5.13)에서 자동 추출한 값이라 상담 전 상품요약서·수협 확인 필요"}


@router.get("/{product_id}")
def product_detail(product_id: int):
    with _db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT product_id, product_name, species, sale_period, insurance_period, eligibility,
                              government_subsidy, deductible, premium_payment_method, contacts, document_version
                       FROM insurance.insurance_products WHERE product_id = %s""", (product_id,))
        product = cur.fetchone()
        if not product:
            raise HTTPException(404, "없는 상품 번호예요")
        cur.execute(f"SELECT * FROM ({HEAT_SQL}) h WHERE product_id = %s", (product_id,))
        heat = cur.fetchone() or {}
        cur.execute("""SELECT contract_type, name, effect, is_optional, risk_types
                       FROM insurance.insurance_coverages WHERE product_id = %s
                       ORDER BY contract_type, coverage_id""", (product_id,))
        coverages = cur.fetchall()
        cur.execute("""SELECT summary, scope FROM insurance.insurance_exclusions
                       WHERE product_id = %s ORDER BY id LIMIT 15""", (product_id,))
        exclusions = cur.fetchall()
    product["heat_cover"] = _heat_label(heat)
    product["heat_items"] = heat.get("heat_items") or []
    return {"product": product, "coverages": coverages, "exclusions_top15": exclusions}
