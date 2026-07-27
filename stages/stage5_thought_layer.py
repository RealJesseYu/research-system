"""
stage5_thought_layer.py — real Thought-Layer stage: ONE isolated Opus call
interprets what the pipeline designed and (when permitted) executed, triages
surprise, and decides what the system should do next. Opus, per CLAUDE.md's
model roles: the iterate decision is a hard judgment.

The stage code is deterministic: it assembles the six CORE prompt inputs from
the baton payload plus the on-disk stage-4 wrapper summaries, and — since D.1a
— an OPTIONAL seventh input, "substrate_contract": the routed substrate's own
fidelity-contract text, threaded so the thought layer can ground its
instrument-fit judgment (and the downstream validation instruction) in the
instrument's declared limits instead of a bare defer. The contract is threaded
ONLY for a substrate that is NOT the declared frozen reproducibility anchor
(registry.is_frozen_anchor) — the anchor (cavity) keeps its byte-frozen
six-key turn, and its exclusion is a declared registry property, never a
substrate-name branch. Nothing else may enter. The model call itself is
factored into run_thought_model, shared with the handfeed_stage5 harness; it
carries a runtime tripwire — the serialized input must not contain the
substring "answer_key", the six core keys must all be present, and no key
beyond the six core plus the optional substrate_contract may appear — which
hard-stops with "ANSWER KEY LEAK" otherwise.

The reply is enforced in Python, not trusted: a shallow envelope schema,
then _validate_thought as call_stage_model's extra_validator (surprise_triage
and iterate_decision enum-locked — the shared schema machinery checks only
top-level fields, so the nested enums are enforced here, still in code;
all five thought fields non-empty strings) inside the same bounded 3-attempt
loop. On success the full thought object becomes evidence at
runs/<run_id>/stage5/thought.json, the payload gains thought and its
iterate_decision (same designed home as the stub era, now model-emitted; the
supervisor still does not loop — deliberate), and the single history note is
written by code from already-validated fields.

JC6, the amnesia fix: decide_journal_entry is a pure function mapping a
validated thought to a learned_summary journal entry (None when the decision
is exit). Only the LIVE stage path appends it via journal_append; the
handfeed harness never writes to the journal — scored cases are experiments,
not runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from baton import Baton
from memory.journal import journal_append
from model_call import call_stage_model, log_stage_call
from tools import substrate_registry as registry
from models import model_for  # model-tier resolver

HEAVY_MODEL = model_for("heavy")

# The six CORE keys, always present, in assembly order. This stays exactly six
# so the frozen anchor's (cavity's) turn keeps its byte-identical shape and
# tests/test_d0_stage5_input.py holds unchanged: the D.1a contract is NOT a
# core key — it is the tolerated optional seventh below.
PROMPT_INPUT_KEYS = (
    "run_id",
    "chosen_hypothesis",
    "experiment_spec",
    "fidelity_verdict",
    "execution_results",
    "stage4_summaries",
)

# D.1a: the optional seventh key. Threaded by run() only for a non-anchor
# substrate that has a wired contract; absent for the frozen anchor and for a
# routable-but-unwired substrate. Kept OUT of PROMPT_INPUT_KEYS on purpose (see
# above) — the tripwire allows it explicitly.
CONTRACT_KEY = "substrate_contract"

TRIAGE_VALUES = ("none", "setup_error", "genuine_surprise", "out_of_envelope")
DECISION_VALUES = ("back_to_ideation", "back_to_design", "more_data", "exit")
THOUGHT_FIELDS = (
    "assessment",
    "surprise_triage",
    "iterate_decision",
    "justification",
    "learned_summary",
)

SYSTEM_PROMPT = (
    "You are the post-run thought layer of an autonomous research system: after "
    "the pipeline has designed and, when permitted, executed an experiment, you "
    "interpret what happened and decide what the system should do next. "
    "Compare the executed result against the spec's prediction in BOTH of its "
    "locations: the quantitative success_criterion {threshold, direction} and "
    "the qualitative mini_experiment.expected_observation. Judge whether the "
    "result is valid and physically realistic. "
    "Triage surprise as exactly one of: "
    '"setup_error" — the experiment as executed was broken or never executed '
    "(wrong or unbuildable configuration, failed run, or unusable measurement); "
    "the outcome says nothing about the hypothesis. "
    '"genuine_surprise" — the instrument worked and is trustworthy here, yet '
    "the result strongly contradicts or greatly deviates from the prediction — "
    "a possible discovery signal. "
    '"out_of_envelope" — the instrument cannot faithfully model this '
    "experiment, so the outcome reflects instrument limits, not the hypothesis. "
    '"none" — a result was obtained and is consistent with the prediction. '
    "Decide iteration as exactly one of: "
    '"back_to_ideation" — the hypothesis itself is off, answered, or a dead end. '
    '"back_to_design" — the experimental design or its fit to the instrument is '
    "the problem. "
    '"more_data" — the approach stands; more or finer runs are needed. '
    '"exit" — the question is answered or nothing further is productive. '
    "Judge only from what you are given plus your own knowledge; do not assume "
    "facts you were not told. "
    'Reply ONLY with JSON of the form {"ack_run_id": "<the run_id you were '
    'given>", "thought": {"assessment": "<what happened and whether the result '
    'is valid, in a few sentences>", "surprise_triage": "<none | setup_error | '
    'genuine_surprise | out_of_envelope>", "iterate_decision": '
    '"<back_to_ideation | back_to_design | more_data | exit>", "justification": '
    '"<one sentence: the single most decisive reason for the triage and '
    'decision>", "learned_summary": "<one or two sentences a future run could '
    'reuse: what was learned>"}} — no other fields anywhere.'
)

SCHEMA = {"required": ["ack_run_id", "thought"]}

ENVELOPE_FIELDS = ("ack_run_id", "thought")


def _validate_thought(parsed: dict) -> list[str]:
    """Deep validator handed to call_stage_model: the reply envelope must be
    exactly {ack_run_id, thought}, and the thought exactly the five fields,
    every one a non-empty string, with surprise_triage and iterate_decision
    enum-locked. Returns plain-language error strings, empty = valid.
    """
    errors = [
        f"reply field '{key}' is not allowed — reply with exactly "
        '"ack_run_id" and "thought", nothing else.'
        for key in parsed
        if key not in ENVELOPE_FIELDS
    ]
    thought = parsed.get("thought")
    if not isinstance(thought, dict):
        errors.append(
            "thought must be an object with assessment, surprise_triage, "
            "iterate_decision, justification, and learned_summary."
        )
        return errors
    for key in thought:
        if key not in THOUGHT_FIELDS:
            errors.append(
                f"thought field '{key}' is not allowed — the thought carries "
                f"exactly: {', '.join(THOUGHT_FIELDS)}."
            )
    for field in THOUGHT_FIELDS:
        value = thought.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"thought {field} must be a non-empty string.")
    if thought.get("surprise_triage") not in TRIAGE_VALUES:
        errors.append(
            f"thought surprise_triage must be exactly one of "
            f"{' | '.join(TRIAGE_VALUES)}; got {thought.get('surprise_triage')!r}."
        )
    if thought.get("iterate_decision") not in DECISION_VALUES:
        errors.append(
            f"thought iterate_decision must be exactly one of "
            f"{' | '.join(DECISION_VALUES)}; got {thought.get('iterate_decision')!r}."
        )
    return errors


def run_thought_model(prompt_inputs: dict) -> tuple[dict, dict]:
    """The ONE shared door to the thought model, used by the live stage and by
    the handfeed_stage5 harness. Serializes the input, trips a hard stop if
    anything beyond the six allowed keys (or any answer-key material) is
    present, makes exactly one bounded call, and asserts the ack echo.
    Returns (validated_reply, timing).
    """
    serialized = json.dumps(prompt_inputs)
    if "answer_key" in serialized:
        raise RuntimeError(
            "ANSWER KEY LEAK: the serialized thought-model input contains the "
            "substring 'answer_key' — refusing to call the model."
        )
    # D.1a: the six CORE keys are required; substrate_contract is the tolerated
    # optional seventh. Any missing core key OR any key beyond the allowed set
    # still hard-stops — the tripwire is relaxed by exactly one named key, not
    # opened up.
    allowed = set(PROMPT_INPUT_KEYS) | {CONTRACT_KEY}
    missing = set(PROMPT_INPUT_KEYS) - set(prompt_inputs)
    extra = set(prompt_inputs) - allowed
    if missing or extra:
        raise RuntimeError(
            "ANSWER KEY LEAK: thought-model input keys must be the six core "
            f"{sorted(PROMPT_INPUT_KEYS)} plus optional {CONTRACT_KEY!r}; got "
            f"{sorted(prompt_inputs)}."
        )

    data, timing = call_stage_model(
        "stage5_thought_layer",
        SYSTEM_PROMPT,
        prompt_inputs,
        SCHEMA,
        model=HEAVY_MODEL,
        extra_validator=_validate_thought,
    )

    run_id = prompt_inputs["run_id"]
    if data["ack_run_id"] != run_id:
        raise RuntimeError(
            f"stage5_thought_layer: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {run_id!r}"
        )
    line = (
        f"ECHO_CHECK stage=stage5_thought_layer ack_run_id={data['ack_run_id']} "
        "matches run_id"
    )
    print(line)
    run_dir = Path("runs") / str(run_id)
    if run_dir.is_dir():  # synthetic case ids have no run dir; print-only then
        with open(run_dir / "log.txt", "a") as f:
            f.write(line + "\n")

    return data, timing


def decide_journal_entry(thought: dict, run_id: str, hypothesis_id: str):
    """JC6, pure: map a validated thought to its journal entry, or None.

    exit means nothing to carry forward; every other decision journals the
    learned_summary so the next run does not start amnesiac.
    """
    if thought["iterate_decision"] == "exit":
        return None
    return {
        "kind": "learned_summary",
        "run_id": run_id,
        "hypothesis_id": hypothesis_id,
        "text": thought["learned_summary"],
    }


def _load_stage4_summaries(run_id: str) -> list:
    """Per-run wrapper summaries from runs/<run_id>/stage4/results.json —
    empty list when stage 4 skipped, halted, or left no results file."""
    results_path = Path("runs") / run_id / "stage4" / "results.json"
    if not results_path.is_file():
        return []
    results = json.loads(results_path.read_text())
    return [r["summary"] for r in results.get("runs", []) if "summary" in r]


def run(baton: Baton) -> Baton:
    prompt_inputs = {
        "run_id": baton.run_id,
        "chosen_hypothesis": baton.payload["chosen_hypothesis"],
        "experiment_spec": baton.payload["experiment_spec"],
        "fidelity_verdict": baton.payload["fidelity_verdict"],
        "execution_results": baton.payload["execution_results"],
        "stage4_summaries": _load_stage4_summaries(baton.run_id),
    }
    # D.1a: thread the routed substrate's OWN fidelity contract into the thought
    # layer, so its instrument-fit judgment — and the validation instruction
    # stage 6 derives from this stage's justification — is grounded in the
    # instrument's declared limits rather than a bare defer. Excluded for the
    # declared frozen anchor (cavity keeps its byte-frozen six-key turn and is
    # the golden case that needs a grounding instruction least) by reading a
    # registry PROPERTY, never a name branch. A routable-but-unwired substrate
    # has no contract yet: no field, and the fail-loud stays downstream.
    substrate_id = baton.payload.get("substrate_id")
    if substrate_id is not None and not registry.is_frozen_anchor(substrate_id):
        try:
            prompt_inputs[CONTRACT_KEY] = registry.contract_for(substrate_id)
        except LookupError:
            pass
    data, timing = run_thought_model(prompt_inputs)

    thought = data["thought"]
    stage_dir = Path("runs") / baton.run_id / "stage5"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "thought.json").write_text(json.dumps(thought, indent=2))

    payload = dict(baton.payload)
    payload["thought"] = thought
    payload["iterate_decision"] = thought["iterate_decision"]
    baton.payload = payload
    baton.add_history(
        "stage5_thought_layer",
        f"thought: triage={thought['surprise_triage']}, "
        f"decision={thought['iterate_decision']}",
    )
    log_stage_call(baton.run_id, "stage5_thought_layer", timing)

    entry = decide_journal_entry(
        thought, baton.run_id, baton.payload["chosen_hypothesis"]["id"]
    )
    if entry is not None:
        journal_append(entry)
    return baton
