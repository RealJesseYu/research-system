"""experiment_investigation.py — an investigation loop over VERIFIED compositions.

Phase 2, T2.1/T2.2/T2.3 scaffolding (docs/next_session_debrief.md §5;
docs/memo_phase1_composition.md is the Phase-1 primitive this builds on).

WHAT THIS IS. The single-run pipeline authors one static spec and runs it once.
An experimenter does not work that way: it runs a cheap probe, reads the result,
and decides the next probe — scale up, try a different tool, or stop — a real
investigation, not a fixed plan. This is the deterministic loop that hosts that:
a strategy proposes the next probe, the controller EXECUTES AND VERIFIES it, and
the verified result feeds the strategy's next decision.

A probe is a COMPOSITION RECIPE (Phase 1): one experiment that calls several
tools and combines their scalars. So an investigation is naturally multi-tool,
and "small before big" is the strategy authoring a cheap recipe first and a
bigger one only once the cheap one reads as promising — an emergent decision
from reading a verified result, never a hardcoded threshold in here.

THE ONE HARD BOUNDARY (same as bench_agent). The strategy PROPOSES; the
controller MEASURES. A measurement of record is produced by run_composition and
independently reproduced by verify_claim — read out by code, never stated by the
strategy. The strategy may predict a value (a prediction is compared, not
recorded as data); any observed value it puts in its action is ignored. Nothing
the strategy returns is ever treated as a measurement.

VERIFICATION IS THE GATE. Each probe is verified inline (so the strategy sees a
reproduced result, not a bare one), and a probe that does not reproduce end-to-
end is recorded as unverified and contributes NO trusted number — un-verifiable
is un-publishable, exactly as for a single artifact. No model anywhere in this
module: it is deterministic Python that calls the verifier, like the supervisor
and the campaign controller.
"""

from __future__ import annotations

import json
from pathlib import Path

from stages.verification import (
    DEFAULT_REL_TOL,
    run_composition,
    verify_claim,
)


class InvestigationError(ValueError):
    """The strategy's proposed action is not a runnable probe."""


def _validate_action(action) -> dict:
    """Structural check on a strategy's action, or raise. Plain-language errors,
    written to be handed straight back to a model as a correction (the
    bench_agent idiom).

    An action is either a STOP or a PROBE:
      {"stop": True, "stop_reason": "..."}                  — end the investigation
      {"recipe": <composition artifact>, "predicted_value": <number|None>,
       "reasoning": "..."}                                  — run this probe next
    """
    if not isinstance(action, dict):
        raise InvestigationError(
            f"the action must be an object, got {type(action).__name__}")
    if action.get("stop"):
        if not str(action.get("stop_reason") or "").strip():
            raise InvestigationError(
                "'stop' is true, so 'stop_reason' must say why the investigation ends")
        return {"stop": True, "stop_reason": action["stop_reason"],
                "reasoning": action.get("reasoning", "")}

    recipe = action.get("recipe")
    if not isinstance(recipe, dict) or recipe.get("kind") != "composition":
        raise InvestigationError(
            "a non-stopping action must carry a 'recipe' that is a composition "
            "artifact (kind='composition'); the controller runs and verifies it")
    predicted = action.get("predicted_value")
    if predicted is not None and (isinstance(predicted, bool)
                                  or not isinstance(predicted, (int, float))):
        raise InvestigationError(
            f"'predicted_value' is {predicted!r}; it must be a number or null — "
            "it is a prediction the code compares, never the measurement")
    return {"stop": False, "recipe": recipe, "predicted_value": predicted,
            "reasoning": action.get("reasoning", "")}


def _measure(recipe: dict, predicted, rel_tol: float) -> dict:
    """Run one probe and independently verify it. The value is produced by
    run_composition and reproduced by verify_claim; the strategy's prediction
    (if any) is compared, never substituted. Returns the measurement record."""
    produced = run_composition(recipe)
    verdict = verify_claim({"value": produced["value"], "artifact": recipe},
                           rel_tol=rel_tol)
    record = {
        "recipe": recipe,
        "value": produced["value"],          # the instrument's number, by code
        "intermediates": produced.get("steps"),
        "verified": bool(verdict.get("verified")),
        "reason": verdict.get("reason"),
        "reproduced": verdict.get("reproduced"),
        "rel_error": verdict.get("rel_error"),
        "predicted": predicted,
        "produce_error": produced.get("error"),
    }
    if (predicted is not None and record["value"] is not None):
        record["prediction_abs_error"] = abs(predicted - record["value"])
    return record


def run_investigation(strategy, *, max_iters: int = 8,
                      rel_tol: float = DEFAULT_REL_TOL,
                      run_id: str = None, goal: str = None) -> dict:
    """Drive an investigation: strategy proposes probes, the controller runs and
    verifies each, verified results feed the next decision. Deterministic; no
    model in this loop (the strategy may hold one — that is its business, and its
    proposals are still only measured here).

    `strategy(state) -> action` is called each iteration with
    state = {"measurements": [...], "budget_remaining": int, "iteration": int,
             "goal": <the research question or None>}.
    It returns a stop action or a probe action (see _validate_action).

    `goal` is the research question the investigation pursues (R-DIR-1). When a
    director dispatches an investigation it names the question here; a standalone
    probe leaves it None and the experimenter self-directs.

    Returns a summary with the measurements and a `publishable` flag that is true
    only when at least one probe ran and every probe that ran reproduced — an
    investigation resting on an unreproducible number does not stand.
    """
    measurements = []
    stop_reason = None
    stopped_by_budget = False

    for iteration in range(max_iters):
        state = {
            "measurements": measurements,
            "budget_remaining": max_iters - iteration,
            "iteration": iteration,
            "goal": goal,
        }
        action = _validate_action(strategy(state))
        if action["stop"]:
            stop_reason = action["stop_reason"]
            break
        record = _measure(action["recipe"], action["predicted_value"], rel_tol)
        record["iteration"] = iteration
        record["reasoning"] = action["reasoning"]
        measurements.append(record)
    else:
        stopped_by_budget = True
        stop_reason = f"reached the {max_iters}-iteration budget"

    verified = [m for m in measurements if m["verified"]]
    summary = {
        "iterations": len(measurements),
        "measurements": measurements,
        "verified": len(verified),
        "total": len(measurements),
        # publishable mirrors verify_run: something ran, and everything that ran
        # reproduced. A probe that failed to verify sinks the whole run's claim
        # to standing, exactly as one bad claim sinks a single-artifact paper.
        "publishable": bool(measurements) and len(verified) == len(measurements),
        "stopped_by_budget": stopped_by_budget,
        "stop_reason": stop_reason,
    }
    if not measurements:
        summary["note"] = (
            "the investigation ran no probes — there is nothing to stand on")

    if run_id:
        run_dir = Path("runs") / str(run_id)
        if run_dir.is_dir():
            (run_dir / "investigation.json").write_text(json.dumps(summary, indent=2))
    return summary
