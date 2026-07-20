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
    write_artifacts,
)
from tools.experiment_picker import (
    _spec_fixed_and_sweep,
    analytic_estimate,
    propose_adaptive_points,
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
# No dollar/model-call accounting (out of scope).
#
# RAISED 4 -> 100 (owner instruction 2026-07-20: "make it unlimited, I don't
# care how many tokens I burn"). Set CAMPAIGN_MAX_ITERS to override, and to 0
# for genuinely unbounded — the campaign then runs until the planner stops
# proposing points, which is its real convergence signal.
#
# The default is high-but-finite rather than infinite for one reason, and it is
# not cost: an unterminating campaign never reaches stage 5 or stage 6, so it
# produces no paper at all. A bound is what converts spend into a deliverable.
# 100 is chosen so a fast substrate (cobrapy solves in ~1-2 s) can explore
# freely; on a slow one (a 600 s-timeout CFD case) 100 points is many hours, so
# set CAMPAIGN_MAX_ITERS deliberately there rather than inheriting this.
_DEFAULT_MAX_CAMPAIGN_ITERS = 100


# "Unbounded" is a very large INT, never float("inf"): the budget is passed to
# the planner as budget_remaining and into log lines, and a float there would
# contaminate arithmetic and print as "inf" in evidence. No campaign reaches a
# billion solver points.
UNBOUNDED_ITERS = 10**9


def _resolve_max_iters() -> int:
    """The iteration budget: CAMPAIGN_MAX_ITERS when set (0 => unbounded),
    else the default. Read at import, so a run's budget is fixed for its
    lifetime and cannot drift mid-campaign."""
    raw = os.environ.get("CAMPAIGN_MAX_ITERS", "").strip()
    if not raw:
        return _DEFAULT_MAX_CAMPAIGN_ITERS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CAMPAIGN_ITERS
    return UNBOUNDED_ITERS if value <= 0 else value


MAX_CAMPAIGN_ITERS = _resolve_max_iters()

# The numeric compare tolerance (relative). Pure Python; no model call (D3/T3).
CAMPAIGN_REL_TOL = 0.05

# The strategy socket (D4): a plain dict mirroring the ANALYTIC_ESTIMATORS
# registry idiom. Exactly ONE strategy ships — the existing planner as default.
# A second competing planner would be a ONE-LINE registration here; no judge,
# no tournament ships in this build (out of scope, parallel-later).
DEFAULT_STRATEGY = "propose_next_points"
STRATEGIES = {
    "propose_next_points": propose_next_points,
    # Step 29 feature #1: a deterministic active-learning planner (model-free)
    # that samples where the observed QoI is least resolved. A second competing
    # planner is exactly this one-line registration — no judge, no tournament.
    "adaptive_refine": propose_adaptive_points,
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


def _isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_success_criterion(success_criterion, actual_qoi) -> dict:
    """Step 29 feature #2: evaluate an observation against the spec's
    success_criterion — the FIRST consumer of the two-sided expectation the
    schema has carried unconsumed since Step 15 (stage2_spec._validate_success_
    criterion). Reads the field; never requires it; the locked schema is
    unchanged.

    Returns a record with the single-sided threshold pass AND, when the optional
    two-sided expectation (expected_value ± tolerance) is present, the
    within-band confirmation. `anomaly` is True when a point PASSES the headline
    threshold but falls OUTSIDE the declared expectation band — the
    'passes but 3x-too-high' case the single-sided criterion is blind to (the
    recorded anomaly-blindness watch). Pure Python, never raises, no model call.
    """
    out: dict = {"present": False, "two_sided": False,
                 "meets_threshold": None, "within_expectation": None, "anomaly": False}
    if not isinstance(success_criterion, dict):
        return out
    out["present"] = True
    numeric = _isnum(actual_qoi)
    threshold = success_criterion.get("threshold")
    direction = success_criterion.get("direction")
    out["threshold"] = threshold
    out["direction"] = direction
    if numeric and _isnum(threshold):
        if direction == "above":
            out["meets_threshold"] = actual_qoi >= threshold
        elif direction == "below":
            out["meets_threshold"] = actual_qoi <= threshold
    ev = success_criterion.get("expected_value")
    tol = success_criterion.get("tolerance")
    if _isnum(ev) and _isnum(tol):
        out["two_sided"] = True
        out["expected_value"] = ev
        out["tolerance"] = tol
        if numeric:
            out["within_expectation"] = (ev - tol) <= actual_qoi <= (ev + tol)
    out["anomaly"] = out["meets_threshold"] is True and out["within_expectation"] is False
    return out


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
    synthesis_failures: list = []
    termination_reason: str | None = None

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
                # Step 29 feature #4: a single case-synthesis failure no longer
                # halts the whole campaign. Record the failed point (as evidence
                # and as a signal the planner can avoid), spend the iteration
                # against the budget, and CONTINUE — the same "hit a problem ->
                # remember it -> keep going" idiom crash-recovery uses. Only an
                # all-points-failed campaign ends as halted_synthesis, below.
                failure = {
                    "iteration": index,
                    "point": point,
                    "params": params,
                    "synthesis_error": halt,
                }
                synthesis_failures.append(failure)
                iteration_records.append(failure)
                (campaign_dir / f"iteration_{index}.json").write_text(
                    json.dumps(failure, indent=2, default=str)
                )
                prior_results.append(
                    {
                        "point": point,
                        "qoi_value": None,
                        "qoi_error": None,
                        "converged": False,
                        "synthesis_error": halt,
                    }
                )
                _log_line(
                    run_id,
                    f"CAMPAIGN iter {index}/{MAX_CAMPAIGN_ITERS} synthesis_failed "
                    f"(continuing within budget): {halt}",
                )
                continue

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
            # feature #2: test the observation against the spec's own claim.
            expectation = check_success_criterion(
                spec.get("success_criterion") if isinstance(spec, dict) else None,
                actual_qoi,
            )

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
                "success_criterion_check": expectation,
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
                f"matched={comparison['matched']} ({comparison['reason']}) "
                f"within_expectation={expectation['within_expectation']}"
                + (" ANOMALY" if expectation["anomaly"] else ""),
            )
            # Stop precedence: the spec's OWN two-sided claim (feature #2) is a
            # stronger signal than the planner's self-prediction. A confirmed
            # observation supports the hypothesis at this regime -> stop; else a
            # matched prediction means the surrogate is resolved here -> stop.
            if expectation["two_sided"] and expectation["within_expectation"] is True:
                termination_reason = "expectation_confirmed"
                break
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
    # feature #4: only an all-points-failed campaign is halted_synthesis; a mix
    # of failures and real runs is an honest 'executed' carrying the runs that
    # succeeded (failures are evidence, never fabricated run entries).
    all_failed = bool(synthesis_failures) and not payload_runs
    status = "halted_synthesis" if all_failed else "executed"
    if all_failed and termination_reason in (None, "budget_exhausted", "no_points_proposed"):
        termination_reason = "all_points_failed_synthesis"

    # feature #2: aggregate the hypothesis-confirmation signal for the record.
    within = sum(
        1 for r in iteration_records
        if r.get("success_criterion_check", {}).get("within_expectation") is True
    )
    outside = sum(
        1 for r in iteration_records
        if r.get("success_criterion_check", {}).get("within_expectation") is False
    )
    anomalies = sum(
        1 for r in iteration_records if r.get("success_criterion_check", {}).get("anomaly")
    )
    expectation_summary = {
        "criterion_present": isinstance(spec, dict) and isinstance(spec.get("success_criterion"), dict),
        "two_sided": any(
            r.get("success_criterion_check", {}).get("two_sided") for r in iteration_records
        ),
        "within_expectation": within,
        "outside_expectation": outside,
        "anomalies": anomalies,
    }

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
        "expectation_summary": expectation_summary,
        "synthesis_failures": synthesis_failures,
        "runs": evidence_runs,
    }
    execution_results = {"status": status, "runs": payload_runs}
    if all_failed:
        reason = f"all {len(synthesis_failures)} attempted point(s) failed case synthesis"
        results["reason"] = reason
        execution_results["reason"] = reason
    if qoi_error_fallback is not None:
        results["qoi_translation_error"] = qoi_error_fallback
    if label == "refine":
        results["flag"] = REFINE_FLAG
        execution_results["flag"] = REFINE_FLAG
    # Artifacts out first (same rule as the single-run path): results.json keeps
    # its pinned shape, and every campaign point's measurement stays verifiable.
    write_artifacts(stage_dir, evidence_runs)
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
                "synthesis_failures": len(synthesis_failures),
                "expectation_summary": expectation_summary,
                "iterations": iteration_records,
            },
            indent=2,
            default=str,
        )
    )

    payload = dict(baton.payload)
    payload["execution_results"] = execution_results
    baton.payload = payload

    if all_failed:
        note = (
            f"campaign halted: all {len(synthesis_failures)} attempted point(s) failed "
            f"case synthesis ({termination_reason})"
        )
    else:
        converged = sum(1 for r in payload_runs if r.get("converged"))
        extracted = sum(1 for r in payload_runs if "qoi_value" in r)
        note = (
            f"campaign executed {len(payload_runs)} point(s): {converged} converged, "
            f"{extracted} QoI extracted"
        )
        if synthesis_failures:
            note += f"; {len(synthesis_failures)} failed synthesis"
        if anomalies:
            note += f"; {anomalies} anomaly(ies)"
        note += f"; stop={termination_reason}"
    baton.add_history("stage4_simulation", note)
    return baton
