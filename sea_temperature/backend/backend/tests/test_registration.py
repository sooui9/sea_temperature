"""Registration contracts and SQL parameter checks without shared DB writes."""
from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from pydantic import ValidationError

from backend.customer_schemas import FarmInput
from backend.db import get_customer_db
from backend.main import app
from backend.tests.support import request


class RegistrationTest(TestCase):
    def setUp(self):
        self.farm_id = uuid4()
        self.input = {"region_id": 17, "species_ids": [35], "farming_method": "land_based",
                      "insurance_status": "insured", "high_temperature_coverage": "yes",
                      "total_premium_won": 10_000_001, "premium_payment_method": "twice",
                      "insurance_start_month": "2026-10-01"}
        self.old = {**self.input, "farm_id": self.farm_id, "customer_id": "test-customer",
                    "sigungu_name": "테스트시", "town_name": "테스트면"}

    def test_insurance_validation(self):
        self.assertEqual(FarmInput(**self.input).insurance_start_month, date(2026, 10, 1))
        for changes in ({"total_premium_won": -1}, {"total_premium_won": 1.5},
                        {"total_premium_won": True}, {"total_premium_won": 1_000_000_000_001},
                        {"insurance_start_month": "2026-10-02"},
                        {"high_temperature_coverage": "invalid"}, {"premium_payment_method": "invalid"},
                        {"insurance_status": "uninsured"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                FarmInput(**{**self.input, **changes})

    def test_existing_clients_can_omit_insurance_details(self):
        farm = FarmInput(region_id=17, species_ids=[35], farming_method="land_based", insurance_status="uninsured")
        self.assertIsNone(farm.total_premium_won)

    def test_insert_binds_all_details(self):
        from backend.customer_api import insert_farm

        database = Mock()
        database.execute.return_value.fetchone.return_value = {"farm_id": self.farm_id}
        with (patch("backend.customer_api.validate_selection", return_value={"sigungu_name": "테스트시", "area_name": "테스트면"}),
              patch("backend.customer_api.replace_species") as replace,
              patch("backend.customer_api.farm_row", return_value=self.old)):
            insert_farm(database, "test-customer", FarmInput(**self.input))
        query, params = database.execute.call_args.args
        self.assertIn("total_premium_won", query)
        self.assertEqual(params, ("test-customer", 17, "테스트시", "테스트면", "land_based", "insured",
                                  "yes", 10_000_001, "twice", date(2026, 10, 1)))
        replace.assert_called_once_with(database, self.farm_id, [35])

    def patch_farm(self, changes):
        database = Mock()

        def dependency():
            yield database

        app.dependency_overrides[get_customer_db] = dependency
        try:
            with (patch("backend.customer_api.current_customer", return_value={"customer_id": "test-customer"}),
                  patch("backend.customer_api.farm_row", return_value=self.old),
                  patch("backend.customer_api.validate_selection", return_value={"sigungu_name": "테스트시", "area_name": "테스트면"}),
                  patch("backend.customer_api.replace_species")):
                result = request("PATCH", f"/api/me/farms/{self.farm_id}", changes, headers={"X-CSRF-Protection": "1"})
            return result, database
        finally:
            app.dependency_overrides.clear()

    def test_uninsured_edit_clears_previous_insurance_details(self):
        (status, _, _), database = self.patch_farm({"insurance_status": "uninsured"})
        self.assertEqual(status, 200)
        _, params = database.execute.call_args.args
        self.assertEqual(params[4:9], ("uninsured", None, None, None, None))
        self.assertEqual(params[-2:], (self.farm_id, "test-customer"))

    def test_patch_rejects_incompatible_details_without_writing(self):
        (status, _, _), database = self.patch_farm({"insurance_status": "uninsured", "total_premium_won": 100})
        self.assertEqual(status, 422)
        database.execute.assert_not_called()

    def test_patch_can_clear_optional_details(self):
        (status, _, _), database = self.patch_farm({"total_premium_won": None, "insurance_start_month": None})
        self.assertEqual(status, 200)
        _, params = database.execute.call_args.args
        self.assertIsNone(params[6])
        self.assertIsNone(params[8])

    def test_patch_rejects_null_region(self):
        (status, _, _), database = self.patch_farm({"region_id": None})
        self.assertEqual(status, 422)
        database.execute.assert_not_called()

    def test_catalog_preserves_all_database_species(self):
        database = Mock()
        rows = [{"species_id": 1, "species_name": "조피볼락 (우럭)"},
                {"species_id": 35, "species_name": "전복(육상)"},
                {"species_id": 63, "species_name": "톳"}]
        database.execute.return_value.fetchall.return_value = rows

        def dependency():
            yield database

        app.dependency_overrides[get_customer_db] = dependency
        try:
            status, body, _ = request("GET", "/api/species")
            self.assertEqual(status, 200)
            self.assertEqual(body, rows)
        finally:
            app.dependency_overrides.clear()
