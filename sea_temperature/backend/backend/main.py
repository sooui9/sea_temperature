import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from psycopg import Connection, Error
from psycopg.errors import UniqueViolation

from backend.api import router as api_router
from backend.config import get_settings
from backend.db import get_db
from backend.insurance import router as insurance_router
from backend.support import router as support_router
from backend.routes import router
from backend.customer_api import router as customer_router
from backend.consult import router as consult_router
from backend.dashboard import router as dashboard_router
from backend.gov_support import router as gov_support_router
from backend.config import get_settings
from backend.dashboard import router as dashboard_router     # 다른 import 줄들 맨 아래                        # 다른 app.include_router 줄들 맨 아래
from backend.farm_detail import router as farm_detail_router
from backend.n8n_bridge import router as n8n_router

logger = logging.getLogger(__name__)
app = FastAPI(
    title="NIFS Ocean API",
    version="0.1.0",
    description="Streamlit에서 사용할 수온·적조 조회 API. 시각은 한국시간(Asia/Seoul)입니다.",
)
app.include_router(router)
app.include_router(api_router)
app.include_router(customer_router)
app.include_router(consult_router)
app.include_router(gov_support_router)
app.include_router(dashboard_router)
app.include_router(farm_detail_router)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "X-CSRF-Protection"])
# Screens ship 30-150KB of uncompressed HTML/JS; gzip cuts the transfer to roughly a quarter.
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # FastAPI's default errors echo submitted values, potentially including passwords.
    errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
              for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors}, headers={"Cache-Control": "no-store"})


@app.exception_handler(UniqueViolation)
async def duplicate_record(_request: Request, _exc: UniqueViolation):
    return JSONResponse(status_code=409, content={"detail": "이미 등록된 정보입니다."},
                        headers={"Cache-Control": "no-store"})


@app.exception_handler(Error)
async def database_error(_request: Request, exc: Error):
    # Do not expose SQL, connection details or credentials to clients/logs.
    logger.error("Database request failed (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "DB 연결 또는 스키마를 확인하세요."})


@app.get("/health/live", tags=["상태"])
def liveness():
    return {"status": "ok"}


@app.get("/health", tags=["상태"])
def health(db: Connection = Depends(get_db)):
    db.execute("SELECT 1").fetchone()
    return {"status": "connected"}


@app.get("/health/db", tags=["상태"])
def database_health(db: Connection = Depends(get_db)):
    db.execute("SELECT 1").fetchone()
    tables = (
        "stations", "sigungu", "sigungu_station_map", "coo_daily_raw",
        "risa_observation", "redtide_report", "daily_temp", "screen3_current",
        "screen3_recent7", "yearly_hotdays", "climatology_3y", "vw_redtide_latest",
    )
    missing = [name for name in tables if db.execute(
        "SELECT to_regclass(%s) AS relation", (name,)
    ).fetchone()["relation"] is None]
    if missing:
        return JSONResponse(status_code=503, content={"status": "schema_missing", "missing": missing})
    return {"status": "ok", "database": "connected", "schema": "ready"}
app.include_router(insurance_router)

app.include_router(n8n_router)

# --- 배포용: 화면 4개를 이 백엔드에서 같이 내보냄 (Render 등 한 주소로 실행) ---
# 폴더 전체를 공개하면 backend/backend/.env 까지 열리므로 파일만 골라서 지정합니다.
from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]   # sea_temperature/
SCREENS = ("consult_home.html", "consult_status.html", "farm_detail.html", "sea_forecast.html")
# 모든 화면이 함께 불러오는 공통 상단 바 · 왼쪽 메뉴 · 알림 (없으면 상단 바·사이드바가 안 그려져요)
# 형식(MIME)을 명시해야 브라우저가 스크립트를 실행하고 스타일을 적용해요.
SHARED = {
    "shell.js": "text/javascript; charset=utf-8",
    "shell.css": "text/css; charset=utf-8",
    "figma-theme.css": "text/css; charset=utf-8",
    "suhyup-logo.png": "image/png",
}


def _screen(path: Path, media_type: str | None = None):
    def serve():
        return FileResponse(path, media_type=media_type)
    return serve


for _name in SCREENS:
    app.add_api_route(f"/{_name}", _screen(ROOT / _name), include_in_schema=False)

for _name, _type in SHARED.items():
    app.add_api_route(f"/{_name}", _screen(ROOT / _name, _type), include_in_schema=False)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/consult_home.html")


app.mount("/out", StaticFiles(directory=ROOT / "out", check_dir=False), name="out")   # 상담 홈 예비 그래프