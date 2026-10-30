"""Ensure per-species identifiers reach the detail screen without a DB connection."""
import unittest
from unittest.mock import MagicMock

from backend.consult import contracts_by_household


class ConsultContractMappingTest(unittest.TestCase):
    def test_each_species_retains_its_mapping_identifier(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [
            {"household_id": 42, "mapping_id": 101, "species": "조피볼락", "coverage": "none"},
            {"household_id": 42, "mapping_id": 102, "species": "전복", "coverage": "covered"},
        ]
        contracts = contracts_by_household(db, [42])[42]
        self.assertEqual([c["mapping_id"] for c in contracts], [101, 102])
        self.assertEqual(contracts[1]["coverage"], "covered")

    def test_empty_species_returns_empty_mapping(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        self.assertEqual(contracts_by_household(db, []), {})


if __name__ == "__main__":
    unittest.main()
