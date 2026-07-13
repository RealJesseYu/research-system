# Milestone 17-E — Meta-review + feedback loop + research overview + iteration controller: WITNESSED PASS

Date: 2026-07-12 (doc-only close session; every number below re-derived from disk —
`harness/killrate_last_run.json`, `harness/witness_17E.log`, `runs/killrate-20260712T*`,
git. Where disk and strategist dictation disagreed, the DISK value is recorded and the
mismatch appears in the asterisk list at the end.)

## Build
- Built at commit `41fe473` (2026-07-12): meta-review (Opus pin `claude-opus-4-8`),
  per-family feedback blocks, per-round `research_overview.json`, review 6 active on
  Haiku pin (advisory), iteration controller (ROUNDS=2, canonical files = last
  successful round, `rounds.json` audit trail). 250/250 tests offline, FAST GREEN.
- 17-CLOSE build items at commit `c9b8837`: 263/263 tests, FAST GREEN hard-gate 3/3,
  ledger 0/0. (Landed AFTER the witness below ran — see asterisk 1.)

## Witness battery: `--mode killrate --repeats 2 --rounds 2`
Report `harness/killrate_last_run.json` (written 2026-07-12T13:36:31Z); run ids
`killrate-20260712T064050Z-same1`, `-090918Z-same2`, `-100725Z-alt1`, `-111203Z-alt2`.

**PASS: 4/4 slots resolved, zero relaunches (every slot's attempts list has exactly one
entry, exception null), memory md5 `373c886b` on 4/4 — all comparable.**

- k distribution: same {4, 4}, alt {4, 2}. Deep-verify kill rates 0.444/0.222 same,
  0.222/0.7 alt. **The 17-D-armed forensic trigger (any k=0 slot OR ≥2 slots at k≤1)
  did NOT fire.** The parent-pool watch stands down from alarm; same2's 17-D k=0 was
  not reproduced.

## The iteration loop, live
- **Loop live in same1 and alt2**: `rounds_completed=2`,
  `termination_reason=round_budget_exhausted` (both slots ran the full 2-round budget).
- **Count cap live in same2 and alt1**: `rounds_completed=1`,
  `termination_reason=survivor_count_cap` (dictation's "count_cap"; disk string is
  `survivor_count_cap`).
- k=1 trivial-marker state: live-unexercised (no round produced k=1; k was 4,4,4,2).

## Feedback blocks proven word-for-word in round-2 transcripts
Grep for the exact composed header `META-REVIEW FEEDBACK (<family>, entering round 2):`
against `runs/<id>/transcripts/`:
- same1: 7 generation / 37 reflection / 15 tournament-judge transcripts carry the block.
- alt2: 7 / 41 / 11.
- The Generation-only overview subsection header `RESEARCH-OVERVIEW DIRECTIONS (the
  prior round's synthesis):` appears in all 7 generation transcripts of each 2-round
  slot. All three families received their blocks; round 1 got the explicit empty block.

## Meta-review
- **6 calls, 0 rejects** (`stage_rejects.stage1_meta_review`: calls 6, rejects 0;
  exactly six `STAGE1_METAREVIEW` lines: same1 rounds 1+2, same2 r1, alt1 r1, alt2
  rounds 1+2). Feedback volumes per round: g/r/k 5–6 / 5–6 / 3–5, directions 2–4.
- **Max-turns transport events absorbed by bounded retry**: 2 meta-review calls hit the
  `Reached maximum number of turns (1)` transport error; TRANSPORT-RETRY fired 3 times
  total (one call needed retry=1; the other retry=1 then retry=2). All 6 calls landed
  attempts=1 after retry; the never-crash degradation path was never needed. (See
  asterisk 2 on the dictated count.)

## Review 6 (recurrent/tournament review)
- **19 calls, 0 rejects** (sum of `stage1_reflection_tournament_h*`: same1 round 2 = 9
  survivors, alt2 round 2 = 10).
- **Inert in every round 1**: four `STAGE1_REVIEW6 inert` lines, one per slot.
- **Advisory property held**: no discard in any slot is attributable to review 6; all
  kills came from initial review / deep verification, exactly as designed.

## Evolution
- **12 emitted / 6 accepted** (summed across `stage1/round*/evolution_variants.json`;
  per-round: same1 r1 2/1, same1 r2 2/2, same2 r1 2/1, alt1 r1 2/0, alt2 r1 2/0,
  alt2 r2 2/2). Reject reasons all honest: judged_known ×3, initial_review_discard ×2,
  fundamental_flaw ×1. Zero-accept tolerance fired twice (alt1 r1, alt2 r1) without
  crash: "zero variants accepted — proceeding over parents alone".
- **All four strategies live**: simplification 6 calls, out_of_box 2,
  grounding_enhancement 1 (with live OpenAlex retrieval, openalex=3), combination 3.
- **First variant debate win**: same2 match `h9_vs_ev2`, tier=debate, verdicts
  `['ev2','ev2']` — ev2 won from BOTH orderings (invariant under position swap).
- **First rank-1 variant delivery at the gate-1 boundary**: same2's delivered
  `hypotheses_ranked[0]` is ev2 at Elo 1260.29 (final ranking ev2 > h10 > h9 > h6 >
  h8). The battery does not exercise gate 1 itself; the first LIVE gate-1 variant
  selection came hours later in supervised Run B (see milestone_17CLOSE.md).

## Dedup — first run with live customers, zero flags
Variants entered tournament pools in four rounds (same1 r1: ev2; same1 r2: ev1+ev2;
same2 r1: ev2; alt2 r2: ev1+ev2), so the proximity matrix had variant pairs to judge
for the first time since 0.85 was ruled a near-verbatim detector.
- `dedup_flags: []` in all four slots' `tournament_state.json`.
- Highest proximity anywhere: **0.3409 for `h3_vs_ev1` in same1 round 2 — a
  parent-child pair (ev1 = simplification of h3) — correctly unflagged**, far below
  0.85 and consistent with the 17-D bands. Outcome (c) reinforced: tf-idf proximity
  does not separate siblings from distinct hypotheses, and the 0.85 near-verbatim
  detector stays as ruled. 0.85-with-flags remains live-unexercised.

## Position-2 watch (judge order sensitivity)
Debate-tier matches whose two orderings produced SPLIT verdicts, cumulative across
17-C and 17-E witness logs:
- 17-C `h1_vs_h2`: verdicts `['h2','h1']` — each verdict favored position 2.
- 17-E `h7_vs_h10` (alt1): `['h10','h7']` — both position 2.
- 17-E `h6_vs_h4` (alt2): `['h4','h6']` — both position 2.

**3 split matches, 6 verdicts, 6/6 favored the hypothesis in position 2.** (17-E alone
contributes 2 split matches / 4 verdicts; the other two 17-E debates were invariant.)
Single-turn matches are single-exposure by construction and cannot self-diagnose this.
This is the named motivation for the R-C3 judge id-hygiene prompt line (landed
`c9b8837`, after this witness).

## Cost
- Per slot: 173 / 80 / 75 / 168 calls (mean **124.0**); wall 8728.0 / 3307.2 / 3697.7 /
  8668.6 s (mean **101.7 min**). Battery total 496 calls (424 model_call + 72
  web_search).
- Per round (from the two 2-round slots): **≈85 calls / ≈72 min** (85.25, 72.5) —
  these are the figures now quoted by the dry-run cost lines.
- Reject rate **0.019** (8 rejects / 424 model_call calls, per the report's total row).
  Rejects: expansion 1, full-review 2, observation 2, simulation 1, tournament judge 2.

## Watches carried forward
1. **Position-2**: 6/6 is a pattern, not yet a scored result; single-turn tier's
   single-exposure blindness is named. Id-hygiene prompt line is in; watch whether
   splits persist under it.
2. **Round-2 kill hardening**: n=2 (only two slots ever ran a round 2); no conclusion
   drawn yet on whether reflection kills harden against feedback-informed candidates.
3. **Max-turns transport shape**: `Reached maximum number of turns (1)` recurred on
   Opus meta-review calls (and once each on a thought-layer and debate call in the
   supervised runs); bounded retry absorbs it, but the shape is recurring — watch.
4. **k=1 trivial-marker** and **0.85-with-flags**: both still live-unexercised.

## Asterisks (dictation vs disk)
1. **Launch HEAD 41fe473 is inferred, not report-recorded.** `launch_git_head` is
   absent from `killrate_last_run.json` — the field landed later that day in
   `c9b8837`. Corroboration: 41fe473 committed 2026-07-12T02:15 local; first slot
   launched 06:40:50Z (02:40 local); c9b8837 committed 15:36 local, after the report
   was written (13:36Z = 09:36 local). Nothing else was on main in that window.
2. Dictation said "2 max-turns transport events"; disk shows **3 TRANSPORT-RETRY
   firings across 2 affected meta-review calls**. Recorded as 2 events / 3 firings.
3. Dictation's "count_cap" is the disk string `survivor_count_cap`.
4. The battery slot records' `variants_emitted/accepted` fields are LAST-ROUND values
   (2/2, 2/1, 2/0, 2/2 emitted/accepted) because this report predates c9b8837's
   additive run-total fields; the 12/6 totals above are re-derived from the per-round
   `evolution_variants.json` files.
5. The "6/6 across 3 split matches" position-2 count is cumulative across the 17-C and
   17-E witness logs, not 17-E alone.
