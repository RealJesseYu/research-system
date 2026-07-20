# Verification wired; stage 4 rebuilt as an experimenting agent (2026-07-20)

Commits `c810087` (task 1), `023a301` (task 2), `d9b8830` (call-path proof), on
branch `scratch-testrun-0719`.

Suite 1584 passed / 1 failed / 1 skipped. The single failure is
`test_report_path.MemoryPin`, pre-existing journal-md5 drift, untouched by this
work (baseline at session start: 1530 passed, same single failure). FAST GREEN:
hard-gate 3/3, zero watch misses, rejects 0/6, ledger 0/0, exit 0.

---

## Task 1 — verification wired

`stages/verification.py` had no caller because nothing emitted artifacts.

**The emitter is the dispatch boundary.** `tools/substrate_dispatch._dispatch`
records the invocation and then makes it, so "what was recorded" and "what was
run" are the same object by construction. Reconstructing the artifact later from
a spec would have been a second copy of the translation logic, free to drift
from the one that actually ran.

Two call styles, because the substrates genuinely differ:

* `typed_dict` — the wrapper takes one typed dict (ngspice, sympy, the
  cantilevers, the threaded bio four). Re-running is calling the wrapper.
* `case_build` — cavity. The case is synthesized *above* the wrapper call, so
  re-running the wrapper against the case left on disk would re-read a case
  rather than regenerate it, and would reproduce a bad build as faithfully as a
  good one. Regeneration re-invokes the adapter into a `_verify` case name, so
  the original run's evidence is never overwritten.

**Harvesting is clear-then-take** in `run_one_point`, the single per-point
chokepoint stage 4, the campaign and the chain runner all share. A point that
halts before reaching a wrapper takes `None` and is recorded as `unrecorded`
rather than inheriting the previous point's artifact.

**Artifacts live in their own evidence file.** `results.json` is byte-identity
pinned for cavity (`tests/fixtures/d4/expected_results.json`) and re-verified at
every substrate wave. An additive key there would have broken a pin that exists
to catch exactly the kind of quiet drift this build could introduce, so
`artifacts.json` sits beside it and the pin was left alone — both cavity fixture
tests still pass unmodified.

**Claims are rebuilt from evidence**, joined on `run_index`, with the value read
through the substrate's own run-entry constructor. That constructor is the code
that read the original measurement; a second, simpler reader in `verification.py`
would have been a second opinion about what the instrument said. It also matters
concretely — cavity returns `{value: ...}`, the cantilevers return a dict of
named numbers the request selects from, and homology_search's clean no-hit is a
`None` that is a result rather than a failure.

**The supervisor gate FAILS CLOSED.** `run_verification_pass` runs after stage 6
on both paper-producing exits, writes `runs/<id>/verification.json`, logs the
verdict loudly, and stamps it into the `run_record` through the non-payload
attribute channel `_maturity_signoff` and `_barren_diagnosis` already use. If the
pass itself breaks, the run is **not** publishable: an unverified paper must
never be recorded as a verified one. The distinction between "checked and failed"
and "could not be checked" survives in the reason, because they call for
different responses — but neither lets a paper stand.

Claims do **not** ride the baton. The payload schema is locked and cumulative, so
a key added at one boundary is required at every later one; evidence on disk
needed no ruling.

Proven against real instruments: a cobrapy growth rate
(`0.8769972144269406`) and an rdkit `MolWt` (`46.069`) reproduced exactly, a
fabricated `99.9` caught as a mismatch, a bare number refused as `no_artifact`.

## Task 2 — the experimenting agent

`tools/bench_agent.py`, registered as `bench_agent` **beside**
`propose_next_points` and `adaptive_refine`, both untouched. The campaign loop,
`run_one_point`, the stage-4-equivalent contract, `compare_prediction`, the
evidence layout, the agreement check and `CampaignDegraded` all survive.

**The socket widened by introspection, not by arity.** The three positional
arguments never move; richer context is offered only to strategies whose
signature asks for it (`_strategy_accepts_context`, the idiom `model_call` uses
for its transport seam). Widening the call would have made every three-argument
test fake raise `TypeError` instead of asserting, silently vacating a whole
family of contract tests. All 51 existing campaign and picker tests pass
unmodified.

**A repaired spec faces the real locked validator** and the R-23.5-4 agreement
check re-runs on every revision. An agent may repair an experiment; it may not
re-route it to a different instrument, and it may not edit its way out of the
schema that makes its output checkable. A refused revision leaves the previous
spec in force and is recorded in `spec_revisions`.

**The hard boundary holds.** The agent proposes; the controller measures. The
wrapper summary is recorded verbatim and the QoI read from it by code. A test
drives an agent that confidently predicts `999.0`; the record keeps the
instrument's own number and the prediction stays a prediction, compared
numerically.

### A real gap fixed on the way

The campaign path never received the regime-input threading the single-run path
got on 2026-07-20, so a campaign on a threaded substrate reproduced run
`20260720T080610Z`'s rejection exactly — `model` sat in the regime block and
never reached the wrapper. `_resolve_for_spec` now threads it, under each point's
own params so a swept value always wins.

### The acceptance case

Handed run `20260720T080610Z`'s actual spec (frozen at
`tests/fixtures/bench/cobrapy_failing_spec.json`, and it still passes
`validate_spec` today — it was a correctly authored spec with one bad value):

1. point 1 rejected: `model 'iJO1366' is not a baked allowlist model (allowed:
   e_coli_core, iML1515)`
2. the agent reads that diagnostic and the wrapper source, repairs `regime.model`
3. point 2 solves: growth rate `0.8769972144269406`
4. one consolidated `execution_results`, one history note, **no relay-level
   loop-back**
5. the measurement carries an artifact; `verify_run` reproduced it;
   `publishable: true`

---

## Costs, surfaced rather than absorbed

* **Calibration is NOT invalidated.** The batteries measure the *fidelity gate*
  (stage 3) on byte-identical inputs; nothing here touches stage 3. The default
  stage-4 path is unchanged in output — proven, not asserted, by the two cavity
  fixture tests (`expected_results.json` and `expected_execution_results.json`)
  passing unmodified. The campaign is opt-in behind `RESEARCH_CAMPAIGN`, and the
  agentic strategy additionally requires being selected by key; the default
  strategy is still `propose_next_points`. The four `MATURE` promotions stay
  comparable.
* **A real turn cap exists.** `BENCH` is its own capability profile —
  `FULL`'s tools, `BENCH_AGENT_MAX_TURNS` turns, default **40**, against `FULL`'s
  200-turn backstop. It is passed to the SDK as the enforced cap, not printed
  somewhere: a declared budget the code does not enforce is a lie told with a
  number in it. `FULL` itself is not mutated (a test pins it at 200).
* **Model-call counts are no longer a cost proxy on this path.**
  `cost_meter.record_call` fires once per agentic loop regardless of turn count.
  A campaign at the default budget of 100 iterations is up to 100 Opus agentic
  calls of up to 40 turns each. **Set `CAMPAIGN_MAX_ITERS` deliberately before
  any live outing.**
* **No transport retry, by design.** A tooled call is not idempotent, so
  `model_call` gives it zero retries. The bench agent therefore catches its own
  transport failures and stops the campaign honestly rather than falling back to
  uniform coverage — a bench agent that cannot think must not be silently
  replaced by a sweep.

## Disclosed asterisks

1. **The bench agent has never made a live model call.** Its judgment is faked in
   every test. The *call path* is proven with only the transport seam patched —
   capability guard, transcript-before-call, and the validator's re-ask loop all
   run for real — but no real Opus outing has happened. Per the absolute
   run-venue rule, that outing must launch from a plain Terminal under
   `caffeinate`, never from a builder session. Suggested first outing, small on
   purpose:
   ```
   caffeinate -i env RESEARCH_CAMPAIGN=1 CAMPAIGN_STRATEGY=bench_agent \
     CAMPAIGN_MAX_ITERS=4 venv/bin/python3 supervisor.py --mode human
   ```
   Selection is by `CAMPAIGN_STRATEGY`, the same opt-in idiom as
   `RESEARCH_CAMPAIGN` — added because without it the agentic strategy sat
   registered in the socket and reachable from no real run
   (`stage4_simulation.run` passes no strategy argument), which is precisely how
   the campaign loop itself once sat dormant behind an unset flag. Default is
   unchanged; an unknown name raises rather than silently delivering a sweep.
2. **`chain_runner` measurements are not verified.** It calls `run_one_point`, so
   its evidence now carries artifacts, but `claims_from_run` reads only
   `stage4/{results,artifacts}.json` — chain node records are not collected.
   Left unbuilt rather than guessed at.
3. **`test_chain_runner.TestT1EraHolds`** compares the frozen surface against
   `git diff HEAD`, so it went red while task 1 was uncommitted and green on
   commit. It pins uncommitted drift, not the era.
4. **Only cobrapy and rdkit were exercised live.** The `case_build` (cavity)
   verification path is unit-tested but has not re-run a real OpenFOAM case; that
   path costs up to 600 s per point and was not worth a live outing to prove
   plumbing that the typed-dict path already exercises.
5. **`stages/verification.py` still has no `rel_tol` policy per substrate.** A
   genuinely nondeterministic instrument would fail verification rather than be
   reported as nondeterministic. That is the intended behavior for now — the
   verdict travels with the claim and the author decides — but it will need a
   ruling the first time a legitimately stochastic substrate is enrolled.
