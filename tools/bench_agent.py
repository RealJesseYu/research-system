"""bench_agent.py — the experimenting agent: a scientist at the bench, not a
coordinate picker.

WHY THIS EXISTS. Stage 4 was never the execution step; it was ONE MEASUREMENT.
Take a validated spec, call a wrapper, return a number. Experimentation is the
loop AROUND that: try it, watch it fail, notice the boundary condition is wrong,
fix it, try a nearby point, realize the sweep runs the wrong direction, go again.
The campaign loop supplied the loop but not the judgment — its planner could
choose WHERE to sample and nothing else. It could not decide that the boundary
condition was wrong, that the QoI should be something else, that the substrate
is a poor fit, or that the interesting result is the failure it just hit.

Run 20260720T080610Z is the concrete case. Three cobrapy runs returned
"input rejected: missing required field(s): model" in 0.0 seconds and the system
had no capacity to look. An agent at the bench reads that string, opens
tools/run_cobrapy.py, finds MODEL_ALLOWLIST, fixes the value and reruns — real
data in under a minute. Instead the run wrote a paper about its own
configuration error.

WHAT THIS AGENT MAY DO. Everything needed to GET a measurement: read the
diagnostics, read wrapper source, run code, search, repair its own spec, choose
what to try next, decide it has enough. It holds the FULL capability profile.

WHAT IT MAY NOT DO — THE ONE HARD BOUNDARY. It never reports a measurement.
It proposes points and repairs; the controller executes them through
run_one_point, the wrapper summary is recorded verbatim, and the QoI is read out
of that summary by code. An agent that can loop and fiddle and rebuild is right;
an agent that can decide what the solver MEANT is how you get a confidently
wrong measurement. The line is the wrapper return boundary — thin, and not the
whole stage. Nothing this module returns is ever treated as data.

COST, STATED RATHER THAN ABSORBED. This is the highest-spend thing the project
runs: an agentic call per iteration, each up to BENCH_AGENT_MAX_TURNS turns, on
an Opus pin, under a campaign budget of 100 iterations by default. cost_meter
records one "call" per agentic loop regardless of turn count, so model-call
counts are NO LONGER a cost proxy for this path. The turn cap below is a real
bound, deliberately lower than FULL's 200-turn backstop, because a bench agent
that needs forty turns to place one point is not converging.
"""

from __future__ import annotations

import os

from model_call import FULL, Capabilities, call_stage_model

# NOT a stage4* name, deliberately and necessarily: capability_guard forbids any
# stage whose name begins with "stage4" from holding tools, because a stage that
# PRODUCES a measurement must stay reproducible. This agent does not produce
# measurements — it proposes what to measure, and the controller measures. That
# distinction is the whole argument for letting it roam, so the name records it.
BENCH_STAGE_NAME = "experiment_bench_agent"
BENCH_MODEL = "claude-opus-4-8"


def _max_turns() -> int:
    """The per-call turn ceiling. Configurable, defaulted low.

    A declared budget the code does not enforce is a lie told with a number in
    it, so this is passed to the SDK as the real cap rather than printed
    somewhere. 40 turns is enough to read a diagnostic, open two wrapper files,
    try something in a shell and answer; a bench agent still going at turn 40 is
    not converging on a point and should be spending the campaign's next
    iteration instead.
    """
    raw = os.environ.get("BENCH_AGENT_MAX_TURNS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return 40


# A capability profile of its own: FULL's tools, a tighter turn ceiling. Built
# here rather than mutating FULL, which is frozen by convention precisely so one
# stage cannot silently widen another's powers.
BENCH = Capabilities("bench", FULL.allowed_tools, _max_turns())


SYSTEM_PROMPT = """You are running an experiment at the bench. You have a
validated experiment spec, a routed scientific instrument, and the results of
every point tried so far in this campaign — including the ones that failed.

Your job is to decide what to do NEXT so that this experiment produces real
data. You are not filling in a sweep. You are the person who notices that the
run failed for a stupid reason, finds out why, fixes it, and gets the
measurement.

YOU MAY DO ANYTHING NEEDED TO GET A MEASUREMENT. Read the instrument wrapper's
source to find out what inputs it actually accepts (the wrapper path is given
below). Read its allowlists and its validation. Run code to check an idea. Search
if that helps. If a point failed because a field was missing, or a value was not
in an allowlist, or a unit was wrong, FIND THE REAL CONSTRAINT AND REPAIR THE
SPEC — do not propose the same broken point again with different coordinates.

YOU MAY NOT REPORT MEASUREMENTS. You never state what the instrument returned
and you never put an observed value anywhere in your answer. The controller runs
the points you propose, records the wrapper's summary verbatim, and reads the
number out of it by code. If you ran something yourself to check an idea, that
was a probe, not a result: it does not go in your answer as data. A predicted
value is fine and expected — it is a prediction, and code compares it to what
the instrument actually returns.

DECIDE HONESTLY WHEN TO STOP. If the campaign has the data it needs, say so and
stop. If the instrument genuinely cannot test this hypothesis, say that and stop
— "this substrate cannot answer this question" is a real finding, and much more
useful than twenty more points that cannot answer it either. A failure you
understand is a result; a failure you paper over is not.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "<what you found and why you are doing this next>",
  "points": [{"<parameter>": <number>}, ...],
  "predicted_qoi_per_point": [<number or null>, ...],
  "revised_spec": <the full corrected spec object, ONLY if you are repairing it>,
  "stop": <true only if the campaign should end now>,
  "stop_reason": "<required when stop is true>"
}

Rules the code enforces, so respect them:
  * points and predicted_qoi_per_point must be the SAME LENGTH.
  * every value inside a point must be a number.
  * when stopping, points may be empty; otherwise propose at least one.
  * "reasoning" must NOT begin with "fallback:" — that string is reserved for a
    degraded planner and will abort the campaign.
  * revised_spec must be the COMPLETE spec object, not a patch: it is re-validated
    against the locked schema, and a revision that does not validate is refused
    and logged, leaving the previous spec in force.
"""


def _diagnostic_digest(prior_results) -> list:
    """The failures so far, verbatim, most recent first.

    This is the input the whole design turns on: the wrapper's own diagnostic
    string is what tells an agent that `model` was missing or that a value was
    not in an allowlist. It is passed through untouched — a summarized
    diagnostic is exactly the detail that gets lost.
    """
    digest = []
    for entry in reversed(prior_results or []):
        if not isinstance(entry, dict):
            continue
        problem = entry.get("qoi_error") or entry.get("synthesis_error")
        if problem:
            digest.append({"point": entry.get("point"), "problem": problem})
    return digest


def _validate_proposal(proposal) -> list:
    """Structural check on the agent's answer. Plain-language errors, written to
    be handed straight back to the model as a correction."""
    errors = []
    if not isinstance(proposal, dict):
        return [f"the reply must be a JSON object, got {type(proposal).__name__}"]

    reasoning = proposal.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        errors.append("'reasoning' must be a non-empty string saying what you found")
    elif reasoning.startswith("fallback:"):
        errors.append(
            "'reasoning' may not begin with 'fallback:' — that prefix is reserved "
            "for a degraded planner and aborts the campaign")

    stopping = bool(proposal.get("stop"))
    if stopping and not str(proposal.get("stop_reason") or "").strip():
        errors.append("'stop' is true, so 'stop_reason' must say why the campaign ends")

    points = proposal.get("points")
    if points is None:
        points = []
    if not isinstance(points, list):
        errors.append("'points' must be a list of objects")
        return errors
    if not points and not stopping:
        errors.append(
            "'points' is empty but 'stop' is not true — either propose a point to "
            "try or stop honestly and say why")
    for i, point in enumerate(points):
        if not isinstance(point, dict) or not point:
            errors.append(f"point {i + 1} must be a non-empty object of parameter values")
            continue
        for name, value in point.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(
                    f"point {i + 1} sets {name!r} to {value!r}; point values must be "
                    "numbers (a categorical instrument selector belongs in the "
                    "spec's regime block, so repair the spec instead)")

    predicted = proposal.get("predicted_qoi_per_point")
    if predicted is None:
        predicted = []
    if not isinstance(predicted, list):
        errors.append("'predicted_qoi_per_point' must be a list")
    elif len(predicted) != len(points):
        errors.append(
            f"'predicted_qoi_per_point' has {len(predicted)} entries but there are "
            f"{len(points)} points — they are read positionally and must match")
    else:
        for i, value in enumerate(predicted):
            if value is not None and (isinstance(value, bool)
                                      or not isinstance(value, (int, float))):
                errors.append(
                    f"prediction {i + 1} is {value!r}; each entry must be a number "
                    "or null")

    if "revised_spec" in proposal and proposal["revised_spec"] is not None:
        if not isinstance(proposal["revised_spec"], dict):
            errors.append("'revised_spec' must be the complete spec object, or absent")
    return errors


def propose_bench_actions(spec, prior_results, budget_remaining, context=None) -> dict:
    """The agentic campaign strategy.

    Signature is the deterministic planners' three positional arguments plus an
    OPTIONAL `context` keyword. The controller inspects the signature and passes
    context only to strategies that accept it, so the existing planners — and
    every test fake written against the three-argument form — are untouched.

    Returns the planner contract {points, reasoning, predicted_qoi_per_point},
    optionally widened with {revised_spec, stop, stop_reason}.

    NEVER RAISES into the campaign. A transport failure here must not destroy a
    run that already has real measurements on disk; it stops the campaign
    honestly instead, naming the failure. It deliberately does NOT fall back to
    uniform coverage: the campaign refuses silent uniform coverage by design, and
    a bench agent that cannot think should not be replaced by a sweep pretending
    it did.
    """
    context = context or {}
    stage_input = {
        "experiment_spec": spec,
        "substrate_id": context.get("substrate_id"),
        "instrument_wrapper_source_path": context.get("wrapper_path"),
        "translated_qoi_request": context.get("qoi_request"),
        "qoi_translation_error": context.get("qoi_error"),
        "regime_inputs_threaded_to_instrument": context.get("regime_inputs"),
        "iteration": context.get("iteration"),
        "budget_remaining": budget_remaining,
        "prior_results": prior_results,
        "failures_so_far": _diagnostic_digest(prior_results),
    }

    try:
        data, _timing = call_stage_model(
            BENCH_STAGE_NAME,
            SYSTEM_PROMPT,
            stage_input,
            {},  # permissive at the door; the real check is the validator below
            model=BENCH_MODEL,
            extra_validator=_validate_proposal,
            capabilities=BENCH,
        )
    except Exception as e:  # noqa: BLE001 — a tooled call gets no transport retry
        return {
            "points": [],
            "predicted_qoi_per_point": [],
            "stop": True,
            "stop_reason": f"bench agent unavailable: {type(e).__name__}: {e}",
            "reasoning": (
                "the bench agent could not be reached, so the campaign stops here "
                "rather than continuing as an unguided sweep"
            ),
        }

    return {
        "points": data.get("points") or [],
        "predicted_qoi_per_point": data.get("predicted_qoi_per_point") or [],
        "reasoning": data.get("reasoning", ""),
        "revised_spec": data.get("revised_spec"),
        "stop": bool(data.get("stop")),
        "stop_reason": data.get("stop_reason"),
    }
