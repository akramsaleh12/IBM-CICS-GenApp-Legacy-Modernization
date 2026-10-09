# GenApp (DB2 + VSAM) → PostgreSQL Migration Toolkit

This package migrates IBM's **GenApp** insurance sample application
(the source found in your `source.zip`) from its mainframe backends —
**DB2 for z/OS** (`customer`, `customer_secure`, `policy`, `endowment`,
`house`, `motor`, `commercial`, `claim`) and **VSAM KSDS**
(`KSDSCUST`, `KSDSPOLY`) — into a single PostgreSQL database.

Everything in this package has been **built and tested end-to-end
against your real extracted source** (copybooks, DB2 DDL, and the
sample data files `reference/data/ksdscust.txt` /
`reference/data/ksdspoly.txt`), not a generic template.

For the *why* behind every design decision (type mappings, how the
REDEFINES-by-policy-type VSAM record is flattened, schema conversion
rules, EBCDIC/COMP-3 unpacking), see
**[`docs/MIGRATION_BLUEPRINT.md`](docs/MIGRATION_BLUEPRINT.md)**.
This README is the "how do I run it" companion to that document.

---

## What's in this package

```
GenApp_migration/
├── docs/
│   └── MIGRATION_BLUEPRINT.md   ← full technical blueprint (read this first)
├── copybooks/
│   ├── derived_vsam_customer.cpy  ← reverse-engineered KSDSCUST record (225 bytes)
│   ├── derived_vsam_policy.cpy    ← reverse-engineered KSDSPOLY record (64 bytes, REDEFINES by type)
│   └── *.cpy                      ← original copybooks from source.zip, unmodified
├── ddl/
│   └── db2_source_schema.sql    ← the real DB2 DDL, extracted from reference/jcl/db2cre.jcl
├── sql/
│   ├── 01_schema.sql            ← creates the "genapp" PostgreSQL schema
│   ├── 02_target_schema.sql     ← all 8 target tables, translated from ddl/db2_source_schema.sql
│   └── 03_comments.sql          ← COMMENT ON TABLE/COLUMN metadata (the data dictionary source of truth)
├── scripts/
│   ├── copybook_parser.py       ← COBOL copybook → byte-offset field model (generic, reusable)
│   ├── ebcdic_utils.py          ← EBCDIC/COMP-3/COMP decoding primitives (generic, reusable)
│   ├── vsam_io.py               ← fixed-width record reader (handles both true binary and text sample files)
│   ├── db_connect.py            ← shared PostgreSQL connection config
│   ├── load_vsam_customer.py    ← loads KSDSCUST → genapp.customer
│   ├── load_vsam_policy.py      ← loads KSDSPOLY → genapp.policy + endowment/house/motor/commercial
│   ├── db2_loader.py            ← loads DB2 CSV/delimited unloads → any target table via COPY
│   └── run_migration.py         ← orchestrates all of the above in the correct order
├── sample_data/                 ← ready-to-run test data (copies of the real files from source.zip)
├── streamlit_app/
│   ├── app.py                   ← popup table selector + row viewer for genapp
│   ├── data_dictionary_app.py   ← popup table selector + column data dictionary viewer
│   └── requirements.txt
└── reference/                   ← original source.zip contents, kept for traceability
    ├── cobol/                   ← all COBOL programs from source.zip
    ├── jcl/db2cre.jcl           ← the authoritative DB2 DDL source
    └── data/                    ← original ksdscust.txt / ksdspoly.txt
```

---

## Prerequisites

- Python 3.9+
- `psycopg2-binary`:
  ```bash
  pip install psycopg2-binary --break-system-packages
  ```
- A reachable PostgreSQL **server** (the `genapp` database itself does
  **not** need to exist yet — `run_migration.py` creates it
  automatically on first run). This package was tested against:
  ```
  host = localhost
  port = 5432
  dbname = genapp
  user = postgres
  password = CHANGE_ME_LOCAL_ONLY
  ```
  (matching the connection defaults already wired into
  `scripts/db_connect.py` — every script also accepts `--host`,
  `--port`, `--dbname`, `--user`, `--password` flags, or reads the
  standard `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`
  environment variables, if your environment differs.)

> **Note:** `run_migration.py` creates the database and applies DDL
> entirely through `psycopg2` — it does **not** shell out to the
> `psql` command-line client, so you do not need `psql` installed or
> on your `PATH` at all (this matters especially on Windows, where
> PostgreSQL's client tools often aren't added to `PATH` by default
> even when the server itself is running). Only `psycopg2-binary` is
> required for Option A below.

---

## Run sequence

### Option A — one command (recommended)

From inside `scripts/`:

```bash
cd scripts
python3 run_migration.py --data-dir ../sample_data \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
```

This applies both DDL files, then loads `ksdscust.txt` → `customer`,
`ksdspoly.txt` → `policy` + detail tables, then any DB2 CSVs present
in `sample_data/` (`claim.csv`, `customer_secure.csv`). It is
**idempotent** — every load uses `INSERT ... ON CONFLICT DO UPDATE`
(the VSAM loaders directly; the DB2 CSV loader via a temp staging
table + upsert on the target's primary key), and the DDL uses
`CREATE TABLE/INDEX IF NOT EXISTS`, so re-running this command
multiple times against the same database is always safe and never
produces duplicate rows or a "relation already exists" error.

Expected output ends with:
```
Migration run complete.
```

### Option B — step by step (useful when adapting to your real extracts)

**1. Create the database, schema, and tables**

The `genapp` database itself must exist before `psql -d genapp ...` can
connect to it. Create it once (skip this if it already exists):

```bash
psql -h localhost -U postgres -c "CREATE DATABASE genapp;"
```

Then apply the schema and tables:

```bash
cd sql
psql -h localhost -U postgres -d genapp -f 01_schema.sql
psql -h localhost -U postgres -d genapp -f 02_target_schema.sql
psql -h localhost -U postgres -d genapp -f 03_comments.sql
```

> If you don't have the `psql` command-line client available (common
> on Windows even when the PostgreSQL server itself is running), skip
> straight to **Option A** instead — `run_migration.py` creates the
> database and applies this same DDL entirely through `psycopg2`, no
> `psql` required.

**2. Load the VSAM customer file**

```bash
cd ../scripts
python3 load_vsam_customer.py \
    --data ../sample_data/ksdscust.txt --encoding ascii \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
```

> `--encoding ascii` is correct for the sample file shipped in this
> package. **A real mainframe extract will be EBCDIC binary** — use
> `--encoding cp037` (the default if you omit the flag) instead. See
> `docs/MIGRATION_BLUEPRINT.md` Section 4.1 for how to tell the
> difference and how to produce a proper binary extract via IDCAMS
> REPRO + binary FTP.

**3. Load the VSAM policy file** (must run after step 2 — policy rows
have a foreign key to customer)

```bash
python3 load_vsam_policy.py \
    --data ../sample_data/ksdspoly.txt --encoding ascii \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
```

Each record is automatically dispatched to `genapp.policy` plus the
correct one of `endowment`/`house`/`motor`/`commercial` based on its
type discriminator byte — no manual sorting required.

**4. Load any DB2 CSV unloads** (must run after steps 2-3 for tables
with foreign keys to customer/policy)

```bash
python3 db2_loader.py --csv ../sample_data/claim.csv --table claim --schema genapp \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY

python3 db2_loader.py --csv ../sample_data/customer_secure.csv --table customer_secure --schema genapp \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
```

Produce these CSVs from a real DB2 system with the standard `EXPORT`
utility, e.g.:
```sql
EXPORT TO claim.csv OF DEL
    MODIFIED BY COLDEL, CHARDEL""
    SELECT * FROM <DB2DBID>.Claim;
```

---

## Verifying the result

```bash
psql -h localhost -U postgres -d genapp -c "
SELECT 'customer' t, count(*) FROM genapp.customer UNION ALL
SELECT 'customer_secure', count(*) FROM genapp.customer_secure UNION ALL
SELECT 'policy', count(*) FROM genapp.policy UNION ALL
SELECT 'endowment', count(*) FROM genapp.endowment UNION ALL
SELECT 'house', count(*) FROM genapp.house UNION ALL
SELECT 'motor', count(*) FROM genapp.motor UNION ALL
SELECT 'commercial', count(*) FROM genapp.commercial UNION ALL
SELECT 'claim', count(*) FROM genapp.claim;"
```

Against the sample data in this package, this should return:

| table | count |
|---|---|
| customer | 10 |
| customer_secure | 2 |
| policy | 10 |
| endowment | 2 |
| house | 3 |
| motor | 3 |
| commercial | 2 |
| claim | 2 |

A relational sanity check — every policy should join back to a real
customer, and every claim to a real policy:

```sql
SELECT p.policy_number, p.policy_type, c.first_name, c.last_name
FROM genapp.policy p JOIN genapp.customer c USING (customer_number)
ORDER BY p.policy_number;

SELECT cl.claim_number, cl.cause, p.policy_type
FROM genapp.claim cl JOIN genapp.policy p USING (policy_number);
```

---

## Adapting this to your real (non-sample) extracts

1. **Get real VSAM extracts off the mainframe**: `IDCAMS REPRO` the
   `KSDSCUST`/`KSDSPOLY` clusters to sequential datasets, then transfer
   them to this host with **binary-mode FTP** (or DFSMS/zFS/SFTP as
   your shop supports) — never text/ASCII mode, which corrupts
   packed/binary fields. Point `load_vsam_customer.py` /
   `load_vsam_policy.py` at the resulting files with `--encoding cp037`.
2. **Get real DB2 unloads**: run the `EXPORT` command shown above (or
   your shop's equivalent) for each of `customer`, `customer_secure`,
   `policy`, `endowment`, `house`, `motor`, `commercial`, `claim`, and
   point `db2_loader.py` at each resulting CSV.
3. **If your copybooks differ from `derived_vsam_customer.cpy` /
   `derived_vsam_policy.cpy`** (e.g. this is a customized fork of
   GenApp), re-derive the physical record layout the same way this
   package did: find the `EXEC CICS WRITE FILE(...) FROM(...)
   LENGTH(...)` statement in the relevant COBOL program and trace what
   working-storage structure `FROM(...)` actually points to — it is
   often *not* the same structure named in the file's copybook. Then
   update the `.cpy` file and re-run:
   ```bash
   python3 copybook_parser.py ../copybooks/your_new_copybook.cpy
   ```
   to sanity-check the computed byte offsets and total record length
   against your real record length before loading any data.

---

## Browsing the migrated data: Streamlit apps

Two small Streamlit apps live in `streamlit_app/`, both using the
same popup table selector (click **📋 Select table**):

- **`app.py`** — row viewer. Pick a table and its rows load in a
  paginated, filterable, downloadable grid.
- **`data_dictionary_app.py`** — data dictionary. Pick a table and see
  every column's name, type, length/precision, nullable, primary/
  foreign key info, and a business description — read from native
  PostgreSQL `COMMENT ON COLUMN` metadata applied by
  `sql/03_comments.sql` (already included in `run_migration.py`'s DDL
  sequence, so a fresh migration run has descriptions populated
  automatically).

```bash
cd streamlit_app
pip install -r requirements.txt --break-system-packages
streamlit run app.py                    # row viewer, port 8501
# or, in another terminal:
streamlit run data_dictionary_app.py --server.port 8502   # data dictionary
```

Each opens at `http://localhost:<port>`. Connection settings (host,
port, database, user, password, schema) are editable from the sidebar
in both apps and default to the same `genapp`/`postgres`/`CHANGE_ME_LOCAL_ONLY`
values used throughout this project — change them there if your
server differs, no code edits needed.

If a table you're viewing in the data dictionary shows blank
Description cells, `sql/03_comments.sql` hasn't been applied to that
database yet — run it once:
```bash
psql -h localhost -U postgres -d genapp -f sql/03_comments.sql
```
(or just re-run `run_migration.py`, which applies it automatically).

---

## Known data-quality findings from this run

Running this toolkit against the sample data surfaced one real
anomaly worth flagging before a production cutover: in
`ksdspoly.txt`, the `HOUSE` policy for customer 4 (policy 6) has a
`bedrooms` field containing `"5 0"` (a stray space) instead of a
zero-padded `"005"`, which numeric-digit extraction currently parses
as `50` rather than the evidently-intended `5`. This is exactly the
kind of issue a byte-precise migration tool is supposed to catch
before it reaches production — validate a sample of numeric DISPLAY
fields from your real extracts the same way (spot-check a handful of
rows post-load against the source) before trusting a full cutover.
