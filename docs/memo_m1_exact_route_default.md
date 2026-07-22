# Ruling M1 — the exact route is default-on

**Date:** 2026-07-21. **Branch:** `iterate-experiment-loop`.
**Authorized by:** owner ("go ahead m1"), on the Phase-A audit
(`docs/audit_cut_list.md`) and the collapse plan
(`docs/plan_collapse_and_simplify.md` §M1).
**Class:** trust-bearing routing-default change → STOP-and-rule (this memo is
the recorded decision).

## Decision
`exact_route_active()` flips from **default-off** (`EXACT_ROUTE==1` required) to
**default-on** with a kill-switch: the exact-tool experimenter path fires for
any run whose gate-1 instrument is EXACT, **unless** `EXACT_ROUTE=0` is set to
force the legacy static pipeline.

New semantics: `os.environ.get("EXACT_ROUTE", "1") != "0"`.
- unset → True (route active)
- `EXACT_ROUTE=1` → True (explicit, unchanged)
- `EXACT_ROUTE=0` → False (transition kill-switch / legacy static path)

## Why now
- The caution the flag was guarding — "validate the live experimenter from a
  Terminal before it is the default" (`supervisor.py:131-138`) — has been met:
  the first `caffeinate` outing of the experimenter passed (3/3 probes verified,
  publishable; plan §4), and the owner ran the exact-route capstone explicitly
  under `EXACT_ROUTE=1`.
- This is the single lever that retires the runtime ceremony (fidelity gate,
  both substrate-agreement checks, static stage-2 spec authoring, the maturity
  hook) for the five exact tools **without deleting any shared static-pipeline
  code** — audit §0 move M1. The ceremony becomes dead code for exact tools; its
  deletion is a later, separate Bucket-1 step.

## Blast radius (traced, not asserted)
- Only `supervisor.py` and `tests/test_exact_route_supervisor.py` read the flag
  (`grep EXACT_ROUTE`); no harness, no `main()` branch, no FAST/killrate gate
  depends on it.
- The branch still requires BOTH `exact_route_active()` AND
  `routed_instrument_is_exact(baton)`. `routed_instrument_is_exact` returns
  False for approximate / missing / unknown `substrate_id`, so **the approximate
  path is untouched**: cavity/calculix/fenicsx keep static stages 2-5 + the
  fidelity gate, byte-identical.
- All four `run_relay` test drivers except the exact-route test inject
  `substrate_id="cavity_2d_cfd"` (approximate) → unaffected by the flip.
- Verification wall (`stages/verification.py`) and cavity byte-identity:
  untouched.

## Kept escape hatch (deliberate, transitional)
The `EXACT_ROUTE=0` kill-switch is retained for the transition — a one-line
rollback to the legacy static path for exact tools if the live experimenter
misbehaves. Deleting the flag entirely (route purely on `instrument_class`) is a
thinner Phase-C move, made once the default-on path has more live mileage.

## Rollback
`export EXACT_ROUTE=0` restores the pre-M1 behavior exactly (static stages 2-5 +
fidelity gate for exact tools too).
