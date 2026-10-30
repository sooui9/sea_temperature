"""지원제도 조회 API (gov24 스키마: 정부24 공공서비스).

양식어가에 해당하는 서비스만 고른다: 해양수산부·경상남도·사용자 시·군이 소관이고,
서비스명/지원내용/지원대상에 양식·어업·수산 관련 단어가 있는 것. 양식·재해보험 관련을 앞에 둔다.
"""
import re
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.routes import DB

router = APIRouter(prefix="/api/v1/support", tags=["지원제도"])

FISHERY = "양식|어업인|어업|어가|수산|어촌|어장"
PRIORITY = "양식"
DISASTER = "재해|보험|고수온|저수온|적조|피해"


class SupportService(BaseModel):
    service_id: str
    name: str | None
    agency: str | None
    support_type: str | None
    purpose: str | None
    content: str | None
    target: str | None
    criteria: str | None
    how_to_apply: str | None
    deadline: str | None
    reception: str | None
    phone: str | None
    detail_url: str | None


def region_agency(region: str) -> str | None:
    """'창원시(진해구)' → '경상남도 창원시'. 앱의 지역은 경남 시·군."""
    name = re.sub(r"\(.*\)", "", region).strip()
    return f"경상남도 {name}" if name else None


@router.get("/services", response_model=list[SupportService])
def services(
    db: DB,
    region: Annotated[str | None, Query(max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
):
    agencies = ["해양수산부", "경상남도"]
    local = region_agency(region) if region else None
    if local:
        agencies.append(local)
    return db.execute("""
        SELECT "서비스ID" AS service_id, "서비스명" AS name, "소관기관명" AS agency,
               "지원유형" AS support_type, "서비스목적요약" AS purpose, "지원내용" AS content,
               "지원대상" AS target, "선정기준" AS criteria, "신청방법" AS how_to_apply,
               "신청기한" AS deadline, "접수기관" AS reception, "전화문의" AS phone,
               "상세조회URL" AS detail_url
        FROM gov24.gov24_service_list
        WHERE "소관기관명" = ANY(%(agencies)s)
          AND concat_ws(' ', "서비스명", "지원내용", "지원대상") ~ %(fishery)s
        ORDER BY (concat_ws(' ', "서비스명", "지원내용") ~ %(priority)s) DESC,
                 ("소관기관명" = %(local)s) DESC,
                 (concat_ws(' ', "서비스명", "지원내용") ~ %(disaster)s) DESC,
                 "서비스명"
        LIMIT %(limit)s
    """, {"agencies": agencies, "fishery": FISHERY, "priority": PRIORITY,
          "disaster": DISASTER, "local": local or "", "limit": limit}).fetchall()
