from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

Source = Literal["coo", "risa"]
RiskLevel = Literal["정보 없음", "정상", "관심", "주의", "경보"]
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int


class Station(BaseModel):
    station_id: int
    source: Source
    sta_cde: str
    sta_name: str
    sea_group: str | None
    latitude: float | None
    longitude: float | None
    start_date: date | None
    end_date: date | None
    is_active: bool | None
    sur_tmp_yn: bool | None
    mid_tmp_yn: bool | None
    bot_tmp_yn: bool | None
    sur_dep: float | None
    mid_dep: float | None
    bot_dep: float | None


class Sigungu(BaseModel):
    sigungu_name: str
    latitude: float | None
    longitude: float | None
    risa_station_id: int | None
    risa_km: float | None
    coo_station_id: int | None
    coo_km: float | None


class DailyTemp(BaseModel):
    station_id: int
    obs_date: date
    avg_temp: float | None
    max_temp: float | None


class CooDaily(BaseModel):
    station_id: int
    obs_date: date
    wtr_tmp: float | None
    qc_wtr: str | None
    qc: str | None


class RisaObservation(BaseModel):
    station_id: int
    obs_at: datetime
    obs_lay: int
    wtr_tmp: float | None
    repair_gbn: str | None
    rpr_yn: str | None


class CurrentStatus(BaseModel):
    sigungu_name: str
    station_name: str | None
    distance_km: float | None
    obs_datetime: datetime | None
    current_temp: float | None
    avg_7d: float | None
    diff_vs_7d: float | None
    streak_ge28: int
    risk_level: RiskLevel
    is_official: bool
    series_source: Source | None
    series_station: str | None


class TemperatureSummary(BaseModel):
    sigungu_name: str
    station_name: str | None
    current_temp: float | None
    risk_level: RiskLevel


class RecentTemp(BaseModel):
    sigungu_name: str
    obs_date: date
    avg_temp: float | None


class RedtideReport(BaseModel):
    cod_news: str
    report_date: date
    item2_raw: str | None
    nam_biology: str | None
    txt_seas: str | None
    min_density: float | None
    max_density: float | None
    min_watertemp: float | None
    max_watertemp: float | None
    min_salt: float | None
    max_salt: float | None
    txt_progress: str | None
    txt_breaking: str | None
    txt_afterview: str | None
    txt_request: str | None
    txt_reference: str | None
    lob_cdnate: str | None


class YearlyHotdays(BaseModel):
    station_id: int
    obs_year: int
    days_ge_25: int
    days_ge_28: int
    max_streak_28: int
    max_temp: float | None
    first_date_28: date | None
    missing_rate_jul_sep: float | None


class Climatology(BaseModel):
    station_id: int
    month_day: str
    clim_temp: float | None
