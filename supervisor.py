"""
supervisor.py — the deterministic traffic cop. NO AI calls anywhere in this
file, ever. Its only job: run the six stages in order, save the baton after
every stage, pause at the three gates, and (Step 16) enact the thought
layer's iterate decision — loop back to stage 1 or 2, bounded at
MAX_LOOPBACKS per run.

Usage:
    python3 supervisor.py --mode human   (pauses at each gate: pick-one-of-k
                                          after stage 1, y/n after stage 2,
                                          accept/override/stop at gate 5)
    python3 supervisor.py --mode auto    (gate 1 selects rank 1; gate 2 logs
                                          "auto-approved"; gate 5 enacts the
                                          model decision; never pauses)
(default mode is human)

The mode switch changes ONLY what happens at a gate. It never changes what
any stage does.
"""

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import schemas
from baton import Baton
from memory.journal import journal_append
from memory.ledgers import override_append
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
# Gate 5's decision prompt reuses the same bound (Step 16).
MAX_GATE1_INVALID_ANSWERS = 3

# Step 16: at most this many loop-backs (back_to_design / back_to_ideation)
# per run; a further non-exit decision forces a stop with a recommendation.
MAX_LOOPBACKS = 2

# Gate-5 override letters -> iterate decisions (Step 16).
GATE5_OVERRIDES = {
    "b": "back_to_design",
    "i": "back_to_ideation",
    "m": "more_data",
    "e": "exit",
}

# Step 15: the locked baton-payload schema enforced at each boundary — the
# validator that must pass right after the stage at this number returns
# (stage 1 has no entry: its ranked-list payload is reshaped by gate 1, and
# the post-gate-1 validator runs after apply_gate1_selection instead).
STAGE_BOUNDARY_VALIDATORS = {
    2: schemas.validate_payload_post_stage2,
    3: schemas.validate_payload_post_stage3,
    4: schemas.validate_payload_post_stage4,
    5: schemas.validate_payload_post_stage5,
}


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


def enforce_boundary_schema(logger: Logger, baton: Baton, boundary: str, validator) -> None:
    """Validate baton.payload at one boundary against the locked schema
    (schemas.py, Step 15). Deterministic Python, no model call.

    Non-empty errors are a broken architecture invariant, not a model error:
    the run halts loudly (durable SCHEMA VIOLATION line, a halted-schema
    run_record in the journal, exit) — there is NO re-ask and NO correction
    loop here, deliberately. On success a durable SCHEMA OK line records
    that the boundary was actually checked.
    """
    errors = validator(baton.payload)
    if errors:
        logger.log(f"SCHEMA VIOLATION after {boundary}: {errors}")
        record_run_outcome(baton, f"halted: schema violation after {boundary}")
        logger.log(
            f"=== supervisor run {baton.run_id} HALTED: schema violation "
            f"after {boundary} ==="
        )
        sys.exit(1)
    logger.log(f"SCHEMA OK after {boundary}: payload passed {validator.__name__}")


def run_single_stage(logger: Logger, baton: Baton, name: str, stage_fn) -> Baton:
    """Run one stage with a crash catch (Step 16, JC1b). Deterministic Python.

    INVARIANT: every run that starts leaves a run_record, no matter how it
    ends. Before this catch, a stage exception killed the process before
    record_run_outcome (first fired live in the Step-15 crashed demo
    20260706T054646Z). Now: durable STAGE-CRASH line (stage, exception
    class, message, last ~5 traceback lines), a "crashed" run_record with
    the exception summary, exit 1.

    Designed loud halts that surface as exceptions — e.g. stage 1's
    zero-survivors RuntimeError, or a model-call loud halt after 3 re-asks —
    are recorded under the same "crashed" status with their honest message;
    refining that taxonomy waits for evidence.
    """
    try:
        return stage_fn(baton)
    except Exception as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else ""
        logger.log(
            f"STAGE-CRASH stage={name} exception={type(exc).__name__}: {first_line}"
        )
        for tb_line in traceback.format_exc().splitlines()[-5:]:
            logger.log(f"STAGE-CRASH | {tb_line}")
        record_run_outcome(
            baton, f"crashed at {name}: {type(exc).__name__}: {first_line}"
        )
        logger.log(
            f"=== supervisor run {baton.run_id} CRASHED at stage {name} ==="
        )
        sys.exit(1)


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
    full baton dump the human has to read past. When the payload carries
    execution_results (stage 4 real, Step 12), an EXECUTION section follows
    the verdict: the status, then per-run one-liners for executed runs, or
    the skip/halt reason otherwise.
    """
    verdict = payload.get("fidelity_verdict")
    if not isinstance(verdict, dict):
        verdict = {}
    label = str(verdict.get("label") or "?").upper()
    lines = [
        "==================================",
        f"FIDELITY VERDICT: {label}",
        f"  rationale: {verdict.get('rationale') or '?'}",
        f"  right instrument: {verdict.get('right_instrument') or '?'}",
    ]
    exec_res = payload.get("execution_results")
    if isinstance(exec_res, dict):
        status = exec_res.get("status") or "?"
        lines.append(f"EXECUTION: {status}")
        if status == "executed":
            runs = exec_res.get("runs")
            for n, entry in enumerate(runs if isinstance(runs, list) else [], start=1):
                if not isinstance(entry, dict):
                    entry = {}
                converged = entry.get("converged")
                converged_txt = str(converged).lower() if isinstance(converged, bool) else "?"
                if "qoi_value" in entry:
                    qoi_txt = f"qoi {entry['qoi_value']}"
                elif "qoi_error" in entry:
                    qoi_txt = f"qoi_error {entry['qoi_error']}"
                else:
                    qoi_txt = "qoi ?"
                lines.append(f"  run {n}: converged {converged_txt}, {qoi_txt}")
        elif status == "skipped_defer":
            lines.append("  nothing executed: defer verdict")
        else:
            lines.append(f"  reason: {exec_res.get('reason') or '?'}")
        if exec_res.get("flag"):
            lines.append(f"  flag: {exec_res['flag']}")
    lines.append("==================================")
    thought_block = build_thought_block(payload)
    if thought_block:
        lines.append(thought_block)
    return "\n".join(lines)


def build_thought_block(payload: dict) -> str:
    """Boxed THOUGHT block for gate after_stage_5 (Step 13: stage 5 real).

    Pure function, no I/O: payload -> str. Same display-only, never-raise
    contract as the other headers; returns "" when the payload carries no
    thought, so pre-Step-13 payload shapes render exactly as before.
    """
    thought = payload.get("thought")
    if not isinstance(thought, dict):
        return ""
    return "\n".join(
        [
            "==================================",
            "THOUGHT",
            f"  triage: {thought.get('surprise_triage') or '?'}",
            f"  decision: {thought.get('iterate_decision') or '?'}",
            f"  justification: {thought.get('justification') or '?'}",
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

    # Step 16.6 chunk 2: observing hook — record the human's gate-2
    # resolution in the override ledger. The system's own decision at this
    # gate is what auto mode would do: approve. Reached only in human mode
    # (auto returned above), so auto runs never write here. Control flow
    # is untouched.
    approved = answer == "y"
    override_append(
        run_id=baton.run_id,
        gate=2,
        system_decision="approve",
        human_decision="approve" if approved else "halt",
        did_override=not approved,
    )

    if approved:
        logger.log(f"GATE {gate_name}: approved, continuing")
        return True
    logger.log(f"GATE {gate_name}: not approved, halting")
    return False


def parse_gate5_decision(raw: str) -> tuple:
    """Classify one raw gate-5 answer (Step 16). Pure function, no I/O.

    Returns ("accept",) for a/A, ("override", <decision>) for one of the
    GATE5_OVERRIDES letters, ("halt",) for n/N, ("invalid",) for everything
    else — whitespace and case tolerated throughout.
    """
    text = raw.strip().lower()
    if text == "a":
        return ("accept",)
    if text == "n":
        return ("halt",)
    if text in GATE5_OVERRIDES:
        return ("override", GATE5_OVERRIDES[text])
    return ("invalid",)


def run_gate5(logger: Logger, baton: Baton, mode: str) -> tuple:
    """Gate after stage 5 (Step 16): accept or override the model's iterate
    decision, or stop. Returns ("enact", decision, "accepted"|"overridden")
    or ("halt",).

    Auto mode enacts the model decision without pausing. Human mode shows
    the VERDICT/EXECUTION/THOUGHT header and baton (as before), prints the
    model decision prominently, and prompts; after
    MAX_GATE1_INVALID_ANSWERS invalid answers it halts (gate-1 pattern).
    Like every gate, decisions are recorded in the LOG only, never in the
    baton's history.
    """
    gate_name = "after_stage_5"
    logger.log(f"GATE {gate_name}: reached")
    model_decision = baton.payload.get("iterate_decision")

    if mode == "auto":
        return ("enact", model_decision, "accepted")

    logger.log(build_gate5_header(baton.payload))
    logger.log(f"--- baton at gate {gate_name} ---")
    logger.log(baton.to_json())
    logger.log("--- end baton ---")
    logger.log(f"MODEL DECISION: {model_decision}")

    prompt = (
        f"GATE {gate_name}: accept model decision '{model_decision}' [a] / "
        "override [b=back_to_design, i=back_to_ideation, m=more_data, "
        "e=exit] / stop [n]: "
    )
    # Step 16.6 chunk 2: observing hooks below — each human resolution of
    # this gate writes one override-ledger entry (system's recommendation =
    # the model's iterate decision). Auto mode returned above and never
    # writes here. Control flow and return values are untouched.
    invalid_count = 0
    while invalid_count < MAX_GATE1_INVALID_ANSWERS:
        logger.log(f"GATE {gate_name}: prompting {prompt!r}")
        answer = input(prompt)
        logger.log(f"GATE {gate_name}: human answered {answer!r}")
        parsed = parse_gate5_decision(answer)
        if parsed[0] == "accept":
            override_append(
                run_id=baton.run_id,
                gate=5,
                system_decision=model_decision,
                human_decision=model_decision,
                did_override=False,
            )
            return ("enact", model_decision, "accepted")
        if parsed[0] == "override":
            override_append(
                run_id=baton.run_id,
                gate=5,
                system_decision=model_decision,
                human_decision=parsed[1],
                did_override=True,
            )
            return ("enact", parsed[1], "overridden")
        if parsed[0] == "halt":
            override_append(
                run_id=baton.run_id,
                gate=5,
                system_decision=model_decision,
                human_decision="halt",
                did_override=True,
            )
            return ("halt",)
        invalid_count += 1
        logger.log(
            f"GATE {gate_name}: invalid answer "
            f"({invalid_count} of {MAX_GATE1_INVALID_ANSWERS} allowed)"
        )

    logger.log(f"GATE {gate_name}: {MAX_GATE1_INVALID_ANSWERS} invalid answers, halting")
    override_append(
        run_id=baton.run_id,
        gate=5,
        system_decision=model_decision,
        human_decision=f"halt ({MAX_GATE1_INVALID_ANSWERS} invalid answers)",
        did_override=True,
    )
    return ("halt",)


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

    # Step 16.6 chunk 2: observing hooks below — each human resolution of
    # this gate writes one override-ledger entry. The system's own decision
    # at this gate is what auto mode would do: select rank 1. Auto mode
    # returned above and never writes here. Control flow is untouched.
    invalid_count = 0
    while invalid_count < MAX_GATE1_INVALID_ANSWERS:
        prompt = f"GATE {gate_name}: pick 1..{k}, or n to stop: "
        logger.log(f"GATE {gate_name}: prompting {prompt!r}")
        answer = input(prompt)
        logger.log(f"GATE {gate_name}: human answered {answer!r}")

        parsed = parse_gate1_selection(answer, k)
        if parsed[0] != "invalid":
            if parsed[0] == "select":
                human_decision = f"select rank {parsed[1]}"
                did_override = parsed[1] != 1
            else:  # ("halt",)
                human_decision = "halt"
                did_override = True
            override_append(
                run_id=baton.run_id,
                gate=1,
                system_decision="select rank 1",
                human_decision=human_decision,
                did_override=did_override,
            )
            return parsed
        invalid_count += 1
        logger.log(
            f"GATE {gate_name}: invalid answer "
            f"({invalid_count} of {MAX_GATE1_INVALID_ANSWERS} allowed)"
        )

    logger.log(f"GATE {gate_name}: {MAX_GATE1_INVALID_ANSWERS} invalid answers, halting")
    override_append(
        run_id=baton.run_id,
        gate=1,
        system_decision="select rank 1",
        human_decision=f"halt ({MAX_GATE1_INVALID_ANSWERS} invalid answers)",
        did_override=True,
    )
    return ("halt",)


def apply_gate1_selection(
    logger: Logger, baton: Baton, mode: str, rank: int, run_dir: Path, pass_number: int = 1
) -> None:
    """Deterministic Python, no model call: replace the baton payload with the
    chosen hypothesis. The ranked list and the hypotheses_ranked flag do not
    travel further — they remain on disk in stage1/ evidence and in
    baton_after_stage_1.json. Baton history is untouched: gates never write
    history entries. pass_number > 1 (Step 16 loop-back re-entry) writes a
    pass-suffixed snapshot so the first pass's record survives.
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

    suffix = "" if pass_number == 1 else f"_pass{pass_number}"
    snapshot_path = run_dir / f"baton_after_gate_1{suffix}.json"
    snapshot_path.write_text(baton.to_json())
    logger.log(f"GATE after_stage_1: payload replaced with chosen hypothesis -> saved {snapshot_path.name}")


def apply_loopback_surgery(logger: Logger, baton: Baton, enacted: str) -> int:
    """Deterministic loop-back payload surgery (Step 16). Returns the 0-based
    stage index to re-enter.

    back_to_design: the payload is reduced to {domain, chosen_hypothesis,
    prior_thought} — prior_thought is the just-recorded thought object, and
    the stale spec/verdict/execution/thought fields are REMOVED (they live
    on in the pass's snapshots and stage evidence; the fresh pass rebuilds
    them).

    back_to_ideation: the payload is reduced to {domain}. NO prior_thought,
    deliberately: stage 1's journal read-side (Step 14) already retrieves
    the learned_summary stage 5 just appended, so the loop context arrives
    through memory, not the baton.
    """
    if enacted == "back_to_design":
        baton.payload = {
            "domain": baton.payload["domain"],
            "chosen_hypothesis": baton.payload["chosen_hypothesis"],
            "prior_thought": baton.payload["thought"],
        }
        re_enter_index = 1
    elif enacted == "back_to_ideation":
        baton.payload = {"domain": baton.payload["domain"]}
        re_enter_index = 0
    else:
        raise ValueError(f"apply_loopback_surgery: not a loop-back decision: {enacted!r}")
    baton.validate()
    logger.log(
        f"LOOP-BACK ({enacted}): payload reduced to "
        f"{{{', '.join(baton.payload)}}} — re-entering at stage {re_enter_index + 1}"
    )
    return re_enter_index


def run_relay(logger: Logger, baton: Baton, run_dir: Path, mode: str, stages=None) -> None:
    """The stage relay with loop control (Step 16). Deterministic Python.

    Runs the stages in order; at gate 5 the enacted iterate decision drives
    control flow: exit -> stage 6 exactly as before; more_data -> honest
    stop (Phase-C machinery, Step 19, is not built); back_to_design /
    back_to_ideation -> payload surgery + re-entry at stage 2 / stage 1,
    at most MAX_LOOPBACKS times per run.

    History invariant (restated Step 16): one entry per stage EXECUTION —
    a twice-run stage appears twice. Snapshots are pass-aware only for
    re-entered stages: pass 1 keeps baton_after_stage_N.json, re-entries
    write baton_after_stage_N_pass2.json etc. Gates behave per mode on
    every pass exactly as on pass 1 — human-in-the-loop by design.

    `stages` is a test seam (stub stages, no model calls); production uses
    the module STAGES.
    """
    stages = STAGES if stages is None else stages
    execution_counts: dict[int, int] = {}
    loopbacks_used = 0
    i = 0
    while i < len(stages):
        name, stage_fn = stages[i]
        stage_number = i + 1

        baton = run_single_stage(logger, baton, name, stage_fn)
        baton.validate()

        execution_counts[stage_number] = execution_counts.get(stage_number, 0) + 1
        pass_number = execution_counts[stage_number]
        suffix = "" if pass_number == 1 else f"_pass{pass_number}"
        pass_label = "" if pass_number == 1 else f" (pass {pass_number})"

        snapshot_path = run_dir / f"baton_after_stage_{stage_number}{suffix}.json"
        snapshot_path.write_text(baton.to_json())
        logger.log(f"STAGE {stage_number} ({name}): done -> saved {snapshot_path.name}")

        # Step 15: boundary enforcement — after the stage returns, before any
        # gate display and before the next stage. The snapshot is written
        # first so a violating baton survives on disk as evidence.
        if stage_number in STAGE_BOUNDARY_VALIDATORS:
            enforce_boundary_schema(
                logger,
                baton,
                f"stage {stage_number}{pass_label}",
                STAGE_BOUNDARY_VALIDATORS[stage_number],
            )

        if i in GATE_AFTER_STAGE_INDEX:
            gate_name = f"after_stage_{stage_number}"
            if gate_name == "after_stage_1":
                outcome = run_gate1(logger, baton, mode)
                if outcome[0] == "halt":
                    logger.log(f"=== supervisor run {baton.run_id} HALTED at gate {gate_name} ===")
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
                apply_gate1_selection(logger, baton, mode, outcome[1], run_dir, pass_number)
                # Step 15: the post-gate-1 payload is the first locked
                # boundary shape (the ranked-list payload before it is
                # gate-owned, not a stage boundary).
                enforce_boundary_schema(
                    logger,
                    baton,
                    f"gate 1{pass_label}",
                    schemas.validate_payload_post_gate1,
                )
            elif gate_name == "after_stage_2":
                should_continue = run_gate(logger, baton, mode, gate_name)
                if not should_continue:
                    logger.log(f"=== supervisor run {baton.run_id} HALTED at gate {gate_name} ===")
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
            else:  # after_stage_5: the iterate decision (Step 16)
                model_decision = baton.payload.get("iterate_decision")
                outcome = run_gate5(logger, baton, mode)
                if outcome[0] == "halt":
                    logger.log(f"=== supervisor run {baton.run_id} HALTED at gate {gate_name} ===")
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
                _, enacted, how = outcome
                logger.log(
                    f"GATE after_stage_5 [{mode}]: model={model_decision} "
                    f"enacted={enacted} ({how})"
                )
                if enacted == "more_data":
                    logger.log(
                        "MORE_DATA requires Phase-C experimentation intelligence "
                        "(Step 19) — ending run with recommendation"
                    )
                    logger.log(
                        f"=== supervisor run {baton.run_id} ended (more_data, "
                        f"unwired): {len(baton.history)} history entries ==="
                    )
                    record_run_outcome(baton, "completed_more_data_unwired")
                    return
                if enacted in ("back_to_design", "back_to_ideation"):
                    if loopbacks_used >= MAX_LOOPBACKS:
                        logger.log(
                            f"LOOP BOUND reached ({MAX_LOOPBACKS}) — forced exit "
                            "with recommendation"
                        )
                        logger.log(
                            f"=== supervisor run {baton.run_id} ended (loop bound): "
                            f"{len(baton.history)} history entries ==="
                        )
                        record_run_outcome(baton, "completed_loop_bound_forced_exit")
                        return
                    loopbacks_used += 1
                    i = apply_loopback_surgery(logger, baton, enacted)
                    if enacted == "back_to_design":
                        # The reduced payload is the post-gate-1 shape plus
                        # the ruled prior_thought — validate it before the
                        # re-entered pass consumes it.
                        enforce_boundary_schema(
                            logger,
                            baton,
                            f"gate 1 (pass {execution_counts.get(2, 0) + 1})",
                            schemas.validate_payload_post_gate1,
                        )
                    continue
                # enacted == "exit": fall through to stage 6 exactly as before.

        i += 1

    logger.log(
        f"=== supervisor run {baton.run_id} complete: {len(baton.history)} history entries ==="
    )
    record_run_outcome(baton, "completed")


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

    run_relay(logger, baton, run_dir, args.mode)


if __name__ == "__main__":
    main()
