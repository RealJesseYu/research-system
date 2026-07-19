# D.4 PROMOTION — HANDOFF (resume from here in a FRESH session)

**Written 2026-07-19 at ~97% context to protect against dying mid-D.4. Main is
clean at this commit. A fresh session executes D.4 from this note.**

## State at handoff
- Main HEAD: `dbf41ec` (D.3 report + JSONs committed). Working tree clean.
- **12 bio substrate rows enrolled INERT** (Option A); registry 19 enrolled;
  **routable 5 / 0 mature** — nothing promoted yet.
- Era-of-record `6befb63` (D.1). repo_facts carries the "D.2 complete + D.3
  mid-flight, NOT re-stamped" note.

## D.3 result (the thing D.4 acts on)
The defer-fix WORKS on all 4 runnable tools (raw gate, N=3, per
`docs/waves/gate_reports/gate_D3_calibration.md` + the 4 committed JSONs):
- **In-envelope 0/60 defer** (57 trust + 3 refine); **out-of-envelope 60/60
  defer**; wrapper 5/5 each; ledgers fidelity=0/override=0 each.
- **CLEAN → promote:** `rdkit` 30/30, `mafft` 30/30.
- **SPLITS (refine, not defer) → owner N=7 re-runs pending:** `cobrapy` G02
  (29/30, 1 refine on iML1515), `homology_search` G03 (28/30, refine 2/3 on the
  HMMER profile case). If a re-run stays trust-dominant → promote; if refine
  PERSISTS → fix that case's CARD criterion (NOT the gate), recommit the slate,
  re-run. Do not promote a miscalibrated card.

## D.4 sequencing (owner-confirmed)
Stage **rdkit + mafft NOW** (definite), HELD not merged. Add **cobrapy +
homology_search** after their N=7 re-runs confirm. Then **ONE FAST-green D.4
merge** with the growing fixtures re-captured to the TRUE final routable set.

## THE DEPENDENCY (do not get this wrong)
The two growing fixtures re-capture EXACTLY `routable_ids()`:
- `tests/fixtures/d1/feasibility_nudge.txt` = `registry.routable_contracts_block()`
  over `routable_ids()` (the all-routable contract block; grows by each promoted
  substrate's contract, in enrollment order).
- `tests/fixtures/c235/chooser_retry_user_turn_v235.txt` = the routable-id list
  (grows to include the promoted ids).
So **do NOT stage a contract/fixture for a tool that ends up getting a card fix
instead of promoting.** Re-capture the fixtures to whatever is actually routable
at the merge. Preserve `*_preb1`/`*_preb2`-style originals append-only; the
re-capture is BLESSED additive growth (per the Option-A ruling), the era-of-record
ADVANCES at this merge (model-visible fixtures change).

## Promotion recipe PER SUBSTRATE (from onboarding/<sub>/d4_wiring_fragments.py)
For each promoting substrate (rdkit, mafft, then cobrapy, homology_search):
1. **Contract → substrates.py + registry `_CONTRACTS`.** Move the constant from
   `onboarding/<sub>/contract.py` into `substrates.py` (RDKIT_DESCRIPTOR_CONTRACT
   / MAFFT_CONTRACT / COBRAPY_FBA_CONTRACT / HOMOLOGY_SEARCH_CONTRACT), import it
   in `tools/substrate_registry.py`, add `_CONTRACTS["<sub>"] = <CONST>`.
   `contract_for("<sub>")` then RETURNS (stops raising).
2. **Signature → `tools/substrate_selection.py` `_SIGNATURES`.**
   `from tools.run_<x> import _REQUIRED_FIELDS`; `_SIGNATURES["<sub>"] =
   frozenset(_REQUIRED_FIELDS)`.
   - rdkit {smiles, quantity}; mafft {sequences, quantity}; cobrapy
     {model, quantity} (min_growth optional, NOT in _REQUIRED_FIELDS);
     homology_search {database, query, tool, quantity}. All pairwise DISJOINT
     from the existing 5 and from each other → no R-B-1 tie. (boltz2/alphafold_db
     share {protein_sequence,quantity} but are NOT promoting — irrelevant here.)
3. **Vocab + regime → `tools/qoi_vocab.py` `_VOCABS`.** New regime dataclasses,
   each `shape` = the regime name, `alien_keys = ("reynolds_min","reynolds_max",
   "analysis_type","operation")`:
   - rdkit: `DescriptorComputationRegime`; `FixedSummaryVocab(names=tuple(
     run_rdkit.QOI_FIELDS), regime=...)`.
   - mafft: `MsaAlignmentRegime`; `FixedSummaryVocab(names=tuple(
     run_mafft.QOI_FIELDS), ...)`.
   - cobrapy: `FbaSteadyStateRegime`; `FixedSummaryVocab(names=tuple(
     run_cobrapy.QOI_FIELDS), ...)`.
   - homology_search: `HomologySearchRegime`; `NamedQuantityVocab(kinds=("evalue",),
     target_re=<an identifier/any regex>, reductions=("min",), regime=...)`.
     (import QOI_FIELDS/_REQUIRED_FIELDS from the wrapper; single source.)
4. **Dispatch → `tools/substrate_dispatch.py`** (READ this file first — mirror the
   ngspice/cantilever wiring): adapter run_<x>(spec) -> {valid,qoi,diagnostics,
   runtime_s}; state-key SCALAR confidence (1.0 when valid, else 0.0; cobrapy's
   is the status gate, mafft's the input gate, homology_search's the DB-integrity
   gate, rdkit deterministic); QoI translation (fixed_summary `quantity` /
   named_quantity `kind,target,reduction` -> the wrapper's typed input); run-entry
   constructor {state, qoi_value|qoi_error, wall_clock_s}.
5. **Registry ROW flip:** `routable=False -> True` AND `maturity=CALIBRATING ->
   MATURE` TOGETHER (the first MATURE substrates — the auto-downgrade-to-defer
   lifts, so in-envelope trust verdicts finally STAND).
6. **Update enrollment/routable tests** (`tests/test_substrate_registry.py`
   routable-count/maturity assertions) and any `_CONTRACTS`-count / contractless-
   set tests (`tests/test_contract_registry.py` — the contractless set shrinks).

## PER-SUBSTRATE PROOF CHECKLIST (prove, don't assume) at each flip
- (a) **No new R-B-1 tie** via `select_substrate`: a spec with the substrate's
  params routes to exactly IT (now the unique routable server), and every other
  substrate's spec still routes unchanged; the shared-nothing signatures mean no
  tie — but PROVE by routing.
- (b) **Both growing fixtures re-capture ADDITIVE-ONLY** — diff shows only the new
  substrate's contract block / id added, nothing else changed (prove additive,
  like the D.1a non-anchor re-captures).
- (c) **Cavity byte-identical** — `tests/test_d0_stage5_input.py` green; frozen
  anchor untouched.
- (d) **ACCEPTANCE #6** — an in-envelope case on the now-MATURE substrate returns
  TRUST, not a forced defer: the maturity hook no longer downgrades (all-routable-
  mature? no — only these promote; the hook downgrades when ANY routable is
  non-mature, so with 5 old + N new, the OLD 5 are still non-mature → the hook
  STILL fires for them. #6 is about the PROMOTED substrate's own verdict standing;
  verify the hook's signoff set no longer names the promoted mature substrate, and
  a trust verdict routed to it is not force-downgraded on ITS account. Re-read the
  hook (supervisor.apply_substrate_maturity_hook) — it keys on the non-mature
  routable set; a mature substrate is excluded from the downgrade trigger).

## repo_facts §8 re-stamp AT THE D.4 MERGE
Routable 5 -> (5 + number promoted, up to 9); mature 0 -> (up to 4). Era-of-record
advances (`6befb63` -> the D.4 merge commit). Refresh §2 (routable/mature counts,
enrollment now 19), §8 (era + the growing-fixture re-capture), and re-stamp. This
is the ONE §8 re-stamp the D.2/D.3 notes deferred.

## Unchanged by D.4
The 8 DEFERRED tools (cas_offinder, autodock_vina, crispr_guide_scoring, boltz2,
proteinmpnn, retrosynthesis, alphafold_db, bio_db_lookup) stay inert
`calibrating`/`routable=False`, contract_for raises, each with its own recorded
un-defer requirement. D.4 does not touch them.

## FAST + suite discipline
FAST green gates the D.4 merge. Full suite green. Run venue: FAST/suite in-session
is fine; the calibration re-runs are the OWNER's plain-Terminal job. Build in a
worktree, merge serially, FAST-green.
