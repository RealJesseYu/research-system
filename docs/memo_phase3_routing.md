# Phase 3 memo — routing the experimenter into a real run (R-ROUTE ruling)

Deliverable of the collapse plan **manifest §6 step 3** (2026-07-21). Written
under the same standing discipline as `docs/memo_phase1_composition.md`: a
direction-changing decision is **recorded as a ruling before any code lands**
(STOP-and-rule). This is a **builder ruling, owner-amendable** — it proposes how
the live experimenter (built today: `tools/compose_agent.py` driving
`stages/experiment_investigation.py`) stops being a standalone tool and becomes
the spine of a real run for exact tools. Nothing here is committed as code yet;
the owner may amend any R-ROUTE point before the first code brick.

The north star this serves (owner, 2026-07-21): **the agent should pull off full,
complex, multi-part experiments more autonomously than a plain Claude agent.** The
experimenter loop is where that lives; routing it in is what makes a real run
actually use it instead of the static one-shot stages.

---

## The question

Manifest §6 step 3: *"Route the experimenter into the pipeline in place of stages
2–5 for the exact-tool path; keep stage 3 (fidelity) firing only for approximate
instruments."* Two things must be decided before code:

1. **How does a run structurally know a tool is *exact* vs *approximate*?** The
   whole manifest argument (§1–§3) is that the fidelity ceremony earns its keep
   *only* for instruments that can be **confidently wrong** (a CFD-class simulator
   converges to a wrong number and re-running reproduces the wrong number). For a
   code step, a lookup, or a deterministic wrapper, "is this valid here?" is a
   non-question — re-running *is* the check.
2. **Where does the experimenter slot in, without demolishing the working
   pipeline** (cavity's frozen-anchor reproducibility, the approximate path, the
   paper stage, memory)?

---

## What the investigation found (checked, not assumed)

**F1 — there is no exact/approximate marker today.** `SubstrateRecord`
(`tools/substrate_registry.py`) carries `substrate_id, wrapper, card_path,
maturity, routable, cost_tier, notes, frozen_anchor`. **None of these says
whether the instrument is an approximate physical simulator.** The
exact-vs-approximate judgment exists *only* inside the fidelity gate's Opus call
(`stages/stage3_fidelity_gate.py`), decided per-experiment as trust/refine/defer.
So "fire fidelity only for approximate instruments" has **nothing structural to
branch on yet** — that gap is the core of this ruling.

**F2 — the instruments already cluster cleanly into the two classes.** Physical,
approximate simulators: `cavity_2d_cfd` (frozen anchor), `calculix_cantilever_fea`,
`fenicsx_cantilever_elastic`, `sympy`/`scipy` regime cards where they *estimate*.
Exact / deterministic tools: `rdkit`, `cobrapy`, `mafft`, `homology_search`
(the four mature ones), plus the `code`/`python_experiment` sandbox. The classes
are real; only the *label* is missing.

**F3 — the pipeline is a deterministic sequence the supervisor drives.**
`supervisor.py` runs `STAGES = [stage2, stage3, stage4, stage5]` in order, each a
`run(baton) -> baton`, each gated by a locked post-stage schema
(`STAGE_SCHEMAS[2..5]`). Stage 3 is the fidelity gate; stage 4 executes.

**F4 — the loop has already replaced the static measurement once, additively.**
The campaign path (`stages/campaign_controller.py`) already swaps stage 4's
single static measurement for a loop, selected by `CAMPAIGN_STRATEGY` /
`resolve_strategy_key()`, **without deleting the static path** — `bench_agent`
plugs in as a strategy beside the deterministic planners. This is the precedent:
a loop slots in as a *selected path*, the supervisor stays deterministic, and the
old path stays byte-runnable for whatever still needs it.

**F5 — the experimenter already produces the publishable verdict.**
`run_investigation` returns `{measurements, verified, publishable, ...}` where
`publishable` is true only if something ran and everything that ran reproduced —
the exact property stage-4 + the verification pass produce today. Composition and
verification ride an **off-baton** artifact channel (R-COMP: no `schemas.py`
change). So the experimenter's output can reach the paper the same off-baton way,
minimizing locked-schema churn.

---

## Ruling

**R-ROUTE-1 — Add an explicit `instrument_class` to the substrate record; default
to the safe class.** A new field `instrument_class: "exact" | "approximate"` is
added to `SubstrateRecord`, set per substrate by a recorded decision (it is
trust-bearing, so it changes only by ruling — same discipline as `maturity` /
`routable`). **Absence or ambiguity resolves to `approximate`** — the fail-*safe*
direction, because the failure mode we refuse is *skipping* the fidelity gate on
something that needed it. This is a structural fact the run reads, never a name
the code branches on (the substrate-agnostic invariant holds: upper layers read
`instrument_class`, they do not parse `substrate_id`). Rejected alternatives:
inferring the class from the wrapper/category name (fragile, violates
substrate-agnostic); keeping fidelity universal but "cheap" for exact tools (does
not strip the ceremony the manifest says to strip, and still gates a non-question).

**R-ROUTE-2 — The fidelity gate fires iff the routed instrument is
`approximate`.** Stage 3 becomes conditional on `instrument_class`, not
mandatory. For an `exact` instrument the gate is *skipped as a non-question* and
that skip is recorded honestly (a logged "fidelity not applicable: exact
instrument" line + an off-baton note), never silently. For an `approximate`
instrument stage 3 runs **exactly as today**, byte-identical — cavity's path does
not move. The gate's real, narrow value (manifest §1) is preserved precisely
where it exists.

**R-ROUTE-3 — For an exact instrument, the experimenter phase replaces the static
stage-2 authoring + stage-4 single execution.** Instead of stage 2 freezing one
spec and stage 4 running it once, the run enters `run_investigation` driven by
`compose_agent.propose_composition_probe`: author a cheap composition probe → run
+ verify it → read the verified result → scale / switch / stop. This is the
multi-part, multi-tool experiment the north star asks for. The controller keeps
the hard boundary (the agent proposes; `run_composition`/`verify_claim` measure),
so a routed exact run is *more* autonomous without loosening the
propose/measure/verify wall.

**R-ROUTE-4 — The experimenter phase is selected structurally, additively, and
the old path is never deleted.** Selection follows F4's precedent: the run reads
`instrument_class` (and, transitionally, an opt-in env switch so the first
outings are deliberate) and chooses the investigation path for exact tools; the
static stages 2–5 remain registered and runnable for anything not yet migrated.
No `capability_guard` change (the stage is the already-cleared non-sealed
`experiment_compose_agent`). The supervisor stays deterministic — it *selects* a
path, it does not gain a model.

**R-ROUTE-5 — The experimenter's result reaches the paper off-baton where
possible; any unavoidable baton/schema touch is its own recorded sub-ruling.**
`run_investigation`'s summary (`investigation.json`, already written) is the
paper's and memory's input for a routed exact run, mirroring how `verification`
added an off-baton evidence file with no `schemas.py` change (R-COMP, F5). If a
locked post-stage schema genuinely cannot carry the routed shape without a
change, that change **stops and gets its own ruling** — it is not made in passing.

**R-ROUTE-6 — First brick, and scope discipline (tested-first).** The first
routing brick is the *smallest genuine end-to-end exact run*: one mature exact
substrate (`rdkit` or `cobrapy`) routed through the experimenter instead of
static stages 2–4, fidelity skipped-as-non-question per R-ROUTE-2, producing a
verified `publishable` result that the paper stage writes up — proven by a test
that (i) drives it with a **scripted** strategy (no live model — the live outing
is the owner's Terminal job, run-venue rule), (ii) confirms the paper receives
the verified number and not a narrated one, and (iii) confirms the **approximate
path stays byte-identical** (cavity's stage-3 fidelity gate still fires, its
run is unchanged). Deferred on evidence, no gold-plating: migrating the
approximate instruments (they keep the static path by design); wiring the
experimenter into the PI action space (manifest §6 step 5, its own brick);
stripping the contract/calibration/maturity rows for exact tools (manifest §6
step 4, its own ruling — R-ROUTE only removes the *fidelity* ceremony here).

---

## Prerequisite that gates the live proof (not this memo's code)

The experimenter *brain* (`compose_agent.py`) is built and proven offline but has
**never run live** — its prompt "will need iteration against real outings"
(`docs/phase2_handoff.md`). The first-brick **code and its scripted test can land
before** that outing (they do not need a live model), but **trusting a routed
exact run end-to-end does need** the owner's `caffeinate` Terminal outing to
confirm the agent reliably emits valid recipes. Order: this ruling → first-brick
code + scripted test → owner live outing of the experimenter → widen migration.

## What this ruling deliberately does NOT do

- It does not migrate approximate instruments off the static path — they keep the
  fidelity gate and stages 2–5 by design (that is the gate's whole remaining job).
- It does not touch `capability_guard`, `FULL`, or any substrate contract.
- It does not change a locked schema in passing (R-ROUTE-5).
- It does not put a model anywhere in the supervisor or the verifier.
- It does not `git add -A`.

## Acceptance for this memo

The decision is recorded (this file). The first Phase-3 code brick builds against
R-ROUTE-1..6, proven by a scripted-strategy test before anything routes live, on
a real mature exact substrate.
