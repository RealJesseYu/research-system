"""pi_agent/capabilities.py — the free director's OPTIONAL tools (Phase 3).

docs/free_director_plan.md §1: nothing is mandatory except the measurement
boundary. Ideation, heavy validation, and data analysis are TOOLS the free
director reaches for when the task warrants — never stages every investigation is
forced through. This module is the registry of executors behind those actions; the
free director routes a non-experiment action here (free_director.execute_capability
defaults to `execute`).

THE SPLIT (plan item 8). Two things are called "validation":
  - The THIN propose/measure boundary — "a number of record comes from a tool +
    verification, never model narration" — stays a LAW, enforced automatically at
    the tool/verification layer inside every experiment run (stages/verification.py
    re-runs each kept artifact; the wall is authoritative). It is NOT a step here
    and is never optional.
  - The HEAVY validation apparatus — on-demand adversarial scrutiny of the
    findings standing so far — is the OPTIONAL tool `call_validation` below. It is
    advisory: it flags concerns and rates confidence but NEVER sets `verified` /
    `publishable`. Only the deterministic wall does that (verification purity).

BUDGET. Each heavy tool call costs one move (MOVE_COST) — the budget bounds the
number of significant operations (experiments + heavy tool calls), not just
experiments, so a director cannot burn unbounded spend on tools while its move
budget looks intact. Token cost is tracked separately (decider/runs spend). An
executor guards its own spend and returns an honest insufficient-budget result
rather than running when it cannot afford to.

TOKENS, TOO (2026-07-28). One move used to be the ONLY bound here: call_ideation
at depth "full" was measured at 176 model calls / 17.5M tokens for that single
move. These calls run IN-PROCESS, so a dispatched move's subprocess env cannot
carry a ceiling to them; the director binds one on its own environment around
the call instead (free_director._capability_allowance), and model_call enforces
it exactly as it does inside a move. Nothing in this file reads it — an executor
that spends its room sees TokenAllowanceExhausted from the model door, which the
director's _survive records as an arc row.

INJECTION. Each real executor takes a seam (`run` / `call`) defaulting to the live
machinery, so every path is exercisable offline with fakes (the repo pattern).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for
from pi_agent.free_decider import DEFAULT_IDEATION_DEPTH
from pi_agent.loop import _cost_snapshot  # the never-raise meter-diff idiom
from pi_agent.study import study_findings, study_scratch_dir

# One move per heavy tool call (see BUDGET above).
MOVE_COST = 1
# Cap on how many items a capability result carries into the arc — the director
# reads a digest, never a raw dump (small typed batons, not transcripts).
_MAX_ITEMS = 8


def _insufficient(name: str) -> dict:
    """An honest 'cannot afford this' — no work done, no budget spent."""
    return {
        "succeeded": False,
        "outcome": f"{name}_insufficient_budget",
        "detail": "no budget remains for this capability; run a cheaper action or stop.",
    }


# --------------------------------------------------------------------------
# call_ideation — the hypothesis apparatus, on demand (plan item 7).
# --------------------------------------------------------------------------

def run_ideation(action: dict, study: Any, budget: Any, seq: int, *, run: Callable = None) -> dict:
    """Invoke ideation for a question and return its ranked hypotheses for the
    director to pick from. Spends one move. `run` is injected for offline tests.

    DEPTH IS THE DIRECTOR'S DIAL (R-FD-6). 'quick' (the default) is one generation
    strategy — cheap, enough when you just need a direction to go test. 'full' is
    the whole Co-Scientist apparatus (four generation strategies, six review types,
    an Elo tournament, evolution, meta-review), for when the IDEAS are the
    deliverable. Both ground in deterministic literature search + native web
    search. An absent/None depth means quick, so a director that never names one
    behaves exactly as before this dial existed."""
    run = run or _default_ideation
    if not budget.can_spend(MOVE_COST):
        return _insufficient("call_ideation")
    budget.spend(MOVE_COST)
    domain = _ideation_brief(
        action.get("domain") or action.get("detail") or study.goal, study)
    depth = action.get("depth") or DEFAULT_IDEATION_DEPTH
    # NOVELTY WEIGHT IS THE DIRECTOR'S DIAL TOO (owner ruling 2026-07-27), for the
    # same reason depth is: it depends on the KIND of goal, and the director is the
    # only thing that knows. An engineering goal ("hold 5 kg") is often best served
    # by a well-established method and should rank on quality alone; a science goal
    # needs novelty or it is not research. One hardcoded weight served neither —
    # and the weight it had (novelty as the primary sort key, then a 4-survivor cap)
    # silently discarded every known-method hypothesis whenever four novel ones
    # existed. Absent => 'balanced', the only setting that cannot drop a whole
    # class of work, so a director that never names one is safe.
    novelty_priority = action.get("novelty_priority")
    # Breadth is the director's to buy (owner ruling 2026-07-27). None keeps
    # the module defaults, so a director that never asks behaves as before.
    try:
        from stages.generation_strategies import set_pool_size
        set_pool_size(action.get("pool_size"))
    except Exception:  # noqa: BLE001 — a sizing hint must not sink the call
        pass
    hyps = _run_ideation_at_depth(run, domain, study, seq, depth,
                                  novelty_priority) or []
    digest = [
        {"id": h.get("id"), "statement": h.get("statement")}
        for h in hyps[:_MAX_ITEMS]
        if isinstance(h, dict)
    ]
    return {
        "succeeded": bool(digest),
        "outcome": "ideation_done" if digest else "ideation_empty",
        "hypotheses": digest,
        # The depth used rides the arc entry: a reader comparing two studies has to
        # be able to tell "thin ideas from a quick pass" from "thin ideas the full
        # apparatus could not improve on" — those mean different things.
        "depth": depth,
        "pool_size": action.get("pool_size"),
        "detail": f"{len(digest)} candidate direction(s) at depth={depth} for: {domain}",
    }


# How much of the arc travels into an ideation request. Bounded so a long study
# does not bury the question being asked.
MAX_BRIEFED_FINDINGS = 12


def _ideation_brief(question: str, study: Any) -> str:
    """The full briefing an ideation call receives.

    Ideation used to get ONLY the string the director typed — no goal, no results,
    no artifacts. The experimenter was given a proper brief on 2026-07-25 and this
    was never done to match, which makes the apparatus useless for exactly the case
    it should be strongest at: "half the system is already built and verified, now
    find me a hypothesis for the next function." The director would have had to
    retype the entire state of the work into one prompt string, and could not hand
    over an artifact at all.

    So ideation now sees what the experimenter sees: the goal, what is already
    ESTABLISHED (verified findings only — an unreproduced number is not a
    foundation to build a hypothesis on), and the reusable file artifacts the study
    has produced, as re-runnable producers. Pure over its inputs; never raises. A
    fresh study with an empty arc gets the question back unchanged."""
    try:
        from pi_agent.free_director import _carry_block, _integration_context
        context = _integration_context(study)
    except Exception:  # noqa: BLE001 — a brief must never sink the call
        return question

    parts = [question]
    established = context["parts"][:MAX_BRIEFED_FINDINGS]
    files = context["files"]
    if not established and not files:
        return question  # nothing built yet: unchanged, as before this existed

    parts.append("\n\n---\nCONTEXT: this is not a blank slate. You are proposing "
                 "hypotheses for an investigation already underway.")
    parts.append(f"\n\nTHE OVERALL GOAL: {study.goal}")
    if established:
        lines = "".join(f"\n  - {p.get('label')} = {p.get('value')}"
                        for p in established)
        parts.append(
            "\n\nALREADY ESTABLISHED (each independently re-run and reproduced — "
            f"treat as settled fact, and do not propose re-measuring it):{lines}")
    if files:
        parts.append(
            "\n\nWORK ALREADY BUILT that a hypothesis may build ON — prefer "
            "hypotheses that take this further over ones that start from nothing:")
        parts.append(_carry_block(files))
    return "".join(parts)


def _run_accepts(run: Callable, name: str) -> bool:
    """True when the injected ideation runner can take `name` as a keyword.

    Every dial added to this capability (depth, now novelty_priority) is a new
    argument to a callable TESTS INJECT, so the older signatures still in the
    suite must keep working rather than break on an unexpected keyword. Same
    introspection idiom as model_call._seam_accepts_capabilities, recomputed per
    call because the injected callable varies."""
    try:
        params = inspect.signature(run).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return name in params


def _ideation_run_accepts_depth(run: Callable) -> bool:
    """True when the ideation runner can take a depth argument. Kept as its own
    name because tests reference it; _run_accepts is the general form."""
    return _run_accepts(run, "depth")


def _run_ideation_at_depth(run: Callable, domain: str, study: Any, seq: int,
                           depth: str, novelty_priority: str = None) -> list:
    """Call the ideation runner, passing each dial only when it can take it. A
    runner that cannot keeps its old behavior rather than crashing — the dials are
    additive, never a break. The runner is INJECTED (tests pass their own), so
    this is checked per call."""
    kwargs = {}
    if _ideation_run_accepts_depth(run):
        kwargs["depth"] = depth
    if novelty_priority is not None and _run_accepts(run, "novelty_priority"):
        kwargs["novelty_priority"] = novelty_priority
    return run(domain, study, seq, **kwargs)


def _default_ideation(domain: str, study: Any, seq: int,
                      depth: str = DEFAULT_IDEATION_DEPTH,
                      novelty_priority: str = None) -> list:
    """Live ideation: a stage1 pass over the domain at the director's chosen depth
    ('quick' = one generation strategy; 'full' = the whole Co-Scientist apparatus).
    Writes its evidence under runs/<study_id>-cap<seq>/stage1/ like any run."""
    from baton import Baton
    from stages import stage1_ideation

    baton = Baton(
        run_id=f"{study.study_id}-cap{seq}",
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=study.mode,
        payload={"domain": domain},
    )
    kwargs = {"depth": depth}
    if novelty_priority is not None:
        kwargs["novelty_priority"] = novelty_priority
    result = stage1_ideation.run(baton, **kwargs)
    return result.payload.get("hypotheses") or []


# --------------------------------------------------------------------------
# call_data_analysis — analyze the accumulated arc (plan item 9).
# --------------------------------------------------------------------------

DATA_ANALYSIS_STAGE = "capability_data_analysis"
DATA_ANALYSIS_PROMPT = """You are a data analyst for an autonomous research program. You are given a goal and the arc of VERIFIED findings gathered so far. Produce an analytical reading: patterns across the results, what they imply for the goal, and 1-3 concrete next directions worth testing.

BOUNDARY: you never produce a measurement of record. Reason only over the already-verified numbers you are given. If you compute a derived quantity to make a point, say it is advisory — a number that must stand has to come from an experiment and its verification, not from you.

Reply ONLY with JSON {"analysis": "<your reading, a few sentences>", "directions": ["<a concrete next direction>", ...]} — no other fields."""


def _analysis_validator(parsed: dict) -> list:
    errors = []
    if not isinstance(parsed.get("analysis"), str) or not parsed["analysis"].strip():
        errors.append("analysis must be a non-empty string.")
    d = parsed.get("directions")
    if not isinstance(d, list) or not all(isinstance(x, str) and x.strip() for x in d):
        errors.append("directions must be a list of non-empty strings.")
    return errors


def run_data_analysis(action: dict, study: Any, budget: Any, seq: int, *, call: Callable = None) -> dict:
    """A FULL analytic pass over the arc's verified findings — advisory, never a
    measurement of record. Spends one move. `call` is injected for offline tests."""
    call = call or call_stage_model
    if not budget.can_spend(MOVE_COST):
        return _insufficient("call_data_analysis")
    budget.spend(MOVE_COST)
    arc = study_findings(study)
    with agent_workspace(study_scratch_dir(study)):
        data, _timing = call(
            DATA_ANALYSIS_STAGE,
            DATA_ANALYSIS_PROMPT,
            {"goal": study.goal, "request": action.get("detail"), "arc_so_far": arc},
            {"required": ["analysis", "directions"]},
            model=model_for("heavy"),
            extra_validator=_analysis_validator,
            capabilities=FULL,
        )
    return {
        "succeeded": True,
        "outcome": "data_analysis_done",
        "analysis": data.get("analysis"),
        "directions": (data.get("directions") or [])[:_MAX_ITEMS],
        "detail": data.get("analysis"),
    }


# --------------------------------------------------------------------------
# call_validation — heavy adversarial scrutiny, on demand (plan item 8).
# --------------------------------------------------------------------------

VALIDATION_STAGE = "capability_validation"
VALIDATION_PROMPT = """You are an adversarial validator for an autonomous research program. You are given a goal and the arc of findings standing so far (each already re-run by a deterministic verification wall). Stress-test the conclusions: where might a result be an artifact, a coincidence, or resting on an unstated assumption? Which findings are load-bearing and deserve an independent re-check before the program builds on them?

BOUNDARY (verification purity): you NEVER declare a finding verified or unverified and you never set publishability — only the deterministic wall does that. You assess confidence and flag concerns; your output is advice, not a verdict of record.

Reply ONLY with JSON {"assessment": "<your scrutiny, a few sentences>", "concerns": ["<a specific concern about a finding>", ...], "recheck": ["<a finding worth an independent re-check>", ...]} — no other fields."""


def _validation_validator(parsed: dict) -> list:
    errors = []
    if not isinstance(parsed.get("assessment"), str) or not parsed["assessment"].strip():
        errors.append("assessment must be a non-empty string.")
    for key in ("concerns", "recheck"):
        v = parsed.get(key)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append(f"{key} must be a list of strings.")
    return errors


def run_validation(action: dict, study: Any, budget: Any, seq: int, *, call: Callable = None) -> dict:
    """Heavy adversarial scrutiny of the standing findings — advisory only. The
    deterministic per-run wall remains the sole authority on `verified` /
    `publishable`; this tool flags concerns, it never overrides the wall. Spends
    one move. `call` is injected for offline tests."""
    call = call or call_stage_model
    if not budget.can_spend(MOVE_COST):
        return _insufficient("call_validation")
    budget.spend(MOVE_COST)
    arc = study_findings(study)
    with agent_workspace(study_scratch_dir(study)):
        data, _timing = call(
            VALIDATION_STAGE,
            VALIDATION_PROMPT,
            {"goal": study.goal, "request": action.get("detail"), "arc_so_far": arc},
            {"required": ["assessment", "concerns", "recheck"]},
            model=model_for("heavy"),
            extra_validator=_validation_validator,
            capabilities=FULL,
        )
    return {
        "succeeded": True,
        "outcome": "validation_done",
        "assessment": data.get("assessment"),
        "concerns": (data.get("concerns") or [])[:_MAX_ITEMS],
        "recheck": (data.get("recheck") or [])[:_MAX_ITEMS],
        "detail": data.get("assessment"),
    }


# --------------------------------------------------------------------------
# spawn_sub_investigation — the manager-of-managers recursion (Phase 4).
# --------------------------------------------------------------------------

def run_spawn(action: dict, study: Any, budget: Any, seq: int, *, investigate: Callable = None) -> dict:
    """Delegate a sub-question to a CHILD free director with a carved slice of the
    budget — the manager-of-managers recursion. `budget_moves` moves are TRANSFERRED
    to the child (budget.allocate), so the child provably cannot overrun and the
    tree's total is conserved (pi_agent/budget.py). The child runs a full
    free_investigate; only its VERIFIED findings bubble up (never the child
    director's narration — the measurement boundary holds at every depth). `budget`
    is not spent by MOVE_COST here: the allocated slice IS the cost. `investigate`
    is injected for offline tests."""
    investigate = investigate or _default_spawn_investigate
    k = action.get("budget_moves")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        return {
            "succeeded": False,
            "outcome": "spawn_invalid_budget",
            "detail": "budget_moves must be a positive integer.",
        }
    if not budget.can_allocate(k):
        # Two honest 'no's, told apart so the director can respond correctly.
        if budget.depth + 1 > budget.max_depth:
            return {
                "succeeded": False,
                "outcome": "spawn_depth_cap",
                "detail": f"recursion is at max_depth {budget.max_depth}; cannot "
                "delegate deeper. Investigate this directly with run_experiment.",
            }
        return {
            "succeeded": False,
            "outcome": "spawn_insufficient_budget",
            "detail": f"cannot carve {k} move(s) for a child; only "
            f"{budget.remaining()} remain. Ask for fewer, or run it directly.",
        }
    child_budget = budget.allocate(k)
    child_id = f"{study.study_id}-sub{seq}"
    report = investigate(action["domain"], child_budget, child_id, study)
    findings, standing, reusables = _bubble_findings(report)
    return {
        "succeeded": bool(standing),
        "outcome": "sub_investigation_done" if standing else "sub_investigation_barren",
        "child_study_id": report.get("study_id", child_id),
        "child_termination": (report.get("termination") or {}).get("reason"),
        "child_moves_run": report.get("moves_run"),
        "findings": findings,
        # Reproducible file producers the child made, so a parent integration can
        # compose the actual files (cross-run file hand-off). Empty for a child
        # that produced no reusable file.
        "reusable_artifacts": reusables,
        "detail": (
            f"sub-investigation of {action['domain']!r}: {standing} verified "
            f"finding(s), {len(reusables)} reusable file(s), across "
            f"{report.get('moves_run')} move(s)"
        ),
    }


def _bubble_findings(report: dict) -> tuple:
    """(digest, standing_count, reusables) of the child's VERIFIED findings and its
    reproduced reusable file artifacts, read from its arc. Findings keep their
    verified flag so the parent sees shaky ones too — but only verified ones count
    as 'standing'. Narration never crosses; only re-run numbers and re-runnable
    file PRODUCERS do."""
    out = []
    standing = 0
    reusables = []
    seen = set()
    for entry in report.get("arc", []) or []:
        for f in entry.get("results", []) or []:
            if not isinstance(f, dict):
                continue
            verified = bool(f.get("verified"))
            if verified:
                standing += 1
            out.append({"label": f.get("label"), "value": f.get("value"), "verified": verified})
        for ra in entry.get("reusable_artifacts", []) or []:
            if isinstance(ra, dict) and ra.get("name") and ra.get("name") not in seen:
                seen.add(ra["name"])
                reusables.append({"name": ra["name"], "producer": ra.get("producer")})
    return out[:_MAX_ITEMS], standing, reusables[:_MAX_ITEMS]


def _default_spawn_investigate(domain: str, child_budget: Any, child_id: str, parent_study: Any) -> dict:
    """Live child investigation: a full free_investigate on the sub-question, under
    the child budget, parent-linked, inheriting the parent's mode + substrate
    constraint (a child stays within its parent's outer bound) and studies_root.

    ARTIFACT HAND-DOWN (the carry bus). The child also inherits the parent's
    verified file PRODUCERS, both ways they are needed: inlined into its goal (so
    its first move can regenerate and build on them) and seeded onto its study (so
    its OWN later moves and its integration carry them onward). This is what makes
    a phase able to build on the phase before it — the parent hands down the work,
    not just the number that scored it. Producers only, never bytes."""
    from pi_agent.free_director import (_carry_domain, _integration_context,
                                        free_investigate)

    carried = _integration_context(parent_study)["files"]
    return free_investigate(
        _carry_domain(domain, parent_study),
        budget=child_budget,
        mode=parent_study.mode,
        allowed_substrates=parent_study.allowed_substrates,
        study_id=child_id,
        parent_study_id=parent_study.study_id,
        studies_root=parent_study.studies_root,
        inherited_artifacts=carried,
        # The child's share of the token ceiling, carved by Budget.allocate in the
        # same transfer that gave it its moves. Omitting this is what let a child
        # run with no token ceiling while the parent believed "the REAL
        # constraint" was holding; None here still means untracked, exactly as
        # before, so a run without --token-budget is unchanged.
        token_budget=child_budget.tokens_remaining(),
    )


# --------------------------------------------------------------------------
# read_memory — read prior studies' accumulated findings (Phase 4, read-only).
# --------------------------------------------------------------------------

def run_read_memory(action: dict, study: Any, budget: Any, seq: int, *, read: Callable = None) -> dict:
    """Read recent learned summaries from the shared journal — the cross-study
    memory a chat cannot keep. Read-only and cheap: spends no move. `read` is
    injected for offline tests."""
    read = read or _default_read_memory
    entries = read() or []
    digest = [
        {"text": e.get("text"), "run_id": e.get("run_id")}
        for e in entries[:_MAX_ITEMS]
        if isinstance(e, dict)
    ]
    return {
        "succeeded": bool(digest),
        "outcome": "memory_read" if digest else "memory_empty",
        "memory": digest,
        "detail": f"{len(digest)} memory entry(ies) from prior work",
    }


def _default_read_memory() -> list:
    """Recent cross-study memory: the runs' learned summaries AND the directors'
    own notes (R-FD-5). Both are read so a director sees prior lessons of both
    kinds; they are kept in SEPARATE journal kinds so a director note can never
    enter the learned_summary window ideation reads."""
    from memory.journal import journal_recent_by_kind

    return (journal_recent_by_kind("learned_summary", 5)
            + journal_recent_by_kind(DIRECTOR_MEMORY_KIND, 5))


# --------------------------------------------------------------------------
# write_memory — record a lesson for future studies (R-FD-5).
# --------------------------------------------------------------------------
# RULING R-FD-5 (2026-07-24, docs/free_director_plan.md). A director note is
# written to a DISTINCT journal kind, "director_note" — NEVER "learned_summary".
# The learned_summary channel is what ideation reads and the kill-rate battery
# pins by md5 (CLAUDE.md "learned-summary poison risk"); keeping director notes in
# their own kind means write_memory can never contaminate it. read_memory reads
# both kinds; nothing else reads director_note, so it is inert to the pinned path.
DIRECTOR_MEMORY_KIND = "director_note"


def run_write_memory(action: dict, study: Any, budget: Any, seq: int, *, write: Callable = None) -> dict:
    """Record a lesson for future studies as a 'director_note' (R-FD-5) — never a
    learned_summary. Cheap: spends no move. `write` is injected for offline tests."""
    write = write or _default_write_memory
    note = action.get("detail")
    if not isinstance(note, str) or not note.strip():
        return {
            "succeeded": False,
            "outcome": "memory_write_empty",
            "detail": "write_memory needs a non-empty 'detail' (the lesson to record).",
        }
    write(study, note.strip())
    return {
        "succeeded": True,
        "outcome": "memory_written",
        "detail": f"recorded a director note: {note.strip()[:120]}",
    }


def _default_write_memory(study: Any, note: str) -> None:
    from memory.journal import journal_append

    journal_append({
        "run_id": study.study_id,
        "kind": DIRECTOR_MEMORY_KIND,
        "text": note,
        "extras": {"source": "free_director"},
    })


def _not_yet_wired(action: dict, study: Any, budget: Any, seq: int) -> dict:
    """An HONEST placeholder for a capability whose executor lands in a later
    phase. Nothing in the registry maps to it now (every action is wired) — kept
    as the documented pattern and safety net for any future action. Spends nothing
    (nothing ran); the director reads it and picks again."""
    name = action.get("action")
    return {
        "succeeded": False,
        "outcome": f"{name}_not_yet_wired",
        "detail": (
            f"the {name} capability is defined in the action space but its executor "
            "is wired in a later phase; choose run_experiment or stop."
        ),
    }


# --------------------------------------------------------------------------
# The registry + dispatcher.
# --------------------------------------------------------------------------

_REGISTRY: dict[str, Callable] = {
    "call_ideation": run_ideation,
    "call_data_analysis": run_data_analysis,
    "call_validation": run_validation,
    "spawn_sub_investigation": run_spawn,       # Phase 4 (recursion, live)
    "read_memory": run_read_memory,             # Phase 4 (read-only, live)
    "write_memory": run_write_memory,           # R-FD-5 (distinct kind, live)
}

# Capabilities whose spend is NOT metered here. spawn_sub_investigation runs a
# whole child director in this process: its spend is recorded in the CHILD's own
# arc and report, and every tree roll-up (liveview totals, cost_report) reads
# those recursively — a meter diff on the spawn row would count the child's
# in-process spend a second time. The spawn row's cost stays null and readers
# derive it from the child, which is exactly what pi_agent/cost_report.py does.
_UNMETERED = frozenset({"spawn_sub_investigation"})


def _with_cost(name: str, result: Any, before: dict) -> Any:
    """Attach this capability call's own model spend to its result as
    {"cost": {calls, tokens}} — record_move maps "cost" onto the arc's cost
    column, so the spend lands beside the experiment runs' and a capability
    phase stops reading as cost-unknown. The diff is against the shared
    process meter (same idiom as loop._cost_snapshot's callers). A result that
    already carries a cost is left alone. Never raises, and never overwrites —
    cost accounting must not be able to sink or distort a capability result."""
    try:
        if name in _UNMETERED or not isinstance(result, dict) or "cost" in result:
            return result
        after = _cost_snapshot()
        result["cost"] = {
            "calls": max(0, after.get("calls", 0) - before.get("calls", 0)),
            "tokens": max(0, after.get("tokens", 0) - before.get("tokens", 0)),
        }
    except Exception:  # noqa: BLE001 — metering is observational, never fatal
        pass
    return result


def execute(name: str, action: dict, study: Any, budget: Any, seq: int) -> dict:
    """Route a non-experiment action to its executor and return the recorded
    result, with the call's own model spend attached (see _with_cost). An
    unknown action (should never happen — the validator gates the vocabulary)
    yields an honest 'unknown' rather than a crash."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {
            "succeeded": False,
            "outcome": f"{name}_unknown",
            "detail": f"no executor registered for action {name!r}.",
        }
    before = _cost_snapshot()
    return _with_cost(name, fn(action, study, budget, seq), before)
