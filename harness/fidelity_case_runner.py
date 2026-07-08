"""harness/fidelity_case_runner.py — deterministic-battery case runner
(Step 16.6 chunk 3).

Runs ONE fidelity gate case from harness/cases/cases.json via the DIRECT
call_stage_model path — the frozen stage-3 SYSTEM_PROMPT (imported from
stages.stage3_fidelity_gate, the single source of the frozen text; never
copied) plus the case's OWN prompt_inputs (substrate / envelope /
experiment) — exactly as the spike's run_fidelity_test.py did. RATIFIED
DESIGN: the battery does NOT go through stage3_fidelity_gate.run(), because
run() hardcodes CAVITY_2D_CONTRACT (14 of 16 cases can't flow through it)
and run() appends to the fidelity ledger.

CRITICAL INVARIANT (ledger-silent): this module never calls any ledger
writer. It is a test, not a real experiment — nothing here may pollute the
Step-21 evidence store (memory/fidelity_ledger.jsonl or any production
ledger). The only writers imported are none; the stage3 import is for its
frozen prompt and validator only, and importing has no side effects.

Calls are BARE by design (no "run_id" key in stage_input), following the
chunk-1 FAST-placeholder precedent: model_call's run-dir machinery
(transcript, durable NOTE/RE-ASK lines) prints but writes nothing, so a
battery run leaves no run dirs in runs/. Consequence, disclosed: the frozen
prompt asks the model to ack "the run_id you were given" and no run_id is
given — ack_run_id is required by the schema but its VALUE is not checked
here (stage3.run()'s echo-check needs a real run_id; the battery's
comparison is the verdict label, same as the spike's scorer).

RULE-1 tripwire carried over from the spike: the answer_key must never
reach the model. stage_input is built from prompt_inputs alone by
construction, and an assert verifies the key's right_instrument string did
not leak into the serialized input.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cost_meter  # noqa: E402
from model_call import call_stage_model  # noqa: E402
from stages.stage3_fidelity_gate import (  # noqa: E402
    OPUS_MODEL,
    SCHEMA,
    SYSTEM_PROMPT,
    _validate_verdict,
)

CASES_PATH = Path(__file__).resolve().parent / "cases" / "cases.json"

STAGE_NAME = "harness_fidelity_case"


def load_cases() -> list[dict]:
    """Read the in-repo copy of the Step-6 case set (never the spike's)."""
    return json.loads(CASES_PATH.read_text())["cases"]


def _meter_delta(before: dict, after: dict) -> dict:
    """Numeric diff of two cost_meter snapshots' flat count dicts."""
    return {key: after[key] - before.get(key, 0) for key in after}


def run_case(case: dict) -> dict:
    """One case end to end: build input -> one Opus call -> score vs key.

    Records case id, true_label, model verdict, pass/fail, wall-time, and
    the cost_meter deltas (model_calls, attempts). Never touches a ledger.
    """
    prompt_inputs = case["prompt_inputs"]
    answer_key = case["answer_key"]

    # NO "run_id" key: bare call, nothing written under runs/ (see module
    # docstring). The model sees exactly this object and the frozen prompt.
    stage_input = {
        "case_id": case["id"],
        "substrate": prompt_inputs["substrate"],
        "envelope": prompt_inputs["envelope"],
        "experiment": prompt_inputs["experiment"],
    }

    # RULE-1 tripwire (spike carry-over): the hidden routing answer must not
    # appear in what the model is sent.
    serialized = json.dumps(stage_input)
    assert answer_key["right_instrument"] not in serialized, (
        f"ANSWER KEY LEAK in case {case['id']} — aborting"
    )

    meter_before = cost_meter.read()
    start = time.perf_counter()
    data, timing = call_stage_model(
        STAGE_NAME,
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=OPUS_MODEL,
        extra_validator=_validate_verdict,
    )
    wall = time.perf_counter() - start
    meter_after = cost_meter.read()

    verdict = data["verdict"]
    return {
        "case_id": case["id"],
        "true_label": answer_key["true_label"],
        "verdict": verdict["label"],
        "passed": verdict["label"] == answer_key["true_label"],
        "rationale": verdict["rationale"],
        "right_instrument": verdict["right_instrument"],
        "key_right_instrument": answer_key["right_instrument"],
        "wall_time_seconds": round(wall, 3),
        "model_calls": _meter_delta(
            meter_before["model_calls"], meter_after["model_calls"]
        ),
        "attempts": _meter_delta(meter_before["attempts"], meter_after["attempts"]),
        "reask_attempts": timing["attempts"],
        "model": timing["model"],
    }
