"""Species catalogue variants must be linked to each customer's farm."""
import os
import unittest

from backend.species_catalog import seed_abalone_species, seed_research_species
from backend.tests.support import RewrittenConnection, customer_sandbox, request


@unittest.skipUnless(os.getenv("RUN_CUSTOMER_DB_TESTS") == "1", "Enable DB checks")
class SpeciesSelectionTest(unittest.TestCase):
    def setUp(self):
        context = customer_sandbox()
        self.db = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.proxy = RewrittenConnection(self.db.connection, self.db.schema)
        seed_abalone_species(self.proxy)
        self.ids = {r["species_name"]: r["species_id"] for r in self.db.connection.execute(
            f"SELECT species_id,species_name FROM {self.db.schema}.species").fetchall()}

    def register(self, name, method):
        return request("POST", "/api/guest-registrations",
                       self.db.farm_input(species_ids=[self.ids[name]], farming_method=method),
                       headers={"X-CSRF-Protection": "1"})

    def linked_names(self, farm_id):
        rows = self.db.connection.execute(f"""
            SELECT s.species_name FROM {self.db.schema}.farm_species fs
            JOIN {self.db.schema}.species s USING(species_id)
            WHERE fs.farm_id=%s ORDER BY s.species_id
        """, (farm_id,)).fetchall()
        return [r["species_name"] for r in rows]

    def test_catalogue_seed_is_repeatable_and_preserves_ids(self):
        seed_abalone_species(self.proxy)
        after = {r["species_name"]: r["species_id"] for r in self.db.connection.execute(
            f"SELECT species_id,species_name FROM {self.db.schema}.species").fetchall()}
        self.assertEqual(after, self.ids)
        status, catalogue, _ = request("GET", "/api/species")
        self.assertEqual(status, 200)
        self.assertEqual({r["species_name"] for r in catalogue}, set(after))

    def test_research_species_are_preserved_in_catalogue_and_can_be_saved(self):
        expected = {"조피볼락 (우럭)", "볼락", "참돔", "돌돔", "감성돔", "점농어", "말쥐치", "참쥐치",
                    "가숭어", "능성어", "방어", "굴", "멍게", "미더덕", "오만둥이"}
        seed_research_species(self.proxy)
        status, catalogue, _ = request("GET", "/api/species")
        self.assertEqual(status, 200)
        ids = {r["species_name"]: r["species_id"] for r in catalogue}
        self.assertTrue(expected.issubset(ids))
        for name, species_id in self.ids.items():
            self.assertEqual(ids[name], species_id)
        seed_research_species(self.proxy)
        self.assertEqual({r["species_name"]: r["species_id"] for r in request("GET", "/api/species")[1]}, ids)
        for name in sorted(expected):
            with self.subTest(species=name):
                status, guest, _ = request("POST", "/api/guest-registrations",
                    self.db.farm_input(species_ids=[ids[name]]), headers={"X-CSRF-Protection": "1"})
                self.assertEqual(status, 201)
                self.assertEqual(self.linked_names(guest["farm"]["farm_id"]), [name])

    def test_land_and_sea_have_distinct_ids_and_correct_farm_links(self):
        self.assertNotEqual(self.ids["전복(육상)"], self.ids["전복(해상)"])
        for name, method in (("전복(육상)", "land_based"), ("전복(해상)", "cage")):
            with self.subTest(name=name):
                status, guest, _ = self.register(name, method)
                self.assertEqual(status, 201)
                self.assertEqual(guest["farm"]["species_ids"], [self.ids[name]])
                self.assertEqual(self.linked_names(guest["farm"]["farm_id"]), [name])
                status, farms, _ = request("GET", "/api/me/farms", token=guest["access_token"])
                self.assertEqual(status, 200)
                self.assertEqual(farms, [guest["farm"]])

    def test_generic_abalone_and_inconsistent_method_are_rejected(self):
        generic = self.db.connection.execute(f"INSERT INTO {self.db.schema}.species (species_name) VALUES ('전복') RETURNING species_id").fetchone()["species_id"]
        for ids, method in (([generic], "cage"), ([self.ids["전복(육상)"]], "cage"),
                            ([self.ids["전복(해상)"]], "land_based"),
                            ([self.ids["전복(육상)"], self.ids["전복(해상)"]], "cage")):
            with self.subTest(ids=ids, method=method):
                status, _, _ = request("POST", "/api/guest-registrations", self.db.farm_input(species_ids=ids, farming_method=method), headers={"X-CSRF-Protection": "1"})
                self.assertEqual(status, 422)
        self.assertEqual(self.db.connection.execute(f"SELECT count(*) AS n FROM {self.db.schema}.customers").fetchone()["n"], 0)

    def test_edit_replaces_species_link_without_changing_the_farm(self):
        _, guest, _ = self.register("전복(육상)", "land_based")
        farm_id = guest["farm"]["farm_id"]
        status, edited, _ = request("PATCH", f"/api/me/farms/{farm_id}", {
            "species_ids": [self.ids["전복(해상)"]], "farming_method": "cage"
        }, guest["access_token"])
        self.assertEqual(status, 200)
        self.assertEqual(edited["farm_id"], farm_id)
        self.assertEqual(self.linked_names(farm_id), ["전복(해상)"])

    def test_signup_and_relogin_preserve_selected_species(self):
        _, guest, _ = self.register("전복(해상)", "cage")
        profile = {"name": "품종 테스트", "birth_date": "1980-01-01", "phone_number": "01012345678", "password": "test-password"}
        status, member, _ = request("POST", "/api/auth/signup", profile, guest["access_token"])
        self.assertEqual(status, 201)
        self.assertEqual(member["customer"]["customer_id"], guest["customer"]["customer_id"])
        status, logged_in, _ = request("POST", "/api/auth/login", {k: profile[k] for k in ("phone_number", "password")}, headers={"X-CSRF-Protection": "1"})
        self.assertEqual(status, 200)
        status, farms, _ = request("GET", "/api/me/farms", token=logged_in["access_token"])
        self.assertEqual(status, 200)
        self.assertEqual(farms[0]["species_ids"], [self.ids["전복(해상)"]])
        self.assertEqual(self.linked_names(farms[0]["farm_id"]), ["전복(해상)"])

    def test_another_customer_cannot_reassign_this_farms_species(self):
        _, owner, _ = self.register("전복(육상)", "land_based")
        _, other, _ = self.register("전복(해상)", "cage")
        farm_id = owner["farm"]["farm_id"]
        status, _, _ = request("PATCH", f"/api/me/farms/{farm_id}", {
            "species_ids": [self.ids["전복(해상)"]], "farming_method": "cage"
        }, other["access_token"])
        self.assertEqual(status, 404)
        self.assertEqual(self.linked_names(farm_id), ["전복(육상)"])
