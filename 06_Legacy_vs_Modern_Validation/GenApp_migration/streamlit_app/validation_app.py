"""
validation_app.py
-------------------
Streamlit migration validation viewer for the GenApp PostgreSQL
database. Click "Run validation" to re-decode every source file
(VSAM bytes and DB2 CSVs) and diff it field-by-field against what's
actually in PostgreSQL, plus check type-dispatch and referential
integrity. Click "🔍 Select check" to open a popup listing every
check that ran; pick one to see its full detail below.

RUN:
    streamlit run validation_app.py
"""
import json
import os
import sys

import pandas as pd
import psycopg2
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from validate_migration import run_full_validation  # noqa: E402

st.set_page_config(page_title="GenApp Migration Validation", page_icon="✅", layout="wide")


# ---------------------------------------------------------------------------
# Connection + run settings
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

    st.header("Validation source")
    data_dir = st.text_input("Source data directory", value="../sample_data")
    vsam_encoding = st.selectbox(
        "VSAM encoding", ["ascii", "cp037", "cp500", "cp1140"],
        help="ascii for the pre-transcoded sample files in sample_data/; "
             "cp037 (or your shop's code page) for real mainframe EBCDIC binary extracts.",
    )
    run_clicked = st.button("▶️ Run validation", type="primary", use_container_width=True)


@st.cache_resource(show_spinner=False)
def get_connection(host, port, dbname, user, password):
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


try:
    conn = get_connection(host, port, dbname, user, password)
    conn.autocommit = True
except Exception as e:
    st.error(f"Could not connect to PostgreSQL: {e}")
    st.stop()


# ---------------------------------------------------------------------------
# Run (or reuse cached) validation
# ---------------------------------------------------------------------------
st.title("✅ GenApp Migration Validation")

if run_clicked:
    with st.spinner("Re-decoding source files and diffing against PostgreSQL..."):
        try:
            st.session_state.validation_report = run_full_validation(
                conn, data_dir, vsam_encoding=vsam_encoding, schema=schema
            )
        except Exception as e:
            st.error(f"Validation run failed: {e}")
            st.stop()

report = st.session_state.get("validation_report")

if report is None:
    st.info("Set the source data directory in the sidebar and click **▶️ Run validation** to begin.")
    st.stop()


# ---------------------------------------------------------------------------
# Overall summary
# ---------------------------------------------------------------------------
overall = "✅ PASS" if report["passed"] else "❌ FAIL"
st.markdown(f"## Overall result: {overall}")

all_checks = []
for c in report["source_checks"]:
    all_checks.append({
        "name": f"{c['source']} → {c['target_table']}",
        "kind": "source",
        "passed": c["passed"],
        "detail": c,
    })
for c in report["integrity_checks"]:
    all_checks.append({
        "name": c["check"].replace("_", " ").title(),
        "kind": "integrity",
        "passed": c["passed"],
        "detail": c,
    })

summary_rows = []
total_anomalies = 0
for c in all_checks:
    d = c["detail"]
    if c["kind"] == "source":
        summary_rows.append({
            "Check": c["name"],
            "Status": "✅ PASS" if c["passed"] else "❌ FAIL",
            "Source records": d["total_source_records"],
            "Matched": d.get("matched_in_target", "-"),
            "Missing": len(d["missing_in_target"]),
            "Mismatches": len(d["field_mismatches"]),
            "Anomalies": len(d["anomalies"]),
        })
        total_anomalies += len(d["anomalies"])
    else:
        extra = ""
        if d["check"] == "type_dispatch_integrity":
            extra = f"{len(d['violations'])} violation(s) / {d['total_policies']} policies"
        elif d["check"] == "referential_integrity":
            orphan_total = sum(r["orphan_count"] for r in d["results"])
            extra = f"{orphan_total} orphan(s) across {len(d['results'])} relationships"
        summary_rows.append({
            "Check": c["name"], "Status": "✅ PASS" if c["passed"] else "❌ FAIL",
            "Source records": "-", "Matched": "-", "Missing": "-", "Mismatches": "-", "Anomalies": extra,
        })

st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

if total_anomalies:
    st.warning(
        f"⚠️ {total_anomalies} source data-quality anomaly(ies) found (numeric fields with "
        f"non-digit characters in the source data itself). These do not fail validation - "
        f"they're a source-data issue, not a migration bug - but review them before a "
        f"production cutover. See the detail panel below for each affected record."
    )


# ---------------------------------------------------------------------------
# Popup check selector + detail panel
# ---------------------------------------------------------------------------
if "selected_check" not in st.session_state or st.session_state.selected_check not in [c["name"] for c in all_checks]:
    st.session_state.selected_check = all_checks[0]["name"]

col_popup, col_current = st.columns([1, 4])
with col_popup:
    with st.popover("🔍 Select check", use_container_width=True):
        st.write(f"**{len(all_checks)} checks ran**")
        for c in all_checks:
            icon = "✅" if c["passed"] else "❌"
            if st.button(f"{icon} {c['name']}", key=f"pick_{c['name']}", use_container_width=True):
                st.session_state.selected_check = c["name"]
                st.rerun()

with col_current:
    st.markdown(f"### Detail: `{st.session_state.selected_check}`")

selected = next(c for c in all_checks if c["name"] == st.session_state.selected_check)
d = selected["detail"]

if selected["kind"] == "source":
    if d.get("unknown_type_records"):
        st.error(f"Unknown policy type discriminator in records: {d['unknown_type_records']}")

    if d["missing_in_target"]:
        st.error(f"{len(d['missing_in_target'])} source record(s) not found in the target table:")
        st.dataframe(pd.DataFrame({"missing_key": d["missing_in_target"]}), use_container_width=True, hide_index=True)
    else:
        st.success("Every source record's key was found in the target table.")

    if d["field_mismatches"]:
        st.error(f"{len(d['field_mismatches'])} field mismatch(es):")
        st.dataframe(pd.DataFrame(d["field_mismatches"]), use_container_width=True, hide_index=True)
    else:
        st.success("Every mapped field matched exactly between source and target.")

    if d["anomalies"]:
        st.warning(f"{len(d['anomalies'])} source data-quality anomaly(ies):")
        st.dataframe(pd.DataFrame(d["anomalies"]), use_container_width=True, hide_index=True)

elif d["check"] == "type_dispatch_integrity":
    st.write(f"Checked {d['total_policies']} policies for exactly-one-correct-detail-row.")
    if d["violations"]:
        st.error(f"{len(d['violations'])} violation(s):")
        st.dataframe(pd.DataFrame(d["violations"]), use_container_width=True, hide_index=True)
    else:
        st.success("Every policy has exactly one detail row, in the correct type-specific table.")

elif d["check"] == "referential_integrity":
    rows = []
    any_orphans = False
    for r in d["results"]:
        rows.append({"Relationship": r["relationship"], "Orphan count": r["orphan_count"],
                      "Sample orphan keys": ", ".join(str(x) for x in r["orphans"][:10])})
        if r["orphan_count"]:
            any_orphans = True
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if any_orphans:
        st.error("Orphaned foreign key(s) found - see table above.")
    else:
        st.success("No orphaned foreign keys found across any relationship.")

st.download_button(
    "⬇️ Download full validation report as JSON",
    data=json.dumps(report, default=str, indent=2),
    file_name="migration_validation_report.json",
    mime="application/json",
)
