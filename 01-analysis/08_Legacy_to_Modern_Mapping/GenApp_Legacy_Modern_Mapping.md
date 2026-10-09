# Legacy → Modern Mapping — GenApp (General Insurance Application)
### Legacy Modernization Assessment

This document maps every legacy component identified across the prior six reports (Application Inventory, Dependency Reference, Business Rules, Complexity Analysis, Database Analysis, Transaction Matrix, CRUD Matrix) to a proposed modern equivalent, with rationale grounded in what the source actually does — not a generic rewrite template. Each mapping states *why* that target is appropriate given GenApp's specific structure, and flags where the legacy component has **no direct equivalent** and represents new-build scope rather than a migration.

---

## 1. Method

Mappings are organized by architectural layer, matching the 3-tier shape already present in the legacy system (Presentation → Business Logic → Data Management), plus cross-cutting layers (Infrastructure/Operational, Security, Batch/Build, and Extension Modules). For each row: **Legacy component**, **What it does today** (one line, for traceability), **Proposed modern equivalent**, and **Migration rationale/risk**. A confidence indicator marks how directly portable each mapping is:

| Marker | Meaning |
|---|---|
| 🟢 | Direct, low-risk mapping — mechanical translation is largely sufficient |
| 🟡 | Requires redesign — same *purpose*, different *shape* in the target |
| 🔴 | No legacy equivalent — net-new build, not a migration |

---

## 2. Architecture-Level Mapping

| Legacy | Modern | Rationale |
|---|---|---|
| CICS region (single/multi, pseudo-conversational) | Container-orchestrated microservices or a modular monolith on Kubernetes/ECS, behind an API gateway | 🟡 GenApp's clean 3-tier LINK-chain structure (Dependency Reference, Sections 1, 9) already resembles a service call graph — each program is a natural function boundary — but CICS's pseudo-conversational state model has no 1:1 modern equivalent and must be redesigned as stateless request/response |
| 3270 terminal + BMS screens | Web UI (React/Angular) or mobile app, calling REST/GraphQL APIs | 🟡 The 3270 "menu → inquire → add/update/delete" interaction pattern maps conceptually to a modern form-based UI, but requires genuine UX redesign, not a screen-scrape |
| `EXEC CICS LINK PROGRAM` synchronous call chain | Synchronous REST/gRPC calls between services, or in-process method calls if kept as a modular monolith | 🟢 Every LINK in the Dependency Reference (Section 1) is already a clean synchronous request/response — this is the most directly portable structural pattern in the whole codebase |
| CICS `SYNCPOINT`/`SYNCPOINT ROLLBACK` (2-phase commit across Db2+VSAM) | Database transactions (single datastore) or a saga/outbox pattern (if data is split across services) | 🟡 If the target consolidates Db2+VSAM into one datastore, this becomes a plain ACID transaction (simpler than today); if split across microservices, needs a saga pattern — either way, the existing 5 two-phase-commit boundaries (`LGACDB01→LGACVS01`, etc., per Dependency Reference Section 5) are exactly the places to redesign first |

---

## 3. Presentation Tier Mapping

| Legacy Program | Function | Modern Equivalent | Confidence | Notes |
|---|---|---|---|---|
| `LGTESTC1` | Customer menu (3270, txn `SSC1`) | REST endpoints `GET/POST/PUT /customers` + a web/mobile "Customer" screen | 🟡 | Menu-option branching (Transaction Matrix, Section 2) maps cleanly to HTTP verbs per CRUD function; the `GO TO`-based screen-flow control (Complexity Analysis, Section 5) does not translate and should be redesigned as normal request handlers |
| `LGTESTP1`–`LGTESTP4` | Policy menus per type (txns `SSP1`–`SSP4`) | REST endpoints `GET/POST/PUT/DELETE /policies?type={motor\|endowment\|house\|commercial}` or one resource per type | 🟡 | The near-identical template duplication across these 4 programs (Complexity Analysis, Section 5) is a strong signal to **consolidate into one parameterized policy controller** in the target architecture rather than porting 4 separate screens 1:1 |
| BMS map set `SSMAP` (6 panels) | Web/mobile UI components (forms, list views, detail views) | 🔴 | No direct migration path exists for 3270 field-attribute definitions into modern UI components — this is a UX/UI design exercise informed by the *data* the maps carry, not a conversion |
| Two-turnaround "Inquire-then-Update" pattern (Transaction Matrix, Section 5) | Single `PUT /policies/{id}` call carrying the full updated object, validated server-side with optimistic-concurrency headers (e.g., `If-Match` / `ETag`) | 🟢 | This is a *simplification* opportunity — the legacy two-round-trip pattern exists only because of 3270's conversational constraints; a modern API can do this in one call |

---

## 4. Business Logic Tier Mapping

| Legacy Program(s) | Function | Modern Equivalent | Confidence | Notes |
|---|---|---|---|---|
| `LGACUS01`, `LGICUS01`, `LGUCUS01` | Customer business rules (validate, orchestrate Db2+VSAM) | `CustomerService` (Add/Get/Update methods) in a Customer microservice or module | 🟢 | Short (82–201 lines), simple (Complexity Analysis composite scores 12–13), `GO TO`-free — the most directly translatable tier in the codebase |
| `LGAPOL01`, `LGIPOL01`, `LGUPOL01`, `LGDPOL01` | Policy business rules (all 4 types share these 4 programs) | `PolicyService` (Add/Get/Update/Delete methods), type-parameterized | 🟢 | Same favorable characteristics as Customer business logic — already the correct shape for a modern service layer |
| Named-counter-with-Db2-identity-fallback pattern (`LGACDB01`) | A single ID-generation strategy — either the target database's native auto-increment/UUID, or a dedicated ID-generation service (e.g., Snowflake-style) if cross-service uniqueness is needed | 🟢 | The dual-path fallback exists only to support both single-region and coupling-facility topologies — a modern deployment doesn't need this complexity; pick one generator |
| Optimistic-concurrency check (`LGUPDB01`'s `LASTCHANGED` comparison) | HTTP `ETag`/`If-Match` conditional updates, or the target ORM's built-in optimistic-locking (`@Version` column) | 🟢 | This is a well-understood, directly portable pattern — just needs re-expression in the target framework's idiom |
| Missing optimistic lock on Customer updates (Business Rules, Section 6) | Apply the same `ETag`/version-column pattern uniformly to Customer as well as Policy | 🟡 | Flagged as an inconsistency in the legacy system — modernization is the right moment to fix it, not preserve it |

---

## 5. Data Management Tier Mapping

| Legacy Component | Modern Equivalent | Confidence | Notes |
|---|---|---|---|
| Db2 `customer`, `policy`, `endowment`, `house`, `motor`, `commercial` tables (Database Analysis, Section 2) | Managed relational database (e.g., PostgreSQL, Aurora, Cloud SQL) with an equivalent normalized schema, or a document store if the policy-type polymorphism is redesigned as a single flexible schema | 🟢 (relational) / 🟡 (document) | The existing FK/cascade-delete structure translates directly to any relational target; a document-store migration is viable too, given each policy type is already effectively a self-contained record, but changes the referential-integrity model (see Section 8 gap) |
| Db2 `claim` table (schema-only, no application CRUD — CRUD Matrix Section 4) | Same table, but **new service/API code must be written** — there is nothing to migrate on the application side | 🔴 | This is 100% new-build; do not assume claims functionality exists to "lift" |
| VSAM `KSDSCUST`, `KSDSPOLY` (Database Analysis, Section 3) | **Retire.** Since VSAM data is a strict subset of Db2 data (Database Analysis, Section 3b) and no browse/scan access exists anywhere (Dependency Reference, Section 3), a cache layer (e.g., Redis) is optional for read performance but VSAM itself has no unique data to preserve | 🟢 | Low-risk retirement — confirmed no VSAM-only fields exist; this is the safest tier to eliminate entirely rather than migrate |
| `LGCMAREA` (COMMAREA copybook, 18-program fan-out) | Per-use-case DTOs/request-response objects (e.g., `AddCustomerRequest`, `InquirePolicyResponse`) | 🟡 | Explicitly flagged in the Dependency Reference (Section 10) as a "god copybook" with `REDEFINES` risk — **do not port this structure as-is**; decompose into one clean object per business operation |
| `LGPOLICY` (Db2 field-length reference copybook) | Shared validation/schema constants (e.g., a JSON Schema, OpenAPI component schema, or ORM entity definitions) | 🟢 | Its narrow purpose (field-length governance) maps cleanly to standard schema-validation tooling in any modern stack |
| `soa*.cpy`, `pollook.cpy`, `polloo2.cpy` (unreferenced by core COBOL — Dependency Reference, Section 10) | If confirmed as the real SOA-layer contract: becomes the basis for the modern API's request/response schema. If confirmed as dead: discard | 🟡 | Confirm with the source team first (per the standing caveat) — don't build the new API contract on unverified legacy copybooks without checking whether they were ever actually used |

---

## 6. Infrastructure / Operational Tier Mapping

| Legacy Component | Function | Modern Equivalent | Confidence | Notes |
|---|---|---|---|---|
| `LGSTSQ` + TSQ `GENAERRS` (called by 20 of 31 programs) | Centralized error/diagnostic logging | Structured logging framework (e.g., JSON logs to CloudWatch/ELK/Datadog), correlation-ID-based tracing | 🟢 | This is a textbook "extract as shared service" candidate — already the most depended-upon component in the legacy system (Dependency Reference, Section 1), so it should become the *first* shared library/sidecar built in the target architecture |
| TSQ `GENACNTL` (customer-number range tracking) | Not needed in a modern architecture if ID generation is handled by the database/ID service directly | 🔴 retire | This existed to support Workload Simulator bookkeeping — no equivalent need exists once WSIM itself is retired (Section 9) |
| `LGASTAT1` + per-function named counters + `LGWEBST5` (transaction-rate statistics) | Application metrics (e.g., Prometheus counters/histograms per endpoint) + a dashboard (Grafana) | 🟢 | Directly analogous purpose — this is exactly what a modern `/metrics` endpoint and time-series dashboard replace |
| Named Counter Server (coupling facility) | Not needed — replaced by native DB auto-increment, UUIDs, or a dedicated ID-generation microservice | 🔴 retire | This was a CICS-specific answer to a distributed-uniqueness problem that has standard modern solutions |
| Shared CICS Temporary Storage (`GENASTST` TSMODEL) | Not needed — replaced by a proper cache (Redis) or message queue if genuine cross-process transient state is required | 🔴 retire | No legacy functionality depends on TSQ *content* being read back (Database Analysis, Section 4) — safe to drop, not preserve |

---

## 7. Batch / JCL Layer Mapping

| Legacy Component | Function | Modern Equivalent | Confidence | Notes |
|---|---|---|---|---|
| `db2cre.jcl`, `adef121.jcl` | Schema/storage provisioning | Infrastructure-as-Code (Terraform/CloudFormation) + database migration tooling (Flyway/Liquibase) using the extracted `genapp_db2_schema.sql` as the starting migration script | 🟢 | Already delivered as a clean, portable script (Database Analysis report) — a direct starting point for a migration-tool baseline |
| `cobol.jcl`, `asmmap.jcl` | Compile/assemble build steps | CI/CD pipeline (GitHub Actions/Jenkins) build stage — irrelevant once source is rewritten in a modern language, or replaced by the modern language's own build tool if COBOL itself is retained via a COBOL-to-Java/C# transpiler approach | 🟡 depends on strategy | Only relevant if pursuing an automated-transpilation modernization path rather than a rewrite — see Section 10 |
| `cdef121–125.jcl` (CICS resource definitions) | Transaction/program/file resource definitions | API route definitions (OpenAPI spec) + container/service deployment manifests (Kubernetes YAML) | 🟢 | The Transaction Matrix report's full transaction-to-function mapping (Section 2) is effectively the OpenAPI spec's table of contents already |
| `cpsmde2.jcl`, `sampcma.jcl`, `defdrep/defwrep.jcl`, `sampwui.jcl` (CICSPlex SM) | Multi-region topology management, ops dashboard | Container orchestration (Kubernetes) for topology; observability stack (Grafana/Datadog) for the ops dashboard | 🟢 | Same underlying need (manage/observe multiple running instances), fully standard tooling exists |
| `wsa*.jcl` (Web Services Assistant) | Generate SOAP/web-service bindings from COBOL programs | OpenAPI/Swagger-generated client/server stubs from the new service definitions | 🟡 | Same *purpose* (generate integration contracts from program shape), but the legacy SOA copybooks' actual usage status is unconfirmed (Section 5) — don't treat this as a ready-made API contract without verification |
| `itpentr/itpll/itpstl.jcl` + WSIM `DATA/ss*`/`ws*` scripts | Synthetic load generation for testing | Modern load-testing tooling (k6, JMeter, Gatling) with test data generated from the same reference vocabularies (`ctype`/`ptype`/`cmake`/`cmodel`/etc., per the Database Analysis report's reference-data caveat) | 🟢 | The domain vocabularies in the WSIM data files are still useful as seed/fixture data even though the WSIM mechanism itself is retired |

---

## 8. Security Mapping

| Legacy Component | Function (or lack thereof) | Modern Equivalent | Confidence | Notes |
|---|---|---|---|---|
| CICS region-level RACF (external, no GenApp-specific config) | 3270 terminal sign-on, if configured at all — GenApp itself has no `RESSEC`/`CMDSEC` set (Business Rules, Section 2) | OAuth2/OIDC (e.g., Auth0, Cognito, Keycloak) or the enterprise's existing IdP, with per-endpoint role/scope checks | 🔴 | **This is entirely new-build.** There is no legacy authentication logic to migrate — the modern security layer must be designed from requirements, not reverse-engineered from GenApp |
| `customer_secure` table (write-only, hardcoded placeholder password — Business Rules, Section 2 / CRUD Matrix, Section 4) | Non-functional demo artifact | **Do not migrate as-is.** If a real customer-facing login is required, build proper password hashing (bcrypt/Argon2) and a genuine authentication flow from scratch | 🔴 | Explicitly flagging: this table's *presence* should not be mistaken for *working* authentication during discovery — a common trap when reverse-engineering demo/training codebases |
| No transaction-level access control (any user can invoke any GenApp transaction) | — | Role-based access control (RBAC) at the API gateway or service layer, mapped to real business roles (e.g., "customer service agent," "underwriter") | 🔴 | New-build; the legacy system provides no role model to inherit |

---

## 9. Extension Module Mapping

| Legacy Extension | Function | Modern Equivalent | Confidence | Notes |
|---|---|---|---|---|
| CICS Event Processing (`Transaction_Counters.evbind`) | Captures a business event on every `LG*` program LINK | Application-level event emission (e.g., publish to Kafka/EventBridge on each business operation) or distributed tracing spans (OpenTelemetry) | 🟢 | Directly analogous — this is exactly what a modern event-driven or observability architecture provides natively |
| Web Services (SOA) layer | Exposes 8 functions as SOAP-style web services | REST/GraphQL API (the primary target architecture itself) | 🟡 | This legacy extension is effectively already "the API" in embryonic form — the modern build supersedes it rather than migrating it literally |
| CICSPlex SM topology | Multi-region scaling/management | Kubernetes horizontal pod autoscaling + service mesh (Istio/Linkerd) | 🟢 | Same purpose, modern tooling is more capable and requires no COBOL-specific configuration |
| Workload Simulator (WSIM) | Synthetic test-transaction generation | Modern load-testing framework (Section 7) | 🟢 | Direct purpose match |
| REXX install/customization scripts | Environment setup automation | Shell scripts / Ansible playbooks / Terraform provisioners | 🟢 | Same purpose, standard modern tooling |
| Two-Phase Commit (Db2+VSAM) | Cross-datastore consistency | Eliminated if data is consolidated into one modern datastore (recommended, since VSAM is retired per Section 5); otherwise a saga pattern if genuinely split | 🟢 | This entire concern likely disappears once VSAM is retired — one less thing to redesign |

---

## 10. Modernization Strategy Options (How to Use This Mapping)

Three broad paths are consistent with the findings across all seven reports; this mapping supports any of them, but the *effort profile* differs:

| Strategy | What it means for this codebase | Where this mapping helps most |
|---|---|---|
| **Full rewrite** (recommended, given findings) | New services in a modern language (Java/C#/Go/Node), new relational schema derived from `genapp_db2_schema.sql`, new REST API derived from the Transaction Matrix, VSAM retired outright | All sections above — this mapping *is* the rewrite blueprint. The Complexity Analysis report's finding that true logical complexity is low and concentrated (3 of 31 programs) makes a rewrite tractable in a small codebase like this one |
| **Automated COBOL transpilation** (e.g., COBOL→Java via a migration tool) | Programs are mechanically converted, preserving structure (including the `LGCMAREA` god-copybook and the 4-way type-fan-out duplication) | Sections 3–4 still apply for planning the *surrounding* architecture (API layer, security), but Sections 5's copybook-decomposition and the type-fan-out consolidation recommendation (Complexity Analysis, Section 6) would need to happen as a **post-transpilation refactor**, not during the mechanical conversion itself |
| **Strangler-fig incremental replacement** | New services stand up alongside the CICS region, transaction-by-transaction, using the Transaction Matrix (8 transactions, 21 functions) as the cutover checklist | The Transaction Matrix report's function-by-function breakdown is the ideal punch-list for sequencing a strangler-fig migration — start with the lowest-risk, highest-value functions (e.g., Inquire Customer/Policy — read-only, `GO TO`-free business logic) before tackling the two-phase-commit Add/Update/Delete paths |

**Given this codebase's specific profile** — small (31 programs, 6,500 code lines), structurally clean (low nesting, isolated `GO TO` usage, uniform tiers), with complexity concentrated in a fixable duplication pattern rather than deep algorithmic difficulty — a **full rewrite is the most defensible recommendation**, informed by this mapping rather than a line-by-line transpilation of legacy artifacts (like `LGCMAREA` or the four-times-repeated type-fan-out logic) that the codebase itself signals should not be preserved.

---

## 11. Quick-Reference — Technology Stack Summary

A condensed, at-a-glance version of the detailed mappings in Sections 2–9, useful as a one-page executive summary:

| Legacy             | Modern                              |
| ------------------ | ----------------------------------- |
| CICS               | FastAPI / application service       |
| COBOL               | Python                              |
| BMS                | React/Streamlit/web UI              |
| COMMAREA           | Pydantic DTO                        |
| Db2                | PostgreSQL                          |
| VSAM KSDS          | PostgreSQL / repository             |
| TSQ                | Redis/logging/observability         |
| Named Counter      | PostgreSQL sequence/UUID/ID service |
| JCL                | CI/CD + Python tooling              |
| CICS LINK          | Service method/API call             |
| SQLCA/return codes | Python exceptions/API responses     |
| BMS map            | REST/UI schema                      |

This summary assumes the **Python/FastAPI/PostgreSQL** stack specifically; Sections 2–9 above frame the same mappings more generally (any modern language/framework/RDBMS) since the target-stack choice should follow the organization's platform standards. If Python/FastAPI is the confirmed target, this table is the fast-reference version of the full mapping.

---

## 12. Caveats

- This mapping reflects **target-architecture options**, not a specific vendor/product recommendation — "PostgreSQL," "Kubernetes," "Kafka," etc. are illustrative of the *category* of modern tool that fills each legacy role; the actual product selection should follow the organization's existing platform standards.
- Every 🔴 (no legacy equivalent) item is **scope the business must explicitly approve** before a migration budget/timeline is set — these are easy to under-estimate if a modernization plan assumes "migrate what exists" without accounting for what must be built new (real security, claims processing, batch posting/interest-fee capability if ever required per the Business Rules report).
- The 🟢/🟡/🔴 confidence markers are directional judgments based on structural analysis (nesting, duplication, coupling, tier separation) documented in the prior six reports — they are not a substitute for a proper migration-effort estimation exercise (story points, team velocity, etc.).
- This mapping assumes the **base GenApp configuration** (Db2 + VSAM, single region) as the migration source. If the actual production system in scope has diverged from this sample application, or has accumulated additional customization not present in this uploaded package, this mapping should be revalidated against the real codebase before being used for planning.

---

*Synthesized from the six prior analysis reports (Application Inventory, Dependency Reference, Business Rules, Complexity Analysis, Database Analysis, Transaction Matrix, CRUD Matrix) generated from static analysis of the uploaded GenApp source package.*
