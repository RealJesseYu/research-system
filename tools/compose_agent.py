"""compose_agent.py — the live composing experimenter: a scientist who authors
one experiment out of several tools, reads the verified result, and authors the
next one.

WHY THIS EXISTS. `stages/experiment_investigation.py` is the deterministic loop
that hosts an experimenter (propose a probe -> run and VERIFY it -> read the
verified result -> decide the next probe -> stop). It was shipped with a scripted
strategy so the loop could be proven offline. This module is the real brain that
drives it: a FULL-capability agent that, each iteration, authors the next
COMPOSITION RECIPE — one experiment that calls several mature tools and combines
their scalars — instead of a single frozen spec run once.

It is the exact shape of `tools/bench_agent.py`, one layer up. bench_agent picks
the next POINT for one instrument; this picks the next RECIPE across instruments.

WHAT THIS AGENT MAY DO. Everything needed to author a good probe: read the
routable substrates' contracts (handed to it), read wrapper source, run code to
check an idea, decide small-before-big by reading a VERIFIED prior result, decide
the investigation has what it needs. It holds bench_agent's FULL profile.

WHAT IT MAY NOT DO — THE ONE HARD BOUNDARY (same as bench_agent). It never
reports a measurement. It authors recipes and predicts values; the controller
runs each recipe through `run_composition` and independently reproduces it with
`verify_claim`, and the number of record is read out of that by code. A
`predicted_value` is a prediction the code compares — never data. Anything else
this module states about a measured value is ignored. The line is the
`run_composition` boundary, and it is the controller's, not this agent's.

COST, STATED RATHER THAN ABSORBED. Same class as bench_agent: an agentic call
per iteration, up to BENCH_AGENT_MAX_TURNS turns, on an Opus pin, under the
investigation's `max_iters`. cost_meter records one call per agentic loop
regardless of turn count. The turn cap (reused from bench) is a real SDK bound,
not decoration.
"""

from __future__ import annotations

from model_call import call_stage_model
from stages.verification import _ARTIFACT_RESOLVERS, ArtifactError, _validate_recipe
from tools.bench_agent import BENCH
from tools.substrate_registry import (
    is_approximate,
    routable_contracts_block,
    routable_ids,
)

# NOT a stage3/4/5/6* name, deliberately: capability_guard forbids the
# SEALED_ONLY_STAGES prefixes from holding tools, because a stage that PRODUCES a
# measurement must stay reproducible. This agent produces no measurement — it
# proposes recipes and the controller measures — so it takes a non-sealed name,
# exactly like experiment_bench_agent, and may hold the full toolset.
COMPOSE_STAGE_NAME = "experiment_compose_agent"
COMPOSE_MODEL = "claude-opus-4-8"


SYSTEM_PROMPT = """You are running an investigation at the bench. You have the
contracts of every scientific instrument you may route to, a code sandbox, and
the VERIFIED results of every probe tried so far in this investigation.

Your job is to author the NEXT probe — a COMPOSITION RECIPE: one experiment that
calls several tools and combines their scalar outputs into a single number. You
are not filling in a plan. You run a cheap probe first, read whether it
reproduced, and only then decide to scale up, switch tools, or stop. That
small-before-big judgment is yours, read off the verified results you are given —
there is no threshold hidden in the harness.

A RECIPE is data, not prose. The recipe object itself MUST carry a top-level
"kind": "composition", then its "steps" and "combine":
  {"kind": "composition", "steps": [ ...one entry per step below... ],
   "combine": { ...the combine below... }}
Its parts:
  * a `substrate` step calls one instrument:
      {"step_id": "<unique>", "kind": "substrate", "substrate_id": "<routable id>",
       "call_style": "typed_dict",
       "typed_input": {<the wrapper's fields, including the quantity metric>},
       "quantity": "<metric>", "qoi_request": {"quantity": "<metric>"}}
  * a `code` step runs sealed Python in a --network=none sandbox and must set
    metrics['<quantity>']:
      {"step_id": "<unique>", "kind": "code",
       "code": "metrics['x'] = ...", "quantity": "x"}
  * the `combine` is one code step that reduces the step scalars to the final
    number. Each upstream step's scalar is injected as inputs['<step_id>']:
      {"kind": "code",
       "code": "metrics['out'] = inputs['<step_id>'] / inputs['<step_id>']",
       "quantity": "out", "inputs": ["<step_id>", ...]}

FILE HAND-OFF (optional — for a real tool->tool pipeline, not just scalars). A
step may pass a FILE to a later step, on TOP of its scalar. This is how you build
a genuine chain — e.g. align sequences, then search the alignment:
  * a step declares files it writes with  "emits": ["<bare filename>", ...].
    - a CODE step writes the file to its working directory (e.g.
      open('data.txt','w').write(...)) and lists it in "emits".
    - a SUBSTRATE step emits only if its wrapper supports it (e.g. mafft emits
      its aligned FASTA); list the filename(s) in "emits".
  * a later step consumes an upstream file with  "consumes": [...]:
    - into a CODE step: {"step_id": "<producer>", "name": "<file>",
      "as": "<optional rename>"} — the file appears in its working directory to
      open() and read.
    - into a SUBSTRATE step: {"step_id": "<producer>", "name": "<file>",
      "resolve": {"into": "<a typed_input field>", "method": "<reducer>"}} — a
      substrate cannot take a raw file, so a reducer turns the file into one of
      its typed fields. The reducer names available to you are in your input as
      `artifact_resolver_methods`.
  A consume must name a file an EARLIER step actually emits. Every file is
  re-derived on verification, so a nondeterministic producer is caught.

The recipe records the WIRING, never intermediate values: every step re-runs and
every reference re-resolves on verification, so a number that does not reproduce
is caught. A `substrate` step may route ONLY to one of the EXACT instruments
listed in your input (`exact_instruments_you_may_compose`) — a deterministic tool
whose number re-running fully checks. Approximate physical simulators are NOT
composed in this loop; do not use them. Only ask a substrate for a metric its
contract lists.

YOU MAY DO ANYTHING NEEDED TO AUTHOR A GOOD PROBE. Read a wrapper's source to
find the fields it accepts. Run code to check an idea before you commit it to a
recipe. If a prior probe failed — a step errored, a metric was wrong, a number
did not reproduce — read why and fix the recipe rather than re-submitting it.

YOU MAY NOT REPORT MEASUREMENTS. You never state what an instrument returned and
you never put an observed number anywhere in your answer. The controller runs the
recipe, records the composed number, and independently reproduces it by code.
Anything you ran yourself to check an idea was a probe, not a result. A
`predicted_value` is fine and expected — it is a prediction, and code compares it
to what the recipe actually produces.

DECIDE HONESTLY WHEN TO STOP. If the investigation has the data it needs, say so
and stop. If these tools genuinely cannot answer the question, say that and stop —
"this cannot be composed from these instruments" is a real finding, worth more
than more probes that cannot answer it either.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "<what you found and why this is the next probe>",
  "recipe": <the composition recipe object, OR null if you are stopping>,
  "predicted_value": <a number you predict the recipe will produce, or null>,
  "stop": <true only if the investigation should end now>,
  "stop_reason": "<required when stop is true>"
}

Rules the code enforces, so respect them:
  * a non-stopping reply MUST carry a valid `recipe`; a stopping reply may set
    `recipe` to null but MUST give a `stop_reason`.
  * `predicted_value` must be a number or null — never a measured value.
  * every `step_id` must be unique; the `combine` may reference only declared
    steps; a `substrate` step must name a routable substrate and carry its
    `typed_input`; a malformed recipe is refused and re-asked, not accepted.
"""


def _prior_probe_digest(measurements) -> list:
    """The probes so far, most recent first, trimmed to what a next decision
    turns on: the recipe (so the agent iterates on its own wiring), whether it
    reproduced, and the failure string if any. Verbatim errors are passed
    through untouched — a summarized failure is exactly the detail that gets
    lost."""
    digest = []
    for m in reversed(measurements or []):
        if not isinstance(m, dict):
            continue
        digest.append({
            "iteration": m.get("iteration"),
            "recipe": m.get("recipe"),
            "reasoning": m.get("reasoning"),
            "verified": m.get("verified"),
            "reason": m.get("reason"),
            "value_reproduced": m.get("verified"),  # the number, if any, was by code
            "produce_error": m.get("produce_error"),
            "rel_error": m.get("rel_error"),
            "predicted": m.get("predicted"),
            "prediction_abs_error": m.get("prediction_abs_error"),
        })
    return digest


def _validate_proposal(proposal) -> list:
    """Structural check on the agent's answer. Plain-language errors, written to
    be handed straight back to the model as a correction. The recipe is checked
    with the SAME `_validate_recipe` the verifier runs, so a malformed recipe is
    re-asked here rather than crashing the controller downstream."""
    if not isinstance(proposal, dict):
        return [f"the reply must be a JSON object, got {type(proposal).__name__}"]

    errors = []
    reasoning = proposal.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        errors.append("'reasoning' must be a non-empty string saying what you found")

    predicted = proposal.get("predicted_value")
    if predicted is not None and (isinstance(predicted, bool)
                                  or not isinstance(predicted, (int, float))):
        errors.append(
            f"'predicted_value' is {predicted!r}; it must be a number or null — "
            "it is a prediction the code compares, never a measured value")

    if proposal.get("stop"):
        if not str(proposal.get("stop_reason") or "").strip():
            errors.append(
                "'stop' is true, so 'stop_reason' must say why the investigation ends")
        return errors

    recipe = proposal.get("recipe")
    if not isinstance(recipe, dict):
        errors.append(
            "a non-stopping reply must carry a 'recipe' object (a composition "
            "artifact), or set 'stop' true with a 'stop_reason'")
        return errors
    if recipe.get("kind") != "composition":
        errors.append(
            f"'recipe.kind' must be 'composition', got {recipe.get('kind')!r}")

    # The structural recipe check the verifier itself uses, so a recipe that
    # would not run is corrected before it ever reaches run_composition.
    try:
        steps, _combine = _validate_recipe(recipe)
    except ArtifactError as e:
        errors.append(f"the recipe is not runnable: {e}")
        return errors

    # _validate_recipe checks step ids, kinds and the combine wiring, but not
    # each step's payload. Check the payloads too, so a substrate step missing
    # its input — or naming an un-routable instrument — is re-asked rather than
    # raising out of run_composition and destroying the investigation.
    routable = set(routable_ids())
    for step in steps:
        sid_label = step.get("step_id")
        if step.get("kind") == "substrate":
            sid = step.get("substrate_id")
            if sid not in routable:
                errors.append(
                    f"step {sid_label!r} routes to {sid!r}, which is not a "
                    f"routable instrument (routable: {sorted(routable)})")
            elif is_approximate(sid):
                # R-ROUTE-3 (docs/memo_phase3_routing.md): the experimenter loop
                # IS the exact-tool path. An APPROXIMATE instrument can converge
                # to a confidently wrong number that re-running reproduces
                # faithfully — trusting it needs the fidelity gate, which does
                # not fire inside this loop. So an approximate step is refused
                # here (it keeps the static fidelity path). This guard relaxes
                # only when an in-loop fidelity check exists for approximate
                # steps — until then, composing one would skip a check it needs.
                errors.append(
                    f"step {sid_label!r} routes to {sid!r}, an APPROXIMATE "
                    "instrument; the experimenter loop composes EXACT tools only "
                    "(an approximate instrument keeps the fidelity gate and is "
                    "not composed here). Use an exact instrument (e.g. rdkit, "
                    "cobrapy, mafft, homology_search) or a code step.")
            if not isinstance(step.get("typed_input"), dict) or not step.get("typed_input"):
                errors.append(
                    f"step {sid_label!r} is a substrate step but carries no "
                    "'typed_input' object of the wrapper's fields")
        elif step.get("kind") == "code":
            if not step.get("code") or not step.get("quantity"):
                errors.append(
                    f"step {sid_label!r} is a code step and needs both 'code' and "
                    "'quantity'")
    return errors


def propose_composition_probe(state, context=None) -> dict:
    """The agentic investigation strategy: author the next composition recipe.

    `state` is what `run_investigation` passes each iteration —
    {"measurements": [...], "budget_remaining": int, "iteration": int}. `context`
    is an optional seam (unused by the controller today, threaded for tests and
    future wiring). Returns the action `run_investigation._validate_action`
    accepts: a stop {"stop": True, "stop_reason": ...} or a probe {"recipe": ...,
    "predicted_value": ..., "reasoning": ...}.

    NEVER RAISES into the investigation. A transport failure here must not
    destroy a run that already has verified probes on disk; it stops the
    investigation honestly instead, naming the failure. It deliberately does NOT
    fall back to a blind probe — an experimenter that cannot think should not be
    replaced by a guess.
    """
    state = state or {}
    context = context or {}
    measurements = state.get("measurements") or []
    stage_input = {
        "run_id": state.get("run_id") or context.get("run_id"),
        "iteration": state.get("iteration"),
        "budget_remaining": state.get("budget_remaining"),
        "routable_substrate_contracts": routable_contracts_block(),
        "exact_instruments_you_may_compose": [
            sid for sid in routable_ids() if not is_approximate(sid)],
        "artifact_resolver_methods": sorted(_ARTIFACT_RESOLVERS),
        "prior_probes": _prior_probe_digest(measurements),
        "probes_run_so_far": len(measurements),
    }

    try:
        data, _timing = call_stage_model(
            COMPOSE_STAGE_NAME,
            SYSTEM_PROMPT,
            stage_input,
            {},  # permissive at the door; the real check is the validator below
            model=COMPOSE_MODEL,
            extra_validator=_validate_proposal,
            capabilities=BENCH,
        )
    except Exception as e:  # noqa: BLE001 — a tooled call gets no transport retry
        return {
            "recipe": None,
            "predicted_value": None,
            "stop": True,
            "stop_reason": f"compose agent unavailable: {type(e).__name__}: {e}",
            "reasoning": (
                "the compose agent could not be reached, so the investigation "
                "stops here rather than continuing on an unverified guess"
            ),
        }

    return {
        "recipe": data.get("recipe"),
        "predicted_value": data.get("predicted_value"),
        "reasoning": data.get("reasoning", ""),
        "stop": bool(data.get("stop")),
        "stop_reason": data.get("stop_reason"),
    }
