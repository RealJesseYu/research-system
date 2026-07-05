"""
handfeed_stage5.py — the scored-experiment harness for the thought layer.

Loads one sealed case file from stage5_cases/ and runs the REAL stage-5
model call on its prompt_inputs half only. The case file's other half
(provenance + answer_key) never reaches the model by construction: this
harness passes case["prompt_inputs"] and nothing else across the
run_thought_model function boundary, and run_thought_model's own tripwire
(input keys exactly the six allowed; serialized input free of the substring
"answer_key") is the runtime guard behind that construction guarantee.

Evidence per case goes to runs/handfeed5-<UTC>-<case_id>/:
  prompt_inputs_sent.json — exactly what was serialized for the model
  reply.json              — the validated reply envelope. (The frozen
                            model_call door does not expose the raw
                            pre-parse text; this parsed envelope plus the
                            captured fence/RE-ASK lines are the closest
                            faithful record available.)
  thought.json            — the parsed thought object
  timing.json             — model, duration, attempts, fence_stripped
  model_log.txt           — fence NOTE / RE-ASK / ECHO_CHECK lines captured
                            from this call
  score.json              — written ONLY after all of the above are saved

The synthetic run_id inside each case's prompt_inputs (e.g. "case-a-frozen")
has a runs/<run_id>/ directory pre-created here so the frozen model-call
machinery can durably log fence NOTEs and RE-ASKs exactly as it does in live
runs; the lines this call appends there are copied into the evidence dir.

Scoring compares thought.surprise_triage and thought.iterate_decision
against the answer_key's allowed lists — after, and only after, the model
evidence is saved. This harness NEVER writes to the journal: scored cases
are experiments, not runs.

Usage: venv/bin/python3 handfeed_stage5.py --case stage5_cases/case_a.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from stages.stage5_thought_layer import run_thought_model

CASE_KEYS = ("case_id", "provenance", "prompt_inputs", "answer_key")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="path to a stage5_cases/ case file")
    args = parser.parse_args()

    case_path = Path(args.case)
    if not case_path.is_file():
        sys.exit(f"case file not found: {case_path}")
    case = json.loads(case_path.read_text())
    missing = [k for k in CASE_KEYS if k not in case]
    if missing:
        sys.exit(f"{case_path} is missing {missing} — not a sealed stage-5 case.")

    case_id = case["case_id"]
    prompt_inputs = case["prompt_inputs"]
    answer_key = case["answer_key"]

    now = datetime.now(timezone.utc)
    out_dir = Path("runs") / f"handfeed5-{now.strftime('%Y%m%dT%H%M%SZ')}-{case_id}"
    out_dir.mkdir(parents=True)
    (out_dir / "prompt_inputs_sent.json").write_text(json.dumps(prompt_inputs, indent=2))

    # Give the frozen model-call machinery a durable log home for the
    # synthetic run_id, and remember where its log ends now so only THIS
    # call's lines get captured.
    synthetic_dir = Path("runs") / str(prompt_inputs["run_id"])
    synthetic_dir.mkdir(parents=True, exist_ok=True)
    synthetic_log = synthetic_dir / "log.txt"
    log_offset = synthetic_log.stat().st_size if synthetic_log.is_file() else 0

    data, timing = run_thought_model(prompt_inputs)

    thought = data["thought"]
    (out_dir / "reply.json").write_text(json.dumps(data, indent=2))
    (out_dir / "thought.json").write_text(json.dumps(thought, indent=2))
    (out_dir / "timing.json").write_text(json.dumps(timing, indent=2))
    captured = ""
    if synthetic_log.is_file():
        with open(synthetic_log) as f:
            f.seek(log_offset)
            captured = f.read()
    (out_dir / "model_log.txt").write_text(captured)

    # Then, and only then: score.
    triage = thought["surprise_triage"]
    decision = thought["iterate_decision"]
    score = {
        "case_id": case_id,
        "model_triage": triage,
        "model_decision": decision,
        "triage_allowed": answer_key["triage_allowed"],
        "decision_allowed": answer_key["decision_allowed"],
        "triage_pass": triage in answer_key["triage_allowed"],
        "decision_pass": decision in answer_key["decision_allowed"],
        "attempts": timing["attempts"],
        "fence_stripped": timing["fence_stripped"],
    }
    (out_dir / "score.json").write_text(json.dumps(score, indent=2))

    print(f"CASE {case_id}")
    print(f"  triage:   {triage!r:20} {'PASS' if score['triage_pass'] else 'FAIL'} "
          f"(allowed: {answer_key['triage_allowed']})")
    print(f"  decision: {decision!r:20} {'PASS' if score['decision_pass'] else 'FAIL'} "
          f"(allowed: {answer_key['decision_allowed']})")
    print(f"  attempts: {timing['attempts']}  fence_stripped: {timing['fence_stripped']}")
    print(f"  evidence: {out_dir}/")


if __name__ == "__main__":
    main()
