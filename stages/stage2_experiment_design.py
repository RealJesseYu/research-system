"""
stage2_experiment_design.py — real Experiment-Design stage: ONE isolated
Sonnet call turns the gate-1 chosen hypothesis into a typed experiment spec.

The stage reads the baton payload ({domain, chosen_hypothesis,
substrate_id} since Step 23.5, R-23.5-4) plus the contract of the payload's
gate-decided substrate (read from the registry — the D.1.1 cavity pin is
retired at this surface) plus,
since Step 18.5, the last 3 learned_summary journal entries, code-composed
into a substrate-capability lessons block (evidence at
runs/<run_id>/stage2/retrieved_memory.json; loop-back re-entry re-reads, so
a fresh lesson informs the redesigned spec). The
reply is enforced in Python, not trusted: a shallow envelope schema, then
validate_spec running as call_stage_model's extra_validator, whose
plain-language errors go back to the model as guided corrections inside the
same bounded 3-attempt loop. On success the validated spec becomes evidence
at runs/<run_id>/stage2/spec.json, the payload becomes
{domain, chosen_hypothesis, experiment_spec}, and the single history note is
written by code from validated fields — never model-authored narration.
"""

from __future__ import annotations

import json
from pathlib import Path

from baton import Baton
from memory.journal import journal_recent_by_kind
from model_call import FULL, call_stage_model, log_stage_call
from tools.run_python_experiment import run_python_experiment
from stages.stage2_spec import validate_spec
from tools import substrate_selection
from tools.qoi_vocab import vocab_for
from tools.substrate_registry import contract_for

SONNET_MODEL = "claude-sonnet-4-6"

# Step 18.5: memory reaches Stage 2. The block is code-composed from journal
# entries — never model-authored — and framed as instrument lessons, keeping
# the leads-not-facts journal-poison ruling.
LESSONS_HEADER = (
    "SUBSTRATE-CAPABILITY LESSONS FROM PRIOR RUNS (unverified model text - "
    "treat as leads, not established facts): prior runs learned these "
    "instrument limits - design within them or justify routing elsewhere:"
)


def build_substrate_lessons_block(entries: list[dict]) -> str | None:
    """Pure, no I/O: format learned_summary journal entries into the
    substrate-capability lessons block for the Stage-2 model input.

    Returns None when `entries` is empty; otherwise the exact LESSONS_HEADER
    line followed by one line per entry:
    "- [run <run_id>, hypothesis <hypothesis_id>] <text>" — the same line
    shape as stage 1's build_memory_block, so journal entries read the same
    everywhere they surface.
    """
    if not entries:
        return None
    lines = [LESSONS_HEADER]
    for e in entries:
        lines.append(
            f"- [run {e.get('run_id')}, hypothesis {e.get('hypothesis_id')}] {e.get('text')}"
        )
    return "\n".join(lines)


EXECUTION_FAILURE_HEADER = (
    "YOUR PREVIOUS SPEC FOR THIS HYPOTHESIS EXECUTED AND MEASURED NOTHING. "
    "These are the substrate's OWN verbatim rejection messages - not a "
    "summary, not a model's opinion, but exactly what the instrument said "
    "when it refused each run. They are FACTS about this instrument. Diagnose "
    "the cause and author a spec that does not repeat it; if the failure "
    "shows the declared instrument genuinely cannot perform this measurement, "
    "say so plainly in the regime notes rather than reissuing a spec that "
    "will fail the same way:"
)


def build_execution_failure_block(diagnosis: dict | None) -> str | None:
    """Pure, no I/O: format the supervisor's barren-run diagnosis into the
    Stage-2 model input (BARREN-RUN REDESIGN, 2026-07-20).

    Returns None when there is no diagnosis (the ordinary first-pass case).
    Unlike the lessons block above, these lines are NOT hedged as leads: a
    wrapper's rejection string is deterministic machine output, and framing it
    as "unverified model text" would invite the redesign to discount the one
    piece of ground truth it has.
    """
    if not isinstance(diagnosis, dict):
        return None
    errors = diagnosis.get("distinct_errors") or []
    if not errors and not diagnosis.get("reason"):
        return None
    lines = [EXECUTION_FAILURE_HEADER]
    attempted = diagnosis.get("runs_attempted")
    status = diagnosis.get("status")
    lines.append(f"- outcome: {status}; {attempted} run(s) attempted, 0 returned a value")
    if diagnosis.get("reason"):
        lines.append(f"- reason: {diagnosis['reason']}")
    for err in errors:
        lines.append(f"- the instrument rejected the run with: {err}")
    return "\n".join(lines)

SYSTEM_PROMPT = (
    "You are the Experiment-Design stage of an autonomous research pipeline: you turn "
    "the one chosen hypothesis you are given into a concrete, typed experiment "
    "specification, grounded in the substrate contract that accompanies it. "
    "Design the experiment this hypothesis actually needs — do NOT self-censor the "
    "quantity of interest down to what the wrapper extracts today, because instrument "
    "feasibility is a later gate's judgment, not yours — but be honest in regime.notes "
    "about anything uncertain, including any mismatch you see between the design and "
    "the substrate's declared limits. "
    "Choose exactly one quantity of interest, declare every parameter with role "
    '"sweep" (numeric min and max) or "fixed" (a value), and make every value '
    "physically sensible for the regime you state. "
    "When, and only when, the quantity of interest is genuinely extractable per the "
    "substrate contract — an existing field the case already writes, one of the "
    "contract's allowed operations, optional component — the qoi object MUST "
    'additionally carry the machine-readable keys "field", "operation", and '
    'optionally "component", using exactly the contract\'s vocabulary; when the '
    "quantity of interest is NOT extractable, those keys MUST be omitted (the "
    "free-text qoi name, definition, and how_extracted remain either way). "
    "When more than one quantity of interest could genuinely test the hypothesis, "
    "prefer one the substrate contract can extract. "
    "When the design genuinely predicts a numeric value for the quantity of "
    'interest, the success_criterion should additionally carry "expected_value" '
    '(the predicted number) and "tolerance" (a positive number: the acceptable '
    "absolute deviation); when it does not, omit both. "
    "If the spec declares a parameter whose value is derived from other "
    'parameters, give it role "derived" and state the rule in a "derived_from" '
    "string. "
    "When prior_thought is present, the previous design for this hypothesis "
    "failed for the reasons it states — the new spec must directly address that "
    "assessment and justification, and must not resubmit an unchanged design. "
    "When a prior_execution_failure block is present, your previous spec for "
    "this hypothesis was executed and returned no measurement at all. Those are "
    "the instrument's own verbatim rejection messages, and they are ground "
    "truth about this instrument — not opinions to weigh. Identify what the "
    "rejection actually demands (a required typed input the spec never "
    "supplied, a value outside a closed set the contract publishes, a "
    "measurement the substrate cannot make) and fix that specific cause. Do not "
    "reissue a design that will be rejected the same way, and do not silently "
    "narrow the science to dodge the error: if the failure shows this "
    "instrument genuinely cannot test this hypothesis, say so plainly in "
    "regime.notes. "
    "When a substrate_capability_lessons block is present, it lists instrument "
    "limits that earlier runs of this system learned the hard way (unverified "
    "model text — treat as leads, not established facts): design within those "
    "limits, and if the hypothesis genuinely requires exceeding one of them, say "
    "so explicitly in regime.notes rather than designing around it silently. "
    "Use the substrate contract's canonical parameter name whenever the physical "
    "quantity you are declaring matches one; parameters with no canonical "
    "equivalent keep their natural names — this is a naming convention, not a "
    "restriction on what may be designed. "
    "The mini_experiment is a cheap preview of 1 to 3 runs; every run must assign "
    "every declared parameter by name, keep fixed parameters at their declared "
    "values, and stay inside the declared sweep bounds. "
    'Reply ONLY with JSON of the form {"ack_run_id": "<the run_id you were given>", '
    '"spec": {"hypothesis_id": "<the id of the chosen hypothesis>", '
    '"title": "<short title>", "objective": "<one sentence>", '
    '"parameters": [{"name": "...", "role": "sweep", "units": "...", "min": <number>, '
    '"max": <number>} or {"name": "...", "role": "fixed", "units": "...", '
    '"value": <value>}, ...], "qoi": {"name": "...", "units": "...", '
    '"definition": "...", "how_extracted": "...", and the machine-readable keys '
    "only in the extractable case}, \"success_criterion\": "
    '{"statement": "...", "threshold": <number>, "direction": "above" or "below"}, '
    '"regime": <this substrate\'s regime declaration: an object with the '
    "regime fields the substrate contract states for this instrument "
    '(where the contract states none, the Reynolds band — "reynolds_min" '
    'and "reynolds_max" as numbers), plus "notes": "...">, '
    '"mini_experiment": {"runs": [{"<parameter name>": <value>, ...}, ...], '
    '"expected_observation": "..."}, "full_experiment": {"design": "...", '
    '"estimated_run_count": <positive integer>}}} — no other fields anywhere.'
)

SCHEMA = {"required": ["ack_run_id", "spec"]}

ENVELOPE_FIELDS = ("ack_run_id", "spec")


def _serve_ability_errors(spec, substrate_id: str) -> list[str]:
    """SERVE-ABILITY, CHECKED AT AUTHORING TIME (2026-07-20). The spec's
    declared parameter names must be a subset of the routed substrate's
    signature — the SAME L0 predicate substrate_selection applies at stage 3,
    read from the same signature_for source (never a second copy of the rule).

    WHY IT MOVED HERE. Stage 3's L0 failure is a LookupError, i.e. a crash,
    and it fires AFTER stage 2 has returned and the baton has been snapshotted
    — far too late to correct the only thing that could be wrong, which is the
    spec stage 2 just wrote. Run 20260719T231117Z died exactly this way: a
    cobrapy spec declaring glucose_lb/oxygen_lb, parameters that substrate has
    no knob for, authored 40 minutes before anything noticed. Checked here it
    is an ordinary re-ask: the model is told which names the instrument cannot
    accept and writes a servable spec on the next attempt.

    Never raises — an unknown/unwired substrate_id is left to the loud raisers
    that already own that failure at stage 3; this returns [] rather than
    inventing a second opinion about enrollment.
    """
    try:
        signature = substrate_selection.signature_for(substrate_id)
        declared = substrate_selection.declared_parameter_names(spec)
    except Exception:
        return []
    unserved = sorted(declared - signature)
    if not unserved:
        return []
    return [
        f"the parameter(s) {', '.join(repr(n) for n in unserved)} cannot be "
        f"run by this instrument — it accepts only "
        f"{', '.join(sorted(signature))}. Redesign the experiment to vary "
        f"only parameters the instrument actually exposes; do not rename "
        f"these to fit, and do not keep a parameter the instrument cannot "
        f"apply. If the hypothesis genuinely requires varying them, say so "
        f"in the design rationale and build the experiment around what this "
        f"instrument can vary."
    ]


def _code_execution_errors(spec, substrate_id: str, runner) -> list[str]:
    """AUTHORING-TIME EXECUTION CHECK (python_experiment only, 2026-07-21).

    After the spec is shape- and vocabulary-valid, actually RUN the authored
    code ONCE in the sealed container — the exact {code}+quantity stage 4 would
    dispatch (regime.code, qoi.quantity; see substrate_dispatch's
    _python_experiment_adapter). On an honest execution failure (a crash, a
    timeout, a missing metric) return the wrapper's own bounded diagnostic, so
    call_stage_model re-asks and the MODEL fixes its own code. This is the SAME
    authoring-time-re-ask pattern as _serve_ability_errors — the check is just
    'does the code actually run and write the metric' — and it is worth a run
    because a code bug caught here costs seconds, while the same bug caught at
    stage 4 burns an Opus fidelity call plus a whole barren relay pass (and one
    of only MAX_LOOPBACKS macro redesigns).

    ARCHITECTURE. The container run is deterministic tool output, not a model
    call, so the validator stays model-free. Its result is used ONLY as
    pass/fail for authoring and is discarded — stage 2 never produces the
    measurement of record; stage 4 runs the code again for that. Only the
    wrapper's already-bounded diagnostic flows back, so the summarize-at-the-
    wrapper invariant holds.

    A no-op (returns []) for every non-code substrate, so their authoring is
    byte-identical.
    """
    if substrate_id != "python_experiment":
        return []
    if not isinstance(spec, dict):
        return []
    regime = spec.get("regime")
    qoi = spec.get("qoi")
    code = regime.get("code") if isinstance(regime, dict) else None
    quantity = qoi.get("quantity") if isinstance(qoi, dict) else None
    # validate_spec already guarantees both for a code_execution spec; if either
    # is somehow absent the cheap checks already reported it, so do not run.
    if not (isinstance(code, str) and code.strip()):
        return []
    if not (isinstance(quantity, str) and quantity.strip()):
        return []

    summary = runner({"code": code, "quantity": quantity})
    if summary.get("valid"):
        return []
    return [
        "the authored code was executed once in the sealed container and did "
        f"not produce the metric {quantity!r}. The instrument reported "
        "verbatim: "
        f"{summary.get('diagnostics') or '(no diagnostic)'}. Fix the code so it "
        "runs cleanly and writes that metric into the results; do not change "
        "the science to dodge a bug."
    ]


def _make_extra_validator(chosen_id: str, vocab, substrate_id: str,
                          runner=run_python_experiment):
    """Deep validator handed to call_stage_model: the reply envelope must be
    exactly {ack_run_id, spec}, and the spec must pass validate_spec for the
    chosen hypothesis under the substrate's OWN QoI vocabulary (R-23.5-4:
    resolved from the payload's gate-decided substrate_id — the cavity
    vocab is the same record the old bare call resolved to, so cavity
    retry surfaces are byte-identical), AND be servable by that substrate
    (2026-07-20; see _serve_ability_errors), AND — for python_experiment only —
    its authored code must actually RUN and write the metric (2026-07-21; see
    _code_execution_errors). Returns plain-language error strings, empty = valid.

    `runner` is injected so unit tests can drive the code check with no
    container; production uses run_python_experiment.
    """

    def check(parsed: dict) -> list[str]:
        errors = [
            f"reply field '{key}' is not allowed — reply with exactly "
            '"ack_run_id" and "spec", nothing else.'
            for key in parsed
            if key not in ENVELOPE_FIELDS
        ]
        errors.extend(validate_spec(parsed["spec"], chosen_id, vocab))
        errors.extend(_serve_ability_errors(parsed["spec"], substrate_id))
        # Execute the code ONLY when the cheap checks all passed — never spin a
        # container for a spec that is already shape-invalid.
        if not errors:
            errors.extend(
                _code_execution_errors(parsed["spec"], substrate_id, runner)
            )
        return errors

    return check


def _log_line(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt (same path rule as log_stage_call)."""
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def run(baton: Baton) -> Baton:
    domain = baton.payload["domain"]
    chosen = baton.payload["chosen_hypothesis"]

    # Step 16 (loop-back): prior_thought is the thought layer's verdict on a
    # previous design of this same hypothesis (None on pass 1); it enters the
    # model input so the redesign can address it, and stays in the payload so
    # pass-2 boundaries and evidence keep the context.
    prior_thought = baton.payload.get("prior_thought")

    # Step 18.5: journal read-side into Stage 2 (deterministic, before the
    # model call; the SAME recency-only top-3 learned_summary read stage 1
    # uses — no similarity retrieval exists yet, disclosed limitation). On a
    # loop-back re-entry this re-read picks up the learned_summary stage 5
    # just journaled, so the redesigned spec sees the fresh instrument lesson.
    # Evidence mirrors stage 1's pattern: stage2/retrieved_memory.json
    # (overwritten on re-entry, same as spec.json).
    memory_entries = journal_recent_by_kind("learned_summary", 3)
    stage_dir = Path("runs") / baton.run_id / "stage2"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "retrieved_memory.json").write_text(json.dumps(memory_entries, indent=2))
    lessons_block = build_substrate_lessons_block(memory_entries)
    _log_line(
        baton.run_id,
        f"STAGE2_MEMORY retrieved {len(memory_entries)} learned_summary entries",
    )

    # R-23.5-4 (owner, 2026-07-17): the composition is grounded in the
    # contract of the payload's gate-decided substrate_id — a structural
    # key read, never a string literal, never a name parse. contract_for
    # fails loud on an unknown (KeyError) or contractless (LookupError)
    # id — NEVER a cavity fallback. For a cavity payload this returns the
    # same imported constant object as the retired literal pin, so the
    # composed bytes are identical (d1 pins hold with zero fixture edits).
    stage_input = {
        "run_id": baton.run_id,
        "domain": domain,
        "chosen_hypothesis": chosen,
        "substrate_contract": contract_for(baton.payload["substrate_id"]),
        "prior_thought": prior_thought,
    }
    if lessons_block is not None:
        stage_input["substrate_capability_lessons"] = lessons_block
    # BARREN-RUN REDESIGN (2026-07-20): on a barren loop-back the supervisor
    # stashes the verbatim execution diagnostics on the baton (a NON-payload
    # attribute — the payload schema is locked). Absent on every ordinary pass,
    # so first-pass composition is byte-identical.
    failure_block = build_execution_failure_block(
        getattr(baton, "_barren_diagnosis", None)
    )
    if failure_block is not None:
        stage_input["prior_execution_failure"] = failure_block
        _log_line(
            baton.run_id,
            "STAGE2_REDESIGN composing against verbatim prior execution failure",
        )
    data, timing = call_stage_model(
        "stage2_experiment_design",
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=SONNET_MODEL,
        extra_validator=_make_extra_validator(
            chosen["id"],
            vocab_for(baton.payload["substrate_id"]),
            baton.payload["substrate_id"],
        ),
        capabilities=FULL,
    )

    if data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage2_experiment_design: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {baton.run_id!r}"
        )
    _log_line(
        baton.run_id,
        f"ECHO_CHECK stage=stage2_experiment_design ack_run_id={data['ack_run_id']} "
        "matches run_id",
    )

    spec = data["spec"]
    (stage_dir / "spec.json").write_text(json.dumps(spec, indent=2))

    n_sweep = sum(1 for p in spec["parameters"] if p["role"] == "sweep")
    n_fixed = sum(1 for p in spec["parameters"] if p["role"] == "fixed")
    n_mini = len(spec["mini_experiment"]["runs"])
    note = (
        f"spec for {spec['hypothesis_id']}: {n_sweep} sweep + {n_fixed} fixed "
        f"parameters, QoI {spec['qoi']['name']}, mini-experiment of {n_mini} "
        f"run{'s' if n_mini != 1 else ''}"
    )

    baton.payload = {
        "domain": domain,
        "chosen_hypothesis": chosen,
        "experiment_spec": spec,
        # R-23.5-4 (owner, 2026-07-17): the gate-decided instrument travels
        # the payload untouched — it enters NO composed prompt; a payload
        # without it fails loud here, never defaults.
        "substrate_id": baton.payload["substrate_id"],
    }
    if prior_thought is not None:
        baton.payload["prior_thought"] = prior_thought
    baton.add_history("stage2_experiment_design", note)
    log_stage_call(baton.run_id, "stage2_experiment_design", timing)
    return baton
