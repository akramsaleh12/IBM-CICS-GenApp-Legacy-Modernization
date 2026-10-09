"""
load_vsam_policy.py
----------------------
Loads a KSDSPOLY fixed-width VSAM extract (64 bytes/record, see
copybooks/derived_vsam_policy.cpy) into genapp.policy plus the
appropriate one of genapp.{endowment,house,motor,commercial}, chosen
by the leading POLICY-REQUEST-ID discriminator byte (C/E/H/M) - this
is the REDEFINES-by-discriminator flattening pattern described in
docs/MIGRATION_BLUEPRINT.md Section 2.

IMPORTANT - VSAM SUMMARY RECORD LIMITATION:
KSDSPOLY is a summary/index record (64 bytes total) - it does NOT
carry every column the DB2-mode policy/endowment/house/motor/
commercial tables have (issue_date, expiry_date, broker_id, payment,
commission, and most type-specific detail fields are DB2-only). Rows
loaded from VSAM will have those columns left NULL. If you are
migrating a shop that ran GenApp in VSAM-only mode (no DB2 side),
either accept the narrower record as-is, or backfill from another
source of record if completeness of those fields matters downstream.
Where a migration runs BOTH the VSAM and DB2 loaders against
overlapping data, load DB2 first (db2_loader.py) - the VSAM pass
below then performs an UPSERT that fills the summary columns without
blanking out the DB2-only columns already populated.

USAGE:
    python3 load_vsam_policy.py --data ../reference/data/ksdspoly.txt \
        --encoding ascii --host localhost --dbname genapp --user postgres
"""
import argparse
import sys

from copybook_parser import parse_copybook, record_length
from ebcdic_utils import decode_field
from db_connect import add_pg_args, connect
from vsam_io import read_records

COPYBOOK_PATH = "../copybooks/derived_vsam_policy.cpy"

# Maps POLICY-REQUEST-ID -> (target detail table, {leaf COBOL name: pg column})
TYPE_DISPATCH = {
    "C": ("commercial", {
        "POLICY-C-POSTCODE": "zipcode",
        "POLICY-C-STATUS": "status",
        "POLICY-C-CUSTOMER": "customer",
    }),
    "E": ("endowment", {
        "POLICY-E-WITH-PROFITS": "with_profits",
        "POLICY-E-EQUITIES": "equities",
        "POLICY-E-MANAGED-FUND": "managed_fund",
        "POLICY-E-FUND-NAME": "fund_name",
        "POLICY-E-LIFE-ASSURED": "life_assured",
    }),
    "H": ("house", {
        "POLICY-H-PROPERTY-TYPE": "property_type",
        "POLICY-H-BEDROOMS": "bedrooms",
        "POLICY-H-VALUE": "value",
        "POLICY-H-POSTCODE": "postcode",
        "POLICY-H-HOUSE-NAME": "house_name",
    }),
    "M": ("motor", {
        "POLICY-M-MAKE": "make",
        "POLICY-M-MODEL": "model",
        "POLICY-M-VALUE": "value",
        "POLICY-M-REGNUMBER": "reg_number",
    }),
}


def _leaf_by_name(roots, redefine_name):
    """Find leaf fields under a specific REDEFINES variant group by the
    variant group's COBOL name (e.g. 'POLICY-E-DATA')."""
    def walk(nodes):
        for n in nodes:
            if n.name == redefine_name:
                return n.children
            if n.children:
                found = walk(n.children)
                if found:
                    return found
        return None
    return walk(roots) or []


def load(data_path: str, conn, encoding: str, schema: str = "genapp") -> dict:
    with open(COPYBOOK_PATH) as fh:
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

    cur = conn.cursor()
    counts = {"policy": 0, "commercial": 0, "endowment": 0, "house": 0, "motor": 0, "skipped": 0}

    for raw in read_records(data_path, rec_len):
        type_char = decode_field(
            raw[request_id_field.offset:request_id_field.offset + request_id_field.length],
            request_id_field, codec=encoding,
        ).strip().upper()

        if type_char not in TYPE_DISPATCH:
            print(f"WARNING: unknown policy type '{type_char}' - record skipped", file=sys.stderr)
            counts["skipped"] += 1
            continue

        cust_num = decode_field(
            raw[cust_num_field.offset:cust_num_field.offset + cust_num_field.length],
            cust_num_field, codec=encoding,
        ).strip()
        policy_num = decode_field(
            raw[policy_num_field.offset:policy_num_field.offset + policy_num_field.length],
            policy_num_field, codec=encoding,
        ).strip()

        cur.execute(
            f"""INSERT INTO {schema}.policy (policy_number, customer_number, policy_type)
                OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s)
                ON CONFLICT (policy_number) DO UPDATE SET
                    customer_number = EXCLUDED.customer_number,
                    policy_type = EXCLUDED.policy_type""",
            (int(policy_num), int(cust_num), type_char),
        )
        counts["policy"] += 1

        table, field_col_map = TYPE_DISPATCH[type_char]
        detail_row = {"policy_number": int(policy_num)}
        for leaf in variant_leaves_cache[type_char]:
            col = field_col_map.get(leaf.name)
            if not col:
                continue
            seg = raw[leaf.offset: leaf.offset + leaf.length]
            detail_row[col] = decode_field(seg, leaf, codec=encoding)

        cols = list(detail_row.keys())
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        update_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "policy_number")
        cur.execute(
            f"INSERT INTO {schema}.{table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT (policy_number) DO UPDATE SET {update_clause}",
            [detail_row[c] for c in cols],
        )
        counts[table] += 1

    conn.commit()
    return counts


def main():
    parser = argparse.ArgumentParser(description="Load a KSDSPOLY VSAM extract into PostgreSQL")
    parser.add_argument("--data", required=True)
    parser.add_argument("--encoding", default="cp037",
                         help="Source byte encoding: cp037 (real mainframe EBCDIC binary, default) "
                              "or ascii/utf-8 (pre-transcoded text extracts)")
    parser.add_argument("--schema", default="genapp")
    add_pg_args(parser)
    args = parser.parse_args()

    conn = connect(args)
    try:
        counts = load(args.data, conn, encoding=args.encoding, schema=args.schema)
        print(f"Done: {counts}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
