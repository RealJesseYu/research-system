# Is the promise triage calibrated? — a report, not a retune

Asked as addendum item 9 alongside the pool-delivery fix. **Every number below was
re-derived from `runs/study-20260730T034915Z-cap2/stage1/reflection_reviews.json`,
`generation.json`, `survivors.json` and `tournament_state.json`.** Nothing here
changes a threshold: the mechanism is `_max_deep_review()` (default 6,
`stages/reflection_reviews.py:1201`) and the sort at `:1290`, and both are left
exactly as they were.

## What the triage did on arm C

| stage | count |
|---|---|
| generated | 33 |
| initial review `pass` | **30** |
| initial review `discard` | 3 |
| deep-reviewed (top `_max_deep_review()` by promise) | 6 |
| held back, never deep-reviewed, all `pass` | **24** |
| survived deep review | 5 |
| survived the filter (`MAX_SURVIVORS = 4`) | **1** |
| delivered to the director | 2 (that survivor + one Evolution variant of it) |

Promise distribution over the 30 passing candidates: `{5: 2, 4: 10, 3: 12, 2: 6}`.

## Finding 1 — the cut fell in the middle of a tie, and the tiebreak is generation order

Twelve candidates scored promise ≥ 4. Six slots. The sort is
`(-promise, index in the generation pool)`, so after the two promise-5 candidates
(h28, h29) the remaining four slots went to the **first four** promise-4 candidates
in pool order — h7, h9, h10, h11 — and the other six promise-4 candidates — **h12,
h15, h16, h18, h30, h31** — were held back with an identical score.

`h12` is the one the post-mortem identifies as the study:

> *"Refitting the AASHO Road Test axle-load equivalency relationship jointly with
> modern long-term pavement performance records will show that no single global
> damage exponent holds…"* — promise 4, verdict `pass`, screen reason: *"Testable
> refit with public long-term pavement records and a large policy prize; the
> universal-exponent mismatch is a well-specified mechanism."*

It lost its slot to nothing but its position in the generation pool. That is a
lottery, and it decided which hypothesis a $143.97 study pursued.

## Finding 2 — the promise score did not predict what deep review found

Of the six candidates the triage selected as most promising, deep review and the
full review returned:

| id | promise | quality | novelty | `answer_established` |
|---|---|---|---|---|
| h28 | 5 | — | — | discarded, fundamental flaw |
| h29 | 5 | 2 | known | **true** |
| h7 | 4 | 3 | novel | false |
| h9 | 4 | 2 | known | **true** |
| h10 | 4 | 2 | known | **true** |
| h11 | 4 | 2 | known | **true** |

Five of six were either fatally flawed or already answered. The single candidate
that cleared the filter — h7 — is the one the director then reported as unusable
(it proposes a simulated population the goal forbids). So on this run the top-6
selection had a usable yield of **zero**, while six equally-scored candidates
including h12 were never examined. The promise number, produced by the no-tools
initial review, carries little discriminating power inside the pass band; the
grounded reviews that follow disagree with it more often than they confirm it.

## Finding 3 — `rescued_from_triage` could not fire, by construction

`rescued_from_triage` was 0. The path is reachable, but only in one shape: the
reserve is reviewed **only when the first batch leaves `reflections` empty**
(`stages/reflection_reviews.py:1398`, `if not reflections and triaged`). Five of
six survived deep review here, so the rescue was correctly skipped by its own
rule. It is a crash-avoidance backstop, not a breadth mechanism, and it was never
going to recover h12.

## What this does and does not justify

Delivering the pool (task 1, this commit) routes around all three findings without
touching a threshold: h12 and its screen reason now reach the director as
`status: "not_reviewed", promise: 4`, and the director decides. The screening keeps
screening; it stops being the last word.

Three retunes are *suggested by* this evidence and **none is applied here** —
each needs a ruling, and two of them cost money:

1. **Do not cut inside a tie band.** Deep-review everything at the highest promise
   level that fits, or break the tie explicitly (recorded random, or a second
   cheap discriminator) rather than by generation index. Cost: variable, bounded
   by the tie width.
2. **Raise `_max_deep_review()` when the pool is large.** 6 of 30 is 20%; the cap
   is a flat number that does not scale with the `pool_size` the director bought.
   Cost: four agentic review calls per extra candidate.
3. **Ask the initial review for a finer promise signal** — 10 of 30 candidates
   landing on the same integer is what forced the arbitrary tiebreak. Cost: free
   (a prompt change), but it changes a frozen screening prompt.

Recommendation, offered not taken: **(1) first**, because it is the one that
actually lost h12, and its cost is bounded. Measure whether the pool channel alone
is enough before buying (2).
