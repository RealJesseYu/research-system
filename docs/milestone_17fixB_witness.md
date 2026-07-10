# 17-fix-B — Witnessed kill-rate run (PASS)

Witnessed kill-rate run for **17-fix-B** (S2 zero-hit fix + keyed-free OpenAlex
hard-required novelty grounding, commit cfa767e, merged to main at **fc0c6b7**).
Launched **2026-07-10** from HEAD **234e309**, in a plain Terminal under
`caffeinate`, with `--repeats 2` (4 slots: same1/same2/alt1/alt2). Battery report
timestamp 2026-07-10T13:25:43Z; total wall time 12,627.4 s.

Evidence read from disk for this document: `harness/killrate_last_run.json`
(the battery's machine report) and `harness/witness_17fixB.log` (942 lines,
the full battery terminal log).

## Purpose

Witness-only, per the run-sizing rule: this run confirms **no regression** from
17-fix-B and confirms the fix of the **slot-loss failure mode** (17-fix-A lost
2 of 10 slots to arXiv-required grounding-transport failures). It is **NOT** a
re-measurement of kill-rate statistics — at --repeats 2 the k and kill-rate
numbers below are observations, not a new baseline.

## Per-slot results (from killrate_last_run.json)

| slot  | k | deep-verify kill rate | wall_s | memory_md5 | comparable | relaunches used | abort_reason |
|-------|---|----------------------|--------|------------|------------|-----------------|--------------|
| same1 | 2 | 0.444 (4/9)          | 3128.3 | 373c886b   | true       | 0               | none         |
| same2 | 1 | 0.500 (5/10)         | 3244.6 | 373c886b   | true       | 0               | none         |
| alt1  | 3 | 0.400 (4/10)         | 3442.1 | 373c886b   | true       | 0               | none         |
| alt2  | 2 | 0.333 (2/6)          | 2272.4 | 373c886b   | true       | 0               | none         |

("relaunches used" = attempts beyond the first; every slot's attempts list has
exactly one entry, all with `exception: null` and `abort_reason: null`.)

## Headline

**4/4 slots resolved with zero relaunches** (vs 8/10 comparable with arXiv-required
grounding in 17-fix-A — the slot-loss failure mode did not recur). All four slots
matched memory md5 **373c886b** (comparable). k band **{2,1} same / {3,2} alt** —
zero zero-survivor runs. Ranking fired on **all k≥2 slots** (same1: 1 pairwise
call; alt1: 3 calls; alt2: 1 call; same2's k=1 is trivially ranked, no call —
correct). Rejects **2/179 = 0.011** (one full-review re-ask, one
simulation-review re-ask, both recovered on attempt 2). Ledger activity **0/0**
(fidelity_entries=0, override_entries=0).

## S2 behavior (counted from witness_17fixB.log)

- **28** `semantic_scholar failed (recorded, proceeding)` lines — each after a
  bounded 429 retry cycle (130 individual "HTTP 429, waiting 20s before retry"
  lines across the run). Best-effort degradation worked exactly as designed:
  every failure was recorded and the run proceeded; **zero aborts** (no abort
  lines anywhere in the log; no slot carries an abort_reason).
- Of 39 retrieval rounds total: 28 ended `s2=error`, **10 ended `s2=0`** — the
  17-fix-B zero-hit fix reporting legitimate no-results as zero hits rather
  than an error, witnessed live — and 1 ended `s2=2` (an in-passing keyless S2
  success).
- No non-S2 source failed a single round (zero non-S2 "recorded, proceeding"
  lines). OpenAlex returned 0 hits on 14 of 39 rounds (hits on the rest);
  grounding never depended on S2.
- The dedicated **live S2 re-probe REMAINS OWED** (attempted 2026-07-10,
  transport-blocked). The single in-passing `s2=2` round above does not
  discharge it.

## VERDICT

**PASS as a witness.** No regression observed; the slot-loss failure mode is
fixed (4/4 vs 8/10). Remaining 17-fix-B debt: **live S2 re-probe only**.

## Clarification for the record

17-fix-A's journal phrase "Elo ranking FIRED" referred to the round-robin
pairwise ranking (the current Ranking implementation). Elo proper is Step 17-C
(tournament), not yet built.
