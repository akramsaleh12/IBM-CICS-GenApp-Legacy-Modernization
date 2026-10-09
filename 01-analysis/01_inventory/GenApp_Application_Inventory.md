# Application Inventory — GenApp (General Insurance Application)
### Legacy Modernization Assessment

**Source package:** `source.zip` (IBM "GenApp" CICS/COBOL/Db2 sample, reorganized by file type)
**Files analyzed:** 147 files across COBOL, Copybooks, BMS, JCL, Data, Event Bindings, REXX, Shell, Documentation

---

## 1. High-Level Structure

| Directory | Purpose | File Count |
|---|---|---|
| `COBOL/` | Application source programs (presentation, business, data-access layers) | 31 |
| `COPYBOOKS/` | Shared data structures (COMMAREA layouts, DB2 host variable groups, integration record layouts) | 11 |
| `BMS/` | 3270 screen map definitions (map set for all transactions) | 1 |
| `JCL/` | Build, resource-definition, Db2, and utility batch jobs | 32 |
| `DATA/` | VSAM seed data + Workload Simulator (WSIM) reference/message tables | 46 |
| `EVENT_BINDINGS/` | CICS event processing (business-event capture) definitions | 1 |
| `OTHER/` | REXX exec scripts, architecture diagram | 3 |
| `SHELL/` | Installation/deployment script | 1 |
| `DOCUMENTATION/` | Architecture, install, build, test, and reference guides | 12 |
| `FILE_MANIFEST.csv` | Original-path → restructured-path mapping | 1 |

**Architecture pattern:** classic 3-tier CICS design — **Presentation** (3270/BMS, `LGTEST*`) → **Business logic** (`LG*01`/`LG*OL01`) → **Data management** (`LG*DB01` for Db2, `LG*VS01` for VSAM) — chained via `EXEC CICS LINK PROGRAM`. The app runs in a single CICS region and optionally extends to a topology using CICSPlex SM, a coupling facility (named counters + shared TSQ), and Db2 two-phase commit alongside VSAM.

---

## 2. Core Application — Online (CICS) Programs

All 30 COBOL programs are CICS-online (every one issues `EXEC CICS` commands); none are traditional batch COBOL. They fall into four functional tiers:

### 2a. Presentation Layer (3270 menu/screen handlers)
| Program | Function | CICS Cmds | Uses BMS Map |
|---|---|---|---|
| `LGTESTC1` | Customer menu — inquire/add customer | 30 | ✅ (10 SEND/RECEIVE) |
| `LGTESTP1` | Motor policy menu (inquire/add/delete) | 26 | ✅ |
| `LGTESTP2` | Endowment policy menu | 25 | ✅ |
| `LGTESTP3` | House policy menu | 25 | ✅ |
| `LGTESTP4` | Commercial property policy menu | 20 | ✅ |

### 2b. Business Logic Layer (orchestration; links VSAM + Db2 tiers)
| Program | Function | Links To |
|---|---|---|
| `LGACUS01` | Add customer — business rules | LGACDB01, LGSTSQ |
| `LGICUS01` | Inquire customer — business rules | LGICDB01, LGSTSQ |
| `LGUCUS01` | Update customer — business rules *(undocumented in Reference.md but present in source)* | LGUCDB01, LGSTSQ |
| `LGAPOL01` | Add policy — business rules | LGAPDB01, LGSTSQ |
| `LGIPOL01` | Inquire policy — business rules | LGIPDB01, LGSTSQ |
| `LGUPOL01` | Update policy — business rules | LGUPDB01, LGSTSQ |
| `LGDPOL01` | Delete policy — business rules | LGDPDB01, LGSTSQ |

### 2c. Data Management Layer — Db2
| Program | Function | SQL Ops |
|---|---|---|
| `LGACDB01` | Add customer to Db2 (`customer` table) | 5 EXEC SQL |
| `LGACDB02` | Add customer security row (`customer_secure`, default hashed password) | 3 EXEC SQL |
| `LGICDB01` | Retrieve customer from Db2 | 3 EXEC SQL |
| `LGUCDB01` | Update customer in Db2 | 4 EXEC SQL |
| `LGAPDB01` | Add policy to Db2 (`policy` + type sub-table) | 11 EXEC SQL |
| `LGIPDB01` | Retrieve policy from Db2 | 16 EXEC SQL |
| `LGUPDB01` | Update policy in Db2 | 12 EXEC SQL |
| `LGDPDB01` | Delete policy from Db2 | 3 EXEC SQL |

### 2d. Data Management Layer — VSAM
| Program | Function |
|---|---|
| `LGACVS01` | Add customer to VSAM KSDS (`KSDSCUST`) |
| `LGICVS01` | Retrieve customer from VSAM |
| `LGUCVS01` | Update customer in VSAM |
| `LGAPVS01` | Add policy to VSAM KSDS (`KSDSPOLY`) |
| `LGIPVS01` | Retrieve policy from VSAM |
| `LGUPVS01` | Update policy in VSAM |
| `LGDPVS01` | Delete policy from VSAM |

### 2e. Infrastructure / Utility Online Programs
| Program | Function |
|---|---|
| `LGSETUP` | Initialize named counters & TSQs (84 CICS cmds — heaviest infra program) |
| `LGSTSQ` | Write diagnostic/error messages to temporary storage queue (`GENAERRS`) |
| `LGASTAT1` | Update transaction counts via named counters |
| `LGWEBST5` | Repeating "business monitor" transaction — copies counter stats to shared TSQ every 60s |

**Note:** `LGACDB02`, `LGUCDB01`, `LGUCUS01`, `LGUCVS01`, and `LGUPVS01` exist in source but are **not listed in `Reference.md`** — likely later additions (customer "update" flow and secure-password handling) that should be flagged during modernization discovery as undocumented components.

---

## 3. Core Application — Batch Programs

**Finding: There are no true batch COBOL programs in this application.** GenApp is designed entirely as an online CICS transaction system; all 30 COBOL modules execute under CICS (confirmed via `EXEC CICS` presence in every program — see grep results, `CICS:7`–`84` occurrences each). "Batch" activity in this codebase is limited to **JCL-driven utility/setup jobs** (schema creation, data load, compilation) rather than scheduled business-processing batch programs — see Section 5.

---

## 4. Copybooks & Screens

| Copybook | Purpose |
|---|---|
| `lgcmarea.cpy` | Master COMMAREA layout — request ID, return code, customer/policy fields passed between presentation → business → data layers |
| `lgpolicy.cpy` | Policy record layout (shared across policy programs) |
| `pollook.cpy` | "Policy lookup" request/response structure (customer number lookup) |
| `polloo2.cpy` | Policy lookup variant — includes policy number + policy type |
| `soaic01.cpy` | SOA/integration COMMAREA — customer inquiry |
| `soaipb1.cpy` | SOA COMMAREA — policy inquiry, base fields |
| `soaipe1.cpy` | SOA COMMAREA — policy inquiry, endowment-specific |
| `soaiph1.cpy` | SOA COMMAREA — policy inquiry, house-specific |
| `soaipm1.cpy` | SOA COMMAREA — policy inquiry, motor-specific |
| `soavcii.cpy` | SOA VSAM-customer inquiry — input layout |
| `soavcio.cpy` | SOA VSAM-customer inquiry — output layout |
| `soavpii.cpy` | SOA VSAM-policy inquiry — input layout (type + customer number) |
| `soavpio.cpy` | SOA VSAM-policy inquiry — output layout |

**Screens (BMS):**
| Map Set | Mapsets/Maps Defined | Purpose |
|---|---|---|
| `ssmap.bms` | `SSMAPC1`, `SSMAPP1`–`SSMAPP5` (6 map panels, 24×80) | Single map set (`SSMAP`) driving all five 3270 transactions (customer menu + 4 policy-type menus) |

---

## 5. Batch / JCL Layer

All 32 JCL members are **build, deployment, and infrastructure-setup jobs** (run once/on-demand by an installer), not recurring business batch cycles.

| Category | Members | Purpose |
|---|---|---|
| **Compilation / Assembly** | `cobol.jcl`, `asmmap.jcl` | Compile COBOL programs; assemble BMS maps |
| **CICS resource definition** | `cdef121`–`cdef125.jcl` | Define CICS resources for single-region, topology, workload-managed, web-services, and workload-simulation configurations |
| **CICSPlex SM** | `cpsmde2.jcl`, `sampcma.jcl`, `defdrep.jcl`, `defwrep.jcl`, `sampwui.jcl` | CICSPlex SM definitions; start CMAS; define CMAS/WUI repositories; start WUI |
| **Db2** | `db2cre.jcl`, `db2bind.jcl`, `db2del.jcl` | Create Db2 storage groups/tablespaces/tables/indexes + seed data; bind plan/packages; drop database |
| **Data set setup** | `adef121.jcl` | Delete/define/load application VSAM data sets |
| **Web services** | `wsaac01`, `wsaap01`, `wsaic01`, `wsaip01`, `wsauc01`, `wsaup01`, `wsavc01`, `wsavp01.jcl` | Web Services Assistant jobs generating web-service bindings for customer/policy add, inquire, update, and VSAM-read functions |
| **Named counter / TSQ servers** | `sampncs.jcl`, `samptsq.jcl` | Sample start-up JCL for coupling-facility named counter server and shared TSQ server |
| **Workload Simulator (WSIM)** | `itpentr.jcl`, `itpll.jcl`, `itpstl.jcl` | Start WSIM to create test customer/policy records; format WSIM logs; translate WSIM scripts |

---

## 6. Data Assets

### 6a. Persistent Application Data Stores
| Store | Type | Key Structure | Contents |
|---|---|---|---|
| `KSDSCUST` | VSAM KSDS | First 10 bytes = customer ID | Customer master records |
| `KSDSPOLY` | VSAM KSDS | First 21 bytes = policy type(1) + customer ID(10) + policy number(10) | Policy master records (all 4 policy types in one file) |
| Db2 database (`<DB2DBID>`) | Relational | See Section 8 | Customer, policy, and policy-type detail tables |

### 6b. Seed / Sample Data Files
| File | Loads Into |
|---|---|
| `ksdscust.txt` | KSDSCUST VSAM seed records |
| `ksdspoly.txt` | KSDSPOLY VSAM seed records |

### 6c. Workload Simulator (WSIM) Reference Data (44 files in `DATA/`)
Message/lookup tables and scripted transaction decks used to generate synthetic load — **not production business data**:
- Reference/lookup tables: `ctype`, `ptype`, `rtype`, `htype` (claim/property/road/house type codes), `pcode` (postcodes), `sname`/`fname` (surnames/first names), `cmake`/`cmodel`/`ccolor` (vehicle make/model/colour)
- Script/config: `genapp.txt`, `oncics.txt`, `stop.txt`, `waserror.txt`, `#ssvars.txt`, `wslgcf.txt`
- Scripted transaction streams: `ssc1a1/a2/i1`, `ssp1a1/a2/d1/i1/u1`, `ssp2a1/a2/d1/i1/u1`, `ssp3a1/a2/d1/i1/u1`, `ssp4a1/d1/i1`, `wsc1a1/i1` (add/inquire/update/delete scripts per transaction, per policy type)
- `linkparm.txt` — Db2 CLI linkage editor include statement

---

## 7. Optional Extension Modules

Features the base configuration can run without, enabled to demonstrate additional CICS capabilities:

| Extension | Enabling Component(s) | Purpose |
|---|---|---|
| **Named Counter Server** | `LGSETUP`, `LGASTAT1`; `sampncs.jcl`; `GENACUSTNUM` counter | Generates unique customer numbers via coupling facility instead of relying on Db2 identity column |
| **Shared Temporary Storage Queues** | `LGSTSQ`, `LGWEBST5`; `samptsq.jcl`; `GENASTST` TSMODEL | `GENACNTL` (customer-number range control) and `GENAERRS` (Db2 error log) queues — used for Workload Simulator automation and diagnostics, not core business logic |
| **CICS Event Processing** | `Transaction_Counters.evbind`, `GENAEV01` BUNDLE | Captures a business event (`Count_business_trans`) on every `LG*`-prefixed program LINK, feeding transaction-count monitoring |
| **Web Services (SOA layer)** | `wsaac01/ap01/ic01/ip01/uc01/up01/vc01/vp01.jcl`; `soa*.cpy` copybooks; `GENAPIP1` PIPELINE, `GENATCP1` TCPIPSERVICE | Exposes customer/policy add, inquire, update, and raw VSAM-read functions as web services |
| **CICSPlex SM Topology** | `cdef122–125.jcl`, `cpsmde2.jcl`, `sampcma.jcl`, `defdrep/defwrep.jcl`, `sampwui.jcl` | Scales the app from single-region to a managed multi-region topology |
| **Workload Simulator (WSIM)** | `itpentr/itpll/itpstl.jcl`, all `DATA/ss*` and `DATA/ws*` scripts | Synthetic transaction load generation for performance/scale testing |
| **REXX Automation** | `cust1.rexx`, `mac1.rexx` (`OTHER/`) | Customization/setup exec scripts invoked during installation |
| **Two-Phase Commit (Db2 + VSAM)** | Data-management layer (`LG*DB01` + `LG*VS01` pairs) | Demonstrates syncpoint coordination across Db2 and VSAM resource managers — not a best-practice pattern, included for testing |

---

## 8. `app-transaction-type-db2` — Transaction Type Management (DB2)

> **Note:** No module or program in the source is literally named `app-transaction-type-db2` — this section maps the requested capability to GenApp's actual Db2 mechanism for managing **insurance policy "transaction types"** (the four policy products), inferred from `db2cre.jcl` and the `LG*P*01`/`LG*PDB01` program chain.

### 8a. Type Discriminator
The `policy` table carries a single-character **`policyType`** column that classifies every transaction:

| Code | Policy Type | Detail Table | Presentation Program | Db2 Program |
|---|---|---|---|---|
| `M` | Motor | `motor` | `LGTESTP1` | `LGAPDB01` / `LGIPDB01` / `LGUPDB01` / `LGDPDB01` |
| `E` | Endowment | `endowment` | `LGTESTP2` | (same chain, driven by type) |
| `H` | House | `house` | `LGTESTP3` | (same chain) |
| `C` | Commercial | `commercial` | `LGTESTP4` | (same chain) |

*(A fifth entity, `claim`, exists in the schema as a child of `policy` but has no dedicated online CRUD program pair in this source drop.)*

### 8b. Db2 Schema Supporting Transaction-Type Management
| Table | Tablespace | Role |
|---|---|---|
| `customer` | GENATS00 | Party master; identity-column customer number |
| `customer_secure` | GENATS01 | Password/security row, 1:1 with customer |
| `policy` | GENATS02 | Transaction/policy master; holds `policyType` discriminator, dates, broker, payment/commission |
| `endowment` | GENATS03 | Type-specific extension (1:1 with policy where type = E) |
| `house` | GENATS04 | Type-specific extension (type = H) |
| `motor` | GENATS05 | Type-specific extension (type = M) |
| `commercial` | GENATS06 | Type-specific extension (type = C), includes peril/premium breakdown and status/rejection fields |
| `claim` | GENATS07 | Claims against a policy (identity-column claim number) |

Referential integrity enforces that a policy cannot exist without a customer, and a type-detail row cannot exist without its parent policy (all `ON DELETE CASCADE`).

### 8c. Programs Governing Transaction-Type Logic
- **Add:** `LGAPOL01` (business rules) → `LGAPDB01` (11 SQL ops: inserts into `policy` + the relevant type table, using Db2 identity generation for the policy number)
- **Inquire:** `LGIPOL01` → `LGIPDB01` (16 SQL ops — the most complex data program, joins policy master with the type-specific table based on `policyType`)
- **Update:** `LGUPOL01` → `LGUPDB01` (12 SQL ops)
- **Delete:** `LGDPOL01` → `LGDPDB01` (3 SQL ops, relies on cascade delete for type-detail rows)

### 8d. Modernization Considerations for This Module
- The type-per-table design (`motor`/`house`/`endowment`/`commercial`) is a natural candidate for either a polymorphic domain model (single `Policy` aggregate with a type-specific value object) or separate microservices per product line.
- `policyType` as a single-character code with no lookup/reference table in Db2 (the `ctype`/`ptype`/`rtype`/`htype` files are WSIM test-data generators, not a Db2-governed reference table) — a modern design should introduce a proper `policy_type` reference table for extensibility (new products) and validation.
- The `claim` table has schema but no online program — worth confirming with business owners whether claims processing was descoped, exists elsewhere, or is a genuine gap.

---

## 9. File-Type Summary

| Category | Extension(s) | Count | Notes |
|---|---|---|---|
| COBOL source | `.cbl` | 30 | 100% CICS-online; 0 batch |
| Copybooks | `.cpy` | 11 | COMMAREA + SOA integration layouts |
| BMS maps | `.bms` | 1 | 1 map set, 6 map panels |
| JCL | `.jcl` | 32 | Build/deploy/Db2/CICSPlex SM/web-services/WSIM utility jobs — no recurring business-batch jobs |
| Data / sample files | `.txt` | 46 | 2 VSAM seed files + 44 WSIM reference/script files |
| Event bindings | `.evbind` | 1 | XML — CICS event processing definition |
| REXX scripts | `.rexx` | 2 | Installation/customization execs |
| Shell scripts | `.sh` | 1 | Data-set allocation & deployment (`install.sh`) |
| Documentation | `.md` | 12 (+2 checkpoint copies) | Architecture, Install, Build, Test, Reference, per-component READMEs |
| Image | `.jpg` | 1 | Topology diagram |
| Manifest | `.csv` | 1 | Original → restructured path mapping |
| **Total** | | **~147** | |

### Language / Technology Footprint
| Technology | Role |
|---|---|
| COBOL | Business logic, presentation logic, data access (100% CICS) |
| CICS (BMS, COMMAREA, LINK, TSQ, Named Counters) | Transaction processing, screen handling, in-region messaging |
| Db2 for z/OS (SQL DDL/DML, embedded SQL) | System of record for customer & policy data |
| VSAM (KSDS) | Secondary/legacy data store, two-phase-commit test target |
| JCL | Build, deployment, and environment provisioning |
| REXX | Installation-time customization scripting |
| XML (CICS Event Binding) | Business-event capture configuration |
| Shell (`sh`) | Cross-platform install automation |

---

*Generated from static analysis of the uploaded source package — program classifications derived by scanning for `EXEC CICS`, `EXEC SQL`, `SEND/RECEIVE MAP`, and `LINK PROGRAM` statements across all 30 COBOL modules, cross-referenced with `DOCUMENTATION/Reference.md` and `DOCUMENTATION/Architecture.md`.*
