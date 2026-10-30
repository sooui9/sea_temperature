"""API integration tests against PostgreSQL, isolated in a random schema.

Set TEST_DATABASE_URL to a dedicated database whose name ends with _test.
No existing schema or rows are changed.
"""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
import pytest

from backend.db import get_db
from backend.main import app
from backend.team import create_team_user


@pytest.fixture(scope="module")
def database():
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not conninfo_to_dict(dsn).get("dbname", "").endswith("_test"):
        pytest.fail("Use a dedicated database with a name ending in _test")
    schema = "test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            schema_sql = (Path(__file__).resolve().parents[2] / "database" / "01_schema.sql").read_text(encoding="utf-8")
            conn.execute(schema_sql)
            # Re-running the bootstrap must preserve schema and data.
            conn.execute("""
                INSERT INTO stations (station_id, source, sta_cde, sta_name)
                VALUES (1, 'coo', 'C01', '연안 시험'), (2, 'risa', 'R01', '실시간 시험');
                INSERT INTO sigungu VALUES ('시험시', 34.8, 128.4), ('빈시', NULL, NULL);
                INSERT INTO sigungu_station_map VALUES ('시험시', 2, 1.25, 1, 2.50);
                INSERT INTO daily_temp VALUES (1, '2026-08-01', 27.12, 28.00), (1, '2026-08-02', NULL, NULL);
                INSERT INTO coo_daily_raw VALUES (1, '2026-08-01', 27.12, NULL, NULL);
                INSERT INTO risa_observation VALUES
                    (2, '2026-08-01 12:00:00', 1, 28.25, NULL, NULL),
                    (2, '2026-08-01 12:00:00', 2, 27.00, NULL, NULL);
                INSERT INTO screen3_current (sigungu_name, risk_level) VALUES ('시험시', '정보 없음');
                INSERT INTO screen3_recent7 VALUES
                    ('시험시', '2026-08-01', 27), ('시험시', '2026-08-07', 28);
                INSERT INTO redtide_report (cod_news, report_date, item2_raw) VALUES
                    ('old', '2026-08-01', NULL), ('new', '2026-08-07', '{unparsed}');
                INSERT INTO yearly_hotdays (station_id, obs_year) VALUES (1, 2026);
                INSERT INTO climatology_3y VALUES (1, '08-01', 26.5);
            """)
            conn.execute(schema_sql)
            yield dsn, schema
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def client(database):
    dsn, schema = database

    def test_db():
        with psycopg.connect(dsn, row_factory=dict_row, options=f"-c search_path={schema}") as conn:
            conn.read_only = True
            yield conn

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_docs_and_liveness_without_database():
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/openapi.json").status_code == 200


def test_db_errors_hide_details():
    def broken():
        raise psycopg.OperationalError("password=secret host=private")

    app.dependency_overrides[get_db] = broken
    try:
        with TestClient(app) as client:
            for path in ("/health", "/health/db", "/api/temperatures"):
                response = client.get(path)
                assert response.status_code == 503
                assert "secret" not in response.text
                assert "private" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_readiness(client):
    assert client.get("/health").json() == {"status": "connected"}
    assert client.get("/health/db").json()["schema"] == "ready"


def test_public_stations_and_temperatures(client):
    stations = client.get("/api/stations?source=coo&limit=1").json()
    assert len(stations) == 1
    assert stations[0]["station_id"] == 1
    assert client.get("/api/stations?offset=2").json() == []
    assert client.get("/api/stations?limit=1001").status_code == 422
    assert client.get("/api/temperatures").json() == [{
        "sigungu_name": "시험시", "station_name": None,
        "current_temp": None, "risk_level": "정보 없음",
    }]


def test_public_week(client):
    rows = client.get("/api/temperatures/시험시/week").json()
    assert len(rows) == 7
    assert rows[0]["avg_temp"] == 27
    assert rows[1]["avg_temp"] is None
    assert rows[-1]["obs_date"] == "2026-08-07"
    assert client.get("/api/temperatures/빈시/week").json() == []
    assert client.get("/api/temperatures/없는시/week").status_code == 404


def test_public_redtide(client):
    reports = client.get("/api/redtide?start_date=2026-08-07").json()
    assert len(reports) == 1
    assert reports[0]["cod_news"] == "new"
    assert client.get("/api/redtide?offset=2").json() == []
    assert client.get("/api/redtide?start_date=2026-08-07&end_date=2026-08-01").status_code == 422


def test_public_hotdays(client):
    rows = client.get("/api/hotdays").json()
    assert len(rows) == 1
    assert rows[0]["station_id"] == 1
    assert client.get("/api/hotdays?station_id=1&year=2026").json() == rows
    assert client.get("/api/hotdays?station_id=2").json() == []
    assert client.get("/api/hotdays?year=2025").json() == []
    assert client.get("/api/hotdays?offset=1").json() == []
    assert client.get("/api/hotdays?station_id=999").status_code == 404
    assert client.get("/api/hotdays?year=1800").status_code == 422


def test_station_filter_and_pagination(client):
    result = client.get("/api/v1/stations", params={"source": "risa", "limit": 1}).json()
    assert len(result["items"]) == 1
    assert result["items"][0]["station_id"] == 2
    assert client.get("/api/v1/stations?offset=2").json()["items"] == []
    assert client.get("/api/v1/stations/999").status_code == 404


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1", "source=other"])
def test_invalid_query(client, query):
    assert client.get("/api/v1/stations?" + query).status_code == 422


def test_dates_numbers_and_nulls(client):
    result = client.get("/api/v1/stations/1/daily-temperatures").json()["items"]
    assert result[0]["avg_temp"] is None
    assert result[1]["avg_temp"] == 27.12
    filtered = client.get("/api/v1/stations/1/daily-temperatures?end_date=2026-08-01").json()["items"]
    assert len(filtered) == 1
    assert client.get("/api/v1/stations/1/daily-temperatures?start_date=2026-08-02&end_date=2026-08-01").status_code == 422


def test_observation_layers_and_time(client):
    result = client.get("/api/v1/stations/2/observations?obs_lay=1&start_at=2026-08-01T12:00:00").json()["items"]
    assert len(result) == 1
    assert result[0]["wtr_tmp"] == 28.25
    assert client.get("/api/v1/stations/2/observations?obs_lay=4").status_code == 422
    assert client.get("/api/v1/stations/2/observations?start_at=2026-08-01T00:00:00Z").status_code == 422
    assert client.get("/api/v1/stations/1/observations").status_code == 404
    assert client.get("/api/v1/stations/2/coo-daily").status_code == 404
    assert len(client.get("/api/v1/stations/1/coo-daily").json()["items"]) == 1


def test_sigungu_mapping_and_missing_days(client):
    rows = client.get("/api/v1/sigungu").json()
    assert next(r for r in rows if r["sigungu_name"] == "시험시")["risa_station_id"] == 2
    assert next(r for r in rows if r["sigungu_name"] == "빈시")["risa_station_id"] is None
    recent = client.get("/api/v1/screen3/recent7", params={"sigungu_name": "시험시"}).json()
    assert len(recent) == 7
    assert recent[0]["obs_date"] == "2026-08-01"
    assert recent[1]["avg_temp"] is None
    assert client.get("/api/v1/screen3/recent7", params={"sigungu_name": "빈시"}).json() == []
    assert client.get("/api/v1/screen3/current", params={"sigungu_name": "시험시"}).json()[0]["risk_level"] == "정보 없음"
    assert client.get("/api/v1/screen3/current", params={"sigungu_name": "' OR 1=1 --"}).status_code == 404


def test_redtide_and_analysis(client):
    assert client.get("/api/v1/redtide/latest").json()["cod_news"] == "new"
    assert len(client.get("/api/v1/redtide/reports?start_date=2026-08-07").json()["items"]) == 1
    assert client.get("/api/v1/stations/1/yearly-hotdays?year=2026").json()["items"][0]["days_ge_28"] == 0
    assert client.get("/api/v1/stations/1/climatology").json()[0]["clim_temp"] == 26.5


def test_foreign_keys_and_readonly(database):
    dsn, schema = database
    with psycopg.connect(dsn, autocommit=True, options=f"-c search_path={schema}") as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("INSERT INTO daily_temp VALUES (9999, '2026-08-01', 20, 21)")
        conn.read_only = True
        with conn.transaction():
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                conn.execute("DELETE FROM stations")


@pytest.mark.parametrize("write_data", [False, True])
def test_team_user_permissions(database, write_data):
    dsn, schema = database
    username = 'nifs_test_' + uuid4().hex
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # Roll back roles, grants and test writes together; no accounts persist.
        with conn.transaction(force_rollback=True):
            create_team_user(conn, username, 'test-password-only-123', write_data=write_data, schema=schema)
            flags = conn.execute('SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = %s', (username,)).fetchone()
            assert not any(flags.values())
            assert conn.execute("SELECT has_schema_privilege(%s, %s, 'CREATE') AS allowed", (username, schema)).fetchone()['allowed'] is False
            with pytest.raises(ValueError, match='already exists'):
                create_team_user(conn, username, 'other-password-123', schema=schema)
            future = sql.Identifier(schema, 'future_team_table')
            conn.execute(sql.SQL('CREATE TABLE {} (id integer)').format(future))
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(username)))
            conn.execute(sql.SQL('SELECT * FROM {}').format(future)).fetchall()
            query = sql.SQL('INSERT INTO {} (station_id, obs_date, avg_temp) VALUES (1, %s, 25)').format(sql.Identifier(schema, 'daily_temp'))
            if write_data:
                conn.execute(query, ('2026-09-01',))
                conn.execute(sql.SQL('INSERT INTO {} VALUES (1)').format(future))
                conn.execute('SELECT nextval(%s)', (schema + '.stations_station_id_seq',))
            else:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(query, ('2026-09-01',))


def test_team_user_validation():
    with pytest.raises(ValueError, match='username'):
        create_team_user(None, 'postgres', 'long-enough-password')
    with pytest.raises(ValueError, match='12 characters'):
        create_team_user(None, 'nifs_team1', 'short')
