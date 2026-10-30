"""Dashboard API for sea_forecast.html, consult_home.html and farm_detail.html."""
from datetime import date
from functools import lru_cache
import io
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from psycopg import sql
from pydantic import BaseModel

from backend.routes import DB, router as api_router

router = APIRouter(prefix="/api/dashboard", tags=["대시보드"])

# Change in ECMWF daily max (°C) between its first and last day that counts as a 2-3 week trend.
TREND_THRESHOLD = 0.5
# om_region_bias rows with this basis borrowed the average of other regions instead of their own comparison.
SHARED_BIAS_BASIS = "7개 지역 평균"
_CHART_LOCK = Lock()


class NotReady(RuntimeError):
    """Required dashboard chart views have not been provisioned."""


def fetch(db, region: str, schema: str = "public") -> tuple[list[dict], list[dict]]:
    views = {}
    for name in ("dash_chart_yearly", "dash_chart_monthly"):
        identifier = sql.Identifier(schema, name)
        if db.execute("SELECT to_regclass(%s) AS rel", (identifier.as_string(),)).fetchone()["rel"] is None:
            raise NotReady("그래프 집계 뷰가 없습니다. DB 관리자에게 확인해 주세요.")
        views[name] = identifier
    yearly = db.execute(sql.SQL("""
        SELECT year, years_ago, metric, value, low, high, kind
        FROM {} WHERE region = %s ORDER BY year, metric
    """).format(views["dash_chart_yearly"]), (region,)).fetchall()
    monthly = db.execute(sql.SQL("""
        SELECT to_char(month, 'YYYY-MM-DD') AS month, years_ago, metric,
               value::float AS value, low::float AS low, high::float AS high, kind
        FROM {} WHERE region = %s ORDER BY month, metric
    """).format(views["dash_chart_monthly"]), (region,)).fetchall()
    return yearly, monthly


@api_router.get("/dashboard/chart/{kind}.svg", tags=["대시보드"],
                response_class=Response, responses={200: {"content": {"image/svg+xml": {}}}})
def chart_svg(kind: Literal["yearly", "monthly"], db: DB,
              region: Annotated[str, Query(min_length=1, max_length=40)] = "전체",
              compact: bool = False,
              forecast: Annotated[bool, Query(description="false 면 예측 해·달을 빼고 실적만 그림 (상담 홈)")] = True):
    try:
        yearly, monthly = fetch(db, region)
    except NotReady as exc:
        raise HTTPException(503, str(exc)) from None
    rows = yearly if kind == "yearly" else monthly
    if not forecast:
        rows = actual_only(rows)
    if not rows:
        raise HTTPException(404, "해당 지역의 그래프 데이터가 없습니다.")
    # Matplotlib figures and font settings are shared across request threads.
    with _CHART_LOCK:
        try:
            # compact: 상담 홈 상단 카드용. 제목·범례·각주는 화면(HTML)이 그려서 그림에서는 빼요.
            fig = yearly_figure(rows, compact) if kind == "yearly" else monthly_figure(rows, compact)
            content = render(fig, "svg")
        except RuntimeError as exc:
            raise HTTPException(503, "그래프 생성 환경을 확인해 주세요.") from exc
    return Response(content=content, media_type="image/svg+xml")


class Point(BaseModel):
    i: int
    max: float
    mean: float
    min: float
    src: str


class Bias(BaseModel):
    diff: float
    own: bool


class Alert(BaseModel):
    type: str
    since: str


class Region(BaseModel):
    id: str
    trend: str
    bias: Bias | None
    alert: Alert | None
    series: list[Point]


class Regions(BaseModel):
    base_date: date
    regions: list[Region]


class Notification(BaseModel):
    id: int
    ty: Literal["apply", "join"]
    lbl: Literal["상담 예약", "가입 완료"]
    farm: str
    at: str
    text: str
    region: str | None = None
    owner_name: str | None = None
    read: bool = False


def farm_label(region: str | None, owner_name: str | None, household_id: int) -> str:
    """'통영 - 김○○'; falls back to whichever part exists, then to the household number."""
    return " - ".join(p for p in (region, owner_name) if p) or f"어가 {household_id}"


@router.get("/notifications", response_model=list[Notification],
            summary="최근 상담 예약·가입 완료 알림")
def notifications(db: DB):
    rows = db.execute("""
        SELECT l.log_id, l.household_id, l.result_status,
               l.contacted_at AT TIME ZONE 'Asia/Seoul' AS contacted_at,
               h.owner_name, regexp_replace(r.sigungu_name, '(시|군)$', '') AS region
        FROM customer_service.consult_logs l
        JOIN customer_service.fishery_households h ON h.household_id = l.household_id
        LEFT JOIN public.sigungu_area_coordinates r ON r.region_id = h.region_code
        WHERE l.result_status IN (%s, %s)
        ORDER BY l.contacted_at DESC, l.log_id DESC
        LIMIT 50
    """, ("상담 예약", "가입 완료")).fetchall()
    # SMS replies and official alerts need their own event source; consult logs cannot establish them.
    return [Notification(
        id=row["log_id"],
        ty="join" if row["result_status"] == "가입 완료" else "apply",
        lbl=row["result_status"], farm=str(row["household_id"]),
        at=row["contacted_at"].strftime("%m/%d %H:%M"),
        text=f'{farm_label(row["region"], row["owner_name"], row["household_id"])} · {row["result_status"]} 기록이 등록됐어요.',
        region=row["region"], owner_name=row["owner_name"],
    ) for row in rows]


class ScheduleItem(BaseModel):
    household_id: int
    date: str           # YYYY-MM-DD (한국 시간)
    time: str           # HH:MM
    status: str         # 상담 상태 (상담 예약 · 부재·재연락 ...)
    region: str | None = None
    owner_name: str | None = None
    label: str          # '통영 - 김○○'
    memo: str | None = None
    staff_name: str | None = None


@router.get("/schedule", response_model=list[ScheduleItem],
            summary="상단 캘린더: 한 달 동안의 다음 연락·상담 일정")
def schedule(db: DB, month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
                                                  description="YYYY-MM")]):
    # consult_cases.next_contact_at is the latest planned contact per household and season
    # (every consultation save overwrites it), so it is the schedule; the memo comes from the latest log.
    start = date.fromisoformat(f"{month}-01")
    end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    rows = db.execute("""
        SELECT c.household_id, c.status,
               c.next_contact_at AT TIME ZONE 'Asia/Seoul' AS at,
               h.owner_name, regexp_replace(r.sigungu_name, '(시|군)$', '') AS region,
               lg.memo, lg.staff_name
        FROM customer_service.consult_cases c
        JOIN customer_service.fishery_households h ON h.household_id = c.household_id
        LEFT JOIN public.sigungu_area_coordinates r ON r.region_id = h.region_code
        LEFT JOIN LATERAL (
            SELECT l.memo, l.staff_name FROM customer_service.consult_logs l
            WHERE l.case_id = c.case_id
            ORDER BY l.contacted_at DESC, l.log_id DESC LIMIT 1) lg ON true
        WHERE c.next_contact_at >= (%(start)s::timestamp AT TIME ZONE 'Asia/Seoul')
          AND c.next_contact_at <  (%(end)s::timestamp AT TIME ZONE 'Asia/Seoul')
        ORDER BY c.next_contact_at, c.household_id
    """, {"start": start, "end": end}).fetchall()
    return [ScheduleItem(
        household_id=row["household_id"], date=row["at"].strftime("%Y-%m-%d"), time=row["at"].strftime("%H:%M"),
        status=row["status"], region=row["region"], owner_name=row["owner_name"],
        label=farm_label(row["region"], row["owner_name"], row["household_id"]),
        memo=row["memo"], staff_name=row["staff_name"],
    ) for row in rows]


def trend_of(series: list[Point]) -> str:
    om = [p.max for p in series if p.src == "ECMWF"]
    if len(om) < 2:
        return "flat"
    change = om[-1] - om[0]
    if change >= TREND_THRESHOLD:
        return "up"
    if change <= -TREND_THRESHOLD:
        return "down"
    return "flat"


@router.get("/regions", response_model=Regions)
def regions(db: DB):
    rows = db.execute("""
        SELECT f.region, f.day_no - 1 AS i, f.max_c, f.mean_c, f.min_c,
               CASE WHEN f.source = 'ROMS' THEN 'ROMS' ELSE 'ECMWF' END AS src,
               b.bias, b.basis
        FROM public.forecast_21d f
        LEFT JOIN public.om_region_bias b ON b.region = f.region
        ORDER BY f.region, f.day_no
    """).fetchall()
    base_date = db.execute("SELECT (now() AT TIME ZONE 'Asia/Seoul')::date AS d").fetchone()["d"]

    by_region: dict[str, dict] = {}
    for r in rows:
        region = by_region.setdefault(r["region"], {"series": [], "bias": None})
        region["series"].append(Point(i=r["i"], max=r["max_c"], mean=r["mean_c"], min=r["min_c"], src=r["src"]))
        if r["bias"] is not None:
            # The view adds bias to raw ECMWF, so the screen's diff (ECMWF minus observed) is its negative.
            region["bias"] = Bias(diff=-r["bias"], own=r["basis"] != SHARED_BIAS_BASIS)

    return Regions(
        base_date=base_date,
        regions=[
            # No official NIFS alert data in the DB yet, so alert stays null.
            Region(id=name, trend=trend_of(v["series"]), bias=v["bias"], alert=None, series=v["series"])
            for name, v in by_region.items()
        ],
    )


METRICS = ("신청", "주의")

COLOR = {"신청": "#1f5ae0", "주의": "#a8500a"}
# 상담 홈 상단 카드(consult_home.html .ht-legend)와 같은 색
COMPACT_COLOR = {"신청": "#0f7c8c", "주의": "#c2620a"}
TEXT, SUB, MUTED = "#161a22", "#4b5363", "#6b7385"
GRID, BAND, AXIS = "#e8ecf1", "#f4f6f9", "#cdd3dd"
FONTS = ("Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", "AppleGothic", "NanumGothic", "Noto Sans CJK KR")


@lru_cache
def _mpl():
    try:
        import matplotlib
    except ImportError:
        raise RuntimeError("그래프 생성에 필요한 matplotlib 설치를 확인해 주세요.") from None
    matplotlib.use("Agg")
    from matplotlib import font_manager
    from matplotlib.figure import Figure

    installed = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in FONTS if f in installed), None)
    matplotlib.rcParams.update({"svg.fonttype": "none", "axes.unicode_minus": False, "font.size": 11, "legend.fontsize": 12, "legend.labelcolor": SUB})
    if font:
        matplotlib.rcParams["font.family"] = font
    return Figure


def _style(ax, *, hide_y: bool = False):
    ax.spines[["top", "right"] + (["left"] if hide_y else [])].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=11, length=0)
    ax.tick_params(axis="x", pad=8)
    ax.tick_params(axis="y", pad=6)
    if hide_y:
        ax.tick_params(left=False, labelleft=False)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def _nice_yaxis(ax, top: float):
    """Y axis from 0 with at most 4 readable steps (10 · 20 · 30 · 50 …) picked by matplotlib for this data.

    The 15% headroom keeps the value label above the tallest bar inside the chart.
    """
    from matplotlib.ticker import MaxNLocator
    ticks = [t for t in MaxNLocator(nbins=4, steps=[1, 2, 3, 5, 10], integer=True).tick_values(0, max(top, 1) * 1.15) if t >= 0]
    ax.set_ylim(0, ticks[-1])
    ax.set_yticks(ticks)


def _heads(ax, x_split: float, past_txt: str, fc_txt: str, compact: bool = False):
    left, right = ax.get_xlim()
    ax.axvspan(x_split, right, color=BAND, zorder=0, linewidth=0)
    ax.set_xlim(left, right)
    if compact:
        return
    kw = dict(xycoords=("data", "axes fraction"), xytext=(0, 6), textcoords="offset points",
              ha="center", va="bottom", fontsize=11, fontweight="bold", annotation_clip=False)
    ax.annotate(past_txt, ((left + x_split) / 2, 1), color=COLOR["신청"], **kw)
    ax.annotate(fc_txt, ((x_split + right) / 2, 1), color=MUTED, **kw)


def _header(fig, title: str, sub: str):
    t = fig.text(0.012, 0.975, title, color=TEXT, fontsize=16, fontweight="bold", va="top")
    fig.canvas.draw()
    bb = t.get_window_extent().transformed(fig.transFigure.inverted())
    fig.text(bb.x1 + 0.012, 0.968, sub, color=MUTED, fontsize=12, va="top")


def _legend(fig, items):
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=c, linewidth=lw, linestyle=ls) for _, c, ls, lw in items]
    fig.legend(handles, [n for n, *_ in items], loc="upper left", bbox_to_anchor=(0.006, 0.9), ncol=len(items),
               frameon=False, handlelength=1.8, columnspacing=1.6, fontsize=12)


def actual_only(rows: list[dict]) -> list[dict]:
    """예측 해·달을 뺀 실적 행만 (상담 홈 그래프는 예측 없이 보여 줌)"""
    return [r for r in rows if r.get("kind") != "예측"]


def yearly_figure(rows: list[dict], compact: bool = False):
    Figure = _mpl()
    C = COMPACT_COLOR if compact else COLOR
    rows = [r for r in rows if r.get("metric") in METRICS]
    years = sorted({int(r["year"]) for r in rows})
    fc_year = max((int(r["year"]) for r in rows if r["kind"] == "예측"), default=None)
    by = {(r["metric"], int(r["year"])): r for r in rows}

    # Compact card chart is flatter (8:2.0) so the home top cards don't leave empty space under the KPI rows.
    fig = Figure(figsize=(8, 2.0) if compact else (10, 5), dpi=100)
    ax = fig.subplots()
    w, top_all = 0.36, 0.0
    for k, mt in enumerate(METRICS):
        for i, y in enumerate(years):
            r = by.get((mt, y))
            if not r:
                continue
            v, is_fc = float(r["value"]), r["kind"] == "예측"
            pos = i + (k - 0.5) * w
            ax.bar(pos, v, w * 0.9, color="white" if is_fc else C[mt], edgecolor=C[mt],
                   linewidth=1.6, linestyle=(0, (4, 3)) if is_fc else "-", zorder=2)
            top = v
            lo, hi = r.get("low"), r.get("high")
            if is_fc and lo is not None and hi is not None and float(hi) > float(lo):
                ax.errorbar(pos, v, yerr=[[v - float(lo)], [float(hi) - v]], color=C[mt], capsize=5, linewidth=1.3, zorder=3)
                top = float(hi)
            ax.annotate(f"{round(v):,}", (pos, top), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", color=C[mt], fontsize=11, fontweight="bold", zorder=4)
            top_all = max(top_all, top)

    ax.set_xticks(range(len(years)), [f"{y}\n(예측)" if y == fc_year else str(y) for y in years])
    ax.set_xlim(-0.6, len(years) - 0.4)
    if compact:
        _nice_yaxis(ax, top_all)
        _style(ax, hide_y=True)
        ax.tick_params(axis="y", labelleft=True)
    else:
        ax.set_ylim(0, (top_all or 1) * 1.15)
        _style(ax, hide_y=True)
    if fc_year is not None:
        _heads(ax, years.index(fc_year) - 0.5, f"{years[0]}~{fc_year - 1} · 실적(가데이터)", "1년 후 · 예측 참고만", compact)

    if compact:
        fig.tight_layout(pad=0.4)
        return fig

    growth = []
    for mt in METRICS:
        cur, prev = by.get((mt, fc_year)), by.get((mt, (fc_year or 0) - 1))
        if cur and prev and float(prev["value"]):
            growth.append(f"{mt} {(float(cur['value']) / float(prev['value']) - 1) * 100:+.0f}%")
    _header(fig, "연도별 신청·주의 건수", f"{fc_year}년 예상 " + " · ".join(growth) if growth else "")
    _legend(fig, [("신청", COLOR["신청"], "-", 6), ("주의", COLOR["주의"], "-", 6)]
            + ([("예측 (점선 · 범위)", MUTED, (0, (4, 3)), 1.6)] if fc_year is not None else []))
    fig.text(0.012, 0.015, "※ 가데이터 기반 시연용 · 예측은 연간 증가율 기하평균, 막대 위 선 = 예상 범위. 신청·주의 판단 기준이 아닌 참고값이에요."
             if fc_year is not None else "※ 가데이터 기반 시연용 · 실적만 표시해요.", color=MUTED, fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.84))
    return fig


def monthly_figure(rows: list[dict], compact: bool = False):
    Figure = _mpl()
    C = COMPACT_COLOR if compact else COLOR
    rows = [r for r in rows if r.get("metric") in METRICS]
    labels = sorted({r["month"][:7] for r in rows})
    idx = {m: i for i, m in enumerate(labels)}

    fig = Figure(figsize=(8, 2.0) if compact else (11, 5), dpi=100)
    ax = fig.subplots()
    for mt in METRICS:
        r = sorted((x for x in rows if x["metric"] == mt), key=lambda x: x["month"])
        past = [x for x in r if x["kind"] != "예측"]
        fc = [x for x in r if x["kind"] == "예측"]
        ax.plot([idx[x["month"][:7]] for x in past], [float(x["value"]) for x in past],
                color=C[mt], linewidth=2.4, solid_joinstyle="round", solid_capstyle="round", zorder=3)
        if fc:
            head = past[-1:]
            ax.plot([idx[x["month"][:7]] for x in head + fc], [float(x["value"]) for x in head + fc],
                    color=C[mt], linewidth=2.4, linestyle=(0, (4, 3)), zorder=3)
            if all(x.get("low") is not None and x.get("high") is not None for x in fc):
                ax.fill_between([idx[x["month"][:7]] for x in fc], [float(x["low"]) for x in fc],
                                [float(x["high"]) for x in fc], color=C[mt], alpha=0.12, linewidth=0, zorder=2)

    ax.set_xticks(range(len(labels)), [m.replace("-", ".") if m.endswith(("-01", "-07")) else "" for m in labels])
    ax.set_xlim(-0.5, len(labels) - 0.5)
    if compact:
        values = [float(x[k]) for x in rows for k in ("value", "high") if x.get(k) is not None]
        _nice_yaxis(ax, max(values, default=0))
    else:
        ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}건")
    _style(ax)
    first_fc = min((idx[x["month"][:7]] for x in rows if x["kind"] == "예측"), default=None)
    if first_fc is not None:
        _heads(ax, first_fc - 0.5, "실적(가데이터)", "1년 후 · 예측 참고만", compact)
    if compact:
        fig.tight_layout(pad=0.4)
        return fig
    _header(fig, "월별 신청·주의 건수", f"{labels[0].replace('-', '.')} ~ {labels[-1].replace('-', '.')} · 전체 지역 합계" if labels else "")
    _legend(fig, [("신청", COLOR["신청"], "-", 3), ("주의", COLOR["주의"], "-", 3)]
            + ([("예측 (점선 · 범위)", MUTED, (0, (4, 3)), 2)] if first_fc is not None else []))
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    return fig


def render(fig, fmt: str = "svg") -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, transparent=True, **({"dpi": 200} if fmt == "png" else {}))
    return buf.getvalue()
