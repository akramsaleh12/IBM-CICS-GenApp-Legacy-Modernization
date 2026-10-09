# CRUD Matrix — GenApp (General Insurance Application)
### Legacy Modernization Assessment

Maps every program to the exact **C**reate/**R**ead/**U**pdate/**D**elete operations it performs against each Db2 table, VSAM file, and operational data store. Verified directly against every `EXEC SQL`/`EXEC CICS READ|WRITE|REWRITE|DELETE FILE` statement in the 31 COBOL programs (not inferred from naming convention alone).

---

## 1. Program × Db2 Table CRUD Matrix

| Program | `customer` | `customer_secure` | `policy` | `endowment` | `house` | `motor` | `commercial` | `claim` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `LGACDB01` | **C** | — | — | — | — | — | — | — |
| `LGACDB02` | — | **C** | — | — | — | — | — | — |
| `LGICDB01` | **R** | — | — | — | — | — | — | — |
| `LGUCDB01` | **U** | — | — | — | — | — | — | — |
| `LGAPDB01` | — | — | **C** | **C**¹ | **C**¹ | **C**¹ | **C**¹ | — |
| `LGIPDB01` | — | — | **R** | **R**¹ | **R**¹ | **R**¹ | **R**¹ | — |
| `LGUPDB01` | — | — | **R+U** | **U**¹ | **U**¹ | **U**¹ | — | — |
| `LGDPDB01` | — | — | **D** | (cascade) | (cascade) | (cascade) | (cascade) | (cascade) |
| *(no program)* | — | — | — | — | — | — | — | **—** |

¹ Only one of `endowment`/`house`/`motor`/`commercial` is actually touched per invocation — the specific table is selected at runtime by `policyType` (`CA-REQUEST-ID` suffix `EMOT`/`END`/`HOU`/`COM`). The matrix shows the union of all four type-branches the program *contains*, not four simultaneous operations.

**Key observations:**
- **No program ever performs Create, Update, or Delete against `customer_secure` after its initial insert** — `LGACDB02` is Create-only; there is no corresponding Read/Update/Delete program anywhere in the codebase (confirmed in the Business Rules report — the password field is write-only).
- **`claim` has zero CRUD coverage from any program** — the only "operation" against it is the implicit cascade-delete triggered when its parent `policy` row is deleted. No program inserts, reads, or explicitly deletes a claim.
- **`LGDPDB01` (Delete Policy) explicitly deletes only `policy`** — the four type-detail tables and `claim` are removed via Db2's `ON DELETE CASCADE`, not by explicit `DELETE` statements in COBOL. This means the "D" for those five columns is enforced by the DBMS, not by application code — an important distinction for any migration target that doesn't have cascade-delete (e.g., some NoSQL stores), where equivalent explicit-delete logic would need to be added.
- **`LGAPDB01` and `LGUPDB01` both touch two tables per call** (`policy` + one type table) — confirming the "wide, not deep" complexity pattern identified in the Complexity Analysis report.

---

## 2. Program × VSAM File CRUD Matrix

| Program | `KSDSCUST` | `KSDSPOLY` |
|---|:---:|:---:|
| `LGACVS01` | **C** (Write) | — |
| `LGICVS01` | **R** (Read) | — |
| `LGUCVS01` | **R+U** (Read then Rewrite) | — |
| `LGAPVS01` | — | **C** (Write) |
| `LGIPVS01` | — | **R** (Read) |
| `LGUPVS01` | — | **R+U** (Read then Rewrite) |
| `LGDPVS01` | — | **D** (Delete) |

**Key observations:**
- Every VSAM program implements **exactly one CRUD verb** (or one Read+Update pair for the Update case) against **exactly one file** — the cleanest, most uniform tier in the entire portfolio (consistent with the Complexity Analysis report's "VSAM tier is uniformly simple" finding).
- **No VSAM program ever deletes a `KSDSCUST` record** — there is no "Delete Customer" function anywhere in the application (confirmed again here at the data layer), and the two files' CRUD coverage is a mirror-image subset of the Db2 coverage: Customer gets C/R/U (no D); Policy gets full C/R/U/D.

---

## 3. Program × Operational Data Store CRUD Matrix

| Program | `GENAERRS` (TSQ) | `GENACNTL` (TSQ) | Transaction-stat TSQ | Named Counters |
|---|:---:|:---:|:---:|:---:|
| `LGSTSQ` | **C** (Write, called by 20 other programs) | — | — | — |
| `LGTESTC1` | — | **C** (Write, on Add Customer) | — | — |
| `LGSETUP` | **C/D** (Delete-then-Define, 37 pairs) | **D** (initial delete/reset) | **D** (initial delete/reset) | **C/D** (Delete-then-Define, ~24 counters) |
| `LGACDB01` | — | — | — | **R+U** (Get/increment `GENACUSTNUM`) |
| `LGASTAT1` | — | — | — | **U** (increment per-function counters) |
| `LGWEBST5` | — | — | **C** (write stats every 60s) | **R** (read counter values to report) |

**Key observations:**
- These are **write-mostly, read-rarely** stores — consistent with the Business Rules report's finding that operational data (error logs, statistics) is captured but essentially never read back programmatically by the application itself (only by external monitoring/CICSPlex SM tooling).
- `LGSETUP`'s "C/D" pattern (Delete-then-Define) is a **re-initialization** idiom, not ongoing CRUD — it resets these resources to empty/zero at environment setup time, not during normal transaction processing.

---

## 4. Entity-Level CRUD Summary (Business View)

Consolidating Sections 1–2 into the business-entity view most useful for migration planning — **which functions exist, and which don't**, per entity:

| Entity | Create | Read | Update | Delete | Notes |
|---|:---:|:---:|:---:|:---:|---|
| **Customer** | ✅ | ✅ | ✅ | ❌ | No delete function exists at any layer (COBOL, Db2, or VSAM) |
| **Customer security (password)** | ✅ | ❌ | ❌ | *(cascade only)* | Write-only; never read, updated, or independently deleted — flagged as dead/non-functional security data |
| **Policy (master)** | ✅ | ✅ | ✅ | ✅ | Full CRUD — the only entity with all four operations implemented |
| **Motor policy detail** | ✅ | ✅ | ✅ | *(cascade only)* | Full CRUD via parent Policy Delete (Db2 cascade); no standalone delete of just the detail row |
| **Endowment policy detail** | ✅ | ✅ | ✅ | *(cascade only)* | Same pattern as Motor |
| **House policy detail** | ✅ | ✅ | ✅ | *(cascade only)* | Same pattern as Motor |
| **Commercial policy detail** | ✅ | ✅ (4 search modes) | ❌ | *(cascade only)* | **No Update function** — the only policy type that cannot be amended once created (see Transaction Matrix report, Section 2) |
| **Claim** | ❌ | ❌ | ❌ | *(cascade only)* | Schema exists; zero application-level CRUD — confirmed gap, recommend confirming scope with the business |

---

## 5. CRUD Completeness Gaps — Consolidated Finding

This matrix confirms, with full traceability to source, the three CRUD-completeness gaps raised across earlier reports:

| Gap | Entity | Missing Operation(s) | Where Confirmed |
|---|---|---|---|
| 1 | Customer | Delete | No `LGDCUS01`/`LGDCDB01`/`LGDCVS01`-style program exists anywhere; `LGTESTC1` menu has no delete option |
| 2 | Commercial policy | Update | `LGTESTP4` menu has only 3 options (Inquire/Add/Delete); no `LGUPDB01` branch touches `commercial` |
| 3 | Claim | Create, Read, Update, explicit Delete | Table and FK exist in `db2cre.jcl`; zero COBOL programs reference it |
| 4 | Customer security | Read, Update, standalone Delete | `LGACDB02` is the only program touching `customer_secure`; write-once, never revisited |

**Modernization guidance:** before treating this as a template for a full CRUD API surface, confirm with the business whether gaps 1–4 are intentional (e.g., customers are never deleted for audit/compliance reasons; commercial policies are cancel-and-rewrite rather than amend; claims processing lives in a separate system) or are simply incomplete demo coverage. A migrated system should not silently "complete" these CRUD sets without that confirmation, since gap 1 (no customer delete) in particular may reflect a deliberate data-retention policy rather than an oversight.

---

*Generated from static analysis of every `EXEC SQL` and `EXEC CICS READ/WRITE/REWRITE/DELETE FILE` statement across all 31 COBOL programs in the uploaded source package, cross-referenced with `db2cre.jcl` (foreign-key cascade behavior) and the Transaction Matrix and Business Rules reports for entity/function context.*
