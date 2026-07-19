# Gate report — BIO Wave D.2 COMPLETE (all 12 bio substrates enrolled)

**2026-07-19, main HEAD `8688235`. All 12 bio substrate rows enrolled inert
(Option A), serial FAST-green merges, era holds, routable still 5/0 mature.**
Canonical committed copy.

## Headline
- **12 of 12 bio substrate rows enrolled** (total registry now 19 = 7
  pre-existing + 12 bio). **Routable still 5 / 0 mature — nothing promoted**
  (promotion is D.4).
- **Enrollment pattern = Option A throughout:** each substrate is a live
  registry row at `calibrating`/`routable=False`, INERT — runtime maps
  (`_CONTRACTS`/`_SIGNATURES`/`_VOCABS`/dispatch) STAGED in
  `onboarding/<substrate>/`, unwired; `contract_for(<sub>)` raises; invisible to
  `select_substrate`.
- **Final suite: 1356 passed / 1 skipped. FAST GREEN (exit 0) at every merge.**
  Cavity byte-identical throughout.

## The 12 — 4 real cards, 8 deferred, each for a DISTINCT reason
Real §3A cards (tool runs here, numbers from real runs):

| substrate | regime | did-it-work signal (proven by triggering) | QoI (real value) | pinned |
|---|---|---|---|---|
| `rdkit` | descriptor_computation | sanitizable SMILES + allowlist descriptor | MolWt 46.069, etc. | rdkit 2026.03.4 |
| `cobrapy` | fba_steady_state | **solver status gate** (infeasible→None, not stale objective) | growth 0.873922 / 0.876997 | cobra+GLPK, models baked |
| `homology_search` (BLAST+HMMER) | homology_search | **stderr integrity scan**; HMMER's TWO surfaces (profile+target) | e-value 4.36e-58 / 8.2e-61 | BLAST 2.16.0+, HMMER 3.4 |
| `mafft` | msa_alignment | **strict INPUT gate** (near-total fn — gate the input, not the output) | identity 94.4444 | MAFFT v7.526 |

Deferred (enroll-inert + input jails proven pure-Python + card skeleton
§3A-PENDING) — **each un-defer requirement is specific, never generic**:

| substrate | why deferred | specific un-defer requirement |
|---|---|---|
| `cas_offinder` | aarch64 pocl kernel computes silently wrong | a **validated environment** — the known-answer probe (built into the wrapper) must find a known-present site first |
| `autodock_vina` | no aarch64 build (won't install) | a **different architecture (x86 host)** + real §3A + fixed-seed determinism + convergence jail triggered |
| `crispr_guide_scoring` | no verified py3 Doench/CFD scorer (Azimuth is Py2) | a **verified py3 scorer/model from a trusted source** — hand-transcribing coefficients is FORBIDDEN (silent-wrong), part of the spec |
| `boltz2` | GPU + weights, no GPU here | **GPU host + PINNED official weights + a known-answer validation run** (mismatched weights = confident garbage) |
| `proteinmpnn` | GPU + weights, no GPU here | **GPU host + PINNED official weights + a known-answer run** |
| `retrosynthesis` | heavy models + a reaction route DB | **models + the reaction ROUTE DATABASE/backend** ("GPU + weights" undercounts the data dependency) + a known-answer run |
| `alphafold_db` | network (endpoint unreachable) | **working network + the AFDB endpoint reachable**; A3 never-trust-alone is PERMANENT |
| `bio_db_lookup` | 4-API network | **ALL FOUR endpoints reachable — one down = PARTIAL defer**; never-trust-alone PERMANENT |

Every deferred wrapper: a valid input returns the honest DEFERRED state, **never
a fabricated number**. Three env-blocked tools were each STOPPED-and-surfaced
with disk evidence before the owner ruled the re-tier.

## Option-A checks (held at every one of the 12 merges)
Inert row at `calibrating`/`routable=False` · `contract_for` raises · no new
R-B-1 tie via `select_substrate` (each signature spec loud-stops; the invisible
inert rows are never candidates) · enrollment-count test bumped · routable 5/0 ·
cavity byte-identical · FAST green · input jails proven by triggering · real §3A
(4 tools) or §3A-PENDING + un-defer requirement (8 tools).

## Held-open (unchanged, correctly)
- **Step-41 L1a live proof:** `boltz2` and `alphafold_db` share the
  `{protein_sequence, quantity}` signature BY DESIGN with DISTINCT regimes
  (structure_affinity_prediction vs predicted_structure_lookup) — the L1a
  discriminating pair. It fires only when both are routable (**D.4**), not D.2.
- **Acceptance #6 (in-envelope trust on a MATURE substrate):** proves at the
  first D.4 promotion.

## Where the packet was wrong (per the report rule — not empty)
- The packet priced **11** substrates; the real census is **12** (the BLAST+HMMER
  bundle is one substrate `homology_search`; MAFFT split out).
- The packet put `cas_offinder`, `autodock_vina`, `crispr_guide_scoring` in the
  real-battery tiers; on this host they can't produce real numbers (aarch64
  kernel / no aarch64 build / no verified py3 scorer) — re-tiered DEFERRED.
- So the real-battery set for D.3 is **4** (rdkit, cobrapy, homology_search,
  mafft), not the packet's larger T1/T2.

## Tasks (owner)
- [ ] Accept Gate D.2 (12 bio rows enrolled, 4 real + 8 deferred, routable 5/0,
      FAST green, suite 1356).
- [ ] **D.3 batteries** — the real-battery set is **rdkit, cobrapy,
      homology_search, mafft** (the 4 that run here); the 8 deferred get NO
      battery until un-deferred (never a stub battery). Confirm the manifest +
      the owner-OK'd serial night.
- [ ] Note: `docs/repo_facts.md` §2 (routable/enrolled counts) is now 19 enrolled
      / 5 routable — a §8-standing refresh is due at the D.2 close if you want it
      re-stamped now, or fold it into D.3.
