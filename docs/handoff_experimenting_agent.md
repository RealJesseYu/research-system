# Session prompt — wire verification, then rebuild stage 4 as an experimenting agent

Paste everything below the line into a fresh session, from
`/Users/jesseyu/research-system`.

---

You are working on `research-system`, an autonomous research system: a relay of
six stages (ideation → design → fidelity gate → execution → thought → paper)
coordinated by a deterministic Python supervisor, routing to nine real
scientific instruments (OpenFOAM, ngspice, cobrapy, rdkit, mafft,
homology_search, sympy, two FEA solvers). Read `CLAUDE.md` first — it is long,
it is the architecture, and its invariants are owner-ruled.

**Read before you build. This project has been burned repeatedly by
assert-without-looking, including three times in the session that produced this
handoff.** Anything you are about to declare missing, check for first.

## Where things stand (2026-07-20)

On 2026-07-20 the system underwent an inversion. Until then every stage was a
Claude Code agent with `allowed_tools=[]` and `max_turns=1` — one blind shot, no
lookups, no reacting to results. That was not an oversight; it is what "the
supervisor is deterministic Python", "typed batons, never transcripts" and
"tool output summarized at the wrapper" require. But it was applied to every
stage when it was only ever needed on the path that produces measurements, and
it cost the project its premise.

What changed (commits `d70779b`, `01b82a9`, `3584450`, `7d47a62`, `aa42ae4`):

- `model_call.py` takes a capability profile. `FULL` is a Claude Code agent
  undiminished (browser, shell, files, 200 turns), wired into all 22 ideation,
  reflection, evolution, ranking and design call sites. `SEALED` (the old
  one-shot behavior) remains for stages that JUDGE a measurement.
- `capability_guard.py` denies, in code: reading other stages' transcripts,
  reading calibration answer keys, mutating `memory/` or `runs/`, reading
  credentials. Plus a stage→profile table so a judge cannot be handed tools by
  a future edit.
- `stages/verification.py` re-runs a recorded artifact and compares. **Built,
  tested, and NOT WIRED — it has no caller.**
- A barren-run gate and a desk-rejection screen were added to the supervisor.
- The campaign loop's budget was raised from 4 to 100 (`CAMPAIGN_MAX_ITERS`).

Suite: 1531/1532. The single failure (`test_report_path.MemoryPin`) is
pre-existing journal-md5 drift, unrelated to any of this.

## The insight driving this work

Stage 4 is not the execution step — it is **one measurement**. Take a validated
spec, call a wrapper, return a number. Experimentation is the *loop around*
that: try it, watch it fail, notice the boundary condition is wrong, fix it,
try a nearby point, realize the sweep runs the wrong direction, go again.

The owner's framing, which is correct: *the model call isn't the step; it's a
tool. The step is experimenting.*

The concrete evidence is run `20260720T080610Z`. Three cobrapy runs returned
`input rejected: missing required field(s): model` in 0.0 seconds, and the
system had no capacity to look. An agent at the bench reads that string, opens
`tools/run_cobrapy.py`, finds `MODEL_ALLOWLIST = ("e_coli_core", "iML1515")`,
fixes the value and reruns — real data in under a minute. Instead the run wrote
a paper about its own configuration error. The barren gate added afterwards
kicks the whole run back to stage 2 for full re-authoring: an expensive,
ceremonious repair for a one-field mistake, because the place it should have
been fixed had no eyes.

## Task 1 — wire verification (do this first, it gates task 2)

`stages/verification.py` works: `verify_claim` / `verify_run` re-run an artifact
(`{kind: "code", code, quantity}` or `{kind: "substrate", substrate_id,
typed_input, quantity}`) with deterministic Python, no model in the loop.
Proven: a cobrapy artifact reproduced `0.8739215069684305` exactly; a
fabricated `0.997` against a real ridge-CV artifact was caught at 0.00066
relative error; a value with no artifact was refused as `no_artifact`.

It has no caller because **nothing emits artifacts yet**. That is the work:

1. Stage 4 (and the campaign controller) must record, for every measurement,
   the artifact that regenerates it. For a substrate run that is the routed
   `substrate_id` plus the exact typed input handed to the wrapper — both
   already exist at the dispatch boundary in `tools/substrate_dispatch.py`.
2. Claims reaching the paper must carry `{value, artifact, label}`.
3. The supervisor runs `verify_run` after stage 6 and before the run is
   considered complete, writing `runs/<id>/verification.json`. A run that is
   not `publishable` must say so loudly and must not present its paper as
   standing.

Why first: verification is what makes opening up execution safe. Today nothing
downstream re-checks a number, so sealing the judges is doing that job badly.
Once every claim must survive an independent rerun, an experimenting agent can
do whatever it likes to *get* a number.

## Task 2 — rebuild stage 4 as an experimenting agent

Today `stages/campaign_controller.py` runs `predict → run → compare → replan`
under an iteration budget. The loop is deterministic Python and the only
judgment in it is `propose_next_points(spec, prior_results, budget_remaining)`
— a planner returning coordinates. It can pick *where* to sample. It cannot
decide the boundary condition was wrong, that the QoI should be something else,
that the substrate is a poor fit, or that the interesting result is the failure
it just hit. It is a parameter sweep in an experiment's clothing.

Replace the planner with an agent on `FULL` that runs the bench: reads
diagnostics, inspects wrapper source, repairs its own spec, chooses the next
action, decides when it has enough.

**DO NOT DELETE THE CAMPAIGN LOOP.** See the section below.

### The one hard boundary

Everything an agent needs to *get* a measurement is fair game: reading
diagnostics, reading wrapper source, editing the case, rerunning, writing and
running code, choosing what to try next.

The **instrument read** stays mechanical. When a wrapper returns
`0.8739215069684305`, that value reaches the record untouched by anything that
could rationalize it. An agent that can loop and fiddle and rebuild is right; an
agent that can decide what the solver *meant* is how you get a confidently
wrong measurement. The line is the wrapper return boundary — thin, and not the
whole stage.

Concretely: the agent may call `wrapper_callable(sid)(typed_input)` and may act
on what comes back, but the summary dict is recorded verbatim as evidence and
the QoI is read from it by code, never restated by the model.

### Known costs — surface these, do not silently absorb them

- **Calibration.** `CALIBRATING → MATURE` promotion rests on batteries measuring
  verdict distributions on byte-identical inputs (`--repeats N`, R-REP-1, built
  because the gate returned trust/defer/refine on identical bytes). Four
  substrates are `MATURE` on that basis. Anything that makes an execution-path
  judgment depend on live external state makes those measurements
  non-comparable. Say so; do not quietly invalidate them.
- **Cost accounting.** `cost_meter.record_call` fires once per agentic loop
  regardless of turn count, so a 200-turn call and a 1-turn call both register
  as one "call". Model calls are no longer a cost proxy and there is no turn or
  token cap anywhere. All stage pins are currently `claude-opus-4-8`. An
  experimenting agent in a loop is the highest-spend thing this project has
  ever run. A turn/token cap is probably a prerequisite, not a follow-up.
- **Non-idempotent retry.** Tooled calls do not get transport retry (a failure
  at turn 55 would replay every side effect already committed). If the agent
  loop needs resilience, it needs checkpointing, not blind replay.

## Does the campaign loop get deleted? No.

Most of it is the scaffolding the new design still needs. Keep:

- `run_one_point` (imported from `stage4_simulation`) — per-point execution and
  evidence.
- The stage-4-equivalent contract: ONE consolidated `execution_results`, ONE
  code-authored history entry, so `run_relay`'s snapshot/history/pass-number
  invariants are undisturbed. This is subtle and load-bearing; do not
  re-derive it.
- `compare_prediction` — pure numeric tolerance compare, no model.
- Per-iteration evidence under `runs/<id>/campaign/`, kept OUT of the baton.
- The substrate agreement check, the budget/termination machinery,
  `CampaignDegraded` (which refuses to proceed as silent uniform coverage).
- Its 26 passing tests.

What becomes obsolete is only the assumption that **the spec is fixed and only
coordinates vary**. The `STRATEGIES` dict is already a socket, and its own
comment says a second planner is a one-line registration — but the signature
`(spec, prior_results, budget_remaining) -> {points, predicted_qoi_per_point}`
is too narrow for an agent that may rewrite the spec, change the QoI, or stop.
Widen the socket, register an agentic strategy, keep the deterministic planners
registered beside it. Evolution, not replacement.

## Traps (all of these were hit for real in the originating session)

1. **Assert-without-looking.** "There is no experimentation step" — Step 29
   existed. "There is no code-execution substrate" — `tools/run_code.py`
   existed, registered as `code_sklearn_eval`, `routable=False`, "owner
   decision pending". "The campaign loop isn't built" — it was, and was merely
   switched off by an unset env flag. Check first, every time.
2. **Never `git add -A` or `git add -u`.** The tree carries the owner's own
   uncommitted work. Stage explicit paths.
3. **Fail-open quality gates.** The desk screen's first version returned "pass"
   when the reviewer's reply failed schema — the paper it had correctly
   rejected sailed through. A gate that fails open is not a gate, and
   "unscreened" must never be recorded as "passed".
4. **Guards that only match absolute paths.** `capability_guard`'s first
   matcher used `/memory/` and allowed `Write("memory/journal.jsonl")` — the
   relative form every call site in this repo actually uses.
5. **Regex edits across call sites.** A naive pattern inserted
   `capabilities=FULL` into `_make_extra_validator(...)` instead of
   `call_stage_model(...)`. Use balanced-paren scanning or edit by hand.
6. **Test fakes have signatures.** Widening `call_stage_model` or the transport
   seam breaks every fake written against the old arity — and they raise
   `TypeError` instead of asserting, so a large family of contract tests goes
   silently vacuous. `model_call._seam_accepts_capabilities()` is the pattern
   used to handle this.
7. **Declared budgets must be enforced.** `run_python_experiment`'s `timeout_s`
   was enforced only by an outer subprocess timeout plus 30 s of docker slack,
   so a script declaring 2 s could run 30 and be reported a clean success. A
   declared budget the code does not enforce is a lie told with a number in it.

## Working discipline

Owner-ruled, in `CLAUDE.md`: tested-first, expand only on evidence, no
gold-plating, honest records including what didn't go to plan. Anything that
cannot afford to break goes in code, not a prompt. Runs launch from a plain
Terminal under `caffeinate`, never from a builder session — a run was killed
mid-flight that way once.

Stop and ask the owner before: changing a `CLAUDE.md` invariant, invalidating a
calibration, or anything that would make existing `MATURE` promotions
non-comparable.

## Done looks like

- `verification.json` written for a real run, with real artifacts, and a
  `publishable` flag the supervisor acts on.
- An experimenting agent that, handed run `20260720T080610Z`'s failing cobrapy
  spec, reads the rejection, finds the allowlist, repairs the input, reruns, and
  returns real growth-rate data — without a relay-level loop-back.
- Instrument reads still mechanical: wrapper summaries recorded verbatim, QoI
  read by code.
- Suite green (1531/1532 baseline; the `MemoryPin` failure is pre-existing).
- FAST gate green before any merge.
