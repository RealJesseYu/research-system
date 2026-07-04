"""
stage2_experiment_design.py — real Experiment-Design stage: ONE isolated
Sonnet call turns the gate-1 chosen hypothesis into a typed experiment spec.

The stage reads only the baton payload ({domain, chosen_hypothesis}) plus the
substrate contract (substrates.py — this stage is its first consumer). The
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
from model_call import call_stage_model, log_stage_call
from stages.stage2_spec import validate_spec
from substrates import CAVITY_2D_CONTRACT

SONNET_MODEL = "claude-sonnet-4-6"

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
    "The mini_experiment is a cheap preview of 1 to 3 runs; every run must assign "
    "every declared parameter by name, keep fixed parameters at their declared "
    "values, and stay inside the declared sweep bounds. "
    'Reply ONLY with JSON of the form {"ack_run_id": "<the run_id you were given>", '
    '"spec": {"hypothesis_id": "<the id of the chosen hypothesis>", '
    '"title": "<short title>", "objective": "<one sentence>", '
    '"parameters": [{"name": "...", "role": "sweep", "units": "...", "min": <number>, '
    '"max": <number>} or {"name": "...", "role": "fixed", "units": "...", '
    '"value": <value>}, ...], "qoi": {"name": "...", "units": "...", '
    '"definition": "...", "how_extracted": "..."}, "success_criterion": '
    '{"statement": "...", "threshold": <number>, "direction": "above" or "below"}, '
    '"regime": {"reynolds_min": <number>, "reynolds_max": <number>, "notes": "..."}, '
    '"mini_experiment": {"runs": [{"<parameter name>": <value>, ...}, ...], '
    '"expected_observation": "..."}, "full_experiment": {"design": "...", '
    '"estimated_run_count": <positive integer>}}} — no other fields anywhere.'
)

SCHEMA = {"required": ["ack_run_id", "spec"]}

ENVELOPE_FIELDS = ("ack_run_id", "spec")


def _make_extra_validator(chosen_id: str):
    """Deep validator handed to call_stage_model: the reply envelope must be
    exactly {ack_run_id, spec}, and the spec must pass validate_spec for the
    chosen hypothesis. Returns plain-language error strings, empty = valid.
    """

    def check(parsed: dict) -> list[str]:
        errors = [
            f"reply field '{key}' is not allowed — reply with exactly "
            '"ack_run_id" and "spec", nothing else.'
            for key in parsed
            if key not in ENVELOPE_FIELDS
        ]
        errors.extend(validate_spec(parsed["spec"], chosen_id))
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

    stage_input = {
        "run_id": baton.run_id,
        "domain": domain,
        "chosen_hypothesis": chosen,
        "substrate_contract": CAVITY_2D_CONTRACT,
    }
    data, timing = call_stage_model(
        "stage2_experiment_design",
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=SONNET_MODEL,
        extra_validator=_make_extra_validator(chosen["id"]),
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
    stage_dir = Path("runs") / baton.run_id / "stage2"
    stage_dir.mkdir(parents=True, exist_ok=True)
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
    }
    baton.add_history("stage2_experiment_design", note)
    log_stage_call(baton.run_id, "stage2_experiment_design", timing)
    return baton
