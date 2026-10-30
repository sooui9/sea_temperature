"""Canonical catalogue entries used to validate new farm selections."""
from pathlib import Path

ABALONE_METHODS = {"전복(육상)": "land_based", "전복(해상)": "cage"}
DEFAULT_SPECIES = ("조피볼락 (우럭)", "넙치 (광어)", "참돔", "돌돔", "감성돔", "숭어", "굴", "멍게", "기타")


def seed_abalone_species(conn):
    script = Path(__file__).resolve().parents[1] / "database" / "02_abalone_species.sql"
    conn.execute(script.read_text(encoding="utf-8"))


def seed_research_species(conn):
    script = Path(__file__).resolve().parents[1] / "database" / "03_research_species.sql"
    conn.execute(script.read_text(encoding="utf-8"))


def seed_default_species(conn):
    for name in DEFAULT_SPECIES:
        conn.execute("INSERT INTO customer_service.species (species_name) VALUES (%s) ON CONFLICT (species_name) DO NOTHING", (name,))
    seed_research_species(conn)
    seed_abalone_species(conn)
