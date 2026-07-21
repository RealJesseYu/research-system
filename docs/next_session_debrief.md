# Debrief & Task List — Next Claude Code Session

**Written:** 2026-07-21, end of a long working session.
**Theme for next time:** make the **experimentation phase work like a human experimenter** —
substrates become *tools you call*, one experiment can *compose several of them*, and the
system runs *small probes before big runs because that's logical*, not because it's hardcoded.

---

## 1. Where we are (what this session built)

The prior arc of this session took the system from "defers nearly every time / can't run"
to a **complete, verified, autonomous experiment run**. Seven commits, all tested:

1. `iterate_experiment` — an author→run→diagnose→re-author loop (the experiment can fix its own code).
2. Stage 2 wired to it — a `python_experiment` spec's code is run at authoring time; a failure
   feeds the container's real diagnostic back and the model rewrites its code.
3. Verification rejects **hardcoded** numbers — reproduction alone passed `metrics['x']=0.99`;
   a model-free AST tripwire now catches a metric that is only ever a compile-time constant.
4. **Transport fix** — tool-bearing (`FULL`) model calls crashed on `can_use_tool requires
   streaming mode`; they now stream the single turn. This had been blocking *every* live run.
5. + 6. `python_experiment` contract corrected — it had told the model to "write to a result
   path" (wrong: the harness gives it a `metrics` dict) and omitted two spec-grammar rules
   (no parameters; metric name goes in `qoi.quantity`). After the fixes the model authored a
   valid, runnable spec **first try, zero re-asks**.
7. Memory-bleed fix — the paper stage fed the *global* journal's recent learned_summaries into
   every section, so a cobrapy note bled into a Random Forest paper. The paper now uses only
   **this run's own** thought summary.

**Proven end-to-end** (run `fullchain-20260721T130413Z`, driven downstream from an
autonomously-authored spec): fidelity gate → **trust**; stage 4 → executed, `cv_accuracy =
0.9774603174603176`; verification → **1/1 reproduced, rel_error 0.0, publishable=True**;
stage 6 → an 8.4 KB paper. No human in that chain.

---

## 2. The architecture reality (read this before designing anything)

- **One experiment = one substrate, chosen at gate 1.** `substrate_id` is decided once and rides
  the payload; stage 2 designs for it, stage 4 runs it, the result is **one scalar QoI**. The
  system **cannot**, within a single experimentation phase, search a database *and* run
  simulation A *and* run simulation B *and* combine them. Each is a separate run on a separate
  substrate. **Everything still surrounds the substrate.**
- **`python_experiment` is the one crack in that wall** — inside it, caller-authored code can chain
  numpy/scipy/sklearn/etc. and report one number. But it is **sealed** (`--network=none`),
  **one-shot**, and returns **one scalar**. It is a sandbox, not yet a composition surface.
- **Verification = reproduction.** `stages/verification.py` re-runs an artifact (code or substrate)
  with no model and checks the number regenerates within `1e-6`. It handles one artifact at a time.
  It is deliberately model-free ("no second opinion").
- **Autonomy is bounded.** Given a hypothesis, the system autonomously designs/judges/runs/verifies/
  writes. It does **not** pick its own hypothesis or domain, and the PI ("boss", `pi_agent/`) still
  has a **3-move action space**: `run_single`, `run_campaign`, `stop`. Each move is one whole pipeline
  run on one substrate.
- **Three capability tiers** (`model_call.py`): `FULL` = a real Claude Code agent (WebSearch, Read,
  Write, Bash, … 200 turns) — used by the *creators* (ideation, stage 2, PI); `SEALED` = one blind
  reply, no tools — used by the *judges* (fidelity gate, thought layer, paper); and **no model at all**
  (deterministic Python) for *measuring* (stage 4, case building, verification, the wrappers).

---

## 3. The vision for next (owner's words)

> "I need the experimentation step as like how a human would experiment: using simulations as
> tools, running smaller-scale experiments before running big ones — not because it's in the code,
> but because that's what is logical and that's what I would do. Composing multiple tools in the
> same experimentation phase."

Decoded into three capabilities the system does **not** have today:

1. **Substrates as tools, not as the experiment.** One experiment can *call* rdkit, then cobrapy,
   then a simulation, then combine — instead of each being an isolated one-substrate run.
2. **An agentic experimentation phase.** Today the "experiment" is a static spec authored once and
   run once. Human-like experimenting means an agent *in the loop during execution*: run a probe,
   read the (verified) result, decide the next probe, scale up, stop — a real investigation, not a
   fixed plan.
3. **Small-before-big by judgment.** The experimenter runs a cheap version first and only scales
   when the cheap result is promising — an emergent decision from reading intermediate results,
   never a hardcoded `if`.

---

## 4. The gap (why the current architecture can't do §3)

- The experiment is a **static artifact** (`spec` authored by stage 2, executed once by stage 4).
  There is no agent *inside* execution that can observe a result and choose the next action.
- Substrates are **routing targets**, not **callable functions** — there is no API by which one
  experiment's code (or an experimenter agent) can invoke another substrate mid-experiment.
- Verification reproduces **one artifact**. A composed, multi-step investigation has no single
  artifact to re-run, so today it could not be verified — and un-verifiable = un-publishable by
  design. **This is the load-bearing constraint: composition and verification must grow together.**

---

## 5. Task list for next session (ordered; Phase 1 is the session's focus)

### Phase 1 — Substrate-as-tool + verifiable composition (do this first)
- **T1.1 — Design decision (write it down before coding).** Where does a composed experiment run,
  and how do substrates become callable? Two candidates:
  (a) inside the `python_experiment` sandbox, with the mature wrappers exposed as an importable API
  (watch: nested containers / network — the sandbox is `--network=none`); or
  (b) an orchestrator layer *above* the wrappers that runs the composition and calls each wrapper
  in its own environment. Pick one, record the ruling (the project rules changes, doesn't just make
  them — see §7). Likely (b) for the container/network reasons, with the composition itself being a
  reproducible recipe.
- **T1.2 — A callable tool API.** Expose 2–3 mature substrates (start with the pure-Python ones —
  `rdkit`, `cobrapy`) as functions an experiment can call, each returning a typed scalar the same way
  the wrappers already do. No new science; just make "call a substrate" a first-class in-experiment action.
- **T1.3 — Verify a two-tool experiment.** Extend `stages/verification.py` so it can reproduce a
  *composition* (a recorded recipe of tool calls) and confirm the final number(s) regenerate. Prove
  it on one concrete two-substrate experiment end-to-end. **If this can't be made reproducible, stop
  and rethink — do not ship an un-verifiable composed result.**

### Phase 2 — Agentic experimenter (small-before-big by judgment)
- **T2.1 — An experimenter agent** (`FULL` capability) that, given a hypothesis + a toolbox, runs a
  cheap probe, reads its *verified* result, and decides the next action (bigger run, different tool,
  stop). This replaces "author one static spec, run once" with an investigation loop. Each *measurement
  of record* must still be a reproducible artifact routed through the verifiable wrapper path — the
  agent orchestrates, it never produces a number itself (same boundary the PI has).
- **T2.2 — Staging logic** emerges from the agent reading intermediate results (cost/scale reasoning),
  not from hardcoded thresholds.
- **T2.3 — Verify a staged, multi-step investigation** (extends T1.3 to a sequence/graph).

### Carry-forward (not Phase 1/2, but track them)
- The PI's action space is still 3 moves — widening it is the top-of-pipeline analogue of T2.1.
- The full pipeline has **not** been run from a blank prompt (ideation included) end-to-end on a real
  Terminal since these fixes — worth doing to see gate-1 route to `python_experiment` on its own.
- Harder domains (the robot/protein dream) are the same architecture extended — don't start there.

---

## 6. Key files
- `tools/run_python_experiment.py` — the sealed code sandbox (the composition seed).
- `tools/iterate_experiment.py` — the author→run→diagnose→re-author loop.
- `tools/substrate_dispatch.py`, `tools/substrate_registry.py` — how substrates route today.
- `stages/stage2_experiment_design.py` — authors the spec; runs the code at authoring time.
- `stages/stage4_simulation.py` — executes; writes `results.json` + `artifacts.json`.
- `stages/verification.py` — reproduction-based checker (the thing to extend for composition).
- `pi_agent/` — the PI (decider.py = the 3-move action space).
- `substrates.py` — the contracts (per-substrate prose shown to the model).

## 7. Rules to respect (the project's own discipline)
- **Run-venue rule (absolute):** launch any *full/long supervised run* from a plain Terminal under
  `caffeinate`, **never** from a builder-session background task (it can be orphaned and lost). Short
  in-session stage drivers that finish in minutes are fine.
- **STOP-and-rule:** changing a contract, a locked schema, or a "ruled" input is a decision to record,
  not just make. Preserve superseded fixtures append-only (`*_pre<change>.txt`).
- **Verification purity:** no model inside the verification path — it holds no second opinion.
- **Never `git add -A`** — stage only the files you changed. Runs/ and cases_/ are gitignored evidence.
- Measurements of record come from a substrate/wrapper (deterministic) or the sealed sandbox — never
  narrated by an agent.

---

## 8. Ready-to-paste prompt for the next session

> We're continuing the autonomous research system. Read `docs/next_session_debrief.md` first — it has
> the full state, the architecture reality, and the plan. This session's goal is **Phase 1: make
> substrates callable tools that one experiment can compose, with the verifier able to reproduce the
> composition.** Start with **T1.1**: investigate where a composed experiment should run (sandbox vs
> an orchestrator above the wrappers) and how the mature substrates (`rdkit`, `cobrapy`) become
> callable functions — then write the design decision down as a recorded ruling before coding.
> Respect the project rules in §7 (run-venue, STOP-and-rule, verification purity, never `git add -A`).
> The load-bearing constraint: **composition and verification grow together** — if a composed result
> can't be independently reproduced, stop and rethink rather than ship an un-verifiable number.
> Move one brick at a time and prove each with a test before the next.
