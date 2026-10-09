# Complexity Analysis — GenApp (General Insurance Application)
### Legacy Modernization Assessment

---

## 1. Method

Metrics were computed by static text analysis of all **31 COBOL programs** in `COBOL/` (one program, `LGWEBST5`, was omitted from the earlier two reports' program counts by oversight — the portfolio has always contained 31 programs; this report corrects that count).

For each program, the following were counted directly from source:

| Metric | How it was counted |
|---|---|
| **Total lines** | `wc -l` on the raw `.cbl` file |
| **Code lines** | Lines that are neither blank nor a `*`-comment line |
| **`IF` statements** | Lines starting with `IF ` (case-insensitive) |
| **`EVALUATE` / `WHEN` clauses** | Occurrences of `EVALUATE` and `WHEN` |
| **`PERFORM` statements** | All `PERFORM` occurrences, then split into **looping** (`PERFORM ... UNTIL/VARYING`, or the cursor-fetch idiom `WITH TEST AFTER UNTIL`) vs. **simple** (calling a paragraph once, no loop) |
| **`GO TO`** | Explicit unstructured branches |
| **`EXEC CICS`** | All CICS API command invocations |
| **`EXEC SQL`** | All embedded Db2 statements |
| **Paragraph count** | Lines matching a 7-space-indented `PARAGRAPH-NAME.` pattern |
| **`AND`/`OR`** | Boolean operators, as a proxy for compound-condition density |
| **Approximate nesting depth** | A running counter incremented on `IF`/`EVALUATE` and decremented on `END-IF`/`END-EVALUATE`, tracking the maximum depth reached — a coarse approximation, not a true AST-based measurement |

**Composite "complexity score"** = `IFs + EVALUATEs + WHENs + all PERFORMs + AND/OR count + 1`. This is a **McCabe-style proxy**, not a compiler-verified cyclomatic complexity number. Its main limitation, confirmed during this analysis: **it counts every `PERFORM` — including simple, non-looping, sequential paragraph calls — as if it added a decision branch.** Two programs (`LGWEBST5`, `LGSETUP`) score artificially high on this composite because they are long chains of straight-line, sequential `PERFORM`s (no `UNTIL`/`VARYING`, no real branching) rather than deep or tangled decision logic. Section 4 (Hotspots) treats these separately from genuinely branch-heavy programs and explains why.

No COBOL structure/complexity tool (e.g., a compiler-based CC analyzer) was available in this environment — all figures below are derived from pattern-matching against source text and should be treated as **directional indicators for prioritization, not certified metrics**.

---

## 2. Portfolio Summary

| Metric | Value |
|---|---|
| COBOL programs | **31** |
| Total lines (COBOL) | **8,982** |
| Code lines (COBOL, non-blank/non-comment) | **6,500** |
| Copybooks | 11 (417 total lines) |
| BMS map set | 1 (688 lines, 6 map panels) |
| JCL members | 32 (3,485 total lines) — the single largest JCL member, `db2cre.jcl`, is 1,248 lines (schema DDL) |
| Total `EXEC CICS` commands (COBOL) | **500** |
| Total `EXEC SQL` statements (COBOL) | **57**, concentrated in only 8 of 31 programs (the Db2 data-management layer) |
| Total `GO TO` statements | **79**, concentrated almost entirely (78 of 79) in the 5 presentation programs |
| Average code lines per program | ~210 |
| Average `EXEC CICS` per program | ~16 |
| Largest program | `LGWEBST5` — 802 lines / 752 code lines |
| Largest *logic-dense* program | `LGIPDB01` — 1,030 lines / 739 code lines, 33 `IF`s, 16 `EXEC SQL` |
| Smallest program | `LGACVS01` — 121 lines, a single-purpose VSAM-write wrapper |

**Overall shape of the portfolio:** a small number of programs (the Db2 inquiry/update layer and the presentation layer) carry a disproportionate share of the total complexity; the majority of programs (VSAM wrappers, most business-logic programs) are short, single-purpose, and structurally simple. This is a favorable characteristic for modernization — see Section 6.

---

## 3. Per-Program Metrics

| Program | Tier | Lines | Code Lines | IFs | EVAL/WHEN | PERFORM (loop/simple) | GO TO | CICS | SQL | Paragraphs | Max Nest (approx) | Composite Score |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `LGIPDB01` | Data (Db2) | 1,030 | 739 | 33 | 1/8 | 2 loop / 23 simple | 0 | 12 | **16** | 5 | 3 | **99** |
| `LGWEBST5` | Infra | 802 | 752 | 1 | 0/0 | 0 loop / 24 simple | 0 | 50 | 0 | 1 | 1 | 27 *(inflated — see §1/§4)* |
| `LGUPDB01` | Data (Db2) | 535 | 324 | 14 | 3/9 | 0 loop / 16 simple | 0 | 14 | 12 | 9 | 3 | **63** |
| `LGSETUP` | Infra | 533 | 482 | 1 | 0/0 | 0 | 0 | **84** | 0 | 1 | 1 | 3 *(low true complexity — see §4)* |
| `LGAPDB01` | Data (Db2) | 595 | 408 | 9 | 3/13 | 0 loop / 12 simple | 0 | 20 | 11 | 7 | 2 | **50** |
| `LGTESTP4` | Presentation | 318 | 264 | 8 | 2/6 | 0 | 14 | 20 | 0 | 9 | **6** | 34 |
| `LGDPDB01` | Data (Db2) | 245 | 131 | 6 | 0/0 | 0 loop / 3 simple | 0 | 10 | 3 | 3 | 2 | 24 |
| `LGICDB01` | Data (Db2) | 245 | 141 | 4 | 1/4 | 0 | 0 | 9 | 3 | 4 | 2 | 21 |
| `LGACDB01` | Data (Db2) | 328 | 213 | 8 | 0/0 | 0 loop / 5 simple | 0 | 13 | 5 | 3 | 2 | 20 |
| `LGUPOL01` | Business | 201 | 117 | 6 | 1/4 | 0 loop / 2 simple | 0 | 11 | 0 | 4 | 2 | 20 |
| `LGDPOL01` | Business | 186 | 101 | 6 | 0/0 | 0 loop / 2 simple | 0 | 10 | 0 | 3 | 2 | 19 |
| `LGTESTC1` | Presentation | 347 | 282 | 8 | 1/4 | 0 | 13 | 30 | 0 | 9 | 3 | 18 |
| `LGTESTP1` | Presentation | 318 | 259 | 6 | 2/7 | 0 | 17 | 26 | 0 | 9 | 3 | 17 |
| `LGTESTP2` | Presentation | 300 | 244 | 6 | 2/7 | 0 | 17 | 25 | 0 | 9 | 3 | 17 |
| `LGTESTP3` | Presentation | 299 | 241 | 6 | 2/7 | 0 | 17 | 25 | 0 | 9 | 3 | 17 |
| `LGICVS01` | Data (VSAM) | 230 | 180 | 9 | 0/0 | 0 loop / 1 simple | 0 | 14 | 0 | 1 | 2 | 17 |
| `LGUCDB01` | Data (Db2) | 222 | 141 | 5 | 0/0 | 0 loop / 3 simple | 0 | 8 | 4 | 4 | 2 | 15 |
| `LGACDB02` | Data (Db2) | 225 | 126 | 4 | 1/2 | 0 loop / 3 simple | 0 | 9 | 3 | 3 | 2 | 15 |
| `LGAPOL01` | Business | 169 | 89 | 4 | 0/0 | 0 loop / 2 simple | 0 | 9 | 0 | 2 | 2 | 13 |
| `LGICUS01` | Business | 166 | 96 | 4 | 0/0 | 0 loop / 2 simple | 0 | 9 | 0 | 4 | 2 | 13 |
| `LGUPVS01` | Data (VSAM) | 206 | 162 | 4 | 1/5 | 0 loop / 2 simple | 0 | 11 | 0 | 2 | 2 | 13 |
| `LGACUS01` | Business | 179 | 95 | 4 | 0/0 | 0 loop / 2 simple | 0 | 9 | 0 | 3 | 2 | 12 |
| `LGUCUS01` | Business | 172 | 96 | 4 | 0/0 | 0 loop / 2 simple | 1 | 8 | 0 | 4 | 2 | 12 |
| `LGAPVS01` | Data (VSAM) | 188 | 146 | 3 | 1/5 | 0 loop / 1 simple | 0 | 7 | 0 | 2 | 2 | 11 |
| `LGIPOL01` | Business | 139 | 82 | 3 | 0/0 | 0 loop / 1 simple | 0 | 8 | 0 | 2 | 2 | 10 |
| `LGASTAT1` | Infra | 140 | 106 | 6 | 0/0 | 0 | 0 | 9 | 0 | 1 | 3 | 9 |
| `LGUCVS01` | Data (VSAM) | 136 | 102 | 4 | 0/0 | 0 loop / 2 simple | 0 | 11 | 0 | 2 | 2 | 7 |
| `LGIPVS01` | Data (VSAM) | 149 | 111 | 3 | 0/0 | 0 | 0 | 7 | 0 | 1 | 1 | 6 |
| `LGACVS01` | Data (VSAM) | 121 | 88 | 3 | 0/0 | 0 loop / 1 simple | 0 | 8 | 0 | 2 | 2 | 5 |
| `LGDPVS01` | Data (VSAM) | 132 | 97 | 3 | 0/0 | 0 loop / 1 simple | 0 | 7 | 0 | 2 | 2 | 5 |
| `LGSTSQ` | Infra | 126 | 85 | 3 | 0/0 | 0 | 0 | 7 | 0 | 1 | 1 | 4 |

*(Sorted by composite complexity score, descending. `LGWEBST5` and `LGSETUP` are annotated because their raw scores overstate genuine decision complexity — see Sections 1 and 4.)*

---

## 4. Hotspots

### 4a. Genuine logic hotspots (real branching/decision complexity)

**`LGIPDB01` — Inquire Policy, Db2 layer — the single most complex program in the portfolio.**
- 1,030 lines, 33 `IF`s, 16 `EXEC SQL` statements, 5 largely-parallel paragraphs: `GET-MOTOR-DB2-INFO`, `GET-ENDOW-DB2-INFO`, `GET-HOUSE-DB2-INFO`, and (per the earlier Dependency Reference) commercial-policy cursor logic.
- **Root cause of complexity: policy-type fan-out.** The program implements essentially the same "open cursor → fetch → map columns → close cursor → handle SQLCODE 0/+100/other" pattern **four times**, once per policy type (Motor/Endowment/House/Commercial), plus a 5-row-limited cursor variant for Commercial multi-match lookups. This is duplicated logic, not deep algorithmic complexity — a strong signal for consolidation (see Section 6).
- Handles 6 distinct return codes (`00`, `01`, `88`, `89`, `90`, `98`) depending on which cursor stage failed.

**`LGUPDB01` — Update Policy, Db2 layer — second-highest genuine complexity.**
- 535 lines, 14 `IF`s, 12 `EXEC SQL`, same four-way type fan-out pattern (`UPDATE-MOTOR-DB2-INFO`, `UPDATE-ENDOW-DB2-INFO`, `UPDATE-HOUSE-DB2-INFO`, plus `UPDATE-POLICY-DB2-INFO`), **plus** the optimistic-concurrency timestamp-comparison logic layered on top (see the Business Rules report, Section 6) — this combination of type fan-out *and* concurrency-control branching makes it the most intricate single decision tree in the codebase.

**`LGAPDB01` — Add Policy, Db2 layer — third-highest genuine complexity.**
- 595 lines, 9 `IF`s, 13 `EVALUATE`/`WHEN`, 11 `EXEC SQL`, the same four-way fan-out (`INSERT-MOTOR`, `INSERT-ENDOW`, `INSERT-HOUSE`, `INSERT-COMMERCIAL`, plus `INSERT-POLICY`), plus the named-counter/identity-column fallback branch (Business Rules report, Section 10).

**`LGTESTP4` — Commercial policy menu — highest-nesting presentation program.**
- Approximate max nesting depth of **6** (vs. 2–3 for every other program in the portfolio) and the only presentation program whose composite score (34) is driven by real conditional logic rather than its `GO TO` count alone — worth a closer manual read before migration, as deeply nested 3270 dialog logic is often the hardest presentation logic to re-platform cleanly.

### 4b. Inflated-score programs (large but not genuinely complex)

**`LGSETUP` — 84 `EXEC CICS` commands, but a composite score of only 3.**
- Structure: **37 paired `Exec CICS Delete` / `Exec CICS Define` blocks**, one pair per named counter or TSQ resource being initialized, with essentially no conditional branching around them. This is **repetitive boilerplate**, not complex logic — every block does the same two-step "delete if exists, then define" idiom against a different resource name. A textbook candidate for table-driven refactoring (loop over a resource-name array) if this program is ever touched again, and a *low-risk* migration target despite its size and CICS-command count.

**`LGWEBST5` — 802 lines, 50 `EXEC CICS` commands, composite score inflated to 27 purely by `PERFORM` count.**
- Structure: **23 near-identical calls to a single paragraph, `Tran-Rate-Counts`**, each presumably differing only in which counter/transaction code is passed — again a repetition pattern, not a decision-tree pattern. True cyclomatic complexity (branch count) is low (1 `IF`, 0 `EVALUATE`). Like `LGSETUP`, this is large-but-shallow: safe to consolidate into a data-driven loop, and low-risk to migrate once consolidated.

**Combined observation:** both of the portfolio's *largest by line count* programs are large because of **copy-pasted repetition**, not because of intrinsic problem complexity — a strong positive signal that the codebase's true logical complexity is more concentrated (and more manageable) than raw line counts alone would suggest.

---

## 5. Structural Observations

- **`GO TO` usage is isolated to the presentation tier.** 78 of the portfolio's 79 `GO TO` statements occur in the 5 `LGTEST*` programs, implementing an old-style "goto a common exit label" pattern (`ENDIT-STARTIT`, `NO-DATA`, `NO-ADD`, `NO-UPD`, `NO-DELETE`, `CLEARIT`, `ENDIT`) after each menu-option branch. **Zero `GO TO`s exist in any business-logic, Db2, or VSAM program** — those 26 programs are cleanly structured with `PERFORM`/`EXIT` and in-line `IF`/`END-IF`. This means the unstructured-control-flow risk is fully contained to one architectural layer, simplifying remediation scope.
- **Type-fan-out duplication is the dominant complexity driver**, appearing identically in `LGAPDB01`, `LGIPDB01`, and `LGUPDB01` (the three most complex programs): each implements near-identical per-policy-type logic four times over rather than a single type-parameterized routine. This single pattern accounts for a large share of total portfolio complexity concentrated in just 3 of 31 programs.
- **Db2 SQL is heavily concentrated**: 57 of 57 `EXEC SQL` statements sit in only 8 of 31 programs (all Db2-tier programs), confirming a clean separation between SQL-bearing and SQL-free code — a favorable trait, since Db2-to-modern-datastore migration work can be scoped precisely to those 8 files without touching the other 23.
- **The VSAM tier is uniformly simple**: all 7 VSAM data-access programs (`LG*VS01`) score in the lowest quartile of the composite metric (5–17), each wrapping exactly one CICS file verb (Section 3 of the Dependency Reference) — the simplest, lowest-risk tier to re-platform or retire.
- **Presentation-tier programs are structurally near-identical to one another**: `LGTESTP1`/`LGTESTP2`/`LGTESTP3` have *line-for-line matching* metrics (6 IFs, 2 EVALUATE, 7 WHEN, 17 GOTOs, composite 17) because they are the same Motor/Endowment/House logic template copy-pasted per policy type — the same duplication pattern seen in the Db2 tier, just at the presentation layer.
- **Paragraph density is low relative to line count** in the largest programs (`LGIPDB01`: 5 paragraphs across 739 code lines; `LGSETUP`/`LGWEBST5`/`LGICVS01`/`LGIPVS01`: essentially 1 paragraph each) — these programs rely on long linear sections rather than fine-grained decomposition, which will make unit-level extraction (e.g., for microservice boundaries) more labor-intensive than the paragraph count alone would suggest.
- **Nesting depth is shallow almost everywhere** (max 2–3 for all but `LGTESTP4`'s outlier depth of 6) — this is a genuinely simple codebase by control-flow-depth standards, consistent with GenApp's origin as an IBM training/demo application rather than a battle-hardened production system with years of accumulated exception-handling layers.

---

## 6. Migration / Modernization Effort Signal

| Signal | Assessment |
|---|---|
| **Overall codebase size** | Small (8,982 total lines / 6,500 code lines across 31 programs) — well within range for a full manual re-platform or an AI-assisted rewrite; not a candidate requiring automated bulk-transformation tooling on cost grounds alone. |
| **Complexity concentration** | High — **3 of 31 programs** (`LGIPDB01`, `LGUPDB01`, `LGAPDB01`) account for a disproportionate share of genuine decision complexity, all driven by the *same* root cause (per-policy-type fan-out). Fixing/refactoring this one pattern would flatten the portfolio's complexity profile substantially. |
| **Refactor-before-migrate opportunity** | Strong. Both complexity hotspots (type fan-out in `LG*PDB01`) and the two "big but shallow" programs (`LGSETUP`, `LGWEBST5`, repetitive boilerplate) are prime candidates for **table-driven consolidation before migration** — collapsing 4 near-identical code paths into 1 parameterized routine would reduce both LOC and true complexity in the hardest-to-migrate programs, and is lower-risk to do in COBOL first than to carry the duplication into a new language/platform. |
| **Structural-risk containment** | Favorable — the only unstructured-control-flow risk (`GO TO`, 79 occurrences) is fully isolated to the 5 presentation programs and does not leak into business or data logic, so remediation/rewrite of `GO TO` patterns can be scoped narrowly. |
| **Data-access-tier migration risk** | Low for VSAM (7 simple, single-verb programs — natural 1:1 mapping to repository methods or API endpoints), moderate for Db2 (8 programs, all SQL cleanly isolated there, but 3 of the 8 are the portfolio's biggest hotspots and will need the type-fan-out refactor addressed either before or during migration). |
| **Business-logic-tier migration risk** | Low — all 7 business-logic programs (`LG*US01`/`LG*POL01`) are short (82–201 lines), simple (composite scores 10–20), `GO TO`-free, and follow one consistent Link-then-check-return-code pattern; strong candidates for direct, mechanical translation or for collapsing into a thin orchestration layer in a modern architecture. |
| **Presentation-tier migration risk** | Moderate — not because of algorithmic complexity, but because 3270/BMS screen-flow logic (menu `EVALUATE`s, `GO TO`-based exit handling, conversational `TRANSID` re-invocation) has no direct equivalent in a modern web/API front end and will require a genuine redesign, not a line-by-line port; `LGTESTP4`'s outlier nesting depth (6) makes it the one presentation program warranting a careful manual walkthrough rather than templated conversion. |
| **Est. relative migration effort by tier (informal ranking, not hours)** | VSAM tier (lowest) < Business-logic tier < Db2 tier < Presentation tier (highest) — driven respectively by: uniformity/simplicity; uniformity/simplicity; concentrated-but-fixable type-fan-out complexity; architectural paradigm mismatch (3270 pseudo-conversational vs. modern UI/API). |

---

## 7. Caveats

- **All metrics are static-text pattern matches, not compiler-derived.** No COBOL parser or true AST-based complexity tool was available in this environment; counts of `IF`, `EVALUATE`, `PERFORM`, etc. are regex/line-pattern matches and can be thrown off by unusual formatting, continuation lines, or in-line comments not caught by the comment filter.
- **The composite "complexity score" is a McCabe-style proxy, not a validated cyclomatic-complexity number**, and — as shown for `LGWEBST5` and `LGSETUP` — can overstate complexity for programs with many *sequential, non-branching* `PERFORM`s. Always read Section 4's qualitative discussion alongside Section 3's raw numbers; do not rank migration priority by the composite score column alone.
- **Nesting depth is a coarse approximation** (a simple open/close counter on `IF`/`EVALUATE`...`END-IF`/`END-EVALUATE`), not a true parse-tree depth measurement, and may undercount nesting inside `PERFORM`ed paragraphs that live outside the syntactic block being measured (COBOL's paragraph-based structure means "nesting" doesn't map as cleanly onto block-structured-language intuitions).
- **Copybook-included code is not reflected in these per-program line/complexity counts** — `LGCMAREA` (103 lines), `LGPOLICY`, and `SSMAP` are `COPY`'d into many programs at compile time but counted here only against the copybook itself (Section 2), not added into each including program's totals. A compiled/expanded-source complexity count would be higher for every program that copies them.
- **JCL, BMS, and copybook complexity were not scored** — this analysis is scoped to the 31 COBOL programs only, per the request. The 32 JCL members (3,485 lines) and the BMS map set (688 lines) are inventoried by line count in Section 2 but not analyzed for their own structural complexity (e.g., JCL step conditionality, BMS map-field complexity).
- **Test coverage / regression-risk data is not available from static analysis** — this report describes structural and logical complexity of the source as written; it says nothing about how well-tested each program is, which would materially change actual migration risk and effort.
- **This analysis reflects the 31-program set found in the uploaded `source.zip`.** The two earlier reports (Application Inventory, Dependency Reference) stated a count of "30" COBOL programs; that was an undercount corrected here — all downstream figures in those earlier reports that depend on "30 programs" should be read as "31."

---

## 8. Anything Else — Additional Observations

- **Complexity does not correlate with call-chain depth.** The programs deepest in the LINK chain (e.g., `LGACDB02`, a leaf called only by `LGACDB01`) are among the *simplest* in the portfolio (composite score 15, 225 lines) — complexity in this codebase is a function of **how many policy types a program must handle**, not how deep in the call graph it sits.
- **The Db2 tier's complexity is "wide," not "deep."** All three hotspot programs (`LG*PDB01` for Add/Inquire/Update) have shallow nesting (max depth 2–3) but wide fan-out (4–5 parallel paragraphs) — meaning the risk during migration is less about untangling deeply nested logic and more about **correctly enumerating and preserving every one of the 4 policy-type-specific column/field mappings** in each program. A checklist-driven migration approach (verify each of Motor/Endowment/House/Commercial handled identically) is more appropriate here than a general code-simplification effort.
- **A single consolidation refactor — parameterizing the four policy-type branches in `LGAPDB01`/`LGIPDB01`/`LGUPDB01` on `CA-REQUEST-ID`'s embedded type code — would simultaneously address the portfolio's top 3 hotspots**, its clearest duplication pattern (Section 5), and (per the Business Rules report) make it easier to introduce a governed `POLICY_TYPE` reference table and support new product lines. This is the single highest-leverage modernization action identifiable from this analysis.

---

*Generated from static complexity analysis (regex/line-pattern metrics) of all 31 COBOL programs in the uploaded source package. Composite scores and nesting-depth figures are directional proxies, not compiler-verified measurements — see Section 7 for full caveats before using these numbers for effort estimation or sizing.*
