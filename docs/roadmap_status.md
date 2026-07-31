# Roadmap status — the checklist

**This file is the shared plan, and it is a CHECKLIST.** The coordinating
("brain") session owns it. Evidence and reasoning live in
`docs/findings_2026-07-28.md`; if this file starts growing narrative again,
move it there.

Last verified against the repo: **2026-07-30 23:10Z**, HEAD `ed5575a`, branch
`iterate-experiment-loop` — **now pushed to `origin` (first push in the project's
history; the audit found no secret ever committed).** Suite: **2444 tests collect,
2423 passed / 1 skipped**.

> `pytest` at the repo root now works (`pyproject.toml` sets `testpaths`). Still run
> ONE suite at a time: `tests/test_run_scipy.py::TestEscape6ResourceBomb` and
> `tests/test_run_code.py::TestJails` assert on GLOBAL Docker state and flake when
> anything else — another suite, or a live study — is using Docker.

> **Do not trust a status without checking.** Several sessions commit to this
> tree in parallel. Re-derive from `git log`, the suite, and `studies/` before
> planning. The project's named trap is assert-without-looking.

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

> **Two roadmaps now.** This file tracks *fixing what broke*. The separate
> question — what would let this system do things no single strong agent can do at
> all ("design this robot", "build this house", "solve this disease") — lives in
> **`docs/roadmap_capability.md`**. Its Tier 0 is two small items that belong
> before the next run; everything above Tier 0 there is REASONED, not measured.

## BEFORE THE NEXT RUN — the experiment-2 arm C post-mortem (2026-07-30)

Arm C ran on goal 2 (`study-20260730T034915Z`): 16 moves, 113.2M tokens, **$143.97+**,
726 turns, 50/136 claims verified. It produced a real deliverable and **failed the
central ask** — "build a model that beats it, and quantify the win". Verdict on the
owner's bar (*a new way of doing this, comparatively better than the others*):
**failed**. Every item below was re-derived from disk, not read from the paper.

**The causal chain, in order — each link verified:**

1. **Ideation found the answer and the funnel threw it away.** `pool_size: 32,
   depth: full, novelty_priority: balanced`, 6.86M tokens (~$8.90). 33 generated →
   **24 triaged out, EVERY ONE `verdict: "pass"`** (six at `promise: 4`) → 1 survivor.
   The director was handed **2 hypotheses, both the same idea**, both proposing a
   simulated population the goal forbids. Usable yield: **zero**.
   **`h12` (promise 4, pass) was the study**: *"Refitting the AASHO Road Test
   axle-load equivalency relationship jointly with modern long-term pavement
   performance records will show that no single global damage exponent holds…"* —
   and it aimed at overweight-permit pricing, a sharper target than what got built.
   The director re-derived it by hand at move 3 and spent ~$150 getting there.
2. **Ideation ALSO did the state-of-the-art check, and that died in the same file.**
   Its triage reasons name the successors: h1 *"ACI 318-19 already adopted a
   size-effect factor"*, h2 *"Modified B31G/RSTRENG already codified … proposes to
   **rediscover**"*, h3 *"a very crowded dynamic-line-rating literature"*. The
   director then hand-picked six targets — **h1, h2 and h3 are three of them** — and
   settled on AASHTO-93, whose successor (Pavement ME) is the same trap ideation had
   flagged three times.
3. **Nothing ever required a comparison to the state of the art.** The fan brief
   asked each member to obtain data and re-implement the incumbent. Selection ran on
   **data obtainability** — the director's words: *"empirically settles data
   obtainability instead of letting me guess"*. `pmed_survey_2024_counts.csv`
   (Pavement ME **D**esign) arrives at **move 14 — two moves AFTER the replacement
   was already being fitted at move 12** — and is used as an adoption argument, never
   as a benchmark.
4. **The core never reproduced, and the director is NOT at fault.** It diagnosed the
   mechanism exactly (*"m11's small independent scalar producers reproduced 12/12,
   whereas m12/m14 sank whole records in monolithic recomputes"*) and spent its last
   two moves on precisely that. Both died in the last mile — after the expensive
   rebuild, before writing the trivial producer files.
5. **And the move's stated reason is FALSE.** m16 claims *"the token budget ran
   out"*. It spent **17.1M of ~53M** available (`_move_allowance` = whole remaining
   budget) and used **105 of 200 turns**; no context-limit marker in the log; no move
   in the study exceeded 124 turns. m15's blocker likewise claims
   `make_producers.py` *"is already written"* — **it is not in the workspace**.
   The blocker channel is unverified prose, and it is the one channel aimed at a human.

**Therefore: removing the move ceiling would NOT have saved this study.** The ceiling
was real and wrong (see 3b) but it was not the cause. The study failed at move 3.

### Blocking — ALL SIX DONE 2026-07-30 (commits 6745196..a1c3d52 + this one)

- [x] **1. DONE `6745196`. Deliver the pass-verdict POOL to the director.**
      `build_candidate_pool` in stage 1 emits every candidate with the review
      reasoning that decided it (status / promise / screen_reason / novelty /
      quality / critique), written to `stage1/candidate_pool.json` and carried on
      `payload.candidate_pool`; `capabilities.read_candidate_pool` rides it into the
      arc beside the unchanged `hypotheses` digest, bounded at 60 rows. Verified
      against the real arm-C evidence: 34 rows, h12 present at promise 4 with its
      screen reason, the B31G sentence present. `survivors.json` and every threshold
      untouched, so the battery is unaffected.
      **`rescued_from_triage` IS reachable, but only when the first batch leaves
      NOTHING** (`reflection_reviews.py:1398`) — crash-avoidance, not breadth.
      **Triage calibration reported, not retuned: `docs/finding_triage_calibration.md`**
      (addendum item 9). The cut fell inside a tie band — 12 candidates at promise
      >= 4 for 6 slots, tiebreak = generation index, which is exactly what lost h12
      — and the promise score did not predict deep review (5 of 6 selected came back
      fatally flawed or already answered; usable yield zero). Three retunes named,
      none applied.
- [x] **2. DONE `646b0fd`. State-of-the-art comparator**, in
      `stages/free_experimenter.py`'s SYSTEM_PROMPT rather than the fan brief —
      argued from the decisions on disk: 8 of 14 experiment moves were NOT fan
      members, including moves 9-12 where the incumbent was measured and the
      replacement fitted. Asks EARLY, "while you can still change what you build".
      Self-scoping, gates nothing, no schema change; a test pins that no enforcement
      came with it.
- [x] **3. DONE `32ba045`. The token budget binds.** `_resolve_ceiling` returns
      (moves, tokens, provenance) and derives a generous move ceiling from the token
      budget (150M -> 75 moves at 2M/move, ~3.5x the measured 7.08M so it overshoots
      by design). `--cost-cap` converts to TOKENS first at $1.30/Mtok. `max_moves`
      demoted, never deleted — an explicit one still wins and the provenance says so.
- [x] **4. DONE `8df1379`. Blockers reach the human.** `blocked_on` now travels
      `baton._blocked_on` -> run_record extras -> `read_run_result` -> `MoveResult.raw`
      -> arc `tool_output`, which is the shape liveview and the CLI summary already
      read. Not a gate: a blocked move still completes and the arc continues.
- [x] **5. DONE `787201a` — DIAGNOSED, fix deliberately NOT shipped.**
      `docs/finding_m16_stopping_mechanism.md`. It was the TURN wind-up, and
      `turns_seen` counts SDK **content blocks**, not turns: m16's transcript holds
      199 assistant events for 97 unique message ids, so it tripped at "turn 197 of
      200" after 97 real turns, and `tokens_seen` double-counts the same usage
      (34.7M seen vs 17.1M metered). **9 of 12 completed moves were cut off this
      way**, m11 and m15 included; m14 and m15 tripped at "turn 230/221 of 200",
      which is the proof the counter is not counting turns. The message says
      `TOKEN ALLOWANCE EXHAUSTED` whatever fired, which is why m16 reported a budget
      it never spent. **The 4-line fix is written out and awaits a ruling** — it
      roughly doubles every move's real turn ceiling.
- [x] **6. DONE `a1c3d52`. Producer discipline in the brief** — one scalar, one
      file, written AS YOU GO. m11: 12 distinct producer files, 12/12 reproduced;
      m12/m14/m15/m16: 98 findings, **zero artifacts named at all** (an honest
      correction to "shipped monolithic records"). Guidance, not a schema.

### Non-blocking — recorded, fix when convenient

- [ ] **6. Paper stages never ask for prior work.** `free_paper.py` / `study_paper.py` /
      `build_critic.py`: **0** mentions of prior work, related work, literature, state
      of the art or novelty. Cosmetic relative to item 2 — it makes a paper *disclose*
      the problem, not avoid it — but it is nearly free.
- [ ] **7. `matplotlib` is not installed** in the experiment environment; it killed a
      producer and blocked the figure set.
- [ ] **8. A transport hiccup costs a whole move.** Moves 10 and 13 died on
      `Exception: Claude Code returned an error result: success` — 2 of 16 moves, ~$18.
      `model_call`'s retry is deliberately disabled for tooled calls (replay can
      re-commit side effects). The trade is sound; its price is now measured.
- [x] **8b. DONE 2026-07-30. Cost was under-reported and now is not.**
      `tree_spend` showed `moves_with_usd: 12` against `moves: 16`, so the $143.97 is
      a FLOOR (addendum item 8). Cause: `pi_agent/loop.py:_cost_snapshot` returned
      `{calls, tokens}` only, so every IN-PROCESS capability row reached the arc
      priced at nothing — including `call_ideation`, 38 calls and 6,860,767 tokens
      (~$8.90 at the measured rate). It now carries `usd`/`turns` with their coverage
      counters, and `_with_cost` writes them ONLY when coverage moved, so "no call
      reported a price" stays an absent key rather than a recorded $0.00. The other
      three gaps are explained, not bugs: seq 1 is a genuinely free memory read, and
      seq 10 / 13 are the two transport crashes, whose run_records carry
      `{calls: 0, tokens: 0}` because the SDK errored before any usage registered —
      their real spend is unrecoverable, and that stays disclosed rather than
      estimated.
- [ ] **9. `succeeded = bool(publishable)`** (`pi_agent/dispatch.py:528`) conflates
      "the move worked" with "the move finished the goal". The DISPLAY half is fixed
      (`735d6e5`); the semantic half is untouched and needs a ruling.
- [ ] **10. `pytest` at the repo root** dies at collection on experimenter workspace
      test files. Add `[tool.pytest.ini_options] testpaths = ["tests"]`.

### The reusable lesson this run paid for — worth more than any single fix

**Emit numbers as small, independent scalar producers.** m11 reproduced **12/12**;
m12/m14/m15/m16 shipped monolithic recompute records and reproduced **0/34, 0/12,
0/26**. The wall sinks a whole record when any part of it fails. This belongs in the
experimenter's brief.

### Free actions available now (no model spend)

- [ ] **A. Recover the core.** `runs/study-20260730T034915Z-m16/workspace/` is intact
      with the exact cached inputs its blocker names (`ltpp_sdr39_segments_compact.csv`
      58 KB, `ltpp_sdr39_sn_check.csv`, `ltpp_sdr39_mr_units_check.csv`,
      `aashto93_core.py`, `aft_interval.py`); m15 holds `fit_final.json`,
      `design_results.json`, `score_results.json` and every analysis script. Writing
      the scalar producers over cached CSVs answers the question that matters —
      **is the replacement real, or noise?** — without re-running anything.
- [ ] **B. Literature check** on the verified half: is *delivered reliability ≈0.80 vs
      nominal 0.95 on LTPP* already published? Tells you whether ANY of it is new.

### Owner decisions outstanding

- **Arm B has not run.** ~$20, needs you at the keyboard, and it answers the
  falsifier directly: if one Claude Code session thinks to check Pavement ME, it
  beats arm C on criteria 1 and 4 and *"arm B matches or beats arm C"* fires.
- **Re-running arm C:** the goal string must NOT change (protocol §6 — arm C has run
  on it). Fixing the system is fine. But arm C would then have had two attempts and
  arm B none; that must be stated in the write-up.

---

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
- [x] **1e. DONE 2026-07-30 — raised to 2_000_000.** m5's rejected `verify.py` is
      336,090 bytes of which **326,454 are one gzip+base64 literal** (a 13,591-row
      NHANES cohort) — ~10 kB of actual code; and m11's *working* per-scalar
      producers are 57-62 kB EACH, already 60% of the old cap. Splitting does not
      help: each split still embeds its own slice. The jail (`--network none`,
      `--rm`, memory/cpu/time caps) is what contains model-authored code, not the
      byte count. Error message now says what to do. **Superseded description:**
- [ ] ~~**1e. `MAX_CODE_BYTES = 100_000` refuses legitimate reproducers.**~~
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
