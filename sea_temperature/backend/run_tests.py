"""Run customer tests from any working directory without extra test packages."""
import argparse
import os
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser(description="고객 데이터 연동 테스트")
    parser.add_argument("--db", action="store_true", help="현재 설정된 DB에 연결해 롤백 통합 검사 실행")
    parser.add_argument("--suite", choices=("all", "accounts", "security", "species", "regions"), default="all")
    args = parser.parse_args()
    # Set before importing modules because unittest skip decorators run on import.
    os.environ["RUN_CUSTOMER_DB_TESTS"] = "1" if args.db else "0"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    if args.suite in ("all", "security"):
        suite.addTests(loader.loadTestsFromName("backend.tests.test_customer_service.SecurityTest"))
    if args.suite in ("all", "accounts"):
        suite.addTests(loader.discover(
            str(Path(__file__).resolve().parent / "backend" / "tests" / "integration"),
            pattern="test_*.py", top_level_dir=str(Path(__file__).resolve().parent)))
        suite.addTests(loader.loadTestsFromName("backend.tests.test_customer_service.DatabaseFlowTest"))
    if args.suite == "species":
        suite.addTests(loader.loadTestsFromName("backend.tests.integration.test_species_selection"))
    if args.suite == "regions":
        suite.addTests(loader.loadTestsFromName("backend.tests.integration.test_region_coordinates"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
