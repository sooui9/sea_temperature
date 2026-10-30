---
name: Backend and shared DB
description: Use for FastAPI backend code, SQL, DB schema or table questions, DB cleanup, and backend tests.
applyTo: "backend/**,**/*.sql"
---

# Backend and shared DB rules

The team shares one PostgreSQL server (`nifs_ocean`, see `LAN_SETUP.md`). A wrong query hits everyone's data.

## Access
- The browser never talks to the DB. HTML screens call the backend (`API_BASE`, default `http://127.0.0.1:8000`), and the backend runs SQL.
- Team accounts are read-only by default; write access is granted per account at creation. A 503 or permission error means missing grants: report it, do not work around it with another account.
- Schemas in use: `customer_service`, `insurance`, `gov24`, `public`. Check real table and column names with `information_schema` before writing SQL. Never guess.

## Changes to the shared DB
- No `CREATE`/`ALTER`/`DROP`/`TRUNCATE`, bulk `UPDATE`/`DELETE`, or grant changes from an agent. Write the SQL in a file, show it, and let the user hand it to the DB admin (schema owner `nifs_team2` or server admin).
- DB cleanup (finding unused tables) is a read-only job: list tables, compare with SQL used in code, and classify as "in use / planned / unused". Never drop anything. Tables created by other teammates follow team ownership rules.
- Seed SQL in `backend/database/` must be idempotent (re-running keeps existing IDs), like `02_abalone_species.sql`.

## Code
- Follow the existing module split: router and logic per feature (`customer_api.py`, `insurance.py`, `support.py`), schemas in `*_schemas.py`, settings only in `config.py`.
- Parameterized queries only. Keep `db_statement_timeout_ms` limits.
- Empty results are not failures: return an empty list and let the screen show "확인된 정보가 아직 없어요".

## Tests
- `py backend/run_tests.py` runs without DB. `--db` copies table definitions into a random temporary schema, uses fake customers, and rolls back. Never write tests that touch real customer rows.
- New DB tests: put them in `backend/backend/tests/integration/test_<feature>.py`, guard with `@unittest.skipUnless(os.getenv('RUN_CUSTOMER_DB_TESTS') == '1', ...)`, and reuse `support.customer_sandbox()` and `support.request()`.
- If you cannot reach the DB, say the DB tests were not run.
