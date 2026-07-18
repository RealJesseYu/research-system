# Gate report — BIO Wave D.2 pre-fan-out (B/C resolved, A RULED w/ corrections)

**Status: A ruled by exception (corrections 1 & 2 applied). Fan-out authorized.
No wrapper built at time of this A. Era `6befb63`.**
Build chat, 2026-07-18. Canonical committed copy (pasted chat versions truncate);
future gate reports live in this directory. This file is the single canonical A
table (the draft `D2_draft_A_B_C.md` Part A is superseded — points here — to
avoid two copies drifting).

Prior context: D.1 closed (era `a07f939` → `6befb63`; repo_facts `b2b62fd`; L2
loud-stop-only; packet tracked). Suite 1219 collected (1201 + 18).

---

## B result — BLAST vs HMMER: **BUNDLE → census 12**

Disk evidence: BLAST/HMMER have **nothing on disk** (no wrappers, onboarding, or
refs). On the merits they co-tie in their primary use — signature
`{query_sequence, database}`, regime `homology_search`, e-value QoI — so a split
would L2-loud-stop forever. → BUNDLE into `homology_search`, `tool ∈ {blast,hmmer}`
a **typed spec field** (see the CONFIRM below). Their only real distinguisher
(HMMER profile input vs BLAST sequence) is an L0 split (proves L0, already proven
by the cantilevers), NOT L1a — so bundling loses no L1a proof.

**L1a's live discriminating proof** is carried by `alphafold_db` vs `boltz2`:
both wired with **required signature `{protein_sequence}`** (boltz2's `ligand` is
an OPTIONAL param, NOT in the required signature — so `alphafold_db`'s signature
⊆ `boltz2`'s, cantilever-style), but **distinct regime shapes**
(`predicted_structure_lookup` vs `structure_affinity_prediction`). A protein-only
spec therefore serves BOTH at L0 and **routes at L1a on the declared regime** — the
first live proof of L1a's discriminating half (fires once these are provisioned
out of T3/T4).

**`bio_db_lookup`: 1 card, but a 4-API wrapper** (PDB/PubChem/UniProt/ChEMBL, each
its own namespace/grammar/error/rate-limit surface behind the `database` field) —
priced as the most expensive single wrapper in the wave; card/battery stay 1
(battery deferred).

**CONFIRMED (owner):** `homology_search`'s `tool ∈ {blast, hmmer}` and
`retrosynthesis`'s / `crispr_guide_scoring`'s / `bio_db_lookup`'s backend/database
selectors are **explicit typed SPEC FIELDS**, validated in code against a closed
allowlist — never an internal heuristic, never an LLM pick.

## C result — tiers; T3's third = `retrosynthesis`

Bindings acknowledged: all 12 get wrapper + 7 dispatch surfaces + R-CARD-2 card +
enrollment `calibrating`/`routable=False` in D.2 (batteries are the subset); real
batteries only for runnable tools; provisioned tools get real batteries ONCE
provisioned; deferred lookups get NONE (never-trusted-alone, no envelope); NEVER a
stub battery; nothing in T3/T4 promoted (D.4) without a REAL passing battery.

| Tier | Substrates | Battery |
|---|---|---|
| **T1 — real, FIRST (local pip, deterministic)** | `rdkit`, `cobrapy`, `cas_offinder` | real ×3 |
| **T2 — real (local CLI, deterministic)** | `autodock_vina`, `crispr_guide_scoring`, `homology_search`, `mafft` | real ×4 |
| **T3 — provisioned (GPU / weights / heavy DB)** | `boltz2`, `proteinmpnn`, `retrosynthesis` | real once provisioned ×3 |
| **T4 — battery-DEFERRED (network-API lookup)** | `alphafold_db`, `bio_db_lookup` | none — flagged deferred ×2 |

**7 real + 3 provisioned-later + 2 deferred.**

---

## A — the RULED 12-row §4b checklist (corrections 1 & 2 applied)

**Correction 1 (regime column):** the six vocab-shape entries replaced with real
task-regime shapes derived from each wrapper's STATED capability — regime shapes
now distinct from the QoI-vocab shapes (so the R-23.5-5c envelope is non-vacuous
and L1a has something to split on). **Correction 2 (checkability):** every
trust-split now gates ONLY on what the gate can read (valid input; the tool ran;
the score is well-formed and in range → TRUST as a relative screen / report),
with WHERE it reads it; "within training distribution / model coverage" is removed
from every precondition and lives in the C1-hole. **C1-hole column unchanged**
except two ADDITIVE clauses (proteinmpnn, crispr) housing the moved
training-distribution concern — flagged in-cell with «+».

Regime-shape names (all owner-approved / ruled): `bounded_enumeration`,
`descriptor_computation`, `fba_steady_state`, `rigid_pocket_dock`,
`guide_activity_scoring`, `homology_search`, `msa_alignment`,
`structure_affinity_prediction`, `backbone_conditioned_sequence_design`,
`retrosynthetic_route_search`, `predicted_structure_lookup`, `record_db_lookup`.

| # | substrate | regime shape | class | inside → TRUST split (what the gate checks + where read → consequence both sides) | conf→verdict | QoI + spec key | C1-hole KNOWN GAP | cost·tier |
|---|---|---|---|---|---|---|---|---|
| 1 | `cas_offinder` | `bounded_enumeration` | answer | guide/pattern parses **AND** genome is indexed **AND** mismatch+bulge counts ≤ the declared budget (read from the spec's typed fields) **AND** enumeration terminates → **TRUST the count**; unparseable pattern / unindexed genome / over-budget / non-terminating → **defer/setup_error** | deterministic; valid enumeration → trust-eligible | `off_target_count` · `fixed_summary{quantity:"off_target_count"}` | counts SEQUENCE matches only — **not functional off-targets** (chromatin accessibility / actual cutting efficiency unmodeled) | s–min, det., local · **T1** |
| 2 | `rdkit` | `descriptor_computation` | answer | molecule string parses **AND** RDKit sanitization succeeds **AND** the requested descriptor is on RDKit's analytic-descriptor allowlist (read from `qoi.quantity`) **AND** a finite value returns → **TRUST**; parse/sanitize failure / non-allowlisted or ML-predicted property / non-finite → **defer/setup_error** | deterministic; valid sanitize → trust-eligible | named descriptor · `fixed_summary{quantity:"<descriptor>"}` | descriptors are COMPUTED PROXIES, **not measured properties** (computed logP ≠ experimental) | ms, det., pip · **T1** |
| 3 | `cobrapy` | `fba_steady_state` | filter | SBML model parses **AND** the FBA LP returns `status=optimal` with a finite objective (read from the solver status) → **TRUST the optimum as a feasibility/relative-growth screen**; parse failure / `infeasible`/`unbounded` / non-finite → **defer/setup_error** | LP `optimal` → trust-eligible (rel.); else defer | `growth_rate` · `fixed_summary{quantity:"growth_rate"}` | FBA gives a feasible steady-state OPTIMUM, **not measured growth** — no regulation/kinetics; media & objective choice uncheckable | ms–s, det., pip · **T1** |
| 4 | `autodock_vina` | `rigid_pocket_dock` | filter | ligand+receptor parse **AND** the search box is well-formed and encloses the declared pocket (read from the spec's box fields) **AND** Vina exits cleanly **AND** the top `docking_score` is finite and in the scoring fn's numeric range → **TRUST as a relative screen**; parse failure / malformed box / failed run / out-of-range/missing → **defer/setup_error** | score + top-pose RMSD spread; rel-only | `docking_score` · `fixed_summary{quantity:"docking_score"}` | rigid receptor + empirical scoring — **no induced fit / explicit water / entropy**; score ≠ true affinity | s–min, seeded det., pip · **T2** |
| 5 | `crispr_guide_scoring` (CRISPOR/CHOPCHOP, `backend` field) | `guide_activity_scoring` | filter | guide parses **AND** its PAM matches the selected enzyme's motif (CHECKABLE:membership; read from the spec's guide+enzyme fields) **AND** the target genome is indexed **AND** the backend returns a score in [0,1] → **TRUST the score as a relative rank**; malformed guide/PAM / unindexed genome / out-of-range/missing → **defer/setup_error** | backend score 0–1; rel | `activity_score` · `fixed_summary{quantity:"activity_score"}` + `backend` | predicts RELATIVE efficiency, **not measured cutting/editing** in the real cellular context (chromatin/delivery uncheckable); «+» whether the guide's species/PAM-context sits within the scoring model's coverage is not checkable from the spec | fast det., local · **T2** |
| 6 | `homology_search` (BLAST+HMMER, `tool` field) | `homology_search` | answer/filter | query parses **AND** the database is indexed **AND** `tool ∈ {blast,hmmer}` is a declared spec field **AND** the search completes **AND** the best-hit e-value ≤ the spec's stated threshold (CHECKABLE:numeric; result vs spec threshold) → **TRUST as a significance filter**; parse failure / unindexed DB / failed search / above-threshold → **defer/refine** | e-value/bit-score; rel (significance) | `e_value` (min) · `named_quantity{kind:"evalue", target:"<query-vs-db>", reduction:"min"}` + `tool` | e-value is significance of SIMILARITY, **not homology/function**; low-complexity & composition bias, matrix/profile choice uncheckable | s–min, det., local CLI · **T2** |
| 7 | `mafft` | `msa_alignment` | filter/answer | ≥2 sequences parse **AND** MAFFT exits cleanly **AND** the alignment + its identity/SP metric are well-formed (read from tool output) → **TRUST the alignment as computed**; <2 or unparseable seqs / failed run / malformed metric → **defer/setup_error** | alignment score; descriptive | `alignment_identity` · `fixed_summary{quantity:"alignment_identity"}` | a computed alignment is a HEURISTIC optimum, **not the true alignment** (guide-tree dependent) | s–min, det., local CLI · **T2** |
| 8 | `boltz2` | `structure_affinity_prediction` | filter | `protein_sequence` (and `ligand` if present) parse **AND** the model run completes without error **AND** the returned affinity/RMSD is finite and in the score's declared range → **TRUST as a relative screen**; malformed input / failed-or-timed-out run / out-of-range/missing → **defer/setup_error**. An explicit absolute-Kd claim in the success-criterion text → **defer** (CHECKABLE:semantic on the claim) | model conf (ipTM); rel-only | `affinity`\|`rmsd` · `fixed_summary{quantity:"affinity"\|"rmsd"}` | predicted affinity ≠ experimental Kd; **OOD generalization / whether the target is within the model's training distribution & absolute calibration uncheckable** | GPU, weights · **T3 (provisioned)** |
| 9 | `proteinmpnn` | `backbone_conditioned_sequence_design` | filter | the input backbone structure parses **AND** the model run completes **AND** the returned sequence-recovery/score is finite and in [0,1] → **TRUST as a relative design screen**; malformed structure / failed run / out-of-range/missing → **defer/setup_error** | score/perplexity; rel | `seq_recovery` · `fixed_summary{quantity:"seq_recovery"}` | high recovery / low perplexity **≠ the sequence folds or functions**; wet-lab validation uncheckable; «+» whether the backbone sits within the model's training distribution is not checkable from the spec | GPU/weights · **T3 (provisioned)** |
| 10 | `retrosynthesis` (AiZynth/ASKCOS, `backend` field) | `retrosynthetic_route_search` | filter | target molecule parses **AND** `backend` is a declared spec field **AND** the route search terminates **AND** the synthesizability score / solved-flag is well-formed → **TRUST as a relative screen**; parse failure / unset backend / non-terminating-or-failed search / malformed → **defer/setup_error** | route score / solved-flag; rel | `synthesizability` · `fixed_summary{quantity:"synthesizability"}` + `backend` | a found route is TEMPLATE-feasible, **not experimentally validated** (yields/conditions/selectivity uncheckable) | heavy models+DB · **T3 (provisioned)** |
| 11 | `alphafold_db` | `predicted_structure_lookup` | lookup | the UniProt id / sequence resolves **AND** AFDB returns a record with a finite `mean_pLDDT` (read from the response) → **report the number, TRUST-as-corroboration-only (never sole basis)**; malformed id / missing record / network failure / non-finite → **defer/setup_error** | pLDDT is the confidence; lookup → never-trust-alone | `mean_pLDDT` (0–100) · `fixed_summary{quantity:"mean_pLDDT"}` | pLDDT is model SELF-confidence, **not experimental accuracy**; disordered / low-pLDDT regions & the model-vs-reality gap uncheckable | network (s), no compute · **T4 (deferred)** |
| 12 | `bio_db_lookup` (PDB/PubChem/UniProt/ChEMBL, `database` field) | `record_db_lookup` | lookup | `database ∈ {pdb,pubchem,uniprot,chembl}` is a declared spec field **AND** the id is well-formed for that namespace **AND** the API returns a well-formed record within the timeout → **report round-trip success, TRUST-as-corroboration-only (never sole basis)**; unset/unknown database / malformed id / missing-or-ambiguous record / network failure/timeout → **defer/setup_error** | lookup → never-trust-alone | round-trip id / record field · `named_quantity{kind:"record_field", target:"<db>:<id>", reduction:"value"}` + `database` | the DB's own curation currency/correctness is unverifiable from inside — **a stale/erroneous record looks identical to a good one** | network (s), 4-API · **T4 (deferred)** |

---

## Fan-out plan (per the packet D.2 per-substrate checklist)
Each of the 12: wrapper (typed input, hard timeout, one retry, capped diagnostics,
log-summarized, **NO LLM in execution**) + 7 dispatch surfaces (contract,
signature, vocab, adapter, QoI translation, run-entry constructor, registry row)
+ R-CARD-2 card (every §3B criterion in "what the gate evaluates + where read →
consequence both sides" form) + state-key scalar confidence + registry row at
`calibrating`/`routable=False`. Tests ADDED, staged to `onboarding/<substrate>/`.
Parallel worktrees, serial merges, FAST-green each merge. Network/GPU wrapper
jails (alphafold_db, bio_db_lookup, boltz2, proteinmpnn) proven by TRIGGERING A
REAL FAILURE, never by reading config. Build order: T1 first.
