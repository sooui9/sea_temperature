import os
import threading
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.config import get_settings


def connect() -> psycopg.Connection:
    # Supabase transaction pooling does not support prepared statements.
    return psycopg.connect(
        **get_settings().connection_kwargs(), row_factory=dict_row, prepare_threshold=None,
    )


_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ConnectionPool:
    # Opening a new Supabase connection takes ~0.4s, so requests reuse pooled ones.
    # Created on first request so tests that override the dependencies never connect.
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    "", min_size=1, max_size=int(os.getenv("DB_POOL_MAX", "5")), open=True,
                    kwargs={**get_settings().connection_kwargs(), "row_factory": dict_row, "prepare_threshold": None},
                )
    return _pool


def get_db() -> Iterator[psycopg.Connection]:
    # One read-only transaction per request; commit/rollback on all exit paths.
    with _get_pool().connection() as conn:
        # Transaction-local settings also work when a pooler reuses server sessions and
        # never leak to the next request that borrows this connection. One round trip.
        conn.execute(
            "SELECT set_config('transaction_read_only', 'on', true),"
            " set_config('TimeZone', 'Asia/Seoul', true), set_config('statement_timeout', %s, true)",
            (str(get_settings().db_statement_timeout_ms),),
        )
        yield conn


def get_customer_db() -> Iterator[psycopg.Connection]:
    """Commit a successful customer request, roll back any failed request."""
    with _get_pool().connection() as conn:
        conn.execute(
            "SELECT set_config('TimeZone', 'Asia/Seoul', true), set_config('statement_timeout', %s, true)",
            (str(get_settings().db_statement_timeout_ms),),
        )
        yield conn
