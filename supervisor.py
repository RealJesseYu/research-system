"""
supervisor.py — the deterministic traffic cop. NO AI calls anywhere in this
file, ever. Its only job: run the six stages in order, save the baton after
every stage, and pause at the three gates.

Usage:
    python3 supervisor.py --mode human   (pauses at each gate: pick-one-of-k
                                          after stage 1, y/n at the other two)
    python3 supervisor.py --mode auto    (gate 1 selects rank 1; the other two
                                          log "auto-approved"; never pauses)
(default mode is human)

The mode switch changes ONLY what happens at a gate. It never changes what
any stage does.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from baton import Baton
from memory.journal import journal_append
from stages import (
    stage1_ideation,
    stage2_experiment_design,
    stage3_fidelity_gate,
    stage4_simulation,
    stage5_thought_layer,
    stage6_paper,
)

# The six stages, in order. The supervisor doesn't know or care what's
# inside each run() function — only that it takes a baton and returns one.
STAGES = [
    ("stage1_ideation", stage1_ideation.run),
    ("stage2_experiment_design", stage2_experiment_design.run),
    ("stage3_fidelity_gate", stage3_fidelity_gate.run),
    ("stage4_simulation", stage4_simulation.run),
    ("stage5_thought_layer", stage5_thought_layer.run),
    ("stage6_paper", stage6_paper.run),
]

# A gate fires right after the stage at this position (0-based) finishes:
# after stage 1 (index 0), after stage 2 (index 1), after stage 5 and
# before stage 6 (index 4).
GATE_AFTER_STAGE_INDEX = {0, 1, 4}

# Gate 1 (pick-one-of-k) halts after this many invalid human answers in a row.
MAX_GATE1_INVALID_ANSWERS = 3


class Logger:
    """Writes every line to both the terminal and runs/<run_id>/log.txt."""

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def log(self, line: str) -> None:
        print(line)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def record_run_outcome(baton: Baton, how_far: str) -> None:
    """Append one run_record to the journal: deterministic bookkeeping, no AI involved.

    `how_far` is e.g. "completed" or "halted at gate after_stage_2".
    """
    iterate_decision = baton.payload.get("iterate_decision")
    text = f"run {baton.run_id} ({baton.mode} mode): {how_far}"
    extras = {"how_far": how_far}
    if iterate_decision is not None:
        text += f", iterate_decision={iterate_decision}"
        extras["iterate_decision"] = iterate_decision
    journal_append({"run_id": baton.run_id, "kind": "run_record", "text": text, "extras": extras})


def build_gate2_header(payload: dict) -> str:
    """Pretty one-line summary of the experiment spec for gate after_stage_2.

    Pure function, no I/O: payload -> str. Display only — the human still
    sees (and the log still carries) the full baton dump right after it.
    Missing or malformed pieces render as '?' rather than raising: a
    display helper must never be able to kill a run.
    """
    spec = payload.get("experiment_spec")
    if not isinstance(spec, dict):
        spec = {}
    qoi = spec.get("qoi")
    full = spec.get("full_experiment")
    title = spec.get("title") or "?"
    qoi_name = (qoi.get("name") if isinstance(qoi, dict) else None) or "?"
    run_count = full.get("estimated_run_count") if isinstance(full, dict) else None
    return (
        f"SPEC: {title} | QoI: {qoi_name} | "
        f"estimated full-experiment runs: {run_count if run_count is not None else '?'}"
    )


def build_gate5_header(payload: dict) -> str:
    """Prominent fidelity-verdict block for gate after_stage_5.

    Pure function, no I/O: payload -> str. Same display-only, never-raise
    contract as build_gate2_header — the verdict is otherwise buried in the
    full baton dump the human has to read past.
    """
    verdict = payload.get("fidelity_verdict")
    if not isinstance(verdict, dict):
        verdict = {}
    label = str(verdict.get("label") or "?").upper()
    return "\n".join(
        [
            "==================================",
            f"FIDELITY VERDICT: {label}",
            f"  rationale: {verdict.get('rationale') or '?'}",
            f"  right instrument: {verdict.get('right_instrument') or '?'}",
            "==================================",
        ]
    )


def run_gate(logger: Logger, baton: Baton, mode: str, gate_name: str) -> bool:
    """Handle one gate. Returns True to continue, False to halt.

    The gate's decision is recorded in the LOG only, not in the baton's
    history — the baton's history is one entry per stage that touched it;
    the supervisor's gate decisions are the supervisor's own record.
    """
    logger.log(f"GATE {gate_name}: reached")

    if mode == "auto":
        logger.log(f"GATE {gate_name}: auto-approved")
        return True

    # Display-only pretty header (Step 11 ruling): summarize what this gate
    # is actually deciding, BEFORE the full baton dump. No logic change.
    if gate_name == "after_stage_2":
        logger.log(build_gate2_header(baton.payload))
    elif gate_name == "after_stage_5":
        logger.log(build_gate5_header(baton.payload))

    logger.log(f"--- baton at gate {gate_name} ---")
    logger.log(baton.to_json())
    logger.log("--- end baton ---")
    answer = input(f"GATE {gate_name}: approve to continue [y] / stop [n]: ").strip().lower()
    logger.log(f"GATE {gate_name}: human answered {answer!r}")

    if answer == "y":
        logger.log(f"GATE {gate_name}: approved, continuing")
        return True
    logger.log(f"GATE {gate_name}: not approved, halting")
    return False


def parse_gate1_selection(raw: str, k: int) -> tuple:
    """Classify one raw gate-1 answer. Pure function, no I/O.

    Returns ("select", i) for an integer 1..k (whitespace and case tolerated),
    ("halt",) for n/N, ("invalid",) for everything else — including
    out-of-range numbers and empty input.
    """
    text = raw.strip().lower()
    if text == "n":
        return ("halt",)
    try:
        value = int(text)
    except ValueError:
        return ("invalid",)
    if 1 <= value <= k:
        return ("select", value)
    return ("invalid",)


def run_gate1(logger: Logger, baton: Baton, mode: str) -> tuple:
    """Gate after stage 1: pick one of the k ranked hypotheses, or halt.

    Auto mode selects rank 1 without pausing. Human mode shows the ranked
    list and prompts; after MAX_GATE1_INVALID_ANSWERS invalid answers it
    halts. Returns ("select", rank) or ("halt",). Like run_gate, decisions
    are recorded in the LOG only, never in the baton's history.
    """
    gate_name = "after_stage_1"
    logger.log(f"GATE {gate_name}: reached")

    hypotheses = baton.payload["hypotheses"]
    k = len(hypotheses)

    if mode == "auto":
        return ("select", 1)

    logger.log(f"--- ranked hypotheses at gate {gate_name} ---")
    for rank, h in enumerate(hypotheses, start=1):
        logger.log(f"rank {rank}: {h['id']} — {h['statement']}")
    logger.log("--- end ranked hypotheses ---")

    invalid_count = 0
    while invalid_count < MAX_GATE1_INVALID_ANSWERS:
        prompt = f"GATE {gate_name}: pick 1..{k}, or n to stop: "
        logger.log(f"GATE {gate_name}: prompting {prompt!r}")
        answer = input(prompt)
        logger.log(f"GATE {gate_name}: human answered {answer!r}")

        parsed = parse_gate1_selection(answer, k)
        if parsed[0] != "invalid":
            return parsed
        invalid_count += 1
        logger.log(
            f"GATE {gate_name}: invalid answer "
            f"({invalid_count} of {MAX_GATE1_INVALID_ANSWERS} allowed)"
        )

    logger.log(f"GATE {gate_name}: {MAX_GATE1_INVALID_ANSWERS} invalid answers, halting")
    return ("halt",)


def apply_gate1_selection(logger: Logger, baton: Baton, mode: str, rank: int, run_dir: Path) -> None:
    """Deterministic Python, no model call: replace the baton payload with the
    chosen hypothesis. The ranked list and the hypotheses_ranked flag do not
    travel further — they remain on disk in stage1/ evidence and in
    baton_after_stage_1.json. Baton history is untouched: gates never write
    history entries.
    """
    hypotheses = baton.payload["hypotheses"]
    k = len(hypotheses)
    chosen = hypotheses[rank - 1]

    logger.log(f"GATE after_stage_1 [{mode}]: selected {chosen['id']} (rank {rank} of {k})")

    baton.payload = {
        "domain": baton.payload["domain"],
        "chosen_hypothesis": {
            "id": chosen["id"],
            "statement": chosen["statement"],
            "rationale": chosen["rationale"],
        },
    }
    baton.validate()

    snapshot_path = run_dir / "baton_after_gate_1.json"
    snapshot_path.write_text(baton.to_json())
    logger.log(f"GATE after_stage_1: payload replaced with chosen hypothesis -> saved {snapshot_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["human", "auto"], default="human")
    parser.add_argument("--domain", required=True, help="the research domain to seed this run with")
    args = parser.parse_args()

    run_id = make_run_id()
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = Logger(run_dir / "log.txt")

    logger.log(f"=== supervisor run {run_id} starting in mode={args.mode} ===")

    baton = Baton(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=args.mode,
        payload={"domain": args.domain},
    )
    baton.validate()

    for i, (name, stage_fn) in enumerate(STAGES):
        baton = stage_fn(baton)
        baton.validate()

        stage_number = i + 1
        snapshot_path = run_dir / f"baton_after_stage_{stage_number}.json"
        snapshot_path.write_text(baton.to_json())
        logger.log(f"STAGE {stage_number} ({name}): done -> saved {snapshot_path.name}")

        if i in GATE_AFTER_STAGE_INDEX:
            gate_name = f"after_stage_{stage_number}"
            if gate_name == "after_stage_1":
                outcome = run_gate1(logger, baton, args.mode)
                if outcome[0] == "halt":
                    logger.log(f"=== supervisor run {run_id} HALTED at gate {gate_name} ===")
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
                apply_gate1_selection(logger, baton, args.mode, outcome[1], run_dir)
            else:
                should_continue = run_gate(logger, baton, args.mode, gate_name)
                if not should_continue:
                    logger.log(f"=== supervisor run {run_id} HALTED at gate {gate_name} ===")
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)

    logger.log(f"=== supervisor run {run_id} complete: {len(baton.history)} history entries ===")
    record_run_outcome(baton, "completed")


if __name__ == "__main__":
    main()
