"""
db_connect.py
--------------
Single source of truth for PostgreSQL connection parameters, shared by
all loader scripts. Resolution order per parameter:
CLI arg > environment variable > hardcoded local-dev default.
"""
import argparse
import os
import psycopg2


def add_pg_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=None, help="PG host (default: env PGHOST or localhost)")
    parser.add_argument("--port", default=None, help="PG port (default: env PGPORT or 5432)")
    parser.add_argument("--dbname", default=None, help="PG database (default: env PGDATABASE or genapp)")
    parser.add_argument("--user", default=None, help="PG user (default: env PGUSER or postgres)")
    parser.add_argument("--password", default=None, help="PG password (default: env PGPASSWORD)")


def resolve_pg_config(args: argparse.Namespace) -> dict:
    return {
        "host": args.host or os.environ.get("PGHOST", "localhost"),
        "port": args.port or os.environ.get("PGPORT", "5432"),
        "dbname": args.dbname or os.environ.get("PGDATABASE", "genapp"),
        "user": args.user or os.environ.get("PGUSER", "postgres"),
        "password": args.password or os.environ.get("PGPASSWORD", "CHANGE_ME_LOCAL_ONLY"),
    }


def connect(args: argparse.Namespace):
    cfg = resolve_pg_config(args)
    return psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
        user=cfg["user"], password=cfg["password"],
    )


def ensure_database_exists(cfg: dict) -> bool:
    """Connect to the server's default 'postgres' maintenance database and
    CREATE DATABASE <cfg['dbname']> if it doesn't already exist. Returns
    True if the database was just created, False if it already existed.
    This lets run_migration.py be run against a brand-new PostgreSQL
    server with zero manual setup beyond having the server itself up."""
    admin_conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname="postgres",
        user=cfg["user"], password=cfg["password"],
    )
    try:
        admin_conn.autocommit = True
        cur = admin_conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg["dbname"],))
        if cur.fetchone():
            return False
        # Database names cannot be parameterized in CREATE DATABASE; the
        # value comes from our own resolved config (CLI/env), not untrusted
        # user input, and is quoted defensively regardless.
        safe_name = cfg["dbname"].replace('"', '""')
        cur.execute(f'CREATE DATABASE "{safe_name}"')
        return True
    finally:
        admin_conn.close()
