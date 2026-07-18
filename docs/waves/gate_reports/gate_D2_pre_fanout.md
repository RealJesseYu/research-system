# Gate report — BIO Wave D.2 pre-fan-out (B/C resolved, A for owner ruling)

**Status: A table HELD for owner ruling. No wrapper built. Era `6befb63`.**
Build chat, 2026-07-18. Canonical, committed copy (the pasted chat version
truncates). Future gate reports live in this directory.

Prior context recap: D.1 closed (era advanced `a07f939` → `6befb63`; repo_facts
refreshed at `b2b62fd`; L2 loud-stop-only recorded; packet tracked at
`docs/waves/BIO_WAVE_BUILD_PACKET.md`). Suite 1219 collected (1201 + 18).

---

## B result — BLAST vs HMMER: **BUNDLE → census is 12**

**Disk evidence:** BLAST and HMMER have **nothing on disk** — no `tools/run_blast.py`
/ `tools/run_hmmer.py`, no `onboarding/blast|hmmer/`, zero references in `tools/`
or `stages/` (grep empty). Both are entirely unbuilt, so the strict "differ on
disk" test cannot be met by construction, and there is no pinned signature /
regime shape / QoI vocab for either to differ on.

**On the merits (how they would wire):** in their overlapping and primary use —
*search a sequence database for homologs of a query and report an e-value* — they
collide on all three routing axes:
- **signature:** both `{query_sequence, database}`;
- **regime shape:** both `homology_search` (sequence-DB significance search);
- **QoI vocab:** both the e-value `named_quantity` (`kind:"evalue"`, `reduction:"min"`).

A homology-search spec would therefore serve BOTH and **L2-loud-stop forever** —
exactly the "two substrates that always co-tie is worse than one" case. → **BUNDLE**
into one `homology_search` wrapper with `tool ∈ {blast, hmmer}` (+ program/mode)
as a typed backend field, same pattern as the approved `crispr_guide_scoring` /
`retrosynthesis` bundles.

**Honest note on the hoped-for payoff:** their only *principled* hard distinguisher
is the INPUT — HMMER's flagship mode searches with a PROFILE/HMM, BLAST with a raw
sequence — which is an **L0/signature** distinction (different signatures →
resolves at serve-ability), **not L1a**. So a split would prove L0 (already proven
live by the cantilever `element_degree` case), **not** L1a's discriminating half.
Bundling loses no L1a proof. **L1a's live discriminating proof therefore moves to
the first genuine same-signature / different-regime-shape pair** — candidate
`alphafold_db` vs `boltz2` (both `{protein_sequence}`, lookup-regime vs
predictor-regime), which cannot fire until those are provisioned out of T3/T4.
Recorded as an updated hold-open (was "first bio near-neighbour", now "first
same-signature/different-regime pair, likely post-provisioning").

**Final census: 12 substrates / 12 cards.** (7 singletons + `bio_db_lookup` +
`crispr_guide_scoring` + `retrosynthesis` + `homology_search` + `mafft`.)

**bio_db_lookup pricing (owner-noted): 1 card, but a 4-API wrapper.** Its card and
(deferred) battery are single, but the WRAPPER spans four distinct services
(PDB / PubChem / UniProt / ChEMBL), each its own id namespace, query grammar,
error surface, and rate-limit behaviour, all behind the `database` typed field.
Price it as **the most expensive single wrapper in the wave** — its build ≈ four
API integrations, and each of its seven dispatch surfaces must handle all four
`database` values. Card/battery cost stays 1 (and the battery is deferred, T4).

## C result — tiers confirmed; T3's third member named

Bindings acknowledged: (1) ALL 12 get wrapper + 7 dispatch surfaces + R-CARD-2
card + enrollment at `calibrating`/`routable=False` in D.2 — batteries are the
subset. (2) Real batteries only for runnable tools; provisioned tools get real
batteries ONCE provisioned; deferred lookups get NONE (never-trusted-alone, no
envelope — web_search precedent). (3) NEVER a stub battery; deferred stays flagged
deferred. (4) Nothing in T3/T4 is promoted in D.4 without a REAL passing battery.

**T3's third member = `retrosynthesis`** (AiZynth/ASKCOS). Provisioned because
AiZynth needs downloadable expansion-policy models + a stock/template DB and
ASKCOS is a heavy service; it gets a REAL battery once provisioned, never a stub.

| Tier | Substrates | Battery |
|---|---|---|
| **T1 — real, FIRST (local pip, deterministic)** | `rdkit`, `cobrapy`, `cas_offinder` | real, 3 |
| **T2 — real (local CLI, deterministic)** | `autodock_vina`, `crispr_guide_scoring`, `homology_search`, `mafft` | real, 4 |
| **T3 — provisioned (GPU / weights / heavy DB)** | `boltz2`, `proteinmpnn`, `retrosynthesis` | real once provisioned, 3 |
| **T4 — battery-DEFERRED (network-API lookup, no envelope)** | `alphafold_db`, `bio_db_lookup` | none — flagged deferred, 2 |

**Batteries this wave: 7 real (T1 3 + T2 4) + 3 provisioned-later + 2 deferred.**

---

## A — the full 12-row §4b checklist (HELD for owner ruling)

The 5 regime-shape NAMES are pre-approved (`bounded_enumeration`,
`fba_steady_state`, `rigid_pocket_dock`, `homology_search`, `msa_alignment`; plus
reuse of `fixed_summary` / `named_quantity`). **The trust-splits and the C1-hole
KNOWN-GAP cells are what need owner eyes** — a vague C1-hole is the #2 named
failure (a card that defers on in-envelope cases). Rule by exception.

| # | substrate | regime shape | class | inside → TRUST split (C4 spine, both sides) | conf → verdict | QoI + spec key | C1-hole KNOWN GAP (gate CANNOT check) | card cost · tier |
|---|---|---|---|---|---|---|---|---|
| 1 | `cas_offinder` | `bounded_enumeration` | answer | pattern+genome indexed **AND** request within the declared mismatch+bulge budget → **TRUST** the count; unindexed genome or over-budget → **defer/setup_error** | deterministic; `state=valid` enumeration → trust-eligible (no probabilistic confidence) | `off_target_count` (int) · `fixed_summary{quantity:"off_target_count"}` | counts SEQUENCE matches only — **not FUNCTIONAL off-targets**; chromatin accessibility & actual cutting efficiency unmodeled | fast, deterministic, scales w/ genome (s–min), local, GPU-optional · **T1** |
| 2 | `rdkit` | `descriptor_set` (fixed_summary) | answer | molecule sanitizes under RDKit's valence model **AND** the descriptor is analytically computed → **TRUST**; unsanitizable molecule or an ML-PREDICTED property → **defer** | deterministic; `state=valid` parse+sanitize → trust-eligible | named descriptor scalar · `fixed_summary{quantity:"<descriptor>"}` | descriptors are COMPUTED PROXIES, not measured properties (computed logP ≠ experimental Kow) | ms-fast, deterministic, pip · **T1** |
| 3 | `cobrapy` | `fba_steady_state` | filter | well-formed SBML **AND** objective within the steady-state LP assumptions → **TRUST** the LP optimum as a feasibility/relative-growth screen; absolute in-vivo growth or a kinetic/transient question → **defer** | LP `status=optimal` → trust-eligible (filter-relative); `infeasible` → defer | `growth_rate` / objective flux · `fixed_summary{quantity:"growth_rate"}` | FBA gives a feasible steady-state OPTIMUM, **not measured growth** — no regulation/kinetics; media & objective choice uncheckable | ms–s LP, deterministic, pip · **T1** |
| 4 | `autodock_vina` | `rigid_pocket_dock` | filter | ligand+box within the scoring-fn applicability **AND** score used as a RELATIVE screen → **TRUST as filter**; rigid-receptor assumption violated (induced fit) or an absolute-ΔG claim → **defer** | score + top-pose RMSD spread; filter-relative, never absolute | `docking_score` (kcal/mol) · `fixed_summary{quantity:"docking_score"}` | rigid receptor + empirical scoring — **no induced fit, no explicit water/entropy**; score ≠ true binding affinity | s–min, seed-fixed deterministic, pip/conda · **T2** |
| 5 | `crispr_guide_scoring` (CRISPOR/CHOPCHOP, `backend` field) | `named_quantity` (scores) | filter | guide+PAM+genome covered by the scoring model **AND** score used as a relative rank → **TRUST as filter**; species/PAM/context outside the model's training → **defer** | model score 0–1; filter-relative | `activity_score` · `fixed_summary{quantity:"activity_score"}` + `backend` | predicts RELATIVE efficiency, **not measured cutting/editing** in the actual cellular context (chromatin/delivery uncheckable) | fast deterministic scoring, local · **T2** |
| 6 | `homology_search` (BLAST+HMMER, `tool` field) | `homology_search` | answer/filter | query+DB within the tool's model **AND** e-value below the stated threshold → **TRUST as a significance filter**; remote homology the tool can't detect or an absolute-homology assertion → **defer** | e-value / bit-score; filter-relative (significance) | `e_value` (min over hits) · `named_quantity{kind:"evalue", target:"<query-vs-db>", reduction:"min"}` + `tool` | e-value is statistical significance of SIMILARITY, **not homology/function**; low-complexity & composition bias, matrix/profile choice uncheckable | s–min (DB size), deterministic, local CLI · **T2** |
| 7 | `mafft` | `msa_alignment` | filter/answer | sequence set within MAFFT's heuristics **AND** an alignment-quality metric used DESCRIPTIVELY → **TRUST** the alignment as computed; a claim of biological/structural correctness → **defer** | alignment score; descriptive/filter | `alignment_identity` (%id / SP-score) · `fixed_summary{quantity:"alignment_identity"}` | a computed alignment is a HEURISTIC optimum, **not the biologically/structurally true alignment** (guide-tree dependent) | s–min, deterministic, local CLI · **T2** |
| 8 | `boltz2` | `fixed_summary` (neural predict) | filter | target within the training distribution **AND** predicted RMSD/affinity used as a RELATIVE screen → **TRUST as filter**; OOD target or an absolute-value claim → **defer** | model confidence (ipTM / pLDDT-like); filter-relative, never absolute | `affinity` \| `rmsd` · `fixed_summary{quantity:"affinity"\|"rmsd"}` | predicted affinity ≠ experimental Kd; **OOD generalization & absolute calibration uncheckable** | GPU, large weights, s–min/inference · **T3 (provisioned)** |
| 9 | `proteinmpnn` | `fixed_summary` (neural design) | filter | backbone within the training distribution **AND** seq-recovery/score used as a relative design screen → **TRUST as filter**; a claim the sequence WILL fold/function → **defer** | score / perplexity; filter-relative | `seq_recovery` · `fixed_summary{quantity:"seq_recovery"}` | high recovery / low perplexity **≠ the sequence folds or functions**; wet-lab validation uncheckable | GPU/weights, s/inference · **T3 (provisioned)** |
| 10 | `retrosynthesis` (AiZynth/ASKCOS, `backend` field) | `fixed_summary` (route search) | filter | target within the template-library chemistry **AND** synthesizability/route-found used as a relative screen → **TRUST as filter**; a claim the route WILL work in the lab, or chemistry outside the templates → **defer** | route score / solved-flag; filter-relative | `synthesizability` · `fixed_summary{quantity:"synthesizability"}` + `backend` | a found route is TEMPLATE-feasible, **not experimentally validated** (yields/conditions/selectivity uncheckable) | heavy (models + reaction DB), s–min · **T3 (provisioned)** |
| 11 | `alphafold_db` | `fixed_summary` / lookup | lookup | id present in AFDB with a returned pLDDT → **report the number BUT never trust alone (corroboration required)**; missing id or low-pLDDT region → **defer** | pLDDT IS the confidence; lookup class → structurally NEVER-trust-alone (web_search maturity) | `mean_pLDDT` (0–100) · `fixed_summary{quantity:"mean_pLDDT"}` | pLDDT is model SELF-confidence, **not experimental accuracy**; disordered / low-pLDDT regions & the model-vs-reality gap uncheckable | network round-trip (s), no compute · **T4 (battery-deferred)** |
| 12 | `bio_db_lookup` (PDB/PubChem/UniProt/ChEMBL, `database` field) | `named_quantity` (record field) / lookup | lookup | id resolvable **AND** a well-formed record returned → **report round-trip success BUT corroboration-required (never the sole basis)**; network failure / ambiguous / missing → **defer/setup_error** | lookup class → structurally NEVER-trust-alone | round-trip id / a named record field · `named_quantity{kind:"record_field", target:"<db>:<id>", reduction:"value"}` + `database` | the DB's own curation currency/correctness is unverifiable from inside — **a stale/erroneous record looks identical to a good one** | network round-trip (s), 4-API wrapper, rate-limit surface · **T4 (battery-deferred)** |

---

## What the owner rules here (then fan-out go)
1. **A table** — correct any trust-split or C1-hole cell (highest leverage); the 5
   new regime-shape names are pre-approved.
2. Confirm the **12** census and the **`homology_search` bundle**.
3. Confirm **T3 = {boltz2, proteinmpnn, retrosynthesis}** and the deferred T4.

**After the A ruling:** build each of the 12 per the packet's per-substrate
checklist (wrapper + 7 dispatch surfaces + R-CARD-2 card + state-key confidence +
registry row at `calibrating`/`routable=False`, tests ADDED, staged to
`onboarding/<substrate>/`); parallel worktrees, serial FAST-green merges;
batteries per the tier table. **STOPPING for the A ruling — no wrapper built.**
