"""
resync_sequences.py
---------------------
Fixes a real, easy-to-miss PostgreSQL gotcha this project's own testing
caught: inserting an explicit value into a GENERATED [BY DEFAULT] AS
IDENTITY column (as every loader in this project does, to preserve
legacy customer/policy/claim numbers from VSAM/DB2 source data) never
advances the underlying sequence. The sequence has no idea a row with
that value now exists, so the NEXT auto-generated insert can collide
with a manually-inserted key and fail with a UniqueViolation - exactly
what happened when this project's business_services layer tried to
add a new claim after sample_data/claim.csv had loaded explicit
claim_number values 1000001/1000002 (the identity column's own START
WITH value).

Run this once after any data load that inserted explicit identity
values (run_migration.py calls it automatically at the end - see
its RESYNC_TABLES list).

USAGE:
    python3 resync_sequences.py --host localhost --dbname genapp \
        --user postgres --password CHANGE_ME_LOCAL_ONLY
"""
import argparse

from db_connect import add_pg_args, connect

# (table, identity_column)
IDENTITY_TABLES = [
    ("customer", "customer_number"),
    ("policy", "policy_number"),
    ("claim", "claim_number"),
]


def resync_sequences(conn, schema: str = "genapp", tables=None) -> dict:
    """For each (table, pk) pair, advance the identity sequence to
    MAX(pk)+1's predecessor (setval sets the 'last returned value', so
    the NEXT nextval() call returns max+1). Returns {table: new_last_value}
    for tables that had at least one row; tables with no rows are left
    at their original START WITH value (nothing to resync)."""
    tables = tables or IDENTITY_TABLES
    results = {}
    with conn.cursor() as cur:
        for table, pk in tables:
            cur.execute(f"SELECT pg_get_serial_sequence(%s, %s)", (f"{schema}.{table}", pk))
            seq = cur.fetchone()
            seq_name = seq[0] if isinstance(seq, (list, tuple)) else seq["pg_get_serial_sequence"]
            if not seq_name:
                continue  # not an identity column - nothing to resync
            cur.execute(f"SELECT MAX({pk}) FROM {schema}.{table}")
            row = cur.fetchone()
            max_val = row[0] if isinstance(row, (list, tuple)) else row["max"]
            if max_val is None:
                continue  # empty table - leave sequence at its START WITH value
            cur.execute("SELECT setval(%s, %s, true)", (seq_name, max_val))
            results[table] = max_val + 1
    conn.commit()
    return results


def main():
    parser = argparse.ArgumentParser(description="Resync identity sequences after an explicit-key data load")
    parser.add_argument("--schema", default="genapp")
    add_pg_args(parser)
    args = parser.parse_args()

    conn = connect(args)
    try:
        results = resync_sequences(conn, schema=args.schema)
        for table, next_val in results.items():
            print(f"  {table}: next auto-generated key will be {next_val}")
        if not results:
            print("  Nothing to resync (all identity tables empty).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
