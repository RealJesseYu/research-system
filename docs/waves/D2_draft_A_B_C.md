# BIO Wave — D.2 DRAFT (A + B + C) — for owner ruling by exception

**Status: DRAFT proposal, UNRULED. No wrappers built. Era `6befb63`.**
Author: build chat, 2026-07-18. This is the "show the design, get the ruling"
artifact the packet's #1 risk demands. Recon findings docs are absent from disk
(known/fine for D.1); every cell below is filled from the packet's D.2 table +
each tool's public semantics + the existing card/vocab machinery
(`docs/envelope_card_ngspice_linear_passive.md` is the R-CARD-2 exemplar;
`tools/qoi_vocab.py` supplies the regime/QoI shapes). **Owner corrects; nothing
is wired.**

Column meanings, anchored to the ngspice card:
- **regime (§3-at-enroll shape)** — the (substrate, physics/compute-regime) card
  unit pinned at enrollment (R-23.5-5c), derived from the wrapper's real
  capability, never invented. Maps to a `qoi_vocab` regime shape or a NEW shape.
- **trust class** — the packet's coarse class: `answer` (the tool's output IS the
  result, deterministic — sympy-like) / `lookup` (authoritative retrieval, never
  trusted alone — web_search precedent) / `filter` (a predictor/screen; relative,
  never absolute).
- **trust split (C4 spine)** — the decisive criterion that separates TRUST from
  defer, with "inside bound → TRUST" explicit (R-CARD-2). This is the defer-fix.
- **conf→verdict** — how the wrapper's scalar `state`/confidence maps to a
  verdict (owner-ruled scalar; the `state`-key pattern).
- **QoI + spec key** — the one scalar QoI and the machine key shape it rides
  (`qoi_vocab` shape).
- **C1-hole KNOWN GAP** — the declared gap the gate CANNOT check (the
  regime-assumption-certainty axis / device-model-honesty analogue, N5-class).
- **card cost** — cost tier + whether local/GPU/network.

---

## PART B FIRST (it fixes the row count A uses)

**The recon bundled some tools onto one packet row. Rule: one wrapper+card per
tool UNLESS two share BOTH regime AND QoI-semantics, in which case bundle behind
one wrapper with the backend as a typed field (the `web_search`/one-wrapper
precedent). Card unit stays (substrate, regime).**

| Packet row | Decision | Why | Resulting substrates |
|---|---|---|---|
| PDB / PubChem / UniProt / ChEMBL | **BUNDLE → 1** (`bio_db_lookup`, `database` typed field) | Identical trust regime (authoritative remote DB, never-trusted-alone) AND identical QoI shape (record/id round-trip). The load-bearing card content — corroboration-required — is the same for all four. | `bio_db_lookup` |
| CRISPOR / CHOPCHOP | **BUNDLE → 1** (`crispr_guide_scoring`, `backend` field) | Shared regime (guide efficiency/off-target scoring for a target site) AND shared QoI (activity/specificity score); CHOPCHOP reuses the same published scoring models. Bundling also avoids a pointless L2 tie. | `crispr_guide_scoring` |
| AiZynth / ASKCOS | **BUNDLE → 1** (`retrosynthesis`, `backend` field) | Shared regime (retrosynthetic MCTS/template route search) AND shared QoI (synthesizability / route-found). | `retrosynthesis` |
| BLAST / HMMER / MAFFT | **SPLIT → 3** | MAFFT is a different regime (multiple-sequence *alignment*) with a different QoI (alignment quality), NOT homology search. BLAST vs HMMER share the e-value QoI but differ in regime (raw local alignment vs profile-HMM remote homology) enough that their trust-splits differ — I recommend SPLIT; acceptable fallback is BLAST+HMMER bundled → 2 if you prefer. | `blast`, `hmmer`, `mafft` |

**Resulting census (recommended): the packet's 11 rows → 13 substrates**
(7 singletons + `bio_db_lookup` + `crispr_guide_scoring` + `retrosynthesis` +
`blast` + `hmmer` + `mafft`). 13 wrappers, 13 cards. Batteries: fewer than 13 —
only the real-battery tiers below (Part C). *(Fallback if BLAST+HMMER bundled:
12 substrates.)* This corrects the packet's "eleven" — the packet's own Block F
warned the count was likely wrong; it is (13, not 11).

Two of the 13 are a deliberate **Step-41 near-neighbour family**: `blast` and
`hmmer` share the `{sequence, database}` signature and the e-value QoI — they are
the first bio pair to exercise L1a/L1b's *discriminating* half (acceptance test
#3's held-open item (i)). They separate on regime-shape (L1a) if their regime
grammars differ, else stop loudly at L2. Likewise the structure family
(`alphafold_db` vs `boltz2`, both `{protein_sequence}`) separates at **L1b** on
the QoI asked (pLDDT vs affinity) — the natural bio proof that L1b routes a
family on its quantity.

---

## PART A — the §4b checklist, one row per resolved substrate (13)

*Every cell filled. Proposal; owner corrects. Spec-key shapes reference
`tools/qoi_vocab.py`; most bio tools return a named scalar → `fixed_summary`
(one `quantity` machine key over the wrapper's own name set) or `named_quantity`
(`kind/target/reduction`). NEW regime shapes are flagged.*

### T1 — local, pip/conda, deterministic (REAL battery, DO FIRST)

**1. `cas_offinder`** — class **answer**
- regime: exhaustive enumeration of sequence near-matches to a guide/pattern in an indexed reference genome within a fixed mismatch+bulge budget (no scoring model). NEW shape `bounded_enumeration`.
- trust split: pattern+genome indexed AND request within the declared mismatch/bulge budget → **TRUST the count**; unindexed genome or over-budget request → **defer/setup_error**.
- conf→verdict: deterministic; `state=valid` enumeration → trust-eligible (no probabilistic confidence).
- QoI + key: `off_target_count` (int) · `fixed_summary {quantity:"off_target_count"}`.
- C1 KNOWN GAP: counts SEQUENCE matches, not FUNCTIONAL off-targets — chromatin accessibility / actual cutting is unmodeled and uncheckable.
- card cost: fast deterministic, scales with genome size (s–min), local, GPU-optional. **T1.**

**2. `rdkit`** — class **answer**
- regime: deterministic 2D/3D molecular descriptor/property computation from a sanitizable parsed molecule (SMILES/mol); cheminformatics, no experimental prediction. Shape `descriptor_set` (≈ fixed_summary over the descriptor allowlist).
- trust split: molecule sanitizes under RDKit's valence model AND the requested descriptor is an ANALYTICALLY-computed one → **TRUST**; unsanitizable molecule OR an ML-predicted property → **defer**.
- conf→verdict: deterministic; `state=valid` parse+sanitize → trust-eligible.
- QoI + key: a named descriptor (`MolWt`/`TPSA`/`NumHDonors`/…) scalar · `fixed_summary {quantity:"<descriptor>"}` over RDKit's descriptor names.
- C1 KNOWN GAP: descriptors are computed PROXIES, not measured properties (computed logP ≠ experimental).
- card cost: ms-fast, deterministic, pip. **T1.**

**3. `cobrapy`** — class **filter**
- regime: constraint-based Flux-Balance Analysis (LP) on a genome-scale metabolic model at steady state; deterministic LP, no kinetics/regulation. NEW shape `fba_steady_state`.
- trust split: well-formed SBML model AND objective within the steady-state LP assumptions → **TRUST the LP optimum as a feasibility/relative-growth screen**; an absolute in-vivo-growth claim or a kinetic/transient question → **defer**.
- conf→verdict: LP solve `status` (optimal/infeasible) is the state; `optimal` → trust-eligible (filter-relative).
- QoI + key: `growth_rate` / objective flux scalar · `fixed_summary {quantity:"growth_rate"}`.
- C1 KNOWN GAP: FBA gives a feasible steady-state OPTIMUM, not measured growth — no regulation/kinetics; media & objective assumptions uncheckable.
- card cost: ms-s LP, deterministic, pip. **T1.**

### T2 — local CLI, deterministic (REAL battery, second)

**4. `autodock_vina`** — class **filter**
- regime: dock a flexible ligand into a RIGID receptor pocket within a defined search box, empirical scoring function; seedable. NEW shape `rigid_pocket_dock`.
- trust split: ligand+box within the scoring function's applicability AND score used as a RELATIVE screen → **TRUST as filter**; rigid-receptor assumption violated (induced fit) or an absolute-ΔG claim → **defer**.
- conf→verdict: score + top-pose RMSD spread; filter-class → relative-only, never absolute.
- QoI + key: `docking_score` (kcal/mol) · `fixed_summary {quantity:"docking_score"}`.
- C1 KNOWN GAP: rigid receptor + empirical scoring — no induced fit, no explicit water/entropy; score ≠ true affinity.
- card cost: s–min, seed-fixed deterministic, pip/conda. **T2.**

**5. `crispr_guide_scoring`** (CRISPOR/CHOPCHOP, `backend` field) — class **filter**
- regime: on-/off-target efficiency scoring of a guide against a target site via published models (Doench-2016, CFD, MIT); deterministic scoring, not measured editing. Shape `named_quantity` (scores).
- trust split: guide+PAM+genome covered by the scoring model AND score used as a relative rank → **TRUST as filter**; species/PAM/context outside the model's training → **defer**.
- conf→verdict: model score (0–1); filter-relative.
- QoI + key: `activity_score` scalar · `fixed_summary {quantity:"activity_score"}` + `backend` field.
- C1 KNOWN GAP: predicts RELATIVE efficiency, not measured cutting/editing in the actual cellular context (chromatin/delivery uncheckable).
- card cost: fast deterministic scoring functions, local. **T2.**

**6. `blast`** — class **answer/filter**
- regime: local sequence-similarity search vs a database with Karlin-Altschul e-value statistics; deterministic given DB+params. NEW shape `homology_search`.
- trust split: query+DB within BLAST's substitution/gap model AND e-value below a stated threshold → **TRUST as significance filter**; a remote-homology claim BLAST can't detect or an absolute-homology assertion → **defer**.
- conf→verdict: e-value/bit-score → filter-relative (significance).
- QoI + key: `e_value` (min over hits) · `named_quantity {kind:"evalue", target:"<query-vs-db>", reduction:"min"}`.
- C1 KNOWN GAP: e-value is statistical significance of SIMILARITY, not homology/function; low-complexity & composition bias uncheckable.
- card cost: s–min (DB size), deterministic, local (NCBI BLAST+ CLI). **T2.**

**7. `hmmer`** — class **answer/filter** — *Step-41 near-neighbour of `blast`*
- regime: profile-HMM search (remote homology) vs a sequence DB, its own e-value/bit-score statistics; deterministic. Shape `homology_search` (profile variant — the L1a discriminator vs `blast`).
- trust split: profile/query+DB within the HMM AND e-value/bit-score below threshold → **TRUST as filter**; a claim beyond the profile's coverage → **defer**.
- conf→verdict: e-value/bit-score → filter-relative.
- QoI + key: `e_value` · `named_quantity {kind:"evalue", target:"<query-vs-db>", reduction:"min"}`.
- C1 KNOWN GAP: same significance-vs-function gap; profile-quality dependence.
- card cost: s–min, deterministic, local (HMMER CLI). **T2.**

**8. `mafft`** — class **filter/answer**
- regime: multiple sequence ALIGNMENT (progressive/iterative) — produces an alignment; heuristic optimum. NEW shape `msa_alignment`.
- trust split: sequence set within MAFFT's heuristics AND an alignment-quality metric used descriptively → **TRUST the alignment as computed**; a claim of biological/structural correctness → **defer**.
- conf→verdict: alignment score → descriptive/filter.
- QoI + key: `alignment_identity` (%id / SP-score) · `fixed_summary {quantity:"alignment_identity"}`.
- C1 KNOWN GAP: a computed alignment is a heuristic optimum, not the biologically/structurally TRUE alignment (guide-tree dependent).
- card cost: s–min, deterministic, local (MAFFT CLI). **T2.**

### T3 — provisioned (real battery; GPU / large weights / heavy DB — after T1/T2)

**9. `boltz2`** — class **filter**
- regime: neural structure + binding-affinity prediction from sequence(+ligand) WITHIN the training distribution; a predictor. Shape `fixed_summary`.
- trust split: target within the training distribution AND predicted RMSD/affinity used as a RELATIVE screen → **TRUST as filter**; OOD target or absolute-value claim → **defer**.
- conf→verdict: model confidence (ipTM/pLDDT-like); filter-relative, never absolute.
- QoI + key: `affinity` or `rmsd` scalar · `fixed_summary {quantity:"affinity"|"rmsd"}`.
- C1 KNOWN GAP: predicted affinity ≠ experimental Kd; OOD generalization & absolute-calibration uncheckable.
- card cost: GPU, large weights, s–min/inference. **T3 (provisioned).**

**10. `proteinmpnn`** — class **filter**
- regime: inverse-folding sequence design for a fixed backbone, neural, within training distribution; a design proposer. Shape `fixed_summary`.
- trust split: backbone within the training distribution AND sequence-recovery/score used as a relative design screen → **TRUST as filter**; a claim the sequence WILL fold/function → **defer**.
- conf→verdict: score/perplexity; filter-relative.
- QoI + key: `seq_recovery` scalar · `fixed_summary {quantity:"seq_recovery"}`.
- C1 KNOWN GAP: high recovery / low perplexity ≠ the sequence folds or functions; wet-lab uncheckable.
- card cost: GPU/weights, s/inference. **T3 (provisioned).**

**11. `retrosynthesis`** (AiZynth/ASKCOS, `backend` field) — class **filter**
- regime: retrosynthetic route search (MCTS/template) to purchasable building blocks within a reaction-template/stock library; a route proposer. Shape `fixed_summary`.
- trust split: target within the template library's chemistry AND a synthesizability/route-found flag used as a relative screen → **TRUST as filter**; a claim the route WILL work in the lab, or chemistry outside the templates → **defer**.
- conf→verdict: route score / solved-flag; filter-relative.
- QoI + key: `synthesizability` scalar · `fixed_summary {quantity:"synthesizability"}` + `backend` field.
- C1 KNOWN GAP: a found route is TEMPLATE-feasible, not experimentally validated (yields/conditions/selectivity uncheckable).
- card cost: heavy (models + reaction DB), s–min. **T3 (provisioned).**

### T4 — network-API lookup class (battery-DEFERRED — flagged deferred)

**12. `alphafold_db`** — class **lookup**
- regime: retrieval of a PRECOMPUTED AlphaFold structure + pLDDT for a UniProt id (a lookup, not a prediction run); network reliability surface; never trusted alone. Shape `fixed_summary` / lookup.
- trust split: id present in AFDB with a returned pLDDT → **report the number BUT never trust alone (corroboration required)**; missing id or low-pLDDT region → **defer**.
- conf→verdict: pLDDT IS the confidence; lookup class → structurally never-trust-alone (web_search-style maturity).
- QoI + key: `mean_pLDDT` (0–100) · `fixed_summary {quantity:"mean_pLDDT"}`.
- C1 KNOWN GAP: pLDDT is model SELF-confidence, not experimental accuracy; disordered/low-pLDDT regions & model-vs-reality gap uncheckable.
- card cost: network round-trip (s), no compute. **T4 (battery-deferred — network).**

**13. `bio_db_lookup`** (PDB/PubChem/UniProt/ChEMBL, `database` field) — class **lookup**
- regime: authoritative remote DB record retrieval by id/query, per-database namespace; network reliability surface; never trusted alone. Shape `named_quantity` (record field).
- trust split: id resolvable AND a well-formed record returned → **report round-trip success BUT corroboration-required (never sole basis)**; network failure / ambiguous / missing → **defer/setup_error**.
- conf→verdict: lookup class → structurally never-trust-alone.
- QoI + key: round-trip id / a named record field · `named_quantity {kind:"record_field", target:"<db>:<id>", reduction:"value"}` + `database` field.
- C1 KNOWN GAP: the DB's own curation currency/correctness is unverifiable from inside — a stale/erroneous record looks identical to a good one.
- card cost: network round-trip (s), rate-limit surface. **T4 (battery-deferred — network).**

---

## PART C — tool tiering (all enroll `calibrating` / `routable=False`)

**NEVER a stub battery. Deferred = flagged deferred, not faked.**

| Tier | What it means | Substrates |
|---|---|---|
| **T1 — real battery, FIRST** | local, pip/conda, fully deterministic — cheapest to calibrate honestly | `rdkit`, `cobrapy`, `cas_offinder` |
| **T2 — real battery, local CLI** | locally installable command-line, deterministic (Vina seed-fixed) | `autodock_vina`, `crispr_guide_scoring`, `blast`, `hmmer`, `mafft` |
| **T3 — provisioned** | REAL battery, but needs GPU / large weights / heavy reaction DB — scheduled after T1/T2, not deferred | `boltz2`, `proteinmpnn`, `retrosynthesis` |
| **T4 — battery-DEFERRED (network-API lookup)** | no physics envelope to batter; trust-split is CORROBORATION, not an envelope; validation is a round-trip + corroboration harness designed later. Flagged deferred, never stubbed. | `alphafold_db`, `bio_db_lookup` |

**Enrollment order proposed (calibration-cost-ascending):** T1 → T2 → T3, with
T4 enrolled (row + card) but its battery explicitly deferred. Real batteries this
wave: **8** (T1 3 + T2 5); provisioned: **3** (T3); deferred: **2** (T4).

---

## What the owner rules here (by exception)
1. **B split/bundle** — confirm the four decisions; in particular BLAST/HMMER
   **split (3)** vs bundle (2), and the three bundles (`bio_db_lookup`,
   `crispr_guide_scoring`, `retrosynthesis`).
2. **The real census** — 13 substrates / 13 cards / 8 real + 3 provisioned + 2
   deferred batteries (or 12 / 12 / 7+3+2 if BLAST+HMMER bundled).
3. **Any A cell** — every regime shape, trust-split, QoI key, and C1 gap is a
   proposal; correct any. New regime shapes proposed: `bounded_enumeration`,
   `fba_steady_state`, `rigid_pocket_dock`, `homology_search`, `msa_alignment`
   (plus reuse of `fixed_summary` / `named_quantity`).
4. **C tiering** — confirm T1 first three; confirm T3 provisioning vs deferral;
   confirm T4 network tools are battery-deferred (validation harness designed,
   not stubbed).

**After the ruling:** build each substrate per the packet's D.2 per-substrate
checklist (wrapper + seven dispatch surfaces + R-CARD-2 card + state-key
confidence + registry row, tests ADDED, staged to `onboarding/<substrate>/`),
serial merges, FAST-green each. Parallelize builds across worktrees; merge
serially. STOP here for the ruling — no wrapper is built.
