# Next-session kickoff prompt

Paste everything below the line into a fresh session, from
`/Users/jesseyu/research-system`.

---

We're continuing `research-system`, an autonomous research system. **The vision has
been sharpened and the architecture is mid-collapse. Read
`docs/architecture_collapse_manifest.md` FIRST — it is the single source of truth
for what the system is for, what stays, what goes, and the ordered plan. Do not
re-litigate what it locks.** Then read, in order: `docs/memo_phase1_composition.md`
(the composition ruling, R-COMP-1..6), `docs/phase2_handoff.md` (the next brick in
detail), and `CLAUDE.md` (the long-standing invariants — but note the manifest
**demotes** much of the ceremony there for exact tools; see below).

**This project has been burned by assert-without-looking. Anything you're about to
call missing, check for first.** Much of what sounds unbuilt already exists.

## The one thing the system is for
A researcher that works when you are **not in the room**: unattended, long-horizon,
accumulating toward a goal, where **every kept number can re-prove itself**. It
closes three gaps a chat can't: narration (a reported number nobody computed),
context loss, and no one directing the arc. Every KEEP exists to close those; every
CUT is ceremony that doesn't. Target shape (manifest §4): **ideation-agent →
experimenter-agent → paper, wrapped in memory + a goal-director**, with a thin
propose/measure/verify layer — much closer to "two agents" than to six sealed stages.

## What is already built and committed — DO NOT rebuild (branch `iterate-experiment-loop`)
- **Phase 1 — composition** (`2b8fbb8`): substrates are callable tools one experiment
  composes, verified. `stages/verification.py` has `kind:"composition"` —
  `rerun_artifact` executes a whole recipe recursively so **running == re-running**
  (non-circular). `run_composition(recipe)` + a hardcoded-combine tripwire. A recipe is
  typed, model-free, **off the baton** (no schema/registry change): steps of
  `kind:"code"|"substrate"` + a sealed `code` **combine** that gets upstream scalars
  injected as deterministic `inputs`. Combines **scalars** (every wrapper returns one);
  file hand-off between substrates is deferred (R-COMP-6). Proven on real
  `rdkit`×`cobrapy` (`tests/test_composition.py`, 11 tests).
- **Phase 2 — the experimenter loop** (`964b094`): `stages/experiment_investigation.py`
  — `run_investigation(strategy, *, max_iters, rel_tol, run_id)`. A strategy proposes a
  probe (a composition recipe); the controller **runs and independently verifies** it;
  the verified result feeds the next decision. Proposes-not-measures boundary holds;
  small-before-big is a strategy decision reading a verified result; an un-reproducible
  probe sinks `publishable`. Proven with a scripted strategy
  (`tests/test_experiment_investigation.py`, 6 tests). Deterministic, no model in the loop.
- **Ideation depth-switch** built 2026-07-21 (`stage1_ideation.run(depth=...)`,
  `quick`/`full`); only the "who chooses depth" wiring remains.

## The next brick (manifest §6 step 2 — "the heart"): `tools/compose_agent.py`
The **live experimenter strategy** — the model brain that drives
`experiment_investigation.py`. Build it **as the replacement spine for the exact-tool
path**, not a strategy bolted onto the six stages. Shape it exactly like
`tools/bench_agent.py` (the template):
- Signature `propose_composition_probe(state, context=None) -> action`; `state` is what
  `run_investigation` passes; `action` is what `experiment_investigation._validate_action`
  accepts (`reasoning`, `recipe` | null, `predicted_value`, `stop`, `stop_reason`).
- It authors the next **composition recipe** (schema in `docs/phase2_handoff.md`),
  re-asked in-loop by `verification._validate_recipe` when malformed.
- **No `capability_guard` edit needed**: the guard denies only sealed prefixes
  (`stage3/4/5/6`, `fidelity_case`, `calibration`); name the stage
  `experiment_compose_agent` (non-sealed, like `experiment_bench_agent`) and it may hold
  tools. Reuse `bench_agent.BENCH` (don't mutate `FULL`). Never-raise → stop honestly.
- **Boundary is already enforced** by the controller: the number of record comes from
  `run_composition` + verify; the agent's stated value is ignored, a prediction is only
  compared. Keep it that way.
- **Connectors are now allowed** (manifest §3): the SDK supports `mcp_servers`. Design the
  prompt so the toolbox is *open* (substrates + code sandbox + connectors), even if no
  connector is wired yet — a connector result becomes a substrate the moment it's a
  re-runnable artifact.
- **Prove offline with faked judgment** (patch the transport seam, like the bench/verification
  tests). Then the FIRST LIVE OUTING is a **plain Terminal under `caffeinate`** (run-venue
  rule, absolute) — small (`max_iters=3`); the recipe-authoring prompt WILL need iteration
  against real outings, so expect `RE-ASK` lines. That live iteration is the owner's, not a
  builder-session job.

## Then, in order (manifest §6, each its own recorded ruling — these touch schemas/registry/supervisor)
3. **Route the experimenter in place of stages 2–5** for the exact-tool path; keep the
   fidelity gate firing **only** for approximate physical instruments.
4. **Strip the contract/calibration/maturity ceremony on exact tools** (code, lookups,
   deterministic) — they need only "record it so it re-runs." STOP-and-rule; preserve
   superseded fixtures append-only.
5. **Widen the PI action space** beyond `run_single/run_campaign/stop` so the director can
   dispatch investigations and set ideation depth.
6. **Wire connectors** into a profile once there's a concrete one to use.

## Rules (do not break)
- **Run-venue (absolute):** full/long runs from a plain Terminal under `caffeinate`, never a
  builder-session background task.
- **STOP-and-rule:** contracts, locked schemas, "ruled" inputs → record the decision;
  preserve superseded fixtures append-only.
- **Verification purity:** no model in the verification path.
- **Never `git add -A`** — the tree carries the owner's uncommitted work (memory ledgers,
  `tests/test_campaign_controller.py`, `tests/test_scholar_search.py` are dirty and NOT mine;
  leave them). Stage only files you changed.
- Measurements of record come from a tool/wrapper or the sealed sandbox — never narrated by an
  agent.

## Traps (hit for real before)
1. Assert-without-looking — check every "missing" claim first.
2. Fail-open gates — a gate that fails open is not a gate; "unscreened" must never read as "passed".
3. Test fakes have signatures — widening `call_stage_model` breaks three-arg fakes silently
   (`_seam_accepts_capabilities` / `_strategy_accepts_context` are the introspection idiom).
4. Dense domain-substrate status in always-loaded context was routing the builder model Fable→Opus;
   it's isolated to `docs/status_archive_substrates.md` (opened on demand) — never drag substrate
   promotion narrative back into `CLAUDE.md`/`MEMORY.md`/recalled memories.

## Done looks like
`tools/compose_agent.py` built, faked-tested, call-path proven offline; the recipe schema and
boundary honored; ready for a small live `caffeinate` outing that runs a composed, verified,
multi-tool experiment end-to-end with no human in the chain. Suite green; FAST gate green before
any merge.
