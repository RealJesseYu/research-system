"""
campaign_controller.py — Step 29: the campaign loop.

Within ONE experiment, iterate predict -> run -> compare -> replan under an
ITERATION budget, REUSING the authored spec instead of re-paying stages 1-2 per
adjustment. It lives BESIDE stage 4's single-run path (D1): it invokes
run_one_point N times and produces ONE consolidated stage-4-equivalent result
(one execution_results, one code-authored history note) so run_relay's
per-stage snapshot / history / pass-number invariants are never disturbed — the
controller is NOT nested inside run_relay's stage loop.

Per-iteration campaign detail lives OUTSIDE the baton in runs/<id>/campaign/
(D2). The run-entry and payload schemas are LOCKED — execution_results keeps
its exact {status, runs[, flag][, reason]} shape, never widened to carry
campaign detail.

ZERO model calls in this controller and in compare (D3, T3). The PLANNER (a
STRATEGIES entry) may itself call a model — that is the pluggable planner, not
the execution step; predict (predicted_qoi + analytic_estimate) and compare (a
numeric tolerance) are pure Python here. No LLM ever enters the execution step.

The campaign is OPT-IN (D5): the RESEARCH_CAMPAIGN env flag. With it unset the
default single-run path in stage4_simulation.run stays byte-identical.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from baton import Baton
from stages.stage4_simulation import (
    REFINE_FLAG,
    _log_line,
    extract_parameter_roles,
    run_one_point,
)
from tools.experiment_picker import (
    _spec_fixed_and_sweep,
    analytic_estimate,
    propose_next_points,
)
from tools.qoi_vocab import vocab_for
from tools.substrate_dispatch import (
    adapter_for,
    qoi_translation_for,
    run_entry_constructor_for,
)
from tools.substrate_selection import select_substrate

# The opt-in flag. Default single-run path is byte-identical when it is unset.
CAMPAIGN_ENV = "RESEARCH_CAMPAIGN"

# Budget is ITERATIONS ONLY (P5) — the integer-counter idiom of MAX_LOOPBACKS.
# No dollar/model-call accounting (out of scope). Stays 4 until evidence demands
# otherwise.
MAX_CAMPAIGN_ITERS = 4

# The numeric compare tolerance (relative). Pure Python; no model call (D3/T3).
CAMPAIGN_REL_TOL = 0.05

# The strategy socket (D4): a plain dict mirroring the ANALYTIC_ESTIMATORS
# registry idiom. Exactly ONE strategy ships — the existing planner as default.
# A second competing planner would be a ONE-LINE registration here; no judge,
# no tournament ships in this build (out of scope, parallel-later).
DEFAULT_STRATEGY = "propose_next_points"
STRATEGIES = {
    "propose_next_points": propose_next_points,
}


class CampaignDegraded(RuntimeError):
    """The planner degraded to its silent uniform-coverage fallback. The
    campaign REFUSES to proceed as silent uniform coverage — it surfaces the
    degradation LOUDLY (T5) rather than dressing a fallback as a real plan."""


def campaign_enabled() -> bool:
    """True iff the RESEARCH_CAMPAIGN opt-in flag is set truthy (D5)."""
    return os.environ.get(CAMPAIGN_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def compare_prediction(predicted_qoi, actual_qoi, rel_tol: float = CAMPAIGN_REL_TOL) -> dict:
    """Numeric tolerance compare — pure Python, ZERO model calls (D3/T3).

    Returns {matched: bool, reason} (+ rel_error when a comparison happened).
    A missing prediction or a non-numeric observation is an honest non-match
    (never a fabricated agreement): the campaign keeps exploring.
    """
    if predicted_qoi is None:
        return {"matched": False, "reason": "no_prediction"}
    if isinstance(predicted_qoi, bool) or not isinstance(predicted_qoi, (int, float)):
        return {"matched": False, "reason": "non_numeric_prediction"}
    if isinstance(actual_qoi, bool) or not isinstance(actual_qoi, (int, float)):
        return {"matched": False, "reason": "no_qoi_value"}
    denom = max(abs(actual_qoi), 1e-12)
    rel_error = abs(predicted_qoi - actual_qoi) / denom
    return {"matched": rel_error <= rel_tol, "reason": "compared", "rel_error": rel_error}


def _base_params(spec) -> dict:
    """The authored base point the proposed points override (REUSING the
    authored spec): the first authored mini-run, else the spec's fixed values.
    Pure; never raises on a malformed spec."""
    mini = spec.get("mini_experiment") if isinstance(spec, dict) else None
    runs = mini.get("runs") if isinstance(mini, dict) else None
    if isinstance(runs, list) and runs and isinstance(runs[0], dict):
        return dict(runs[0])
    fixed, _ = _spec_fixed_and_sweep(spec)
    return dict(fixed)


def run_campaign(baton: Baton, strategy_key: str | None = None) -> Baton:
    """The stage-4-equivalent campaign entry. Same verdict gating and same
    consolidated {status, runs} execution_results as the single-run path, built
    from N run_one_point calls under an iteration budget. Returns the baton with
    exactly ONE code-authored history note."""
    verdict = baton.payload["fidelity_verdict"]
    label = verdict["label"]
    run_id = baton.run_id
    stage_dir = Path("runs") / run_id / "stage4"
    stage_dir.mkdir(parents=True, exist_ok=True)
    campaign_dir = Path("runs") / run_id / "campaign"
    campaign_dir.mkdir(parents=True, exist_ok=True)

    if label == "defer":
        # A campaign on a defer verdict executes nothing — the same honest skip
        # the single-run path takes (no case built, no solver run).
        reason = 'fidelity verdict label is "defer" — nothing was executed.'
        results = {"status": "skipped_defer", "reason": reason}
        (stage_dir / "results.json").write_text(json.dumps(results, indent=2))
        payload = dict(baton.payload)
        payload["execution_results"] = {"status": "skipped_defer"}
        baton.payload = payload
        baton.add_history("stage4_simulation", "skipped (defer)")
        _log_line(run_id, "STAGE4 skipped_defer: no case built, no solver run (campaign)")
        (campaign_dir / "summary.json").write_text(
            json.dumps(
                {
                    "status": "skipped_defer",
                    "termination_reason": "defer_verdict",
                    "iterations_used": 0,
                    "iterations": [],
                },
                indent=2,
            )
        )
        return baton

    if label not in ("trust", "refine"):
        raise ValueError(
            f"campaign_controller: unknown fidelity verdict label {label!r} — "
            "expected trust, refine, or defer"
        )

    # --- setup: dispatch hoisted, agreement check ONCE (A1 decision) --------
    # run_one_point takes the resolved substrate/roles/adapter as params and
    # does NOT carry the agreement check; the campaign resolves them here, once,
    # for every iteration.
    spec = baton.payload["experiment_spec"]
    substrate_id = select_substrate(spec)
    carried_id = baton.payload["substrate_id"]
    if substrate_id != carried_id:
        raise RuntimeError(
            f"campaign_controller: substrate agreement check failed — "
            f"spec-derived selection {substrate_id!r} != gate-decided payload "
            f"substrate_id {carried_id!r}; stopping before execution."
        )
    adapter = adapter_for(substrate_id)
    vocab = vocab_for(substrate_id)
    translate = qoi_translation_for(substrate_id)
    entry_constructor = run_entry_constructor_for(substrate_id)
    parameter_roles = extract_parameter_roles(spec.get("parameters"))
    qoi_name = spec.get("qoi", {}).get("name") if isinstance(spec.get("qoi"), dict) else None
    qoi_request, refusal = translate(spec.get("qoi"), vocab)
    qoi_error_fallback = (
        None
        if qoi_request is not None
        else f"QoI {qoi_name!r} not extractable by contract: {refusal}"
    )

    base = _base_params(spec)

    strategy_key = strategy_key or DEFAULT_STRATEGY
    if strategy_key not in STRATEGIES:
        raise KeyError(
            f"campaign_controller: strategy {strategy_key!r} is not registered; "
            f"known strategies: {sorted(STRATEGIES)}"
        )
    strategy = STRATEGIES[strategy_key]

    # --- the bounded loop --------------------------------------------------
    iters_used = 0
    prior_results: list = []
    evidence_runs: list = []
    payload_runs: list = []
    iteration_records: list = []
    termination_reason: str | None = None
    halt_reason: str | None = None

    while iters_used < MAX_CAMPAIGN_ITERS:
        budget_remaining = MAX_CAMPAIGN_ITERS - iters_used
        proposal = strategy(spec, prior_results, budget_remaining)

        # T5: the planner's fallback is a SILENT degradation to uniform
        # coverage (a printed NOTICE only). The campaign surfaces it LOUDLY and
        # refuses to proceed — never a silent uniform-coverage run.
        reasoning = proposal.get("reasoning", "") if isinstance(proposal, dict) else ""
        if isinstance(reasoning, str) and reasoning.startswith("fallback:"):
            raise CampaignDegraded(
                f"campaign planner {strategy_key!r} degraded to its uniform-coverage "
                f"fallback ({reasoning!r}); refusing to proceed as silent uniform "
                "coverage."
            )

        points = proposal.get("points", []) if isinstance(proposal, dict) else []
        predicted_list = (
            proposal.get("predicted_qoi_per_point", []) if isinstance(proposal, dict) else []
        )
        if not points:
            termination_reason = "no_points_proposed"
            break

        for j, point in enumerate(points):
            if iters_used >= MAX_CAMPAIGN_ITERS:
                termination_reason = "budget_exhausted"
                break
            iters_used += 1
            index = iters_used
            params = {**base, **(point if isinstance(point, dict) else {})}
            case_name = f"{run_id}_campaign_iter{index}"

            evidence_run, payload_run, halt = run_one_point(
                run_id,
                index,
                MAX_CAMPAIGN_ITERS,
                params,
                substrate_id=substrate_id,
                adapter=adapter,
                entry_constructor=entry_constructor,
                parameter_roles=parameter_roles,
                qoi_request=qoi_request,
                qoi_error_fallback=qoi_error_fallback,
                case_name=case_name,
            )
            if halt is not None:
                halt_reason = halt
                termination_reason = "halted_synthesis"
                rec = {"iteration": index, "point": point, "params": params, "halt_reason": halt}
                iteration_records.append(rec)
                (campaign_dir / f"iteration_{index}.json").write_text(
                    json.dumps(rec, indent=2, default=str)
                )
                break

            evidence_runs.append(evidence_run)
            payload_runs.append(payload_run)

            # predict: reuse the predicted_qoi machinery (proposer) and the
            # analytic_estimate ladder (cheap-first). compare: numeric only.
            predicted_qoi = (
                predicted_list[j]
                if isinstance(predicted_list, list) and j < len(predicted_list)
                else None
            )
            estimate = analytic_estimate(spec, point if isinstance(point, dict) else {})
            actual_qoi = payload_run.get("qoi_value")
            comparison = compare_prediction(predicted_qoi, actual_qoi)

            rec = {
                "iteration": index,
                "strategy": strategy_key,
                "point": point,
                "params": params,
                "predicted_qoi": predicted_qoi,
                "analytic_estimate": estimate,
                "actual_qoi": actual_qoi,
                "qoi_error": payload_run.get("qoi_error"),
                "converged": payload_run.get("converged"),
                "comparison": comparison,
            }
            iteration_records.append(rec)
            (campaign_dir / f"iteration_{index}.json").write_text(
                json.dumps(rec, indent=2, default=str)
            )
            prior_results.append(
                {
                    "point": point,
                    "qoi_value": actual_qoi,
                    "qoi_error": payload_run.get("qoi_error"),
                    "converged": payload_run.get("converged"),
                }
            )
            _log_line(
                run_id,
                f"CAMPAIGN iter {index}/{MAX_CAMPAIGN_ITERS} strategy={strategy_key} "
                f"matched={comparison['matched']} ({comparison['reason']})",
            )
            if comparison["matched"]:
                termination_reason = "prediction_within_tolerance"
                break

        if termination_reason is not None:
            break

    # Budget is the only remaining stop when nothing else fired — ALWAYS set,
    # never an infinite loop, never a silent stop.
    if termination_reason is None:
        termination_reason = "budget_exhausted"

    # --- consolidate into ONE stage-4-equivalent result --------------------
    status = "halted_synthesis" if halt_reason else "executed"

    # results.json is EVIDENCE (may carry campaign detail); the payload's
    # execution_results is the LOCKED shape and carries NONE of it (D2).
    results = {
        "status": status,
        "verdict_label": label,
        "qoi_request": qoi_request,
        "campaign": True,
        "strategy": strategy_key,
        "termination_reason": termination_reason,
        "iterations_used": iters_used,
        "runs": evidence_runs,
    }
    execution_results = {"status": status, "runs": payload_runs}
    if halt_reason:
        results["reason"] = halt_reason
        execution_results["reason"] = halt_reason
    if qoi_error_fallback is not None:
        results["qoi_translation_error"] = qoi_error_fallback
    if label == "refine":
        results["flag"] = REFINE_FLAG
        execution_results["flag"] = REFINE_FLAG
    (stage_dir / "results.json").write_text(json.dumps(results, indent=2, default=str))

    # The campaign audit trail lives OUTSIDE the baton (D2).
    (campaign_dir / "summary.json").write_text(
        json.dumps(
            {
                "status": status,
                "strategy": strategy_key,
                "budget_max_iters": MAX_CAMPAIGN_ITERS,
                "iterations_used": iters_used,
                "termination_reason": termination_reason,
                "rel_tol": CAMPAIGN_REL_TOL,
                "iterations": iteration_records,
            },
            indent=2,
            default=str,
        )
    )

    payload = dict(baton.payload)
    payload["execution_results"] = execution_results
    baton.payload = payload

    if halt_reason:
        note = (
            f"campaign halted: case synthesis after {iters_used} iteration(s) "
            f"({termination_reason})"
        )
    else:
        converged = sum(1 for r in payload_runs if r.get("converged"))
        extracted = sum(1 for r in payload_runs if "qoi_value" in r)
        note = (
            f"campaign executed {len(payload_runs)} point(s): {converged} converged, "
            f"{extracted} QoI extracted; stop={termination_reason}"
        )
    baton.add_history("stage4_simulation", note)
    return baton
