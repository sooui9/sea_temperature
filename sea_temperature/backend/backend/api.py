"""Public API paths agreed for the future Streamlit client."""
from typing import Annotated

from fastapi import APIRouter, Query

from backend.routes import (
    DB, Dates, Limit, Offset, page, recent7, redtide_reports, require_station, stations,
)
from backend.schemas import (
    RecentTemp, RedtideReport, Source, Station, TemperatureSummary, YearlyHotdays,
)

router = APIRouter(prefix="/api", tags=["기본 조회"])


@router.get("/stations", response_model=list[Station])
def station_list(db: DB, source: Source | None = None, limit: Limit = 100, offset: Offset = 0):
    return stations(db, source, limit, offset)["items"]


@router.get("/temperatures", response_model=list[TemperatureSummary])
def temperatures(db: DB):
    return db.execute("""
        SELECT sigungu_name, station_name, current_temp, risk_level
        FROM screen3_current ORDER BY sigungu_name
    """).fetchall()


@router.get("/temperatures/{region}/week", response_model=list[RecentTemp])
def temperature_week(region: str, db: DB):
    return recent7(db, region)


@router.get("/redtide", response_model=list[RedtideReport])
def redtide(db: DB, dates: Dates, limit: Limit = 100, offset: Offset = 0):
    return redtide_reports(db, dates, limit, offset)["items"]


@router.get("/hotdays", response_model=list[YearlyHotdays])
def hotdays(
    db: DB,
    station_id: Annotated[int | None, Query(gt=0)] = None,
    year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    limit: Limit = 100, offset: Offset = 0,
):
    conditions, params = [], []
    if station_id is not None:
        require_station(db, station_id)
        conditions.append("station_id = %s")
        params.append(station_id)
    if year is not None:
        conditions.append("obs_year = %s")
        params.append(year)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return page(db, "SELECT * FROM yearly_hotdays" + where
                + " ORDER BY obs_year DESC, station_id LIMIT %s OFFSET %s",
                params, limit, offset)["items"]
