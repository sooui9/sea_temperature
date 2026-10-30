"""Shape tests for the dashboard forecast response (no DB needed)."""
import unittest

from backend.dashboard import build_regions


def day(region, d, max_c):
    return {"region": region, "day": d, "max_c": max_c, "mean_c": max_c - 0.6, "min_c": max_c - 1.1}


class BuildRegionsTest(unittest.TestCase):
    def setUp(self):
        self.roms = [day("통영", f"2026-10-{23 + i}", 20.0 + i * 0.1) for i in range(7)]
        self.om = [day("통영", f"2026-10-{30 + k}" if k < 2 else f"2026-11-{k - 1:02d}", 19.5 - k * 0.1)
                   for k in range(14)]

    def test_series_indexes_follow_screen_contract(self):
        data = build_regions("2026-10-23", self.roms, self.om, [])
        series = data["regions"][0]["series"]
        self.assertEqual([p["i"] for p in series], list(range(21)))
        self.assertEqual({p["src"] for p in series[:7]}, {"ROMS"})
        self.assertEqual({p["src"] for p in series[7:]}, {"ECMWF"})

    def test_bias_uses_latest_record_and_is_null_without_one(self):
        bias = [{"region": "통영", "offset_c": 1.4}, {"region": "통영", "offset_c": 0.2}]
        self.assertEqual(build_regions("2026-10-23", self.roms, self.om, bias)["regions"][0]["bias"],
                         {"diff": -1.4, "own": True})
        self.assertIsNone(build_regions("2026-10-23", self.roms, self.om, [])["regions"][0]["bias"])

    def test_trend_and_alert(self):
        region = build_regions("2026-10-23", self.roms, self.om, [])["regions"][0]
        self.assertEqual(region["trend"], "down")
        self.assertIsNone(region["alert"])

    def test_region_without_roms_is_left_out(self):
        self.assertEqual(build_regions("2026-10-23", [], self.om, [])["regions"], [])


if __name__ == "__main__":
    unittest.main()
