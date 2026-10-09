"""
legacy_parity_app.py
-----------------------
Streamlit viewer for legacy_parity.py's behavioral parity report -
distinct from validation_app.py (which shows DATA validation results).
This shows whether the modern business_services layer's BEHAVIOR
matches the documented legacy business rules.

Click "▶️ Run parity check" to execute all rules against a live
database, then "🔍 Select rule" to open a popup listing every rule
with a status badge; pick one to see its legacy citation, description,
and evidence.

RUN:
    streamlit run legacy_parity_app.py
"""
import json
import os
import sys

import pandas as pd
import psycopg2
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))
from legacy_parity import run_legacy_parity_validation  # noqa: E402

st.set_page_config(page_title="GenApp Legacy vs Modern Parity", page_icon="⚖️", layout="wide")

STATUS_BADGE = {
    "MATCH": "✅ MATCH",
    "DEVIATION": "🔄 DEVIATION",
    "NEW_CAPABILITY": "🆕 NEW_CAPABILITY",
    "NOT_IMPLEMENTED": "⚠️ NOT_IMPLEMENTED",
    "FAIL": "❌ FAIL",
}


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
    run_clicked = st.button("▶️ Run parity check", type="primary", use_container_width=True)


@st.cache_resource(show_spinner=False)
def get_connection(host, port, dbname, user, password):
    import psycopg2.extras
    conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


try:
    conn = get_connection(host, port, dbname, user, password)
except Exception as e:
    st.error(f"Could not connect to PostgreSQL: {e}")
    st.stop()


st.title("⚖️ GenApp Legacy vs Modern Parity")
st.caption(
    "Checks that the business_services layer's **behavior** matches (or deliberately, "
    "documented-ly deviates from) rules extracted from the real GenApp COBOL source — "
    "distinct from data migration validation, which checks that data **values** match."
)

if run_clicked:
    with st.spinner("Running every rule check against the live database..."):
        try:
            st.session_state.parity_report = run_legacy_parity_validation(conn)
        except Exception as e:
            st.error(f"Parity run failed: {e}")
            st.stop()

report = st.session_state.get("parity_report")
if report is None:
    st.info("Click **▶️ Run parity check** in the sidebar to begin.")
    st.stop()


# ---------------------------------------------------------------------------
# Overall summary
# ---------------------------------------------------------------------------
overall = "✅ PASS (no FAILs)" if report["passed"] else "❌ FAIL"
st.markdown(f"## Overall result: {overall}")

count_cols = st.columns(5)
for i, status in enumerate(["MATCH", "DEVIATION", "NEW_CAPABILITY", "NOT_IMPLEMENTED", "FAIL"]):
    count_cols[i].metric(status, report["counts"].get(status, 0))

summary_df = pd.DataFrame([
    {"ID": r["id"], "Category": r["category"], "Check type": r["check_type"],
     "Status": STATUS_BADGE[r["status"]], "Rule": r["description"]}
    for r in report["rules"]
])
st.dataframe(summary_df, use_container_width=True, hide_index=True)

if report["counts"].get("NOT_IMPLEMENTED"):
    st.warning(
        f"⚠️ {report['counts']['NOT_IMPLEMENTED']} legacy rule(s) have no modern equivalent yet — "
        f"honestly reported gaps, not silently dropped. See the detail panel below."
    )
if report["counts"].get("DEVIATION"):
    st.info(
        f"🔄 {report['counts']['DEVIATION']} rule(s) are intentional, documented deviations from "
        f"legacy behavior (improvements or architecture simplifications), not parity failures."
    )


# ---------------------------------------------------------------------------
# Popup rule selector + detail panel
# ---------------------------------------------------------------------------
rule_ids = [r["id"] for r in report["rules"]]
if "selected_rule" not in st.session_state or st.session_state.selected_rule not in rule_ids:
    st.session_state.selected_rule = rule_ids[0]

col_popup, col_current = st.columns([1, 4])
with col_popup:
    with st.popover("🔍 Select rule", use_container_width=True):
        st.write(f"**{len(rule_ids)} rules checked**")
        for r in report["rules"]:
            label = f"{STATUS_BADGE[r['status']]}  {r['id']}"
            if st.button(label, key=f"pick_{r['id']}", use_container_width=True):
                st.session_state.selected_rule = r["id"]
                st.rerun()

with col_current:
    st.markdown(f"### Detail: `{st.session_state.selected_rule}`")

selected = next(r for r in report["rules"] if r["id"] == st.session_state.selected_rule)

st.markdown(f"**Status:** {STATUS_BADGE[selected['status']]}  ·  **Category:** {selected['category']}  ·  **Check type:** {selected['check_type']}")
st.markdown(f"**Legacy citation:** {selected['citation']}")
st.markdown(f"**Rule:** {selected['description']}")
st.markdown("**Evidence:**")
st.code(selected["evidence"], language=None)

st.download_button(
    "⬇️ Download full parity report as JSON",
    data=json.dumps(report, default=str, indent=2),
    file_name="legacy_parity_report.json",
    mime="application/json",
)
