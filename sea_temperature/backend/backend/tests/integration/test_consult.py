"""Consultation queries against the real schema: read-only on shared data, writes only in a rolled-back sandbox."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from uuid import uuid4

from psycopg import errors

from backend.consult import HEAT_EXCLUSION, HEAT_RIDER, list_customers, list_history, save_consultation
from backend.db import connect, get_customer_db, get_db
from backend.main import app
from backend.tests.support import request

DB_ENABLED = os.getenv("RUN_CUSTOMER_DB_TESTS") == "1"
SEASON = "2026-고수온"
TABLES = ("fish_species", "fishery_households", "household_species", "insurance_contracts", "insurance_targets",
          "contact_queue", "consult_cases", "consult_logs", "consult_log_items")


class RewrittenConnection:
    """Route consultation SQL to an isolated schema; don't use this in production."""
    def __init__(self, conn, schema):
        self.conn, self.schema = conn, schema

    def execute(self, query, params=None):
        query = query.replace("customer_service.", self.schema + ".")
        query = query.replace("public.sigungu_area_coordinates", self.schema + ".regions")
        query = query.replace("insurance.insurance_map", self.schema + ".insurance_map")
        return self.conn.execute(query, params)


@contextmanager
def consult_sandbox():
    """Clone table definitions plus reference rows (species, regions, product map); roll everything back.

    Fixture rows always pass explicit IDs: cloned serial defaults still point at the
    shared sequences, and sequences do not roll back.
    """
    schema = "consult_test_" + uuid4().hex
    with connect() as conn:
        try:
            with conn.transaction(force_rollback=True):
                conn.execute("SET LOCAL statement_timeout = '15s'")
                conn.execute(f"CREATE SCHEMA {schema}")
                for table in TABLES:
                    conn.execute(f"CREATE TABLE {schema}.{table} (LIKE customer_service.{table} INCLUDING ALL)")
                conn.execute(f"CREATE TABLE {schema}.regions (LIKE public.sigungu_area_coordinates INCLUDING ALL)")
                conn.execute(f"CREATE TABLE {schema}.insurance_map (LIKE insurance.insurance_map INCLUDING ALL)")
                # LIKE does not copy foreign keys: restore the ones the queries rely on.
                for table, columns, parent, parent_columns in (
                    ("household_species", "household_id", "fishery_households", "household_id"),
                    ("consult_cases", "household_id", "fishery_households", "household_id"),
                    ("consult_logs", "case_id, household_id", "consult_cases", "case_id, household_id"),
                    ("consult_log_items", "log_id", "consult_logs", "log_id"),
                    ("consult_log_items", "mapping_id", "household_species", "mapping_id"),
                ):
                    conn.execute(f"ALTER TABLE {schema}.{table} ADD FOREIGN KEY ({columns}) "
                                 f"REFERENCES {schema}.{parent}({parent_columns})")
                conn.execute(f"INSERT INTO {schema}.fish_species SELECT * FROM customer_service.fish_species")
                conn.execute(f"INSERT INTO {schema}.regions OVERRIDING SYSTEM VALUE "
                             "SELECT * FROM public.sigungu_area_coordinates")
                conn.execute(f"INSERT INTO {schema}.insurance_map SELECT * FROM insurance.insurance_map")
                yield RewrittenConnection(conn, schema)
        finally:
            with conn.transaction(force_rollback=True):
                if conn.execute("SELECT to_regnamespace(%s) AS s", (schema,)).fetchone()["s"] is not None:
                    raise RuntimeError("Test schema was not rolled back.")


def seed(db):
    """Three farms: 통영 two species (one no-rider contract), 거제 base-heat abalone, 고성 rider + expired contract."""
    s = db.schema
    for row in ((1, "어가1", "가상어업인1", 1, "해상가두리식", "T-1"), (2, "어가2", "가상어업인2", 4, "해상가두리식", "T-2"),
                (3, "어가3", "가상어업인3", 7, "해상가두리식", "T-3")):
        db.conn.execute(f"INSERT INTO {s}.fishery_households (household_id, household_name, owner_name, region_code, "
                        "fishery_type, license_number) VALUES (%s,%s,%s,%s,%s,%s)", row)
    for row in ((11, 1, 11, True), (12, 1, 13, False), (21, 2, 22, True), (31, 3, 11, True)):
        db.conn.execute(f"INSERT INTO {s}.household_species (mapping_id, household_id, species_id, is_primary) "
                        "VALUES (%s,%s,%s,%s)", row)
    for row in ((101, 1, 3, "유효"), (201, 2, 2, "유효"), (301, 3, 3, "유효"), (302, 3, 3, "만료")):
        db.conn.execute(f"INSERT INTO {s}.insurance_contracts (insurance_id, household_id, product_id, policy_number, "
                        "start_date, end_date, contract_status) VALUES (%s,%s,%s,%s,'2026-01-01','2026-12-31',%s)",
                        (row[0], row[1], row[2], f"P-{row[0]}", row[3]))
    for target_id, insurance_id, mapping_id, riders in ((1, 101, 11, []), (2, 201, 21, []),
                                                       (3, 301, 31, [HEAT_RIDER]), (4, 302, 31, [])):
        db.conn.execute(f"INSERT INTO {s}.insurance_targets (target_id, insurance_id, mapping_id, rider_details) "
                        "VALUES (%s,%s,%s,%s)", (target_id, insurance_id, mapping_id, json.dumps({"riders": riders})))
    db.conn.execute(f"UPDATE {s}.fishery_households SET phone_number = '01000001203', sms_consent = true, "
                    "sms_consent_at = now() WHERE household_id = 1")
    db.conn.execute(f"UPDATE {s}.fishery_households SET phone_number = '01000000727' WHERE household_id = 2")
    db.conn.execute(f"INSERT INTO {s}.contact_queue (base_date, household_id, rank, score, risk_stage, list_reason) "
                    "VALUES ('2026-10-21',1,2,50,1,'위험 단계'), ('2026-10-22',1,1,70,2,'위험 단계'), "
                    "('2026-10-22',2,2,40,1,'판매 마감')")


@unittest.skipUnless(DB_ENABLED, "Run backend/run_tests.py --db to enable DB checks")
class SharedSchemaReadTest(unittest.TestCase):
    def test_queries_run_read_only_on_shared_tables(self):
        with connect() as conn:
            conn.read_only = True
            customers = list_customers(conn, SEASON)
            history = list_history(conn)
        self.assertGreater(len(customers), 0)
        self.assertEqual(set(customers[0]), {"code", "name", "phone_masked", "sms_consent", "region", "contracts",
                                             "risk_stage", "status", "last_contact", "consult_count"})
        self.assertTrue(all(k["coverage"] in ("none", "no_rider", "covered") for c in customers for k in c["contracts"]))
        self.assertIsInstance(history, list)


@unittest.skipUnless(DB_ENABLED, "Run backend/run_tests.py --db to enable DB checks")
class ConsultFlowTest(unittest.TestCase):
    def test_customer_list_shape_and_derived_coverage(self):
        with consult_sandbox() as db:
            seed(db)
            rows = {c["code"]: c for c in list_customers(db, SEASON)}
        self.assertEqual(rows["1"]["phone_masked"], "010-****-1203")
        self.assertTrue(rows["1"]["sms_consent"])
        self.assertEqual(rows["1"]["region"], "통영")
        self.assertEqual(rows["1"]["risk_stage"], 2, "latest base_date wins")
        self.assertEqual([(k["species"], k["coverage"]) for k in rows["1"]["contracts"]],
                         [("조피볼락", "no_rider"), ("참돔", "none")])
        self.assertEqual(rows["2"]["contracts"][0]["coverage"], "covered", "base-heat product without exclusion")
        self.assertFalse(rows["2"]["sms_consent"])
        self.assertEqual(rows["3"]["contracts"][0]["coverage"], "covered", "heat rider on the valid contract")
        self.assertIsNone(rows["3"]["phone_masked"])
        self.assertFalse(rows["3"]["sms_consent"], "column default")
        self.assertIsNone(rows["3"]["risk_stage"], "farms n8n did not list have no stage")
        self.assertEqual({r["status"] for r in rows.values()}, {"미연락"})

    def test_heat_exclusion_rider_removes_base_coverage(self):
        with consult_sandbox() as db:
            seed(db)
            db.conn.execute(f"UPDATE {db.schema}.insurance_targets SET rider_details = %s WHERE target_id = 2",
                            (json.dumps({"riders": [HEAT_EXCLUSION]}),))
            rows = {c["code"]: c for c in list_customers(db, SEASON)}
        self.assertEqual(rows["2"]["contracts"][0]["coverage"], "no_rider")

    def test_saving_consultations_updates_case_and_appends_history(self):
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        with consult_sandbox() as db:
            seed(db)
            save_consultation(db, 1, SEASON, "부재·재연락", "전화", "부재", tomorrow, [])
            save_consultation(db, 1, SEASON, "상담 예약", "전화", "견적 요청", tomorrow,
                              [{"mapping_id": 11, "result": "안내"}])
            save_consultation(db, 2, SEASON, "가입 완료", "창구", None, None,
                              [{"mapping_id": 21, "result": "가입", "insurance_id": 201}])
            customers = {c["code"]: c for c in list_customers(db, SEASON)}
            history = list_history(db)
            only_first = list_history(db, 1)
            cases = db.conn.execute(f"SELECT count(*) AS n FROM {db.schema}.consult_cases").fetchone()["n"]
        self.assertEqual(cases, 2, "one case per household per season")
        self.assertEqual(customers["1"]["status"], "상담 예약")
        self.assertEqual(customers["1"]["consult_count"], 2)
        self.assertIsNotNone(customers["1"]["last_contact"])
        self.assertEqual(customers["2"]["status"], "가입 완료")
        self.assertEqual([h["result"] for h in history], ["가입 완료", "상담 예약", "부재·재연락"])
        self.assertEqual(history[0]["memo"], "–")
        self.assertEqual(history[1]["species"], ["조피볼락", "참돔"])
        self.assertEqual([h["code"] for h in only_first], ["1", "1"])

    def test_rejects_other_households_species_and_contracts(self):
        with consult_sandbox() as db:
            seed(db)
            with self.assertRaises(ValueError):
                save_consultation(db, 1, SEASON, "안내 완료", "전화", None, None, [{"mapping_id": 21, "result": "안내"}])
            with self.assertRaises(ValueError):
                save_consultation(db, 1, SEASON, "가입 완료", "전화", None, None,
                                  [{"mapping_id": 11, "result": "가입", "insurance_id": 201}])

    def test_booking_without_next_contact_is_rejected_by_schema(self):
        with consult_sandbox() as db:
            seed(db)
            with self.assertRaises(errors.CheckViolation):
                save_consultation(db, 1, SEASON, "상담 예약", "전화", None, None, [])


@contextmanager
def api_sandbox():
    """Route the consult API's read and write connections into the seeded sandbox."""
    with consult_sandbox() as db:
        seed(db)

        def database():
            yield db
        original = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_customer_db] = database
        try:
            yield db
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original)


@unittest.skipUnless(DB_ENABLED, "Run backend/run_tests.py --db to enable DB checks")
class ConsultApiTest(unittest.TestCase):
    CSRF = {"X-CSRF-Protection": "1"}

    def test_dashboard_reads_and_saves_through_http(self):
        body = {"household_id": 1, "status": "상담 예약", "channel": "전화", "memo": "견적 요청",
                "next_contact_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "items": [{"mapping_id": 11, "result": "안내"}]}
        with api_sandbox():
            status, customers, _ = request("GET", "/api/consult/customers")
            created, saved, _ = request("POST", "/api/consult/logs", body, headers=self.CSRF)
            _, history, _ = request("GET", "/api/consult/history?household_id=1")
            _, after, _ = request("GET", "/api/consult/customers")
        self.assertEqual(status, 200)
        self.assertEqual(len(customers), 3)
        self.assertEqual(created, 201)
        self.assertIn("log_id", saved)
        self.assertEqual([(h["result"], h["memo"]) for h in history], [("상담 예약", "견적 요청")])
        self.assertEqual({c["code"]: c["status"] for c in after}["1"], "상담 예약")

    def test_write_rules_are_enforced(self):
        with api_sandbox():
            no_csrf, _, _ = request("POST", "/api/consult/logs", {"household_id": 1, "status": "안내 완료", "channel": "전화"})
            no_date, _, _ = request("POST", "/api/consult/logs", {"household_id": 1, "status": "상담 예약", "channel": "전화"},
                                    headers=self.CSRF)
            foreign, detail, _ = request("POST", "/api/consult/logs",
                                         {"household_id": 1, "status": "안내 완료", "channel": "전화",
                                          "items": [{"mapping_id": 21, "result": "안내"}]}, headers=self.CSRF)
            missing, _, _ = request("POST", "/api/consult/logs", {"household_id": 999, "status": "안내 완료", "channel": "전화"},
                                    headers=self.CSRF)
        self.assertEqual(no_csrf, 403)
        self.assertEqual(no_date, 422)
        self.assertEqual((foreign, detail["detail"]), (422, "다른 어가의 어종이 포함되어 있습니다."))
        self.assertEqual(missing, 422)


if __name__ == "__main__":
    unittest.main()
