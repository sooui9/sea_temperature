"""Connection configuration and request lifecycle without remote credentials."""
from unittest.mock import MagicMock

import pytest

from backend.config import Settings
from backend import db


def settings(**values):
    # Explicit values prevent a developer's real .env from affecting tests.
    defaults = dict(database_url="", db_host="localhost", db_port=5432,
                    db_name="nifs_ocean", db_user="postgres", db_password="",
                    db_sslmode="prefer", db_connect_timeout=5,
                    db_statement_timeout_ms=15000)
    return Settings(_env_file=None, **(defaults | values))


def test_legacy_connection():
    params = settings(db_password="p@ss:word").connection_kwargs()
    assert params["host"] == "localhost"
    assert params["password"] == "p@ss:word"
    assert params["sslmode"] == "prefer"
    assert "options" not in params


def test_supabase_url_precedence_and_ssl():
    config = settings(database_url=(
        "postgresql://postgres.project:p%40ss%3Aword@pooler.example:6543/postgres"
    ), db_host="ignored", db_password="ignored", db_sslmode="disable")
    params = config.connection_kwargs()
    assert params["host"] == "pooler.example"
    assert params["port"] == "6543"
    assert params["dbname"] == "postgres"
    assert params["user"] == "postgres.project"
    assert params["password"] == "p@ss:word"
    assert params["sslmode"] == "require"
    assert params["connect_timeout"] == 5
    assert "p%40ss" not in repr(config)


def test_url_preserves_certificate_and_timeout():
    params = settings(database_url=(
        "postgresql://user:pw@db.example/postgres"
        "?sslmode=verify-full&sslrootcert=root.crt&connect_timeout=12"
    )).connection_kwargs()
    assert params["sslmode"] == "verify-full"
    assert params["sslrootcert"] == "root.crt"
    assert params["connect_timeout"] == "12"


def test_invalid_url_does_not_expose_secret():
    with pytest.raises(ValueError) as error:
        settings(database_url="postgresql://user:private-secret@host/db?invalid_option=1").connection_kwargs()
    assert "private-secret" not in str(error.value)


def test_pooler_disables_prepared_statements(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(db, "get_settings", lambda: settings())
    monkeypatch.setattr(db.psycopg, "connect", connect)
    db.connect()
    assert connect.call_args.kwargs["prepare_threshold"] is None


@pytest.mark.parametrize("fails", [False, True])
def test_request_transaction_settings_and_cleanup(monkeypatch, fails):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "connect", lambda: connection)
    monkeypatch.setattr(db, "get_settings", lambda: settings(db_statement_timeout_ms=2500))
    request = db.get_db()
    assert next(request) is connection
    assert connection.read_only is True
    assert connection.execute.call_args_list[0].args == (
        "SELECT set_config('TimeZone', 'Asia/Seoul', true)",
    )
    assert connection.execute.call_args_list[1].args[1] == ("2500",)
    if fails:
        with pytest.raises(RuntimeError):
            request.throw(RuntimeError("request failed"))
    else:
        with pytest.raises(StopIteration):
            next(request)
    connection.__exit__.assert_called_once()
