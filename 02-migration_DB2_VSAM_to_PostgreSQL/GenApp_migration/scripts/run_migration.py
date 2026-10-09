"""
run_migration.py
------------------
End-to-end orchestrator for the GenApp DB2/VSAM -> PostgreSQL migration.
Applies DDL, then loads data in dependency order:
  1. schema + tables (customer must exist before policy; policy before
     endowment/house/motor/commercial/claim)
  2. VSAM customer extract (KSDSCUST) -> genapp.customer
  3. VSAM policy extract (KSDSPOLY)   -> genapp.policy + type-detail tables
  4. any DB2 CSV unloads present (customer_secure, claim, and/or full
     DB2-mode policy/endowment/house/motor/commercial records if the
     source shop ran GenApp in DB2 mode instead of/alongside VSAM)

Everything is idempotent (INSERT ... ON CONFLICT DO UPDATE), so this
script is safe to re-run.

USAGE:
    python3 run_migration.py --data-dir ../sample_data \
        --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY

    # Real mainframe EBCDIC binary extracts instead of the ASCII sample:
    python3 run_migration.py --data-dir /path/to/extracts --vsam-encoding cp037 ...

The target database itself does NOT need to already exist - this
script connects to the server's 'postgres' maintenance database first
and creates it (CREATE DATABASE) if it's missing, so a completely
fresh PostgreSQL install works with zero manual setup.
"""
import argparse
import os
import subprocess
import sys

import psycopg2

from db_connect import add_pg_args, resolve_pg_config, connect, ensure_database_exists

DDL_SEQUENCE = ["../sql/01_schema.sql", "../sql/02_target_schema.sql", "../sql/03_comments.sql"]

# DB2 CSV unloads this orchestrator knows how to place, in FK-safe order.
# customer/policy are normally sourced from VSAM (see VSAM_JOBS below);
# list them here too in case a shop ran GenApp in DB2-only mode and you
# point --data-dir at DB2 EXPORT output instead of VSAM extracts.
DB2_CSV_JOBS_ORDER = [
    "customer", "customer_secure", "policy",
    "endowment", "house", "motor", "commercial", "claim",
]


def run_ddl(args):
    """Apply each DDL file directly via psycopg2 (no dependency on the
    psql command-line client being installed/on PATH - important on
    Windows, where psql often isn't available even if PostgreSQL itself
    is running, e.g. via a service or Docker container)."""
    conn = connect(args)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        for path in DDL_SEQUENCE:
            print(f"\n=== Applying {path} ===")
            with open(path, "r", encoding="utf-8") as fh:
                sql_text = fh.read()
            try:
                cur.execute(sql_text)
                print("OK")
            except psycopg2.Error as e:
                print(f"DDL failed at {path}: {e}", file=sys.stderr)
                sys.exit(1)
    finally:
        conn.close()


def pg_cli_args(args):
    return ["--host", args.host or "localhost", "--dbname", args.dbname or "genapp",
            "--user", args.user or "postgres", "--password", args.password or "CHANGE_ME_LOCAL_ONLY",
            "--schema", "genapp"]


def run_vsam_jobs(args, data_dir):
    cust_path = os.path.join(data_dir, "ksdscust.txt" if os.path.exists(
        os.path.join(data_dir, "ksdscust.txt")) else "KSDSCUST.bin")
    poly_path = os.path.join(data_dir, "ksdspoly.txt" if os.path.exists(
        os.path.join(data_dir, "ksdspoly.txt")) else "KSDSPOLY.bin")

    if os.path.exists(cust_path):
        print(f"\n=== Loading customer from {cust_path} ===")
        cmd = [sys.executable, "load_vsam_customer.py", "--data", cust_path,
               "--encoding", args.vsam_encoding] + pg_cli_args(args)
        subprocess.run(cmd, check=True)
    else:
        print(f"SKIP customer VSAM load: no ksdscust.txt/KSDSCUST.bin found in {data_dir}")

    if os.path.exists(poly_path):
        print(f"\n=== Loading policy from {poly_path} ===")
        cmd = [sys.executable, "load_vsam_policy.py", "--data", poly_path,
               "--encoding", args.vsam_encoding] + pg_cli_args(args)
        subprocess.run(cmd, check=True)
    else:
        print(f"SKIP policy VSAM load: no ksdspoly.txt/KSDSPOLY.bin found in {data_dir}")


def run_db2_jobs(args, data_dir):
    for table in DB2_CSV_JOBS_ORDER:
        csv_path = os.path.join(data_dir, f"{table}.csv")
        if not os.path.exists(csv_path):
            continue
        print(f"\n=== Loading {table} from {csv_path} ===")
        cmd = [sys.executable, "db2_loader.py", "--csv", csv_path, "--table", table] + pg_cli_args(args)
        subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Run the full GenApp DB2/VSAM -> PostgreSQL migration")
    parser.add_argument("--data-dir", default="../sample_data")
    parser.add_argument("--vsam-encoding", default="ascii",
                         help="cp037 for real mainframe EBCDIC binary extracts, "
                              "ascii/utf-8 for pre-transcoded text extracts (default: ascii, "
                              "matching the sample files in sample_data/)")
    parser.add_argument("--skip-ddl", action="store_true")
    add_pg_args(parser)
    args = parser.parse_args()

    cfg = resolve_pg_config(args)

    if not args.skip_ddl:
        print(f"\n=== Ensuring database '{cfg['dbname']}' exists ===")
        created = ensure_database_exists(cfg)
        print(f"Created new database '{cfg['dbname']}'." if created
              else f"Database '{cfg['dbname']}' already exists.")
        run_ddl(args)
    run_vsam_jobs(args, args.data_dir)
    run_db2_jobs(args, args.data_dir)
    print("\nMigration run complete.")


if __name__ == "__main__":
    main()
