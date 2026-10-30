"""
우리 바다 안심도우미 - 대시보드 신청·주의 그래프를 파일(SVG·PNG)로 저장 (피그마·상담 홈 예비 그림용)

그래프 모양과 DB 조회는 backend/backend/dashboard.py 한 곳에만 있습니다. 이 파일은 그 함수를 불러 파일로 저장만 합니다.
상담 홈은 들어갈 때마다 백엔드(/api/v1/dashboard/chart/yearly.svg)에서 새로 그린 그래프를 받습니다.
백엔드가 꺼져 있으면 이 파일이 만든 out/ 그림을 대신 보여 줍니다.

결과 (기본 out/ 폴더)
  신청주의_연도별.svg / .png   신청·주의를 한 그래프에 (예측 해는 점선 빈 막대 + 예상 범위)
  신청주의_월별.svg / .png     월별 신청·주의 선 그래프
  - SVG는 피그마에 끌어다 놓으면 선·글자를 하나하나 고칠 수 있음 (글자가 글자로 남음)

실행 (sea_temperature 폴더에서)
  pip install matplotlib                       (나머지는 backend/backend/requirements.txt 그대로)
  python dash_chart.py                         DB에서 (옵션 없이 실행하면 --db 와 같음)
  python dash_chart.py --region 통영           지역별
  python dash_chart.py --schema 스키마명        dash 뷰가 public 이 아닐 때 (또는 환경변수 DASH_SCHEMA)
  python dash_chart.py --url http://localhost:5678/webhook/dash-forecast   n8n Webhook 응답에서
  python dash_chart.py --json 응답.json        저장해 둔 n8n 응답 파일에서 (DB 없이 시험용)
  python dash_chart.py --with-forecast         예측 해·달까지 (기본은 상담 홈처럼 실적만)
DB 접속은 팀 백엔드와 같습니다: backend/backend/.env 또는 환경변수 DATABASE_URL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # sea_temperature/
sys.path.insert(0, str(ROOT / "backend"))       # backend 패키지를 불러오기 위해

from backend.dashboard import NotReady, actual_only, fetch, monthly_figure, render, yearly_figure  # noqa: E402


def load(args) -> tuple[list[dict], list[dict]]:
    if args.url or args.json:
        if args.url:
            import requests

            r = requests.get(args.url, timeout=60)
            r.raise_for_status()
            data = r.json()
        else:
            data = json.loads(Path(args.json).read_text(encoding="utf-8"))
        # n8n 응답은 '전체' 기준. kind 가 '2년 전'처럼 와도 그래프는 '예측' 여부만 봄
        return data["chart_yearly"], data["chart"]

    import psycopg
    from backend.db import connect

    try:
        with connect() as conn:
            conn.read_only = True
            return fetch(conn, args.region, args.schema)
    except NotReady as exc:
        sys.exit(str(exc))
    except psycopg.Error as exc:
        # 접속 문자열·비밀번호가 화면에 찍히지 않도록 오류 종류만 보여 줌
        sys.exit(f"DB 연결 또는 조회 실패 ({type(exc).__name__}). backend/backend/.env 또는 DATABASE_URL을 확인하세요.")


def main():
    p = argparse.ArgumentParser(description="대시보드 그래프를 SVG·PNG로 저장 (옵션 없이 실행하면 DB에서)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--db", action="store_true", help="DB 뷰 dash_chart_yearly / dash_chart_monthly (기본)")
    src.add_argument("--url", help="n8n Webhook 주소")
    src.add_argument("--json", help="저장해 둔 n8n 응답 파일")
    p.add_argument("--region", default="전체", help="'전체'(기본) 또는 통영·거제·고성·남해·창원 …")
    p.add_argument("--schema", default=os.getenv("DASH_SCHEMA", "public"), help="dash 뷰가 있는 스키마 (기본 public)")
    p.add_argument("--out", default=str(ROOT / "out"), help="저장 폴더 (기본 sea_temperature/out — 상담 홈이 읽는 곳)")
    p.add_argument("--format", choices=["svg", "png", "both"], default="both")
    p.add_argument("--with-forecast", action="store_true", help="예측 해·달도 그림 (기본은 상담 홈처럼 실적만)")
    a = p.parse_args()

    yearly, monthly = load(a)
    if not a.with_forecast:   # 상담 홈 그래프는 예측 없이 실적만 보여 줌
        yearly, monthly = actual_only(yearly), actual_only(monthly)
    if not yearly:
        sys.exit(f"'{a.region}' 데이터가 없습니다. n8n '대시보드 신청·주의 예측'을 먼저 실행했는지, --region 값을 확인하세요.")
    try:
        charts = [("연도별", yearly_figure(yearly))] + ([("월별", monthly_figure(monthly))] if monthly else [])
    except RuntimeError as exc:
        sys.exit(str(exc))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if a.region == "전체" else f"_{a.region}"
    fmts = ["svg", "png"] if a.format == "both" else [a.format]
    for name, fig in charts:
        for fmt in fmts:
            path = out / f"신청주의_{name}{suffix}.{fmt}"
            path.write_bytes(render(fig, fmt))
            print("저장:", path)


if __name__ == "__main__":
    main()
