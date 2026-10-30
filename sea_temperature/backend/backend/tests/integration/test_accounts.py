"""Configured DB access and per-account data round trips."""
import os
import unittest

from backend.customer_security import token_hash, verify_password
from backend.db import connect
from backend.tests.support import customer_sandbox, request


DB_ENABLED = os.getenv("RUN_CUSTOMER_DB_TESTS") == "1"


@unittest.skipUnless(DB_ENABLED, "Run backend/run_tests.py --db to enable DB checks")
class ConfiguredConnectionTest(unittest.TestCase):
    def test_configured_database_account_has_required_customer_permissions(self):
        requirements = {
            "customer_service.customers": ("SELECT", "INSERT", "UPDATE"),
            "customer_service.farms": ("SELECT", "INSERT", "UPDATE", "DELETE"),
            "customer_service.farm_species": ("SELECT", "INSERT", "DELETE"),
            "customer_service.guest_sessions": ("SELECT", "INSERT", "UPDATE"),
            "customer_service.species": ("SELECT",),
            "public.sigungu_area_coordinates": ("SELECT",),
        }
        with connect() as conn:
            conn.read_only = True
            for schema in ("customer_service", "public"):
                self.assertTrue(conn.execute("SELECT has_schema_privilege(current_user, %s, 'USAGE') AS allowed",
                                             (schema,)).fetchone()["allowed"], f"Missing USAGE on {schema}")
            for table, privileges in requirements.items():
                for privilege in privileges:
                    with self.subTest(table=table, privilege=privilege):
                        row = conn.execute("SELECT has_table_privilege(current_user, %s, %s) AS allowed",
                                           (table, privilege)).fetchone()
                        self.assertTrue(row["allowed"], f"Missing {privilege} on {table}")

    def test_configured_database_account_can_read_required_columns(self):
        # No customer rows or credentials are printed or copied.
        with connect() as conn:
            conn.read_only = True
            self.assertEqual(conn.execute("SELECT 1 AS connected").fetchone()["connected"], 1)
            queries = {
                "customers": "SELECT customer_id, membership_status, name, birth_date, phone_number, password_hash FROM customer_service.customers LIMIT 0",
                "farms": "SELECT farm_id, customer_id, region_id, sigungu_name, town_name, farming_method, insurance_status FROM customer_service.farms LIMIT 0",
                "species": "SELECT species_id, species_name FROM customer_service.species LIMIT 0",
                "farm_species": "SELECT farm_id, species_id FROM customer_service.farm_species LIMIT 0",
                "guest_sessions": "SELECT customer_id, token_hash, expires_at, revoked_at FROM customer_service.guest_sessions LIMIT 0",
                "regions": "SELECT region_id, sigungu_name, area_name, latitude, longitude FROM public.sigungu_area_coordinates LIMIT 0",
            }
            for table, query in queries.items():
                with self.subTest(table=table):
                    self.assertEqual(conn.execute(query).fetchall(), [])


@unittest.skipUnless(DB_ENABLED, "Run backend/run_tests.py --db to enable DB checks")
class AccountDataTest(unittest.TestCase):
    def setUp(self):
        context = customer_sandbox()
        self.db = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def call(self, method, path, body=None, token=None, expected=200, headers=None):
        status, result, _ = request(method, path, body, token, headers)
        self.assertEqual(status, expected, f"{method} {path}: unexpected status {status}")
        return result

    def guest(self, **changes):
        return self.call("POST", "/api/guest-registrations", self.db.farm_input(**changes),
                         expected=201, headers={"X-CSRF-Protection": "1"})

    def member(self, phone="01012345678"):
        guest = self.guest()
        profile = {"name": "테스트 회원", "birth_date": "1985-03-15",
                   "phone_number": phone, "password": "test-account-password"}
        member = self.call("POST", "/api/auth/signup", profile, guest["access_token"], expected=201)
        return guest, member, profile

    def test_guest_registration_matches_database_and_api(self):
        guest = self.guest(insurance_status="uninsured")
        token = guest["access_token"]
        rows = self.call("GET", "/api/me/farms", token=token)
        self.assertEqual(rows, [guest["farm"]])
        stored = self.db.connection.execute(
            f"SELECT * FROM {self.db.schema}.farms WHERE farm_id=%s", (guest["farm"]["farm_id"],)
        ).fetchone()
        self.assertEqual(str(stored["customer_id"]), guest["customer"]["customer_id"])
        for field, expected in self.db.farm_input(insurance_status="uninsured").items():
            if field != "species_ids":
                self.assertEqual(stored[field], expected)
        region = self.db.connection.execute(
            f"SELECT * FROM {self.db.schema}.regions WHERE region_id=%s", (stored["region_id"],)
        ).fetchone()
        self.assertEqual(stored["sigungu_name"], region["sigungu_name"])
        self.assertEqual(stored["town_name"], region["area_name"])
        links = self.db.connection.execute(
            f"SELECT species_id FROM {self.db.schema}.farm_species WHERE farm_id=%s ORDER BY species_id",
            (stored["farm_id"],)
        ).fetchall()
        self.assertEqual([r["species_id"] for r in links], [1, 2])
        session = self.db.connection.execute(
            f"SELECT token_hash FROM {self.db.schema}.guest_sessions WHERE customer_id=%s",
            (stored["customer_id"],)
        ).fetchone()
        self.assertEqual(session["token_hash"], token_hash(token))
        self.assertNotEqual(session["token_hash"], token)

    def test_signup_keeps_farm_and_stores_member_profile(self):
        guest, member, profile = self.member("010-1234-5678")
        self.assertEqual(guest["customer"]["customer_id"], member["customer"]["customer_id"])
        customer = self.call("GET", "/api/me", token=member["access_token"])
        self.assertEqual(customer["membership_status"], "member")
        self.assertEqual(customer["name"], profile["name"])
        self.assertEqual(customer["birth_date"], profile["birth_date"])
        self.assertEqual(customer["phone_number"], "01012345678")
        self.assertNotIn("password_hash", customer)
        stored = self.db.connection.execute(
            f"SELECT password_hash, registered_at FROM {self.db.schema}.customers WHERE customer_id=%s",
            (customer["customer_id"],)
        ).fetchone()
        self.assertTrue(verify_password(profile["password"], stored["password_hash"]))
        self.assertIsNotNone(stored["registered_at"])
        self.assertEqual(self.call("GET", "/api/me/farms", token=member["access_token"]), [guest["farm"]])
        self.call("GET", "/api/me", token=guest["access_token"], expected=401)

    def test_relogin_returns_the_same_accounts_data(self):
        guest, member, profile = self.member()
        self.call("POST", "/api/auth/logout", token=member["access_token"], expected=204)
        logged_in = self.call("POST", "/api/auth/login", {
            "phone_number": profile["phone_number"], "password": profile["password"]
        }, headers={"X-CSRF-Protection": "1"})
        self.assertNotEqual(logged_in["access_token"], member["access_token"])
        self.assertEqual(logged_in["customer"]["customer_id"], guest["customer"]["customer_id"])
        self.assertEqual(self.call("GET", "/api/me/farms", token=logged_in["access_token"]), [guest["farm"]])

    def test_two_accounts_cannot_read_change_or_delete_each_others_data(self):
        guest_a, member_a, _ = self.member("01011112222")
        guest_b, member_b, _ = self.member("01033334444")
        for member, own_farm in ((member_a, guest_a["farm"]), (member_b, guest_b["farm"])):
            self.assertEqual(self.call("GET", "/api/me/farms", token=member["access_token"]), [own_farm])
        for owner, other_farm in ((member_a, guest_b["farm"]), (member_b, guest_a["farm"])):
            path = "/api/me/farms/" + other_farm["farm_id"]
            self.call("PATCH", path, {"insurance_status": "insured"}, owner["access_token"], expected=404)
            self.call("DELETE", path, token=owner["access_token"], expected=404)
        self.assertEqual(self.call("GET", "/api/me/farms", token=member_b["access_token"]), [guest_b["farm"]])

    def test_member_updates_are_reflected_in_database_and_next_read(self):
        guest, member, _ = self.member()
        changes = {"region_id": self.db.region_ids[-1], "species_ids": [2],
                   "farming_method": "land_based", "insurance_status": "insured"}
        updated = self.call("PATCH", "/api/me/farms/" + guest["farm"]["farm_id"], changes, member["access_token"])
        for field, value in changes.items():
            self.assertEqual(updated[field], value)
        self.assertEqual(self.call("GET", "/api/me/farms", token=member["access_token"]), [updated])
        stored = self.db.connection.execute(
            f"SELECT farming_method, insurance_status, region_id FROM {self.db.schema}.farms WHERE farm_id=%s",
            (updated["farm_id"],)
        ).fetchone()
        self.assertEqual(stored, {k: changes[k] for k in stored})

    def test_failed_write_does_not_change_saved_values(self):
        guest, member, _ = self.member()
        self.call("PATCH", "/api/me/farms/" + guest["farm"]["farm_id"], {
            "insurance_status": "insured", "species_ids": [999999]
        }, member["access_token"], expected=422)
        self.assertEqual(self.call("GET", "/api/me/farms", token=member["access_token"]), [guest["farm"]])


if __name__ == "__main__":
    unittest.main()
