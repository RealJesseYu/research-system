"""
stage4_simulation.py — real (isolated) Haiku call, plumbing only.

In a later chunk this becomes the stage that actually runs the simulation
(via the run_cfd wrapper graduating from the spike at Step 11). Right now
it proves the wiring.
"""

from baton import Baton
from model_call import call_stage_model, log_stage_call

SYSTEM_PROMPT = (
    "You are the placeholder for the Simulation stage of a research pipeline. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"note": "<one line, under 15 words, in your own words, naming this stage\'s future job>"}.'
)

SCHEMA = {"required": ["ack_run_id", "note"]}


def run(baton: Baton) -> Baton:
    stage_input = {"run_id": baton.run_id, "payload": baton.payload}
    data, timing = call_stage_model("stage4_simulation", SYSTEM_PROMPT, stage_input, SCHEMA)

    if data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage4_simulation: ack_run_id mismatch — got {data['ack_run_id']!r}, "
            f"expected {baton.run_id!r}"
        )

    baton.add_history("stage4_simulation", data["note"])
    log_stage_call(baton.run_id, "stage4_simulation", timing)
    return baton
