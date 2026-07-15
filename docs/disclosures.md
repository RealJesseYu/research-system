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
