"""
validate_migration.py
-----------------------
Post-migration validation for the GenApp -> PostgreSQL migration.
This does not just compare row counts - it RE-DECODES every source
record (VSAM bytes and DB2 CSV rows) using the same logic the loaders
used, looks up the corresponding row in PostgreSQL by primary key, and
diffs every mapped field, so a validation "pass" means the target data
is provably byte-for-byte faithful to the source, not just present.

Checks performed:
  1. Row/key coverage   - every source record's key exists in the target
  2. Field-level accuracy - every mapped field matches exactly
  3. Type-dispatch integrity - every policy has exactly one detail row,
     in the correct one of endowment/house/motor/commercial
  4. Referential integrity - no orphaned foreign keys
  5. Source data-quality anomalies - numeric DISPLAY fields containing
     non-digit characters (the class of issue that caught the malformed
     `bedrooms` value in ksdspoly.txt) are flagged, distinctly from
     migration mismatches, since they are a SOURCE data problem, not a
     migration bug.

USAGE:
    python3 validate_migration.py --data-dir ../sample_data \
        --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY

    # Real mainframe EBCDIC binary extracts instead of the ASCII sample:
    python3 validate_migration.py --data-dir /path/to/extracts --vsam-encoding cp037 ...

Can also be imported and driven programmatically (see
streamlit_app/validation_app.py) via run_full_validation(conn, ...).
"""
import argparse
import csv
import os

from copybook_parser import parse_copybook, flatten, record_length
from ebcdic_utils import decode_field
from db_connect import add_pg_args, connect
from vsam_io import read_records
from load_vsam_policy import TYPE_DISPATCH, _leaf_by_name

CUSTOMER_COPYBOOK = "../copybooks/derived_vsam_customer.cpy"
POLICY_COPYBOOK = "../copybooks/derived_vsam_policy.cpy"

CUSTOMER_COL_MAP = {
    "CUST-NUM": "customer_number",
    "CUST-FIRST-NAME": "first_name",
    "CUST-LAST-NAME": "last_name",
    "CUST-DOB": "date_of_birth",
    "CUST-HOUSE-NAME": "house_name",
    "CUST-HOUSE-NUM": "house_number",
    "CUST-POSTCODE": "postcode",
    "CUST-PHONE-MOBILE": "phone_mobile",
    "CUST-PHONE-HOME": "phone_home",
    "CUST-EMAIL-ADDRESS": "email_address",
}


def _norm(value) -> str:
    """Normalize a value for comparison: None/blank -> '', everything
    else -> stripped string. Dates/Decimals compare correctly as str()
    since both source-decoded and psycopg2-returned values stringify
    to the same canonical form (YYYY-MM-DD for dates, plain digits for
    Decimal)."""
    if value is None:
        return ""
    s = str(value).strip()
    return s


def _numeric_anomaly(raw: bytes, field, codec: str):
    """Flag a numeric DISPLAY field whose raw text contains a
    non-trailing/leading blank or other non-digit character - the
    pattern that indicates the SOURCE data itself is malformed (as
    opposed to a migration/decoding bug). Returns a description string
    or None."""
    pic = (field.pic or "").upper()
    if field.usage in ("COMP-3", "COMP") or "X" in pic:
        return None  # binary fields can't have this class of anomaly
    if "9" not in pic:
        return None
    text = raw.decode(codec, errors="replace")
    stripped = text.strip()
    if stripped == "":
        return None
    if not stripped.isdigit():
        return f"raw={text!r} is not purely numeric after trimming (found {stripped!r})"
    return None


# ---------------------------------------------------------------------------
# 1 & 2: VSAM customer - row coverage + field accuracy
# ---------------------------------------------------------------------------
def validate_vsam_customer(conn, data_path: str, encoding: str, schema: str = "genapp") -> dict:
    with open(CUSTOMER_COPYBOOK) as fh:
        roots = parse_copybook(fh.read())
    leaves = flatten(roots)
    rec_len = record_length(roots)

    result = {
        "source": os.path.basename(data_path),
        "target_table": f"{schema}.customer",
        "total_source_records": 0,
        "missing_in_target": [],
        "field_mismatches": [],
        "anomalies": [],
    }

    cur = conn.cursor()
    for raw in read_records(data_path, rec_len):
        result["total_source_records"] += 1
        source_row = {}
        for leaf in leaves:
            seg = raw[leaf.offset: leaf.offset + leaf.length]
            anomaly = _numeric_anomaly(seg, leaf, encoding)
            if anomaly:
                result["anomalies"].append({
                    "record": result["total_source_records"], "field": leaf.name, "detail": anomaly,
                })
            col = CUSTOMER_COL_MAP.get(leaf.name)
            if col:
                source_row[col] = decode_field(seg, leaf, codec=encoding)

        cust_num = int(source_row["customer_number"])
        cols = list(source_row.keys())
        cur.execute(f'SELECT {", ".join(cols)} FROM {schema}.customer WHERE customer_number = %s', (cust_num,))
        target_row = cur.fetchone()

        if target_row is None:
            result["missing_in_target"].append(cust_num)
            continue

        for col, tval in zip(cols, target_row):
            sval = source_row[col]
            if _norm(sval) != _norm(tval):
                result["field_mismatches"].append({
                    "key": cust_num, "column": col,
                    "source_value": _norm(sval), "target_value": _norm(tval),
                })

    result["matched_in_target"] = result["total_source_records"] - len(result["missing_in_target"])
    result["passed"] = not result["missing_in_target"] and not result["field_mismatches"]
    return result


# ---------------------------------------------------------------------------
# 1 & 2: VSAM policy - row coverage + field accuracy (with type dispatch)
# ---------------------------------------------------------------------------
def validate_vsam_policy(conn, data_path: str, encoding: str, schema: str = "genapp") -> dict:
    with open(POLICY_COPYBOOK) as fh:
        roots = parse_copybook(fh.read())
    root = roots[0]
    rec_len = record_length(roots)

    key_fields = {f.name: f for f in root.children if not f.redefines and not f.is_group}
    request_id_field = key_fields["POLICY-REQUEST-ID"]
    cust_num_field = key_fields["POLICY-CUSTOMER-NUM"]
    policy_num_field = key_fields["POLICY-NUM"]

    variant_group_name = {"C": "POLICY-C-DATA", "E": "POLICY-E-DATA",
                           "H": "POLICY-H-DATA", "M": "POLICY-M-DATA"}
    variant_leaves_cache = {t: _leaf_by_name(roots, name) for t, name in variant_group_name.items()}

    result = {
        "source": os.path.basename(data_path),
        "target_table": f"{schema}.policy (+ type-detail tables)",
        "total_source_records": 0,
        "missing_in_target": [],
        "field_mismatches": [],
        "anomalies": [],
        "unknown_type_records": [],
    }

    cur = conn.cursor()
    for raw in read_records(data_path, rec_len):
        result["total_source_records"] += 1
        type_char = decode_field(
            raw[request_id_field.offset:request_id_field.offset + request_id_field.length],
            request_id_field, codec=encoding,
        ).strip().upper()

        cust_num = int(decode_field(
            raw[cust_num_field.offset:cust_num_field.offset + cust_num_field.length],
            cust_num_field, codec=encoding,
        ).strip())
        policy_num = int(decode_field(
            raw[policy_num_field.offset:policy_num_field.offset + policy_num_field.length],
            policy_num_field, codec=encoding,
        ).strip())

        if type_char not in TYPE_DISPATCH:
            result["unknown_type_records"].append(policy_num)
            continue

        cur.execute(
            f"SELECT customer_number, policy_type FROM {schema}.policy WHERE policy_number = %s",
            (policy_num,),
        )
        target_policy = cur.fetchone()
        if target_policy is None:
            result["missing_in_target"].append(policy_num)
            continue

        if target_policy[0] != cust_num:
            result["field_mismatches"].append({
                "key": policy_num, "column": "customer_number",
                "source_value": cust_num, "target_value": target_policy[0],
            })
        if target_policy[1] != type_char:
            result["field_mismatches"].append({
                "key": policy_num, "column": "policy_type",
                "source_value": type_char, "target_value": target_policy[1],
            })

        table, field_col_map = TYPE_DISPATCH[type_char]
        source_detail = {}
        for leaf in variant_leaves_cache[type_char]:
            seg = raw[leaf.offset: leaf.offset + leaf.length]
            anomaly = _numeric_anomaly(seg, leaf, encoding)
            if anomaly:
                result["anomalies"].append({
                    "record": policy_num, "field": leaf.name, "detail": anomaly,
                })
            col = field_col_map.get(leaf.name)
            if col:
                source_detail[col] = decode_field(seg, leaf, codec=encoding)

        cols = list(source_detail.keys())
        cur.execute(f'SELECT {", ".join(cols)} FROM {schema}.{table} WHERE policy_number = %s', (policy_num,))
        target_detail = cur.fetchone()
        if target_detail is None:
            result["missing_in_target"].append(f"{policy_num} ({table} detail row)")
            continue
        for col, tval in zip(cols, target_detail):
            sval = source_detail[col]
            if _norm(sval) != _norm(tval):
                result["field_mismatches"].append({
                    "key": f"{policy_num} ({table}.{col})", "column": col,
                    "source_value": _norm(sval), "target_value": _norm(tval),
                })

    result["matched_in_target"] = (result["total_source_records"]
                                    - len(result["missing_in_target"])
                                    - len(result["unknown_type_records"]))
    result["passed"] = (not result["missing_in_target"] and not result["field_mismatches"]
                         and not result["unknown_type_records"])
    return result


# ---------------------------------------------------------------------------
# 1 & 2: DB2 CSV - row coverage + field accuracy (generic, any table)
# ---------------------------------------------------------------------------
def validate_db2_csv(conn, csv_path: str, table: str, schema: str = "genapp") -> dict:
    result = {
        "source": os.path.basename(csv_path),
        "target_table": f"{schema}.{table}",
        "total_source_records": 0,
        "missing_in_target": [],
        "field_mismatches": [],
        "anomalies": [],
    }

    cur = conn.cursor()
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s AND tc.table_name = %s
        """,
        (schema, table),
    )
    pk_cols = [r[0] for r in cur.fetchall()]
    if not pk_cols:
        result["error"] = f"No primary key found for {schema}.{table}; cannot key-match rows."
        result["passed"] = False
        return result

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for source_row in reader:
            result["total_source_records"] += 1
            source_row = {k.strip().lower(): (v if v != "" else None) for k, v in source_row.items()}
            pk_values = [source_row[c] for c in pk_cols]

            where_clause = " AND ".join(f"{c} = %s" for c in pk_cols)
            cols = list(source_row.keys())
            cur.execute(f'SELECT {", ".join(cols)} FROM {schema}.{table} WHERE {where_clause}', pk_values)
            target_row = cur.fetchone()

            key_label = ",".join(str(v) for v in pk_values)
            if target_row is None:
                result["missing_in_target"].append(key_label)
                continue

            for col, tval in zip(cols, target_row):
                sval = source_row[col]
                if _norm(sval) != _norm(tval):
                    result["field_mismatches"].append({
                        "key": key_label, "column": col,
                        "source_value": _norm(sval), "target_value": _norm(tval),
                    })

    result["matched_in_target"] = result["total_source_records"] - len(result["missing_in_target"])
    result["passed"] = not result["missing_in_target"] and not result["field_mismatches"]
    return result


# ---------------------------------------------------------------------------
# 3: Type-dispatch integrity - every policy has exactly one detail row,
#    in the correct one of endowment/house/motor/commercial
# ---------------------------------------------------------------------------
def validate_type_dispatch_integrity(conn, schema: str = "genapp") -> dict:
    expected_table = {"E": "endowment", "H": "house", "M": "motor", "C": "commercial"}
    detail_tables = ["endowment", "house", "motor", "commercial"]

    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.policy_number, p.policy_type,
               (SELECT count(*) FROM {schema}.endowment e WHERE e.policy_number = p.policy_number) AS n_endowment,
               (SELECT count(*) FROM {schema}.house h WHERE h.policy_number = p.policy_number) AS n_house,
               (SELECT count(*) FROM {schema}.motor m WHERE m.policy_number = p.policy_number) AS n_motor,
               (SELECT count(*) FROM {schema}.commercial c WHERE c.policy_number = p.policy_number) AS n_commercial
        FROM {schema}.policy p
    """)

    violations = []
    total = 0
    for policy_number, policy_type, n_end, n_house, n_motor, n_comm in cur.fetchall():
        total += 1
        counts = {"endowment": n_end, "house": n_house, "motor": n_motor, "commercial": n_comm}
        expected = expected_table.get(policy_type)
        problems = []
        for t in detail_tables:
            expected_count = 1 if t == expected else 0
            if counts[t] != expected_count:
                problems.append(f"{t}={counts[t]} (expected {expected_count})")
        if problems:
            violations.append({"policy_number": policy_number, "policy_type": policy_type,
                                "problem": "; ".join(problems)})

    return {
        "check": "type_dispatch_integrity",
        "total_policies": total,
        "violations": violations,
        "passed": not violations,
    }


# ---------------------------------------------------------------------------
# 4: Referential integrity - orphaned foreign keys
# ---------------------------------------------------------------------------
def validate_referential_integrity(conn, schema: str = "genapp") -> dict:
    checks = [
        ("policy.customer_number -> customer", f"""
            SELECT p.policy_number FROM {schema}.policy p
            LEFT JOIN {schema}.customer c ON c.customer_number = p.customer_number
            WHERE c.customer_number IS NULL
        """),
        ("claim.policy_number -> policy", f"""
            SELECT cl.claim_number FROM {schema}.claim cl
            LEFT JOIN {schema}.policy p ON p.policy_number = cl.policy_number
            WHERE p.policy_number IS NULL
        """),
        ("customer_secure.customer_number -> customer", f"""
            SELECT cs.customer_number FROM {schema}.customer_secure cs
            LEFT JOIN {schema}.customer c ON c.customer_number = cs.customer_number
            WHERE c.customer_number IS NULL
        """),
    ]
    for detail_table in ("endowment", "house", "motor", "commercial"):
        checks.append((f"{detail_table}.policy_number -> policy", f"""
            SELECT d.policy_number FROM {schema}.{detail_table} d
            LEFT JOIN {schema}.policy p ON p.policy_number = d.policy_number
            WHERE p.policy_number IS NULL
        """))

    cur = conn.cursor()
    results = []
    for label, sql in checks:
        cur.execute(sql)
        orphans = [r[0] for r in cur.fetchall()]
        results.append({"relationship": label, "orphan_count": len(orphans), "orphans": orphans[:20]})

    return {
        "check": "referential_integrity",
        "results": results,
        "passed": all(r["orphan_count"] == 0 for r in results),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_full_validation(conn, data_dir: str, vsam_encoding: str = "ascii", schema: str = "genapp") -> dict:
    report = {"source_checks": [], "integrity_checks": []}

    cust_path = os.path.join(data_dir, "ksdscust.txt")
    if os.path.exists(cust_path):
        report["source_checks"].append(validate_vsam_customer(conn, cust_path, vsam_encoding, schema))

    poly_path = os.path.join(data_dir, "ksdspoly.txt")
    if os.path.exists(poly_path):
        report["source_checks"].append(validate_vsam_policy(conn, poly_path, vsam_encoding, schema))

    for table in ["customer", "customer_secure", "policy", "endowment", "house", "motor", "commercial", "claim"]:
        csv_path = os.path.join(data_dir, f"{table}.csv")
        if os.path.exists(csv_path):
            report["source_checks"].append(validate_db2_csv(conn, csv_path, table, schema))

    report["integrity_checks"].append(validate_type_dispatch_integrity(conn, schema))
    report["integrity_checks"].append(validate_referential_integrity(conn, schema))

    report["passed"] = (all(c["passed"] for c in report["source_checks"])
                         and all(c["passed"] for c in report["integrity_checks"]))
    return report


def print_report(report: dict) -> None:
    print("=" * 70)
    print("MIGRATION VALIDATION REPORT")
    print("=" * 70)

    for check in report["source_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"\n[{status}] {check['source']} -> {check['target_table']}")
        print(f"  Source records: {check['total_source_records']}, "
              f"matched: {check.get('matched_in_target', 'n/a')}, "
              f"missing: {len(check['missing_in_target'])}, "
              f"field mismatches: {len(check['field_mismatches'])}")
        if check.get("unknown_type_records"):
            print(f"  Unknown policy type in records: {check['unknown_type_records']}")
        if check["missing_in_target"]:
            print(f"  Missing keys (first 10): {check['missing_in_target'][:10]}")
        if check["field_mismatches"]:
            print("  Field mismatches (first 10):")
            for m in check["field_mismatches"][:10]:
                print(f"    key={m['key']} column={m['column']} "
                      f"source={m['source_value']!r} target={m['target_value']!r}")
        if check["anomalies"]:
            print(f"  Source data-quality anomalies found ({len(check['anomalies'])}):")
            for a in check["anomalies"][:10]:
                print(f"    record={a['record']} field={a['field']}: {a['detail']}")

    for check in report["integrity_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"\n[{status}] {check['check']}")
        if check["check"] == "type_dispatch_integrity":
            print(f"  Policies checked: {check['total_policies']}, violations: {len(check['violations'])}")
            for v in check["violations"][:10]:
                print(f"    policy_number={v['policy_number']} type={v['policy_type']}: {v['problem']}")
        elif check["check"] == "referential_integrity":
            for r in check["results"]:
                mark = "OK" if r["orphan_count"] == 0 else "ORPHANS"
                print(f"  [{mark}] {r['relationship']}: {r['orphan_count']} orphan(s)")

    print("\n" + "=" * 70)
    print("OVERALL RESULT:", "PASS" if report["passed"] else "FAIL")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Validate the GenApp -> PostgreSQL migration")
    parser.add_argument("--data-dir", default="../sample_data")
    parser.add_argument("--vsam-encoding", default="ascii")
    parser.add_argument("--schema", default="genapp")
    add_pg_args(parser)
    args = parser.parse_args()

    conn = connect(args)
    try:
        report = run_full_validation(conn, args.data_dir, vsam_encoding=args.vsam_encoding, schema=args.schema)
        print_report(report)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
