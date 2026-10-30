"""Shared ASGI requests and rollback-only customer database fixtures."""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
import json
from urllib.parse import urlsplit
from unittest.mock import patch
from uuid import uuid4

from psycopg import Connection

from backend.customer_security import LoginLimiter
from backend.db import connect, get_customer_db
from backend.main import app


def request(method, path, body=None, token=None, headers=None):
    """Exercise routing, validation, auth and serialization without starting a server."""
    async def invoke():
        response = []
        raw_headers = [(b"content-type", b"application/json")]
        raw_headers.extend((k.lower().encode(), v.encode()) for k, v in (headers or {}).items())
        if token:
            raw_headers.append((b"authorization", ("Bearer " + token).encode()))
        payload = json.dumps(body).encode() if body is not None else b""
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            response.append(message)

        target = urlsplit(path)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": target.path, "raw_path": target.path.encode(),
                 "query_string": target.query.encode(), "root_path": "", "headers": raw_headers,
                 "client": ("127.0.0.1", 12345), "server": ("testserver", 80)}
        await app(scope, receive, send)
        start = next(x for x in response if x["type"] == "http.response.start")
        content = b"".join(x.get("body", b"") for x in response if x["type"] == "http.response.body")
        return start["status"], json.loads(content) if content else None, dict(start["headers"])
    return asyncio.run(invoke())


class RewrittenConnection:
    """Route customer SQL to an isolated schema; don't use this in production."""
    def __init__(self, conn, schema):
        self.conn, self.schema = conn, schema

    def execute(self, query, params=None):
        query = query.replace("customer_service.", self.schema + ".")
        query = query.replace("public.sigungu_area_coordinates", self.schema + ".regions")
        return self.conn.execute(query, params)


@dataclass
class CustomerSandbox:
    connection: Connection
    schema: str
    region_ids: list[int]

    def farm_input(self, **changes):
        return {"region_id": self.region_ids[0], "farming_method": "cage",
                "insurance_status": "unknown", "species_ids": [1, 2], **changes}


def add_coordinate_fixtures(sandbox):
    """Synthetic coordinates, including equal area names in two different cities."""
    base = max(sandbox.region_ids) + 100
    rows = [
        {"region_id": base + 1, "sigungu_name": "테스트시 A", "area_name": "공통면", "latitude": 35.125, "longitude": 128.5},
        {"region_id": base + 2, "sigungu_name": "테스트시 A", "area_name": "다른리", "latitude": 35.25, "longitude": 128.625},
        {"region_id": base + 3, "sigungu_name": "테스트시 B", "area_name": "공통면", "latitude": 34.654321, "longitude": 127.123456},
    ]
    for row in rows:
        sandbox.connection.execute(f"""
            INSERT INTO {sandbox.schema}.regions
                (region_id,sigungu_name,area_name,latitude,longitude,coordinate_type)
            OVERRIDING SYSTEM VALUE VALUES (%s,%s,%s,%s,%s,%s)
        """, (row["region_id"], row["sigungu_name"], row["area_name"], row["latitude"], row["longitude"], "행정지명 대표점(테스트)"))
    return rows


@contextmanager
def customer_sandbox():
    """Clone definitions, isolate requests with savepoints, and roll everything back.

    Uses the configured DB account, but copies no real customers, passwords or
    tokens. Requires CREATE SCHEMA. Parallel processes get separate schemas;
    do not run this fixture concurrently in threads (FastAPI overrides are global).
    """
    schema = "customer_test_" + uuid4().hex
    with connect() as conn:
        try:
            with conn.transaction(force_rollback=True):
                conn.execute("SET LOCAL statement_timeout = '15s'")
                conn.execute(f"CREATE SCHEMA {schema}")
                for table in ("customers", "farms", "species", "farm_species", "guest_sessions"):
                    conn.execute(f"CREATE TABLE {schema}.{table} (LIKE customer_service.{table} INCLUDING ALL)")
                # The shared DB now uses a function/sequence for C-... IDs. Never
                # call that default in tests: PostgreSQL sequences don't roll back.
                id_type = conn.execute("SELECT data_type FROM information_schema.columns WHERE table_schema=%s AND table_name='customers' AND column_name='customer_id'", (schema,)).fetchone()["data_type"]
                if id_type == "text":
                    conn.execute(f"CREATE SEQUENCE {schema}.customer_id_seq")
                    conn.execute(f"ALTER TABLE {schema}.customers ALTER COLUMN customer_id SET DEFAULT ('C-' || lpad(nextval('{schema}.customer_id_seq')::text, 6, '0'))")
                conn.execute(f"CREATE TABLE {schema}.regions (LIKE public.sigungu_area_coordinates INCLUDING ALL)")
                # LIKE does not copy foreign keys: restore all customer relations explicitly.
                for table, column, parent, parent_column, cascade in (
                    ("farms", "customer_id", "customers", "customer_id", True),
                    ("farms", "region_id", "regions", "region_id", False),
                    ("farm_species", "farm_id", "farms", "farm_id", True),
                    ("farm_species", "species_id", "species", "species_id", False),
                    ("guest_sessions", "customer_id", "customers", "customer_id", True),
                ):
                    suffix = " ON DELETE CASCADE" if cascade else ""
                    conn.execute(f"ALTER TABLE {schema}.{table} ADD FOREIGN KEY ({column}) "
                                 f"REFERENCES {schema}.{parent}({parent_column}){suffix}")
                conn.execute(f"INSERT INTO {schema}.regions OVERRIDING SYSTEM VALUE "
                             "SELECT * FROM public.sigungu_area_coordinates ORDER BY region_id LIMIT 2")
                conn.execute(f"INSERT INTO {schema}.species (species_name) VALUES ('test fish'), ('test shellfish')")
                region_ids = [r["region_id"] for r in conn.execute(f"SELECT region_id FROM {schema}.regions ORDER BY region_id").fetchall()]
                if not region_ids:
                    raise RuntimeError("Integration tests require at least one configured region.")
                proxy = RewrittenConnection(conn, schema)

                def database():
                    with conn.transaction():
                        yield proxy

                original_overrides = dict(app.dependency_overrides)
                app.dependency_overrides[get_customer_db] = database
                try:
                    with patch("backend.customer_api.login_limiter", LoginLimiter()):
                        yield CustomerSandbox(conn, schema, region_ids)
                finally:
                    app.dependency_overrides.clear()
                    app.dependency_overrides.update(original_overrides)
        finally:
            # Even if an assertion fails, confirm the outer rollback removed the schema.
            with conn.transaction(force_rollback=True):
                exists = conn.execute("SELECT to_regnamespace(%s) AS schema", (schema,)).fetchone()["schema"]
                if exists is not None:
                    raise RuntimeError("Test schema was not rolled back.")
