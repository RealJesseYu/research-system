# Substrate Onboarding Recipe (Step 26)

*A walkable checklist for adding a new (substrate, physics-regime) pair to the
system. Each of the seven items cites the real file(s) that already instantiate
it for `cavity_2d`, so a new substrate has a working reference for every step.*

The **card unit is the (substrate, physics-regime) pair** — the same solver in a
different regime (e.g. laminar vs turbulent CFD) is a *different* card and a
*different* onboarding pass. Do not reuse a card across regimes.

Legend for effort tags (used in the worked estimate at the end):
**delegated-day** = mechanical engineering an agent can do in ~a day ·
**judgment-heavy** = needs human/domain expertise · **⚙ run** = consumes real
compute and needs an explicit owner OK before it fires.

---

## 1. Wrap the solver as an MCP tool

Build a deterministic wrapper with: a **typed input**, execution in a **sandbox**
(container), **no LLM anywhere in the execution step**, bounded **retry**, and a
**log-summarizer** that reduces raw solver output down to a small summary —
`{valid/converged, QoI, diagnostics, runtime}` — never the full log.

CFG instantiation:
- `tools/run_cfd.py` — the deterministic wrapper: declares solver/endTime/deltaT
  (never guesses), `docker exec` into `of12-prod`, 600 s hard-kill timeout, parses
  the log to the bounded summary with an explicit converged definition, **full
  log never returned**, optional single-QoI extraction.
- `stages/stage4_case_builder.py` — typed input → concrete case; canonical
  parameter vocabulary, halts loudly by name on anything else.
- `stages/stage4_simulation.py` — the verdict-gated runner (defer → skip,
  trust/refine → execute); no model calls.
- `tools/drive_cfd.py` — the minimal no-AI CLI.
- `tools/pi_gate.py` — the wrapper-side numerics pre-check (Re, duplicate-Re,
  Courant), advisory.

*Note:* "reached over MCP eventually" is an architecture invariant not yet
wired; today the wrapper is a direct Python tool. Onboarding a substrate does
not require MCP first, but the wrapper's shape must be MCP-ready (typed I/O,
summarized output).

## 2. Documentation index (manual + V&V literature)

Index the solver's user manual and its verification-&-validation literature so
retrieval can ground both design and fidelity judgments.

CFD instantiation:
- `retrieval/solver_docs_corpus/` + `retrieval/solver_docs_index.pkl` (built by
  `retrieval/build_solver_docs_index.py`) — the TF-IDF solver-docs index
  graduated from the spike.
- `retrieval/literature_corpus/` + `retrieval/literature_index.pkl` (built by
  `retrieval/build_literature_index.py`) — domain literature.
- `retrieval/tfidf_core.py` — shared TF-IDF core (keep both indices on the same
  vectorizer path; `tests/test_tfidf_drift.py` guards drift).

## 3. Envelope card (hand-authored, provenance-tracked)

Hand-author an envelope card: the honest, disk-cited statement of what the
(substrate, regime) pair can and cannot do. It **must** carry a **provenance
field** with an explicit state — `drafted-by-agent` → `provisionally-signed` →
`expert-reviewed` — and its **unit is the (substrate, physics-regime) pair**.

CFD instantiation:
- `docs/envelope_card_cavity2d.md` — the reference card: §1 Identity, §2
  Provenance (state `provisionally-signed / awaiting-external-review`), §3
  Validated envelope (3A disk-cited / 3B ruled-but-unexercised), §4 Known
  failure modes, §5 what diagnostics can/cannot see, §6 extraction contract
  (verbatim), §7 cost model, §8 resolved questions. Includes the **QoI-screening
  rule** (§6, ruling 2026-07-15: every extremum QoI screened for
  boundary-singularity contamination, not merely contract fit).
- Template: `docs/templates/envelope_card_TEMPLATE.md`.

## 4. Stage-2 spec-schema extension

Teach the experiment-design schema the new substrate's canonical parameter
vocabulary and machine-readable QoI keys, enforced in Python (never in a prompt).

CFD instantiation:
- `stages/stage2_spec.py` — `validate_spec` and the QoI machine-key validators
  (`field` / `operation` / optional `component`); plain-language errors written
  to be re-sent to the model inside the bounded correction loop.
- `substrates.py` `CAVITY_2D_CONTRACT` — the canonical parameter vocabulary and
  extraction contract the schema is grounded against.
- `schemas.py` — the locked baton boundary validators (any schema change here
  requires a recorded ruling).

## 5. Router card + cost tier

Give the router the facts it needs to *choose* this substrate for a hypothesis:
an abstract capability summary (what physics/QoIs it serves) and a **cost tier**,
so the upper layers can route on `{validated envelope, cost, confidence}`
without naming the solver.

CFD instantiation:
- Cost tier: `docs/envelope_card_cavity2d.md` §7 (measured rates) + `substrates.py`
  §3 indicative-cost sentence — the disk-backed cost facts.
- De-facto router today: `stages/stage3_fidelity_gate.py` — the fidelity gate
  emits `right_instrument` (trust/refine/defer + "route to human/real
  experiment"), which is the only routing decision the system currently makes.
- Template: `docs/templates/router_card_TEMPLATE.md`.

*Honest status:* there is **no standalone multi-substrate router yet** — with one
substrate there is nothing to route between. The router card is authored now so
that the second substrate (Step 27) has a real choice to route to; the fidelity
gate's `right_instrument` field is the seam it will plug into.

## 6. Calibration battery (10–20 labeled in/out-of-envelope cases)

Assemble a battery of 10–20 hand-labeled cases spanning clearly-in-envelope,
clearly-out-of-envelope, and edge cases, so the fidelity gate's verdicts can be
scored against known-correct labels.

CFD instantiation:
- `harness/fidelity_case_runner.py` + `harness/triage_battery.py` — the battery
  drivers.
- `harness/triage_cases/` — the labeled fixtures (`1_broken_bc.json`,
  `2_coarse_mesh.json`, `3_genuine_surprise.json`, `4_envelope_drift.json`); this
  set is the seed, to be grown to the 10–20 target.
- `harness/killrate_battery.py`, `harness/validation_batch.py` — related scored
  batteries.
- Template: `docs/templates/calibration_battery_TEMPLATE.md`.

**⚙ Battery *execution* is a real compute run** — it dispatches model calls
and/or solver runs — and needs an **explicit owner OK before it fires**.
Assembling and labeling the cases (this item) is offline; running them to score
the gate is a ⚙ run, gated separately.

## 7. Autonomy earned per substrate

Autonomy is **earned per substrate**, not granted globally. A new substrate
starts with a human at its trust calls and climbs a **maturity ladder** as its
card and calibration accrue; **per-substrate overrides are tracked** so the
ladder is evidence-based.

CFD instantiation:
- Maturity ladder: `docs/reviewer_rubric.md` "Provenance-field update rule" —
  `provisionally-signed` grants *interim* fidelity-gate authority with a human at
  every trust call (the Step-28 hook); FULL standalone grounding authority
  requires Provenance state `signed`.
- Per-substrate override tracking: `memory/override_ledger.jsonl` — every gate's
  model-decision-vs-human-decision recorded (e.g. gate-1 rank-1 overridden in all
  three human runs; gate-2 never overridden — induced Rule 5).
- Reviewer sign-off gate: `docs/reviewer_rubric.md` verdict vocabulary
  (sign-off / sign-off-with-amendments / reject-with-reasons).

---

## Reviewer-rubric pointer

The expert-review lane for the envelope card (item 3) is **not duplicated here.**
Use the existing one-page checklist: **`docs/reviewer_rubric.md`** — the external
domain expert scores each card section PASS/CONCERN/FAIL and writes the
resulting provenance state back into the card's §2. Its template mirror is
`docs/templates/` (the reviewer-rubric pointer file).

---

## Done-when — worked estimate for FEA (CalculiX or FEniCS)

A one-paragraph walk of the checklist for the planned second substrate, a
finite-element structural/mechanics solver (CalculiX or FEniCS), with each item
tagged. **(1) Wrap** — a deterministic wrapper around `ccx`/FEniCS in a
container, typed input, log-summarizer to `{solved/converged, QoI, diagnostics,
runtime}`: **delegated-day** (mirrors `tools/run_cfd.py`; the mesh/solve/extract
cycle is mechanical). **(2) Docs index** — index the CalculiX/FEniCS manual +
FEA V&V literature: **delegated-day** (reuse `retrieval/tfidf_core.py`; corpus
gathering is rote). **(3) Envelope card** — hand-author the FEA card: what
element types, materials, linear-vs-nonlinear regimes, and QoIs (stress/
displacement/eigenfrequency) are validated, and where the mesh/regime edges are:
**judgment-heavy** (needs FEA domain expertise to fence the envelope honestly;
the template gives the skeleton but not the physics). **(4) Stage-2 schema
extension** — add the FEA canonical vocabulary (geometry, material, BC, load,
element size) and its machine QoI keys to `stages/stage2_spec.py`:
**delegated-day** (pattern-follow the cavity_2d extension), with a
**judgment-heavy** slice deciding *which* parameters are canonical vs
builder-halting. **(5) Router card + cost tier** — author the FEA capability
summary and measure a cost tier: **delegated-day** to draft, but the cost-tier
numbers require a **⚙ run** to measure. **(6) Calibration battery** — assemble
10–20 labeled in/out-of-envelope FEA cases: **judgment-heavy** to label
correctly; **⚙ run** to *execute* the battery and score the gate (explicit owner
OK required). **(7) Autonomy earned** — the FEA substrate starts
`drafted-by-agent`, a human sits at every trust call, and it climbs the ladder
only as its card is expert-reviewed and its override ledger accrues:
**judgment-heavy** and time-gated, not a one-session deliverable. **Net:** the
wrap/index/schema/router-draft work is delegated-day mechanical; the
envelope-card physics, battery labeling, and autonomy graduation are the
judgment-heavy critical path; and the cost-tier measurement + battery execution
are the ⚙ runs that need an owner's go-ahead before they fire.
