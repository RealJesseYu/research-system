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
    python3 supervisor.py --mode auto    (gate 1 selects by the Stage-1.5
                                          chooser, rank-1 fallback; gate 2
                                          logs "auto-approved"; gate 5 enacts
                                          the model decision; never pauses)
(default mode is human)

The mode switch changes ONLY what happens at a gate. It never changes what
any stage does.
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import schemas
from baton import Baton
from memory.journal import blank_memory_active, journal_append
from memory.ledgers import override_append
from stages import (
    gate1_chooser,
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

# Wide crash-recovery fix (2026-07-19): an UNCAUGHT stage exception no longer
# hard-exits the run. It is journaled as a dead-end (the same learned_summary
# channel stage 5's back_to_ideation uses, so the next ideation round remembers
# and avoids it) and loops back to ideation, at most this many times per run.
# This is its OWN bounded budget, independent of MAX_LOOPBACKS (graceful gate-5
# loop-backs) and the total-defer retry. On exhaustion the run takes the honest
# terminal halt (memo + crashed run_record + exit) that predated this fix — a
# data-less crash cannot be turned into a real paper, so bounded recovery is the
# guarantee, not a fabricated deliverable. This deliberately softens the
# loud-halt doctrine for the crash path, on owner request.
MAX_CRASH_LOOPBACKS = 2

# 19-lite / retry build: retry-on-total-defer. Auto mode ONLY, env-gated,
# DEFAULT OFF. A "total defer" is a run terminating with ZERO executed solver
# runs and a final fidelity verdict class of "defer" — the pipeline produced
# no experiment at all. When RETRY_ON_TOTAL_DEFER=1 (auto mode), such a run
# loops back to Stage 1 exactly ONCE (its own counter, NOT the loop-bound
# counter), with the feasibility nudge forced on for that one retried ideation
# pass. A second total-defer terminates normally. Human mode ignores the flag.
RETRY_ON_TOTAL_DEFER_ENV = "RETRY_ON_TOTAL_DEFER"
MAX_TOTAL_DEFER_RETRIES = 1
# The Generation feasibility-nudge switch (stages/generation_strategies.py reads
# this env at call time); the retry forces it on for the retried pass only.
FEASIBILITY_NUDGE_ENV = "FEASIBILITY_NUDGE"
# Crash-recovery gate (mirrors retry-on-total-defer EXACTLY). Auto mode ONLY,
# env-gated, DEFAULT OFF. When CRASH_RECOVERY=1 (auto mode), an uncaught stage
# crash loops back to Stage 1 up to MAX_CRASH_LOOPBACKS times (journaling a
# dead-end each round) before the honest terminal halt. In human mode, or on
# default (env unset), the loopback is never entered: a crash halts LOUD on the
# FIRST occurrence — memo + crashed run_record + exit 1 — exactly as before this
# fix. Naming matches the no-prefix style of RETRY_ON_TOTAL_DEFER / FEASIBILITY_NUDGE.
CRASH_RECOVERY_ENV = "CRASH_RECOVERY"

# BARREN-RUN REDESIGN (owner-ruled 2026-07-20, after run 20260720T080610Z).
# A "barren" run is one that reached the end of stage 4 having produced ZERO
# usable measurements: every mini-run came back with a qoi_error and no run
# yielded a value, or synthesis halted before anything executed. Such a run is
# not a scientific result — there is nothing to think about and nothing to
# write up — so it must NEVER be allowed to reach stage 5/6 and become a paper
# about its own failure. It loops back to stage 2 carrying the VERBATIM
# execution diagnostics, so the redesign is a diagnosis and not a re-roll.
#
# DEFAULT ON, BOTH MODES — a deliberate departure from the opt-in convention of
# RETRY_ON_TOTAL_DEFER / CRASH_RECOVERY, per the owner's explicit instruction
# that this must not require being asked for. Set RETRY_ON_BARREN=0 to disable.
#
# The budget is its OWN counter, independent of MAX_LOOPBACKS: a barren run is
# an executional failure, not the thought layer's scientific judgment, and
# spending the scientific loop budget on plumbing would starve the real loop.
# When the budget is spent the run ends HONESTLY (no paper is fabricated) —
# a bounded retry, never an unbounded reroll.
RETRY_ON_BARREN_ENV = "RETRY_ON_BARREN"
MAX_BARREN_REDESIGNS = 2

# DESK-REJECTION REDESIGN (owner-ruled 2026-07-20). Stage 6 screens its own
# finished paper the way a handling editor would (stages/desk_review.py) and
# repairs manuscript-level defects itself. When the editor's remedy is
# "redesign" — the experiment cannot support any paper — the fix is upstream,
# so the supervisor loops back to stage 2 on its own bounded counter, exactly
# as the barren gate does. Same default-on rule and the same opt-out shape.
RETRY_ON_DESK_REJECT_ENV = "RETRY_ON_DESK_REJECT"
MAX_DESK_REDESIGNS = 1

# PHASE 3 — the exact-tool experiment path (R-ROUTE-4; docs/memo_phase3_routing.md).
# DEFAULT-ON since M1 (2026-07-21; docs/memo_m1_exact_route_default.md): a run
# whose gate-1 instrument is EXACT takes the experimenter loop in place of static
# stages 2-5 + the fidelity gate. An approximate instrument ALWAYS keeps the
# static pipeline + fidelity gate (routed_instrument_is_exact returns False for
# it), so the approximate path — cavity/calculix/fenicsx — is byte-identical.
# Set EXACT_ROUTE=0 to force the legacy static path for exact tools too (a
# transition kill-switch: a one-line rollback of the M1 default-on decision).
EXACT_ROUTE_ENV = "EXACT_ROUTE"

_UNSET = object()  # sentinel: no pending nudge-env restore

# Gate-5 override letters -> iterate decisions (Step 16).
GATE5_OVERRIDES = {
    "b": "back_to_design",
    "i": "back_to_ideation",
    "m": "more_data",
    "e": "exit",
}

# R-14-G1: the paste-first protocol banner. Printed at gate after_stage_2
# (always, human mode) and at gate after_stage_5 whenever the model's iterate
# decision is NOT 'exit'. A non-exit decision at gate 5 additionally requires
# the two-step typed CONFIRM form to enact ANY option (see run_gate5).
NON_EXIT_BANNER = (
    "!! NON-EXIT DECISION — PROTOCOL: paste this full gate text to the "
    "strategist and WAIT for the ruling before answering. !!"
)

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


class StageCrashed(Exception):
    """Raised by run_single_stage when a stage function raises (wide crash-
    recovery fix, 2026-07-19). Carries the stage name and the original
    exception so run_relay can decide recover-vs-halt — the terminal
    memo/record/exit no longer happens inside run_single_stage."""

    def __init__(self, stage_name: str, original: BaseException):
        self.stage_name = stage_name
        self.original = original
        super().__init__(str(original))


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


def record_run_outcome(baton: Baton, how_far: str, retry_on_total_defer: int = 0) -> None:
    """Append one run_record to the journal: deterministic bookkeeping, no AI involved.

    `how_far` is e.g. "completed" or "halted at gate after_stage_2".
    `retry_on_total_defer` (19-lite/retry build): number of total-defer retries
    this run consumed; when >0 it is stamped into the record's extras and text.
    Default 0 keeps the record byte-identical to the pre-build shape.
    """
    iterate_decision = baton.payload.get("iterate_decision")
    text = f"run {baton.run_id} ({baton.mode} mode): {how_far}"
    extras = {"how_far": how_far}
    if iterate_decision is not None:
        text += f", iterate_decision={iterate_decision}"
        extras["iterate_decision"] = iterate_decision
    if retry_on_total_defer:
        text += f", retry_on_total_defer={retry_on_total_defer}"
        extras["retry_on_total_defer"] = retry_on_total_defer
    # STEP 28: the substrate-maturity hook (apply_substrate_maturity_hook)
    # stashes its signoff decision on the baton as a NON-payload attribute
    # (the payload schema is locked; this fact never travels the baton). When
    # a trust decision touched a non-mature substrate, every terminal
    # run_record carries needs_human_signoff prominently — in extras and in
    # the human-readable text. No hook / mature-only route => key absent =>
    # record byte-identical to the pre-Step-28 shape.
    signoff = getattr(baton, "_maturity_signoff", None)
    if isinstance(signoff, dict) and signoff.get("required"):
        rungs = signoff.get("substrates") or []
        extras["needs_human_signoff"] = True
        extras["needs_human_signoff_substrates"] = rungs
        text += f", needs_human_signoff=[{', '.join(rungs)}]"
    # Phase-1 Lane-2: blank-memory disclosure. When the ablation is active
    # (env BLANK_MEMORY=1, default off) the run_record carries blank_memory=true
    # prominently — both in extras and in the human-readable text — so the
    # record is never silently ambiguous about whether memory was starved.
    # Flag off (default): the key is not added and the record is byte-identical.
    if blank_memory_active():
        extras["blank_memory"] = True
        text = f"[BLANK_MEMORY] {text}"
    # SUBSTRATE CONSTRAINT disclosure. A run restricted to a subset of the
    # routable substrates must say so permanently: a reader comparing two runs
    # has to be able to tell "this instrument was never chosen" from "this
    # instrument was never offered". Unconstrained (the default) => the key is
    # absent and the record is byte-identical to the pre-constraint shape.
    # Never raises: a malformed constraint has already stopped the run long
    # before this point, and a record must not fail to be written.
    try:
        from tools import substrate_registry as registry

        constrained_to = registry.allowed_constraint()
    except Exception:  # noqa: BLE001
        constrained_to = None
    if constrained_to is not None:
        extras["allowed_substrates"] = sorted(constrained_to)
        text += f", allowed_substrates=[{', '.join(sorted(constrained_to))}]"
    # VERIFICATION (2026-07-20). run_verification_pass stashes its summary on the
    # baton as a NON-payload attribute — the same channel _maturity_signoff and
    # _barren_diagnosis use, for the same reason (the payload schema is locked).
    # Whether the run's numbers survived an independent re-run belongs in the
    # permanent record, not only in the log: a reader of the journal must be able
    # to tell a standing paper from one whose numbers did not reproduce.
    verification = getattr(baton, "_verification", None)
    if isinstance(verification, dict):
        extras["verification"] = {
            "publishable": verification.get("publishable"),
            "verified": verification.get("verified"),
            "total": verification.get("total"),
        }
        text += (
            f", verification={verification.get('verified')}/{verification.get('total')}"
            f" publishable={verification.get('publishable')}"
        )
    journal_append({"run_id": baton.run_id, "kind": "run_record", "text": text, "extras": extras})


def run_verification_pass(logger: Logger, baton: Baton) -> dict:
    """Re-run every measured claim's artifact and decide whether this run's
    paper stands. Deterministic Python; no model anywhere in this path.

    Runs after stage 6 and before the run is recorded, on every path that
    produced a paper. The verdict is logged loudly and stashed on the baton for
    record_run_outcome.

    FAILS CLOSED. If the pass itself breaks, the run is NOT publishable: an
    unverified paper must never be recorded as a verified one, which is the same
    failure the desk screen had when a malformed reviewer reply returned "pass".
    The distinction between "checked and failed" and "could not be checked"
    survives in the reason, because they call for different responses — but
    neither one lets a paper stand.
    """
    from stages.verification import claims_from_run, verify_run

    try:
        claims = claims_from_run(baton.run_id)
        summary = verify_run(claims, run_id=baton.run_id)
    except Exception as e:  # noqa: BLE001 — see FAILS CLOSED above
        summary = {
            "total": 0, "verified": 0, "failed": 0, "publishable": False,
            "verdicts": [],
            "error": f"the verification pass could not run: {type(e).__name__}: {e}",
        }
        logger.log(f"VERIFICATION ERROR: {summary['error']} — run is NOT publishable")

    baton._verification = summary

    if summary.get("publishable"):
        logger.log(
            f"VERIFICATION: {summary['verified']}/{summary['total']} claims "
            "independently reproduced — the paper's numbers stand."
        )
    else:
        failed = [
            f"{v.get('label')}: {v.get('reason')}"
            for v in summary.get("verdicts", []) if not v.get("verified")
        ]
        detail = "; ".join(failed) if failed else (
            summary.get("error") or summary.get("note") or "no verifiable claims"
        )
        logger.log(
            f"VERIFICATION FAILED: {summary.get('verified', 0)}/"
            f"{summary.get('total', 0)} claims reproduced — THIS PAPER DOES NOT "
            f"STAND as a verified result [{detail}]"
        )
    return summary


def _run_dir_for(baton: Baton) -> Path:
    """The canonical run directory for a baton — the same path main() creates."""
    return Path("runs") / str(baton.run_id)


def write_failure_memo_safe(logger: Logger, run_dir: Path) -> None:
    """Write a code-authored failure memo, defensively. Step 4 (19-lite/retry
    build): a memo is record-keeping, written at every terminal outcome that is
    NOT a clean exit — but its write must never mask or replace the original
    failure path, so any error is logged and swallowed (nothing new is raised).
    The producer itself never raises; this is belt-and-suspenders."""
    try:
        from tools.failure_memo import write_failure_memo

        path = write_failure_memo(run_dir)
        if path is not None:
            logger.log(f"FAILURE-MEMO written -> {path.name}")
        else:
            logger.log("FAILURE-MEMO: nothing written (no run artifacts on disk)")
    except Exception as exc:  # never let record-keeping break the failure path
        logger.log(f"FAILURE-MEMO write skipped ({type(exc).__name__}: {exc})")


def is_total_defer(baton: Baton) -> bool:
    """True iff the run is terminating with ZERO executed solver runs AND a
    final fidelity verdict class of 'defer' (19-lite/retry build). Zero executed
    = the execution_results carries no non-empty runs list (a defer verdict
    produces skipped_defer with no runs)."""
    verdict = (baton.payload.get("fidelity_verdict") or {}).get("label")
    exec_res = baton.payload.get("execution_results") or {}
    runs = exec_res.get("runs")
    zero_executed = not runs  # None / missing / empty list -> nothing ran
    return verdict == "defer" and zero_executed


def is_barren(baton: Baton) -> bool:
    """True iff stage 4 finished having produced ZERO usable measurements.

    Three shapes qualify (all: no run anywhere yielded a value):
      * status 'executed' with runs present, every one carrying qoi_error —
        run 20260720T080610Z's shape: three cobrapy solves rejected on a
        missing typed field before the solver started;
      * status 'halted_synthesis' — the spec could not be turned into a case,
        so nothing executed at all;
      * any other non-defer status with no run carrying a qoi_value.

    NOT barren, deliberately:
      * skipped_defer — a defer verdict is the fidelity gate working; that path
        belongs to is_total_defer, which has its own ruled retry;
      * a PARTIALLY barren run — if even one run returned a value there IS
        data, and an absent value elsewhere may be the finding itself (a
        cobrapy infeasibility onset is a result, not a failure). Barren means
        the run measured NOTHING, not that something came back empty.
    """
    exec_res = baton.payload.get("execution_results") or {}
    status = exec_res.get("status")
    if status == "skipped_defer":
        return False
    runs = exec_res.get("runs") or []
    if any("qoi_value" in r for r in runs):
        return False  # at least one real measurement — there is data
    return status == "halted_synthesis" or bool(runs)


def barren_diagnosis(baton: Baton) -> dict:
    """The verbatim, model-free diagnosis carried back to stage 2 on a barren
    loop-back. Composed by deterministic Python from what stage 4 recorded —
    no paraphrase, because the actionable content of 'input rejected: missing
    required field(s): model' lives in its exact wording and a prose summary
    would launder it away.

    Distinct errors are de-duplicated (three identical rejections are ONE
    lesson, and repeating it three times would only crowd the context).
    """
    exec_res = baton.payload.get("execution_results") or {}
    errors, seen = [], set()
    for r in exec_res.get("runs") or []:
        err = r.get("qoi_error")
        if err and err not in seen:
            seen.add(err)
            errors.append(err)
    return {
        "status": exec_res.get("status"),
        "reason": exec_res.get("reason"),
        "distinct_errors": errors,
        "runs_attempted": len(exec_res.get("runs") or []),
        "runs_with_data": 0,
    }


def apply_substrate_maturity_hook(logger: Logger, baton: Baton, mode: str) -> None:
    """STEP 28: the substrate-maturity routing hook. CODE — not prompt text —
    intercepting the trust decision the moment the stage-3 fidelity verdict is
    produced and validated, BEFORE stage 4 consumes it.

    A trust decision is a trust/refine verdict (a defer verdict routes to no
    substrate, so there is nothing to gate).

    OWNER RULING (2026-07-19): the restriction is LIFTED for a MATURE routed
    substrate. The run's routed substrate is the gate-1 decision the payload
    carries — substrate_id (Step 23.5, R-23.5-4; the SAME field stage 3's
    agreement check reads) — and when it is mature a trust/refine verdict
    STANDS in both modes: no signoff, no downgrade. Reading substrate_id as a
    registry KEY for its maturity is a structural query (is_mature), not a
    substrate-name branch, so the substrate-agnostic invariant holds. A
    missing or unknown id falls through to the conservative check below.

    Otherwise (routed substrate non-mature, or unknown/missing): the run is
    still gated on the non-mature routable set — if ANY routable substrate is
    non-mature the trust decision is human-required: a NEEDS_HUMAN_SIGNOFF line
    is logged (a display) and the fact is stashed on the baton (a NON-payload
    attribute — the payload schema is locked) so every terminal run_record and
    the human gate carry it.

    Mode behavior:
      * human — the verdict is UNTOUCHED. A human sits at every gate; the
        hook's only effect is the explicit needs_human_signoff line in
        records/displays, so existing human-mode routing is byte-identical.
      * auto  — the trust/refine verdict is DOWNGRADED to 'defer' in place, so
        stage 4 runs its existing defer-class handling (skipped_defer, nothing
        executed). The substrate is NEVER silently trusted; the downgrade is
        logged. (rationale/right_instrument are left as the model wrote them —
        the override is documented by the log line and the run record, not by
        rewriting model-authored text.)

    All-mature route (no substrate today, but the future path): returns having
    touched nothing — verdict, baton, and logs unchanged.
    """
    from tools import substrate_registry as registry

    verdict = baton.payload.get("fidelity_verdict")
    if not isinstance(verdict, dict):
        return
    label = verdict.get("label")
    if label not in ("trust", "refine"):
        return  # not a trust decision — a defer verdict routes to no substrate

    # OWNER RULING (2026-07-19): a MATURE routed substrate lifts the restriction
    # — the verdict stands untouched, both modes. Keyed on the routed
    # substrate_id (registry lookup, not a name branch); unknown/missing falls
    # through to the conservative global check.
    routed = baton.payload.get("substrate_id")
    if isinstance(routed, str):
        try:
            if registry.is_mature(routed):
                return
        except KeyError:
            pass  # unknown id -> conservative: keep the restriction

    non_mature = [sid for sid in registry.routable_ids() if not registry.is_mature(sid)]
    if not non_mature:
        return  # every routable substrate is mature: byte-identical, nothing to do

    rungs = [f"{sid}@{registry.maturity_of(sid)}" for sid in non_mature]
    baton._maturity_signoff = {  # NON-payload attribute; asdict() ignores it
        "required": True,
        "substrates": rungs,
        "verdict_label_at_hook": label,
        "mode": mode,
    }
    logger.log(
        "NEEDS_HUMAN_SIGNOFF: stage-3 trust decision "
        f"(verdict={label}) touches non-mature substrate(s): {', '.join(rungs)}"
    )
    if mode == "auto":
        verdict["label"] = "defer"
        logger.log(
            f"MATURITY_DOWNGRADE [auto]: verdict {label} -> defer — non-mature "
            f"{', '.join(rungs)}; routed to existing defer-class handling, "
            "never silently trusted"
        )


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
        write_failure_memo_safe(logger, _run_dir_for(baton))
        record_run_outcome(baton, f"halted: schema violation after {boundary}")
        logger.log(
            f"=== supervisor run {baton.run_id} HALTED: schema violation "
            f"after {boundary} ==="
        )
        sys.exit(1)
    logger.log(f"SCHEMA OK after {boundary}: payload passed {validator.__name__}")


def run_single_stage(logger: Logger, baton: Baton, name: str, stage_fn) -> Baton:
    """Run one stage with a crash catch (Step 16, JC1b). Deterministic Python.

    Logs the crash — durable STAGE-CRASH line (stage, exception class, message,
    last ~5 traceback lines) — and re-raises it as StageCrashed for run_relay
    to handle. WIDE FIX (2026-07-19): the terminal memo/record/exit moved OUT
    of here. run_relay now journals the crash as a dead-end and loops back to
    ideation while its crash-recovery budget lasts, and only takes the honest
    terminal halt (memo + "crashed" run_record + exit 1) once the budget is
    spent — so every run that starts STILL leaves a run_record no matter how
    it ends, but a crash gets bounded recovery first.

    Designed loud halts that surface as exceptions — e.g. stage 1's
    zero-survivors RuntimeError, or a model-call loud halt after 3 re-asks —
    take the same recovery-then-halt path with their honest message; refining
    that taxonomy waits for evidence.
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
        raise StageCrashed(name, exc)


def journal_crash_dead_end(logger: Logger, baton: Baton, crash: StageCrashed) -> None:
    """WIDE FIX (crash recovery): journal a learned_summary dead-end so the
    NEXT ideation round remembers this crash and avoids re-proposing what hit
    it. Reflection's initial review reads recent learned_summary entries as its
    prior_dead_ends block (stages/reflection_reviews.py), so this code-authored
    entry rides the EXACT channel a stage-5 back_to_ideation dead-end uses — the
    crash becomes a lesson, not a silent death.

    ONLY a HYPOTHESIS-ATTRIBUTABLE crash is journaled: a chosen_hypothesis must
    exist in the payload (the crash happened at/after gate 1, so there is a
    specific approach to avoid). A crash BEFORE gate 1 — e.g. a stage-1
    retrieval/transport failure like an OpenAlex 400 — is NOT a scientific dead
    end; writing an 'unknown-hypothesis' lesson would both mislead ideation and
    churn the learned_summary memory baseline (the kill-rate md5 pin). Such a
    crash still loops back and retries; it just leaves no false lesson.

    Never raises: a failed journal write is logged and swallowed, like the memo."""
    chosen = baton.payload.get("chosen_hypothesis")
    if not (isinstance(chosen, dict) and chosen.get("id")):
        logger.log(
            "CRASH-RECOVERY: no chosen_hypothesis — crash is not a scientific "
            "dead-end (pre-gate-1 / infrastructure), no learned_summary journaled"
        )
        return
    try:
        hid = chosen["id"]
        statement = (chosen.get("statement") or "").strip()
        reason = (
            str(crash.original).splitlines()[0]
            if str(crash.original)
            else type(crash.original).__name__
        )
        if len(reason) > 240:
            reason = reason[:240].rstrip() + "…"
        # WORDING CORRECTED 2026-07-20. This used to assert the approach
        # "could not be modeled by any available instrument" and instruct
        # ideation to avoid it. The supervisor CANNOT know that: a crash is
        # just as likely a defect in this system as a limit of the
        # instrument, and on 20260719T231117Z it was exactly that — a missing
        # QoI key crashed stage 4 twice and wrote two entries condemning the
        # only two hypotheses in the run that had EARNED TRUST from the
        # fidelity gate. Reflection's initial review discards candidates that
        # re-propose a dead end, so a false entry does not merely mislead; it
        # kills the run's best science on the next attempt. The entry now
        # records what is actually known — the crash, the stage, the reason —
        # and explicitly flags the cause as unattributed.
        text = (
            f"CRASH (recovery loop-back): the run crashed at "
            f"{crash.stage_name} while pursuing hypothesis {hid}. Reason: "
            f"{reason}"
        )
        if statement:
            text += f" (hypothesis: {statement})"
        text += (
            " CAUSE NOT ATTRIBUTED: this may be a limitation of the available "
            "instruments OR a defect in the system itself — a crash alone "
            "does not distinguish them. Do NOT treat this as proof the "
            "approach is unworkable, and do not discard a candidate solely "
            "for resembling it. Prefer a formulation that avoids whatever "
            "the stated reason names, if one is available."
        )
        journal_append(
            {
                "kind": "learned_summary",
                "run_id": baton.run_id,
                "hypothesis_id": hid,
                "text": text,
            }
        )
        logger.log(f"CRASH-RECOVERY: journaled dead-end learned_summary for {hid}")
    except Exception as exc:  # never let record-keeping break recovery
        logger.log(
            f"CRASH-RECOVERY: dead-end journal skipped ({type(exc).__name__}: {exc})"
        )


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


def build_pi_gate_display(payload: dict) -> list[str]:
    """Display-only π-gate advisory lines for the human at gate after_stage_2.

    Phase-1 Lane-2 seam. Returns [] unless env PI_GATE == 'warn' (modes:
    off|warn, default off). In 'warn' mode it attaches the Buckingham-π report
    (Reynolds per point, duplicate-Re, dimensional coherence, Courant estimate)
    to the HUMAN gate-2 display only — exactly like the Elo table: informational,
    never gating, and auto mode never reaches here (run_gate returns early).
    v1 never kills: this is advisory text, and the module's enforce function is
    wired nowhere. Never raises — a display helper cannot kill a run; any error
    degrades to a single honest line.
    """
    if os.environ.get("PI_GATE") != "warn":
        return []
    try:
        from tools.pi_gate import pi_report, format_report_lines

        spec = payload.get("experiment_spec")
        report = pi_report(spec if isinstance(spec, dict) else {})
        return ["--- π-gate (warn, advisory only) ---", *format_report_lines(report)]
    except Exception as exc:  # never let the advisory kill the gate
        return [f"--- π-gate (warn): unavailable ({exc}) ---"]


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


def build_gate1_neartie_display(stage1_dir: Path) -> str:
    """Near-tie visibility at gate 1 (17-CLOSE, display-only).

    When stage1/tournament_state.json exists (the canonical file — under the
    17-E controller that is the LAST SUCCESSFUL round's state), render its
    final_ranking as a rank/id/Elo table so the human can see how close the
    ranks actually are (the 17-C witness surfaced a 0.79-Elo near-tie
    presented as a clean rank order); when stage1/research_overview.json
    exists, append each direction's summary line. Same contract as the other
    gate headers: pure read-and-format, no payload or parsing change, and it
    must never raise — missing or malformed files render as nothing or '?',
    never an exception.
    """
    lines: list[str] = []
    try:
        state_path = stage1_dir / "tournament_state.json"
        if state_path.exists():
            ranking = json.loads(state_path.read_text()).get("final_ranking")
            if isinstance(ranking, list) and ranking:
                lines.append("---- tournament Elo (final round) ----")
                for rank, entry in enumerate(ranking, start=1):
                    if not isinstance(entry, dict):
                        entry = {}
                    elo = entry.get("elo")
                    elo_txt = f"{elo:.1f}" if isinstance(elo, (int, float)) else "?"
                    lines.append(f"  rank {rank}: {entry.get('id') or '?'}  elo {elo_txt}")
    except Exception:
        pass  # display helpers must never be able to kill a run
    try:
        overview_path = stage1_dir / "research_overview.json"
        if overview_path.exists():
            directions = json.loads(overview_path.read_text()).get("directions")
            if isinstance(directions, list) and directions:
                lines.append("---- research-overview directions ----")
                for direction in directions:
                    summary = (
                        direction.get("summary") if isinstance(direction, dict) else None
                    )
                    lines.append(f"  - {summary or '?'}")
    except Exception:
        pass
    return "\n".join(lines)


def build_gate1_chooser_advisory(record: dict) -> str:
    """Chooser advisory at gate 1 (Step 23, display-only). Same contract as
    the other gate display helpers: pure record -> str, no payload or
    parsing change, and it must never raise — a malformed record renders as
    '?', never an exception. The human's integer pick remains the decision.
    """
    try:
        chosen = record.get("chosen_id") or "?"
        reasoning = record.get("reasoning") or "?"
        # R-23.5-3 (owner, 2026-07-17): the chooser's instrument read joins
        # the advisory — display-only; the human's instrument answer decides.
        instrument = record.get("substrate_id") or "?"
        fallback = " (FALLBACK to rank 1)" if record.get("fallback") else ""
        return "\n".join(
            [
                "---- CHOOSER ADVISORY (display-only; your pick decides) ----",
                f"  chooser chose: {chosen}{fallback}",
                f"  chooser instrument: {instrument}",
                f"  reasoning: {reasoning}",
                "---- end chooser advisory ----",
            ]
        )
    except Exception:
        return "---- CHOOSER ADVISORY unavailable ----"


def build_maturity_signoff_display(baton: Baton) -> str:
    """STEP 28 gate display: surface the substrate-maturity signoff requirement
    at the human gate. Reads the NON-payload attribute the hook stashed (the
    payload schema is locked, so the fact does not travel the payload); returns
    "" when no signoff was required, so gates render exactly as before Step 28.
    Same never-raise contract as the other gate display helpers.
    """
    signoff = getattr(baton, "_maturity_signoff", None)
    if not (isinstance(signoff, dict) and signoff.get("required")):
        return ""
    rungs = ", ".join(signoff.get("substrates") or [])
    return "\n".join(
        [
            "==================================",
            "!! NEEDS HUMAN SIGN-OFF: trust decision touched a non-mature "
            "substrate !!",
            f"  non-mature: {rungs}",
            "  a trust/refine verdict here may only proceed on your explicit "
            "sign-off",
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
        # Phase-1 Lane-2: π-gate warn display (env PI_GATE=warn, human only,
        # advisory; [] and thus no output when off). Auto mode never reaches
        # here. Enforce is unwired — this only prints.
        for line in build_pi_gate_display(baton.payload):
            logger.log(line)
    elif gate_name == "after_stage_5":
        logger.log(build_gate5_header(baton.payload))

    logger.log(f"--- baton at gate {gate_name} ---")
    logger.log(baton.to_json())
    logger.log("--- end baton ---")
    # R-14-G1: the paste-first banner also fronts gate 2 (y/n mechanics
    # below are unchanged — the banner is display only).
    if gate_name == "after_stage_2":
        logger.log(NON_EXIT_BANNER)
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

    R-14-G1 (human mode): when the model's iterate decision is NOT 'exit',
    the gate prints the paste-first NON_EXIT_BANNER and the single-key accept
    path is removed — enacting ANY option (accept, override, or halt) requires
    the two-step typed form: first the choice letter, then literally typing
    "CONFIRM <enacted-decision>". A model 'exit' decision keeps the old
    single-key fast path unchanged. A mismatched confirmation re-prompts the
    choice and counts toward the invalid bound.

    Like every gate, decisions are recorded in the LOG only, never in the
    baton's history.
    """
    gate_name = "after_stage_5"
    logger.log(f"GATE {gate_name}: reached")
    model_decision = baton.payload.get("iterate_decision")

    if mode == "auto":
        return ("enact", model_decision, "accepted")

    logger.log(build_gate5_header(baton.payload))
    signoff_display = build_maturity_signoff_display(baton)
    if signoff_display:
        logger.log(signoff_display)
    logger.log(f"--- baton at gate {gate_name} ---")
    logger.log(baton.to_json())
    logger.log("--- end baton ---")
    logger.log(f"MODEL DECISION: {model_decision}")

    # R-14-G1: a non-exit model decision fronts the gate with the paste-first
    # banner and switches enactment into the typed-CONFIRM regime below.
    require_confirm = model_decision != "exit"
    if require_confirm:
        logger.log(NON_EXIT_BANNER)

    prompt = (
        f"GATE {gate_name}: accept model decision '{model_decision}' [a] / "
        "override [b=back_to_design, i=back_to_ideation, m=more_data, "
        "e=exit] / stop [n]: "
    )

    def _enacted_decision_word(parsed_choice: tuple) -> str:
        """The decision the human's choice enacts — the token typed after
        CONFIRM. accept enacts the model decision; override enacts its
        target; halt enacts 'halt'."""
        if parsed_choice[0] == "accept":
            return model_decision
        if parsed_choice[0] == "override":
            return parsed_choice[1]
        return "halt"

    def _confirmed(decision_word: str) -> bool:
        """Exit keeps the single-key fast path; a non-exit decision demands
        the exact typed 'CONFIRM <decision_word>' as a deliberate second step."""
        if not require_confirm:
            return True
        confirm_prompt = (
            f"GATE {gate_name}: type 'CONFIRM {decision_word}' to enact "
            "(anything else re-prompts): "
        )
        logger.log(f"GATE {gate_name}: prompting {confirm_prompt!r}")
        confirmation = input(confirm_prompt)
        logger.log(f"GATE {gate_name}: human confirmation {confirmation!r}")
        ok = confirmation.strip() == f"CONFIRM {decision_word}"
        if not ok:
            logger.log(f"GATE {gate_name}: confirmation mismatch — re-prompting")
        return ok

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
        if parsed[0] != "invalid":
            decision_word = _enacted_decision_word(parsed)
            if not _confirmed(decision_word):
                invalid_count += 1
                logger.log(
                    f"GATE {gate_name}: unconfirmed choice "
                    f"({invalid_count} of {MAX_GATE1_INVALID_ANSWERS} allowed)"
                )
                continue
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


def parse_gate1_instrument(raw: str, routable: tuple) -> tuple:
    """Classify one raw gate-1 instrument answer (Step 23.5, R-23.5-3). Pure
    function, no I/O — the same pattern as parse_gate1_selection.

    Returns ("instrument", substrate_id) for the exact id (whitespace
    tolerated, case-sensitive) or its 1-based index in `routable`,
    ("halt",) for n/N, ("invalid",) for everything else — including
    out-of-range indexes and empty input.
    """
    text = raw.strip()
    if text.lower() == "n":
        return ("halt",)
    if text in routable:
        return ("instrument", text)
    try:
        value = int(text)
    except ValueError:
        return ("invalid",)
    if 1 <= value <= len(routable):
        return ("instrument", routable[value - 1])
    return ("invalid",)


def _prompt_gate1_instrument(
    logger: Logger, baton: Baton, gate_name: str, rank: int, chooser_record: dict
) -> tuple:
    """R-23.5-3 (owner, 2026-07-17): the human instrument prompt after the
    valid rank pick — an instrument from the registry's LIVE routable list,
    or halt, under the same MAX_GATE1_INVALID_ANSWERS cap pattern as the
    rank prompt. Returns ("select", rank, substrate_id) or ("halt",). The
    instrument answer is logged additively as a second override-ledger
    entry of the exact current entry shape, beside the rank entry."""
    from tools import substrate_registry as registry

    # permitted_ids(): the human is offered only the instruments this run is
    # allowed to reach. Listing a forbidden one and rejecting the answer after
    # the fact would be a worse gate than not offering it.
    routable = registry.permitted_ids()
    chooser_read = (
        chooser_record.get("substrate_id")
        if isinstance(chooser_record, dict)
        else None
    )
    listing = ", ".join(f"{i}={sid}" for i, sid in enumerate(routable, start=1))
    invalid_count = 0
    while invalid_count < MAX_GATE1_INVALID_ANSWERS:
        prompt = (
            f"GATE {gate_name}: instrument — routable: {listing} — "
            f"type the id or 1..{len(routable)}, or n to stop: "
        )
        logger.log(f"GATE {gate_name}: prompting {prompt!r}")
        answer = input(prompt)
        logger.log(f"GATE {gate_name}: human answered {answer!r}")

        parsed = parse_gate1_instrument(answer, routable)
        if parsed[0] != "invalid":
            if parsed[0] == "instrument":
                human_decision = f"instrument {parsed[1]}"
                did_override = parsed[1] != chooser_read
            else:  # ("halt",)
                human_decision = "halt (instrument prompt)"
                did_override = True
            override_append(
                run_id=baton.run_id,
                gate=1,
                system_decision=f"instrument {chooser_read}",
                human_decision=human_decision,
                did_override=did_override,
            )
            if parsed[0] == "instrument":
                return ("select", rank, parsed[1])
            return ("halt",)
        invalid_count += 1
        logger.log(
            f"GATE {gate_name}: invalid instrument answer "
            f"({invalid_count} of {MAX_GATE1_INVALID_ANSWERS} allowed)"
        )

    logger.log(
        f"GATE {gate_name}: {MAX_GATE1_INVALID_ANSWERS} invalid instrument "
        "answers, halting"
    )
    override_append(
        run_id=baton.run_id,
        gate=1,
        system_decision=f"instrument {chooser_read}",
        human_decision=(
            f"halt ({MAX_GATE1_INVALID_ANSWERS} invalid instrument answers)"
        ),
        did_override=True,
    )
    return ("halt",)


def run_gate1(logger: Logger, baton: Baton, mode: str) -> tuple:
    """Gate after stage 1: pick one of the k ranked hypotheses AND the
    instrument, or halt.

    Auto mode (Step 23; instrument decision Step 23.5, R-23.5-1) resolves to
    the Stage-1.5 chooser's chosen_id and substrate_id — one Opus call in
    stages/gate1_chooser.py, never invoked in this file's own logic beyond
    scheduling it, exactly as stages are scheduled; the chooser never raises
    and falls back to rank 1 (the old placeholder) with the fallback
    recorded in gate1_chooser.json. R-23.5-2: the fallback carries
    substrate_id null, and a null instrument stops the run loudly at the
    gate — a cavity default is forbidden. Human mode shows the ranked list
    plus the chooser's reasoning and instrument read as a display-only
    advisory and prompts; the human's integer pick remains the decision,
    then one more prompt decides the instrument (R-23.5-3, superseding the
    frozen human-gate flow by that ruling); after
    MAX_GATE1_INVALID_ANSWERS invalid answers at either prompt it halts.
    Returns ("select", rank, substrate_id) or ("halt",). Like run_gate,
    decisions are recorded in the LOG only, never in the baton's history.
    """
    gate_name = "after_stage_1"
    logger.log(f"GATE {gate_name}: reached")

    hypotheses = baton.payload["hypotheses"]
    k = len(hypotheses)

    if mode == "auto":
        record = gate1_chooser.choose_hypothesis(
            baton.run_id, hypotheses, Path("runs") / baton.run_id
        )
        # R-23.5-2 (owner, 2026-07-17): a null instrument STOPS the run
        # loudly at the gate — a cavity default is forbidden. The
        # null-instrument marker below names the reason and is
        # distinguishable in the log from a human halt.
        if record.get("substrate_id") is None:
            logger.log(
                f"GATE {gate_name} [auto]: STOP null-instrument (R-23.5-2) — "
                f"chooser returned substrate_id null "
                f"(fallback={record.get('fallback')}); "
                f"reason: {record.get('reasoning')}"
            )
            return ("halt",)
        # The chooser guarantees a valid id (validator + rank-1 fallback);
        # the default-1 here is deterministic belt-and-braces only.
        rank = next(
            (i for i, h in enumerate(hypotheses, start=1) if h["id"] == record["chosen_id"]),
            1,
        )
        logger.log(
            f"GATE {gate_name} [auto]: chooser chose {record['chosen_id']} "
            f"(rank {rank} of {k}, fallback={record['fallback']}) "
            f"on instrument {record['substrate_id']}"
        )
        # R-23.5-1: in auto mode the chooser's same single call names the
        # instrument; it travels with the selection.
        return ("select", rank, record["substrate_id"])

    logger.log(f"--- ranked hypotheses at gate {gate_name} ---")
    for rank, h in enumerate(hypotheses, start=1):
        logger.log(f"rank {rank}: {h['id']} — {h['statement']}")
    logger.log("--- end ranked hypotheses ---")

    # 17-CLOSE, display-only: near-tie Elo table + research-overview
    # direction summaries, read from stage1 evidence when present. No
    # payload change, no parsing change.
    neartie = build_gate1_neartie_display(Path("runs") / baton.run_id / "stage1")
    if neartie:
        logger.log(neartie)

    # Step 23, display-only: the Stage-1.5 chooser's reasoned pick, shown
    # as a labeled advisory before the prompt. The human's integer pick
    # remains the decision — payload, parsing, and gate control flow are
    # untouched. This spends the chooser's one Opus call in human mode too
    # (disclosed cost delta); the record lands in gate1_chooser.json.
    chooser_record = gate1_chooser.choose_hypothesis(
        baton.run_id, hypotheses, Path("runs") / baton.run_id
    )
    logger.log(build_gate1_chooser_advisory(chooser_record))

    # Step 16.6 chunk 2: observing hooks below — each human resolution of
    # this gate writes one override-ledger entry. The ledger's
    # system_decision baseline stays "select rank 1" deliberately (Step 23):
    # human-gate behavior is frozen, and the chooser is advisory here — its
    # pick is on disk in gate1_chooser.json, not in the ledger. Auto mode
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
            if parsed[0] != "select":
                return parsed
            # R-23.5-3 (owner, 2026-07-17; supersedes the frozen human-gate
            # flow by this ruling): after the valid rank pick, one more
            # prompt — an instrument from the LIVE routable list, or halt —
            # under the same invalid-answer cap pattern. The override-ledger
            # entry above keeps its exact current shape; the instrument
            # answer is logged additively BESIDE it as a second entry of
            # the same shape.
            return _prompt_gate1_instrument(
                logger, baton, gate_name, parsed[1], chooser_record
            )
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
    logger: Logger,
    baton: Baton,
    mode: str,
    rank: int,
    run_dir: Path,
    pass_number: int = 1,
    *,
    substrate_id: str,
) -> None:
    """Deterministic Python, no model call: replace the baton payload with the
    chosen hypothesis and the decided instrument (R-23.5-4, owner
    2026-07-17: the post-gate-1 payload is exactly {domain,
    chosen_hypothesis, substrate_id}; substrate_id enters NO composed
    prompt anywhere — it travels forward so stages 3 and 4 compare it
    against select_substrate's spec-derived answer). substrate_id is a
    required keyword: a caller that fails to pass the gate's decision
    raises, never defaults. The ranked list and the hypotheses_ranked flag
    do not travel further — they remain on disk in stage1/ evidence and in
    baton_after_stage_1.json. Baton history is untouched: gates never write
    history entries. pass_number > 1 (Step 16 loop-back re-entry) writes a
    pass-suffixed snapshot so the first pass's record survives.
    """
    hypotheses = baton.payload["hypotheses"]
    k = len(hypotheses)
    chosen = hypotheses[rank - 1]

    logger.log(
        f"GATE after_stage_1 [{mode}]: selected {chosen['id']} "
        f"(rank {rank} of {k}) on instrument {substrate_id}"
    )

    baton.payload = {
        "domain": baton.payload["domain"],
        "chosen_hypothesis": {
            "id": chosen["id"],
            "statement": chosen["statement"],
            "rationale": chosen["rationale"],
        },
        "substrate_id": substrate_id,
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
            # R-23.5-4 + loop-back invariant (build-chat ruling, 2026-07-17):
            # the carried substrate_id is read from the LIVE payload — the
            # standing decision of the pass being redesigned, never a
            # prior-pass snapshot, never a default; absent = loud KeyError.
            "substrate_id": baton.payload["substrate_id"],
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


def exact_route_active() -> bool:
    """True unless explicitly disabled (EXACT_ROUTE=0). DEFAULT-ON since M1
    (2026-07-21): an exact-tool run takes the experimenter loop; static stages
    2-5 + the fidelity gate are reserved for approximate instruments. Set
    EXACT_ROUTE=0 to force the legacy static path for exact tools too (a
    transition kill-switch). See docs/memo_m1_exact_route_default.md."""
    return os.environ.get(EXACT_ROUTE_ENV, "1") != "0"


def routed_instrument_is_exact(baton: Baton) -> bool:
    """R-ROUTE-4: does gate 1's chosen instrument take the experimenter path?
    Reads the substrate_id off the post-gate-1 payload and asks the registry its
    class — never a substrate-name branch. Missing/unknown id => False (keep the
    static path): the routed path is entered only on a POSITIVE exact answer, so
    an ambiguity can never skip the fidelity gate."""
    from tools import substrate_registry as registry

    sid = baton.payload.get("substrate_id")
    if not sid:
        return False
    try:
        return not registry.is_approximate(sid)
    except KeyError:
        return False


def run_exact_route(logger: Logger, baton: Baton, run_dir: Path, mode: str,
                    exact_strategy=None) -> None:
    """The exact-tool experiment path: the experimenter loop REPLACES static
    stages 2-5 (R-ROUTE-3), the fidelity gate is a non-question skipped honestly
    (R-ROUTE-2). Deterministic supervisor code: the STRATEGY holds the model
    (compose_agent in production, a scripted strategy in tests), and every number
    of record still comes from run_composition + verify_claim inside the loop.

    Ends the run here — it does not fall through to stages 2-5. The verified
    investigation summary (runs/<id>/investigation.json), the recorded fidelity
    skip (runs/<id>/fidelity_route.json), and a DETERMINISTIC write-up
    (runs/<id>/exact_route_report.md, R-ROUTE-5) are the honest artifacts of what
    reproduced. The report is generated by code from the verified numbers — no
    model — so it cannot narrate a value the run did not compute; a model-narrated
    paper over a routed result is a later enhancement."""
    from stages.experiment_report import write_report
    from stages.experiment_route import run_exact_investigation

    strategy = exact_strategy
    if strategy is None:
        from tools.compose_agent import propose_composition_probe
        strategy = propose_composition_probe

    sid = baton.payload.get("substrate_id")
    # The research question for the experimenter (R-DIR-1): the chosen
    # hypothesis' statement, falling back to the domain — whatever the gate left
    # on the payload. Never raises: a missing field just yields None (the
    # experimenter self-directs).
    chosen = baton.payload.get("chosen_hypothesis") or {}
    goal = (chosen.get("statement") if isinstance(chosen, dict) else None) \
        or baton.payload.get("domain")
    logger.log(
        f"EXACT ROUTE: instrument {sid} is exact — the experimenter loop replaces "
        "stages 2-5; fidelity gate skipped as a non-question (R-ROUTE-2)"
    )
    result = run_exact_investigation(strategy, run_id=baton.run_id, goal=goal)
    summary = result["investigation"]
    logger.log(
        f"EXACT ROUTE: investigation ran {summary['iterations']} probe(s), "
        f"{summary['verified']} verified, publishable={result['publishable']}"
    )
    report_path = write_report(result, baton.run_id)
    if report_path is not None:
        logger.log(f"EXACT ROUTE: wrote report -> {report_path.name}")
    how_far = (
        "completed exact-route investigation (publishable)"
        if result["publishable"]
        else "completed exact-route investigation (nothing publishable)"
    )
    record_run_outcome(baton, how_far)
    logger.log(f"=== supervisor run {baton.run_id} {how_far} ===")


def run_relay(logger: Logger, baton: Baton, run_dir: Path, mode: str, stages=None,
              exact_strategy=None) -> None:
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
    forced_exit_reason = None  # R-14-G2: set to "loop_bound" on a cap exit
    # 19-lite/retry build: total-defer retry counter (SEPARATE from
    # loopbacks_used — hard rule c) and the env flag. Flag off (or human mode)
    # => the retry branch is never entered and control flow is byte-identical.
    retry_used = 0
    retry_enabled = mode == "auto" and os.environ.get(RETRY_ON_TOTAL_DEFER_ENV) == "1"
    # DEFAULT ON in both modes (owner instruction) — opt OUT with RETRY_ON_BARREN=0.
    barren_enabled = os.environ.get(RETRY_ON_BARREN_ENV, "1") != "0"
    barren_redesigns_used = 0
    desk_enabled = os.environ.get(RETRY_ON_DESK_REJECT_ENV, "1") != "0"
    desk_redesigns_used = 0
    pending_nudge_restore = _UNSET  # env value to restore after the retried pass
    crash_loopbacks_used = 0  # wide fix: bounded crash -> ideation recoveries
    # Crash recovery mirrors retry_enabled EXACTLY: auto mode + env opt-in only.
    # Off (human mode, or env unset) => the loopback guard is never true and a
    # crash takes the loud terminal halt on the FIRST occurrence.
    crash_recovery_enabled = mode == "auto" and os.environ.get(CRASH_RECOVERY_ENV) == "1"
    i = 0
    while i < len(stages):
        name, stage_fn = stages[i]
        stage_number = i + 1

        try:
            baton = run_single_stage(logger, baton, name, stage_fn)
        except StageCrashed as crash:
            # WIDE FIX (crash recovery): an uncaught stage crash is NOT a hard
            # exit. While budget remains, journal the crash as a dead-end (so
            # the retried ideation round remembers and avoids it) and loop back
            # to stage 1 with the payload reduced to {domain} — the same
            # back_to_ideation shape apply_loopback_surgery produces. This is
            # the "run into a problem -> go back, remember it, avoid it next
            # round" path the owner intended. Budget spent -> the honest
            # terminal halt (memo + crashed run_record + exit 1) that predated
            # this fix, so every run still leaves a run_record.
            if crash_recovery_enabled and crash_loopbacks_used < MAX_CRASH_LOOPBACKS:
                crash_loopbacks_used += 1
                journal_crash_dead_end(logger, baton, crash)
                baton.payload = {"domain": baton.payload["domain"]}
                baton.validate()
                logger.log(
                    f"CRASH-RECOVERY: crash at {crash.stage_name} — looping back "
                    f"to ideation (recovery {crash_loopbacks_used} of "
                    f"{MAX_CRASH_LOOPBACKS}); payload reduced to {{domain}}"
                )
                i = 0
                continue
            first_line = (
                str(crash.original).splitlines()[0] if str(crash.original) else ""
            )
            halt_reason = (
                f"budget spent ({MAX_CRASH_LOOPBACKS})"
                if crash_recovery_enabled
                else "disabled (default; auto+env only)"
            )
            logger.log(
                f"CRASH-RECOVERY: {halt_reason} — honest terminal halt "
                f"at {crash.stage_name}"
            )
            write_failure_memo_safe(logger, run_dir)
            record_run_outcome(
                baton,
                f"crashed at {crash.stage_name}: "
                f"{type(crash.original).__name__}: {first_line}",
            )
            logger.log(
                f"=== supervisor run {baton.run_id} CRASHED at stage "
                f"{crash.stage_name} ==="
            )
            sys.exit(1)
        baton.validate()

        # 19-lite/retry build: the retried ideation pass ran with the nudge
        # forced on; restore the FEASIBILITY_NUDGE env the moment Stage 1
        # (stage_number 1) returns, so the force never leaks past this one pass.
        if pending_nudge_restore is not _UNSET and stage_number == 1:
            if pending_nudge_restore is None:
                os.environ.pop(FEASIBILITY_NUDGE_ENV, None)
            else:
                os.environ[FEASIBILITY_NUDGE_ENV] = pending_nudge_restore
            logger.log("RETRY_ON_TOTAL_DEFER: feasibility nudge env restored after retried Stage 1")
            pending_nudge_restore = _UNSET

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

        # STEP 28: the substrate-maturity routing hook fires the moment the
        # stage-3 verdict is validated, BEFORE stage 4 consumes it. There is
        # no human gate between stage 3 and stage 4, so this is a pure code
        # seam; it may downgrade the verdict (auto mode) and always records
        # the signoff requirement for the run record + the gate-5 display.
        if stage_number == 3:
            apply_substrate_maturity_hook(logger, baton, mode)

        # BARREN-RUN REDESIGN (2026-07-20). Fires the moment stage 4 returns,
        # BEFORE the thought layer or the paper agent can spend a call on a run
        # that measured nothing. A barren run is an executional failure, so it
        # goes back to stage 2 (the spec is what needs fixing — the hypothesis
        # and the chosen instrument were never tested) carrying the verbatim
        # diagnostics. Budget spent => the run ends honestly rather than
        # producing a paper about its own plumbing.
        if stage_number == 4 and barren_enabled and is_barren(baton):
            diagnosis = barren_diagnosis(baton)
            errs = "; ".join(diagnosis["distinct_errors"]) or diagnosis.get("reason") or "?"
            if barren_redesigns_used >= MAX_BARREN_REDESIGNS:
                logger.log(
                    f"BARREN RUN: {diagnosis['runs_attempted']} run(s), 0 with data "
                    f"[{errs}] — redesign budget spent "
                    f"({barren_redesigns_used}/{MAX_BARREN_REDESIGNS}); ending the "
                    "run honestly rather than writing a paper with no data"
                )
                write_failure_memo_safe(logger, run_dir)
                record_run_outcome(baton, "halted_barren_budget_spent", retry_used)
                return
            barren_redesigns_used += 1
            logger.log(
                f"BARREN RUN: {diagnosis['runs_attempted']} run(s) executed, 0 "
                f"produced a value [{errs}] — NOT writing this up; redesigning "
                f"({barren_redesigns_used}/{MAX_BARREN_REDESIGNS}), looping back "
                "to stage 2 with the verbatim execution diagnostics"
            )
            # NON-payload attribute: the payload schema is locked (Step 15), and
            # this rides the same channel as _maturity_signoff. Stage 2 reads it
            # off the baton and composes it into its input.
            baton._barren_diagnosis = diagnosis
            i = apply_loopback_surgery(logger, baton, "back_to_design")
            enforce_boundary_schema(
                logger,
                baton,
                f"gate 1 (barren redesign {barren_redesigns_used})",
                schemas.validate_payload_post_gate1,
            )
            continue

        if i in GATE_AFTER_STAGE_INDEX:
            gate_name = f"after_stage_{stage_number}"
            if gate_name == "after_stage_1":
                outcome = run_gate1(logger, baton, mode)
                if outcome[0] == "halt":
                    logger.log(f"=== supervisor run {baton.run_id} HALTED at gate {gate_name} ===")
                    write_failure_memo_safe(logger, run_dir)
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
                apply_gate1_selection(
                    logger, baton, mode, outcome[1], run_dir, pass_number,
                    substrate_id=outcome[2],
                )
                # Step 15: the post-gate-1 payload is the first locked
                # boundary shape (the ranked-list payload before it is
                # gate-owned, not a stage boundary).
                enforce_boundary_schema(
                    logger,
                    baton,
                    f"gate 1{pass_label}",
                    schemas.validate_payload_post_gate1,
                )
                # PHASE 3 (R-ROUTE-2/3/4): the exact-tool experiment path.
                # Default-on since M1; when gate 1 chose an EXACT instrument (and
                # EXACT_ROUTE is not set to 0), the experimenter loop REPLACES
                # static stages 2-5 and the run ends here. An approximate
                # instrument never enters this branch — it keeps the static
                # pipeline + fidelity gate, byte-identical.
                if exact_route_active() and routed_instrument_is_exact(baton):
                    run_exact_route(logger, baton, run_dir, mode, exact_strategy)
                    return
            elif gate_name == "after_stage_2":
                should_continue = run_gate(logger, baton, mode, gate_name)
                if not should_continue:
                    logger.log(f"=== supervisor run {baton.run_id} HALTED at gate {gate_name} ===")
                    write_failure_memo_safe(logger, run_dir)
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
            else:  # after_stage_5: the iterate decision (Step 16)
                model_decision = baton.payload.get("iterate_decision")
                outcome = run_gate5(logger, baton, mode)
                if outcome[0] == "halt":
                    logger.log(f"=== supervisor run {baton.run_id} HALTED at gate {gate_name} ===")
                    write_failure_memo_safe(logger, run_dir)
                    record_run_outcome(baton, f"halted at gate {gate_name}")
                    sys.exit(0)
                _, enacted, how = outcome
                logger.log(
                    f"GATE after_stage_5 [{mode}]: model={model_decision} "
                    f"enacted={enacted} ({how})"
                )
                # 19-lite/retry build (Step 5): retry-on-total-defer. This gate-5
                # resolution TERMINATES the run when it enacts exit/more_data, or
                # when a loop-back is enacted but the loop bound is already spent
                # (forced exit). If such a terminating resolution is a total
                # defer (0 executed runs, defer verdict) and the flag is on in
                # auto mode with the retry budget unspent, write the memo and
                # loop back to Stage 1 ONCE — feasibility nudge forced on for the
                # retried pass, its env restored the moment that pass's Stage 1
                # returns. loopbacks_used is deliberately untouched (hard rule c).
                terminating = enacted in ("exit", "more_data") or (
                    enacted in ("back_to_design", "back_to_ideation")
                    and loopbacks_used >= MAX_LOOPBACKS
                )
                if (
                    retry_enabled
                    and retry_used < MAX_TOTAL_DEFER_RETRIES
                    and terminating
                    and is_total_defer(baton)
                ):
                    write_failure_memo_safe(logger, run_dir)
                    retry_used += 1
                    pending_nudge_restore = os.environ.get(FEASIBILITY_NUDGE_ENV)
                    os.environ[FEASIBILITY_NUDGE_ENV] = "on"
                    baton.payload = {"domain": baton.payload["domain"]}
                    baton.validate()
                    logger.log(
                        "RETRY_ON_TOTAL_DEFER: total defer (0 executed runs, defer "
                        f"verdict) — retry {retry_used}/{MAX_TOTAL_DEFER_RETRIES}, "
                        "feasibility nudge forced on for the retried Stage 1; "
                        "looping back to stage 1"
                    )
                    i = 0
                    continue
                if enacted == "more_data":
                    logger.log(
                        "MORE_DATA requires Phase-C experimentation intelligence "
                        "(Step 19) — ending run with recommendation"
                    )
                    logger.log(
                        f"=== supervisor run {baton.run_id} ended (more_data, "
                        f"unwired): {len(baton.history)} history entries ==="
                    )
                    write_failure_memo_safe(logger, run_dir)
                    record_run_outcome(baton, "completed_more_data_unwired", retry_used)
                    return
                if enacted in ("back_to_design", "back_to_ideation"):
                    if loopbacks_used >= MAX_LOOPBACKS:
                        # R-14-G2: a cap exit no longer ends on a bare
                        # recommendation. The final baton is routed through
                        # stage 6 + paperlint exactly as a human 'e' (exit)
                        # would — the loop falls through to stage 6 below, and
                        # the end-of-relay block prints the paper path + lint
                        # verdict. The validation sidecar reflects the last
                        # fidelity verdict class (stage 6 reads verdict.json).
                        forced_exit_reason = "loop_bound"
                        fidelity_class = (
                            baton.payload.get("fidelity_verdict") or {}
                        ).get("label")
                        logger.log(
                            f"LOOP BOUND reached ({MAX_LOOPBACKS}) — forced exit: "
                            f"routing final baton through stage 6 "
                            f"(validation sidecar class={fidelity_class})"
                        )
                        # Fall through to stage 6 exactly as 'exit' does.
                    else:
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
                # enacted == "exit" (or a loop-bound forced exit): fall through
                # to stage 6 exactly as before.

        # DESK-REJECTION REDESIGN. Stage 6 already repaired whatever it could
        # by rewriting; reaching here means the editor judged the underlying
        # experiment incapable of supporting a paper. That is an upstream fix,
        # so it loops back to stage 2 carrying the editor's reasons. Budget
        # spent => the paper stands with the rejection recorded beside it,
        # rather than looping forever chasing an editor's approval.
        if stage_number == 6 and desk_enabled:
            review = getattr(baton, "_desk_reject", None)
            if review and review.get("remedy") == "redesign":
                reasons = "; ".join(review.get("reasons") or []) or "?"
                if desk_redesigns_used >= MAX_DESK_REDESIGNS:
                    logger.log(
                        f"DESK REJECT: redesign budget spent "
                        f"({desk_redesigns_used}/{MAX_DESK_REDESIGNS}) — paper "
                        f"stands with the rejection recorded [{reasons}]"
                    )
                else:
                    desk_redesigns_used += 1
                    logger.log(
                        f"DESK REJECT (remedy=redesign): [{reasons}] — "
                        f"redesigning ({desk_redesigns_used}/"
                        f"{MAX_DESK_REDESIGNS}), looping back to stage 2"
                    )
                    baton._barren_diagnosis = {
                        "status": "desk_rejected",
                        "reason": (
                            "A journal editor desk-rejected the paper this "
                            "experiment produced: " + reasons
                        ),
                        "distinct_errors": [],
                        "runs_attempted": 0,
                        "runs_with_data": 0,
                    }
                    baton._desk_reject = None
                    i = apply_loopback_surgery(logger, baton, "back_to_design")
                    enforce_boundary_schema(
                        logger,
                        baton,
                        f"gate 1 (desk redesign {desk_redesigns_used})",
                        schemas.validate_payload_post_gate1,
                    )
                    continue

        i += 1

    # R-14-G2: a loop-bound forced exit routes through stage 6 like a human
    # 'exit', then surfaces the paper path + lint verdict before the run-end
    # line. Stage 6 returning without raising means the paper passed lint.
    if forced_exit_reason == "loop_bound":
        paper_path = run_dir / "stage6" / "paper.md"
        verification = run_verification_pass(logger, baton)
        standing = "stands" if verification.get("publishable") else "DOES NOT STAND"
        logger.log(
            f"FORCED-EXIT (loop_bound): paper -> {paper_path} ; "
            f"lint verdict=clean (stage 6 completed lint-clean) ; "
            f"verification: paper {standing}"
        )
        logger.log(
            f"=== supervisor run {baton.run_id} ended (loop bound, forced exit "
            f"through stage 6): {len(baton.history)} history entries ==="
        )
        write_failure_memo_safe(logger, run_dir)
        record_run_outcome(baton, "completed_loop_bound_forced_exit", retry_used)
        return

    # After stage 6, before the run is declared complete: every number this run
    # would publish must survive an independent re-run of the artifact that
    # produced it.
    verification = run_verification_pass(logger, baton)
    standing = (
        "paper stands (all claims reproduced)"
        if verification.get("publishable")
        else "PAPER DOES NOT STAND (claims unverified)"
    )
    logger.log(
        f"=== supervisor run {baton.run_id} complete: {len(baton.history)} "
        f"history entries; {standing} ==="
    )
    # 19-lite/retry build: a "completed" run that is nonetheless a total defer
    # (defer verdict, nothing executed) is NOT a clean exit — leave a memo. A
    # genuinely clean completion (real execution) gets none.
    if is_total_defer(baton):
        write_failure_memo_safe(logger, run_dir)
    record_run_outcome(baton, "completed", retry_used)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["human", "auto"], default="human")
    parser.add_argument("--domain", required=True, help="the research domain to seed this run with")
    # A caller that dispatches runs as subprocesses (the PI control layer) needs
    # to know the run dir BEFORE the child mints it, so it can read the result
    # back. An explicit --run-id lets the caller choose it; omitted, behavior is
    # byte-identical to before (make_run_id()). A caller-supplied id that
    # collides with an existing run dir is the caller's error — the dir is
    # created with exist_ok, the same as a make_run_id() collision would be.
    parser.add_argument(
        "--run-id",
        default=None,
        help="use this run id (and runs/<run-id>/) instead of a fresh "
        "timestamp; for a controller that must locate the run's evidence",
    )
    args = parser.parse_args()

    run_id = args.run_id or make_run_id()
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = Logger(run_dir / "log.txt")

    logger.log(f"=== supervisor run {run_id} starting in mode={args.mode} ===")

    # The constraint is resolved and announced BEFORE stage 1 composes any
    # prompt, so a malformed one stops the run before it spends a model call,
    # and a valid one is the first thing a reader of log.txt sees.
    from tools import substrate_registry as registry

    _constrained = registry.allowed_constraint()
    if _constrained is not None:
        logger.log(
            f"SUBSTRATE CONSTRAINT: this run may route only to "
            f"{sorted(_constrained)} — permitted set is "
            f"{list(registry.permitted_ids())} "
            f"(from {registry.ALLOWED_SUBSTRATES_ENV})"
        )

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
