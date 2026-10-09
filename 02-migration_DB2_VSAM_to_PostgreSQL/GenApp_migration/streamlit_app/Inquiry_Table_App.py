"""
app.py
-------
Streamlit viewer for the GenApp PostgreSQL database.

Click "Select table" to open a popup listing every table in the
`genapp` schema; pick one and its rows are displayed in a data grid
below, with row-count, a configurable row limit, a text filter, and a
CSV download button.

RUN:
    streamlit run app.py

Connection defaults match the rest of this project (see
scripts/db_connect.py): host=localhost, port=5432, dbname=genapp,
user=postgres, password=CHANGE_ME_LOCAL_ONLY - all editable from the sidebar and
overridable via the standard PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
environment variables.
"""
import os

import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="GenApp DB Viewer", page_icon="🗄️", layout="wide")


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
# Table discovery
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60)
def list_tables(_conn, schema: str) -> pd.DataFrame:
    sql = """
        SELECT t.table_name,
               (SELECT count(*) FROM information_schema.columns c
                WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) AS column_count
        FROM information_schema.tables t
        WHERE t.table_schema = %s AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """
    return run_query(_conn, sql, (schema,))


@st.cache_data(show_spinner=False, ttl=60)
def row_count(_conn, schema: str, table: str) -> int:
    with _conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
        return cur.fetchone()[0]


@st.cache_data(show_spinner=False, ttl=15)
def fetch_rows(_conn, schema: str, table: str, limit: int, offset: int) -> pd.DataFrame:
    return run_query(
        _conn,
        f'SELECT * FROM "{schema}"."{table}" ORDER BY 1 LIMIT %s OFFSET %s',
        (limit, offset),
    )


try:
    tables_df = list_tables(conn, schema)
except Exception as e:
    st.error(f"Could not list tables in schema '{schema}': {e}")
    st.stop()

if tables_df.empty:
    st.warning(f"No tables found in schema '{schema}'.")
    st.stop()

table_names = tables_df["table_name"].tolist()

if "selected_table" not in st.session_state:
    st.session_state.selected_table = table_names[0]


# ---------------------------------------------------------------------------
# Popup table selector
# ---------------------------------------------------------------------------
st.title("🗄️ GenApp Database Viewer")

col_popup, col_current = st.columns([1, 4])
with col_popup:
    with st.popover("📋 Select table", use_container_width=True):
        st.write(f"**{len(table_names)} tables in `{schema}`**")
        for name in table_names:
            cols_meta = tables_df.loc[tables_df.table_name == name, "column_count"].iloc[0]
            label = f"{name}  ·  {cols_meta} cols"
            if st.button(label, key=f"pick_{name}", use_container_width=True):
                st.session_state.selected_table = name
                st.rerun()

with col_current:
    st.markdown(f"### Selected table: `{st.session_state.selected_table}`")

selected = st.session_state.selected_table

# ---------------------------------------------------------------------------
# Row viewer
# ---------------------------------------------------------------------------
try:
    total_rows = row_count(conn, schema, selected)
except Exception as e:
    st.error(f"Could not read table '{selected}': {e}")
    st.stop()

ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 2])
with ctrl1:
    page_size = st.selectbox("Rows per page", [10, 25, 50, 100, 500], index=1)
with ctrl2:
    max_page = max((total_rows - 1) // page_size, 0)
    page = st.number_input("Page", min_value=0, max_value=max_page, value=0, step=1)
with ctrl3:
    st.metric("Total rows", total_rows)

offset = page * page_size
rows_df = fetch_rows(conn, schema, selected, page_size, offset)

search = st.text_input("Filter (matches any column, case-insensitive substring)")
if search:
    mask = rows_df.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
    display_df = rows_df[mask]
else:
    display_df = rows_df

st.dataframe(display_df, use_container_width=True, height=460)

st.download_button(
    "⬇️ Download this page as CSV",
    data=display_df.to_csv(index=False).encode("utf-8"),
    file_name=f"{selected}_page{page}.csv",
    mime="text/csv",
)

st.caption(
    f"Showing rows {offset + 1}-{min(offset + page_size, total_rows)} of {total_rows} "
    f"in `{schema}.{selected}` (page {page + 1} of {max_page + 1})."
)
