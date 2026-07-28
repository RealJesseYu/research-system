"""
experiment_picker.py — 19-lite experiment picker + analytic cheap-first ladder.

Two independent pieces, both deterministic Python at the seams:

  1. propose_next_points(spec, prior_results, budget_remaining) — ONE model
     call (PICKER_MODEL, pin R-19L-1, this tool only) that proposes the next
     experiment points given the spec and whatever prior results exist. The
     model's reasoning is recorded verbatim in the returned object. The call
     is schema-checked; on a bad reply the picker re-asks ONCE and, if that
     also fails, degrades to a deterministic uniform-coverage fallback with a
     printed NOTICE. It never crashes and NEVER exceeds 2 model attempts
     (initial + one re-ask). The call goes through call_stage_model — the one
     door — with a permissive door-schema so the two-attempt bound is owned
     here, not by the door's own 3-attempt loop; strict shape validation is
     done in this module.

  2. The cheap-first ladder — code, not prompt. Before a picker-proposed
     point is handed to the full solver, an analytic estimator for the spec's
     family (if one is registered) computes a cheap prediction first, attached
     to the point's record as {analytic_estimate, source: "analytic"}. The
     registry is keyed by spec family; a family with no estimator yields an
     honest None (no estimate attached). One estimator ships: the lid-driven-
     cavity Courant + wall-time predictor, grounded in CAVITY_2D_CONTRACT's
     measured per-step range (2.3-4.1 ms/step).

This tool is NOT wired into the supervisor this session — it is built and
tested in isolation.
"""

from __future__ import annotations

from typing import Any

from model_call import FULL, call_stage_model
from models import model_for  # model-tier resolver

# --- R-19L-1: the picker's model pin, this tool ONLY. ------------------------
PICKER_MODEL = model_for("light")
PICKER_STAGE_NAME = "experiment_picker"
# Hard cap on model attempts: initial call + at most one re-ask, then fallback.
PICKER_MAX_ATTEMPTS = 2
# Uniform-coverage fallback density when the model path is abandoned.
DEFAULT_FALLBACK_POINTS = 4

PICKER_SYSTEM_PROMPT = (
    "You are an experiment picker. Given an experiment SPEC (with its swept "
    "and fixed parameters) and any PRIOR_RESULTS already collected, propose "
    "the next few experiment points to run, staying within budget_remaining. "
    "Each point is a JSON object mapping parameter names to numeric values, "
    "using only parameters declared in the spec and keeping swept parameters "
    "inside their declared [min, max]. Prefer points that most reduce "
    "uncertainty about the hypothesis given what prior results already show.\n"
    "Reply with ONLY a JSON object of the form:\n"
    '{"ack_run_id": <echo run_id or null>, '
    '"points": [ {<param>: <number>, ...}, ... ], '
    '"reasoning": "<why these points, in one short paragraph>", '
    '"predicted_qoi_per_point": [<number or null>, ... ]}\n'
    "predicted_qoi_per_point must be the same length as points (one entry per "
    "point; use null when you cannot predict a value). Never propose more "
    "points than budget_remaining."
)


# ---------------------------------------------------------------------------
# Analytic cheap-first ladder
# ---------------------------------------------------------------------------

# Lid-driven-cavity per-step solver rate, the MEASURED range from
# CAVITY_2D_CONTRACT (substrates.py, section 3): 2.3-4.1 ms/step, not a single
# fixed rate. The wall-time predictor spans that range.
CAVITY_MS_PER_STEP_LOW = 2.3
CAVITY_MS_PER_STEP_HIGH = 4.1

# The estimator's required inputs (canonical cavity parameter names).
_CAVITY_ESTIMATOR_INPUTS = (
    "cavity_length",
    "mesh_resolution",
    "lid_velocity",
    "time_step",
    "end_time",
)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def spec_family(spec: Any) -> str | None:
    """Classify the spec into an analytic-ladder family, or None if unknown.

    The lid-driven-cavity signature is the joint presence of lid_velocity and
    cavity_length among the declared parameter names — a fluids spec on any
    other substrate won't carry both. Returns None (honest) for anything else.
    """
    if not isinstance(spec, dict):
        return None
    names = {
        p.get("name")
        for p in spec.get("parameters", [])
        if isinstance(p, dict) and isinstance(p.get("name"), str)
    }
    if {"lid_velocity", "cavity_length"} <= names:
        return "lid_driven_cavity"
    return None


def lid_driven_cavity_estimate(params: dict) -> dict | None:
    """Analytic Courant + wall-time predictor for a lid-driven-cavity point.

    Math (all from the point's own numeric values):
      dx      = cavity_length / mesh_resolution        (uniform N x N mesh)
      courant = lid_velocity * time_step / dx          (advective CFL)
      n_steps = round(end_time / time_step)            (writeInterval = step count)
      wall-time range = n_steps * {2.3, 4.1} ms/step   (measured per-step range)

    Returns None (not an error, just not estimable) if any required input is
    missing or non-numeric, or if a divisor is zero.
    """
    if not isinstance(params, dict):
        return None
    if any(not _is_number(params.get(k)) for k in _CAVITY_ESTIMATOR_INPUTS):
        return None
    cavity_length = params["cavity_length"]
    mesh_resolution = params["mesh_resolution"]
    lid_velocity = params["lid_velocity"]
    time_step = params["time_step"]
    end_time = params["end_time"]
    if mesh_resolution == 0 or time_step == 0:
        return None
    dx = cavity_length / mesh_resolution
    if dx == 0:
        return None
    courant = lid_velocity * time_step / dx
    n_steps = round(end_time / time_step)
    wall_low_s = n_steps * CAVITY_MS_PER_STEP_LOW / 1000.0
    wall_high_s = n_steps * CAVITY_MS_PER_STEP_HIGH / 1000.0
    return {
        "family": "lid_driven_cavity",
        "dx": round(dx, 6),
        "courant": round(courant, 6),
        "n_steps": n_steps,
        "predicted_wall_time_s": {
            "low": round(wall_low_s, 3),
            "high": round(wall_high_s, 3),
        },
        "per_step_ms_range": [CAVITY_MS_PER_STEP_LOW, CAVITY_MS_PER_STEP_HIGH],
    }


# Registry keyed by spec family. A family absent here (value would be missing)
# yields an honest None from analytic_estimate.
ANALYTIC_ESTIMATORS = {
    "lid_driven_cavity": lid_driven_cavity_estimate,
}


def _spec_fixed_and_sweep(spec: Any) -> tuple[dict, dict]:
    """Extract (fixed_values, sweep_ranges) from a spec's parameters list.

    Self-contained and defensive (no import of stage-2 validation): malformed
    entries are skipped rather than raising.
    """
    fixed_values: dict[str, Any] = {}
    sweep_ranges: dict[str, tuple[float, float]] = {}
    if not isinstance(spec, dict):
        return fixed_values, sweep_ranges
    for p in spec.get("parameters", []):
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name:
            continue
        role = p.get("role")
        if role == "fixed" and _is_number(p.get("value")):
            fixed_values[name] = p["value"]
        elif role == "sweep" and _is_number(p.get("min")) and _is_number(p.get("max")):
            fixed_values.pop(name, None)
            sweep_ranges[name] = (p["min"], p["max"])
    return fixed_values, sweep_ranges


def analytic_estimate(spec: Any, point: dict | None) -> dict | None:
    """Cheap-first estimate for one point, or None when no estimator applies.

    Merges the spec's fixed values under the point (the point's own values
    win), then dispatches on spec family. None is honest: either the family is
    unknown or the point lacks a required input.
    """
    est_fn = ANALYTIC_ESTIMATORS.get(spec_family(spec))
    if est_fn is None:
        return None
    fixed, _ = _spec_fixed_and_sweep(spec)
    merged = {**fixed, **(point or {})}
    return est_fn(merged)


def build_point_record(spec: Any, point: dict, predicted_qoi: Any = None) -> dict:
    """Wrap one proposed point into a record, attaching the analytic estimate
    (cheap-first) when one is available. Shape:
      {point, [predicted_qoi], [analytic_estimate, source: "analytic"]}."""
    record: dict[str, Any] = {"point": point}
    if predicted_qoi is not None:
        record["predicted_qoi"] = predicted_qoi
    estimate = analytic_estimate(spec, point)
    if estimate is not None:
        record["analytic_estimate"] = estimate
        record["source"] = "analytic"
    return record


def attach_analytic_estimates(spec: Any, proposal: dict) -> list[dict]:
    """Turn a proposal (points + predicted_qoi_per_point) into point records
    with cheap-first analytic estimates attached where the ladder can help."""
    points = proposal.get("points", []) if isinstance(proposal, dict) else []
    predicted = proposal.get("predicted_qoi_per_point", []) if isinstance(proposal, dict) else []
    records = []
    for i, point in enumerate(points):
        pq = predicted[i] if isinstance(predicted, list) and i < len(predicted) else None
        records.append(build_point_record(spec, point, pq))
    return records


# ---------------------------------------------------------------------------
# The picker (one model call, one re-ask, uniform-coverage fallback)
# ---------------------------------------------------------------------------


def _validate_proposal(data: Any, spec: Any = None) -> list[str]:
    """Strict shape check for a model proposal, AND — when `spec` is given —
    a check that every proposed point stays inside the ranges the spec declared.
    Returns plain-language errors (empty list = valid); the picker owns this,
    not the model-call door.

    THE BOUNDS CHECK WAS PROMPT-ONLY. PICKER_SYSTEM_PROMPT tells the model to use
    only declared parameters and to stay within each swept [min, max], and
    nothing verified it. campaign_controller then merges the point over the
    spec's base parameters and RUNS it — so a point outside the declared sweep
    produced a real measurement of a question the study did not declare, and
    potentially outside the envelope the fidelity gate reasoned about. An
    unknown parameter name fared worse: it was caught only downstream as a case
    -synthesis failure, after the iteration was already spent.

    This is the project's own rule that anything it cannot afford to have broken
    goes in code, not in a prompt. The errors are re-asked through the same
    bounded loop as every other validation failure, so the model gets a chance to
    correct rather than the run being killed.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["proposal must be a JSON object."]
    points = data.get("points")
    if not isinstance(points, list) or not points:
        errors.append("points must be a non-empty list of objects.")
    else:
        for i, pt in enumerate(points):
            if not isinstance(pt, dict) or not pt:
                errors.append(f"points[{i}] must be a non-empty object of parameter values.")
            elif any(not _is_number(v) for v in pt.values()):
                errors.append(f"points[{i}] values must all be numeric.")
    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        errors.append("reasoning must be a non-empty string.")
    pq = data.get("predicted_qoi_per_point")
    if not isinstance(pq, list):
        errors.append("predicted_qoi_per_point must be a list.")
    elif isinstance(points, list) and len(pq) != len(points):
        errors.append(
            f"predicted_qoi_per_point length ({len(pq)}) must equal points length "
            f"({len(points)})."
        )
    elif any(v is not None and not _is_number(v) for v in pq):
        errors.append("predicted_qoi_per_point entries must each be a number or null.")

    if spec is not None and isinstance(points, list):
        fixed, sweep = _spec_fixed_and_sweep(spec)
        known = set(fixed) | set(sweep)
        for i, pt in enumerate(points):
            if not isinstance(pt, dict):
                continue
            for name, value in pt.items():
                if known and name not in known:
                    errors.append(
                        f"points[{i}] names parameter {name!r}, which the spec does "
                        f"not declare (declared: {sorted(known)}).")
                    continue
                bounds = sweep.get(name)
                if bounds is None or not _is_number(value):
                    continue
                lo, hi = bounds
                if not (lo <= float(value) <= hi):
                    errors.append(
                        f"points[{i}] sets {name}={value}, outside the declared "
                        f"sweep range [{lo}, {hi}]. Propose a point inside the "
                        "range the experiment declared — measuring outside it "
                        "answers a question this study did not pose.")
    return errors


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    """n evenly spaced points across [lo, hi] inclusive (n>=1)."""
    if n <= 1:
        return [round((lo + hi) / 2.0, 6)]
    step = (hi - lo) / (n - 1)
    return [round(lo + step * i, 6) for i in range(n)]


def _uniform_coverage_fallback(spec: Any, budget_remaining: Any) -> dict:
    """Deterministic uniform coverage across the spec's sweep ranges, merged
    with fixed values. Returns the same {points, reasoning,
    predicted_qoi_per_point} shape, with predictions left None (honest)."""
    fixed, sweeps = _spec_fixed_and_sweep(spec)
    try:
        budget = int(budget_remaining)
    except (TypeError, ValueError):
        budget = DEFAULT_FALLBACK_POINTS
    n = max(1, min(budget, DEFAULT_FALLBACK_POINTS))
    if not sweeps:
        points = [dict(fixed)]
    else:
        grids = {name: _linspace(lo, hi, n) for name, (lo, hi) in sweeps.items()}
        points = []
        for i in range(n):
            point = dict(fixed)
            for name, grid in grids.items():
                point[name] = grid[i]
            points.append(point)
    return {
        "points": points,
        "reasoning": (
            "fallback: model proposal unavailable; uniform coverage across the "
            "spec's declared sweep ranges (deterministic, no model)."
        ),
        "predicted_qoi_per_point": [None] * len(points),
    }


def propose_next_points(spec: Any, prior_results: Any, budget_remaining: Any) -> dict:
    """Propose the next experiment points. ONE model call, one re-ask on a bad
    reply, then a uniform-coverage fallback (with a printed NOTICE). Never
    crashes; never exceeds PICKER_MAX_ATTEMPTS (2) model attempts.

    Returns {points, reasoning, predicted_qoi_per_point} in every path.
    """
    base_input = {
        "run_id": None,
        "spec": spec,
        "prior_results": prior_results,
        "budget_remaining": budget_remaining,
    }
    last_error: str | None = None
    for attempt in range(1, PICKER_MAX_ATTEMPTS + 1):
        if last_error is None:
            call_input = base_input
        else:
            # Own the re-ask here so the door's 3-attempt loop can't push us
            # past 2 model attempts: a permissive door-schema means the door
            # returns the first parseable reply, and this module re-asks.
            call_input = {"original_input": base_input, "validation_error": last_error}
        try:
            data, _timing = call_stage_model(
                PICKER_STAGE_NAME,
                PICKER_SYSTEM_PROMPT,
                call_input,
                {},  # permissive door-schema; strict validation is done here
                model=PICKER_MODEL,
                capabilities=FULL,
            )
        except Exception as exc:  # transport/parse exhaustion — degrade, never crash
            last_error = f"model call failed: {exc}"
            continue
        errors = _validate_proposal(data, spec)
        if not errors:
            return {
                "points": data["points"],
                "reasoning": data["reasoning"],
                "predicted_qoi_per_point": data["predicted_qoi_per_point"],
            }
        last_error = "; ".join(errors)

    print(
        f"[experiment_picker] NOTICE: model proposal failed after "
        f"{PICKER_MAX_ATTEMPTS} attempts ({last_error}); degrading to "
        f"uniform-coverage fallback."
    )
    return _uniform_coverage_fallback(spec, budget_remaining)


# ---------------------------------------------------------------------------
# Step 29 feature #1: a deterministic active-learning planner for the campaign
# STRATEGIES socket. Same (spec, prior_results, budget_remaining) -> {points,
# reasoning, predicted_qoi_per_point} contract as propose_next_points, so it
# drops into the socket as a one-line registration. ZERO model calls: it fits a
# piecewise-linear surrogate over prior observations and samples where that
# surrogate is least resolved, predicting the sample by linear interpolation —
# a real prediction the campaign's numeric compare then tests (a match means
# the surrogate holds there and the region is resolved). Never raises; never
# emits a 'fallback:'-tagged reasoning (that string is reserved for the silent
# degradation the campaign refuses).
# ---------------------------------------------------------------------------


def _adaptive_result(name: str, x: float, predicted, reasoning: str) -> dict:
    return {
        "points": [{name: x}],
        "reasoning": reasoning,
        "predicted_qoi_per_point": [predicted],
    }


def propose_adaptive_points(spec: Any, prior_results: Any, budget_remaining: Any) -> dict:
    """Active-learning planner: sample where the observed QoI is least resolved.

    Bootstrap samples the two endpoints of the primary sweep range; thereafter
    it proposes the midpoint of the adjacent observed pair with the largest QoI
    change (the least-resolved sub-interval), predicting it by linear
    interpolation. An already-resolved region (the informative midpoint
    coincides with an existing sample) returns no points — an honest, bounded
    stop. Deterministic and model-free.
    """
    fixed, sweep = _spec_fixed_and_sweep(spec)
    try:
        budget = max(int(budget_remaining), 0)
    except (TypeError, ValueError):
        budget = 0
    if budget <= 0 or not sweep:
        return {
            "points": [],
            "reasoning": "adaptive: no declared sweep range or no budget remaining; nothing to propose.",
            "predicted_qoi_per_point": [],
        }

    # Primary sweep parameter, chosen deterministically (first by sorted name).
    name = sorted(sweep)[0]
    raw_lo, raw_hi = sweep[name]
    lo, hi = float(min(raw_lo, raw_hi)), float(max(raw_lo, raw_hi))
    span = hi - lo
    eps = abs(span) * 1e-9 if span else 1e-9

    # Observed (x, y) at this parameter, from prior numeric results only.
    observed: list[tuple[float, float]] = []
    for r in prior_results or []:
        if not isinstance(r, dict):
            continue
        pt = r.get("point")
        x = pt.get(name) if isinstance(pt, dict) else None
        y = r.get("qoi_value")
        if (
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and isinstance(y, (int, float))
            and not isinstance(y, bool)
        ):
            observed.append((float(x), float(y)))
    observed.sort()

    if not observed:
        return _adaptive_result(
            name, lo, None, f"adaptive: bootstrap at sweep '{name}' lower endpoint {lo}."
        )
    if len(observed) == 1:
        x0 = observed[0][0]
        target = hi if abs(x0 - lo) <= abs(x0 - hi) else lo  # the far endpoint
        return _adaptive_result(
            name, target, None, f"adaptive: second endpoint at sweep '{name}' = {target}."
        )

    # >=2 observed: midpoint of the widest-change adjacent sub-interval.
    best = None  # (score, xmid, y_interp)
    for (x1, y1), (x2, y2) in zip(observed, observed[1:]):
        if abs(x2 - x1) <= eps:
            continue
        score = abs(y2 - y1)
        xmid = (x1 + x2) / 2.0
        y_interp = (y1 + y2) / 2.0
        if best is None or score > best[0]:
            best = (score, xmid, y_interp)

    if best is None:
        return {
            "points": [],
            "reasoning": f"adaptive: sweep '{name}' region resolved; no informative midpoint remains.",
            "predicted_qoi_per_point": [],
        }
    _score, xmid, y_interp = best
    return _adaptive_result(
        name,
        xmid,
        y_interp,
        f"adaptive: refining widest-change interval at sweep '{name}' midpoint {xmid} "
        f"(linear prediction {y_interp}).",
    )
