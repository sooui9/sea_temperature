---
name: Security
description: Security checklist for code that touches input, auth, data, network, files, or config.
applyTo: "**/*.py,**/*.js,**/*.html,**/*.sql,**/*.sh,**/*.ps1,**/*.json,**/*.toml,**/*.yml,**/*.yaml,**/*.env*,**/Dockerfile"
---

# Security checklist

Apply when writing or reviewing code that touches input, auth, data, network, files, or config.

## Secrets
- Secrets come from environment variables. This repo reads them through `backend/backend/config.py` (pydantic `SecretStr`) from `backend/backend/.env`. Document names in `.env.example` / `team.env.example` with empty or fake values only.
- Never put real values in code, tests, fixtures, comments, logs, error messages, screenshots, or chat messages. Each teammate uses their own DB account (`nifs_team1`, `nifs_team2`, ...); never copy someone else's.
- If a secret was exposed, tell the user to rotate it (change the DB password). Deleting the commit is not enough.

```python
# BAD
DB_PASSWORD = "team2pass!"

# GOOD (existing pattern)
db_password: SecretStr = SecretStr("")  # loaded from .env by pydantic-settings
```

## Input and data
- Validate type, length, and range at every trust boundary (HTTP, CLI, file, env, DB). Backend input goes through pydantic schemas; follow `customer_schemas.py`.
- Use parameterized queries only (`psycopg` `%s` placeholders, `psycopg.sql` for identifiers). Never build SQL, shell, or paths by string concatenation.
- Avoid `eval`, `exec`, `shell=True`, and unsafe deserialization on untrusted data.
- Frontend: insert API or user text with `textContent` or escape it. Use `innerHTML` only with constant markup.
- Do not log personal data (name, birth date, phone number, farm address) or full request bodies.

## Personal data on the client
- `sessionStorage` key `farm` holds only farm conditions (region, species, method, insurance). Never store name, birth date, phone number, password, or tokens in `localStorage` or `sessionStorage`.
- Passwords are cleared from page memory after signup or navigation (existing behavior). Keep it that way.

## Auth and network
- Enforce authorization on the server for every protected action (see `customer_security.py`: hashed session tokens, CSRF header). Never trust client-side checks.
- A customer can read or change only their own farm. Tests in `integration/test_accounts.py` cover this; do not weaken them.
- CORS: explicit allowlist in `CORS_ORIGINS`. No `*` with credentials.
- Hash passwords with a standard algorithm. Never invent crypto.
- Error responses must not leak stack traces, SQL, or whether an account exists.
- Set `SESSION_COOKIE_SECURE=true` when served over HTTPS.

## Dependencies
- Prefer maintained, widely used packages. Pin versions (`requirements-lock.txt`).
- Run `pip-audit` before release if available; if not run, say so.
