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

import json
from pathlib import Path
from typing import Any, Callable, Optional

from pi_agent.budget import Budget
from pi_agent.dispatch import Move, MoveResult, MoveType
from pi_agent.loop import _cost_snapshot, _sum_runs_spend  # identical cost accounting
from pi_agent.study import STUDIES_ROOT, create_study, record_move, study_findings


def _move_from_action(action: dict, study: Any) -> Move:
    """Build the dispatchable Move from a run_experiment action. A campaign flag
    selects the iterated sweep; a named instrument narrows the run to it (else the
    run chooses from the study's permitted set).

    The question travels as a full BRIEF (_brief): the study goal, what is already
    established, why this experiment now, the freedom to deviate, and the verified
    file producers to build on. A run used to receive one line and no idea what
    investigation it belonged to.
    """
    instrument = action.get("instrument")
    mtype = MoveType.CAMPAIGN if action.get("campaign") else MoveType.SINGLE
    return Move(
        type=mtype,
        domain=_brief(action["domain"], study, action),
        mode=study.mode,
        allowed_substrates=[instrument] if instrument else None,
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


def _brief(domain: str, study: Any, action: dict) -> str:
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


def _survive(study: Any, action_name: str, seq: int, finding: Optional[str], fn):
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
    director alone. Returns True when the action ran, False when it failed."""
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
                       f"investigation — {detail}"},
            finding,
        )
        return False


def _tokens_spent(arc: list, spend_start: dict) -> int:
    """Real tokens spent by this investigation so far: this process's own model
    calls (director decisions plus in-process capabilities like ideation) plus
    every dispatched run's persisted cost, read back off the arc. Same accounting
    _build_report does at the end — computed per turn so the director can see it
    while it still has decisions left to make. Never raises."""
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
    decide_action: Callable = None,
    run_move: Callable = None,
    execute_capability: Callable = None,
) -> dict:
    """Run one free-director investigation to completion and return its report.

    `inherited_artifacts` are the spawning study's verified file producers, handed
    down so this study's moves build on work an earlier phase already did rather
    than reconstructing it from prose (the carry bus; None for a root study).

    `budget` is the Budget (Phase 1) — the hard, divisible ceiling. `decide_action`
    (default pi_agent.free_decider.decide_action) is the open-action-space model
    brain; `run_move` (default pi_agent.study.run_study_move) dispatches and records
    an experiment; `execute_capability` (default _unwired_capability) runs the
    non-experiment actions — all injected so the whole loop is exercisable offline
    with fakes and the real path is proven with only the model transport faked.

    Returns a report dict (also written to studies/<id>/report.json).
    """
    if decide_action is None:
        from pi_agent.free_decider import decide_action as decide_action
    if run_move is None:
        from pi_agent.study import run_study_move as run_move
    if execute_capability is None:
        from pi_agent.capabilities import execute as execute_capability

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
            _survive(study, "run_experiment", decisions, finding,
                     lambda: run_move(study, _move_from_action(action, study),
                                      finding=finding, runs_root=runs_root))
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
            domain = _integration_domain(study.goal, action.get("detail"), context)
            instrument = action.get("instrument")
            _survive(
                study, "call_integration", decisions, finding,
                lambda: run_move(
                    study,
                    Move(type=MoveType.SINGLE, domain=domain, mode=study.mode,
                         allowed_substrates=[instrument] if instrument
                         else study.allowed_substrates),
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
        _survive(study, name, decisions, finding,
                 lambda: _record_capability(
                     study, name, decisions,
                     execute_capability(name, action, study, budget, decisions),
                     finding))

    spend_end = _cost_snapshot()
    report = _build_report(study, budget, termination, decisions, ceiling, spend_start, spend_end)
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
