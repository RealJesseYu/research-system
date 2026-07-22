"""experiment_route.py — the EXACT-tool experiment path (Phase 3, R-ROUTE-2/3).

docs/memo_phase3_routing.md. For an exact-tool investigation the fidelity gate is
a NON-QUESTION: re-running a deterministic tool IS the check, so there is no
"is this valid here?" for a gate to ask (manifest §1). Instead of the static
stages 2–5 plus a fidelity gate, such a run enters the experimenter loop directly
— author a cheap composition probe, run + verify it, read the verified result,
decide the next probe.

This is the deterministic seam that (a) RECORDS the fidelity skip honestly — the
skip is a decision on the record, never silent (R-ROUTE-2) — and (b) hosts
run_investigation. No model here: the strategy holds the model (compose_agent in
production, a scripted strategy in tests); this module records the routing and
calls the loop, exactly like the supervisor is deterministic Python around the
stages.

The experimenter's exact-only boundary (R-ROUTE-3) is enforced upstream at the
recipe boundary (tools/compose_agent._validate_proposal): a composition step may
route only to an EXACT instrument, so the fidelity skip this module records is
justified for every probe the loop actually runs — an approximate instrument is
refused before it can be measured, and keeps the static fidelity path.

Wiring this into the production supervisor loop (selecting this path for an exact
run, in place of stages 2–5) is the next brick and is gated on the experimenter's
first live outing (run-venue rule) — this seam is built and proven standalone
first, the way Phase 1 and Phase 2 were.
"""

from __future__ import annotations

import json
from pathlib import Path

from stages.experiment_investigation import run_investigation
from stages.verification import DEFAULT_REL_TOL


def _fidelity_skip_record() -> dict:
    """The honest record of WHY the fidelity gate did not fire. R-ROUTE-2: the
    skip is a decision on the record, not an omission."""
    return {
        "applies": False,
        "instrument_class": "exact",
        "reason": (
            "exact-tool investigation: re-running a deterministic tool IS the "
            "check, so the fidelity gate is a non-question and is skipped "
            "honestly (R-ROUTE-2). The experimenter composes EXACT tools only "
            "(R-ROUTE-3), enforced at the recipe boundary, so every probe the "
            "loop runs is one reproduction fully validates."
        ),
    }


def run_exact_investigation(strategy, *, max_iters: int = 8,
                            rel_tol: float = DEFAULT_REL_TOL,
                            run_id: str = None, goal: str = None) -> dict:
    """Drive an exact-tool investigation: record the fidelity skip, then host the
    experimenter loop. Deterministic; no model in this function.

    Returns {fidelity, investigation, publishable} where `investigation` is
    run_investigation's summary and `publishable` mirrors it (something ran and
    everything that ran reproduced). When `run_id` names an existing run dir, the
    fidelity-skip record is written to runs/<id>/fidelity_route.json so the skip
    is durable evidence, never only an in-memory value.
    """
    fidelity = _fidelity_skip_record()
    if run_id:
        run_dir = Path("runs") / str(run_id)
        if run_dir.is_dir():
            (run_dir / "fidelity_route.json").write_text(json.dumps(fidelity, indent=2))

    summary = run_investigation(strategy, max_iters=max_iters, rel_tol=rel_tol,
                                run_id=run_id, goal=goal)
    return {
        "fidelity": fidelity,
        "investigation": summary,
        "publishable": summary["publishable"],
    }
