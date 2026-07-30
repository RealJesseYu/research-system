# Roadmap status — the checklist

**This file is the shared plan, and it is a CHECKLIST.** The coordinating
("brain") session owns it. Evidence and reasoning live in
`docs/findings_2026-07-28.md`; if this file starts growing narrative again,
move it there.

Last verified against the repo: **2026-07-30 01:30Z**, HEAD `2fd77a1`, branch
`iterate-experiment-loop`. Suite: **2278 passed, 1 skipped, 63 subtests**, via
`venv/bin/python3 -m pytest tests/`.

> ⚠️ **Run `pytest tests/`, not bare `pytest`.** There is no pytest config, and
> experimenter workspaces now contain their own `test_*.py`
> (`runs/study-20260729T210651Z-m2/workspace/test_lgamma.py` and two others), so
> a bare `pytest` dies at collection with 3 errors and reads as a broken suite.
> Fix when convenient: `[tool.pytest.ini_options] testpaths = ["tests"]`.
> Also: two suites in parallel collide on a fixed Docker container name and
> `test_run_scipy.py::TestEscape6ResourceBomb` fails spuriously. Run one at a time.

> **Do not trust a status without checking.** Several sessions commit to this
> tree in parallel. Re-derive from `git log`, the suite, and `studies/` before
> planning. The project's named trap is assert-without-looking — it caught the
> brain session twice today (see the findings file).

---

## THE CHECKLIST

Ordered by one constraint: **a long run consumes the rest of the week's limit**,
so it is the last act of the week. Everything free happens first, and the long
run must carry every job it can.

### NEXT SESSION — the five additive improvements (owner ruled 2026-07-29)

Full plan with file:line detail, traps and ordering: **`docs/plan_additive_director.md`**.
The test they all pass: ADDITIVE (adds a capability) survives, SUBSTITUTIVE
(replaces the agent's access to what happened) does not — measured, see the
result section below.

- [x] **A1. DONE `6eca379`. Wire parallel fan-out into the free director.** `run_study_fan`
      (`pi_agent/study.py:378`) is finished and concurrency-safe; its only caller
      is the dead enum loop. **Wall-clock serialism is the real ceiling** — every
      move is 69–84 turns and ~1 hour, strictly sequential. Needs: new action +
      envelope field + validator, N moves spent for an N-wide fan, and the token
      allowance divided (it currently hands one move the WHOLE remainder).
- [x] **A2. DONE `82db60e`. Show the director its own trajectory.** Dollars, turns, decisions
      remaining. Item C already records `usd`/`turns` per arc entry — the data
      exists and is simply not surfaced in `_budget_view`.
- [x] **A3. DONE `4b1da90`. Prediction column.** The director records what it expects a move to
      show; sees prediction vs outcome next turn. h13's idea moved to the
      additive side — it must gate nothing.
- [x] **A4. DONE `7ebb28a`. ev2** — persist failed/superseded producers tagged with the regime
      that broke them, at the artifact level beside the carry bus. A hypothesis
      to measure against a matched floor, not a fix to ship.
- [~] **A5. DEFERRED `9863271`, design recorded in docs/design_intermediate_signal.md. Intermediate signal from a running move.** 69–84 turns with zero
      visibility. Hardest; shares a seam with interjection; do last.

### AFTER THE FIVE — the fork everything has been clearing the way for

### EXPERIMENT 2 — goal 2, the open-ended class (IN FLIGHT 2026-07-30)

Experiment 1 (goal 1, defined task) is COMPLETE and arm C won — see Done below.
Experiment 2 is the class where the director's judgement *is* the product.

- [~] **Arm C.** `./run_comparison.sh goal2` from a plain Terminal.
      150M tokens ≈ **$150** at the verified ~$1/M conversion, 15 moves.
      **An aborted launch exists on disk:** `studies/study-20260730T011933Z`,
      created 01:19:33Z, goal string byte-identical to the frozen one (1144 chars,
      matches `run_comparison.sh` and `docs/comparison_goals.md`), but ZERO moves —
      no `arc.jsonl`, no `decisions/`, empty `director_workspace` — and no process
      alive. It died before move 1. The launch path is unchanged since experiment
      1's arm C succeeded on it 4 h earlier, so a startup crash is unlikely; treat
      it as an abort unless a traceback says otherwise. Nothing to resume (zero
      arc): relaunch fresh, leave the empty dir as evidence of the attempt.
- [ ] **Arm B — AND MEASURE ITS COST THIS TIME** (the named gap from experiment 1).
      Method verified live 2026-07-30:
      `claude -p "<GOAL2>" --dangerously-skip-permissions --output-format json > armB.json`
      in a clean directory. That JSON carries `total_cost_usd`, `num_turns`,
      `duration_ms` and a per-model breakdown, and it runs on **`claude-opus-5`** —
      the same model arm C uses on every tier (`models.py:44`, `:75`), so the
      comparison is not confounded by model. Same measurement basis as arm C.
      Take the goal string out of `run_comparison.sh`; never retype it.
- [ ] **Arm A — a BARE chat this time** (claude.ai, no tools, one prompt). In
      experiment 1 arm A had tools, so there was no floor arm. Protocol §2: claim
      nothing from beating it.
- [ ] **Judge per protocol §4/§6** — score each arm blind to the others, recompute
      criteria 2 and 3 mechanically, and have someone who did NOT watch the runs
      do the scoring.

- [ ] **B1. The long engineering run, which IS the chat comparison.** One goal,
      run once through the system and once as a single Claude chat prompt.
      Fan-out (A1) changes what this run can be — 15 moves stops being a
      15-hour serial chain. Write the goal saying what the deliverable IS, with
      NO standing "verify each part" clause, and pass `--token-budget` and
      `--director free`. Design the judging criteria BEFORE either side runs
      (see B0) or the result is an impression.
- [x] **B0. DONE 2026-07-29** — `docs/comparison_protocol.md`, written before
      any arm ran and frozen. Three arms (bare chat / **Claude Code one prompt,
      the real baseline** / this system), seven criteria, and four falsifiers
      named in advance. **The question is not "better than a chat" — it is
      whether the orchestration beats ONE strong agent with the same tools.**
      An independent system (AI Scientist) is cited, not run: standing it up
      would consume the week B1 needs. Offline, free, and it must
      precede B1: what must a good answer contain, written down in advance.

**One risk to weigh before B1 (owner's call, stated with numbers rather than
relitigated).** Fan-out is new CONCURRENCY in the critical path of the
week-ending spend, and concurrency is precisely what offline tests miss. Its
blast radius is bounded by design — a failing member is recorded, not fatal —
but a wedged fan spends up to 8 moves for nothing. A 2–3 wide fan on throwaway
questions costs ~$10–20 and about an hour, roughly 10% of B1. That is insurance
on the one unexercised path, not a return to the validation-run habit. Declining
it knowingly is a perfectly reasonable call; declining it by default is not.

**Then the roadmap forks, and this is the honest shape of it:**

- **If the system clearly beats one chat prompt** → the product claim is real.
  Go to Phase 4: security and multi-tenancy (running strangers' code in Docker
  is a security problem, not cleanup), then interjection + front end, then ship.
- **If it does not** → that is the most valuable finding available, and it
  reshapes everything above it. Better to learn it from one $150 run than after
  building a product on top of it.

**Do not schedule past this fork.** Everything beyond B1 is contingent on what
B1 says, and planning it now is planning against imagination — the same mistake
that produced the arc-compaction work the system later refuted.

### C1 — PACKAGE THE DELIVERABLE (new, owner 2026-07-29) ← on the todo

- [x] **C1. DONE 2026-07-29** (`c330ab7`) — `stages/study_deliverable.py`. Verified on the experiment-1 winner: opening `studies/<id>/deliverable/` and running `verify_betainc.py` reproduces `n_points_over_1e-12 = 0` with the stdlib alone. It also caught the paper wrongly claiming its own source was unavailable. ~~A study's deliverable must be usable without assembling it.~~
      **This is the one criterion a single Claude Code session BEAT the
      orchestration on** in experiment 1. Arm B shipped `~/ibeta-lib`: a clean
      directory, a `REPORT.md`, and reproduce-from-scratch commands. Arm C's
      artifacts sit in `runs/<id>/workspace/`, the paper is in
      `studies/<id>/paper.md`, and there is **no README anywhere**. A competent
      person can act on B's output immediately; C's has to be excavated first.
      It is also the first thing any reader hits, so it is worth more than its
      size suggests. Likely shape: at study close, collect the deliverable
      files beside the paper with a generated README naming what each is and how
      to reproduce it. Offline, small. See `docs/debrief_experiment1.md` §5.

### Also open — offline, costs no compute

- [x] **1. System map — DONE 2026-07-28** (`1e6c16d`), `docs/system_map.md`.
      Control flow, where the money goes, a CODE-vs-PROMPT lever table, the
      knobs, what is built but never runs, and the interjection seams.
      **It surfaced 11 verified defects — see below; three are worth doing
      before the long run.**
- [x] **1b. DONE — verified in code 2026-07-30.** The guard is delivered as a real
      `PreToolUse` hook (`model_call.py:598`, `HookMatcher(matcher=None, ...)`),
      not the `can_use_tool` callback the SDK skips for allowed tools. Covered by
      `tests/test_pre_tool_use_hook.py`.
- [x] **1c. DONE — verified in code 2026-07-30.** `_capability_allowance`
      (`pi_agent/free_director.py:108`) binds the study's remaining token room onto
      this process's env around the in-process call (`:1103`); `model_call` enforces
      it as it does inside a move. `pi_agent/capabilities.py:28` records the why.
- [x] **1d. DONE — verified in code 2026-07-30.** `novelty_priority` is in the
      envelope key list (`pi_agent/free_decider.py:73`), documented in the decider
      prompt (`:113`), validated as call_ideation-only with an enum
      (`:236`–`:244`), and consumed at `pi_agent/capabilities.py:100`.

*(These three were listed open until 2026-07-30 and had in fact shipped with the
five additive improvements. Re-derived from the files, not from the handoff.)*
- [ ] **1e. `MAX_CODE_BYTES = 100_000` refuses legitimate reproducers.**
      `tools/run_python_experiment.py:199`, enforced at `:316`. Found live in
      experiment 2, move 5 (`study-20260730T034915Z`): a real NHANES analysis over
      6 CDC public-use files lost **19 of 19 claims** to `unrunnable_artifact:
      'code' exceeds 100000 bytes`. The analysis was not wrong — it was
      unverifiable for a size cap, so the wall discarded sound work. Not a purity
      question (no model enters the path either way); the cap is arbitrary and a
      real analysis outgrew it. Decide: raise it, or split a large reproducer.
      **Do not touch this while a run is live.**
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

### 2026-07-29 — EXPERIMENT 1 COMPLETE (goal 1, defined task)
- ✅ **The orchestration met a spec a single strong agent missed.** 0 of 73,688
  points over 1e-12 (worst 4.508e-13) vs Claude Code's 6 of 57,282 (worst
  1.405e-12), and **~26x better at the exact corner that defeated it**. Every
  headline recomputed from raw data. No falsifier fired.
  `docs/comparison_results_goal1.md` · `docs/debrief_experiment1.md`
- ✅ **Three of the four new improvements earned their keep on first outing** —
  fan-out ran 3 concurrent supervisors, the trajectory view was reasoned from,
  and the prediction column **called the final error to within ~20% before the
  integration ran**. A4 (ev2) never fired.

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
  reads at $0.50/M.
- **REFINED 2026-07-30, recomputed from `report.json` across every study: the rate
  is $1.30 per million reported tokens, not $1.00.** Only one study has
  `moves_with_usd == moves_with_cost` — every move reporting dollars —
  `study-20260729T210651Z`: 46,357,309 tokens / **$60.41** = **$1.303 /M**. The
  other ($27.50 over 35.1M = $0.78/M) reports dollars for 3 of 4 moves and so
  under-counts. n=1 for the clean rate; re-derive when experiment 2 lands.
- **Two factors, not one — and confusing them will overrun a budget.** Experiment
  1 was given 60M and spent **46.4M (77% utilisation)**, so at $1.30/M it cost
  $60.41 and *looked* like a 1:1 budget-to-dollars rule. It is not.
  **Worst case = budget_M × $1.30. Likely case = budget_M × $1.00 at ~77%
  utilisation. Plan with the worst case** — a 150M budget can cost ~$195.
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
