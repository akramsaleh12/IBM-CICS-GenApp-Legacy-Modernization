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
│   ├── 03_comments.sql          ← COMMENT ON TABLE/COLUMN metadata (the data dictionary source of truth)
│   └── 04_business_rules.sql    ← customer.last_changed column + auto-update triggers, for the business services layer
├── scripts/
│   ├── copybook_parser.py       ← COBOL copybook → byte-offset field model (generic, reusable)
│   ├── ebcdic_utils.py          ← EBCDIC/COMP-3/COMP decoding primitives (generic, reusable)
│   ├── vsam_io.py               ← fixed-width record reader (handles both true binary and text sample files)
│   ├── db_connect.py            ← shared PostgreSQL connection config
│   ├── load_vsam_customer.py    ← loads KSDSCUST → genapp.customer
│   ├── load_vsam_policy.py      ← loads KSDSPOLY → genapp.policy + endowment/house/motor/commercial
│   ├── db2_loader.py            ← loads DB2 CSV/delimited unloads → any target table via COPY
│   ├── validate_migration.py    ← re-decodes source files and diffs field-by-field against PostgreSQL
│   └── run_migration.py         ← orchestrates all of the above in the correct order (--validate to also validate)
├── sample_data/                 ← ready-to-run test data (copies of the real files from source.zip)
├── streamlit_app/
│   ├── app.py                   ← popup table selector + row viewer for genapp
│   ├── data_dictionary_app.py   ← popup table selector + column data dictionary viewer
│   ├── validation_app.py        ← popup check selector + migration validation viewer
│   └── requirements.txt
├── api/                         ← FastAPI REST API over genapp
│   ├── main.py                  ← app entry point (uvicorn main:app)
│   ├── database.py              ← connection pool + FastAPI dependency
│   ├── schemas.py                ← Pydantic request/response models, one set per table
│   ├── crud.py                  ← generic CRUD router factory used by every table router
│   ├── business_services/       ← Business Logic tier - see "Business services" below
│   │   ├── customer_service.py  ← CustomerService (LGACUS01/LGICUS01/LGUCUS01 equivalent)
│   │   ├── policy_service.py    ← PolicyService, type-parameterized (LGAPOL01/LGIPOL01/LGUPOL01/LGDPOL01)
│   │   ├── claim_service.py     ← ClaimService (net-new, no legacy equivalent)
│   │   └── exceptions.py        ← typed exceptions carrying legacy CA-RETURN-CODE values
│   ├── test_business_services.py ← pytest suite (15 tests) for the business services layer
│   ├── routers/                 ← one router per table + composite/meta/business endpoints
│   └── requirements.txt
└── reference/                   ← original source.zip contents, kept for traceability
    ├── 01-analysis/             ← business rules, CRUD matrix, and legacy-to-modern mapping reports
    │                               that business_services/ is directly built from
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
psql -h localhost -U postgres -d genapp -f 04_business_rules.sql
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

Three small Streamlit apps live in `streamlit_app/`, all using the
same popup selector pattern (click **📋 Select table** or **🔍 Select
check**):

- **`app.py`** — row viewer. Pick a table and its rows load in a
  paginated, filterable, downloadable grid.
- **`data_dictionary_app.py`** — data dictionary. Pick a table and see
  every column's name, type, length/precision, nullable, primary/
  foreign key info, and a business description — read from native
  PostgreSQL `COMMENT ON COLUMN` metadata applied by
  `sql/03_comments.sql` (already included in `run_migration.py`'s DDL
  sequence, so a fresh migration run has descriptions populated
  automatically).
- **`validation_app.py`** — migration validation. Click **▶️ Run
  validation** to re-decode every source file and diff it against
  PostgreSQL field-by-field, then **🔍 Select check** to drill into
  any of the checks that ran. See "Migration validation" below for
  the full detail.

```bash
cd streamlit_app
pip install -r requirements.txt --break-system-packages
streamlit run app.py                                       # row viewer, port 8501
# in another terminal:
streamlit run data_dictionary_app.py --server.port 8502    # data dictionary
# in another terminal:
streamlit run validation_app.py --server.port 8503         # migration validation
```

Each opens at `http://localhost:<port>`. Connection settings (host,
port, database, user, password, schema) are editable from the sidebar
in every app and default to the same `genapp`/`postgres`/`CHANGE_ME_LOCAL_ONLY`
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

## Migration validation

`scripts/validate_migration.py` proves the migration is correct, not
just that it ran. It re-decodes every source record from scratch
(VSAM bytes and DB2 CSV rows, using the exact same copybook/EBCDIC
logic the loaders used) and diffs it field-by-field against what's
actually sitting in PostgreSQL — a pass means the target data is
byte-for-byte faithful to the source, not merely "present."

**Checks performed:**
1. **Row/key coverage** — every source record's key exists in the target
2. **Field-level accuracy** — every mapped field matches exactly
3. **Type-dispatch integrity** — every policy has exactly one detail
   row, in the correct one of `endowment`/`house`/`motor`/`commercial`
4. **Referential integrity** — no orphaned foreign keys
5. **Source data-quality anomalies** — numeric DISPLAY fields
   containing non-digit characters are flagged separately from
   mismatches, since they're a *source* data problem, not a migration
   bug (this is exactly the class of issue that caught the malformed
   `bedrooms`/`status` fields in `ksdspoly.txt` — see below)

**Run it standalone:**
```bash
cd scripts
python3 validate_migration.py --data-dir ../sample_data \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
```

**Or run it automatically right after a migration**, by adding
`--validate` to `run_migration.py`:
```bash
python3 run_migration.py --data-dir ../sample_data --validate \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
```

**Or use the Streamlit UI** — `streamlit_app/validation_app.py` uses
the same popup pattern as the other two apps: click **▶️ Run
validation** in the sidebar, then **🔍 Select check** to open a popup
listing every check that ran (with a ✅/❌ badge each), and pick one
to see its full detail — missing keys, field-level mismatches, or
anomalies, in a downloadable table. An overall PASS/FAIL summary and
a JSON report download are always available at the top.
```bash
cd streamlit_app
streamlit run validation_app.py --server.port 8503
```

To confirm validation actually catches real problems (not just
rubber-stamping), try deliberately corrupting a row and re-running it:
```bash
psql -h localhost -U postgres -d genapp -c \
    "UPDATE genapp.customer SET last_name = 'CORRUPTED' WHERE customer_number = 1;"
python3 scripts/validate_migration.py --data-dir sample_data \
    --host localhost --dbname genapp --user postgres --password CHANGE_ME_LOCAL_ONLY
# then restore it:
psql -h localhost -U postgres -d genapp -c \
    "UPDATE genapp.customer SET last_name = 'PANDY' WHERE customer_number = 1;"
```

---

## REST API

`api/` is a FastAPI application exposing full CRUD over all 8 tables,
plus a few composite/introspection endpoints that hide the migration's
internal complexity behind simple calls:

| Endpoint | What it does |
|---|---|
| `GET/POST /customers`, `GET/PUT/DELETE /customers/{id}` | Full CRUD on customers |
| `GET /customers/{id}/policies` | All policies held by a customer |
| `GET/POST /policies`, `GET/PUT/DELETE /policies/{id}` | Full CRUD on policy headers |
| `GET /policies/{id}/detail` | Policy joined with its type-specific detail row — hides the REDEFINES-by-policy-type dispatch (see blueprint Section 2) behind one call |
| `GET /policies/{id}/claims` | All claims filed against a policy |
| `GET/POST /endowments`, `/houses`, `/motors`, `/commercials` (+ `{id}` for GET/PUT/DELETE) | Full CRUD on each policy-type detail table |
| `GET/POST /claims`, `GET/PUT/DELETE /claims/{id}` | Full CRUD on claims |
| `GET/POST /customer-secure`, `GET/PUT/DELETE /customer-secure/{id}` | CRUD on auth credentials — `customer_pass` is never returned in any response, by design |
| `GET /tables` | Same table listing as the data dictionary app |
| `GET /tables/{table}/columns` | Full column-level data dictionary (type, nullable, PK/FK, description) for one table |
| `GET /validate` | Runs `validate_migration.py` live and returns the full JSON report — the same checks documented above, available over HTTP |

**Run it:**
```bash
cd api
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload
```

Opens at `http://localhost:8000`. Interactive Swagger docs are at
`http://localhost:8000/docs` (try every endpoint from the browser,
including request bodies); ReDoc is at `http://localhost:8000/redoc`.

Connection settings come from the standard `PGHOST`/`PGPORT`/
`PGDATABASE`/`PGUSER`/`PGPASSWORD` environment variables (same
`genapp`/`postgres`/`CHANGE_ME_LOCAL_ONLY` defaults as the rest of this project);
set them before launching `uvicorn` if your server differs, e.g.:
```bash
PGHOST=myhost PGPASSWORD=mypass uvicorn main:app --reload
```

**Example calls:**
```bash
curl http://localhost:8000/customers/1
curl http://localhost:8000/customers/1/policies
curl http://localhost:8000/policies/6/detail
curl -X POST http://localhost:8000/customers \
    -H "Content-Type: application/json" \
    -d '{"first_name": "JANE", "last_name": "DOE", "email_address": "jane@example.com"}'
curl "http://localhost:8000/validate?data_dir=../sample_data&vsam_encoding=ascii"
```

Foreign key violations return `422` with the database's own error
message (e.g. creating a policy for a nonexistent customer); duplicate
primary keys return `409`; a missing row returns `404` — all tested
against the real migrated data, including a full create → read →
update → delete lifecycle across `customers` → `policies` → `motors`.

---

## Business services

`api/business_services/` is the **Business Logic tier** — distinct
from the raw per-table CRUD above (the **Data Management tier**). This
distinction, and everything each service does, comes directly from a
deep analysis of the actual GenApp COBOL source
(`reference/01-analysis/`) — not assumptions. Read
`reference/01-analysis/08_Legacy_to_Modern_Mapping/GenApp_Legacy_Modern_Mapping.md`
Section 4 for the source recommendation this implements, and
`reference/01-analysis/03_business_rules/GenApp_Business_Rules.md` for
the full rule catalogue every design choice below cites.

| Layer | Path prefix | Legacy equivalent | What it does |
|---|---|---|---|
| Data Management | `/customers`, `/policies`, ... | `LGxxDB01`/`LGxxVS01` | Thin per-table CRUD, no orchestration |
| **Business Logic** | `/business/customers`, `/business/policies`, ... | `LGACUS01`/`LGAPOL01`/etc. | Orchestration + the business rules below |

### CustomerService (`LGACUS01`/`LGICUS01`/`LGUCUS01`)
- **Add**: creates the `customer` row **and** its `customer_secure`
  row atomically (one transaction — the modern equivalent of the
  legacy two-phase Db2 write). Faithfully reproduces a real legacy
  bug found during analysis: every customer gets the exact same
  hardcoded placeholder password (`preserve_legacy_password_bug=True`
  by default) — a business-services layer's job during a strangler-fig
  migration is to preserve documented behavior for parity testing, not
  silently fix things nobody asked about. Set the flag `False` for a
  random-per-customer placeholder instead (still not real hashing).
- **Update**: enforces optimistic concurrency (`If-Match` header) —
  legacy Customer updates never had this, `Policy` did; the
  Legacy-to-Modern Mapping report explicitly recommends fixing that
  inconsistency here rather than preserving it, so `sql/04_business_rules.sql`
  adds a `last_changed` column + auto-updating trigger to `customer`
  to match.
- **No delete method, on purpose** — the CRUD Matrix analysis found no
  delete-customer capability at any layer (COBOL, Db2, or VSAM) in the
  legacy system. This service preserves that as a genuine finding
  rather than silently completing the CRUD set.

### PolicyService (`LGAPOL01`/`LGIPOL01`/`LGUPOL01`/`LGDPOL01`)
One type-parameterized service instead of 4 near-duplicate ones —
consolidating exactly the "wide, not deep" duplication the source
analysis's complexity report flagged in the legacy programs.
- **Add**: creates the `policy` header **and** the correct
  `endowment`/`house`/`motor`/`commercial` detail row in one
  transaction — both commit together or neither does.
- **Update**: requires a mandatory `If-Match` header (mirrors
  `LGUPDB01`'s mandatory optimistic-concurrency check exactly);
  **blocks updates to Commercial policies by default** — the CRUD
  Matrix analysis found Commercial is the only policy type with no
  Update path in the legacy system, and explicitly flags it as
  "unclear whether intentional... worth confirming with the business."
  This service preserves the restriction rather than guessing;
  construct `PolicyService(allow_commercial_update=True)` to lift it
  once confirmed.
- **Delete**: deletes only the `policy` row and relies on
  `ON DELETE CASCADE` for the detail row and any claims — exactly
  what `LGDPDB01` does (an explicit `DELETE` for policy only; the
  Db2 cascade handles the rest, not COBOL logic).

### ClaimService — net-new, explicitly flagged
No legacy program implements claims CRUD at all (a confirmed gap in
the analysis, not an oversight in this migration). This service exists
because a real system needs *some* way to file a claim, but it's
built new, not migrated — treat its (minimal) business rules as a
starting point pending real requirements.

### Typed exceptions ↔ legacy return codes
Every business-rule violation raises a typed exception
(`NotFoundError`, `OptimisticLockError`, `ValidationError`,
`UnsupportedOperationError`, `ForeignKeyError`), each carrying the
corresponding legacy `CA-RETURN-CODE` from the Business Rules report's
return-code catalogue, surfaced in every HTTP error response for
traceability back to the source system's documented behavior:
```json
{"detail": {"message": "policy 12 is type 'C' (Commercial) - ...",
            "legacy_return_code": "99"}}
```

### Run it
Same app as the REST API above — business endpoints are already
wired in at `/business/*`:
```bash
cd api
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload
```

**Example: add a customer and a policy, with optimistic locking:**
```bash
curl -X POST http://localhost:8000/business/customers \
    -H "Content-Type: application/json" \
    -d '{"first_name": "JANE", "last_name": "DOE"}'
# -> {"customer_number": 11, ..., "last_changed": "2026-08-20T08:11:58.263459"}

curl -X POST http://localhost:8000/business/policies \
    -H "Content-Type: application/json" \
    -d '{"customer_number": 11, "policy_type": "M", "detail": {"make": "HONDA", "model": "CIVIC"}}'

curl -X PUT http://localhost:8000/business/policies/11 \
    -H "Content-Type: application/json" \
    -H "If-Match: 2026-08-20T08:11:58.263459" \
    -d '{"detail": {"value": 13000}}'
# Reusing a stale If-Match value returns 409 with legacy_return_code "02"
```

### Automated tests
```bash
cd api
pytest test_business_services.py -v
```
15 tests, covering atomic add (with rollback-on-failure verified by
checking no orphan row is left behind), 404/409/422/405 paths, the
Commercial-update block and its override, cascade delete, and the
`LGTESTC1` postcode-uppercasing rule — all run against a real
PostgreSQL database, not mocks.

### A real bug this testing caught
Building and testing `ClaimService` surfaced a genuine PostgreSQL
gotcha worth knowing about generally: inserting an **explicit** value
into a `GENERATED ... AS IDENTITY` column (exactly what every loader
in this project does, to preserve legacy customer/policy/claim
numbers) **never advances the underlying sequence** — so the next
auto-generated insert can collide with a manually-inserted key.
`scripts/resync_sequences.py` fixes this by resyncing every identity
sequence to `MAX(pk)+1` after a load; `run_migration.py` now calls it
automatically as a final step.

---

## Known data-quality findings from this run

Running `validate_migration.py` against the sample data surfaced 4
real anomalies worth flagging before a production cutover — all in
`ksdspoly.txt`, all the same class of issue (a numeric `PIC 9(n)
DISPLAY` field containing a stray space instead of zero-padding,
which currently gets parsed as a shorter/different number than
evidently intended):

| Policy | Field | Raw bytes | Parsed as | Likely intended |
|---|---|---|---|---|
| 6 (House) | `bedrooms` | `"5 0"` | `50` | `5` |
| 8 (House) | `bedrooms` | `"1 0"` | `10` | `1` |
| 9 (Commercial) | `status` | `"A  0"` | non-numeric, fails strict parse | unclear — confirm with the business |
| 10 (Commercial) | `status` | `"A  0"` | non-numeric, fails strict parse | unclear — confirm with the business |

This is exactly the kind of issue a byte-precise migration tool is
supposed to catch before it reaches production. `validate_migration.py`
flags this whole class of anomaly automatically (see "Migration
validation" above) — run it against your real extracts and review
every anomaly it reports before trusting a full cutover.
