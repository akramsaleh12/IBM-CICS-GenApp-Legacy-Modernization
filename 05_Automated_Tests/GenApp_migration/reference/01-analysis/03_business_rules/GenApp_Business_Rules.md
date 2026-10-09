# Business Rules — GenApp (General Insurance Application)
### Legacy Modernization Assessment

Derived by static analysis of the uploaded source package — every `IF`/`EVALUATE` decision, `MOVE 'nn' TO CA-RETURN-CODE`, `EXEC SQL` predicate, and field-length/COMMAREA check across all 30 COBOL programs was traced to reconstruct the rules below.

> **Scope caveat used throughout this document:** the section list requested mirrors a general banking/core-application business-rules template (Security/sign-on, User maintenance, Account rules, Batch posting, Interest and fees, Transaction-type maintenance in DB2, etc.). GenApp is an **insurance** demo application, not a banking core system, so several requested sections have **no equivalent functionality in this codebase**. Rather than invent rules that aren't there, each such section states plainly what exists, what's genuinely analogous, and what's simply absent.

---

## 1. Scope and Modules

GenApp implements four business capabilities, each with an identical 3-tier shape (Presentation → Business logic → Data management):

| Module | Presentation (3270) | Business Logic | Data Management (Db2) | Data Management (VSAM) |
|---|---|---|---|---|
| **Customer maintenance** | `LGTESTC1` (txn `SSC1`) | `LGACUS01`, `LGICUS01`, `LGUCUS01` | `LGACDB01`, `LGACDB02`, `LGICDB01`, `LGUCDB01` | `LGACVS01`, `LGICVS01`, `LGUCVS01` |
| **Motor policy** | `LGTESTP1` (txn `SSP1`) | `LGAPOL01`, `LGIPOL01`, `LGUPOL01`, `LGDPOL01` | `LGAPDB01`, `LGIPDB01`, `LGUPDB01`, `LGDPDB01` | `LGAPVS01`, `LGIPVS01`, `LGUPVS01`, `LGDPVS01` |
| **Endowment policy** | `LGTESTP2` (txn `SSP2`) | *(same business/data programs, driven by `policyType = E`)* | | |
| **House policy** | `LGTESTP3` (txn `SSP3`) | *(same, `policyType = H`)* | | |
| **Commercial policy** | `LGTESTP4` (txn `SSP4`, no Update option) | *(same, `policyType = C`)* | | |

**Cross-module infrastructure:** `LGSETUP` (init), `LGSTSQ` (shared error logging, called by 20 of 30 programs), `LGASTAT1` / `LGWEBST5` (transaction-count statistics).

**No batch cycle, no interest/fee engine, and no user-authentication module exist as GenApp business modules** — see Sections 2, 3, 6, and 10.

---

## 2. Security, Sign-on, and Menu Access

**Finding: GenApp implements no application-level security, authentication, or sign-on logic of its own.**

| Aspect | What actually exists |
|---|---|
| **Sign-on / logon** | None in the application. 3270 terminal sign-on (if used at all) is handled entirely by the surrounding CICS region and RACF (or equivalent ESM) — outside GenApp's own code. `DOCUMENTATION/Installation.md` mentions RACF only once, and only for the install-time Db2 administrator ID, not end-user authentication. |
| **Transaction-level security** | The CICS resource-definition JCL (`cdef121.jcl`) defines `SSC1`, `SSP1`–`SSP4`, `LGSE`, `LGCF`, `LGPF` with **no `RESSEC`/`CMDSEC`/`SecurityName` attribute set** — i.e., transaction attach security is left at the CICS-region default, not configured by GenApp. Any user able to reach the region can invoke any GenApp transaction. |
| **Menu access control** | The single BMS map set (`SSMAP`) drives all five transactions; menu options are plain `EVALUATE` statements on a typed field (`ENT1OPTO`/`ENP1OPTO`) with no role check. There is no concept of "this user cannot see option 2." An unrecognized option shows `'Please enter a valid option'` and re-prompts — that is the *only* form of "access control" present. |
| **Customer password field** | The `customer_secure` Db2 table (see Section 9) exists and is populated on every Add Customer, but **no program in this package ever reads or validates it** — there is no login/authentication flow that checks `CUSTSECR-PASS`. The password is always set to a **hardcoded literal MD5-looking string** (`'5732fec825535eeafb8fac50fee3a8aa'`) in `LGACDB01`, regardless of what the user entered — i.e., every customer gets the identical stored password value. This is a demo artifact, not a real credential system, but it is a genuine finding to flag: **do not treat this table as a working authentication mechanism during modernization.** |

**Modernization implication:** a real security/AuthN/AuthZ layer (RACF passticket, LDAP, OAuth, per-transaction role mapping) will need to be **designed from scratch** — there is no legacy sign-on business logic to reverse-engineer beyond "the region's default."

---

## 3. User Maintenance

**Finding: GenApp has no concept of an application "user" distinct from a "customer."** There is no user-provisioning, role-assignment, password-reset, or account-lockout logic anywhere in the 30 COBOL programs.

The closest analog is **Customer maintenance** (Section 1), which is a business-data CRUD function, not a security-user function:

| Function | Program Chain | What it does |
|---|---|---|
| Add customer | `LGTESTC1`→`LGACUS01`→`LGACDB01`→`LGACDB02`→`LGACVS01` | Creates a `customer` row (Db2), a `customer_secure` row with the fixed placeholder password (Db2), and a `KSDSCUST` record (VSAM) |
| Inquire customer | `LGTESTC1`→`LGICUS01`→`LGICDB01` | Reads the `customer` row from Db2 only |
| Update customer | `LGTESTC1`→`LGUCUS01`→`LGUCDB01`→`LGUCVS01` | Updates `customer` (Db2) and `KSDSCUST` (VSAM); does **not** touch `customer_secure` |

There is no "Delete Customer" transaction/option anywhere in the presentation layer (`LGTESTC1` only offers options 1, 2, 4 — Inquire, Add, Update).

---

## 4. Account Rules

GenApp has no "account" entity (in the banking sense of a balance-bearing account). The nearest equivalent is the **policy**, which behaves as the unit-of-record analogous to an account:

| Rule | Enforcement Point |
|---|---|
| A policy cannot exist without a parent customer | Db2 foreign key `POLICY.CUSTOMERNUMBER → CUSTOMER.CUSTOMERNUMBER` (`db2cre.jcl`); no COBOL-level pre-check — a bad customer number simply fails the FK insert with a Db2 error, surfaced as return code `90` |
| A policy is uniquely identified by `(policyType, customerNumber, policyNumber)` in VSAM (21-byte composite key) and by `POLICYNUMBER` (Db2 identity column) in Db2 | `LGAPVS01`/`LGIPVS01`/`LGUPVS01`/`LGDPVS01` (VSAM key construction); Db2 `IDENTITY` column with named-counter fallback (see below) |
| Policy number assignment prefers a coupling-facility **named counter** (`GENAPOLNUM`), falling back to Db2 `IDENTITY_VAL_LOCAL()` if the named-counter server is unavailable | `LGAPDB01` — `Obtain-POLICY-Number` paragraph, same pattern as customer numbering (Section 9) |
| A policy row cannot exist without its type-specific detail row (Motor/Endowment/House/Commercial), and vice versa | Db2 FK `ON DELETE CASCADE` from `POLICY` to each detail table |
| Deleting a policy removes the type-detail row automatically | Cascade delete — `LGDPDB01` only issues `DELETE FROM POLICY`; it does not separately delete the child row |
| Every Add Policy is a Db2 + VSAM two-phase write within one CICS unit of work | `LGAPDB01` → `LGAPVS01` (both under the same syncpoint scope; a failure in either triggers `EXEC CICS SYNCPOINT ROLLBACK` in the calling presentation program) |

---

## 5. Field Validation

Validation in GenApp is intentionally minimal (it is a demo/test application) and happens almost entirely at the **COMMAREA-length** level rather than the individual-field level:

| Validation Rule | Where Enforced | Behavior on Failure |
|---|---|---|
| COMMAREA must be present (`EIBCALEN > 0`) | Every business-logic and Db2-layer program (all 24 non-presentation programs) | `EXEC CICS ABEND ABCODE('LGCA')` — hard abend, not a graceful error return |
| COMMAREA must be at least header-length + entity-length | Same programs (e.g., `LGACUS01` requires ≥ 18 + 72 bytes for a customer add) | `CA-RETURN-CODE = '98'`, immediate `EXEC CICS RETURN` (no abend) |
| Postcode is forced to uppercase before storage | `LGTESTC1` (`FUNCTION UPPER-CASE(CA-POSTCODE)`) — Add and Update paths only | Silent normalization, not a rejection |
| Low-values in transmitted 3270 fields are replaced with spaces before use | `LGTESTC1`, presumably mirrored in `LGTESTP1-4` (`INSPECT COMM-AREA REPLACING ALL X'00' BY X'40'`) | Silent normalization |
| Menu option must be one of the defined `EVALUATE` values | All 5 presentation programs | `'Please enter a valid option'`, cursor repositioned, screen re-sent — no program call made |
| Optimistic-concurrency timestamp match (Update Policy only) | `LGUPDB01` — compares caller-supplied `LASTCHANGED` to the current Db2 row | `CA-RETURN-CODE = '02'` if mismatched (see Section 7) |

**No field-level business validation exists for:** date-of-birth format/plausibility, postcode format, phone-number format, email-address format, mandatory-field (non-blank) enforcement on individual name/address fields, numeric-range checks on premiums/values, or vehicle/registration format. Any such validation exists only at the 3270 BMS map-attribute level (if at all — this package's `ssmap.bms` was not decompiled to field-attribute granularity in this pass) or must be added during modernization. **This is a significant finding**: a modern rewrite should not assume the legacy layer already enforces data quality — it mostly does not.

---

## 6. Update Protocol

GenApp's update discipline is built around a single, consistently-applied pattern: **optimistic concurrency control via a last-changed timestamp**, applied only to Policy updates (not Customer updates).

| Step | Program | Rule |
|---|---|---|
| 1 | `LGIPOL01`→`LGIPDB01` | Inquire returns the current `LASTCHANGED` timestamp to the caller in the COMMAREA |
| 2 | `LGTESTPn` (presentation) | The timestamp round-trips through the 3270 screen unchanged (user cannot see or edit it, but the program carries it) |
| 3 | `LGUPOL01`→`LGUPDB01` | `LGUPDB01` re-reads the row with `SELECT ... FOR UPDATE`/`WHERE CURRENT OF POLICY_CURSOR` pattern and compares the row's live `LASTCHANGED` against the value the caller sent |
| 4a | `LGUPDB01` | If they **match**: proceeds with `UPDATE ... SET LASTCHANGED = CURRENT TIMESTAMP`, returns `CA-RETURN-CODE = '00'` and the new timestamp |
| 4b | `LGUPDB01` | If they **don't match** (another user updated the policy since it was read): `CA-RETURN-CODE = '02'` — **update rejected, no rollback needed since nothing was written** |
| 4c | `LGUPDB01` | If the initial re-fetch itself returns "not found" (`SQLCODE = +100`): `CA-RETURN-CODE = '01'` |

**Customer updates (`LGUCUS01`→`LGUCDB01`→`LGUCVS01`) have no equivalent optimistic-lock check** — the Db2 row is updated unconditionally, and the VSAM record is read `UPDATE` (exclusive) immediately before `REWRITE`, relying on VSAM's own record-locking rather than a timestamp comparison. This is an **inconsistency between the Customer and Policy update paths** worth flagging for a modernized design (should Customer updates also be optimistically locked?).

**Rollback protocol:** any non-zero return code from a business-logic LINK causes the calling presentation program to issue `EXEC CICS SYNCPOINT ROLLBACK` before displaying the error — ensuring the Db2/VSAM two-phase write is fully undone on any failure partway through (e.g., Db2 insert succeeds but VSAM write fails).

---

## 7. Transaction Rules, Batch Posting

**Online transaction rules:**
- All work for a single business function (e.g., "add a policy") executes as **one CICS unit of work** — Db2 and VSAM writes share the same syncpoint scope, and a failure anywhere in the chain rolls back everything written so far in that UOW.
- The `LG*`-prefixed program-naming convention itself is used as the CICS **Event Processing filter** (`Transaction_Counters.evbind`) — every LINK to a program whose name starts with `LG` increments a business-event counter, regardless of which specific function ran.
- Screen-to-screen "conversational" state is passed forward via `EXEC CICS RETURN TRANSID('SSC1'/'SSP1'.. ) COMMAREA(...)` — a pseudo-conversational CICS pattern, not a true batch or stateless-API pattern.

**Batch posting: does not exist in GenApp.** There is no COBOL batch program, no scheduled job that posts, sweeps, or reconciles transactions, and no "batch window." As established in the prior Dependency Reference, every one of the 30 COBOL programs is CICS-online. The only things resembling "batch" are:
- **One-time JCL setup jobs** (`@DB2CRE`, `@ADEF121`, `@CDEF121`, `@COBOL`, `@DB2BIND`) — infrastructure provisioning, not business posting.
- **Workload Simulator (WSIM) jobs** (`@ITPENTR` etc.) — synthetic load generation for testing, which *drives* the online transactions repeatedly; it does not implement independent batch business logic.

If the target modernized architecture requires a batch-posting capability (e.g., end-of-day settlement, bulk policy renewal, premium reconciliation), that is **entirely new functionality to design**, not a migration of existing batch COBOL.

---

## 8. Interest and Fees

**Finding: GenApp has no interest-calculation or fee-calculation logic anywhere in the codebase.** This is expected — GenApp models general-insurance policies (motor/endowment/house/commercial), not deposit or loan accounts.

The closest analogous concept is the **premium/peril structure on Commercial policies** — the only policy type that carries a fine-grained pricing breakdown:

| Field (per peril: Fire, Crime, Flood, Weather) | Table | Nature |
|---|---|---|
| `<Peril>Peril` (e.g., `FirePeril`) | `commercial` | A stored value (peril indicator/rating), captured as-entered — **no calculation is performed in COBOL** |
| `<Peril>Premium` (e.g., `FirePremium`) | `commercial` | A stored premium amount, likewise captured as-entered |
| `Status` / `RejectReason` | `commercial` | A stored underwriting decision outcome, captured as-entered (see Section 10) |

All of these are **plain pass-through fields**: the presentation/business/data layers move the value from the 3270 screen straight into the Db2 column with no arithmetic, no rate table lookup, and no derived calculation. **There is no interest-accrual, no late-fee, no premium-calculation-engine, and no rate table in this codebase.** Any such capability is new-build scope for modernization, not something to reverse-engineer from GenApp.

---

## 9. Reporting

GenApp has no reporting programs, report-generation JCL, or extract feeds. "Reporting" activity is limited to two mechanisms, both operational/diagnostic rather than business reporting:

| Mechanism | Program | Purpose |
|---|---|---|
| Error/diagnostic log | `LGSTSQ` writes to CICS TSQ `GENAERRS` | Every failure path across the 20 calling programs writes a structured message (date, time, program name, customer/policy number, SQLCODE) — this is an operations log, not a business report |
| Transaction-volume statistics | `LGASTAT1` (updates named counters) and `LGWEBST5` (copies counts to a shared TSQ every 60 seconds) | A simple running count of transactions by type, for monitoring — again operational telemetry, not a business report |

There is no month-end statement generation, no customer-facing report, no regulatory/compliance extract, and no Db2 reporting view defined in `db2cre.jcl`. A modernized platform's reporting layer would be built against the Db2 schema directly (Section 10) rather than migrated from any existing GenApp report logic, because none exists.

---

## 10. Decision Rules

The application's decision logic is expressed almost entirely as **return-code assignment** on `CA-RETURN-CODE`, propagated from the data layer up through business logic to the presentation layer, where it drives which screen/message is shown. Consolidated return-code catalogue (from all 30 programs):

| Code | Meaning | Typical Origin |
|---|---|---|
| `00` | Success | All programs, happy path |
| `01` | No row found (`SQLCODE = +100`) | `LGICDB01`, `LGIPDB01` (multiple cursors), `LGUCDB01`, `LGUPDB01` |
| `02` | Optimistic-lock conflict — `LASTCHANGED` timestamp mismatch | `LGUPDB01` only |
| `70` | *(Reserved / policy-add specific — appears once in `LGAPDB01`, adjacent to a success path variant)* | `LGAPDB01` |
| `80` | VSAM `WRITE` failed (e.g., duplicate key) | `LGACVS01`, `LGAPVS01` |
| `81` | VSAM `READ`/`DELETE` failed (e.g., record not found) | `LGUCVS01`, `LGUPVS01`, `LGDPVS01` |
| `82` | VSAM `REWRITE` failed | `LGUCVS01`, `LGUPVS01` |
| `88` | Db2 cursor `CLOSE` failed | `LGIPDB01` (multiple type-specific cursors) |
| `89` | Db2 cursor `OPEN` failed | `LGIPDB01` (multiple type-specific cursors) |
| `90` | General/unexpected Db2 `SQLCODE ≠ 0` error | Nearly every Db2-layer program — the catch-all failure code |
| `98` | COMMAREA shorter than required for the request type | Every business-logic and Db2-layer program (universal input-validation code) |
| `99` | Program-specific logic error (e.g., insert failed for a reason other than the raw SQLCODE catch-all) | `LGACUS01`(?)/`LGUCUS01`, `LGAPDB01`, `LGDPDB01`, `LGDPOL01`, `LGUPOL01` |

**Other decision rules:**
- **Named-counter vs. identity-column fallback**: on every Add Customer and Add Policy, the business rule is *"try the coupling-facility named counter first; if it's unavailable (`WS-RESP ≠ DFHRESP(NORMAL)`), fall back to a Db2 `IDENTITY` column value obtained via `IDENTITY_VAL_LOCAL()`"* — this makes GenApp portable between single-region (no coupling facility) and multi-region (coupling facility present) topologies without changing business logic.
- **Cursor row-limit rule**: the Commercial-policy multi-row cursor fetch (`GET-Commercial-DB2-INFO-3-Cur`) enforces a **hard cap of 20 rows** (`IF ICOM-Record-Count > 20 MOVE 17 TO SQLCODE`) — an artificial "stop fetching" signal, not a real SQLCODE. This is a business/performance rule limiting how many matching commercial policies are returned per inquiry, and should be preserved (or replaced with proper pagination) in a modernized design.
- **Underwriting decision fields** (`Status`, `RejectReason` on Commercial policies) are **stored, not computed** — GenApp captures an underwriting outcome entered by the user; it does not contain underwriting/decision-engine logic itself.

---

## 11. Transaction Type / Category Maintenance (DB2)

> As with the prior Dependency Reference, no module literally named for "transaction type maintenance" exists; the closest real capability is the **policy-type discriminator** governing the four insurance product lines.

| Rule | Detail |
|---|---|
| Type discriminator | `POLICY.POLICYTYPE` — single character: `M` (Motor), `E` (Endowment), `H` (House), `C` (Commercial) |
| No reference/lookup table for policy type | `db2cre.jcl` defines no `POLICY_TYPE` table — the four-value domain is **hardcoded implicitly** by which presentation transaction/program the user entered from (`SSP1`→M, `SSP2`→E, `SSP3`→H, `SSP4`→C), not validated against a governed list in Db2 |
| Type-specific extension tables | `MOTOR`, `ENDOWMENT`, `HOUSE`, `COMMERCIAL` — each a 1:1 child of `POLICY`, enforced by FK + cascade delete |
| Type-specific field sets differ materially | e.g., Commercial carries 4 peril/premium pairs + status/reject-reason; Motor carries vehicle make/model/registration/value; House and Endowment have their own distinct field sets (not enumerated in this pass — see `Reference.md`/`db2cre.jcl` for full column lists) |
| Category maintenance (add/edit/retire a policy *type* itself) | **Does not exist.** The four types are fixed in the program/transaction structure (5 presentation programs, one per type plus customer); there is no admin function to add a fifth product line without new COBOL/BMS/JCL work |
| `CLAIM` table exists with no maintaining program | Schema present (`db2cre.jcl`), FK to `POLICY`, but **no `LG*` program in this package inserts, updates, or queries it** — flagged again here as a gap to confirm with the business (claims processing may be out of scope, exist elsewhere, or be a genuine missing capability) |

**Modernization recommendation (repeated from the Dependency Reference):** introduce a governed `POLICY_TYPE` reference table with validation, rather than perpetuating the implicit "which transaction did they use" pattern, if new product lines are anticipated.

---

## 12. Cross-Cutting Conventions

| Convention | Description |
|---|---|
| **Program naming** | `LG` + function letter (`A`=Add, `I`=Inquire, `U`=Update, `D`=Delete) + entity (`CUS`=Customer, `POL`=Policy) + layer (`01`=business, `DB01`=Db2 data, `VS01`=VSAM data) — e.g. `LGUPDB01` = "Update POLicy, DataBase (Db2) layer, variant 01" |
| **Request-ID tagging** | Every COMMAREA carries a 6-char `CA-REQUEST-ID` (e.g., `'01ACUS'`, `'01ICUS'`, `'01UCUS'`, `'01DMOT'`) that identifies the specific function being invoked — used by shared/multi-purpose programs to branch internally |
| **COMMAREA-first design** | All inter-program communication is via one shared, `REDEFINES`-heavy `LGCMAREA` copybook (32,500-byte LINK length used almost universally) rather than distinct per-call structures — a significant coupling point (see the earlier Dependency Reference's "god copybook" risk flag) |
| **Universal error-logging call** | Every program that can fail calls `LGSTSQ` with a standard `ERROR-MSG` layout: date, time, program name, then a program-specific variable-text field (customer number, policy number, and/or `SQLCODE`) |
| **EIBCALEN-zero = hard abend** | Every non-presentation program abends (`ABCODE` unique per program, e.g. `LGCA`, `LGV0`, `LGV1`, `LGV2`) if invoked with no COMMAREA at all — this is a defensive-programming convention, distinct from the graceful `'98'` return code used for *too-short* (but present) COMMAREAs |
| **Syncpoint discipline** | Presentation-layer programs, not business-logic programs, issue `EXEC CICS SYNCPOINT ROLLBACK` on error — rollback authority sits at the top of the call chain, one layer below the user |
| **Copyright/versioning header** | Every source file carries an identical `(C) Copyright IBM Corp. 2011, 2020/2021` banner and a fixed eyecatcher (`WS-EYECATCHER`) pattern for storage-dump diagnostics |

---

## 13. Reference Data Files

Two categories exist, and they serve entirely different purposes — conflating them would be a modernization mistake:

| Category | Files | Purpose | Governs Business Rules? |
|---|---|---|---|
| **VSAM seed data** | `ksdscust.txt`, `ksdspoly.txt` | Initial data load for `KSDSCUST`/`KSDSPOLY` at install time | No — sample data only |
| **WSIM synthetic-data generators** | `ctype.txt`, `ptype.txt`, `rtype.txt`, `htype.txt`, `pcode.txt`, `sname.txt`, `fname.txt`, `cmake.txt`, `cmodel.txt`, `ccolor.txt` | Random-value pools used by the Workload Simulator to generate realistic-looking test transactions (claim types, postcodes, names, vehicle makes/models/colors) | **No** — these are test-data generators, not governed reference/lookup tables consulted by any COBOL program at runtime. No `LG*` program reads any `DATA/*.txt` file. |

**There is no runtime-governed reference/code table in this application** — not for policy types (Section 11), not for postcodes, not for vehicle makes, not for claim types. Every "type/category" value the online programs handle is either free-text captured from the user or an implicit discriminator baked into program/transaction structure. If the modernized design wants normalized, validated reference data, it will need to be built new — the `DATA/*.txt` files are testing artifacts, not a starting schema for reference tables (though `ctype`/`ptype`/`rtype`/`htype`/`cmake`/`cmodel`/`ccolor` could reasonably seed the *values* of new reference tables, since they represent realistic domain vocabularies even though they were never enforced as such).

---

## 14. Anything Else — Notable Findings Outside the Requested Sections

- **No true multi-record browse anywhere in VSAM** — every VSAM access is by direct key (Section 3 of the Dependency Reference); all "list" behavior (e.g., "which commercial policies match this postcode") is Db2-cursor-based only (`GET-Commercial-DB2-INFO-5` / `Zip_Cursor`), so any VSAM-only deployment (GenApp Lite) cannot support that inquiry — a hidden feature-parity gap between the Db2-backed and VSAM-only configurations.
- **`LGACDB01`'s customer-add path always inserts a `customer_secure` row via `LGACDB02`, but no program ever reads it back** — the write-only security table is effectively dead functionality from a business-rule standpoint (see Section 2).
- **Undocumented programs** (`LGACDB02`, `LGUCDB01`, `LGUCUS01`, `LGUCVS01`, `LGUPVS01` — not listed in `DOCUMENTATION/Reference.md`) implement real, load-bearing business rules (Sections 3, 6) despite being undocumented — a discovery-completeness risk for any modernization team relying on `Reference.md` alone.
- **Inconsistent update-locking strategy** between Customer (VSAM exclusive-read lock only) and Policy (Db2 timestamp-based optimistic lock) — worth a deliberate design decision rather than silent carry-forward in the target architecture.
- **Commercial policies are the only type with no Update path** (`LGTESTP4` only offers Inquire/Add/Delete) — unclear whether this is an intentional business rule ("commercial policies can't be amended, only replaced") or simply incomplete demo coverage; worth confirming with the business.

---

*Generated from static business-logic analysis of the uploaded source package — all rules traced to specific `IF`/`EVALUATE` branches, `CA-RETURN-CODE` assignments, and `EXEC SQL`/`EXEC CICS` predicates in the 30 COBOL programs, cross-referenced with `db2cre.jcl` (Db2 schema/constraints) and `cdef121.jcl` (CICS resource definitions).*
