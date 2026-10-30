"""Public region list/detail queries against isolated PostgreSQL fixtures."""
import os
import unittest
from urllib.parse import urlencode

from backend.tests.support import add_coordinate_fixtures, customer_sandbox, request


@unittest.skipUnless(os.getenv("RUN_CUSTOMER_DB_TESTS") == "1", "Enable DB checks")
class RegionCoordinatesTest(unittest.TestCase):
    def setUp(self):
        context = customer_sandbox()
        self.db = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.rows = add_coordinate_fixtures(self.db)

    def test_city_filter_returns_only_its_areas_and_coordinates(self):
        query = urlencode({"sigungu_name": "테스트시 A"})
        status, rows, _ = request("GET", "/api/regions?" + query)
        self.assertEqual(status, 200)
        self.assertEqual({r["region_id"] for r in rows}, {r["region_id"] for r in self.rows[:2]})
        self.assertTrue(all(r["sigungu_name"] == "테스트시 A" for r in rows))
        self.assertTrue(all(isinstance(r["latitude"], float) and isinstance(r["longitude"], float) for r in rows))

    def test_selected_region_matches_stored_latitude_longitude_and_metadata(self):
        for expected in self.rows:
            with self.subTest(region_id=expected["region_id"]):
                status, row, _ = request("GET", f"/api/regions/{expected['region_id']}")
                self.assertEqual(status, 200)
                self.assertEqual(row["sigungu_name"], expected["sigungu_name"])
                self.assertEqual(row["area_name"], expected["area_name"])
                self.assertAlmostEqual(row["latitude"], expected["latitude"], places=6)
                self.assertAlmostEqual(row["longitude"], expected["longitude"], places=6)
                self.assertEqual(row["coordinate_type"], "행정지명 대표점(테스트)")
                self.assertIsNone(row["source_url"])

    def test_equal_area_names_in_different_cities_remain_distinct(self):
        first = request("GET", f"/api/regions/{self.rows[0]['region_id']}")[1]
        other = request("GET", f"/api/regions/{self.rows[2]['region_id']}")[1]
        self.assertEqual(first["area_name"], other["area_name"])
        self.assertNotEqual(first["sigungu_name"], other["sigungu_name"])
        self.assertNotEqual((first["latitude"], first["longitude"]), (other["latitude"], other["longitude"]))

    def test_invalid_missing_region_and_unknown_city(self):
        for value in ("0", "-1", "not-an-id"):
            with self.subTest(value=value):
                self.assertEqual(request("GET", "/api/regions/" + value)[0], 422)
        self.assertEqual(request("GET", "/api/regions/999999999")[0], 404)
        status, rows, _ = request("GET", "/api/regions?" + urlencode({"sigungu_name": "없는시"}))
        self.assertEqual(status, 200)
        self.assertEqual(rows, [])
