"""Chart rendering and API contract checks without a database connection."""
from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

from fastapi import HTTPException

from backend.dashboard import chart_svg, fetch, NotReady
from backend.db import get_db
from backend.main import app
from backend.tests.support import request


class DashboardChartsTest(unittest.TestCase):
    def setUp(self):
        self.previous = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        self.yearly = [
            {"year": 2026, "metric": "신청", "value": 10, "kind": "실적"},
            {"year": 2027, "metric": "신청", "value": 12, "kind": "예측", "low": 11, "high": 13},
        ]
        self.monthly = [
            {"month": "2026-10-01", "metric": "신청", "value": 10, "kind": "실적"},
            {"month": "2027-10-01", "metric": "신청", "value": 12, "kind": "예측", "low": 11, "high": 13},
        ]

    def tearDown(self):
        if self.previous is None:
            app.dependency_overrides.pop(get_db)
        else:
            app.dependency_overrides[get_db] = self.previous

    def test_both_chart_kinds_render_svg(self):
        with patch("backend.dashboard.fetch", return_value=(self.yearly, self.monthly)):
            for kind in ("yearly", "monthly"):
                with self.subTest(kind=kind):
                    response = chart_svg(kind, MagicMock(), "전체")
                    self.assertEqual(response.media_type, "image/svg+xml")
                    root = ElementTree.fromstring(response.body)
                    self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")

    def test_route_is_registered_and_rejects_unknown_kind(self):
        self.assertIn("/api/v1/dashboard/chart/{kind}.svg", app.openapi()["paths"])
        status, _, _ = request("GET", "/api/v1/dashboard/chart/unknown.svg")
        self.assertEqual(status, 422)

    def test_empty_region_is_not_a_successful_chart(self):
        with patch("backend.dashboard.fetch", return_value=([], [])):
            with self.assertRaises(HTTPException) as raised:
                chart_svg("yearly", MagicMock(), "전체")
        self.assertEqual(raised.exception.status_code, 404)

    def test_missing_views_are_reported_as_unavailable(self):
        with patch("backend.dashboard.fetch", side_effect=NotReady("missing views")):
            with self.assertRaises(HTTPException) as raised:
                chart_svg("yearly", MagicMock(), "전체")
        self.assertEqual(raised.exception.status_code, 503)

    def test_missing_renderer_is_reported_as_unavailable(self):
        with patch("backend.dashboard.fetch", return_value=(self.yearly, self.monthly)), \
                patch("backend.dashboard.yearly_figure", side_effect=RuntimeError("missing renderer")):
            with self.assertRaises(HTTPException) as raised:
                chart_svg("yearly", MagicMock(), "전체")
        self.assertEqual(raised.exception.status_code, 503)

    def test_fetch_detects_missing_views(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {"rel": None}
        with self.assertRaises(NotReady):
            fetch(db, "전체")

    def test_cli_imports_shared_chart_functions(self):
        script = Path(__file__).resolve().parents[3] / "dash_chart.py"
        namespace = runpy.run_path(str(script))
        self.assertTrue(callable(namespace["yearly_figure"]))
        self.assertTrue(callable(namespace["monthly_figure"]))


if __name__ == "__main__":
    unittest.main()
