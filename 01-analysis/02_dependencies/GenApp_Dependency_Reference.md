# Dependency Reference — GenApp (General Insurance Application)
### Legacy Modernization Assessment

Derived by static analysis of the uploaded source package: every `EXEC CICS LINK PROGRAM`, `COPY`, `EXEC CICS READ/WRITE/REWRITE/DELETE FILE`, and JCL `EXEC PGM=` statement was extracted from all 30 COBOL programs and 32 JCL members, cross-checked against `DOCUMENTATION/Reference.md` and CICS resource-definition JCL (`cdef121.jcl`).

---

## 1. Online (CICS) Navigation — Program-to-Program Control Transfer

Every business function follows the same three-hop pattern: **3270 transaction → Presentation → Business logic → Data management (Db2 and/or VSAM) → shared utility (`LGSTSQ`)**, using `EXEC CICS LINK PROGRAM` (synchronous call/return, same task).

### 1a. Transaction → Entry Program (from `cdef121.jcl` resource definitions)
| Transaction | Entry Program | Function |
|---|---|---|
| `SSC1` | `LGTESTC1` | Customer menu |
| `SSP1` | `LGTESTP1` | Motor policy menu |
| `SSP2` | `LGTESTP2` | Endowment policy menu |
| `SSP3` | `LGTESTP3` | House policy menu |
| `SSP4` | `LGTESTP4` | Commercial policy menu |
| `LGSE` | `LGSETUP` | Initialize counters/TSQs (setup utility) |
| `LGCF` | `LGICVS01` | Retrieve random customer number from VSAM (WSIM support) |
| `LGPF` | `LGIPVS01` | Retrieve policy/customer number from VSAM (WSIM support) |

### 1b. Full Control-Transfer Chains

**Customer chains** (from `SSC1` / `LGTESTC1`):
```
LGTESTC1 ──LINK──▶ LGACUS01 ──LINK──▶ LGACDB01 ──LINK──▶ LGACDB02 ──LINK──▶ LGSTSQ
                                          │
                                          └──LINK──▶ LGACVS01 ──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ

LGTESTC1 ──LINK──▶ LGICUS01 ──LINK──▶ LGICDB01 ──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ

LGTESTC1 ──LINK──▶ LGUCUS01 ──LINK──▶ LGUCDB01 ──LINK──▶ LGUCVS01 ──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ
```

**Policy chains** (identical pattern from `SSP1`/`LGTESTP1`, `SSP2`/`LGTESTP2`, `SSP3`/`LGTESTP3`; `SSP4`/`LGTESTP4` omits Update):
```
LGTESTPn ──LINK──▶ LGIPOL01 ──LINK──▶ LGIPDB01 ──LINK──▶ LGSTSQ
LGTESTPn ──LINK──▶ LGAPOL01 ──LINK──▶ LGAPDB01 ──LINK──▶ LGAPVS01 ──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ
LGTESTPn ──LINK──▶ LGUPOL01 ──LINK──▶ LGUPDB01 ──LINK──▶ LGUPVS01 ──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ            (n = 1,2,3 only)
LGTESTPn ──LINK──▶ LGDPOL01 ──LINK──▶ LGDPDB01 ──LINK──▶ LGDPVS01 ──LINK──▶ LGSTSQ
                                          └──LINK──▶ LGSTSQ
```

### 1c. Complete LINK Target Table (every program's outbound calls)
| Caller | Links To |
|---|---|
| `LGTESTC1` | `LGACUS01`, `LGICUS01`, `LGUCUS01` |
| `LGTESTP1` | `LGAPOL01`, `LGDPOL01`, `LGIPOL01`, `LGUPOL01` |
| `LGTESTP2` | `LGAPOL01`, `LGDPOL01`, `LGIPOL01`, `LGUPOL01` |
| `LGTESTP3` | `LGAPOL01`, `LGDPOL01`, `LGIPOL01`, `LGUPOL01` |
| `LGTESTP4` | `LGAPOL01`, `LGDPOL01`, `LGIPOL01` *(no update path)* |
| `LGACUS01` | `LGACDB01`, `LGSTSQ` |
| `LGICUS01` | `LGICDB01`, `LGSTSQ` |
| `LGUCUS01` | `LGUCDB01`, `LGSTSQ` |
| `LGAPOL01` | `LGAPDB01`, `LGSTSQ` |
| `LGIPOL01` | `LGIPDB01`, `LGSTSQ` |
| `LGUPOL01` | `LGUPDB01`, `LGSTSQ` |
| `LGDPOL01` | `LGDPDB01`, `LGSTSQ` |
| `LGACDB01` | `LGACDB02`, `LGACVS01`, `LGSTSQ` |
| `LGACDB02` | `LGSTSQ` |
| `LGICDB01` | `LGSTSQ` |
| `LGUCDB01` | `LGUCVS01`, `LGSTSQ` |
| `LGAPDB01` | `LGAPVS01`, `LGSTSQ` |
| `LGIPDB01` | `LGSTSQ` |
| `LGUPDB01` | `LGUPVS01`, `LGSTSQ` |
| `LGDPDB01` | `LGDPVS01`, `LGSTSQ` |
| `LGACVS01` / `LGUCVS01` / `LGAPVS01` / `LGUPVS01` / `LGDPVS01` | `LGSTSQ` only |
| `LGICVS01`, `LGIPVS01` | *(none — leaf/terminal programs)* |
| `LGSTSQ` | *(none — terminal utility, writes to TSQ `GENAERRS`)* |
| `LGSETUP`, `LGASTAT1`, `LGWEBST5` | *(none — standalone infrastructure programs, no static LINK chain)* |

**Key structural observations:**
- **`LGSTSQ` is the most depended-upon program** — linked from 20 of the other 29 programs as a shared error/diagnostic-logging utility. It is a single point of contention/failure for error handling and a natural candidate for extraction as a common logging service in a modernized design.
- Control flow is strictly **linear and synchronous** (LINK, not XCTL) — the calling program's storage stays on the stack, consistent with a request/reply commarea pattern. This maps cleanly to a request/response microservice call chain.
- `LGACDB01` and `LGUCDB01`/`LGAPDB01`/`LGUPDB01`/`LGDPDB01` are the only business-to-data hops that fan out to *two* downstream data stores (Db2 **and** VSAM) in the same transaction — this is the two-phase-commit boundary described in `Architecture.md` and the highest-risk area for behavioral drift during modernization.
- `LGICDB01`, `LGIPDB01`, `LGICVS01`, `LGIPVS01` (all "Inquire" data programs) call **no further programs** except (for the Db2 pair) `LGSTSQ` — they are read-only leaves.

---

## 2. Copybook Dependencies (`COPY` statements)

| Program | Copybooks Used |
|---|---|
| `LGACUS01` | `LGCMAREA`, `LGPOLICY` |
| `LGACVS01` | `LGCMAREA` |
| `LGACDB01` | `LGPOLICY` |
| `LGACDB02` | `LGPOLICY` |
| `LGICUS01` | `LGCMAREA`, `LGPOLICY` |
| `LGICDB01` | `LGPOLICY` |
| `LGICVS01` | *(none)* |
| `LGUCUS01` | `LGCMAREA` |
| `LGUCVS01` | `LGCMAREA` |
| `LGUCDB01` | *(none)* |
| `LGAPOL01` | `LGCMAREA` |
| `LGAPVS01` | `LGCMAREA` |
| `LGAPDB01` | *(none)* |
| `LGIPOL01` | `LGCMAREA`, `LGPOLICY` |
| `LGIPVS01` | *(none)* |
| `LGIPDB01` | *(none)* |
| `LGUPOL01` | `LGCMAREA` |
| `LGUPVS01` | `LGCMAREA` |
| `LGUPDB01` | *(none)* |
| `LGDPOL01` | `LGCMAREA` |
| `LGDPVS01` | `LGCMAREA` |
| `LGDPDB01` | *(none)* |
| `LGTESTC1` | `LGCMAREA`, `SSMAP` |
| `LGTESTP1` | `LGCMAREA`, `SSMAP` |
| `LGTESTP2` | `LGCMAREA`, `SSMAP` |
| `LGTESTP3` | `LGCMAREA`, `SSMAP` |
| `LGTESTP4` | `LGCMAREA`, `SSMAP` |
| `LGASTAT1` | `LGCMAREA` |
| `LGSETUP` | *(none)* |
| `LGSTSQ` | *(none)* |
| `LGWEBST5` | *(none)* |

**Interpretation:** `LGPOLICY` is used only by Db2-facing/business programs handling policy field lengths; the DB2 host-variable data programs themselves (`LG*DB01`) largely define working storage inline rather than via COPY, so only 4 of 8 Db2 programs use a copybook. `SSMAP` is used exclusively by the 5 presentation programs (as expected — it's the BMS symbolic map).

---

## 3. VSAM File Dependencies

| File (CICS FILE resource) | VSAM Type | Programs Reading/Writing It | Operations |
|---|---|---|---|
| `KSDSCUST` | KSDS | `LGACVS01` | `WRITE` (add customer) |
| | | `LGICVS01` | `READ` (inquire customer) |
| | | `LGUCVS01` | `READ` + `REWRITE` (update customer) |
| `KSDSPOLY` | KSDS | `LGAPVS01` | `WRITE` (add policy) |
| | | `LGIPVS01` | `READ` (inquire policy) |
| | | `LGUPVS01` | `READ` + `REWRITE` (update policy) |
| | | `LGDPVS01` | `DELETE` (delete policy) |

**Key structure:**
- `KSDSCUST` key = first 10 bytes of the record (customer ID).
- `KSDSPOLY` key = first 21 bytes (policy type 1 byte + customer ID 10 bytes + policy number 10 bytes).
- Each VSAM-access program is a thin, single-purpose wrapper around exactly one CICS file verb — clean 1:1 mapping that will simplify a VSAM→relational or VSAM→API refactor (each program is already a natural microservice/repository-method boundary).
- No program performs `STARTBR`/`READNEXT`/`ENDBR` (browse) — the application never scans either VSAM file sequentially; all access is by direct/random key. This is significant for modernization: a key-value store or indexed table substitute for VSAM is sufficient — no need to replicate sequential-browse semantics.

---

## 4. Batch (JCL) Execution Chains

GenApp has no recurring business-batch chain; JCL here performs **one-time build/deploy/provisioning** work. Chains below reflect typical *installation order* (per `DOCUMENTATION/Building.md`/`Installation.md`), not a scheduled dependency graph.

```
1. @ADEF121  (define & load VSAM: KSDSCUST, KSDSPOLY)
2. @ASMMAP   (assemble ssmap.bms → load module)
3. @CDEF121  (define CICS resources: transactions, programs, files — single region)
      │  optional variants:
      ├─ @CDEF122  (topology environment resources)
      ├─ @CDEF123  (workload-managed environment resources)
      ├─ @CDEF124  (web-services resources)
      └─ @CDEF125  (workload-simulation resources)
4. @COBOL    (compile all 30 COBOL programs → load library)
5. @DB2CRE   (create Db2 storage group, database, 7 tablespaces, 8 tables/indexes, grants, seed INSERTs)
6. @DB2BIND  (bind Db2 plan/packages required by the LG*DB01 programs — must follow @DB2CRE and @COBOL)
      └─ (optional) @DB2DEL — drop the GenApp database (teardown path)
```

**Optional coupling-facility / CICSPlex extensions** (independent branch, only needed if testing named counters / shared TSQ / multi-region topology):
```
@SAMPNCS  (start named counter server)
@SAMPTSQ  (start shared TSQ server)
@SAMPCMA  (start a CMAS)
@DEFDREP  (define CMAS data repository) ──▶ @CPSMDE2 (CICSPlex SM definitions)
@DEFWREP  (define WUI repository) ──▶ @SAMPWUI (start CICSPlex SM Web User Interface)
```

**Web-services branch** (independent of the two chains above; requires @CDEF124 first):
```
@WSAAC01  (generate web service — customer add)
@WSAIC01  (generate web service — customer inquiry)
@WSAAP01  (generate web service — policy add)
@WSAIP01  (generate web service — policy inquiry)
@WSAUC01  (generate web service — customer update)
@WSAUP01  (generate web service — policy update)
@WSAVC01  (generate web service — read KSDSCUST directly)
@WSAVP01  (generate web service — read KSDSPOLY directly)
```

**Workload Simulator branch** (test/load generation, run after the core chain completes):
```
@ITPSTL  (translate WSIM programs into scripts)
   │
@ITPENTR (start WSIM — creates customer/policy records using DATA/ss*.txt & ws*.txt scripts)
   │
@ITPLL   (format WSIM log file for review)
```

---

## 5. Extension-Module Dependencies (layered on the core)

All extensions are additive — the base configuration (VSAM + Db2, single region) runs without any of them. Each layers on top of the base `LG*` program set and `cdef121.jcl` resource baseline.

| Extension | Depends On (from base) | Adds |
|---|---|---|
| **Named Counter Server** | `LGSETUP`, `LGASTAT1`; `KSDSCUST`/`GENACUSTNUM` counter concept | `sampncs.jcl`; coupling-facility named-counter pool resource |
| **Shared TSQ** | `LGSTSQ` (already core), `LGWEBST5` | `samptsq.jcl`; `GENASTST` TSMODEL; `GENACNTL`/`GENAERRS` queue names become *shared* rather than local |
| **CICS Event Processing** | Every `LG*`-prefixed program (event filter matches `currentProgram` starting with `LG`) | `Transaction_Counters.evbind`; `GENAEV01` BUNDLE — captures `Count_business_trans` on each LINK |
| **Web Services (SOA)** | The 4 business-logic + Db2/VSAM chains for Customer-Add/Inquire/Update and Policy-Add/Inquire/Update/Read-VSAM | `cdef124.jcl` (PIPELINE `GENAPIP1`, TCPIPSERVICE `GENATCP1`); `wsa*.jcl` binding-generation jobs; **note:** the SOA-facing copybooks (`soaic01`, `soaipb1/e1/h1/m1`, `soavcii/o`, `soavpii/o`, `pollook`, `polloo2`) exist in `COPYBOOKS/` but are **not referenced by any COPY statement in the 30 supplied COBOL programs** — see Section 6 caveat |
| **CICSPlex SM Topology** | `cdef122–125.jcl` supersede/extend `cdef121.jcl`'s single-region definitions | `cpsmde2.jcl`, `sampcma.jcl`, `defdrep.jcl`, `defwrep.jcl`, `sampwui.jcl` |
| **Workload Simulator** | `LGCF`/`LGPF` transactions (`LGICVS01`/`LGIPVS01` as WSIM helper entry points), `cdef125.jcl` | `itpentr/itpll/itpstl.jcl`; all 44 `DATA/ss*`/`ws*` reference & script files |
| **Two-Phase Commit (Db2+VSAM)** | Already embedded in base — `LGACDB01→LGACVS01`, `LGUCDB01→LGUCVS01`, `LGAPDB01→LGAPVS01`, `LGUPDB01→LGUPVS01`, `LGDPDB01→LGDPVS01` | No separate resource — architectural characteristic of the core add/update/delete data-management programs |

---

## 6. `app-transaction-type-db2` — Dependency View

> As noted in the Application Inventory, no module literally named `app-transaction-type-db2` exists in the uploaded package or in the current public GenApp repository (verified against `cicsdev/cics-genapp` on GitHub, which today contains only the `base/` component). The dependencies below describe the **transaction-type (policy-type) management capability actually present in `base/`**, expressed as a dependency chain.

```
Db2 policy.policyType (M/E/H/C)
        │
        ├── LGAPDB01 ──INSERT──▶ policy + {motor|endowment|house|commercial}   (type-specific detail table)
        ├── LGIPDB01 ──SELECT──▶ policy JOIN {motor|endowment|house|commercial} on policyType
        ├── LGUPDB01 ──UPDATE──▶ policy + {motor|endowment|house|commercial}
        └── LGDPDB01 ──DELETE──▶ policy   (cascades to detail table via FK ON DELETE CASCADE)

Each Db2 program is reached only via its business-logic parent:
  LGAPOL01 → LGAPDB01     LGIPOL01 → LGIPDB01     LGUPOL01 → LGUPDB01     LGDPOL01 → LGDPDB01

Each business-logic program is reached only via the type-specific presentation program:
  LGTESTP1 (Motor) / LGTESTP2 (Endowment) / LGTESTP3 (House) / LGTESTP4 (Commercial)
```

**Db2 object dependency (from `db2cre.jcl`):** `customer` ← `policy` ← {`motor`, `endowment`, `house`, `commercial`, `claim`} (all foreign-key children of `policy.policyNumber`, `ON DELETE CASCADE`). `claim` has schema but no program dependency in this package (no `LG*` program references it) — a gap to confirm with the business.

---

## 7. `app-vsam-mq` — Dependency View

> **Finding: No MQ (message-queue) dependency exists anywhere in the uploaded source.** A targeted search of all 30 COBOL programs for MQ verbs (`MQOPEN`, `MQPUT`, `MQGET`, `EXEC CICS ... MQ`) returned zero matches, and this extension directory is not present in the uploaded package or in the current public `cicsdev/cics-genapp` repository. The application's only asynchronous/queue-like mechanism is **CICS Temporary Storage (TSQ)**, not MQ:

| Mechanism | Programs | Queues Used |
|---|---|---|
| CICS TSQ (not MQ) | `LGSTSQ` (writer, called by 20 programs) | `GENAERRS` (error/diagnostic queue) |
| CICS TSQ (not MQ) | `LGSETUP` (initializer), business/Db2 layer implicitly via customer-number range tracking | `GENACNTL` (control queue — customer number range) |
| CICS TSQ (not MQ) | `LGWEBST5` (writer, every 60s) | Shared TSQ for business-monitor statistics |

**Modernization implication:** if a target architecture requires MQ (or a cloud equivalent — Kafka, SNS/SQS, etc.), it would be a **net-new integration**, not a lift-and-shift of existing functionality — there is no legacy MQ dependency to preserve or replicate. The existing VSAM-file dependency (Section 3) is the only "VSAM" half of a prospective `app-vsam-mq` extension; the "MQ" half would need to be designed from scratch, likely by intercepting the same points where `LGSTSQ` is currently called (all 20 error-logging call sites) or where the Db2/VSAM two-phase-commit boundary is (`LGACDB01`, `LGUCDB01`, `LGAPDB01`, `LGUPDB01`, `LGDPDB01`).

---

## 8. Copybook Usage by Program

| Copybook | Used By |
|---|---|
| `LGCMAREA` | `LGTESTC1`, `LGTESTP1`, `LGTESTP2`, `LGTESTP3`, `LGTESTP4`, `LGACUS01`, `LGICUS01`, `LGUCUS01`, `LGACVS01`, `LGUCVS01`, `LGAPOL01`, `LGUPOL01`, `LGDPOL01`, `LGAPVS01`, `LGUPVS01`, `LGDPVS01`, `LGIPOL01`, `LGASTAT1` *(18 programs)* |
| `LGPOLICY` | `LGACUS01`, `LGICUS01`, `LGIPOL01`, `LGACDB01`, `LGACDB02`, `LGICDB01` *(6 programs)* |
| `SSMAP` | `LGTESTC1`, `LGTESTP1`, `LGTESTP2`, `LGTESTP3`, `LGTESTP4` *(5 presentation programs — the full set)* |
| `soaic01.cpy`, `soaipb1.cpy`, `soaipe1.cpy`, `soaiph1.cpy`, `soaipm1.cpy`, `soavcii.cpy`, `soavcio.cpy`, `soavpii.cpy`, `soavpio.cpy`, `pollook.cpy`, `polloo2.cpy` | **None of the 30 supplied COBOL programs** — see caveat below |

**Caveat on the 11 unreferenced copybooks:** They are present under `COPYBOOKS/` and appear designed for the web-services / SOA integration layer (their names align with the `WSAAC01/AP01/IC01/IP01/UC01/UP01/VC01/VP01` web-service–generation JCL). They are most likely consumed by artifacts **generated at deploy time by the Web Services Assistant** (from the `wsa*.jcl` jobs) rather than compiled directly into the base COBOL, or they support extension/adapter programs not included in this upload. This should be confirmed with the source team before assuming they are dead code — for modernization purposes, treat them as **interface contracts for the SOA layer**, not as currently-compiled dependencies of the core 30 programs.

---

## 9. Core Application — Online CICS Programs (`cbl/`)

Dependency summary for all 30 programs in `COBOL/` (equivalent of `base/src/*.cbl` in the source repo), consolidating Sections 1–3:

| Program | Tier | Calls (LINK) | Copybooks | VSAM File | Db2 |
|---|---|---|---|---|---|
| `LGTESTC1` | Presentation | LGACUS01, LGICUS01, LGUCUS01 | LGCMAREA, SSMAP | — | — |
| `LGTESTP1` | Presentation | LGAPOL01, LGDPOL01, LGIPOL01, LGUPOL01 | LGCMAREA, SSMAP | — | — |
| `LGTESTP2` | Presentation | LGAPOL01, LGDPOL01, LGIPOL01, LGUPOL01 | LGCMAREA, SSMAP | — | — |
| `LGTESTP3` | Presentation | LGAPOL01, LGDPOL01, LGIPOL01, LGUPOL01 | LGCMAREA, SSMAP | — | — |
| `LGTESTP4` | Presentation | LGAPOL01, LGDPOL01, LGIPOL01 | LGCMAREA, SSMAP | — | — |
| `LGACUS01` | Business | LGACDB01, LGSTSQ | LGCMAREA, LGPOLICY | — | — |
| `LGICUS01` | Business | LGICDB01, LGSTSQ | LGCMAREA, LGPOLICY | — | — |
| `LGUCUS01` | Business | LGUCDB01, LGSTSQ | LGCMAREA | — | — |
| `LGAPOL01` | Business | LGAPDB01, LGSTSQ | LGCMAREA | — | — |
| `LGIPOL01` | Business | LGIPDB01, LGSTSQ | LGCMAREA, LGPOLICY | — | — |
| `LGUPOL01` | Business | LGUPDB01, LGSTSQ | LGCMAREA | — | — |
| `LGDPOL01` | Business | LGDPDB01, LGSTSQ | LGCMAREA | — | — |
| `LGACDB01` | Data (Db2) | LGACDB02, LGACVS01, LGSTSQ | LGPOLICY | — | ✅ (5 stmts) |
| `LGACDB02` | Data (Db2) | LGSTSQ | LGPOLICY | — | ✅ (3 stmts) |
| `LGICDB01` | Data (Db2) | LGSTSQ | LGPOLICY | — | ✅ (3 stmts) |
| `LGUCDB01` | Data (Db2) | LGUCVS01, LGSTSQ | — | — | ✅ (4 stmts) |
| `LGAPDB01` | Data (Db2) | LGAPVS01, LGSTSQ | — | — | ✅ (11 stmts) |
| `LGIPDB01` | Data (Db2) | LGSTSQ | — | — | ✅ (16 stmts) |
| `LGUPDB01` | Data (Db2) | LGUPVS01, LGSTSQ | — | — | ✅ (12 stmts) |
| `LGDPDB01` | Data (Db2) | LGSTSQ | — | — | ✅ (3 stmts) |
| `LGACVS01` | Data (VSAM) | LGSTSQ | LGCMAREA | KSDSCUST (WRITE) | — |
| `LGICVS01` | Data (VSAM) | — | — | KSDSCUST (READ) | — |
| `LGUCVS01` | Data (VSAM) | LGSTSQ | LGCMAREA | KSDSCUST (READ+REWRITE) | — |
| `LGAPVS01` | Data (VSAM) | LGSTSQ | LGCMAREA | KSDSPOLY (WRITE) | — |
| `LGIPVS01` | Data (VSAM) | — | — | KSDSPOLY (READ) | — |
| `LGUPVS01` | Data (VSAM) | LGSTSQ | LGCMAREA | KSDSPOLY (READ+REWRITE) | — |
| `LGDPVS01` | Data (VSAM) | LGSTSQ | LGCMAREA | KSDSPOLY (DELETE) | — |
| `LGSETUP` | Infrastructure | — | — | — | — |
| `LGSTSQ` | Infrastructure (shared utility) | — | — | — | — |
| `LGASTAT1` | Infrastructure | — | LGCMAREA | — | — |
| `LGWEBST5` | Infrastructure | — | — | — | — |

---

## 10. Copybook Cross-Reference — Which Programs Use Each Shared Copybook

| Copybook | Category | Programs (count) | Notes |
|---|---|---|---|
| `LGCMAREA` | COMMAREA (universal) | 18 programs — all 5 presentation, most business & VSAM-data programs | Central inter-program communication structure; changing its layout has the widest blast radius in the codebase |
| `LGPOLICY` | Db2 field-length reference | 6 programs — `LGACUS01`, `LGICUS01`, `LGIPOL01` (business); `LGACDB01`, `LGACDB02`, `LGICDB01` (Db2 data) | Defines field lengths for Customer/Policy/Endowment/House/Motor Db2 columns so length changes are made in one place |
| `SSMAP` | BMS symbolic map | 5 programs — all presentation-tier programs (`LGTESTC1`, `LGTESTP1-4`) | 1:1 with the single `ssmap.bms` map set |
| `soaic01.cpy` | SOA/web-service (customer inquiry) | 0 supplied programs | Likely used by generated web-service adapter, not core COBOL |
| `soaipb1.cpy` | SOA/web-service (policy inquiry, base) | 0 supplied programs | Same caveat |
| `soaipe1.cpy` | SOA/web-service (policy inquiry, endowment) | 0 supplied programs | Same caveat |
| `soaiph1.cpy` | SOA/web-service (policy inquiry, house) | 0 supplied programs | Same caveat |
| `soaipm1.cpy` | SOA/web-service (policy inquiry, motor) | 0 supplied programs | Same caveat |
| `soavcii.cpy` | SOA/web-service (VSAM customer inquiry, input) | 0 supplied programs | Same caveat |
| `soavcio.cpy` | SOA/web-service (VSAM customer inquiry, output) | 0 supplied programs | Same caveat |
| `soavpii.cpy` | SOA/web-service (VSAM policy inquiry, input) | 0 supplied programs | Same caveat |
| `soavpio.cpy` | SOA/web-service (VSAM policy inquiry, output) | 0 supplied programs | Same caveat |
| `pollook.cpy` | Policy/customer lookup request | 0 supplied programs | Same caveat |
| `polloo2.cpy` | Policy lookup (with policy type) | 0 supplied programs | Same caveat |

**Modernization risk flag:** `LGCMAREA` is a "god copybook" (103 lines, multiple `REDEFINES` for different request types sharing one 32K commarea) used by 18 of 30 programs. In a service-decomposition effort, this copybook should be broken into per-use-case DTOs (Add-Customer, Inquire-Customer, Add-Policy, etc.) rather than carried forward as a single shared structure — its `REDEFINES` pattern is a common source of subtle bugs when only some fields are populated per call.

---

*Generated from static dependency analysis of the uploaded source package (COBOL `LINK`/`COPY`/file-I/O statements, JCL job steps, and CICS resource-definition JCL). Cross-referenced against the public `cicsdev/cics-genapp` GitHub repository to confirm which requested module names (`app-transaction-type-db2`, `app-vsam-mq`) are and are not present in the current codebase.*
