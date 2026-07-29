"""pi_agent/free_director.py — free_investigate(): the free director's research
cycle, with a divided budget and an open action space.

This is pi_agent/loop.py's investigate() freed. investigate() runs a flat arc of
four-verb moves under an integer max_moves. free_investigate() runs the same
read→decide→act→record cycle, but the decision comes from the OPEN action space
(pi_agent/free_decider.py) and the ceiling is a Budget (pi_agent/budget.py) that
DIVIDES down a tree — so a spawn_sub_investigation can carve a child a slice that
provably cannot overrun the whole. Built ALONGSIDE investigate() (R-FD-1); the enum
loop is untouched and stays the default until this path is live-validated.

THE CYCLE.
    create the study
    loop:
        if the budget is spent            -> stop (budget_spent)
        if the decision cap is hit        -> stop (decision_cap)  [no-op backstop]
        decide an action (a FULL model turn over the arc + budget) -> or stop
        execute it, spending/allocating budget, and record it in the arc
    write the report

TWO INDEPENDENT TERMINATION BACKSTOPS. The budget bounds real work (every
run_experiment spends a move; a spawn allocates moves to a child). But a director
that only ever picks a not-yet-wired capability spends nothing, so a decision cap —
generous, derived from the budget — bounds total loop turns as a second guarantee,
exactly as budget.max_depth backstops recursion. Neither can be exceeded.

CAPABILITY WIRING. run_experiment, call_integration, and stop are handled in the
loop (call_integration dispatches a joint-verification experiment that assembles the
arc's verified parts — Phase 5). Other non-experiment actions route to
`execute_capability` (default pi_agent.capabilities.execute): call_ideation /
call_validation / call_data_analysis (Phase 3), spawn_sub_investigation, read_memory
and write_memory (Phase 4 / R-FD-5) are ALL LIVE. spawn recurses into a child
free_investigate on a carved budget slice, and only the child's VERIFIED findings
bubble up (the measurement boundary holds at every depth). Nothing is ever faked or
silently dropped.

No measurement is touched here. This layer chooses actions and reads their recorded
outcomes; the sealed execution path and sealed judges are unreachable from it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from model_call import MOVE_ALLOWANCE_ENV, in_process_allowance_ceiling
from pi_agent.budget import Budget
from pi_agent.dispatch import Move, MoveResult, MoveType
from pi_agent.loop import _cost_snapshot, _sum_runs_spend  # identical cost accounting
from pi_agent.study import (STUDIES_ROOT, create_study, load_study, record_move,
                            study_findings)


def _move_allowance(token_budget: Optional[int], spent: Optional[int]) -> Optional[int]:
    """The token allowance a dispatched move gets (item A, 2026-07-28): the
    investigation's whole remaining budget. None when no token budget is set,
    when the meter failed this turn (unknown must not cage the move), or when
    nothing remains (the loop-top ceiling ends the study before dispatching).
    The move-side enforcement lives in model_call (wind-up tool denial +
    derived max_turns + pre-attempt refusal); this is only the hand-off."""
    if not token_budget or spent is None:
        return None
    remaining = token_budget - spent
    return remaining if remaining > 0 else None


def _allowance_env(allowance: Optional[int]) -> Optional[dict]:
    """The env dict carrying the allowance into the run subprocess, or None."""
    return {MOVE_ALLOWANCE_ENV: str(allowance)} if allowance else None


def _fan_member_allowance(allowance: Optional[int], width: int) -> Optional[int]:
    """Each member of an N-wide fan gets an EQUAL SHARE of the move allowance:
    floor(remaining / N). _move_allowance hands one dispatched move the entire
    remainder, which is correct when moves are sequential — with N running at
    once it would over-grant N-fold, and the study could spend N times its
    ceiling inside one fan. None stays None (no budget set, or meter failed —
    unknown must not cage the move)."""
    if not allowance or width < 1:
        return None
    share = allowance // width
    return share if share > 0 else None


# IN-PROCESS CAPABILITIES GET THE SAME CEILING (2026-07-28, system-map defect
# 4.3). run_experiment and call_integration hand their subprocess an allowance;
# the generic capability branch handed nothing, and capabilities.py never
# mentioned one. So call_ideation at depth "full" — measured at 176 model calls
# and 17.5M tokens in one study — cost ONE move and was bounded by nothing.
#
# spawn_sub_investigation is DELIBERATELY ABSENT. A child director carries a
# TRANSFERRED move budget and runs the same three termination checks itself, so
# it is already bounded; and an environment ceiling held across it would also
# gate the child's own decider call, which is the one call that must never be
# refused — a director that cannot decide cannot stop honestly either.
# read_memory / write_memory make no model calls, so an allowance there would
# be dead weight.
_ALLOWANCE_CAPABILITIES = frozenset({
    "call_ideation", "call_validation", "call_data_analysis",
})


@contextlib.contextmanager
def _capability_allowance(name: str, token_budget: Optional[int],
                          spent: Optional[int]):
    """Bind the study's remaining token room to an in-process capability call.

    The subprocess route (`extra_env` on a Move) cannot reach here: a
    capability runs in THIS process, so the allowance has to sit on this
    process's own environment while the call is in flight and come off again
    afterwards — the director's next decider call must not inherit it, and
    neither must anything else in the loop.

    The VALUE is not the remaining budget: MOVE_ALLOWANCE_ENV is an absolute
    ceiling on the reading process's face-value spend, and this process's meter
    already carries the whole study (see model_call.in_process_allowance_ceiling).

    NEVER RAISES, in either direction. Accounting may not sink a capability, so
    a failure to set the ceiling simply leaves the call uncapped — the same way
    a broken meter disables the allowance rather than fabricating exhaustion —
    and the restore runs in a finally."""
    ceiling = None
    if name in _ALLOWANCE_CAPABILITIES and token_budget and spent is not None:
        try:
            ceiling = in_process_allowance_ceiling(token_budget - spent)
        except Exception:  # noqa: BLE001 — a broken knob must widen, never cage
            ceiling = None
    if ceiling is None:
        yield None
        return
    previous = os.environ.get(MOVE_ALLOWANCE_ENV)
    try:
        os.environ[MOVE_ALLOWANCE_ENV] = str(ceiling)
        yield ceiling
    finally:
        if previous is None:
            os.environ.pop(MOVE_ALLOWANCE_ENV, None)
        else:
            os.environ[MOVE_ALLOWANCE_ENV] = previous


def _allowance_sentence(allowance: Optional[int]) -> str:
    """The brief paragraph telling the dispatched agent its room, so the
    ceiling is something it plans around rather than a wall it hits. Empty
    when no allowance is set — the brief is then byte-identical."""
    if not allowance:
        return ""
    return (
        f"\n\nTOKEN ALLOWANCE FOR THIS MOVE: ~{allowance:,} tokens (face-value "
        "sum over every usage field, cache reads included). Scale the "
        "investigation to it and wind up deliberately — finish measuring, "
        "verify, and report before it runs out. If it is exhausted mid-work, "
        "tool access is withdrawn and you must immediately write your honest "
        "final answer from what you have; an honest partial answer is expected "
        "then, not a failure."
    )


def _move_from_action(action: dict, study: Any, allowance: Optional[int] = None) -> Move:
    """Build the dispatchable Move from a run_experiment action. A campaign flag
    selects the iterated sweep; a named instrument narrows the run to it (else the
    run chooses from the study's permitted set).

    The question travels as a full BRIEF (_brief): the study goal, what is already
    established, why this experiment now, the freedom to deviate, and the verified
    file producers to build on. A run used to receive one line and no idea what
    investigation it belonged to.

    `allowance` (item A) is the move's token allowance: it rides both the env
    (where model_call enforces it) and the brief (where the agent reads it).
    """
    instrument = action.get("instrument")
    mtype = MoveType.CAMPAIGN if action.get("campaign") else MoveType.SINGLE
    return Move(
        type=mtype,
        domain=_brief(action["domain"], study, action, allowance=allowance),
        mode=study.mode,
        allowed_substrates=[instrument] if instrument else None,
        extra_env=_allowance_env(allowance),
    )


def _record_capability(study: Any, action_name: str, seq: int, result: dict, finding: str) -> None:
    """Record a non-experiment action to the arc via the same record_move path the
    runs use, so the next decision reads it uniformly. Wrapped as a MoveResult
    whose move_type is the action and whose raw carries the capability result.
    A result that came through capabilities.execute carries its own metered
    {"cost": {calls, tokens}}, which record_move maps onto the arc's cost column;
    a result recorded directly (a refusal, a guarded failure) carries none, and
    its cost honestly reads as unknown rather than zero."""
    record_move(
        study,
        MoveResult(
            move_type=action_name,
            run_id=f"{study.study_id}-cap{seq}",
            succeeded=bool(result.get("succeeded")),
            outcome=result.get("outcome"),
            raw=result,
        ),
        finding=finding,
    )


def _integration_context(study: Any) -> dict:
    """What an integration check has to compose: the VERIFIED scalar findings across
    the arc (parts) AND the reproduced reusable FILE artifacts (files), including
    those bubbled up from sub-investigations and those INHERITED from the spawning
    study. A part that did not reproduce is not something to build an assembly on,
    so only verified ones count (the measurement boundary: an integration composes
    re-run numbers and re-runnable file producers, never narration or stored bytes).

    Arc artifacts are collected BEFORE inherited ones and dedup is first-wins, so a
    file this study regenerated supersedes the version it inherited — which is what
    iterative work needs: the newest version of a design is the one that carries.
    """
    parts, files, seen = [], [], set()
    for entry in study_findings(study):
        for f in entry.get("results", []) or []:
            if isinstance(f, dict) and f.get("verified"):
                parts.append({"label": f.get("label"), "value": f.get("value"),
                              "from": entry.get("run_id")})
        for ra in entry.get("reusable_artifacts", []) or []:
            if isinstance(ra, dict) and ra.get("name") and ra["name"] not in seen:
                seen.add(ra["name"])
                files.append({"name": ra["name"], "producer": ra.get("producer")})
    for ra in getattr(study, "inherited_artifacts", None) or []:
        if isinstance(ra, dict) and ra.get("name") and ra["name"] not in seen:
            seen.add(ra["name"])
            files.append({"name": ra["name"], "producer": ra.get("producer")})
    return {"parts": parts, "files": files}


# The carry bus (artifact hand-off). A phase that built something must be able to
# hand the THING to the next phase, not just the number it scored — otherwise every
# move rebuilds the world from a sentence and nothing compounds. The mechanism
# already existed for call_integration; this extends the same producers-not-bytes
# hand-off to run_experiment and spawn_sub_investigation.
#
# Bounded so a long arc cannot grow the question without limit; the newest
# artifacts (arc before inherited, see _integration_context) survive the cap.
MAX_CARRIED_FILES = 8


def _carry_block(files: list) -> str:
    """The prose that hands re-runnable file producers to a dispatched move. Same
    contract as _integration_domain's file clause: the file travels as a PRODUCER
    the receiver re-runs, never as a stored copy, so a carried artifact is
    reproducible at every hop. Empty string when there is nothing to carry (the
    caller then leaves the question byte-identical)."""
    carried = (files or [])[:MAX_CARRIED_FILES]
    if not carried:
        return ""
    producers = json.dumps(
        [{"name": f.get("name"), "producer": f.get("producer")} for f in carried]
    )
    return (
        "\n\nWORK ALREADY BUILT AND VERIFIED, handed to you to BUILD ON. Each is a "
        "re-runnable producer: INLINE it as a step to regenerate the file in your "
        "workspace (never assume a stored copy is present), then build on the "
        f"result instead of starting from scratch: {producers}"
    )


def _carry_domain(domain: str, study: Any) -> str:
    """The question a dispatched move actually receives: the director's question
    plus the study's carried file producers. Byte-identical to `domain` when the
    study has carried nothing — a first move in a fresh study is unchanged."""
    return domain + _carry_block(_integration_context(study)["files"])


# How many established results travel into a brief. Bounded so a long study does
# not bury the question it is asking.
MAX_BRIEFED_FINDINGS = 12


def _brief(domain: str, study: Any, action: dict,
           allowance: Optional[int] = None) -> str:
    """The full briefing a dispatched experiment receives.

    A run used to get ONE LINE — the director's question, nothing else. It did not
    know the study's goal, what had already been established, or why it was being
    asked this now. A researcher handing work to a colleague would never do that,
    and a Claude Code session started by a human gets far more context than this,
    which is the floor the experimenter must never fall below.

    Everything here is information the director ALREADY produces (the goal, the
    arc's verified findings, its own reasoning and reading), so no action-schema
    change is needed — it was simply being thrown away at the door. Pure over its
    inputs; never raises."""
    context = _integration_context(study)
    parts = [domain, "\n\n---\nCONTEXT FOR THIS EXPERIMENT (you are one move of a "
                     "larger investigation):"]
    parts.append(f"\n\nTHE OVERALL GOAL: {study.goal}")

    established = context["parts"][:MAX_BRIEFED_FINDINGS]
    if established:
        lines = "".join(
            f"\n  - {p.get('label')} = {p.get('value')}" for p in established)
        parts.append(
            "\n\nALREADY ESTABLISHED (each independently re-run and reproduced — "
            f"treat as settled, do not redo):{lines}")
    else:
        parts.append("\n\nALREADY ESTABLISHED: nothing yet — this is the first "
                     "result the investigation will have.")

    reading = action.get("reading")
    if isinstance(reading, str) and reading.strip():
        parts.append(f"\n\nWHAT THE LAST MOVE SHOWED: {reading.strip()}")

    reasoning = action.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        parts.append(f"\n\nWHY THIS EXPERIMENT, NOW: {reasoning.strip()}")

    parts.append(
        "\n\nYou are not restricted to the literal question above — it is what the "
        "investigation needs, not a script. If the honest answer requires a "
        "different measurement, a cheaper probe first, or reporting that the "
        "question is malformed, do that and say so.")
    parts.append(_allowance_sentence(allowance))
    parts.append(_carry_block(context["files"]))
    return "".join(parts)


def _integration_domain(goal: str, detail: Optional[str], context: dict) -> str:
    """Frame the integration experiment. The verified parts and the reproducible
    file PRODUCERS travel in the question so the run's experimenter authors a probe
    that ASSEMBLES them — inlining each producer to regenerate the file (never a
    stored copy) — and the wall verifies the joint number, which stands only if the
    parts are actually compatible together, not merely each valid alone."""
    crit = f" Joint criterion: {detail}." if detail else ""
    parts = "; ".join(f"{p['label']}={p['value']}" for p in context["parts"])
    lines = [
        f"Integration check for the goal: {goal}.{crit}",
        f"Independently-verified subsystem results: {parts}." if parts else "",
    ]
    if context["files"]:
        producers = json.dumps([
            {"name": f["name"], "producer": f["producer"]} for f in context["files"]
        ])
        lines.append(
            "Reusable FILES from the sub-investigations, each as a re-runnable "
            "producer you should INLINE as a step (regenerate the file, never assume "
            f"a stored copy): {producers}."
        )
    lines.append(
        "Author a probe that ASSEMBLES these parts (and files) and measures whether "
        "they compose into a working whole — a joint quantity that stands only if "
        "the parts are compatible together, not merely each valid alone. Report the "
        "joint measurement and whether the assembly meets the goal."
    )
    return " ".join(line for line in lines if line)


# The director's decision call is provably side-effect-free — it returns a JSON
# action and writes a decision record — so replaying it after a transport failure
# is safe, unlike the experimenter's tooled calls. Short backoffs: an SDK/CLI
# hiccup usually clears immediately.
DECIDE_RETRY_BACKOFFS = (2, 5, 10)
# How many CONSECUTIVE turns may fail to produce a decision before the arc ends.
# A director that cannot think at all has nothing left to steer with, but one bad
# turn is not that.
MAX_CONSECUTIVE_DECIDER_FAILURES = 3


def _decide_with_retry(decide_action, study, arc, budget_report):
    """Ask the director for one decision, retrying a transport failure. Raises the
    last exception if every attempt fails; the caller records it and lets the next
    turn try again."""
    import time
    last = None
    for attempt in range(1 + len(DECIDE_RETRY_BACKOFFS)):
        try:
            return decide_action(study, arc, budget_report)
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == len(DECIDE_RETRY_BACKOFFS):
                break
            print(f"DECIDE-RETRY attempt={attempt + 1} {type(e).__name__}: {e}")
            time.sleep(DECIDE_RETRY_BACKOFFS[attempt])
    raise last


def _survive(study: Any, action_name: str, seq: int, finding: Optional[str], fn,
             failure_extra: Optional[dict] = None):
    """Run one dispatched action so that NOTHING BELOW IT CAN END THE ARC.

    OWNER RULING 2026-07-25: nothing may kill an arc except the director. Before
    this, neither run_move nor execute_capability was guarded, so any exception
    anywhere beneath them — a screening stage raising on zero survivors, a
    validator KeyError, a model door giving up after its re-asks, a substrate
    blowing up — propagated out of the loop and killed the whole study, losing
    every verified result already in the arc. Both live crashes took that path.

    A tool that fails is a RESULT, not a fatality: the failure is recorded to the
    arc with its error text, and the director reads it on its next turn and
    decides — retry differently, route around it, or stop. That is the same
    judgment a researcher makes when an instrument breaks, and it belongs to the
    director alone. Returns True when the action ran, False when it failed.

    `failure_extra` rides into the failure record verbatim (e.g. a fan's spent
    width, so resume accounting can reconstruct what the failure cost)."""
    try:
        fn()
        return True
    except Exception as e:  # noqa: BLE001 — the whole point is that nothing escapes
        detail = f"{type(e).__name__}: {e}"
        # Say so loudly. A dying child subprocess prints its own traceback to the
        # shared terminal, which is indistinguishable from a fatal error — it
        # convinced the owner a healthy run had died. This line is what tells a
        # watcher the difference.
        print(f"MOVE FAILED ({action_name}): {detail} — recorded to the arc; "
              f"the director continues. This is NOT a fatal error.")
        _record_capability(
            study, action_name, seq,
            {"succeeded": False, "outcome": f"{action_name}_failed", "error": detail,
             "detail": f"this action raised and was recorded instead of ending the "
                       f"investigation — {detail}",
             **(failure_extra or {})},
            finding,
        )
        return False


# --------------------------------------------------------------------------
# RESUMABILITY (item B, 2026-07-28): a long run's likeliest death is a usage
# window five hours in — that happened once and lost everything, although the
# arc was fully on disk. Resume is RECONSTRUCTION from that evidence, not new
# state to persist: relaunch against the existing study id, rebuild the arc,
# spend and budget from disk, and continue from the next move. Completed moves
# are never re-run (the arc IS the director's memory), and a move whose run
# finished after the director died is recovered from its run evidence rather
# than re-dispatched. Move granularity only — no resuming inside a move.
# --------------------------------------------------------------------------

def _recover_orphan_runs(study: Any, runs_root: Path) -> int:
    """Record runs the dead director dispatched but never read back.

    A move's run is a SUBPROCESS with its own lifetime ("Sessions and Terminal
    runs have independent lifetimes"): when the director dies mid-move, the run
    may still have completed and journaled — but record_move never fired, so
    the arc has no entry and a naive resume would mint the same run id again
    and RE-RUN a finished move. Every runs/<study>-m<N> dir absent from the arc
    is read back through the same evidence path a live dispatch uses
    (read_run_result: journal run_record + verification.json) and recorded as
    move_type "recovered_run". A run that died without journaling is recorded
    as an honest orphaned outcome — a readable entry, never a re-run and never
    an invented result. Returns how many entries were recovered."""
    from pi_agent.dispatch import _fetch_run_record, read_run_result

    recorded = {e.get("run_id") for e in study_findings(study)}
    pattern = re.compile(re.escape(study.study_id) + r"-m(\d+)$")
    orphans = []
    try:
        for d in Path(runs_root).iterdir():
            m = pattern.fullmatch(d.name)
            if m and d.is_dir() and d.name not in recorded:
                orphans.append((int(m.group(1)), d))
    except OSError:
        return 0
    for _n, run_dir in sorted(orphans):
        run_id = run_dir.name
        run_record = _fetch_run_record(run_id)
        result = read_run_result(run_dir, run_id, 0 if run_record else 1,
                                 run_record)
        outcome = result.outcome or (
            "orphaned_run (no run_record — the run died with the director; "
            "recorded on resume, not re-run)")
        record_move(
            study,
            MoveResult("recovered_run", run_id, bool(result.publishable),
                       outcome, result.as_dict()),
            finding="recovered from disk evidence on resume — this move ran "
                    "before the director's process died and is not re-run",
        )
    return len(orphans)


# Arc rows that consumed one move from the pool. The _survive failure rows keep
# the ACTION name as move_type, and run_experiment/call_integration spend
# BEFORE dispatching, so a failed one still consumed its move.
#
# "run_fan" here is the fan's _survive FAILURE row only (a successful fan
# records one "single" row per member, counted individually above). The fan
# spent its full width BEFORE dispatching, so the failure row carries
# fan_width and _moves_consumed counts that — possibly over-counting when some
# members recorded before the raise (they count again as "single" rows), which
# is the deliberate conservative direction: over-counting only shrinks the
# structural backstop, while under-counting would let a resumed tree exceed
# the total the human set.
_MOVE_CONSUMING_TYPES = ("single", "campaign", "recovered_run",
                        "run_experiment", "run_fan", "call_integration",
                        "call_ideation", "call_validation", "call_data_analysis")
# Outcomes recorded before any spend happened — honest refusals, zero cost.
_UNSPENT_OUTCOMES = ("insufficient_budget", "integration_nothing_to_compose",
                     "spawn_invalid_budget", "spawn_depth_cap")


def _moves_consumed(arc: list, studies_root: Path) -> int:
    """How many moves the recorded arc consumed from the pool — the resume-side
    mirror of the loop's spend/allocate calls, reconstructed from evidence.
    Deliberately CONSERVATIVE where the arc under-determines it (a failure row
    whose spend cannot be known counts as spent; a spawn whose exact slice is
    unrecoverable falls back to what the child demonstrably ran): over-counting
    only shrinks the structural backstop, while under-counting would let a
    resumed tree exceed the total the human set."""
    consumed = 0
    for e in arc:
        if not isinstance(e, dict):
            continue
        mtype = e.get("move_type")
        outcome = str(e.get("outcome") or "")
        if any(marker in outcome for marker in _UNSPENT_OUTCOMES):
            continue
        if mtype == "run_fan":
            # The fan's failure row: the whole width was spent before dispatch.
            width = (e.get("tool_output") or {}).get("fan_width")
            consumed += width if isinstance(width, int) and width > 0 else 1
        elif mtype in _MOVE_CONSUMING_TYPES:
            consumed += 1
        elif mtype == "spawn_sub_investigation":
            consumed += _spawn_allocation(e, studies_root)
    return consumed


def _spawn_allocation(entry: dict, studies_root: Path) -> int:
    """The moves a spawn row transferred to its child: the child's own
    report.json records the slice it was constructed with
    (budget_final.total_at_node); fall back to the moves it demonstrably ran,
    then to 1 — a spawn that got as far as a child study cost something."""
    tool_output = entry.get("tool_output") or {}
    child_id = tool_output.get("child_study_id")
    if isinstance(child_id, str) and child_id:
        report = None
        try:
            report = json.loads(
                (Path(studies_root) / child_id / "report.json").read_text())
        except Exception:  # noqa: BLE001 — a child that died wrote no report
            pass
        if isinstance(report, dict):
            total = (report.get("budget_final") or {}).get("total_at_node")
            if isinstance(total, int) and total > 0:
                return total
    ran = tool_output.get("child_moves_run")
    if isinstance(ran, int) and not isinstance(ran, bool) and ran > 0:
        return ran
    return 1


def _prior_arc_tokens_outside_runs(arc: list) -> int:
    """Token spend recorded on arc rows that _tokens_spent will NOT count:
    capability rows and recovered runs. Live, their spend sits in this
    process's meter delta; after a resume the meter restarted at zero, so
    without this constant offset the whole prior in-process spend would vanish
    from the ceiling. Computed ONCE at resume over the arc as it stands —
    rows recorded after that go through the live accounting, never both."""
    total = 0
    for e in arc:
        if not isinstance(e, dict) or e.get("move_type") in ("single", "campaign"):
            continue
        cost = e.get("cost")
        if isinstance(cost, dict):
            t = cost.get("tokens")
            if isinstance(t, int) and not isinstance(t, bool):
                total += t
    return total


def _tokens_spent(arc: list, spend_start: dict) -> int:
    """Real tokens spent by this investigation so far: this process's own model
    calls (director decisions plus in-process capabilities like ideation) plus
    every dispatched run's persisted cost, read back off the arc. Same accounting
    _build_report does at the end — computed per turn so the director can see it
    while it still has decisions left to make. Never raises.

    (Item B: a RESUMED study's prior in-process spend is a separate constant
    the caller adds on top — the signature here stays two-argument because
    test fakes patch it as such, and adding an offset to an unknown spend must
    stay unknown, which the call site preserves.)"""
    try:
        now = _cost_snapshot()
        mine = max(0, now.get("tokens", 0) - spend_start.get("tokens", 0))
        # Subprocess (experiment) moves only: a capability row's metered cost
        # came out of THIS process's meter and is already inside `mine` —
        # summing the whole arc would count it twice, every turn.
        runs = [e for e in arc if isinstance(e, dict)
                and e.get("move_type") in ("single", "campaign")]
        return mine + (_sum_runs_spend(runs) or {}).get("tokens", 0)
    except Exception as e:  # noqa: BLE001 — accounting must not sink a decision
        # RETURNING 0 HERE IS ACTIVELY DANGEROUS, so say so rather than lie
        # quietly. A 0 both disables the ceiling below (`spent >= token_budget`
        # can never fire) and tells the director `tokens_spent: 0` every turn —
        # encouraging maximum depth at the exact moment metering has broken. The
        # accounting still must not sink a decision, so this stays non-fatal;
        # None is the honest value, and the two readers treat it as "unknown"
        # rather than "nothing spent".
        print(f"NOTE: token accounting failed ({type(e).__name__}: {e}) — spend "
              "is UNKNOWN this turn, not zero; the token ceiling cannot be "
              "enforced until it recovers")
        return None


def _budget_view(budget: Budget, tokens_spent: int, token_budget: Optional[int]) -> dict:
    """What the director is shown about its own ceiling. The move pool is the
    structural bound — it guarantees termination and divides for spawns — but
    MOVES ARE A POOR PROXY FOR COST: measured live, a 2-move study cost 55M tokens
    while a 4-move one cost 15.9M, because a single experimenter call runs an
    agentic loop of up to 200 turns. So when a token budget is set it is shown as
    the real constraint, and the director scales depth to it."""
    view = dict(budget.report())
    view["tokens_spent"] = tokens_spent
    if token_budget:
        view["token_budget"] = token_budget
        if tokens_spent is None:
            # UNKNOWN IS NOT ZERO. Showing a spend of 0 with a full remaining
            # budget would invite the director to scale UP precisely when the
            # meter has failed. Told plainly instead, so it can be conservative.
            view["tokens_spent"] = "unknown — token accounting failed this turn"
            view["note"] = (
                "tokens are the REAL ceiling for this investigation, but the "
                "meter FAILED this turn: spend is unknown, not zero, and the "
                "ceiling cannot be enforced right now. Treat remaining budget as "
                "unknown and prefer finishing what is started over decomposing "
                "further."
            )
            return view
        view["tokens_remaining"] = max(0, token_budget - tokens_spent)
        view["fraction_of_token_budget_used"] = round(tokens_spent / token_budget, 3)
        view["note"] = (
            "tokens are the REAL ceiling for this investigation; the move pool is a "
            "structural backstop. Scale your ambition to tokens_remaining."
        )
    return view


def _decision_cap(budget: Budget, override: Optional[int]) -> int:
    """The backstop on total loop turns. Generous vs the budget so real work is
    never starved, but finite so a director looping on unwired capabilities cannot
    spin forever. Derived from the budget's initial total."""
    if override is not None:
        return override
    total = budget.report()["total_at_node"]
    return total * 3 + 10


def free_investigate(
    goal: str,
    *,
    budget: Budget,
    allowed_substrates: Optional[list] = None,
    mode: str = "auto",
    ceiling: Optional[dict] = None,
    study_id: Optional[str] = None,
    parent_study_id: Optional[str] = None,
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = Path("runs"),
    inherited_artifacts: Optional[list] = None,
    token_budget: Optional[int] = None,
    max_decisions: Optional[int] = None,
    resume: bool = False,
    decide_action: Callable = None,
    run_move: Callable = None,
    run_fan: Callable = None,
    execute_capability: Callable = None,
) -> dict:
    """Run one free-director investigation to completion and return its report.

    `inherited_artifacts` are the spawning study's verified file producers, handed
    down so this study's moves build on work an earlier phase already did rather
    than reconstructing it from prose (the carry bus; None for a root study).

    `budget` is the Budget (Phase 1) — the hard, divisible ceiling. `decide_action`
    (default pi_agent.free_decider.decide_action) is the open-action-space model
    brain; `run_move` (default pi_agent.study.run_study_move) dispatches and records
    an experiment; `run_fan` (default pi_agent.study.run_study_fan) dispatches a
    run_fan action's members concurrently and records each in the arc;
    `execute_capability` (default _unwired_capability) runs the
    non-experiment actions — all injected so the whole loop is exercisable offline
    with fakes and the real path is proven with only the model transport faked.

    `resume=True` (item B, 2026-07-28) relaunches against an EXISTING study id:
    the study identity, arc and spend are rebuilt from disk (see the RESUMABILITY
    block above), orphaned runs are recovered rather than re-run, the caller's
    fresh `budget` is debited by what the arc shows consumed, and the loop
    continues from the next move. `goal` may be None then — the study's recorded
    goal is the authority; `study_id` is required.

    Returns a report dict (also written to studies/<id>/report.json).
    """
    if decide_action is None:
        from pi_agent.free_decider import decide_action as decide_action
    if run_move is None:
        from pi_agent.study import run_study_move as run_move
    if run_fan is None:
        from pi_agent.study import run_study_fan as run_fan
    if execute_capability is None:
        from pi_agent.capabilities import execute as execute_capability

    prior_tokens = 0
    resumed_state = None
    if resume:
        if not study_id:
            raise ValueError("resume=True requires the study_id to resume.")
        study = load_study(study_id, studies_root=studies_root)
        recovered = _recover_orphan_runs(study, runs_root)
        arc0 = study_findings(study)
        consumed = _moves_consumed(arc0, studies_root)
        # Debit the fresh pool by what the arc shows consumed; a study that
        # already spent its whole budget resumes straight into an honest
        # budget_spent termination rather than getting a second budget.
        budget.spend(min(consumed, budget.remaining()))
        prior_tokens = _prior_arc_tokens_outside_runs(arc0)
        resumed_state = {"resumed": True, "arc_entries_at_resume": len(arc0),
                         "orphan_runs_recovered": recovered,
                         "moves_reconstructed_as_consumed": consumed,
                         "prior_in_process_tokens_reconstructed": prior_tokens}
        print(f"RESUME {study.study_id}: {len(arc0)} arc entrie(s) on disk "
              f"({recovered} orphaned run(s) recovered, not re-run), "
              f"{consumed} move(s) reconstructed as consumed, "
              f"budget remaining {budget.remaining()}")
    else:
        study = create_study(
            goal,
            allowed_substrates=allowed_substrates,
            mode=mode,
            study_id=study_id,
            studies_root=studies_root,
            parent_study_id=parent_study_id,
            inherited_artifacts=inherited_artifacts,
        )
    spend_start = _cost_snapshot()
    cap = _decision_cap(budget, max_decisions)

    termination = None
    decisions = 0
    decider_failures = 0
    while True:
        arc = study_findings(study)

        spent = _tokens_spent(arc, spend_start)
        # Item B: a resumed study's prior in-process spend (reconstructed once
        # from the arc at resume) rides on top. Unknown stays unknown: a failed
        # meter's None must not become a number just because an offset exists.
        if spent is not None:
            spent += prior_tokens
        # `spent is None` means the meter failed, not that nothing was spent — so
        # the ceiling does not fire on it (a broken meter must not end a healthy
        # investigation either). The failure is printed and shown in the budget
        # view; the move pool is the backstop while it lasts.
        if token_budget and spent is not None and spent >= token_budget:
            termination = {
                "reason": "token_budget_spent",
                "detail": f"the token budget is spent ({spent:,} of {token_budget:,} "
                          "tokens). This is the real ceiling; the move pool was a "
                          "structural backstop.",
            }
            break

        if budget.remaining() <= 0:
            termination = {
                "reason": "budget_spent",
                "detail": f"the move budget is spent ({budget.report()})",
            }
            break
        if decisions >= cap:
            termination = {
                "reason": "decision_cap",
                "detail": f"the decision backstop of {cap} turns was reached — "
                "the director made no further progress (likely looping on an "
                "unwired capability).",
            }
            break

        decisions += 1
        try:
            action = _decide_with_retry(
                decide_action, study, arc,
                _budget_view(budget, spent, token_budget))
            decider_failures = 0
        except Exception as e:  # noqa: BLE001
            # A TRANSPORT HICCUP MUST NOT END A STUDY. This used to break out of
            # the loop on the first failure, and live (study-20260726T063702Z) an
            # SDK error — "Claude Code returned an error result: success", the
            # CLI subprocess exiting non-zero — ended an investigation that had
            # already decomposed, carried artifacts across phases, and found a
            # real composition failure. Six moves of budget were left.
            #
            # It is also why model_call's transport retry did not help: that
            # retry is disabled for TOOLED calls because replaying an agentic
            # loop can re-commit side effects. Sound for the experimenter, which
            # writes files and runs solvers — wrong for the director, whose call
            # produces a JSON decision and nothing else, so replay is safe. Hence
            # the retry here, at the one call site where idempotence is provable.
            #
            # After retries are exhausted the failure is RECORDED and the loop
            # continues, so the next turn tries again. Only repeated consecutive
            # failures end the arc, because a director that cannot think at all
            # has nothing left to steer with.
            decider_failures += 1
            _record_capability(
                study, "decide", decisions,
                {"succeeded": False, "outcome": "decision_failed",
                 "error": f"{type(e).__name__}: {e}",
                 "detail": "the director could not produce a decision this turn "
                           f"({type(e).__name__}); retrying on the next turn."},
                None,
            )
            if decider_failures >= MAX_CONSECUTIVE_DECIDER_FAILURES:
                termination = {
                    "reason": "director_failed",
                    "detail": (
                        f"the free director failed to produce a decision "
                        f"{decider_failures} turns in a row: {type(e).__name__}: {e}. "
                        "REPEATED transport failures this early usually mean a "
                        "USAGE LIMIT rather than a bug — check your plan's limits "
                        "(/usage in a Claude Code session) before re-running. The "
                        "retry backoffs here are seconds, which cannot outwait a "
                        "multi-hour window; re-launch once the window resets."
                    ),
                }
                break
            continue

        name = action.get("action")
        finding = action.get("reasoning")

        if name == "stop":
            termination = {
                "reason": "director_judged_complete",
                "detail": action.get("stop_reason"),
            }
            break

        if name == "run_experiment":
            # Guard: never start a move the budget cannot cover. If the director
            # asked for one it cannot afford, record the honest refusal and let it
            # choose again (it may still spawn/stop within a spent budget only via
            # the top-of-loop budget check next turn).
            if not budget.can_spend(1):
                _record_capability(
                    study, "run_experiment", decisions,
                    {"succeeded": False, "outcome": "insufficient_budget",
                     "detail": "no moves remain to run an experiment."},
                    finding,
                )
                continue
            budget.spend(1)
            # Item A: the move carries the remaining token budget as its own
            # allowance, enforced inside the run by model_call (wind-up tool
            # denial, derived max_turns, pre-attempt refusal) — the ceiling
            # now binds inside a move, not only between moves.
            move_allowance = _move_allowance(token_budget, spent)
            _survive(study, "run_experiment", decisions, finding,
                     lambda: run_move(
                         study,
                         _move_from_action(action, study, allowance=move_allowance),
                         finding=finding, runs_root=runs_root))
            continue

        if name == "run_fan":
            # A1 (2026-07-29): several experiments dispatched CONCURRENTLY —
            # the attack on wall-clock serialism, the real ceiling on a long
            # study (every move is ~1 hour, strictly sequential before this).
            # run_study_fan is the finished concurrency-safe machinery the enum
            # loop already used; this wires it to the free director. An N-wide
            # fan spends N moves (budget conservation — one of the few hard
            # guarantees), and each member gets an EQUAL SHARE of the token
            # allowance (_fan_member_allowance), since handing each the whole
            # remainder would over-grant N-fold. Each member is recorded in the
            # arc as its own ordinary "single" entry, so nothing downstream
            # (cost report, liveview, resume) learns a new shape.
            domains = [d for d in (action.get("fan_domains") or [])
                       if isinstance(d, str) and d.strip()]
            width = min(len(domains), budget.remaining())
            if width <= 0:
                _record_capability(
                    study, "run_fan", decisions,
                    {"succeeded": False, "outcome": "insufficient_budget",
                     "detail": "no moves remain to run a fan."},
                    finding,
                )
                continue
            if width < len(domains):
                # Clamped to the pool, like the enum loop — said out loud so a
                # watcher (and the arc reader) knows members were dropped.
                print(f"FAN CLAMPED: {len(domains)} questions asked, "
                      f"{width} moves remain — dispatching the first {width}.")
            domains = domains[:width]
            budget.spend(width)
            member_allowance = _fan_member_allowance(
                _move_allowance(token_budget, spent), width)
            fan_moves = [
                Move(type=MoveType.SINGLE,
                     domain=_brief(d, study, action, allowance=member_allowance),
                     mode=study.mode,
                     extra_env=_allowance_env(member_allowance))
                for d in domains
            ]
            _survive(study, "run_fan", decisions, finding,
                     lambda: run_fan(
                         study, fan_moves,
                         findings=[finding] * len(fan_moves),
                         runs_root=runs_root),
                     failure_extra={"fan_width": width})
            continue

        if name == "call_integration":
            # Joint verification (Phase 5): dispatch a real experiment that
            # ASSEMBLES the verified parts and measures whether they compose. The
            # parts each already re-ran (per-number verification); an integration
            # check catches what re-running each part cannot — "each locally
            # optimal, the assembly incompatible." It IS an experiment (verified by
            # the wall), so it goes through run_move and spends a move.
            context = _integration_context(study)
            if not context["parts"] and not context["files"]:
                _record_capability(
                    study, "call_integration", decisions,
                    {"succeeded": False, "outcome": "integration_nothing_to_compose",
                     "detail": "no verified findings or reusable files yet to "
                     "integrate — run experiments or sub-investigations first."},
                    finding,
                )
                continue
            if not budget.can_spend(1):
                _record_capability(
                    study, "call_integration", decisions,
                    {"succeeded": False, "outcome": "insufficient_budget",
                     "detail": "no moves remain to run an integration check."},
                    finding,
                )
                continue
            budget.spend(1)
            # Item A: an integration run is a dispatched experiment too — it
            # gets the same allowance hand-off as run_experiment.
            move_allowance = _move_allowance(token_budget, spent)
            domain = (_integration_domain(study.goal, action.get("detail"), context)
                      + _allowance_sentence(move_allowance))
            instrument = action.get("instrument")
            _survive(
                study, "call_integration", decisions, finding,
                lambda: run_move(
                    study,
                    Move(type=MoveType.SINGLE, domain=domain, mode=study.mode,
                         allowed_substrates=[instrument] if instrument
                         else study.allowed_substrates,
                         extra_env=_allowance_env(move_allowance)),
                    finding=finding or "integration check", runs_root=runs_root,
                ))
            continue

        # call_ideation / call_validation / call_data_analysis (Phase 3, live) and
        # spawn_sub_investigation + memory (Phase 4, not-yet-wired): routed to the
        # capability executor, which spends its own budget and returns a recorded
        # result. seq (the decision count) gives each capability run a unique id.
        # A capability that RAISES must not end the arc either — the executor
        # returns honest failure dicts, but the machinery beneath it (ideation,
        # validation, a spawned child) can still throw.
        #
        # The allowance context is around the whole _survive, not just the
        # executor: it costs nothing (the recording below makes no model call)
        # and it means the ceiling is off again by the time the loop turns,
        # whether the capability returned or threw. A capability that spends its
        # room raises TokenAllowanceExhausted, which _survive records as an arc
        # row — an honest ceiling reached, read by the director next turn.
        with _capability_allowance(name, token_budget, spent):
            _survive(study, name, decisions, finding,
                     lambda: _record_capability(
                         study, name, decisions,
                         execute_capability(name, action, study, budget, decisions),
                         finding))

    spend_end = _cost_snapshot()
    report = _build_report(study, budget, termination, decisions, ceiling,
                           spend_start, spend_end, resumed_state)
    try:
        (study.dir / "report.json").write_text(json.dumps(report, indent=2))
    except Exception:  # noqa: BLE001 — the report value is returned regardless
        pass
    return report


def _build_report(
    study: Any,
    budget: Budget,
    termination: dict,
    decisions: int,
    ceiling: Optional[dict],
    spend_start: dict,
    spend_end: dict,
    resumed_state: Optional[dict] = None,
) -> dict:
    """Assemble the free investigation's report. Pure over its inputs. Counts
    experiment moves separately from total arc entries (capability actions appear
    in the arc too), and carries the final budget state so a reader sees exactly
    what was spent and allocated across the tree."""
    arc = study_findings(study)
    experiment_moves = [e for e in arc if e.get("move_type") in ("single", "campaign")]
    # runs_spend sums SUBPROCESS spend only (experiment runs) — exactly what its
    # note has always said. Capability rows now carry their own metered cost in
    # the arc, but that spend came out of THIS process's meter, i.e. it is
    # already inside the process-delta term below; summing it here too would
    # double-count it in total_spend.
    runs_spend = _sum_runs_spend(experiment_moves)
    # RENAMED from decider_spend (2026-07-28, roadmap item 1): the meter is
    # process-global, so this delta is everything that ran IN this process
    # during the investigation — the director's decisions, capability calls
    # (ideation/validation/analysis), and any spawned child directors, which
    # run in-process too. One study had 68 calls / 15.17M tokens of ideation
    # sitting in a field named for the PI's own decisions. Per-phase
    # attribution lives in the arc's cost column (pi_agent/cost_report.py).
    process_spend = {
        "calls": spend_end["calls"] - spend_start["calls"],
        "tokens": spend_end["tokens"] - spend_start["tokens"],
    }
    return {
        "study_id": study.study_id,
        "goal": study.goal,
        "director": "free",
        # Item B: present (with the reconstruction numbers) only for a resumed
        # study, so a reader knows process_spend covers the CURRENT process
        # only — the dead director's in-process spend is the reconstructed
        # prior_in_process_tokens figure inside this block, and the arc's own
        # cost column remains the per-move truth. Absent for a fresh study:
        # the report is byte-identical to before.
        **({"resumed_from": resumed_state} if resumed_state else {}),
        "allowed_substrates": study.allowed_substrates,
        "mode": study.mode,
        "moves_run": len(experiment_moves),
        "decisions_made": decisions,
        "ceiling": ceiling,
        "budget_final": budget.report(),
        "termination": termination,
        "arc": arc,
        "process_spend": process_spend,
        "runs_spend": runs_spend,
        "total_spend": {
            "calls": process_spend["calls"] + runs_spend["calls"],
            "tokens": process_spend["tokens"] + runs_spend["tokens"],
        },
        # The number to quote for a study that spawned children. total_spend
        # covers THIS study only (its process delta + its own experiment runs);
        # a root's total_spend under-counted the glider tree by ~3x because the
        # children's runs live only in the children's arcs. tree_spend is the
        # recursive arc roll-up over this study and every descendant on disk —
        # a NEW field, deliberately not a redefinition of total_spend, which
        # other readers (liveview spend_reported) rely on as-is.
        "tree_spend": _tree_spend(study),
        "spend_note": (
            "moves_run counts only experiment moves; the arc also holds capability "
            "actions. process_spend (renamed from decider_spend 2026-07-28) is "
            "everything this process spent: director decisions + in-process "
            "capability calls + in-process child directors. runs_spend sums each "
            "experiment's persisted per-run cost. tree_spend is the recursive "
            "arc-cost roll-up including every descendant study (capability rows "
            "in it overlap process_spend — see pi_agent/cost_report.py for the "
            "deduplicated grand total). The hard ceiling is the budget "
            "(divisible across the tree); decision_cap is the no-op backstop."
        ),
    }


def _tree_spend(study: Any) -> Optional[dict]:
    """The recursive arc-cost roll-up over this study and every descendant on
    disk ({calls, tokens, studies, moves_with_cost, moves}), read back from the
    evidence files at report time — children finish before the parent's report
    is written, so their arcs are complete here. Never raises; None means
    'could not be computed', which is not the same fact as zero."""
    try:
        from pi_agent.cost_report import tree_arc_spend
        return tree_arc_spend(study.study_id, study.studies_root)
    except Exception:  # noqa: BLE001 — accounting must never sink a report
        return None
