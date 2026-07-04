"""
stage6_paper.py — real (isolated) Haiku call, plumbing only.

In a later chunk this becomes a real Sonnet call that writes up the
findings as a paper. Right now it proves the wiring.
"""

from baton import Baton
from model_call import call_stage_model, log_stage_call

SYSTEM_PROMPT = (
    "You are the placeholder for the Paper stage of a research pipeline. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"note": "<one line, under 15 words, in your own words, naming this stage\'s future job>"}.'
)

SCHEMA = {"required": ["ack_run_id", "note"]}


def run(baton: Baton) -> Baton:
    stage_input = {"run_id": baton.run_id, "payload": baton.payload}
    data, timing = call_stage_model("stage6_paper", SYSTEM_PROMPT, stage_input, SCHEMA)

    if data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage6_paper: ack_run_id mismatch — got {data['ack_run_id']!r}, "
            f"expected {baton.run_id!r}"
        )

    baton.add_history("stage6_paper", data["note"])
    log_stage_call(baton.run_id, "stage6_paper", timing)
    return baton
