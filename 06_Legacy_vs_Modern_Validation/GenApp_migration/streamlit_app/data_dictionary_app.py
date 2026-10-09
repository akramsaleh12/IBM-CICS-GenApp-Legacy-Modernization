"""
data_dictionary_app.py
------------------------
Streamlit data dictionary viewer for the GenApp PostgreSQL database.

Click "Select table" to open a popup listing every table in the
`genapp` schema; pick one and its full column-level data dictionary
is displayed below - name, data type, length/precision, nullable,
default, and a business description (read from native PostgreSQL
COMMENT ON COLUMN metadata, applied by sql/03_comments.sql).

RUN:
    streamlit run data_dictionary_app.py

If a table's columns show a blank Description, sql/03_comments.sql
has not been applied to that database yet - run it once:
    psql -h <host> -U <user> -d genapp -f ../sql/03_comments.sql
"""
import os

import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="GenApp Data Dictionary", page_icon="📖", layout="wide")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def get_pg_defaults() -> dict:
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "dbname": os.environ.get("PGDATABASE", "genapp"),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "CHANGE_ME_LOCAL_ONLY"),
    }


with st.sidebar:
    st.header("Connection")
    defaults = get_pg_defaults()
    host = st.text_input("Host", value=defaults["host"])
    port = st.text_input("Port", value=defaults["port"])
    dbname = st.text_input("Database", value=defaults["dbname"])
    user = st.text_input("User", value=defaults["user"])
    password = st.text_input("Password", value=defaults["password"], type="password")
    schema = st.text_input("Schema", value="genapp")
    st.caption("Change any field and the app reconnects automatically.")


@st.cache_resource(show_spinner=False)
def get_connection(host, port, dbname, user, password):
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def run_query(conn, sql, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


try:
    conn = get_connection(host, port, dbname, user, password)
    conn.autocommit = True
except Exception as e:
    st.error(f"Could not connect to PostgreSQL: {e}")
    st.stop()


# ---------------------------------------------------------------------------
# Table discovery + table-level comment
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60)
def list_tables(_conn, schema: str) -> pd.DataFrame:
    sql = """
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
    """
    return run_query(_conn, sql, (schema,))


# ---------------------------------------------------------------------------
# Column-level data dictionary
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60)
def fetch_column_dictionary(_conn, schema: str, table: str) -> pd.DataFrame:
    sql = """
        SELECT
            c.ordinal_position AS "#",
            c.column_name AS "Column",
            CASE
                WHEN c.data_type = 'character varying' AND c.character_maximum_length IS NOT NULL
                    THEN 'varchar(' || c.character_maximum_length || ')'
                WHEN c.data_type = 'numeric' AND c.numeric_precision IS NOT NULL
                    THEN 'numeric(' || c.numeric_precision || ',' || COALESCE(c.numeric_scale, 0) || ')'
                ELSE c.data_type
            END AS "Data Type",
            CASE WHEN c.is_nullable = 'YES' THEN 'Yes' ELSE 'No' END AS "Nullable",
            COALESCE(c.column_default, '') AS "Default",
            CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE '' END AS "Key",
            CASE WHEN fk.column_name IS NOT NULL THEN 'FK -> ' || fk.foreign_table || '.' || fk.foreign_column ELSE '' END AS "References",
            COALESCE(pgd.description, '') AS "Description"
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
    """
    return run_query(_conn, sql, (schema, table))


try:
    tables_df = list_tables(conn, schema)
except Exception as e:
    st.error(f"Could not list tables in schema '{schema}': {e}")
    st.stop()

if tables_df.empty:
    st.warning(f"No tables found in schema '{schema}'.")
    st.stop()

table_names = tables_df["table_name"].tolist()

if "selected_dict_table" not in st.session_state:
    st.session_state.selected_dict_table = table_names[0]


# ---------------------------------------------------------------------------
# Popup table selector
# ---------------------------------------------------------------------------
st.title("📖 GenApp Data Dictionary")

col_popup, col_current = st.columns([1, 4])
with col_popup:
    with st.popover("📋 Select table", use_container_width=True):
        st.write(f"**{len(table_names)} tables in `{schema}`**")
        for _, row in tables_df.iterrows():
            name = row["table_name"]
            label = f"{name}  ·  {row['column_count']} cols"
            if st.button(label, key=f"dict_pick_{name}", use_container_width=True):
                st.session_state.selected_dict_table = name
                st.rerun()

with col_current:
    st.markdown(f"### Selected table: `{st.session_state.selected_dict_table}`")

selected = st.session_state.selected_dict_table
table_desc = tables_df.loc[tables_df.table_name == selected, "table_description"].iloc[0]

if table_desc:
    st.info(table_desc)
else:
    st.caption("No table-level description found (run sql/03_comments.sql to add one).")


# ---------------------------------------------------------------------------
# Column dictionary grid
# ---------------------------------------------------------------------------
try:
    dict_df = fetch_column_dictionary(conn, schema, selected)
except Exception as e:
    st.error(f"Could not read column metadata for '{selected}': {e}")
    st.stop()

missing_desc = (dict_df["Description"] == "").sum()
if missing_desc:
    st.warning(
        f"{missing_desc} of {len(dict_df)} column(s) have no description yet. "
        f"Run `sql/03_comments.sql` against this database to populate them."
    )

st.dataframe(
    dict_df,
    use_container_width=True,
    height=460,
    column_config={
        "#": st.column_config.NumberColumn(width="small"),
        "Column": st.column_config.TextColumn(width="medium"),
        "Data Type": st.column_config.TextColumn(width="small"),
        "Nullable": st.column_config.TextColumn(width="small"),
        "Key": st.column_config.TextColumn(width="small"),
        "References": st.column_config.TextColumn(width="medium"),
        "Description": st.column_config.TextColumn(width="large"),
    },
    hide_index=True,
)

st.download_button(
    "⬇️ Download this dictionary as CSV",
    data=dict_df.to_csv(index=False).encode("utf-8"),
    file_name=f"{selected}_data_dictionary.csv",
    mime="text/csv",
)

st.caption(f"{len(dict_df)} columns in `{schema}.{selected}`.")
