# Design — ④.3 de-funnel gate 1 (STOP-and-rule proposal)

**Written:** 2026-07-22 (during the second live director run). **Status:** DESIGN
for owner sign-off — no code written. The last "on rails" piece of step ④.

## The funnel, traced
For every exact-path run today (including each director move):
1. `stage1_ideation.run` (now `quick`) re-forms hypotheses from the domain/question.
2. `gate1_chooser` — ONE Opus call — collapses them to **one** `chosen_hypothesis`
   **and** picks **one** `substrate_id` (`stages/gate1_chooser.py`).
3. `enforce_boundary_schema(validate_payload_post_gate1)` locks the payload to
   `{domain, chosen_hypothesis, substrate_id}` (`supervisor.py:1653`, `schemas.py:60`).
4. `routed_instrument_is_exact(substrate_id)` → `run_exact_route`, whose goal is
   **that one hypothesis' statement** (`run_exact_route`: `goal =
   chosen_hypothesis.statement or domain`).
5. The experimenter investigates **only that one hypothesis**, though it can
   compose multiple exact tools and the director's question was broader.

**The harm:** ideation generates several hypotheses; gate 1 discards all but one;
the experimenter — which can pursue multiple angles across tools — is handed a
single frozen hypothesis. In the director context this is doubly wasteful: the
director already picks the question per move (it IS arc-level ideation), so the
per-move ideation + gate-1 Opus call re-collapse a question the director already
chose.

## The locked constraint (why this is STOP-and-rule)
`POST_GATE1_KEYS = (domain, chosen_hypothesis, substrate_id)` is a **locked
schema** (`schemas.py`; Step 15). Editing its shape is STOP-and-rule and cascades
to the downstream boundary validators.

**Key finding:** we do NOT need to edit it. The post-gate-1 schema is enforced
*after* `apply_gate1_selection`, to protect the payload for **stages 2–5**. The
exact route already **exits before stages 2–5** (`run_exact_route` returns; it
only needs `domain` + a goal + an exact toolset). So a branch that goes to the
experimenter *before* gate 1 simply **never forms that payload** — the locked
schema is untouched (not edited, just not exercised on this path), exactly as the
exact route already skips the stage-2..5 boundary schemas.

## Proposal (recommended): constraint-gated experimenter-direct entry
Add one pre-ideation branch in the supervisor:

> **If the run is constrained to an all-exact substrate set** (the director sets
> `allowed_substrates`, e.g. `rdkit,python_experiment`), **skip ideation + gate 1
> and run the experimenter directly on the domain/question**, composing the full
> allowed exact toolset. Otherwise, the current flow is byte-identical.

- **De-funnels the director path** (where `allowed_substrates` is an exact set):
  the experimenter receives the broad question and self-directs across tools — the
  vision's "endless freedom in HOW."
- **No locked-schema edit** (branches before the post-gate-1 boundary; see above).
- **Standalone `supervisor.py --domain` runs unchanged** when unconstrained or
  mixed — they keep ideation → gate 1 → (exact route | static stages).
- **Removes per-move ideation + gate-1 Opus spend** on the director path.
- **The wall is untouched:** the experimenter still verifies every kept number.

### Decision points for the owner (STOP-and-rule)
1. **Trigger:** gate on "`allowed_substrates` non-empty AND all-exact"? Or a more
   explicit signal (a `--experimenter-direct` flag / a director move kind)?
   Recommend: all-exact constraint — it's already how the director scopes a
   study, needs no new vocabulary, and can't misroute an approximate tool.
2. **Ideation-skip tradeoff:** skipping ideation means the experimenter works from
   the raw question without literature-grounded hypothesis framing. For exact-tool
   computation (descriptors, FBA, alignments) that framing is usually unnecessary,
   and the vision explicitly wants ideation to be an *opt-in tool*, not a
   mandatory stage. But record it as a deliberate loss; a director that wants
   candidate breadth can still dispatch a `full`-ideation move.
3. **Evidence/record shape:** the direct path produces the same routed evidence
   (`investigation.json`, `exact_route_report.md`, and now `verification.json`),
   so the director's read-back (just fixed) works unchanged.

### Alternatives considered (not recommended)
- **B — keep gate 1, leak more context:** gate 1 still picks one hypothesis but
  `run_exact_route` also hands the experimenter the ranked list. Minimal, but a
  half-measure — still pays ideation + gate-1 per move and still frames around one
  hypothesis. Doesn't actually de-funnel.
- **Editing the locked schema** to make `substrate_id`/`chosen_hypothesis`
  optional: unnecessary (see key finding) and a STOP-and-rule cascade. Rejected.

## What this does NOT change
`stages/verification.py` (the wall); cavity byte-identity; the approximate-tool
pipeline (ideation → gate 1 → fidelity gate → stages 2–5); the locked
`schemas.py`. Only the exact/experimenter entry, and only when the run is scoped
to exact tools.

## Sequence when approved
Tested-first: (1) the branch predicate (all-exact constraint) as a pure,
unit-tested helper; (2) the experimenter-direct entry reusing `run_exact_route`'s
investigation with the domain as goal and the allowed set as the toolset; (3)
prove standalone + approximate runs byte-identical; (4) a director-move test that
the arc reaches the experimenter without ideation/gate-1. No schema edit.
