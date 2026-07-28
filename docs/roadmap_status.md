# Roadmap status — the living list

**This file is the shared plan.** The coordinating ("brain") session owns it and
updates it as work lands. Anyone can read it; do not let it go stale.

Last verified against the repo: **2026-07-28** (evening), HEAD `538ef97`,
branch `iterate-experiment-loop` (no remote). Suite re-run in full: **2107
passed, 1 skipped, 63 subtests**, 155 s, exit 0. Item 1 landed and was verified
by running it, not by reading its tests — see "Item 1 result" below.

> **Do not trust the statuses below without checking.** Several sessions commit
> to this tree in parallel. Re-derive from `git log`, the test suite, and
> `studies/` before planning. The project's named trap is assert-without-looking.

---

## What this pass verified, and what it changed

Four findings from reading `studies/` and the cost/verification code. Three of
them move items on this list.

**1. Nothing has run live since the run-readiness fixes.** The newest study on
disk is `study-20260727T153408Z` (mtime 07-27 11:34). The three run-killer
commits landed 07-27 20:21 (`8898681`), 07-27 20:34 (`3f9cc7b`) and 07-28 05:00
(`dbb9469`). **Every one of those fixes is unexercised live.** One of them
(`dbb9469` item 1, ideation crashing when a whole review batch died while
never-reviewed candidates sat untouched) is a direct fix for the observed
`call_ideation_failed` in `study-20260727T045848Z`.

**2. Six of the last ten studies produced no report at all.** All died with 0–2
decisions and an empty `director_workspace/`, i.e. within about two minutes.
And `study-20260727T045848Z` burned **68 decider calls / 15,171,280 tokens for
zero experiments** before dying on three consecutive decider failures. It was
launched with **no `--token-budget`**, so nothing bounded the spend — the move
ceiling (20) is not a cost ceiling, and it barely moved. See Standing rules.

**3. The verification wall costs ZERO model tokens.** `stages/verification.py`
is deterministic Python with no model in the path (that is the purity rule); per
claim it starts a Docker container. So **"the glider study was ~90%
verification" cannot be a claim about token spend** — the tokens went to the
experimenter *authoring* the self-contained recompute artifacts the prompt
demands, and to serial container wall-clock. Which of those actually dominated
**has never been measured.** This is why item 1 now blocks item 2 rather than
merely preceding it.

**4. The cost numbers we do have are wrong in two specific ways.**
- `report.json.total_spend` at a study with children **under-counts the tree by
  ~3x**: the root's 18.9M for `study-20260726T185547Z` omits sub1's 10.3M and
  sub2's 25.5M, which live only in the child reports. True tree total 54.0M.
- `decider_spend` is a misnomer — it is the whole process delta, so
  `call_ideation` and in-process child directors are folded into it. One study
  shows **176 calls / 17.5M tokens** sitting inside a field named for the PI's
  own decisions.

Consequence: the roadmap's framing of item 1 as "small, it just takes
hand-analysis of `report.json`" was optimistic in one direction and pessimistic
in the other. `report.json` is not merely un-summarized, it is **incorrect at
the root**; but ~85% of the per-phase table can be produced today by pure
post-processing, because `arc.jsonl` already carries `cost {calls, tokens}` and
`at` per entry.

---

---

## Item 1 result — the measurement, and what it still cannot see

`pi_agent/cost_report.py` shipped in three commits (`9f19e20` report, `4d16ead`
capability instrumentation, `538ef97` the two wrong numbers). Verified by
RUNNING it, on the glider tree, the 0-move degenerate case, and a study with no
`arc.jsonl` at all (clean, exit 0). It reproduces the 54,013,618-token tree
total the root's own `report.json` under-counted as 18,919,715.

**The headline number — where a real study's tokens actually go:**

| phase kind | tokens | share |
|---|---|---|
| `spawn_sub_investigation` (children's runs) | 35,800,518 | 65.4% |
| `single` (this study's own runs) | 18,213,100 | 33.3% |
| process-side (director decisions + orchestration) | 706,615 | **1.3%** |

**98.7% of spend is inside experimenter runs.** Orchestration is a rounding
error. Two consequences:

- **"Streamline compute" at the director/phase level is not worth doing.** There
  is nothing there to win. Any real cost work is inside the experimenter.
- **The verification question is STILL unanswered, and this instrument cannot
  answer it.** Every one of those numbers is a single opaque experimenter call —
  one move recorded 10.46M tokens and logs nothing about its own composition.
  Whether that went to exploring, to authoring recompute artifacts, or to
  re-checking, is invisible. Item 2 remains blocked on evidence, and the
  evidence needs *intra-run* attribution, which is a separate instrument.

Two things the worker got right that the brief had wrong or omitted:
- `spawn_sub_investigation` is deliberately left UNMETERED: the child director
  runs in-process, so a meter diff there would double-count against the child's
  own recursive roll-up. The brief did not anticipate this.
- `total_spend` was NOT redefined — `liveview/reader.py:613` reads it as
  `spend_reported`. `tree_spend` was added as a new field instead, and
  `decider_spend` → `process_spend` keeps a backward-compatible read for old
  studies on disk.

---

## Phase 0 — done, and proven live

| | What | Evidence |
|---|---|---|
| ✅ | Free director: decomposes, spawns sub-investigations, recursion to depth 5, divisible budget | `study-20260726T063702Z`, `…185547Z` |
| ✅ | Carry bus — a phase hands its WORK to the next as re-runnable producers | control-law phase regenerated `glider_design.json` and verified it |
| ✅ | Integration check catches composition failures | found a fin-moment-arm defect invisible to either subsystem alone |
| ✅ | Verification wall: no-model re-run, authoritative over the agent's self-report | every study |
| ✅ | Study-level write-up: form follows the goal, figures, provenance tags | glider v2: design document, planform drawing, 127 tagged values |
| ✅ | Nothing ends an arc except the director (tools, screens, transport all recorded) | `b717512`, `3f1cdfa` |
| ✅ | Ideation freed to search the literature itself; keyword APIs retired | `d03a2fa`, `2977ce0` |
| ✅ | Blockers: a run says what it needs from a human rather than faking | `3f1cdfa` |
| ✅ | Token budget the director reasons about; buys depth and breadth | `017dbe6`, `ea91491`; ceiling enforced at `free_director.py:434` — **only when `--token-budget` is passed** |
| ⚠️ | Ideation restructure: pool 76, top-6 deep-reviewed, 2 calls each, 6 concurrent | `c296689` — **arithmetic only, STILL NOT validated live** |
| ⚠️ | Run-readiness fixes (logging run-killer, unauthorized wrapper, ideation reserve) | `8898681`, `3f9cc7b`, `dbb9469` — **green in tests, never run live** |
| ✅ | Build critic (practitioner lens) + referee (words vs code) + claim review | `72ea67f`, `7bffb43` |
| ✅ | Sandbox profiles (atomistic / biodesign / engineering), remote GPU lane, connector→kept-number bridge | parallel sessions |
| ✅ | liveview event log; watcher sees decisions, hypotheses, blockers | `dafa57d`, `7d9cc09` |

## Phase 1 — before any long run

| # | Task | Status | Why here |
|---|---|---|---|
| 1 | **Per-phase cost reporting** | ✅ **DONE 2026-07-28**, verified by running it | `pi_agent/cost_report.py`. Result above: 98.7% of spend is inside experimenter runs. Its honest limit is that it cannot see *inside* a run. |
| 2 | **Proportional verification** | **STILL BLOCKED — premise unmeasured** | The wall spends zero tokens, and item 1 confirms the spend is all intra-run but cannot split it. Needs intra-run attribution before anything is built. Candidates named below and deliberately held. |
| 3 | **Cheap validation run** | ⚠️ **HALF DONE 2026-07-28** — `study-20260728T151306Z` | The system COMPLETES A RUN AGAIN: 1 move, 3m52s, 1,136,628 tokens against a 3M budget, publishable, zero `decision_failed`, zero retries, clean log. First completed run since 07-27. **But ideation never fired**, so the restructure is still 100% unvalidated, and no spawn/integration/multi-move path was touched. See #3a. |
| 3a | **Second cheap run — one that forces ideation** | **DO THIS NEXT** | The goal in #3 was accidentally the literal placeholder text, so the director (correctly) answered a trivial self-chosen question in one move and stopped. Needs a real goal, ideally one that warrants decomposition, to exercise `call_ideation` and spawn. Same cost class as #3. |
| 3b | **Intra-run cost attribution** | not started, gated on #3 | What item 2 actually needs, and item 1 revealed rather than delivered. Scope only AFTER #3 — a completed run may make the shape obvious, and the experimenter's turn loop is the thing to instrument. |
| 4 | **Resumability** | not started | Still the ceiling on multi-day research. Note the six recent deaths were at move 1, not five hours in — resumability would not have saved them; a token ceiling would have saved the 15M-token one. Do not over-rate this on the strength of those six. |

### Item 2's candidates, held deliberately until there is a baseline

Named now so they are not re-derived, **not to be applied before the run in #3** —
changing the incentive before measuring destroys the baseline.

- `stages/free_experimenter.py:74` still tells the agent `"publishable": true
  only if ... every kept finding reproduced`. The code was relaxed to
  "any reproduced" by owner ruling on 2026-07-25
  (`free_experimenter.py:322-331`). **The prompt is stating a rule the code no
  longer enforces**, and the stricter rule is exactly the pressure to keep only
  trivially-verifiable findings. This is the cheapest, highest-leverage
  candidate, and it is the project's recurring shape: a prompt forbidding what
  the system already permits.
- `liveview/render.py:193-195` colours a run green only when
  `verified == claims` — an operator-facing scoreboard that rewards making every
  claim trivial.
- No claim carries importance / load-bearing-ness. The concept exists as prose
  only (`free_experimenter.py:66`, "a number the whole conclusion rests on").
  Per-claim declarative fields already ride the finding schema end-to-end
  (`tolerance`, `profile`), so the wiring for an `importance` field is built.
- The obstacle to name in any design: `verification.py:825-829` and
  `free_experimenter.py:188-190` record an explicit anti-triage ruling ("would
  quietly shrink the denominator"). Skipping claims argues against a recorded
  honesty invariant — that is a STOP-and-rule, not a refactor.

**NEW EVIDENCE 2026-07-28 (`study-20260728T151306Z`, current code):** the
finding-padding half of item 2 is REAL and CURRENT, not a glider-era artifact.
The run answered a question whose content is about three numbers (S₁₀, ln 2,
their difference) and recorded **ten findings, nine verified** — including the
*numerator* of a fraction and its *denominator* as two separate verified
findings, ln 2 (a mathematical constant) "verified" by recomputing it, and two
residuals that are checks of checks. Everything trivially reproducible was kept
and reproduced; the one finding that failed (`rerun_failed`, n·|error| at n=40)
was the only one making a non-trivial claim.

This does NOT yet establish the token half — 1,041,139 tokens went into that one
move and its composition is still invisible (item 3b). But the incentive shape
is now observed on current code, which it was not before.

Observed shape, for calibration: across all 410 findings on disk only **7%** are
verification bookkeeping by label (SHA-256, byte size, "INDEPENDENT CHECK 2",
"maximum spread across routes") — but **20%** in glider v2 and **75%** in the
climate study. In glider v2 the headline glide ratio is `verified: false` while
three checks *of* it are `verified: true`.

## Phase 2 — genuinely smarter than a chat

| # | Task | Status | Note |
|---|---|---|---|
| 5 | Finish unblocking | ongoing | The recurring pattern: a prompt forbids what the agent can already do. Item 2's first candidate above is one. |
| 6 | **Smarter phase system + more powerful director** | not started | The core differentiator and least-built item. Likely needs MACHINERY, not prompts: dependencies between phases, feedback edges so an integration failure reopens a subsystem, budget reservable for that. Scope deliberately. |
| 7 | Make cross-study memory actually work | not started | `read_memory`/`write_memory` exist; no evidence a later study is better for an earlier one. That is the accumulation premise, unvalidated. |

## Phase 3 — prove it

| # | Task | Status | Note |
|---|---|---|---|
| 8 | Comparison protocol | not started | Same goal, chat vs system, side by side. Without it "better than a chat" is an impression — and it is what the product claim rests on. |
| 9 | Test-time compute scaling experiments | owner | |
| 10 | Long validation run — engineering | not started | **Bar: something nobody would imagine a single chat doing.** |
| 11 | Long validation run — science | not started | Same bar. |

## Phase 4 — product

| # | Task | Status | Note |
|---|---|---|---|
| 12 | Security and multi-tenancy | not started | Running strangers' code in Docker on owned infrastructure is a security problem, not cleanup. Secrets, isolation, cost attribution. May shape architecture — do not defer thinking about it. |
| 13 | Cleanup and ship | not started | |

---

## Deferred, waiting on evidence

- **Director-chosen carry selection** — every move carries all artifacts (cap 8).
  Wake when a study is seen to over-carry.
- **Merging the remaining review calls** — scrutiny already merged three into
  one; the `full_review` split could go further if cost still bites.
- **Dead measurement rails** — `memory/ledgers.py` (zero non-test callers, its
  producers purged 2026-07-23) and `harness/` batteries. `tools/gpu_budget.py`
  is live but orphan: 368 ledger lines, all `usd: 0.0`, never wired to the
  director's cost picture. Clean up when touching cost code, not before.

## Standing rules

PRIME DIRECTIVE (never weaker than a chat) · nothing ends an arc but the
director · verification purity (no model in that path) · never `git add -A` ·
run-venue rule (plain Terminal under `caffeinate`) · STOP-and-rule for contracts
and locked schemas.

**NEW (2026-07-28) — always pass `--token-budget`.** `--max-moves` is a
structural backstop, not a cost ceiling. `study-20260727T045848Z` spent 15.17M
tokens and ran zero experiments with no token ceiling set; the enforcement at
`free_director.py:434` is a no-op without the flag. Also pass `--director free`
— the CLI still defaults to `enum`.
