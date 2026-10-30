"""Run from the repository root: python -m backend.manage --help."""
import argparse
from getpass import getpass
import json
from pathlib import Path

import psycopg

from backend.db import connect
from backend.team import create_team_user, server_info
from backend.species_catalog import seed_abalone_species, seed_default_species, seed_research_species


def main():
    parser = argparse.ArgumentParser(description="NIFS PostgreSQL 관리")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-db")
    commands.add_parser("init-db")
    commands.add_parser("seed-customer-species", help="Add missing default aquaculture species; preserve existing IDs")
    commands.add_parser("seed-abalone-species", help="Add separate land/sea abalone catalogue entries without changing existing farms")
    commands.add_parser("seed-research-species", help="Add species verified in the four supplied research PDFs")
    commands.add_parser("server-info", help="Print PostgreSQL configuration paths without secrets")
    user_parser = commands.add_parser("create-user", help="Create a team login; prompts privately for its password")
    user_parser.add_argument("username")
    user_parser.add_argument("--write-data", action="store_true", help="Allow INSERT/UPDATE/DELETE as well as SELECT")
    args = parser.parse_args()
    try:
        if args.command == "create-user":
            password = getpass("New team DB password (at least 12 characters): ")
            if password != getpass("Confirm password: "):
                raise ValueError("Passwords do not match.")
        with connect() as conn:
            if args.command == "create-user":
                create_team_user(conn, args.username, password, write_data=args.write_data)
                access = "read/write data" if args.write_data else "read only"
                message = f"Created {args.username} ({access})."
            elif args.command == "server-info":
                message = json.dumps(server_info(conn), ensure_ascii=True, indent=2)
            elif args.command == "seed-customer-species":
                conn.execute("LOCK TABLE customer_service.species IN EXCLUSIVE MODE")
                seed_default_species(conn)
                message = "Missing default species added. Existing species preserved."
            elif args.command == "seed-abalone-species":
                seed_abalone_species(conn)
                message = "Land/sea abalone species added. Existing IDs and farm selections preserved."
            elif args.command == "seed-research-species":
                seed_research_species(conn)
                message = "Research species added. Existing species IDs and customer selections preserved."
            elif args.command == "init-db":
                schema = Path(__file__).resolve().parents[1] / "database" / "01_schema.sql"
                # The SQL file owns its BEGIN/COMMIT; avoid nesting transactions.
                conn.autocommit = True
                conn.execute(schema.read_text(encoding="utf-8"))
                message = "Schema initialized. Existing rows were preserved."
            else:
                row = conn.execute("SELECT current_database() AS name").fetchone()
                message = f"Connected to {row['name']}"
        print(message)
    except ValueError as exc:
        # Validation errors can contain connection strings; never print inputs.
        print("Invalid configuration or input. Check backend/.env, username and password requirements.")
        raise SystemExit(1) from None
    except psycopg.Error as exc:
        print(f"Database operation failed ({type(exc).__name__}). Check backend/.env and PostgreSQL.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
