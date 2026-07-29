# Roadmap status — the checklist

**This file is the shared plan, and it is a CHECKLIST.** The coordinating
("brain") session owns it. Evidence and reasoning live in
`docs/findings_2026-07-28.md`; if this file starts growing narrative again,
move it there.

Last verified against the repo: **2026-07-28** (evening), HEAD `aaa2279`,
branch `iterate-experiment-loop`. Suite: **2147 passed, 1 skipped**, exit 0.

> **Do not trust a status without checking.** Several sessions commit to this
> tree in parallel. Re-derive from `git log`, the suite, and `studies/` before
> planning. The project's named trap is assert-without-looking — it caught the
> brain session twice today (see the findings file).

---

## THE CHECKLIST

Ordered by one constraint: **a long run consumes the rest of the week's limit**,
so it is the last act of the week. Everything free happens first, and the long
run must carry every job it can.

### Next — offline, costs no compute

- [x] **1. System map — DONE 2026-07-28** (`1e6c16d`), `docs/system_map.md`.
      Control flow, where the money goes, a CODE-vs-PROMPT lever table, the
      knobs, what is built but never runs, and the interjection seams.
      **It surfaced 11 verified defects — see below; three are worth doing
      before the long run.**
- [ ] **1b. Fix the tool guard (`PreToolUse`).** Small, and the highest-value
      thing the map found: `capability_guard` AND layer 1 of the token ceiling
      are both delivered via `can_use_tool`, which the SDK never invokes for
      tools already on `allowed_tools`. Both are inert today. Fixing it restores
      two protections that are currently believed to exist — and it makes the
      token ceiling actually bind, which matters for a $150 run.
- [ ] **1c. Give in-process capabilities a token allowance.** `call_ideation` at
      `depth:"full"` costs one move and is uncapped; one was measured at 17.5M
      tokens. A long run can lose its budget to a single capability call.
- [ ] **1d. Either wire `novelty_priority` into the director's envelope or
      delete it.** It is read by `capabilities.py` but the validator rejects it,
      so the 2026-07-27 ruling is unimplemented either way.
- [ ] **2. Auto-commit run code to git.** Small.
- [ ] **3. Design the comparison protocol.** Not a run — the written-in-advance
      criteria for what a good answer must contain, fixed *before* either side
      runs. Without it the comparison is an impression.

### The week-ending spend — one run, three jobs

- [ ] **4. Long engineering run = the comparison (owner ruling 2026-07-28).**
      One goal, run once through the system and once as a single Claude chat
      prompt. Does the long engineering run, the comparison protocol, and the
      open compute-allocation question in a single spend.
      `--token-budget 150000000` ≈ $150.
      **Goal-writing rules, learned the expensive way:**
      - Say what the deliverable IS ("design it, tell me how to build it, give
        me the code") — the system should not turn a clear engineering ask into
        a research study.
      - **No standing "each part must be verified before it is built on".**
        That clause was in the glider goal and cost most of its $53.
      - Always pass `--token-budget` and `--director free`.

### Later, or blocked on runs that do not exist yet

- [ ] 5. Interjection — human watches a live run and injects a request.
      Owner: probably not V1.
- [ ] 6. Front end. After interjection; they share a surface.
- [ ] 7. Science long run — a different week.
- [ ] 8. Security and multi-tenancy — offline thinking, gating nothing now.
- [ ] 9. Cleanup and ship.

### Open question, not yet a task

- **Does the director allocate compute smartly?** The owner's framing, and the
  better one. The glider filled its move pool because a pool was the only
  budget it could see (see findings). A prompt fix landed 2026-07-27 and the two
  runs since have not padded — but both goals were cheap. **The long run is
  where this shows.** Do not build for it beforehand.

---

## RESULT 2026-07-29 — the system refuted the memory fix, with verified numbers

`study-20260728T225951Z` ($27.50, 228 agentic turns, 4 moves). The goal was the
architecture problem itself. **The director called ideation at full depth
unprompted** — the apparatus is reached for exactly when the ideas are the
deliverable, confirming the pattern.

Then it did real science on it: simulate → test against reality → refute →
verify the refutation.

- **Move 2** (simulation, 12 findings): designed a memory policy that beat an
  unbounded-memory floor **1.55x** on a simulated long arc.
- **Move 3** (real LLM director, 14 findings, **0 verified**): every claim from
  move 2 died. Predicted ≥1.0, got **0.336**. Predicted 1.45x, got **0.403**.
  This is the move that printed FAILED — it is the most valuable move in the
  study.
- **Move 4** (22 findings, **22 verified**): made the refutation a measured
  result. Four bounded-memory policies against a matched per-seed floor:

| arm | ratio to floor |
|---|---|
| B — raw append-everything log, 2 kB bounded re-read | **0.970** |
| E — v2 records, staling trigger disabled | 0.909 |
| C — catalogue-sized 14,936 B budget | 0.835 |
| D — v2 record discipline, no re-read bound | 0.697 |

**No policy cleared the floor.** The floor is *re-read the entire arc* — which
is exactly what the system does today.

**And the mechanism why, which is the deeper finding.** An injected FALSE
"already answered" record was re-probed **0.0 times** under a summarised ledger,
versus **1.67 times** under plain full-arc re-read. A summarised memory can
carry a wrong belief that nothing ever challenges. **The un-summarised arc is
the self-correction mechanism** — compaction would remove it.

### Consequences

- ❌ **Arc compaction / memory summarisation: DROPPED.** I recommended it on
  reasoning about context growth; the system measured it and it loses. Do not
  revive without evidence that beats a matched floor.
- ⚠️ **CORRECTED: this does NOT show the apparatus beats a chat.** The "floor"
  in the experiment is *the system's own director re-reading its whole arc* —
  the do-nothing baseline, which move 3's summary calls "a plain chat that
  re-reads its arc". So what is measured is **candidate memory policies vs the
  current design**, and the current design won. Whether the whole apparatus
  (director + experimenter + wall + tools) beats one prompt to a chat window is
  **still unmeasured** — it is the checklist's comparison item and nothing here
  substitutes for it. The cage pattern is real and measured *within* the
  director; do not stretch it into the product claim.
- ⚠️ **Caution on simulated evidence:** move 2's 1.55x winner was a simulation
  artifact that did not survive a real director. Simulation earned its keep only
  because move 3 tested it.
- **Director-smarter survives as the direction** — but memory is not the lever.
  What remains: it cannot see its own trajectory (no dollars, no remaining
  turns, no decision cap), and `stop` is unconditional.

## Done

### Today (2026-07-28)
- ✅ **Per-phase cost reporting** — `pi_agent/cost_report.py` (`9f19e20`,
  `4d16ead`, `538ef97`). Also fixed a 3x tree under-count and the misnamed
  `decider_spend`.
- ✅ **Token ceiling binds inside a move** (`27da720`). A 5M budget had spent
  7.9M; the ceiling was only checked between moves.
- ✅ **Resumability** — `--resume-study <id>` (`1913b6f`).
- ✅ **`--paper` writes the PDF** (`aaa2279`). Runs after the referee and build
  critic, since both append to `paper.md`. Needs a TeX engine
  (`brew install tectonic`); degrades to `.tex` without one.

### Earlier — proven live
Free director (decomposes, spawns, recurses, divisible budget) · carry bus ·
integration check that caught a real interface defect · verification wall
(no model in the path) · study write-up with figures and provenance tags ·
nothing ends an arc but the director · blockers instead of faking · token
budget the director reasons about · build critic + referee + claim review ·
sandbox profiles, remote GPU lane, connector→kept-number bridge · liveview.

---

## Settled, with the number that settled it

- **A study costs ~$53, not ~$270.** Reported "tokens" sum input, output, cache
  writes and cache reads at face value; 96.3% of the glider's 54M were cache
  reads at $0.50/M. **Conversion: ~$1 per million reported tokens.**
- **Orchestration is 1.3% of spend.** 98.7% is inside experimenter runs.
- **Cost levers, if ever needed:** output tokens (1.5% of tokens, 38% of cost)
  and cache reads. **Not** context size — real input is 0.1%.

## Dropped — do not resurrect without new evidence

- **Streamline compute at the director/phase level** — nothing there to win.
- **Proportional verification** — the wall spends zero tokens; the padding was
  a pre-fix budget-filling behaviour plus a verification clause in the goal.
- **Intra-run cost attribution** — existed only to serve the item above.
- **Further validation runs** — two proved the machinery.
- **"Director constructs a comparative frontier"** — withdrawn 2026-07-28. Built
  on a pre-fix study; a clear engineering ask should get a clear engineering
  deliverable.
- **Cross-study memory** — owner: not wanted.
- **Paper digestibility check** — the build critic already asks "could a
  competent person use this tomorrow".
- ⏸️ **The ideation apparatus** — has never fired in any live run; may be dead
  code on the free path. A simplification opportunity, not a task. Never make
  it mandatory.

---

## Standing rules

PRIME DIRECTIVE (never weaker than a chat) · nothing ends an arc but the
director · verification purity (no model in that path) · never `git add -A` ·
run-venue rule (plain Terminal under `caffeinate`) · STOP-and-rule for contracts
and locked schemas.

**Always pass `--token-budget` and `--director free`.** `--max-moves` is a
structural backstop, not a cost ceiling, and the CLI still defaults to the enum
director. A run launched without a token budget once spent 15.17M tokens and ran
zero experiments.
