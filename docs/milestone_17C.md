# Step 17-C (Elo tournament) — CLOSED

Built at commit **5038c1e** ("17-C: Elo tournament (K=32, init 1200) with tiered
debate/single-turn matches, both-orderings draw rule, proximity-ordered
round-robin, dedup flags, tournament_state.json").
Witnessed **2026-07-10 → 2026-07-11**, `--repeats 2`, launched from 5038c1e,
plain Terminal under caffeinate (launch commit/environment are dictated
provenance — see Debrief asterisks). HARD STOP read recorded **2026-07-11**.
**Status: CLOSED.**

Evidence: `harness/killrate_last_run.json` (battery report,
timestamp_utc 2026-07-11T02:20:18Z), `harness/witness_17C.log` (1043 lines),
`runs/killrate-*/stage1/{tournament_state.json, ranking.json,
reflection_reviews.json}` for the four slot runs. Every number below was
re-derived from those files during this close.

## Witness (disk-derived)

Per-slot results (one attempt per slot — **zero relaunches** battery-wide;
`abort_reason` null everywhere):

| slot  | run_id                          | k | kill rate | wall_s  | memory_md5 | comparable | relaunches | abort_reason |
|-------|---------------------------------|---|-----------|---------|------------|------------|------------|--------------|
| same1 | killrate-20260710T224120Z-same1 | 3 | 0.333     | 2261.3  | 373c886b   | true       | 0          | none         |
| same2 | killrate-20260710T232201Z-same2 | 4 | 0.100     | 3522.2  | 373c886b   | true       | 0          | none         |
| alt1  | killrate-20260711T002344Z-alt1  | 3 | 0.333     | 3235.0  | 373c886b   | true       | 0          | none         |
| alt2  | killrate-20260711T012039Z-alt2  | 3 | 0.500     | 3579.1  | 373c886b   | true       | 0          | none         |

All four match the expected memory md5 (373c886b). Per-slot total calls
(model_call + web_search): 50 / 72 / 63 / 67.

**Totals:** 252 model calls (model_call 213 + web_search 39);
wall 13,137.7 s (3.65 h).

**The four new stage names** (expectation: 8/8/8/11 calls, 0 rejects — MET):

| stage                          | calls | rejects |
|--------------------------------|-------|---------|
| stage1_tournament_debate_turn1 | 8     | 0       |
| stage1_tournament_debate_turn2 | 8     | 0       |
| stage1_tournament_debate_turn3 | 8     | 0       |
| stage1_tournament_judge        | 11    | 0       |

(Consistency: 4 debates × 2 orderings = 8 per debate turn; 11 judge calls =
2+5+2+2 single-turn matches across the four runs.)

**Overall reject rate:** 6 rejects / 213 model_call calls = **0.028**, below
the ~0.04 baseline. All 6 rejects are pre-existing Reflection re-ask shapes
(full/simulation reviews replying with prose around the JSON); zero rejects in
any tournament stage.

**Ledger activity:** fidelity_entries 0 / override_entries 0 — **0/0**.

**Artifacts:** `ranking.json` is still written in its historical shape — a
JSON list of `{pair, ack_run_id, winner_id, reason}` records (verified
identical key-set in all four runs; record counts 4/7/4/4 — one record per
judge verdict, so a both-orderings debate contributes two).
`tournament_state.json` is present in **all four** runs. Every run this
battery had k≥3, so the k≥2 condition is satisfied by all of them; **no k=1
run exists this battery** to witness the absent-at-k=1 case.

## Mechanism verification (disk-derived)

**Tier logic — debates fire iff both participants are in the live top-2 at
match time.** Code-confirmed (`_live_top2`, stage1_ideation.py: top-2 by live
Elo, equal Elo broken by survivor-list order — the same J9 tiebreak as
final_ranking). Witnessed on alt2's three matches
(killrate-20260711T012039Z-alt2, witness log lines 1012/1027/1031):

1. `h1_vs_h7` tier=**single_turn** — all three survivors tied at 1200.0
   (init); h7 wins, h1 drops to 1184.0.
2. `h8_vs_h7` tier=**debate** — live top-2 is {h7: 1216.0, h8: 1200.0}
   (h1, at 1184.0 after its match-1 loss, has dropped out of debate
   eligibility); both participants top-2 → full both-orderings debate;
   h7 wins both orderings.
3. `h8_vs_h1` tier=**single_turn** — live top-2 is {h7: 1231.26, h8:
   1184.74}; h1 at 1184.0 sits rank 3, so the pair is not both-top-2 →
   single-turn. h1 wins.

**Elo arithmetic spot-check** (recomputed by hand, K=32): same2 match
`h2_vs_h10`, before {h2: 1200.736306793522, h10: 1184.0}, winner h2.
E(h2) = 1 / (1 + 10^((1184.0 − 1200.736306793522)/400)) = 0.5240668692075855;
h2' = 1200.736306793522 + 32 × (1 − 0.5240668692075855) =
**1215.9661669788793**; h10' = 1184.0 − 32 × 0.4759331307924145 =
**1168.7701398146428**. Both match the log and tournament_state.json to full
float precision. The draw update was also recomputed: same2 `h1_vs_h2` split
→ score 0.5 each → h1' = 1215.263693206478, h2' = 1200.736306793522 — exact
match to the logged values.

**The four both-orderings debates** (from the witness log; one per run):

| run   | pair     | orderings           | verdicts | outcome                          |
|-------|----------|---------------------|----------|----------------------------------|
| same1 | h2 vs h3 | [h3,h2] then [h2,h3] | h2, h2   | h2 wins (order-invariant)        |
| same2 | h1 vs h2 | [h1,h2] then [h2,h1] | h2, h1   | **SPLIT → draw** (0.5 each)      |
| alt1  | h3 vs h7 | [h3,h7] then [h7,h3] | h7, h7   | h7 wins (order-invariant)        |
| alt2  | h8 vs h7 | [h8,h7] then [h7,h8] | h7, h7   | h7 wins (order-invariant)        |

## HARD STOP READ (recorded 2026-07-11; strategist findings + human concurrence — dictated, disk-checkable claims verified)

**Q1 RANKING SENSIBLE — PASS.** Judge reasons do real scientific work and
visibly weigh addressable_notes as carried concerns. Two verified instances
from same2's tournament_state.json against the same run's
reflection_reviews.json:

(i) **h4's losses cite its unspecified metric and gradient-orientation
ambiguity — h4 addressable_notes #2–3, near-verbatim.** Judge reason,
`h1_vs_h4`: "…whereas h4's stratification claim hinges on **unspecified
metric, gradient orientation**, and monotonicity bounds that leave its core
mechanism ambiguous." Judge reason, `h2_vs_h4`: "…carries an **unresolved
gradient-orientation ambiguity** that undermines its mechanistic soundness…"
Against h4 note #2: "The **metric** for 'magnitude of circulation
modification' is **unspecified**…" and note #3: "The **spatial orientation of
the imposed temperature gradient** relative to the lid and gravity is left
implicit…" (h4's third loss, `h4_vs_h10`, cites the same pair: "unspecified
gradient orientation and metric choices"). VERIFIED.

(ii) **The h1-vs-h2 debate's ordering-2 verdict attacks h2's unverified
enstrophy-positivity prerequisite — h2 note #3.** Verdict reason: "…whereas
H2's headline non-monotonic optimum is entirely contingent on the
**unverified prerequisite that obstacle-induced enstrophy enhancement is ever
positive**." Against h2 note #3: "**Whether enstrophy enhancement is ever
positive (prerequisite for the non-monotonic maximum)** is precisely what the
experiment tests; it is an open empirical question, not a structural
contradiction." VERIFIED.

The 17-fix-A carried-notes promise is complete end-to-end: born in review,
carried in survivors, weighed at ranking.

Non-blocking observations:
- h1 vs h2 is a statistical near-tie — **0.79 Elo apart** (verified:
  1230.5612 − 1229.7698 = 0.7914) with **identical 2.5/3 match scores**
  (verified: h1 = win + draw + win; h2 = draw + win + win) — final_ranking
  presents false precision at near-ties.
- One judge reason narrated in positional labels ("**Hypothesis B** ties a
  measurable KE-fraction trend…", match `h4_vs_h10`) though the enum-pinned
  verdict was correct (winner_id h10, valid per the log's ACK line). VERIFIED.
- The J6 critique-withhold means the judge credited h2's configuration as
  "underexplored" (h1_vs_h2 ordering-1 verdict) while the withheld critique
  knew of adjacent prior work (h2's full_review critique: "R4 already targets
  this exact system (same geometry, same parameters), so the novelty claim is
  incremental…") — by design (novelty screening is Reflection's job).
  Recorded as a pattern for 17-E's meta-review to surface. VERIFIED.

**Q2 DEDUP — VACUOUSLY PASSED, deferred with teeth.** Zero dedup flags
battery-wide (verified: `dedup_flags: []` in all four tournament_state.json
files); exhibit max pairwise similarity **0.167** (verified in same2's state
file: h1_vs_h10 = 0.16702 — but see Debrief asterisk 1 on battery-wide
scope). Upstream deep-verify already kills near-duplicates pre-tournament;
dedup's real customer is 17-D's Evolution variants. **RULING: threshold stays
0.85; MANDATORY 17-D witness check — verify dedup fires on Evolution
variants; recalibrate against observed variant similarities if it does not.**

**Q3 POSITION BIAS — CONTROLLED.** 3 of 4 debates order-invariant — the
winner won from both presentation positions (verified in the debate table
above: h2 won from position 2 and position 1 in same1; h7 likewise in alt1
and alt2). The 1 split (same2, h1 vs h2) neutralized to a draw exactly as
designed — **the draw rule's first live firing**, on the pair the system
itself scores as a near-tie. **WATCH ITEM:** both split verdicts favored
position 2 (verified: ordering [h1,h2] → h2; ordering [h2,h1] → h1) —
possible last-word signature, n=1; track split-position patterns in future
runs.

## Cost note

Mean total calls/run = 252 / 4 = **63.0**; mean wall/run = 13,137.7 s / 4 =
3,284.4 s = **54.7 min**. The Step-18 descope trigger (>~75 calls or >~70
min) does **NOT** fire on these numbers. Formal ruling remains at 17-CLOSE.

## Carried forward

- **17-D witness (MANDATORY):** verify dedup fires on Evolution variants;
  recalibrate the 0.85 threshold against observed variant similarities if it
  does not.
- **For 17-CLOSE:** prompt-hygiene tweak (ids, not positional labels, in
  judge reasons); near-tie Elo visibility in the gate-1 demo (read from
  tournament_state.json — the payload schema stays untouched); log-tracking
  convention; tfidf/proximity param-sync; Step-18 formal re-price.
- **For 17-E:** the critique-withhold pattern (judge can credit novelty the
  withheld critique already qualifies).

No checksum snapshot here — that is 17-CLOSE's final-write, per plan.

## Debrief asterisks

1. **Battery-wide max pairwise similarity is 0.1971, not 0.167.** The
   dictated exhibit (0.167) is same2-local and verifies exactly there
   (h1_vs_h10 = 0.16702), but the dictation juxtaposes it with "zero flags
   battery-wide"; the battery-wide maximum is alt1's h3_vs_h1 = 0.19714.
   Both are far below the 0.85 threshold — the Q2 conclusion is unchanged.
2. **"Launched from 5038c1e, plain Terminal under caffeinate" is dictated
   provenance, not disk-provable.** Neither the battery JSON nor the witness
   log records a git hash or launch environment. It is consistent with disk
   (HEAD is 5038c1e with only the two untracked witness logs; the witness
   files' mtimes match the battery's end), but recorded here as dictated.
