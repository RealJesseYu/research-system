# Phase 1 memo — substrate-as-tool + verifiable composition (T1.1 ruling)

Deliverable of Phase 1, Task T1.1 (2026-07-21). Written under the owner's
standing pre-authorization in `docs/next_session_debrief.md` §5/§8: *"write the
design decision down as a recorded ruling before coding."* This is a **builder
ruling, owner-amendable** — it changes the project's direction and so is
recorded, per STOP-and-rule, before any code lands. It touches **no** locked
schema, **no** substrate contract, and **no** CLAUDE.md invariant; it adds an
additive artifact kind and a new deterministic orchestrator, off the baton,
exactly as `stages/verification.py` was added on 2026-07-20.

---

## The question (from the debrief)

Where does a *composed* experiment run, and how do the mature substrates
(`rdkit`, `cobrapy`, …) become callable functions one experiment can invoke,
**with the verifier able to reproduce the composition**? Two candidates:

- **(a)** inside the `python_experiment` sandbox, with the mature wrappers
  exposed as an importable API; or
- **(b)** an orchestrator layer *above* the wrappers that runs the composition
  and calls each wrapper in its own environment, the composition itself being a
  reproducible recipe.

---

## What the investigation found (checked, not assumed)

**F1 — the mature substrates run by `docker exec` from the host.** `run_rdkit`
and `run_cobrapy` (tools/run_rdkit.py, tools/run_cobrapy.py) are already plain
host-side callables that turn a typed input into a job and `docker exec` it into
their own production container (`rdkit-prod`, `cobrapy-prod`), returning the
bounded 4-key scalar summary `{valid, qoi, diagnostics, runtime_s}`. The host
venv never imports rdkit/cobra; the science lives in the container.

**F2 — the `python_experiment` sandbox is network- and daemon-isolated.**
`DOCKER_RUN_FLAGS` (tools/run_python_experiment.py:100) is `--network=none`,
`--read-only`, a size-capped tmpfs, no docker socket, and `code-img` carries no
docker CLI. The sandbox exists *precisely so a result can never depend on the
internet or on host state*. It structurally cannot reach the colima daemon.

**F3 — therefore candidate (a) is architecturally impossible** without demolishing
F2's guarantee. Exposing the wrappers *inside* the sandbox means the sandbox
must `docker exec` into `rdkit-prod`/`cobrapy-prod` — i.e. reach the daemon it is
sealed away from. Docker-in-docker or mounting the socket would give sealed,
model-authored code the ability to start arbitrary containers with arbitrary
mounts: the exact escape the jail set was hardened against. (a) is rejected on
architecture, not preference.

**F4 — verification already re-runs single primitives, off the baton.**
`stages/verification.py` re-executes a `{kind:"code"}` or `{kind:"substrate"}`
artifact with no model and compares within `1e-6`. The artifact is *recorded at
the dispatch boundary* (`tools/substrate_dispatch._dispatch`), so "what ran" and
"what re-runs" are the same object; the scalar is read back through each
substrate's own run-entry constructor (no second opinion). Artifacts live in
`runs/<id>/stage4/artifacts.json` beside `results.json` — a separate evidence
file, no baton/schema change. A composition must *extend this*, not sidestep it.

**F5 — the Jul-20 artifact-channel spike measured a harder, different problem.**
`spike_artifact_channel/REPORT.txt` studied a 2-node *chain* that passes a **file
artifact** (an aligned FASTA) from one substrate to the next. Its findings, which
bound this ruling: (i) **no mature substrate emits a file artifact today** —
making one emit is a large shared cost paid by every option; and (ii) a spec
routes to exactly ONE substrate and a handle can never be a declared spec
parameter, so *stage 2 cannot author a chain and selection cannot route one*
regardless of channel. That spike's subject (file hand-off through the
spec/routing path) is strictly more expensive than what Phase 1 needs and is
**deferred** — see R-COMP-6.

---

## Ruling

**R-COMP-1 — Venue: (b), an orchestrator above the wrappers.** A composed
experiment runs in a **deterministic Python orchestrator that sits above the
wrappers** — same class as the supervisor and the campaign controller: no model
call inside it, ever. It calls each substrate/code step in that step's own
environment (each mature wrapper spawns its own prod container; each code step
its own sealed sandbox). Candidate (a) is rejected on F3. Rationale recorded so
a future reader does not re-open it: the sandbox's network isolation (F2) is a
load-bearing security property, and nesting the wrappers inside it trades that
property for convenience.

**R-COMP-2 — Callable substrates reuse the existing dispatch path; no new
per-substrate API is minted.** A substrate is made callable through the
machinery that already exists and is already verifiable:
`substrate_dispatch.adapter_for(sid)` (or `wrapper_callable(sid)`) to invoke,
and `run_entry_constructor_for(sid)` to read the scalar mechanically. The
orchestrator calls a substrate exactly the way stage 4 and verification already
do, so **every composed step records a re-runnable artifact at the dispatch
boundary by construction** (F4). "Expose rdkit/cobrapy as callable functions"
(debrief T1.2) means *reach them through this path*, not write a second wrapper
API.

**R-COMP-3 — A composition is a typed, model-free recipe of primitive steps.**
A composition is a typed, ordered **recipe** (data, not code) interpreted by the
orchestrator. Each step is one existing primitive artifact — a `substrate` step
`{substrate_id, typed_input, quantity}` or a `code` step `{code, quantity}`.
Model-authored code stays confined to sealed `code` steps; the *wiring* between
steps is typed data. Step-to-step data flow is expressed by **typed references
resolved deterministically by the orchestrator** (a step/combine input names an
upstream step by id; the orchestrator substitutes that step's recorded scalar) —
**never by a model in the loop**. The recipe records the **wiring, not the
intermediate values**, so a re-run re-derives every intermediate. Scalars only:
composition combines the scalar QoIs every wrapper already returns — it does
**not** pass file artifacts between steps (F5, R-COMP-6).

**R-COMP-4 — Verification grows with composition, or the composition does not
ship (the load-bearing constraint).** A new artifact kind **`composition`** is
added to `stages/verification.py`. `rerun_artifact` re-executes the *whole
recipe* deterministically — every substrate step re-invoked through the same
dispatch path, every code step re-run in the same sealed sandbox, references
re-resolved from the *re-run* upstream scalars (never the recorded ones, so a
nondeterministic step is caught, not masked) — and returns the recomputed final
scalar(s); `verify_claim` compares within `rel_tol`. A composition whose recipe
cannot be re-executed end-to-end with no model is **unverifiable and therefore
un-publishable**: no composed number reaches the record unless its recipe
reproduces. **If a genuine composition cannot be made reproducible this way,
STOP and rethink — do not ship an un-verifiable composed number** (debrief §7).

**R-COMP-5 — First brick, and scope discipline (tested-first).** The first
proven composition (T1.2 → T1.3) is the *smallest genuine two-tool* one: two
substrate steps on two different mature substrates, combined by a **sealed
`code` step** that receives the two upstream scalars as injected, deterministic
inputs and computes one final scalar. It is proven end-to-end on one concrete
cross-substrate case (e.g. `rdkit`×`cobrapy`), with a test that (i) runs it,
(ii) re-runs it through the new `composition` verification path and confirms the
final number regenerates within `1e-6`, and (iii) confirms a **perturbed
recorded final value is caught** as a mismatch and a **hardcoded-constant combine
is caught** by the existing tripwire. Deferred to later bricks, on evidence, no
gold-plating: three-plus-step recipes, a step whose *typed input* (not just the
combine) depends on an upstream scalar, a fixed non-code reduction vocabulary
(not built — the code combine is strictly more general), and enrolling a
composition as a routable/gate-1 target (it is a composition *of* substrates, a
layer above the maturity ladder — it stays out of the registry for Phase 1).

**R-COMP-6 — File-artifact hand-off is deferred, distinct from this ruling.**
The Jul-20 spike's subject — a substrate *emitting a file* another consumes,
through the spec/routing path — is **not** Phase 1. Scalar composition (R-COMP-3)
covers the debrief's goal at a fraction of the cost (no wrapper needs to grow a
new emit surface, F5). When a real experiment needs a non-scalar hand-off, that
is its own ruling, informed by the spike's A1/A2/B analysis; it does not block
Phase 1 and Phase 1 does not presume its answer.

---

## What this ruling deliberately does NOT do

- No `schemas.py` change: the composition rides the verification artifact channel
  (F4), not the locked, cumulative baton payload. Same discipline the 2026-07-20
  verification wiring used.
- No `substrate_registry.py` row change and no maturity flip: a composition is a
  layer above the routable ladder, not a substrate.
- No substrate-contract edit and no CLAUDE.md invariant change.
- No model anywhere in the orchestrator or the verifier (verification purity).
- No `git add -A`: only the files this work creates/edits are staged.

## Acceptance for T1.1

The decision is recorded (this memo). The remaining Phase-1 bricks (T1.2 callable
tool composition; T1.3 verified two-tool experiment) build against R-COMP-1..5,
each proven by a test before the next, on the real `rdkit-prod`/`cobrapy-prod`
substrates (both confirmed Up 2026-07-21).
