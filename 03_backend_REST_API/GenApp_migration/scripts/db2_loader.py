"""
db2_loader.py
---------------
Loads data exported from DB2 (via the DB2 EXPORT/UNLOAD utility, or
db2 "IXF"/delimited unload) into the equivalent PostgreSQL table
created by sql/02_target_schema.sql.

INPUT ASSUMPTION: DB2 data has been unloaded to delimited (CSV/pipe)
files, one per table, with a header row, using DB2's own EXPORT
utility on the mainframe/LUW side:

    EXPORT TO claim.csv OF DEL
        MODIFIED BY COLDEL, CHARDEL""
        SELECT * FROM <DB2DBID>.Claim;

This script is intentionally thin: DB2 relational data does not need
EBCDIC/COMP-3 unpacking (DB2's EXPORT utility already renders native
types as text), so the main job here is type coercion + efficient
bulk load via COPY, upserted through a temp staging table on the
target's primary key so the load is safely re-runnable.

USAGE:
    python3 db2_loader.py --csv claim.csv --table claim --schema genapp \
        --host localhost --dbname genapp --user postgres
"""
import argparse
import csv
import io

from db_connect import add_pg_args, connect


def _primary_key_columns(conn, schema: str, table: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s AND tc.table_name = %s
        ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    )
    return [r[0] for r in cur.fetchall()]


def load_csv(csv_path: str, table: str, conn, schema: str = "genapp",
             delimiter: str = ",") -> int:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        header = [h.strip().lower() for h in next(reader)]
        rows = list(reader)

    if not rows:
        return 0

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t")
    for row in rows:
        # Normalize DB2 NULL markers and pad/truncate ragged rows
        normalized = [("\\N" if (v is None or v == "") else v) for v in row]
        writer.writerow(normalized)
    buf.seek(0)

    cur = conn.cursor()
    col_list = ", ".join(header)
    pk_cols = _primary_key_columns(conn, schema, table)

    if not pk_cols:
        # No primary key found (unusual for this schema, but fall back to a
        # plain COPY rather than failing outright) - NOT idempotent/re-runnable.
        cur.copy_expert(
            f"COPY {schema}.{table} ({col_list}) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N')",
            buf,
        )
        conn.commit()
        return len(rows)

    # Idempotent load: COPY into a temp staging table, then UPSERT into the
    # real target on its primary key, so re-running this script (e.g. after
    # fixing a source data issue, or because run_migration.py was re-run)
    # never fails with a duplicate-key error the way a plain COPY would.
    staging_table = f"_staging_{table}"
    cur.execute(f"CREATE TEMP TABLE {staging_table} (LIKE {schema}.{table} INCLUDING DEFAULTS) ON COMMIT DROP")
    cur.copy_expert(
        f"COPY {staging_table} ({col_list}) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N')",
        buf,
    )
    pk_list = ", ".join(pk_cols)
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in header if c not in pk_cols)
    if update_clause:
        upsert_sql = (
            f"INSERT INTO {schema}.{table} ({col_list}) "
            f"SELECT {col_list} FROM {staging_table} "
            f"ON CONFLICT ({pk_list}) DO UPDATE SET {update_clause}"
        )
    else:
        upsert_sql = (
            f"INSERT INTO {schema}.{table} ({col_list}) "
            f"SELECT {col_list} FROM {staging_table} "
            f"ON CONFLICT ({pk_list}) DO NOTHING"
        )
    cur.execute(upsert_sql)
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Load a DB2 delimited unload file into PostgreSQL")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--schema", default="genapp")
    parser.add_argument("--delimiter", default=",")
    add_pg_args(parser)
    args = parser.parse_args()

    conn = connect(args)
    try:
        n = load_csv(args.csv, args.table, conn, schema=args.schema, delimiter=args.delimiter)
        print(f"Done: {n} rows loaded into {args.schema}.{args.table}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
