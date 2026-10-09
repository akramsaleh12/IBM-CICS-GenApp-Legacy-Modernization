"""
meta.py
--------
Introspection endpoints: which tables exist, their data dictionary
(same queries used by streamlit_app/data_dictionary_app.py), and a
live migration-validation run (wraps scripts/validate_migration.py).
"""
import os
import sys

from fastapi import APIRouter, Depends, HTTPException

from database import get_db, SCHEMA
from schemas import TableInfo, ColumnInfo

router = APIRouter(tags=["meta"])

# scripts/validate_migration.py lives one level up, in ../scripts
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))


@router.get("/tables", response_model=list[TableInfo], summary="List all tables in the schema")
def list_tables(db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT t.table_name,
                   (SELECT obj_description(c.oid) FROM pg_catalog.pg_class c
                    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = t.table_schema AND c.relname = t.table_name
                      AND c.relkind = 'r') AS table_description,
                   (SELECT count(*) FROM information_schema.columns c
                    WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) AS column_count
            FROM information_schema.tables t
            WHERE t.table_schema = %s AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name
            """,
            (SCHEMA,),
        )
        return cur.fetchall()


@router.get("/tables/{table}/columns", response_model=list[ColumnInfo], summary="Column-level data dictionary for a table")
def table_columns(table: str, db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
            (SCHEMA, table),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"table '{table}' not found in schema '{SCHEMA}'")

        cur.execute(
            """
            SELECT
                c.ordinal_position AS position,
                c.column_name AS column,
                CASE
                    WHEN c.data_type = 'character varying' AND c.character_maximum_length IS NOT NULL
                        THEN 'varchar(' || c.character_maximum_length || ')'
                    WHEN c.data_type = 'numeric' AND c.numeric_precision IS NOT NULL
                        THEN 'numeric(' || c.numeric_precision || ',' || COALESCE(c.numeric_scale, 0) || ')'
                    ELSE c.data_type
                END AS data_type,
                (c.is_nullable = 'YES') AS nullable,
                c.column_default AS default,
                CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE NULL END AS key,
                CASE WHEN fk.column_name IS NOT NULL
                     THEN 'FK -> ' || fk.foreign_table || '.' || fk.foreign_column ELSE NULL END AS references,
                pgd.description AS description
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_statio_all_tables st
                ON st.relname = c.table_name AND st.schemaname = c.table_schema
            LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
            LEFT JOIN (
                SELECT kcu.table_schema, kcu.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
            ) pk ON pk.table_schema = c.table_schema AND pk.table_name = c.table_name AND pk.column_name = c.column_name
            LEFT JOIN (
                SELECT kcu.table_schema, kcu.table_name, kcu.column_name,
                       ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
            ) fk ON fk.table_schema = c.table_schema AND fk.table_name = c.table_name AND fk.column_name = c.column_name
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
            """,
            (SCHEMA, table),
        )
        return cur.fetchall()


@router.get("/validate", summary="Run full migration validation and return the report")
def run_validation(
    data_dir: str = "../sample_data",
    vsam_encoding: str = "ascii",
):
    """Wraps scripts/validate_migration.py: re-decodes the source VSAM/DB2
    files and diffs them field-by-field against this database, plus
    type-dispatch and referential-integrity checks. See
    docs/MIGRATION_BLUEPRINT.md / README "Migration validation" for
    full details on what each check does.

    Uses its own plain (tuple-cursor) connection rather than the pooled
    RealDictCursor connection the rest of the API uses - validate_migration.py
    was written expecting positional tuple unpacking (e.g. `for a, b, c in
    cur.fetchall()`), which breaks against dict-row cursors."""
    import psycopg2
    from validate_migration import run_full_validation
    from database import PG_CONFIG

    if not os.path.isdir(data_dir):
        raise HTTPException(status_code=400, detail=f"data_dir '{data_dir}' not found on the API server's filesystem")

    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = True
    try:
        report = run_full_validation(conn, data_dir, vsam_encoding=vsam_encoding, schema=SCHEMA)
    finally:
        conn.close()
    return report
