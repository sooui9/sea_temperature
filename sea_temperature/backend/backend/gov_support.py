"""정부지원금 · 고수온·저수온 피해 지원 API (Super DB 사용 안 함).

DB에 연결하지 않고 backend/backend/data/damage/ 의 CSV 4개만 읽는다.
  programs.csv : 고수온·저수온 피해 지원 제도 (재해복구비 · 긴급방류 · 상환연기 · 보증 …)
  prices.csv   : 해양수산부 「자연재난 복구비용 산정기준(단가)」 고시 품목별 복구 단가
                 → 여기에 없는 어종은 화면에 '정부 지원 품목 아님'
  relief.csv   : 피해율별 정책자금 상환연기
  sources.csv  : 출처 (정부 사이트 *.go.kr · gov.kr 링크만 내보냄)

  GET /api/v1/gov-support/damage?species=조피볼락&species=넙치

파이썬에서 바로 (backend 폴더에서):
  python -m backend.gov_support --species 조피볼락 --species 감성돔

단가·비율은 고시·규정 기준 참고값이다. 실제 지원 여부·금액은 시·군청 수산과와 수협 확인이 필요하다.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.insurance import species_terms

router = APIRouter(prefix="/api/v1/gov-support", tags=["정부지원금"])

HEAT = r"고수온|저수온|이상\s*수온"   # 이상수온 피해(고수온·저수온) 지원 제도만 남김
# 품종 별칭 (가두리 어류는 '어류'·'가두리'로도 찾음)
ALIAS = {"우럭": "조피볼락", "광어": "넙치", "우렁쉥이": "멍게", "참굴": "굴", "참전복": "전복"}
CAGE_FISH = {"조피볼락", "참돔", "돌돔", "감성돔", "농어", "점농어", "쥐치", "말쥐치", "숭어", "가숭어", "능성어", "방어", "넙치", "강도다리"}


def species_words(species: str | None) -> list[str]:
    """'조피볼락 (우럭)' → ['조피볼락', '우럭', '어류', '가두리']"""
    if not species:
        return []
    words = [ALIAS.get(t, t) for t in species_terms(species)]
    words += [t for t in species_terms(species) if t not in words]
    if any(w in CAGE_FISH for w in words):
        words += ["어류", "가두리"]
    return [w for w in dict.fromkeys(words) if w and w != "기타"]


# ---------------------------------------------------------------------------
# 고수온 피해 시 지원 (팀 자료 4개 표: 제도 · 복구 단가 · 상환연기 · 출처)
# DB는 보지 않고 backend/backend/data/damage/ 의 CSV 4개만 읽는다.
#   prices.csv : 해양수산부 「자연재난 복구비용 산정기준(단가)」 고시 품목 → 여기에 없는 어종은 '정부 지원 품목 아님'
# 제도는 고수온 관련 사후 지원·피해보상만 남기고, 링크는 정부 사이트(*.go.kr)만 내보낸다.
# ---------------------------------------------------------------------------
DAMAGE_TABLES = {
    "programs": ["제도ID", "제도명", "지원내용"],
    "prices": ["품목", "단가_원", "단위"],
    "relief": ["피해율_이상", "피해율_미만", "상환연기_년"],
    "sources": ["분류", "기관_자료명", "링크"],
}
# 단가 고시 (품목·단가의 출처)
PRICE_NOTICE = {"name": "해양수산부 「자연재난 복구비용 산정기준(단가)」 고시",
                "link": "https://www.mof.go.kr/doc/ko/selectDoc.do?docSeq=43104&menuSeq=885&bbsSeq=35"}
# 재해복구비 나누는 비율 · 어가당 한도. 근거 규정 별표 원문 대조 전이라 확인 필요로 표시
RECOVERY_SPLIT = {"grant": 50, "loan": 30, "self": 20, "cap": 50_000_000,
                  "source": "「자연재난 구호 및 복구 비용 부담기준 등에 관한 규정」 별표",
                  "link": "https://www.law.go.kr/LSW/lumLsLinkPop.do?lspttninfSeq=63234&chrClsCd=010202",
                  "confirmed": False}


def gov_url(url: Any) -> str | None:
    """정부 사이트(*.go.kr · 정부24 gov.kr · 정책브리핑 korea.kr) 링크만 통과. 기사·민간·연구원 사이트는 None"""
    m = re.match(r"^https?://([^/:?#]+)", str(url or "").strip(), re.I)
    return str(url).strip() if m and re.search(r"(^|\.)((go|gov)\.kr|korea\.kr)$", m.group(1).lower()) else None


class DamageProgram(BaseModel):
    id: str
    kind: str | None              # 지원금 · 대출 · 보증 · 참고
    name: str
    agency: str | None
    target: str | None
    content: str | None
    required: str | None
    apply_to: str | None
    when: str | None              # 앱표시시점 (경보·피해 후, 관심·주의보 …)
    status_2026: str | None
    to_check: list[str]           # 확인필요_항목
    link: str | None              # 정부 사이트 링크만 (없으면 null)
    basis: str | None
    checked: str | None


class UnitPrice(BaseModel):
    item: str
    size: str | None
    price: float | None           # 원
    unit: str | None
    raise_pct: str | None
    since: str | None
    note: str | None


class ReliefRule(BaseModel):
    min_rate: float               # 피해율 이상 (%)
    max_rate: float               # 피해율 미만 (%)
    years: float                  # 상환연기 (년)
    interest: str | None
    apply_to: str | None
    note: str | None


class DamageSource(BaseModel):
    kind: str | None
    name: str
    use: str | None
    link: str | None              # 정부 사이트 링크만
    read: str | None              # 내용_열람확인


class DamageSupport(BaseModel):
    programs: list[DamageProgram]
    prices: dict[str, list[UnitPrice]]   # 요청한 어종 → 맞는 단가 (없으면 빈 목록)
    supported: dict[str, bool]           # 요청한 어종 → 복구 단가 고시 품목인지
    items: list[str]                     # 지원 품목 이름 (단가가 있는 것)
    all_prices: list[UnitPrice]
    relief: list[ReliefRule]
    split: dict[str, Any]
    notice: dict[str, str]               # 단가 고시 이름 · 링크
    sources: list[DamageSource]
    missing: list[str]            # CSV가 없는 표 (programs · prices · relief · sources)


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _txt(v: Any) -> str | None:
    return str(v).strip() if v is not None and str(v).strip() not in ("", "-") else None


BOM = "\ufeff"   # 엑셀 UTF-8 CSV 맨 앞 숨은 문자 ('\ufeff제도ID')


def _key(name: str) -> str:
    return str(name).replace(BOM, "").strip()


DAMAGE_DIR = Path(__file__).resolve().parent / "data" / "damage"


def _csv_rows(key: str, missing: list[str]) -> list[dict]:
    """data/damage/{key}.csv (엑셀 UTF-8 BOM 있어도 됨). 없거나 칸 이름이 안 맞으면 missing 에 넣고 빈 목록"""
    path = DAMAGE_DIR / f"{key}.csv"
    rows: list[dict] = []
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [{_key(k): (v if v != "" else None) for k, v in row.items() if k is not None}
                    for row in csv.DictReader(f)]
        rows = [r for r in rows if any(v for v in r.values())]
    if not rows or not all(c in rows[0] for c in DAMAGE_TABLES[key]):
        missing.append(key)
        return []
    return rows


def _item_words(item: str) -> set[str]:
    """'조피볼락(우럭)' → {'조피볼락', '우럭'}"""
    return {ALIAS.get(w, w) for w in species_terms(item)} | set(species_terms(item))


def damage_support(species: list[str] | None = None) -> dict:
    missing: list[str] = []
    programs = []
    for r in _csv_rows("programs", missing):
        programs.append({
            "id": str(r.get("제도ID") or ""), "kind": _txt(r.get("구분")), "name": _txt(r.get("제도명")) or "(이름 없음)",
            "agency": _txt(r.get("운영기관")), "target": _txt(r.get("대상")), "content": _txt(r.get("지원내용")),
            "required": _txt(r.get("필수조건")), "apply_to": _txt(r.get("신청처")), "when": _txt(r.get("앱표시시점")),
            "status_2026": _txt(r.get("2026년_현황")),
            "to_check": [x.strip() for x in str(r.get("확인필요_항목") or "").split(";") if x.strip()],
            "link": gov_url(r.get("공식링크")), "basis": _txt(r.get("근거_법령고시")), "checked": _txt(r.get("확인일")),
        })
    # 이상수온(고수온·저수온)과 관련된 제도만 (대상·지원내용·2026년 현황 등에 그 말이 있는 것. '확인 필요' 칸은 보지 않음)
    programs = [x for x in programs if re.search(HEAT, " ".join(str(v) for v in x.values() if isinstance(v, str)))]
    order = {"지원금": 0, "대출": 1, "보증": 2}
    programs.sort(key=lambda x: (order.get(x["kind"] or "", 9), x["id"]))
    prices = [{"item": str(r.get("품목") or "").strip(), "size": _txt(r.get("규격")), "price": _num(r.get("단가_원")),
               "unit": _txt(r.get("단위")), "raise_pct": _txt(r.get("전년대비_인상률_퍼센트")),
               "since": _txt(r.get("시행일")), "note": _txt(r.get("비고"))}
              for r in _csv_rows("prices", missing)]
    relief = sorted(({"min_rate": _num(r.get("피해율_이상")) or 0, "max_rate": _num(r.get("피해율_미만")) or 0,
                      "years": _num(r.get("상환연기_년")) or 0, "interest": _txt(r.get("이자감면")),
                      "apply_to": _txt(r.get("신청처")), "note": _txt(r.get("비고"))}
                     for r in _csv_rows("relief", missing)), key=lambda x: x["min_rate"])
    sources = [{"kind": _txt(r.get("분류")), "name": _txt(r.get("기관_자료명")) or "", "use": _txt(r.get("용도")),
                "link": gov_url(r.get("링크")), "read": _txt(r.get("내용_열람확인"))}
               for r in _csv_rows("sources", missing)]
    sources = [x for x in sources if x["link"]]   # 정부 사이트가 아닌 출처(기사·연구원 등)는 빼기
    priced = [p for p in prices if p["price"] is not None]
    by_species = {}
    for sp in species or []:
        words = set(species_words(sp)) - {"어류", "가두리"}
        by_species[sp] = [p for p in priced if words & _item_words(p["item"])]
    return {"programs": programs, "prices": by_species,
            "supported": {sp: bool(v) for sp, v in by_species.items()},
            "items": list(dict.fromkeys(p["item"] for p in priced)),
            "all_prices": prices, "relief": relief, "split": RECOVERY_SPLIT, "notice": PRICE_NOTICE,
            "sources": sources, "missing": missing}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.get("/damage", response_model=DamageSupport)
def damage(species: Annotated[list[str] | None, Query(max_length=50, description="조피볼락 · 넙치 … (여러 번 가능)")] = None):
    """DB 연결 없이 CSV(복구 단가 고시 기준)만 읽음"""
    return damage_support(species[:10] if species else None)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="고수온·저수온 피해 시 정부 지원 (CSV, DB 안 씀)")
    ap.add_argument("damage", nargs="?", help="(예전 실행 방법 호환용, 생략 가능)")
    ap.add_argument("--species", action="append", help="어종 (여러 번 가능)")
    a = ap.parse_args()
    print(json.dumps(damage_support(a.species), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
