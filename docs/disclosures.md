# Disclosures

Dated, append-only record of corrections and disclosures. Committed text is
never rewritten; each entry here is a remedy that stands alongside the
original, not a replacement for it.

## R-20.5-2 (2026-07-14)

docs committed at 20.5 CLOSE and in commit 22c12c7 carry 2026-07-15 date
labels; the real date was Tuesday 2026-07-14. Committed text is never
rewritten; this note is the remedy.

## R-WIN-1 — new comparability era (2026-07-14)

The sanctioned prompt-touch window, moved from Thursday 2026-07-16 to now by
owner ruling R-WIN-1. This commit opens a NEW COMPARABILITY ERA: scored-battery
numbers produced BEFORE this commit are NOT comparable to numbers produced
after it, because the following model-visible surfaces changed.

Model-visible changes made in this window:
  - Tournament judge rubric (RANKING and DEBATE-JUDGE prompts): two new
    separately-toggleable criteria — IMPACT (if the hypothesis were true, who
    changes what they do?) and ALIGNMENT (does it answer what the domain
    actually asked?), env switches CRITERIA_IMPACT / CRITERIA_ALIGNMENT, both
    default 0 (off). With both off the judge prompts are byte-identical to the
    prior era's.
  - Reflection review family (full review): a matching IMPACT lens behind the
    same CRITERIA_IMPACT switch (default off), plus — UNCONDITIONAL — an
    INSTRUMENT CONTRACT block grounding the review in what the instrument can
    actually measure.
  - Gate-1 chooser: the same UNCONDITIONAL INSTRUMENT CONTRACT block (the h6
    fix — a hypothesis whose test needs out-of-contract measurement is now
    stated as a weaker bet).
  - CAVITY_2D_CONTRACT cost text: corrected to the measured truth — a per-step
    rate RANGE of 2.3-4.1 ms/step and wall-time that scales with Reynolds
    number (measured ~9.2-9.3 s baseline vs 161-175 s for Re 100-1600 sweeps,
    against the ~95 s a stale single-rate estimate predicted).
  - FEASIBILITY_NUDGE seam in Generation (env FEASIBILITY_NUDGE, default off):
    plumbing only; AUTO enabling is NOT wired this session (the supervisor is
    frozen today and it rides the retry-toggle build).
  - Memory-comparability pin re-taken over the live journal: EXPECTED_MEMORY_MD5
    073ff57e -> cf9bb3a2.

Era id: the single commit that lands this window (its hash is recorded in the
git log for this session; not embedded here, since a commit cannot contain its
own hash). All contract blocks IMPORT CAVITY_2D_CONTRACT — no pasted copy.

## 19-lite / retry follow-on (rides era f9dd2ca — no new era)

- FEASIBILITY_NUDGE seam coverage EXTENDED from the two steering strategies
  (literature_exploration, research_expansion) to ALL four prompt-composing
  Generation strategies — simulated_debate and assumptions_identification now
  carry the same switch and the same nudge block. This changes only the seam's
  COVERAGE, not the block text (still the imported CAVITY_2D_CONTRACT + recent
  failure memo + one instruction sentence), so it rides era f9dd2ca's existing
  FEASIBILITY_NUDGE disclosure and opens no new comparability era. With the
  switch off (default) all composed inputs remain byte-identical to era
  f9dd2ca's.

## R-MB-1 — era-of-record moves to this commit (Multi-QoI build, part B)

The model-visible surface changed this window, so the comparability era moves
to the single commit that lands it (its hash is in this session's git log; a
commit cannot embed its own hash). All contract blocks still IMPORT
CAVITY_2D_CONTRACT — no pasted copy anywhere.

Model-visible changes:
  - `CAVITY_2D_CONTRACT` §3 (extraction) — ADDED a `qois` bullet: a VECTOR of
    QoIs from one solved case, each a min | max | volAverage reduction over U
    or p (component mag or 0|1|2), each optionally carrying a deterministic
    spatial mask — corner_exclusion {radius_frac}, boundary_exclusion
    {distance_frac}, or box {x/y fractions} — with masked results reporting
    cells masked / total; and a COMPACT FIELD EXPORT (cell centres + volumes +
    final U, p) for offline analysis, summary-only across the wrapper boundary.
  - `CAVITY_2D_CONTRACT` §4 (honest limits) — AMENDED the "single-shot" bullet:
    the latest-time-only reduction now covers a single QoI OR a vector (masked
    or whole-domain) plus the field export; the whole-domain-only framing is
    gone (time-series / probes still absent). ADDED a masked-extremum honesty
    bullet: (i) a masked extremum MUST state its mask type and parameters in
    the spec; (ii) masked-extremum trends must be shown mask-insensitive before
    they are relied on — measured example: interior min(p) at Re 100 is −0.270
    at radius 0.05 vs −0.141 at radius 0.10.
  - `stages/stage2_spec.py` schema — ADDED optional additive fields, all
    present-only (control_block precedent), old on-disk specs validate
    unchanged: a `qois` list of qoi objects (each validated exactly like the
    single `qoi`) alongside the existing single `qoi`, and a per-qoi optional
    `mask` {type ∈ MASK_TYPES, params object}. No stage-2 prompt text changed;
    stage 2 meets this vocabulary only through the contract it already imports.

Comparability note: era `f9dd2ca` held ZERO scored data points (no scored run
landed under it), so the boundary moves cleanly to this commit — there is no
in-era scored data to straddle. Scored numbers taken before this commit are not
comparable to scored numbers taken after it; this commit is the new
era-of-record for anything the model-visible contract or spec schema touches.

## R5 — all-routable contract block at Stage-1 surfaces; era-of-record moves to this commit (2026-07-17)

Owner ruling R5 executes the D.1.1 direction's Stage-1 half. The comparability
era moves to the single commit that lands it (its hash is in this session's
git log; a commit cannot embed its own hash). Era-of-record leaves 862531b.

Model-visible changes (STAGE-1 surfaces only; the P8 stage-2 cavity pin and
every stage-2+ surface are untouched — proven by the zero-edit fixture
families):
  - P5 `stages/gate1_chooser.py` + P6 `stages/reflection_reviews.py`
    instrument-contract blocks and P7 `stages/generation_strategies.py`
    feasibility nudge now embed
    `tools/substrate_registry.routable_contracts_block()`: per routable
    substrate, a fixed `ROUTABLE SUBSTRATE: <substrate_id>` header then the
    imported contract VERBATIM, enrollment order — today
    cavity_2d_cfd then ngspice_linear_passive. Never a paraphrase, never a
    pasted copy; fail-loud inherits from `contract_for`.
  - Singular-instrument prose minimally edited where it became false:
    block header "INSTRUMENT CONTRACT (what the available instrument…)" →
    "INSTRUMENT CONTRACTS (what the available instruments…)"; instruction
    "outside this contract" → "outside every listed contract"; nudge
    instruction "Prefer hypotheses this instrument can test as-is." →
    "Prefer hypotheses at least one of these instruments can test as-is."
  - Fixture re-capture: tests/fixtures/d1/feasibility_nudge.txt (8,739 →
    19,861 bytes, both contracts present). The rwin1 fixtures pin BASE
    prompts and are byte-unchanged; the composed blocks are asserted live
    with grounding asserts extended to ngspice.

Comparability note: scored numbers taken before this commit are not
comparable to scored numbers taken after it for anything a Stage-1 composed
surface touches.
