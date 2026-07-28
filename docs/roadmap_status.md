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

## The ideation question (opened 2026-07-28, two runs)

**`call_ideation` has not fired in either live run**, and in both the director's
reasoning is defensible rather than broken:

- `study-20260728T151306Z`: the goal was a placeholder, so one cheap exact
  question was the whole job.
- `study-20260728T152819Z`: *"one broad but cheap survey run that fits and
  FLOP-counts several genuinely different functional families at once will tell
  me which family is even in contention, before I spend the remaining tokens
  refining"* — and it did exactly that, comparing six families in one move.

So the director explores **inside a single experiment** rather than by reaching
for the ideation apparatus. That is not obviously wrong; it may be cheaper and
better. But it means the whole Co-Scientist ideation stack — four generation
strategies, six review types, Elo tournament, evolution, meta-review, and the
`c296689` restructure — **may be effectively dead code on the free path**, and
every kill-rate measurement behind it describes a subsystem that production
never calls. Do NOT fix this by making ideation mandatory (that is a cage, and
the PRIME DIRECTIVE forbids it). The open question is whether the director
should be *told what the tool is for* more clearly, or whether the honest
finding is that a free agent does not want it. Resolve before item 6.

## Finding quality — the padding claim needs splitting

`study-20260728T152819Z` did NOT pad. Its 16 findings are two numbers
(worst-case error, operation count) across six functional families, plus a
tail-bound witness and a discontinuity check. That is proportionate to the
question. Contrast `study-20260728T151306Z`, which recorded a fraction's
numerator and denominator as separate verified findings and "verified" ln 2 by
recomputing a constant.

Provisional read: padding shows up on **trivial** questions, where there is not
enough real content to fill a findings list, and not on substantive ones. If
that holds, item 2 matters much less than the glider study suggested — the
glider's 20% check-like rate may say more about that particular goal than about
the system. **Two runs is not enough to conclude this.** Watch it on the next
substantive run before acting.

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

## OWNER RULING 2026-07-28 (evening): stop validating, start running

Compute is the scarce resource and it is being spent on smoke runs and plumbing.
The list below is cut to the two things that genuinely block a long run. Both
are OFFLINE build tasks costing zero compute to develop. **No further validation
runs.** The long run IS the validation.

**Cut, with reasons — do not resurrect these without new evidence:**

- ⚠️ **"Streamline compute" — NARROWED, NOT DELETED (corrected 2026-07-28).**
  Orchestration is 1.3%, so streamlining *the director* is pointless. But the
  owner's actual question was never about orchestration — it was "why does a
  glider study cost 55M tokens", and that is about the 98.7%. See "What 55M
  tokens actually means" below. It is now item C, and it is nearly free.
- ❌ **Proportional verification (old item 2, the former "BLOCKING" item).** Its
  premise has weakened twice in one day: the wall spends zero tokens, and the
  substantive run did not pad (16 findings = 2 numbers × 6 families). Padding
  appears on TRIVIAL questions, and long runs are not trivial. **Do not build
  it.** Revisit only if a substantive long run shows a real verification ratio
  problem — which the cost report can now detect.
- ❌ **Intra-run cost attribution (old 3b).** Existed only to serve the item
  above. Dropped with it.
- ❌ **Further cheap/validation runs.** Two were enough to prove the machinery
  runs. More would only re-prove it.
- ⏸️ **The ideation apparatus.** Never fired in either live run; may be dead code
  on the free path. That is a SIMPLIFICATION opportunity, not a task — do not
  spend on it, do not make it mandatory. Note it and move on.

## What 55M tokens actually means (2026-07-28) — the number is not a cost

**The reported token totals are not dollars, and are not even comparable
quantities.** `cost_meter.record_call` sums **every integer field** of the SDK
usage dict (`cost_meter.py:91-95`, `for key, value in usage.items()`). That
means `input_tokens`, `output_tokens`, `cache_creation_input_tokens` and
`cache_read_input_tokens` are all added together at face value — and a cache
read costs about a tenth of an input token. So "55M tokens" is four differently
priced things summed as if they were one.

**Proof it is dominated by re-reads, by arithmetic alone:** one move in
`study-20260728T152819Z` recorded **7,851,857 tokens across 2 calls** — ~3.9M
per call. A single call cannot have 3.9M *distinct* input tokens; the context
window is ~200k. So the overwhelming majority of that number is **the same
context counted again on every turn** of a 200-turn agentic loop
(`model_call.py:212-217`, `FULL = Capabilities(..., 200)`), not 3.9M tokens of
distinct work.

**And the real number is already being handed to us and thrown away.**
`ResultMessage` carries `total_cost_usd` (SDK `types.py:1210`) — the CLI's own
correctly-priced figure — and `num_turns`. Neither is recorded:
`total_cost_usd` appears **nowhere** in the codebase, and `num_turns` is read
only on the error path (`model_call.py:260`). `model_call.py:392` passes only
`message.usage` to the meter.

### ANSWERED 2026-07-28 — and the cost problem is 5x smaller than it looked

Item C landed (`a1b7dae`). The question was then settled for the PAST studies too,
by recovering per-message usage from the Claude CLI's own session transcripts
(`~/.claude/projects/*<run_id>-workspace/*.jsonl`, deduped by message id). The
recovered sum reproduces the recorded arc tree **exactly — 54,013,618** — so the
breakdown is trustworthy:

| field | tokens | share | rate (opus-5) | cost |
|---|---|---|---|---|
| `cache_read_input_tokens` | 52,032,882 | **96.3%** | $0.50/M | $26.02 |
| `cache_creation_input_tokens` | 1,134,946 | 2.1% | $6.25/M | $7.09 |
| `output_tokens` | 801,965 | 1.5% | $25.00/M | $20.05 |
| `input_tokens` | 43,825 | 0.1% | $5.00/M | $0.22 |
| **true cost** | 54,013,618 | | | **$53.38** |

Claude Opus 5 is **$5 input / $25 output** per MTok; cache reads are 0.1x input
and 5-minute cache writes 1.25x. Priced as if the summed figure were all real
input it would be $270 — so **the token sums overstate cost by ~5.1x**.

**What this means for the roadmap:**
- The glider study cost about **$53**, not the ~$270 the raw number implies.
  Compute is roughly 5x less of a constraint than assumed.
- **The levers are output tokens and cache reads, not context size.** Output is
  1.5% of tokens but 38% of cost; cache reads are 96.3% of tokens but 49% of
  cost. Optimising "context size" would chase the 0.1% that is real input.
- Whether $53/study is even worth optimising is now an owner judgement, not a
  blocked question.

---

## THE VALUE FAILURE IS MOSTLY GOAL SHAPE (2026-07-28, n=3 — read the goals)

Comparing the three live studies' goal text against their output explains the
value difference almost entirely, and it is not flattering to the goals.

**Glider v2 ($53, ~90% verification, 20% check-like findings).** Goal text:
*"Design a small autonomous glider… size the wing for a target glide ratio…
**Each part must be verified before it is built on.**"*
- ZERO comparison: one artifact, one target. Nothing to search over.
- ONE explicit standing verification command, unbounded in scope.
→ The system did exactly what it was told. The 90% verification was **commanded
by the goal**, not a malfunction of the machinery.

**Normal-CDF ($8, 16 proportionate findings, six families compared, shippable C).**
Goal text: *"Find the **cheapest**… where cheap is counted in floating-point
operations… **Consider genuinely different functional families before committing
to one**, and report the winner's worst-case error **verified by a route
independent of the one used to fit it**."*
- An OBJECTIVE WITH A TRADEOFF (minimise cost subject to an accuracy bound).
- An explicit instruction to SEARCH ALTERNATIVES.
- Verification scoped to ONE clause on ONE number.
→ Proportionate verification and real comparative engineering.

**The pattern:** the system's differentiator is *search over alternatives under a
measurable objective*. Given one, it does work a chat cannot (six families
actually measured, not asserted). Given none, it has budget and no remaining
question — and it fills the space with verification, especially if the goal
asked for verification.

### What this means for fixing it

1. **Immediate and free — goal shape.** Every goal should carry: an objective
   with a tradeoff, an explicit instruction to consider genuinely different
   approaches, and verification scoped to the one or two numbers the conclusion
   rests on. Never a standing "verify each part" command.
2. **The real build item — make the DIRECTOR do this.** Turning *"design a
   glider"* into *"compare N planforms on glide ratio vs build difficulty"* is
   what a good PI does with a vague ask. **This is what item 6 should be**, not
   phase plumbing: the director constructing a comparative frontier when the
   goal lacks one. It is the only identified lever that creates value rather
   than moving cost around.
3. **Measurement — the chat comparison.** Until the same goal is run both ways,
   every value judgement is an after-the-fact impression. n=3 is a hypothesis,
   not a finding.

**Falsifier to watch:** if a well-shaped goal still produces output no better
than a chat's, the premise fails and no machinery fixes it. That is what the
paired long run tests.

## NEXT ACTION (2026-07-28, after C/A/B landed): do the long run

Both blockers are closed and the cost worry is 5x smaller than it looked, so
the honest next step is the thing the whole roadmap was clearing the way for.

**Nothing that landed makes a run cheaper, and that is fine.** C is measurement
only; A caps overshoot so the budget means something (it does NOT reduce normal
spend); B stops a death from costing you the work. Cost per unit of work is
unchanged — and at ~$1 per million reported tokens it does not need to change.

**Rule of thumb for sizing a run:** $53.38 / 54.01M = **~$1 per million tokens
as the reports count them**. So `--token-budget 200000000` ≈ $200. A 20-move
study lands around $250. That is the real budget conversation, not 55M-token
sticker shock.

**Do NOT build the smarter phase system first.** Both live runs used a SINGLE
move — there is still no evidence the director uses the phase structure it
already has. Building more phase machinery now repeats the ideation mistake:
elaborate apparatus production never calls.

**Pair the long run with a chat on the same goal.** That gets Phase 3 item 8
(comparison protocol) for free, and it is the only thing that answers the
question the cost work turned out not to be about: is the output worth more
than a chat's? The glider cost $53 and was ~90% verification of a five-minute
problem — that was never a cost failure, it was a value failure.

## Phase 1 — CLOSED (both landed 2026-07-28)

Both are offline builds. Neither needs a run to develop. Do them in ONE session —
they live in the same loop.

| # | Task | Status | Why it is non-negotiable |
|---|---|---|---|
| A | **Make the token ceiling bind INSIDE a move** | **BLOCKING** | `study-20260728T152819Z` was given `--token-budget 5000000` and spent **7,900,340** — 58% over. `free_director.py:434` checks only BETWEEN moves, and one free-experimenter move is an agentic loop of up to 200 turns. A long run cannot be budgeted until this holds, and two windows have already died to runs that ate their budget. |
| B | **Resumability** | **BLOCKING** | A long run's likeliest death is a usage window five hours in — that has already happened once and lost everything. The arc is fully on disk, so this is reconstruction, not new state. Without it a long run is a coin flip you pay a window for. |
| — | Per-phase cost reporting | ✅ DONE | `pi_agent/cost_report.py`. Gave the 1.3% number that deleted "streamline compute". Keep it — it is how a long run gets read afterwards. |
| — | Machinery runs at all | ✅ DONE | Two live runs 2026-07-28, both publishable, clean logs, cost report correct on both. Enough. |

### If proportional verification ever comes back — what was already found

Verification work is CUT (see the ruling above). These are recorded only so a
future session does not re-derive them from scratch, and are **not tasks**.

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
| 6 | **Smarter phase system + more powerful director** | **THE MAIN EVENT — next after A and B** | The core differentiator and least-built item. Needs MACHINERY, not prompts: dependencies between phases, feedback edges so an integration failure reopens a subsystem, budget reservable for that. Note both live runs used ONE move — the director is not yet using the phase structure it has, so measure that before adding more. |
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
