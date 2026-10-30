"""Notification routing and response tests without a database connection."""
from datetime import datetime
import unittest
from unittest.mock import MagicMock

from psycopg import OperationalError

from backend.db import get_db
from backend.main import app
from backend.tests.support import request


class DashboardNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()

        def read_db():
            yield self.db

        self.previous = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = read_db

    def tearDown(self):
        if self.previous is None:
            app.dependency_overrides.pop(get_db)
        else:
            app.dependency_overrides[get_db] = self.previous

    def test_no_records_returns_empty_list(self):
        self.db.execute.return_value.fetchall.return_value = []
        status, data, _ = request("GET", "/api/dashboard/notifications")
        self.assertEqual(status, 200)
        self.assertEqual(data, [])

    def test_records_match_bell_and_household_link(self):
        self.db.execute.return_value.fetchall.return_value = [
            {"log_id": 12, "household_id": 42, "result_status": "가입 완료",
             "contacted_at": datetime(2026, 10, 26, 10, 30)},
            {"log_id": 11, "household_id": 43, "result_status": "상담 예약",
             "contacted_at": datetime(2026, 10, 25, 9, 5)},
        ]
        status, data, _ = request("GET", "/api/dashboard/notifications")
        self.assertEqual(status, 200)
        self.assertEqual([n["ty"] for n in data], ["join", "apply"])
        self.assertEqual(data[0]["farm"], "42")
        self.assertEqual(data[0]["id"], 12)
        self.assertEqual(data[0]["lbl"], "가입 완료")
        self.assertEqual(data[1]["at"], "10/25 09:05")
        self.assertTrue(all(not n["read"] for n in data))
        self.assertNotIn("name", data[0])
        self.assertNotIn("phone", data[0])

    def test_database_failure_is_not_an_empty_success(self):
        self.db.execute.side_effect = OperationalError("test database unavailable")
        status, _, _ = request("GET", "/api/dashboard/notifications")
        self.assertEqual(status, 503)


if __name__ == "__main__":
    unittest.main()
