"""n8n 워크플로우 브릿지: 화면·파이썬 → 백엔드 → n8n webhook.

화면(HTML)은 8000번 백엔드만 부르고, 이 파일이 n8n(기본 http://localhost:5678)을 대신 부른다.
n8n 워크플로우는 Active 로 켜 둬야 /webhook/... 주소가 열린다.

| 백엔드 주소 (/api/v1/n8n/...)   | n8n webhook                     | 워크플로우                                   |
|--------------------------------|---------------------------------|---------------------------------------------|
| POST /insurance-consult        | POST /webhook/insurance-consult | 2조 보험 상담 (AI 안내문)                       |
| POST /premium-calc             | POST /webhook/premium-calc      | 보험료 자동 계산 API                            |
| GET  /sst-forecast             | GET  /webhook/sst-forecast      | n8n-3 지역별 수온·위험도 API                    |
| GET  /gov-support              | GET  /webhook/gov-support       | 정부 지원사업 조회 API (AI 요약)                 |
| GET  /support-compare          | GET  /webhook/support-compare   | 보험 vs 정부 지원 비교 (AI)                     |
| POST /dash-forecast/refresh    | GET  /webhook/dash-forecast     | 대시보드 신청·주의 추이 + 1년 예측 (지금 다시 계산) |
| GET  /health                   | GET  /healthz                   | n8n이 켜져 있는지                               |


환경변수 (backend/backend/.env 에 적어도 됨, 모두 선택)
  N8N_BASE_URL        n8n 주소 (기본 http://localhost:5678)
  N8N_WEBHOOK_PREFIX  webhook (운영, 기본) / webhook-test (n8n 화면에서 'Listen for test event' 누른 동안만)
  N8N_WEBHOOK_KEY     n8n Webhook 노드에 Header Auth 를 걸었을 때 그 값 (헤더 X-N8N-Key 로 보냄)

파이썬에서 바로 (backend 폴더에서):
  python -m backend.n8n_bridge health
  python -m backend.n8n_bridge sst-forecast --region 통영 --species 조피볼락
  python -m backend.n8n_bridge premium-calc --species 굴 --region 통영 --premium 3000000 --installments 2
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/n8n", tags=["n8n 연결"])

# Same .env the rest of the backend reads; real environment variables win.
_ENV_FILE = Path(__file__).with_name(".env")


def _env(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    if _ENV_FILE.is_file():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip('"').strip("'")
    return default


class N8nError(Exception):
    """n8n 에 연결하지 못했거나 n8n 이 오류를 돌려줌"""

    def __init__(self, status: int, detail: Any):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# ---------------------------------------------------------------------------
# 공통 호출
# ---------------------------------------------------------------------------
def call(path: str, *, method: Literal["GET", "POST"] = "GET", params: dict | None = None,
         body: dict | None = None, timeout: float = 60) -> Any:
    """n8n webhook 하나를 불러 JSON 을 돌려준다. 실패하면 N8nError."""
    base = _env("N8N_BASE_URL", "http://localhost:5678").rstrip("/")
    prefix = _env("N8N_WEBHOOK_PREFIX", "webhook").strip("/")
    query = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    url = f"{base}/{prefix}/{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps({k: v for k, v in body.items() if v not in (None, "")}, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    key = _env("N8N_WEBHOOK_KEY")
    if key:
        headers["X-N8N-Key"] = key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except ValueError:
            detail = raw[:300] or f"n8n HTTP {exc.code}"
        if exc.code == 404 and (not isinstance(detail, dict) or "not registered" in str(detail.get("message", ""))):
            detail = (f"n8n webhook '{prefix}/{path}' 이 열려 있지 않아요. "
                      "n8n에서 그 워크플로우를 Active 로 켜 주세요.")
        elif isinstance(detail, dict):
            # n8n's own error pages carry a server stacktrace; never pass it on to the browser.
            detail.pop("stacktrace", None)
        raise N8nError(exc.code, detail) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
            raise N8nError(504, f"n8n 응답이 {int(timeout)}초 안에 오지 않았어요.") from None
        raise N8nError(503, f"n8n({base})에 연결하지 못했어요. n8n이 켜져 있는지 확인하세요.") from None
    if not raw.strip():
        return {"ok": True}
    try:
        return json.loads(raw)
    except ValueError:
        return {"ok": True, "text": raw}


def health() -> dict:
    base = _env("N8N_BASE_URL", "http://localhost:5678").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/healthz", timeout=5) as res:
            return {"ok": res.status == 200, "n8n": base}
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return {"ok": False, "n8n": base, "message": "n8n에 연결하지 못했어요. n8n이 켜져 있는지 확인하세요."}


# ---------------------------------------------------------------------------
# 워크플로우별 함수 (파이썬 코드에서 바로 써도 됨)
# ---------------------------------------------------------------------------
def insurance_consult(species: str, method: str | None = None) -> Any:
    """보험 상담 AI 안내문. 응답: {품목, 보험상품, answer}"""
    return call("insurance-consult", method="POST", body={"품목": species, "양식방식": method}, timeout=120)


def premium_calc(species: str, *, premium: int | None = None, sum_insured: int | None = None,
                 rate_pct: float | None = None, region: str | None = None, method: str | None = None,
                 installments: int | None = None, start_date: str | None = None,
                 local_pct: float | None = None) -> Any:
    """보험료 계산. 보험료(총액) 또는 가입금액+요율(%) 중 하나는 꼭 넣어야 함"""
    return call("premium-calc", method="POST", timeout=60, body={
        "species": species, "premium": premium, "sum_insured": sum_insured, "rate_pct": rate_pct,
        "region": region, "method": method, "installments": installments,
        "start_date": start_date, "local_pct": local_pct,
    })


def sst_forecast(region: str, species: str | None = None) -> Any:
    """지역 7일 수온·위험 단계 (지난 7일 포함)"""
    return call("sst-forecast", params={"region": region, "species": species}, timeout=30)


def gov_support(region: str | None = None, species: str | None = None) -> Any:
    """정부 지원사업 + AI 요약(answer, 실패하면 규칙 문장)"""
    return call("gov-support", params={"region": region, "species": species}, timeout=120)


def support_compare(region: str | None = None, species: str | None = None, method: str | None = None,
                    insured: Literal["가입", "미가입", "모름"] | None = None) -> Any:
    """보험 vs 정부 지원 비교 + AI 답변"""
    flag = {"가입": "y", "미가입": "n"}.get(insured or "", "")
    return call("support-compare", params={"region": region, "species": species, "method": method,
                                           "insured": flag}, timeout=120)


# The forecast refresh rewrites dash tables; refuse repeats so several staff clicking at once
# do not run it on top of each other.
_RUN_LOCK = threading.Lock()
_LAST_RUN: dict[str, float] = {}
DASH_COOLDOWN_SEC = 60


def _guarded(name: str, cooldown: float, fn) -> Any:
    with _RUN_LOCK:
        wait = _LAST_RUN[name] + cooldown - time.monotonic() if name in _LAST_RUN else 0
        if wait > 0:
            raise N8nError(409, f"방금 실행했어요. {int(wait // 60)}분 {int(wait % 60)}초 뒤에 다시 눌러 주세요.")
        _LAST_RUN[name] = time.monotonic()
    try:
        return fn()
    except N8nError:
        with _RUN_LOCK:
            _LAST_RUN.pop(name, None)   # failed to start, so allow a retry right away
        raise


def dash_forecast_refresh() -> Any:
    """신청·주의 예측을 지금 다시 계산해 DB에 저장하고 그래프 데이터를 돌려줌"""
    return _guarded("dash", DASH_COOLDOWN_SEC, lambda: call("dash-forecast", timeout=180))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _relay(fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except N8nError as exc:
        # n8n's own 400/404 bodies already explain the problem in Korean; pass them through.
        content = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        return JSONResponse(status_code=exc.status, content=content)


Region = Annotated[str, Query(min_length=1, max_length=30, description="통영 · 거제 · 고성 · 남해 · 하동 · 창원 · 사천")]
OptRegion = Annotated[str | None, Query(max_length=30)]
Species = Annotated[str | None, Query(max_length=50, description="조피볼락 · 굴 · 전복 …")]


class ConsultIn(BaseModel):
    species: str = Field(min_length=1, max_length=50, examples=["굴"])
    method: str | None = Field(default=None, max_length=20, examples=["가두리"])


class PremiumIn(BaseModel):
    species: str = Field(min_length=1, max_length=50, examples=["굴"])
    premium: int | None = Field(default=None, gt=0, description="총 보험료(원). 없으면 가입금액×요율", examples=[3000000])
    sum_insured: int | None = Field(default=None, gt=0, description="보험가입금액(원)")
    rate_pct: float | None = Field(default=None, gt=0, le=100, description="요율(%) — 수협 견적서")
    region: str | None = Field(default=None, max_length=30, examples=["통영"])
    method: str | None = Field(default=None, max_length=20)
    installments: Literal[1, 2, 4] | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2026-11-02"])
    local_pct: float | None = Field(default=None, ge=0, le=100, description="지자체 보조율(%) 직접 입력")


@router.get("/health", summary="n8n 연결 확인")
def n8n_health():
    return health()


@router.post("/insurance-consult", summary="보험 상담 AI 안내문")
def insurance_consult_api(body: ConsultIn):
    return _relay(insurance_consult, body.species, body.method)


@router.post("/premium-calc", summary="보험료 자동 계산")
def premium_calc_api(body: PremiumIn):
    if not body.premium and not (body.sum_insured and body.rate_pct):
        raise HTTPException(422, "보험료(총액)를 넣거나, 가입금액과 요율(%)을 함께 넣어 주세요.")
    return _relay(premium_calc, **body.model_dump())


@router.get("/sst-forecast", summary="지역 7일 수온·위험 단계")
def sst_forecast_api(region: Region, species: Species = None):
    return _relay(sst_forecast, region, species)


@router.get("/gov-support", summary="정부 지원사업 + AI 요약")
def gov_support_api(region: OptRegion = None, species: Species = None):
    return _relay(gov_support, region, species)


@router.get("/support-compare", summary="보험 vs 정부 지원 비교 (AI)")
def support_compare_api(region: OptRegion = None, species: Species = None,
                        method: Annotated[str | None, Query(max_length=20)] = None,
                        insured: Literal["가입", "미가입", "모름"] | None = None):
    return _relay(support_compare, region, species, method, insured)


@router.post("/dash-forecast/refresh", summary="신청·주의 예측 지금 다시 계산")
def dash_forecast_refresh_api():
    return _relay(dash_forecast_refresh)


# ---------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------
def main():
    import argparse

    ap = argparse.ArgumentParser(description="n8n 워크플로우를 파이썬에서 바로 부르기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    c = sub.add_parser("insurance-consult"); c.add_argument("--species", required=True); c.add_argument("--method")
    p = sub.add_parser("premium-calc")
    p.add_argument("--species", required=True); p.add_argument("--premium", type=int)
    p.add_argument("--sum-insured", type=int); p.add_argument("--rate-pct", type=float)
    p.add_argument("--region"); p.add_argument("--method"); p.add_argument("--installments", type=int, choices=[1, 2, 4])
    p.add_argument("--start-date"); p.add_argument("--local-pct", type=float)
    s = sub.add_parser("sst-forecast"); s.add_argument("--region", required=True); s.add_argument("--species")
    g = sub.add_parser("gov-support"); g.add_argument("--region"); g.add_argument("--species")
    v = sub.add_parser("support-compare"); v.add_argument("--region"); v.add_argument("--species")
    v.add_argument("--method"); v.add_argument("--insured", choices=["가입", "미가입", "모름"])
    sub.add_parser("dash-refresh")
    a = ap.parse_args()

    run = {
        "health": lambda: health(),
        "insurance-consult": lambda: insurance_consult(a.species, a.method),
        "premium-calc": lambda: premium_calc(a.species, premium=a.premium, sum_insured=a.sum_insured,
                                             rate_pct=a.rate_pct, region=a.region, method=a.method,
                                             installments=a.installments, start_date=a.start_date,
                                             local_pct=a.local_pct),
        "sst-forecast": lambda: sst_forecast(a.region, a.species),
        "gov-support": lambda: gov_support(a.region, a.species),
        "support-compare": lambda: support_compare(a.region, a.species, a.method, a.insured),
        "dash-refresh": dash_forecast_refresh,
    }[a.cmd]
    try:
        out = run()
    except N8nError as exc:
        sys.exit(f"[{exc.status}] {exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)}")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
