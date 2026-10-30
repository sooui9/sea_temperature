from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import service
from .repository import PgRepository, Repository
from .schemas import EstimateRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        from psycopg_pool import ConnectionPool
        app.state.pool = ConnectionPool(dsn, min_size=1, max_size=int(os.environ.get("DB_POOL_MAX", "5")), open=True)
        app.state.repo = PgRepository(app.state.pool)
    yield
    if getattr(app.state, "pool", None):
        app.state.pool.close()


def _plain(o):
    """금액은 float 로 바꾸지 않는다: 정수 Decimal → int, 그 외 Decimal → str."""
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else str(o.normalize())
    if isinstance(o, (date,)):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    return o


def ok(obj) -> JSONResponse:
    return JSONResponse(content=_plain(obj))


app = FastAPI(title="양식보험 보험금·자기부담금 계산 API", version="0.1.0", lifespan=lifespan)


def get_repo(request: Request) -> Repository:
    repo = getattr(request.app.state, "repo", None)
    if repo is None:
        raise HTTPException(503, "DATABASE_URL 이 설정되지 않았습니다")
    return repo


@app.exception_handler(service.ServiceError)
async def _service_error(_: Request, exc: service.ServiceError):
    return JSONResponse(status_code=exc.status, content=_plain({"detail": exc.message, **exc.extra}))


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/households/{household_id}/insurance")
def household_insurance(household_id: int, repo: Repository = Depends(get_repo)):
    """어가의 계약·보험목적·가입금액·특약·자기부담비율·보험료(분납 일정) — 대시보드 초기 화면용."""
    return ok(service.household_overview(repo, household_id))


@app.post("/claims/estimate")
def estimate_claim(req: EstimateRequest, repo: Repository = Depends(get_repo)):
    """사고 시뮬레이션: 보장 여부 → 적용가격 조회 → 보험가액·손해액 → 자기부담금 → 지급 예상 보험금."""
    return ok(service.estimate(repo, req))


@app.get("/applied-prices")
def applied_price(product_id: int, species_id: int, region_no: str = Query(pattern=r"^\d+$"),
                  on_date: date = Query(...), weight_g: Decimal | None = None,
                  repo: Repository = Depends(get_repo)):
    """대시보드에서 적용가격만 따로 보여줄 때."""
    p = repo.find_price(product_id=product_id, species_id=species_id, region_no=region_no,
                        on_date=on_date, weight_g=weight_g, variant=None)
    if p is None:
        raise HTTPException(404, "해당 조건의 적용가격 공시가 없습니다")
    return ok(p)
