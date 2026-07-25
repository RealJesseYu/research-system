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

INJECTION. Each real executor takes a seam (`run` / `call`) defaulting to the live
machinery, so every path is exercisable offline with fakes (the repo pattern).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for
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
    director to pick from. Reuses stage1_ideation at depth='quick' (the cheap
    default per the collapse manifest) — which already grounds in BOTH search
    styles (deterministic arXiv/OpenAlex/S2 + native web search). Spends one move.
    `run` is injected for offline tests."""
    run = run or _default_ideation
    if not budget.can_spend(MOVE_COST):
        return _insufficient("call_ideation")
    budget.spend(MOVE_COST)
    domain = action.get("domain") or action.get("detail") or study.goal
    hyps = run(domain, study, seq) or []
    digest = [
        {"id": h.get("id"), "statement": h.get("statement")}
        for h in hyps[:_MAX_ITEMS]
        if isinstance(h, dict)
    ]
    return {
        "succeeded": bool(digest),
        "outcome": "ideation_done" if digest else "ideation_empty",
        "hypotheses": digest,
        "detail": f"{len(digest)} candidate direction(s) for: {domain}",
    }


def _default_ideation(domain: str, study: Any, seq: int) -> list:
    """Live ideation: a quick-depth stage1 pass over the domain. Writes its
    evidence under runs/<study_id>-cap<seq>/stage1/ like any run."""
    from baton import Baton
    from stages import stage1_ideation

    baton = Baton(
        run_id=f"{study.study_id}-cap{seq}",
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=study.mode,
        payload={"domain": domain},
    )
    result = stage1_ideation.run(baton, depth="quick")
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
    constraint (a child stays within its parent's outer bound) and studies_root."""
    from pi_agent.free_director import free_investigate

    return free_investigate(
        domain,
        budget=child_budget,
        mode=parent_study.mode,
        allowed_substrates=parent_study.allowed_substrates,
        study_id=child_id,
        parent_study_id=parent_study.study_id,
        studies_root=parent_study.studies_root,
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


def execute(name: str, action: dict, study: Any, budget: Any, seq: int) -> dict:
    """Route a non-experiment action to its executor and return the recorded
    result. An unknown action (should never happen — the validator gates the
    vocabulary) yields an honest 'unknown' rather than a crash."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {
            "succeeded": False,
            "outcome": f"{name}_unknown",
            "detail": f"no executor registered for action {name!r}.",
        }
    return fn(action, study, budget, seq)
