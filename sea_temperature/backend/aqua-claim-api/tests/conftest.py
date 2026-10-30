import json
import os
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repo
from app.repository import MemoryRepository

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures"


def _targets():
    rows = json.loads((FX / "targets_all.json").read_text(encoding="utf-8"))
    for r in rows:
        r["start_date"] = date.fromisoformat(r["start_date"])
        r["end_date"] = date.fromisoformat(r["end_date"])
        r["total_premium"] = D(r["total_premium"])
        r["coverage_amount"] = D(r["coverage_amount"])
    return rows


@pytest.fixture(scope="session")
def repo():
    """TEST_DATABASE_URL 이 있으면 실제 PostgreSQL 저장소로, 없으면 메모리 저장소로 같은 테스트를 돌린다."""
    dsn = os.environ.get("TEST_DATABASE_URL")
    if dsn:
        from psycopg_pool import ConnectionPool
        from app.repository import PgRepository
        pool = ConnectionPool(dsn, min_size=1, max_size=2, open=True)
        yield PgRepository(pool)
        pool.close()
        return
    yield MemoryRepository(_targets(), json.loads((FX / "coverages_all.json").read_text(encoding="utf-8")),
                            str(ROOT / "data" / "applied_price_r7_r8.csv"),
                           str(ROOT / "data" / "applied_price_formula.csv"))


@pytest.fixture()
def client(repo):
    app.dependency_overrides[get_repo] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
