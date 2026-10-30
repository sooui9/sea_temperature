from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from psycopg import Connection, sql

from backend.db import get_db
from backend.schemas import (
    Climatology, CooDaily, CurrentStatus, DailyTemp, Page, RecentTemp,
    RedtideReport, RisaObservation, Sigungu, Source, Station, YearlyHotdays,
)

router = APIRouter(prefix="/api/v1")
DB = Annotated[Connection, Depends(get_db)]
StationID = Annotated[int, Path(gt=0)]
Limit = Annotated[int, Query(ge=1, le=1000)]
Offset = Annotated[int, Query(ge=0)]


def date_range(
    start_date: date | None = None, end_date: date | None = None,
) -> tuple[date | None, date | None]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date는 end_date보다 늦을 수 없습니다.")
    return start_date, end_date


Dates = Annotated[tuple[date | None, date | None], Depends(date_range)]


def require_station(db: Connection, station_id: int, source: Source | None = None):
    station = db.execute(
        "SELECT * FROM stations WHERE station_id = %s", (station_id,)
    ).fetchone()
    if station is None or (source is not None and station["source"] != source):
        raise HTTPException(404, "해당 관측소가 없습니다.")
    return station


def require_sigungu(db: Connection, name: str):
    if db.execute("SELECT 1 FROM sigungu WHERE sigungu_name = %s", (name,)).fetchone() is None:
        raise HTTPException(404, "해당 시군이 없습니다.")


def page(db: Connection, query, params: list | tuple, limit: int, offset: int):
    return {
        "items": db.execute(query, (*params, limit, offset)).fetchall(),
        "limit": limit,
        "offset": offset,
    }


@router.get("/stations", response_model=Page[Station], tags=["관측소"])
def stations(db: DB, source: Source | None = None, limit: Limit = 100, offset: Offset = 0):
    where = " WHERE source = %s" if source else ""
    return page(db, "SELECT * FROM stations" + where + " ORDER BY station_id LIMIT %s OFFSET %s",
                [source] if source else [], limit, offset)


@router.get("/stations/{station_id}", response_model=Station, tags=["관측소"])
def station_detail(station_id: StationID, db: DB):
    return require_station(db, station_id)


def daily_rows(db, table, station_id, dates, limit, offset):
    # Table names come only from the two internal callers below.
    conditions = [sql.SQL("station_id = %s")]
    params = [station_id]
    for operator, value in zip((">=", "<="), dates):
        if value is not None:
            conditions.append(sql.SQL("obs_date {} %s").format(sql.SQL(operator)))
            params.append(value)
    query = sql.SQL("SELECT * FROM {} WHERE {} ORDER BY obs_date DESC LIMIT %s OFFSET %s").format(
        sql.Identifier(table), sql.SQL(" AND ").join(conditions)
    )
    return page(db, query, params, limit, offset)


@router.get("/stations/{station_id}/daily-temperatures", response_model=Page[DailyTemp], tags=["수온"])
def daily_temperatures(station_id: StationID, db: DB, dates: Dates, limit: Limit = 100, offset: Offset = 0):
    require_station(db, station_id)
    return daily_rows(db, "daily_temp", station_id, dates, limit, offset)


@router.get("/stations/{station_id}/coo-daily", response_model=Page[CooDaily], tags=["수온"])
def coo_daily(station_id: StationID, db: DB, dates: Dates, limit: Limit = 100, offset: Offset = 0):
    require_station(db, station_id, "coo")
    return daily_rows(db, "coo_daily_raw", station_id, dates, limit, offset)


@router.get("/stations/{station_id}/observations", response_model=Page[RisaObservation], tags=["수온"])
def observations(
    station_id: StationID, db: DB,
    start_at: datetime | None = None, end_at: datetime | None = None,
    obs_lay: Annotated[int | None, Query(ge=1, le=3)] = None,
    limit: Limit = 100, offset: Offset = 0,
):
    # Existing SQL stores TIMESTAMP without timezone: input/output use naive KST.
    if any(value is not None and value.tzinfo is not None for value in (start_at, end_at)):
        raise HTTPException(422, "시각은 시간대 표기 없이 한국시간으로 입력하세요.")
    if start_at and end_at and start_at > end_at:
        raise HTTPException(422, "start_at은 end_at보다 늦을 수 없습니다.")
    require_station(db, station_id, "risa")
    conditions, params = ["station_id = %s"], [station_id]
    for expression, value in (("obs_at >= %s", start_at), ("obs_at <= %s", end_at), ("obs_lay = %s", obs_lay)):
        if value is not None:
            conditions.append(expression)
            params.append(value)
    return page(db, "SELECT * FROM risa_observation WHERE " + " AND ".join(conditions)
                + " ORDER BY obs_at DESC, obs_lay LIMIT %s OFFSET %s", params, limit, offset)


@router.get("/sigungu", response_model=list[Sigungu], tags=["시군"])
def sigungu(db: DB):
    return db.execute("""
        SELECT s.*, m.risa_station_id, m.risa_km, m.coo_station_id, m.coo_km
        FROM sigungu s LEFT JOIN sigungu_station_map m USING (sigungu_name)
        ORDER BY s.sigungu_name
    """).fetchall()


@router.get("/screen3/current", response_model=list[CurrentStatus], tags=["시군 현황"])
def current(db: DB, sigungu_name: str | None = None):
    if sigungu_name is not None:
        require_sigungu(db, sigungu_name)
        return db.execute("SELECT * FROM screen3_current WHERE sigungu_name = %s", (sigungu_name,)).fetchall()
    return db.execute("SELECT * FROM screen3_current ORDER BY sigungu_name").fetchall()


@router.get("/screen3/recent7", response_model=list[RecentTemp], tags=["시군 현황"])
def recent7(db: DB, sigungu_name: str):
    require_sigungu(db, sigungu_name)
    # Anchor to the latest stored day, preserving missing calendar days as NULL.
    return db.execute("""
        WITH anchor AS (
            SELECT max(obs_date) AS last_date FROM screen3_recent7 WHERE sigungu_name = %s
        ), days AS (
            SELECT generate_series(last_date - 6, last_date, interval '1 day')::date AS obs_date
            FROM anchor
        )
        SELECT %s::text AS sigungu_name, days.obs_date, r.avg_temp
        FROM days LEFT JOIN screen3_recent7 r ON r.obs_date = days.obs_date AND r.sigungu_name = %s
        ORDER BY days.obs_date
    """, (sigungu_name, sigungu_name, sigungu_name)).fetchall()


@router.get("/redtide/latest", response_model=RedtideReport | None, tags=["적조"])
def latest_redtide(db: DB):
    return db.execute("SELECT * FROM redtide_report ORDER BY report_date DESC, cod_news DESC LIMIT 1").fetchone()


@router.get("/redtide/reports", response_model=Page[RedtideReport], tags=["적조"])
def redtide_reports(db: DB, dates: Dates, limit: Limit = 100, offset: Offset = 0):
    conditions, params = [], []
    for expression, value in zip(("report_date >= %s", "report_date <= %s"), dates):
        if value is not None:
            conditions.append(expression)
            params.append(value)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return page(db, "SELECT * FROM redtide_report" + where
                + " ORDER BY report_date DESC, cod_news DESC LIMIT %s OFFSET %s", params, limit, offset)


@router.get("/stations/{station_id}/yearly-hotdays", response_model=Page[YearlyHotdays], tags=["분석"])
def yearly_hotdays(
    station_id: StationID, db: DB,
    year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    limit: Limit = 100, offset: Offset = 0,
):
    require_station(db, station_id)
    where, params = "station_id = %s", [station_id]
    if year is not None:
        where += " AND obs_year = %s"
        params.append(year)
    return page(db, "SELECT * FROM yearly_hotdays WHERE " + where
                + " ORDER BY obs_year DESC LIMIT %s OFFSET %s", params, limit, offset)


@router.get("/stations/{station_id}/climatology", response_model=list[Climatology], tags=["분석"])
def climatology(station_id: StationID, db: DB):
    require_station(db, station_id)
    return db.execute("SELECT * FROM climatology_3y WHERE station_id = %s ORDER BY month_day", (station_id,)).fetchall()
