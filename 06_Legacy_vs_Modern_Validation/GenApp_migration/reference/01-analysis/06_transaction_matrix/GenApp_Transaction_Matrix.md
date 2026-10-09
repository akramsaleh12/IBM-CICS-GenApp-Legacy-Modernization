# Transaction Matrix — GenApp (General Insurance Application)
### Legacy Modernization Assessment

A transaction-level view of the application: every CICS transaction ID, the program it invokes, every menu-option "sub-transaction" (function) it offers, the internal request-ID code that drives business/data-layer routing, and the data stores each one touches. Derived by tracing every `EVALUATE ENTnOPTO` / `EVALUATE ENPnOPTO` menu branch and its `CA-REQUEST-ID` assignment in all 5 presentation programs, cross-referenced with `JCL/cdef121.jcl` (CICS resource definitions).

---

## 1. Transaction-to-Program Matrix

| Trans ID | Program | Group | Description (per `cdef121.jcl`) | Map Set | Entry Point Type |
|---|---|---|---|---|---|
| `SSC1` | `LGTESTC1` | GENASAT | Solution Customer Menu | `SSMAP` (`SSMAPC1`) | 3270 user menu |
| `SSP1` | `LGTESTP1` | GENASAT | Solution Motor Policy Menu | `SSMAP` (`SSMAPP1`) | 3270 user menu |
| `SSP2` | `LGTESTP2` | GENASAT | Solution Life (Endowment) Policy Menu | `SSMAP` (`SSMAPP1`, shared layout) | 3270 user menu |
| `SSP3` | `LGTESTP3` | GENASAT | Solution House Policy Menu | `SSMAP` (`SSMAPP1`, shared layout) | 3270 user menu |
| `SSP4` | `LGTESTP4` | GENASAT | Solution Commercial Policy Menu | `SSMAP` (`SSMAPP1`, shared layout) | 3270 user menu |
| `LGSE` | `LGSETUP` | GENASAT | Initial setup of TSQueue / named counters | — | Admin/setup utility (run once) |
| `LGCF` | `LGICVS01` | GENASAT | *(no description in resource JCL — VSAM customer inquiry)* | — | WSIM helper (random customer-number retrieval) |
| `LGPF` | `LGIPVS01` | GENASAT | *(no description in resource JCL — VSAM policy inquiry)* | — | WSIM helper (random policy-number retrieval) |

**Note on `LGCF`/`LGPF`:** these two transactions attach the same VSAM "Inquire" programs that also serve as internal data-layer components of the main chains (Section 2) — they are dual-purpose: normally reached only via `LINK` from `LGICUS01`/`LGIPOL01`, but also independently attachable as their own transaction for Workload Simulator scripts that need a quick random-key lookup without going through the full menu flow.

---

## 2. Transaction Function Matrix (Menu Option → Business Function)

Each 3270 menu presents 3–4 numbered options; each option is a distinct business function with its own internal `CA-REQUEST-ID` code (format: `<seq><Function><Entity>`, e.g. `01ACUS` = sequence 01, **A**dd, **CUS**tomer) that routes through the business-logic and data-management layers.

### `SSC1` / `LGTESTC1` — Customer Menu
| Option | Function | Request ID | Program Chain | Data Touched |
|---|---|---|---|---|
| 1 | Inquire Customer | `01ICUS` | `LGICUS01` → `LGICDB01` | Db2 `customer` |
| 2 | Add Customer | `01ACUS` | `LGACUS01` → `LGACDB01` → `LGACDB02` → `LGACVS01` | Db2 `customer`, `customer_secure`; VSAM `KSDSCUST`; TSQ `GENACNTL` |
| 3 | *(not offered — no Delete Customer function exists in this menu)* | — | — | — |
| 4 | Update Customer | `01ICUS` (re-inquire) then `01UCUS` | `LGICUS01`→`LGICDB01` (display current), then `LGUCUS01`→`LGUCDB01`→`LGUCVS01` (apply update) | Db2 `customer`; VSAM `KSDSCUST` |

### `SSP1` / `LGTESTP1` — Motor Policy Menu
| Option | Function | Request ID | Program Chain | Data Touched |
|---|---|---|---|---|
| 1 | Inquire Motor Policy | `01IMOT` | `LGIPOL01` → `LGIPDB01` | Db2 `policy` + `motor` |
| 2 | Add Motor Policy | `01AMOT` | `LGAPOL01` → `LGAPDB01` → `LGAPVS01` | Db2 `policy` + `motor`; VSAM `KSDSPOLY` |
| 3 | Delete Motor Policy | `01DMOT` | `LGDPOL01` → `LGDPDB01` → `LGDPVS01` | Db2 `policy` + `motor` (cascade); VSAM `KSDSPOLY` |
| 4 | Update Motor Policy | `01IMOT` (re-inquire) then `01UMOT` | `LGIPOL01`→`LGIPDB01` (display current), then `LGUPOL01`→`LGUPDB01`→`LGUPVS01` (apply update) | Db2 `policy` + `motor`; VSAM `KSDSPOLY` |

### `SSP2` / `LGTESTP2` — Endowment (Life) Policy Menu
| Option | Function | Request ID | Program Chain | Data Touched |
|---|---|---|---|---|
| 1 | Inquire Endowment Policy | `01IEND` | `LGIPOL01` → `LGIPDB01` | Db2 `policy` + `endowment` |
| 2 | Add Endowment Policy | `01AEND` | `LGAPOL01` → `LGAPDB01` → `LGAPVS01` | Db2 `policy` + `endowment`; VSAM `KSDSPOLY` |
| 3 | Delete Endowment Policy | `01DEND` | `LGDPOL01` → `LGDPDB01` → `LGDPVS01` | Db2 `policy` + `endowment` (cascade); VSAM `KSDSPOLY` |
| 4 | Update Endowment Policy | `01IEND` (re-inquire) then `01UEND` | `LGIPOL01`→`LGIPDB01`, then `LGUPOL01`→`LGUPDB01`→`LGUPVS01` | Db2 `policy` + `endowment`; VSAM `KSDSPOLY` |

### `SSP3` / `LGTESTP3` — House Policy Menu
| Option | Function | Request ID | Program Chain | Data Touched |
|---|---|---|---|---|
| 1 | Inquire House Policy | `01IHOU` | `LGIPOL01` → `LGIPDB01` | Db2 `policy` + `house` |
| 2 | Add House Policy | `01AHOU` | `LGAPOL01` → `LGAPDB01` → `LGAPVS01` | Db2 `policy` + `house`; VSAM `KSDSPOLY` |
| 3 | Delete House Policy | `01DHOU` | `LGDPOL01` → `LGDPDB01` → `LGDPVS01` | Db2 `policy` + `house` (cascade); VSAM `KSDSPOLY` |
| 4 | Update House Policy | `01IHOU` (re-inquire) then `01UHOU` | `LGIPOL01`→`LGIPDB01`, then `LGUPOL01`→`LGUPDB01`→`LGUPVS01` | Db2 `policy` + `house`; VSAM `KSDSPOLY` |

### `SSP4` / `LGTESTP4` — Commercial Policy Menu *(only 3 options — no Update)*
| Option | Function | Request ID | Program Chain | Data Touched |
|---|---|---|---|---|
| 1 | Inquire Commercial Policy — **4 search variants** (see 2a below) | `01ICOM` / `02ICOM` / `03ICOM` / `05ICOM` | `LGIPOL01` → `LGIPDB01` | Db2 `policy` + `commercial` |
| 2 | Add Commercial Policy | `01ACOM` | `LGAPOL01` → `LGAPDB01` → `LGAPVS01` | Db2 `policy` + `commercial`; VSAM `KSDSPOLY` |
| 3 | Delete Commercial Policy | `01DCOM` | `LGDPOL01` → `LGDPDB01` → `LGDPVS01` | Db2 `policy` + `commercial` (cascade); VSAM `KSDSPOLY` |
| — | *(Update not offered on this menu)* | — | — | — |

**2a. `SSP4` Option 1 — Commercial Inquiry sub-variants** (the only menu option in the portfolio with multiple internal request-ID codes for one option — a search-criteria selector):

| Request ID | Search Criterion | Db2 Cursor (per `LGIPDB01`) |
|---|---|---|
| `01ICOM` | By policy number | Single-row lookup |
| `02ICOM` | By customer number | Single-row lookup |
| `03ICOM` | By postcode/zip | Multi-row cursor (`Zip_Cursor`, capped at 20 rows — see the Complexity Analysis report, Section 10) |
| `05ICOM` | *(a fourth search mode — exact criterion not further decoded in this pass; recommend a manual read of `LGTESTP4`'s option-1 sub-menu for confirmation)* | Multi-row cursor variant |

---

## 3. Transaction Volume/Monitoring Matrix (Named Counters, per `LGSETUP`)

`LGSETUP` defines a dedicated named counter pair (low/high range, `00`–`99`) for most Add/Inquire/Update/Delete functions, used by `LGASTAT1` to track per-function transaction volume:

| Counter Prefix | Function | Entity |
|---|---|---|
| `GENA01ICUS` | Inquire | Customer |
| `GENA01ACUS` | Add | Customer |
| `GENA01IMOT` | Inquire | Motor policy |
| `GENA01AMOT` | Add | Motor policy |
| `GENA01DMOT` | Delete | Motor policy |
| `GENA01UMOT` | Update | Motor policy |
| *(equivalent counters exist for `IEND`/`AEND`/`DEND`/`UEND`, `IHOU`/`AHOU`/`DHOU`/`UHOU`, and `ICOM`/`ACOM`/`DCOM` — following the identical naming pattern seen above)* | | |

This confirms the `CA-REQUEST-ID` scheme (Section 2) is the same vocabulary used end-to-end — from 3270 menu option, through business/data-layer routing, to transaction-volume monitoring.

---

## 4. Referenced-but-Missing Program — New Finding

`JCL/cdef121.jcl` defines a CICS program resource for **`LGAPBR01`** (`Define Program(LGAPBR01) Group(GENASAP)`) alongside the other 30 core programs — but **no `LGAPBR01` source file exists anywhere in the uploaded package**, and no COBOL program in `COBOL/` links to it. Based on the naming convention (`AP` = Add Policy pattern seen elsewhere, `BR` most likely "Browse"), this is plausibly a **multi-row policy browse program** — which would align naturally with the Commercial multi-row cursor search modes in Section 2a (`03ICOM`/`05ICOM`) — but this is inferred, not confirmed. **This is a second undocumented/missing-source program gap** (in addition to the five undocumented-but-present programs flagged in the Application Inventory report) and should be raised with the source-code owners before migration: either the source was omitted from this package, or the resource definition is stale/unused.

---

## 5. Summary Observations

- **21 distinct business functions** are exposed across the 5 presentation transactions: 1 Inquire + 1 Add + 1 Update for Customer (no Delete); Inquire/Add/Delete/Update × 3 for Motor/Endowment/House (12 functions); Inquire (×4 search variants) + Add + Delete for Commercial (6 functions, no Update) — for a combined total of **3 + 12 + 6 = 21** menu-driven functions, all reachable from just 5 transaction IDs.
- **Update is implemented as "Inquire then re-submit,"** not as a single request/response — every Update option (`4` on Customer/Motor/Endowment/House) first performs a full Inquire to populate the screen, then a second `RECEIVE MAP`/`LINK` round-trip carries the edited fields back for the actual update. This is a two-transaction-turnaround pattern baked into pseudo-conversational CICS design, and it's the same touchpoint where the optimistic-concurrency timestamp check (Business Rules report, Section 6) applies.
- **Commercial policies are structurally the outlier**: the only entity with no Update path, and the only one whose Inquire option branches into 4 distinct search modes rather than a single customer/policy-number lookup — consistent with Commercial being the most complex entity in the schema (peril/premium/status fields — Database Analysis report, Section 2).
- **A second missing-source-code gap was found** (`LGAPBR01`, Section 4) beyond the five previously-flagged undocumented programs — reinforcing that `Reference.md` and even the CICS resource JCL should not be treated as fully in sync with the delivered source; a full source-completeness audit against the CSD/resource definitions is recommended before migration scoping is finalized.

---

*Generated from static analysis of all 5 presentation-tier COBOL programs (menu `EVALUATE` branches and `CA-REQUEST-ID` assignments) and `JCL/cdef121.jcl` (CICS transaction and program resource definitions) in the uploaded source package.*
