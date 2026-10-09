"""
load_vsam_customer.py
-----------------------
Loads a KSDSCUST fixed-width VSAM extract (225 bytes/record, see
copybooks/derived_vsam_customer.cpy) into genapp.customer.

Real mainframe VSAM extracts (via IDCAMS REPRO to a sequential
dataset, then FTP'd BINARY to this host) are EBCDIC-encoded and
should be loaded with --encoding cp037 (the default). The sample
file shipped in reference/data/ksdscust.txt is a pre-transcoded
plain-ASCII convenience copy for local testing; load it with
--encoding ascii.

USAGE (production EBCDIC binary extract):
    python3 load_vsam_customer.py --data /path/to/KSDSCUST.bin \
        --host localhost --dbname genapp --user postgres

USAGE (ASCII sample data from reference/data/):
    python3 load_vsam_customer.py --data ../reference/data/ksdscust.txt \
        --encoding ascii --host localhost --dbname genapp --user postgres
"""
import argparse

from copybook_parser import parse_copybook, flatten, record_length
from ebcdic_utils import decode_field
from db_connect import add_pg_args, connect
from vsam_io import read_records

COPYBOOK_PATH = "../copybooks/derived_vsam_customer.cpy"


def load(data_path: str, conn, encoding: str, schema: str = "genapp") -> int:
    with open(COPYBOOK_PATH) as fh:
        roots = parse_copybook(fh.read())
    root = roots[0]
    leaves = flatten(roots)
    rec_len = record_length(roots)

    # COBOL field -> target column name (VSAM record is a superset of
    # DB2's customer table minus num_policies, which is a derived count
    # kept only in the VSAM commarea, not persisted in DB2 - dropped here)
    col_map = {
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
        # CUST-NUM-POLICIES intentionally not mapped (see note above)
    }

    cur = conn.cursor()
    rows = []
    for raw in read_records(data_path, rec_len):
        row = {}
        for leaf in leaves:
            col = col_map.get(leaf.name)
            if not col:
                continue
            seg = raw[leaf.offset: leaf.offset + leaf.length]
            row[col] = decode_field(seg, leaf, codec=encoding)
        rows.append(row)

    if not rows:
        return 0

    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    update_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "customer_number")
    sql = (f"INSERT INTO {schema}.customer ({col_list}) OVERRIDING SYSTEM VALUE "
           f"VALUES ({placeholders}) "
           f"ON CONFLICT (customer_number) DO UPDATE SET {update_clause}")
    values = [[row.get(c) for c in cols] for row in rows]
    cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Load a KSDSCUST VSAM extract into PostgreSQL")
    parser.add_argument("--data", required=True)
    parser.add_argument("--encoding", default="cp037",
                         help="Source byte encoding: cp037 (real mainframe EBCDIC binary, default) "
                              "or ascii/utf-8 (pre-transcoded text extracts)")
    parser.add_argument("--schema", default="genapp")
    add_pg_args(parser)
    args = parser.parse_args()

    conn = connect(args)
    try:
        n = load(args.data, conn, encoding=args.encoding, schema=args.schema)
        print(f"Done: {n} customer records loaded into {args.schema}.customer")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
