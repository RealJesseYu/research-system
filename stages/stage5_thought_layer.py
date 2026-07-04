"""
stage5_thought_layer.py — real (isolated) Haiku call, plumbing only.

In a later chunk this becomes a real Opus call that interprets the
simulation results and decides whether to iterate or exit (Step 13). Right
now the model is plumbing, not a decision-maker: its iterate_decision is
schema-locked to the single allowed value "exit".
"""

from baton import Baton
from model_call import call_stage_model, log_stage_call

SYSTEM_PROMPT = (
    "You are the placeholder for the Thought-Layer stage of a research pipeline. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"note": "<one line, under 15 words, in your own words, naming this stage\'s future job>", '
    '"iterate_decision": "exit"}. '
    'The iterate_decision field must always be exactly the string "exit".'
)

SCHEMA = {
    "required": ["ack_run_id", "note", "iterate_decision"],
    "enums": {"iterate_decision": ["exit"]},
}


def run(baton: Baton) -> Baton:
    stage_input = {"run_id": baton.run_id, "payload": baton.payload}
    data, timing = call_stage_model("stage5_thought_layer", SYSTEM_PROMPT, stage_input, SCHEMA)

    if data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage5_thought_layer: ack_run_id mismatch — got {data['ack_run_id']!r}, "
            f"expected {baton.run_id!r}"
        )

    baton.payload["iterate_decision"] = data["iterate_decision"]
    baton.add_history("stage5_thought_layer", data["note"])
    log_stage_call(baton.run_id, "stage5_thought_layer", timing)
    return baton
