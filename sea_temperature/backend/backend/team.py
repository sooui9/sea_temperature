"""Provision a project login without sharing the PostgreSQL administrator account."""
import re

from psycopg import Connection, sql


def create_team_user(conn: Connection, username: str, password: str, *, write_data: bool = False, schema: str = "public"):
    if not re.fullmatch(r"nifs_[a-z0-9_]{1,50}", username):
        raise ValueError("Use a username starting with nifs_ and lowercase letters, digits or underscores.")
    if len(password) < 12:
        raise ValueError("Use a password containing at least 12 characters.")
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (username,)).fetchone():
        raise ValueError("That role already exists. Its password and permissions were not changed.")
    identity = conn.execute("SELECT current_database() AS db, current_user AS owner").fetchone()
    role, namespace = sql.Identifier(username), sql.Identifier(schema)
    conn.execute("SET LOCAL password_encryption = 'scram-sha-256'")
    conn.execute(sql.SQL(
        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}"
    ).format(role, sql.Literal(password)))
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(identity["db"]), role))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(namespace, role))
    privileges = sql.SQL("SELECT, INSERT, UPDATE, DELETE" if write_data else "SELECT")
    conn.execute(sql.SQL("GRANT {} ON ALL TABLES IN SCHEMA {} TO {}").format(privileges, namespace, role))
    # Future objects created by the provisioning owner inherit the same grants.
    conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT {} ON TABLES TO {}").format(
        sql.Identifier(identity["owner"]), namespace, privileges, role,
    ))
    if write_data:
        conn.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(namespace, role))
        conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE, SELECT ON SEQUENCES TO {}").format(
            sql.Identifier(identity["owner"]), namespace, role,
        ))


def server_info(conn: Connection) -> dict:
    row = conn.execute("""
        SELECT current_database() AS database, current_user AS username,
               current_setting('listen_addresses') AS listen_addresses,
               current_setting('port')::int AS port,
               current_setting('config_file') AS config_file,
               current_setting('hba_file') AS hba_file
    """).fetchone()
    row["hba_errors"] = conn.execute(
        "SELECT line_number, error FROM pg_hba_file_rules WHERE error IS NOT NULL"
    ).fetchall()
    return row
