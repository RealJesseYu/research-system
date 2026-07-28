# Roadmap status — the living list

**This file is the shared plan.** The coordinating ("brain") session owns it and
updates it as work lands. Anyone can read it; do not let it go stale.

Last verified against the repo: **2026-07-28**, HEAD `47cad5c`, suite 2083 passed
/ 1 skipped / 1 known Docker flake.

> **Do not trust the statuses below without checking.** Several sessions commit
> to this tree in parallel. Re-derive from `git log`, the test suite, and
> `studies/` before planning. The project's named trap is assert-without-looking.

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
| ✅ | Token budget the director reasons about; buys depth and breadth | `017dbe6`, `ea91491` |
| ✅ | Ideation restructure: pool 76, top-6 deep-reviewed, 2 calls each, 6 concurrent | `c296689` — **arithmetic only, NOT validated live** |
| ✅ | Build critic (practitioner lens) + referee (words vs code) + claim review | `72ea67f`, `7bffb43` |
| ✅ | Sandbox profiles (atomistic / biodesign / engineering), remote GPU lane, connector→kept-number bridge | parallel sessions |
| ✅ | liveview event log; watcher sees decisions, hypotheses, blockers | `dafa57d`, `7d9cc09` |

## Phase 1 — before any long run

| # | Task | Status | Why here |
|---|---|---|---|
| 1 | **Per-phase cost reporting** | not started | You cannot streamline what you cannot see. It is the instrument for measuring #2, and today it takes hand-analysis of `report.json`. Small. |
| 2 | **Proportional verification** | **BLOCKING** | The glider study was ~90% verification of a five-minute problem. On a complex task that ratio is unaffordable. The review side is proportional; the verification side is not. Root cause is the INCENTIVE — verified findings are the only thing scored — so prompt text alone will lose to the gradient. |
| 3 | **Cheap validation run (~10 min)** | not started | Confirms the ideation restructure AND #2 on real work for a fraction of a window. |
| 4 | **Resumability** | not started | Two runs have died (one on a usage window, five hours in) and lost everything. This is the ceiling on multi-day research, and the arc is already fully on disk. |

## Phase 2 — genuinely smarter than a chat

| # | Task | Status | Note |
|---|---|---|---|
| 5 | Finish unblocking | ongoing | The recurring pattern: a prompt forbids what the agent can already do. |
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

## Standing rules

PRIME DIRECTIVE (never weaker than a chat) · nothing ends an arc but the
director · verification purity (no model in that path) · never `git add -A` ·
run-venue rule (plain Terminal under `caffeinate`) · STOP-and-rule for contracts
and locked schemas.
