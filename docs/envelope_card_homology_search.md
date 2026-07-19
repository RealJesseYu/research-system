# Envelope Card — (homology_search, homology_search)

> **STATUS: DRAFT — signed-from-real-runs (BLAST backend), external review
> pending.** §3A numbers MEASURED in `homology-search-prod` (BLAST 2.16.0+). The
> HMMER backend of this bundle is added in the next D.2 increment (same
> substrate, same card). HUMAN-FACING ONLY (R-20.5-1). ENROLLED
> `calibrating`/`routable=False` — inert (`contract_for("homology_search")`
> raises).

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, regime) pair |
| Substrate | `homology_search` (the ruled BLAST+HMMER bundle; **ENROLLED**, `calibrating`/`routable=False`) |
| Regime | **homology_search**: a local sequence-similarity search against a validly-built database, with Karlin-Altschul e-value statistics. |
| Backends | `tool ∈ {blast, hmmer}` — a typed spec field (never a heuristic/LLM pick). **blast wired now**; hmmer next increment. |
| Tool | **BLAST 2.16.0+** (bioconda; `blastp`), in `homology-search-prod` (from `homology-search-img`, the reusable bioconda base). Databases BAKED at `/opt/blastdb/` — deterministic, no runtime network. **PINNED.** |
| Wrapper | `tools/run_homology_search.py` (deterministic Python, no AI) |
| Class | **filter** — the e-value is the SIGNIFICANCE of similarity, a relative screen |
| Contract text (staged) | `onboarding/homology_search/contract.py` — moves to `substrates.py` at D.4 |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | real `homology-search-prod` runs against the baked `demo_prot` DB (2 sequences): a known-present query, a no-hit query, and a broken-DB fault injection. |
| Signature | `unsigned` |
| Provenance state | `drafted-by-agent` (BLAST backend measured; HMMER pending) |

## 3. Validated envelope

### 3A. Cases actually exercised (disk-cited, MEASURED — BLAST backend)
| Case | Query | DB | Result | e_value (QoI) |
|---|---|---|---|---|
| known hit | a sequence present in `demo_prot` | `demo_prot` | search ran, 1 hit | **4.36e-58** (strong) |
| no homolog | a `W×30` sequence | `demo_prot` | search ran cleanly, **0 hits** | **None** (valid — a real 'no homolog at this cutoff') |
| **DB-integrity JAIL** | known sequence | `_broken_selftest` (missing DB) | **search could NOT run** (DB error on stderr, exit 0) | **None, valid=False** — distinct from '0 hits' |

The known hit reproduces e-value **4.36e-58**; determinism verified (identical
repeat → identical e-value). **The load-bearing result: a clean 0-hits run
(valid=True, qoi=None) is DISTINGUISHED from a search that could not run
(valid=False)** — BLAST exits 0 on a missing DB, so the wrapper gates on a
stderr error scan, not the exit code.

### 3B. Ruled envelope bounds (R-CARD-2 — Class / Criterion / Consequence both sides)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **H1 — THE DID-IT-WORK / DB-INTEGRITY GATE** | The search must run against a valid DB with NO error | `CHECKABLE:semantic` (stderr scan, in code) | blastp stderr carries no BLAST error marker (exit code is NOT trusted — a missing DB exits 0) | clean run → **the result is trustworthy**; a BLAST DB/query error → **defer/setup_error** (valid=False), NOT reported as '0 hits' |
| **H2** | e-value below the caller's stated threshold | `CHECKABLE:numeric` | the best (min) e-value vs the spec's threshold | e-value ≤ threshold → **TRUST as a significance filter**; above → **defer/refine** (no significant homolog at this cutoff) |
| **H3** | Query is a valid protein sequence | `CHECKABLE:membership` (pre-run) | `query` is amino-acid letters | valid → eligible; else → **setup_error** |
| **H4** | Database on the baked allowlist | `CHECKABLE:membership` (pre-run) | `database ∈ DATABASE_ALLOWLIST` | on list → eligible; off list → **setup_error** |
| **H5 (C1-hole)** | e-value ≠ homology/function | **JUDGMENT / KNOWN GAP** | **none the gate can read** — statistical significance of SIMILARITY is not homology, orthology, or function | any claim that a significant hit IS a homolog/functional match → **defer**; the e-value is a similarity-significance screen only. Low-complexity & composition bias also live here. |

## 4. Known failure modes
- **4A. Missing/malformed DB read as '0 hits' → the dangerous case (structural, H1).** BLAST prints a DB error to stderr and **exits 0 with no output** — indistinguishable from a legitimate no-hit if you check exit code + count. The wrapper's stderr error scan is the only defense; proven by triggering (`_broken_selftest` → valid=False). A clean 0-hits run stays valid=True/qoi=None.
- **4B. e-value read as homology/function → defer (H5, the C1-hole).** Invisible to every diagnostic — the search is perfectly healthy; the number is significance-of-similarity only.
- **4C. Non-protein / off-allowlist input → setup_error (H3/H4).**
- **4D. Container down / timeout → transient.** One retry, then honest failure.

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Whether the search ran against a valid DB with no error (H1) | Whether a significant hit is a true homolog / functional match (H5) |
| The best (min) e-value; the hit count (incl. 0) | Whether the mismatch/e-value cutoff captures all biologically-relevant homologs |
| Input validity: protein query, allowlist DB (H3/H4) | (HMMER's profile-based remote homology — pending backend) |

## 6. Extraction contract + QoI status
Typed input `{database, query, tool, quantity}`; `tool` is an explicit spec field
`∈ {blast, hmmer}` (closed allowlist, code-validated — never a heuristic/LLM
pick). QoI = `e_value` (the best/min hit e-value), returned only behind the H1
gate. `DATABASE_ALLOWLIST`/`QOI_FIELDS`/`TOOLS` are the single source, imported at
promotion. HMMER backend: pending the next increment (same substrate).

## 7. Cost model (measured — BLAST backend)
| Operating point | Measured wall-clock |
|---|---|
| blastp on the small `demo_prot` DB | **~1.4 s/run** |
| Hard kill limit | 600 s → reported failure |
*Cost is container-exec overhead on this tiny DB; real-DB search scales with DB
size — measured envelope for a large DB is a provisioning-time addition.*

## 8. Negative space + open watches
Out of scope (this increment): the HMMER backend (next increment); nucleotide
search (blastn — v1 is protein blastp); databases outside the baked allowlist;
any homology/function claim beyond similarity-significance (H5). **Open watches:**
(1) **HMMER backend** — wired next, extends `tool`/§3A on this same card. (2)
External reviewer — pending. (3) Registration deferred —
`contract_for("homology_search")` must keep raising until a D.4 ruling. (4) Real
reference databases baked at provisioning; today only `demo_prot`.
