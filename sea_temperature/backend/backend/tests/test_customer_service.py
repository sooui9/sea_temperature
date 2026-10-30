"""Standard-library API tests; no httpx/pytest required.

RUN_CUSTOMER_DB_TESTS=1 enables a rollback-only PostgreSQL integration test.
It clones table definitions into a random, uncommitted schema, never edits
the real customer tables, and rolls back the test schema on exit.
"""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.customer_security import LoginLimiter, hash_password, verify_password
from backend.db import get_customer_db
from backend.main import app
from backend.tests.support import RewrittenConnection, customer_sandbox, request



class SecurityTest(unittest.TestCase):
    def test_password_hash_and_invalid_hashes(self):
        first = hash_password("a secure password")
        self.assertNotEqual(first, hash_password("a secure password"))
        self.assertTrue(verify_password("a secure password", first))
        self.assertFalse(verify_password("wrong password", first))
        for malformed in (None, "plaintext", "scrypt$v2$00$00", "scrypt$v1$gg$00"):
            self.assertFalse(verify_password("a secure password", malformed))

    def test_login_limiter(self):
        limiter = LoginLimiter()
        for _ in range(10):
            limiter.check("client")
        with self.assertRaises(Exception) as error:
            limiter.check("client")
        self.assertEqual(error.exception.status_code, 429)

    def test_validation_redacts_secrets_and_requires_csrf_header(self):
        def no_database():
            yield None
        app.dependency_overrides[get_customer_db] = no_database
        try:
            status, _, _ = request("POST", "/api/guest-registrations", {})
            self.assertEqual(status, 403)
            status, body, _ = request("POST", "/api/auth/signup", {
                "phone_number": "invalid", "password": "secret", "name": "", "birth_date": "2099-01-01"
            }, headers={"X-CSRF-Protection": "1"})
            self.assertEqual(status, 422)
            self.assertNotIn("secret", json.dumps(body))
            self.assertNotIn('"input"', json.dumps(body))
            status, _, _ = request("GET", "/api/me")
            self.assertEqual(status, 401)
        finally:
            app.dependency_overrides.clear()


@unittest.skipUnless(os.getenv("RUN_CUSTOMER_DB_TESTS") == "1", "Enable rollback-only DB integration explicitly")
class DatabaseFlowTest(unittest.TestCase):
    def test_guest_signup_login_ownership_and_rollback(self):
        with customer_sandbox() as sandbox:
            self.run_flow(sandbox.connection, sandbox.schema, sandbox.region_ids[0])

    def run_flow(self, conn, schema, region_id):
        data = {"region_id": region_id, "farming_method": "cage", "insurance_status": "unknown", "species_ids": [1, 2]}
        csrf = {"X-CSRF-Protection": "1"}
        self.assertEqual(request("GET", "/api/regions")[0], 200)
        self.assertEqual(len(request("GET", "/api/species")[1]), 2)
        status, _, _ = request("POST", "/api/guest-registrations", {**data, "species_ids": [999]}, headers=csrf)
        self.assertEqual(status, 422)
        self.assertEqual(conn.execute(f"SELECT count(*) AS n FROM {schema}.customers").fetchone()["n"], 0)
        status, guest, headers = request("POST", "/api/guest-registrations", data, headers=csrf)
        self.assertEqual(status, 201)
        token = guest["access_token"]
        self.assertIn(b"HttpOnly", headers[b"set-cookie"])
        self.assertIn(b"SameSite=lax", headers[b"set-cookie"])
        self.assertEqual(headers[b"cache-control"], b"no-store")
        self.assertEqual(request("GET", "/api/me", headers={"Cookie": "nifs_session=" + token})[0], 200)
        farm_id = guest["farm"]["farm_id"]
        status, _, _ = request("PATCH", "/api/me/farms/" + farm_id, {"insurance_status": "insured"},
                               headers={"Cookie": "nifs_session=" + token})
        self.assertEqual(status, 403)
        self.assertEqual(request("PATCH", "/api/me/farms/" + farm_id, {}, token)[0], 422)
        self.assertEqual(request("PATCH", "/api/me/farms/" + farm_id, {"region_id": None}, token)[0], 422)
        self.assertEqual(request("GET", "/api/me/farms", token=token)[1][0]["species_ids"], [1, 2])
        self.assertEqual(request("GET", "/api/me", token="g_" + "a" * 43)[0], 401)
        before = conn.execute(f"SELECT count(*) AS n FROM {schema}.customers").fetchone()["n"]
        original = RewrittenConnection.execute

        def fail_session(db, query, params=None):
            if "INSERT INTO customer_service.guest_sessions" in query:
                raise RuntimeError("test transaction failure")
            return original(db, query, params)

        with patch.object(RewrittenConnection, "execute", fail_session):
            with self.assertRaises(RuntimeError):
                request("POST", "/api/guest-registrations", data, headers=csrf)
        self.assertEqual(conn.execute(f"SELECT count(*) AS n FROM {schema}.customers").fetchone()["n"], before)
        _, other, _ = request("POST", "/api/guest-registrations", data, headers=csrf)
        for method, body in (("PATCH", {"insurance_status": "insured"}), ("DELETE", None)):
            self.assertEqual(request(method, "/api/me/farms/" + farm_id, body, other["access_token"])[0], 404)
        self.assertEqual(request("PATCH", "/api/me/farms/" + farm_id, {"species_ids": [999]}, token)[0], 422)
        status, updated, _ = request("PATCH", "/api/me/farms/" + farm_id, {"species_ids": [2], "insurance_status": "insured"}, token)
        self.assertEqual(status, 200)
        self.assertEqual(updated["species_ids"], [2])
        signup = {"name": "Test User", "birth_date": "1980-01-01", "phone_number": "010-1234-5678", "password": "example-password"}
        status, member, _ = request("POST", "/api/auth/signup", signup, token)
        self.assertEqual(status, 201)
        self.assertEqual(member["customer"]["customer_id"], guest["customer"]["customer_id"])
        self.assertNotIn("password_hash", member["customer"])
        self.assertEqual(request("GET", "/api/me", token=token)[0], 401)
        self.assertEqual(request("GET", "/api/me/farms", token=member["access_token"])[1][0]["farm_id"], farm_id)
        self.assertEqual(request("POST", "/api/auth/signup", signup, other["access_token"])[0], 409)
        self.assertEqual(request("GET", "/api/me", token=other["access_token"])[1]["membership_status"], "guest")
        self.assertEqual(request("POST", "/api/auth/login", {"phone_number": "01012345678", "password": "wrong-password"}, headers=csrf)[0], 401)
        status, logged_in, _ = request("POST", "/api/auth/login", {"phone_number": "01012345678", "password": "example-password"}, headers=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(request("POST", "/api/auth/logout", token=logged_in["access_token"])[0], 204)
        self.assertEqual(request("GET", "/api/me", token=logged_in["access_token"])[0], 401)
        self.assertEqual(request("DELETE", "/api/me/farms/" + farm_id, token=member["access_token"])[0], 204)
        self.assertEqual(conn.execute(f"SELECT count(*) AS n FROM {schema}.farm_species WHERE farm_id=%s", (farm_id,)).fetchone()["n"], 0)
        conn.execute(f"UPDATE {schema}.guest_sessions SET expires_at=CURRENT_TIMESTAMP + interval '1 second' WHERE token_hash IS NOT NULL")
        # Database clock is used for expiry; set created_at back first to satisfy its check.
        conn.execute(f"UPDATE {schema}.guest_sessions SET created_at=CURRENT_TIMESTAMP - interval '2 days', expires_at=CURRENT_TIMESTAMP - interval '1 day'")
        self.assertEqual(request("GET", "/api/me", token=other["access_token"])[0], 401)


if __name__ == "__main__":
    unittest.main()
