"""pi_agent/study.py — the study: a persistent identity an arc of moves
accumulates under.

THE PROBLEM THIS SOLVES. Today every run is an isolated event. run_id is
per-process, evidence lives in runs/<run_id>/, and the one cross-run memory
channel — journal_recent_by_kind("learned_summary", limit=3) — is global and
keyed only by kind, so a run reads the last three summaries from ALL runs,
whoever produced them. A PI that runs many experiments toward one goal has
nowhere to accumulate: its moves would forget each other, and its own summaries
would crowd the shared window every unrelated run reads.

A STUDY is that missing place. It is a durable identity carrying the digested
goal and its constraints, under which a sequence of moves — the research arc —
is recorded in order. The PI reads its OWN arc to judge what it has found and
whether to continue, without touching the shared journal's meaning and without
being polluted by other studies. The paper, when it comes, is written from the
whole arc, not from a single run.

WHAT A STUDY OWNS.
  - study.json         — the identity: goal, constraints (allowed_substrates),
                         mode, created_at. Written once, never rewritten.
  - arc.jsonl          — append-only, one entry per move in order: the move
                         type, its run_id, its outcome, whether it stood, and a
                         short finding the PI attaches. THIS IS THE ARC.

Evidence-class, like runs/ and cases_*/: studies/ is gitignored, append-only,
pruned only at a recorded checkpoint.

TWO CONNECTIONS THIS MAKES.
  1. Constraints span the arc. A study's allowed_substrates is stamped onto
     every move it runs, so "only cobrapy" (chunk 1) binds not just one run but
     the whole investigation — the study is where a goal-level constraint lives.
  2. Moves stop colliding. The study mints a study-scoped run_id per move
     (studies link to their runs by that id), so two campaigns or two chains in
     one arc no longer overwrite each other's runs/<id>/ evidence — the
     parent-link the flat run_id never had.

WHAT THIS CHUNK DELIBERATELY DOES NOT DO. It does NOT change how a single run
reads memory during ideation (that read is still the global journal window).
Scoping the per-run ideation read to the study is a real change to a stage's
behavior and to the calibration memory-md5 pins, and it is left for later, on
evidence — not folded in here. This chunk gives the PI a scoped view of its own
arc; it does not re-plumb the runs beneath it.

No model call anywhere. Pure persistence + one thin dispatch-and-record helper
whose model-touching part (invoke_move) is injected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

STUDIES_ROOT = Path("studies")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class Study:
    """A study's identity. The arc itself lives in arc.jsonl beside study.json,
    read on demand rather than held in the object, so a Study loaded in one
    process sees moves another process appended."""

    study_id: str
    goal: str
    allowed_substrates: Optional[list] = None
    mode: str = "auto"
    created_at: str = field(default_factory=_utc_now)
    studies_root: Path = STUDIES_ROOT
    # The study this one was spawned from, or None for a root study. This is the
    # tree link the manager-of-managers recursion needs (a free director may spawn
    # a sub-investigation as its own study); a reader of studies/ can reconstruct
    # the decomposition tree from these back-pointers.
    parent_study_id: Optional[str] = None
    # Reusable FILE artifacts handed DOWN from the spawning study, each
    # {name, producer} — the work a parent phase already built and verified, so a
    # child's very first move can build ON it instead of from scratch. Empty/None
    # for a root study. Producers only, never bytes: a child regenerates the file
    # by re-running the producer, exactly as an integration does.
    inherited_artifacts: Optional[list] = None

    @property
    def dir(self) -> Path:
        return Path(self.studies_root) / self.study_id

    @property
    def arc_path(self) -> Path:
        return self.dir / "arc.jsonl"

    def identity(self) -> dict:
        """The study.json contents. run-scoped constraint and goal in one place
        so a reader of studies/<id>/ knows what the arc was pointed at."""
        return {
            "study_id": self.study_id,
            "goal": self.goal,
            "allowed_substrates": self.allowed_substrates,
            "mode": self.mode,
            "created_at": self.created_at,
            "parent_study_id": self.parent_study_id,
            "inherited_artifacts": self.inherited_artifacts,
        }


def create_study(
    goal: str,
    *,
    allowed_substrates: Optional[list] = None,
    mode: str = "auto",
    study_id: Optional[str] = None,
    studies_root: Path = STUDIES_ROOT,
    parent_study_id: Optional[str] = None,
    inherited_artifacts: Optional[list] = None,
) -> Study:
    """Mint a study, write its identity, return it. The goal must be non-empty
    — a study with no goal is not a study. A caller-supplied study_id that
    already exists RAISES rather than silently reopening: a study identity is
    written once, and reopening one by accident is how an arc gets two goals.
    `parent_study_id` records the spawning study for a nested sub-investigation
    (None for a root study). `inherited_artifacts` are the parent's reproduced
    file PRODUCERS handed down, so the child's first move can build on the work
    the parent phase already did (None for a root study)."""
    if not (isinstance(goal, str) and goal.strip()):
        raise ValueError("a study requires a non-empty goal.")
    sid = study_id or f"study-{_stamp()}"
    study = Study(
        study_id=sid,
        goal=goal.strip(),
        allowed_substrates=list(allowed_substrates) if allowed_substrates else None,
        mode=mode,
        studies_root=studies_root,
        parent_study_id=parent_study_id,
        inherited_artifacts=list(inherited_artifacts) if inherited_artifacts else None,
    )
    if study.dir.exists():
        raise FileExistsError(
            f"study {sid!r} already exists at {study.dir} — a study identity is "
            "written once. Load it with load_study, or choose a fresh id."
        )
    study.dir.mkdir(parents=True)
    (study.dir / "study.json").write_text(json.dumps(study.identity(), indent=2))
    return study


def load_study(study_id: str, *, studies_root: Path = STUDIES_ROOT) -> Study:
    """Reload a study from its written identity. Raises FileNotFoundError on an
    unknown id — an unknown study is never silently treated as a fresh one."""
    path = Path(studies_root) / study_id / "study.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no study {study_id!r} at {path} — create it with create_study."
        )
    data = json.loads(path.read_text())
    return Study(
        study_id=data["study_id"],
        goal=data["goal"],
        allowed_substrates=data.get("allowed_substrates"),
        mode=data.get("mode", "auto"),
        created_at=data.get("created_at", _utc_now()),
        studies_root=studies_root,
        parent_study_id=data.get("parent_study_id"),
        inherited_artifacts=data.get("inherited_artifacts"),
    )


def study_arc(study: Study) -> list:
    """The recorded arc, oldest-first, as a plain list of move entries. Empty
    before the first move. Never raises on a missing file."""
    path = study.arc_path
    if not path.is_file():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def move_count(study: Study) -> int:
    """How many moves the arc holds so far."""
    return len(study_arc(study))


def next_move_run_id(study: Study) -> str:
    """The run_id for the study's next move: study-scoped and ordered, so the
    run dir links back to the study and successive moves never collide. Shape
    is <study_id>-m<N> with N one past the current arc length."""
    return f"{study.study_id}-m{move_count(study) + 1}"


# Keys record_move already maps onto named arc fields. Anything else a move
# returns is the TOOL's own payload and rides in "tool_output" (see below).
_ARC_MAPPED_KEYS = frozenset(
    {"findings", "cost", "reusable_artifacts", "publishable", "succeeded", "outcome"}
)


def record_move(
    study: Study,
    move_result: Any,
    *,
    finding: Optional[str] = None,
) -> dict:
    """Append one move to the arc and return the entry written.

    `move_result` is a MoveResult (or anything exposing move_type / run_id /
    succeeded / outcome, or an as_dict() with them). `finding` is the short
    thing the PI learned from this move — the accumulating substance the next
    decision and the eventual paper read. The entry is sequenced (seq is one
    past the current length) so the arc's order is intrinsic, not mtime-derived.
    """
    seq = move_count(study) + 1
    m = move_result.as_dict() if hasattr(move_result, "as_dict") else dict(move_result)
    raw = m.get("raw") or {}
    entry = {
        "seq": seq,
        "at": _utc_now(),
        "move_type": m.get("move_type"),
        "run_id": m.get("run_id"),
        "succeeded": m.get("succeeded"),
        "outcome": m.get("outcome"),
        "publishable": raw.get("publishable"),
        # The run's VERIFIED findings — the values it measured and whether each
        # reproduced — travel into the arc so the PI decides the next move from
        # results, not just from pass/fail. Empty for a run that measured nothing
        # or halted before verification.
        "results": raw.get("findings") or [],
        # The move's model spend ({calls, tokens}), so the study's total spend is
        # a sum over its arc — real per-run cost, not the launch-time estimate.
        "cost": raw.get("cost"),
        # Reusable FILE artifacts the run produced that reproduced — each
        # {name, producer} — so a later integration can compose the actual files,
        # not just the scalars (cross-run file hand-off).
        "reusable_artifacts": raw.get("reusable_artifacts") or [],
        # WHAT THE TOOL ACTUALLY RETURNED. The researcher calls tools — ideation,
        # validation, data analysis — and must READ what they give back, or it is
        # deciding blind. Everything above is shaped for experiment runs, whose
        # payload lives under "findings"; a tool answers under its own key
        # (ideation -> "hypotheses", analysis -> "analysis"/"directions",
        # validation -> "concerns"). Those were silently dropped: a call_ideation
        # arc entry carried no ideas at all, so a full-depth run costing millions
        # of tokens reached the director as an empty receipt and it confabulated a
        # hypothesis to fill the gap (study-20260725T073215Z). Carrying the
        # payload verbatim is the fix, and it is generic so a NEW tool needs no
        # change here. Empty for an experiment move (all its keys are mapped).
        "tool_output": {k: v for k, v in raw.items() if k not in _ARC_MAPPED_KEYS},
        "finding": finding,
    }
    study.dir.mkdir(parents=True, exist_ok=True)
    with open(study.arc_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def study_scratch_dir(study: Study) -> Path:
    """A study-scoped workspace for the DIRECTOR-LAYER agents — the director's own
    decisions and the analysis/validation tools. These are FULL agents (they may
    run code to sanity-check before committing) that run in the FOREGROUND process,
    so without a confined cwd their scratch files land in the repo root (this is how
    stray files — even an empty harness.py that shadowed the package — appeared).
    Pointing their cwd here keeps that scratch inside studies/ (gitignored evidence)
    where it belongs. Created on demand; the experimenter is already confined in its
    own subprocess workspace and is unaffected."""
    d = study.dir / "director_workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def study_findings(study: Study) -> list:
    """What this study knows so far: the ordered findings across its arc, each
    tagged with the move that produced it. THIS is what the PI reads to judge
    whether to continue — its own arc, scoped to this study, never the global
    journal window that every unrelated run shares. Moves with no attached
    finding still appear (with finding None), because 'a move that taught us
    nothing' is itself part of the record."""
    out = []
    for e in study_arc(study):
        out.append(
            {
                "seq": e.get("seq"),
                "move_type": e.get("move_type"),
                "run_id": e.get("run_id"),
                "succeeded": e.get("succeeded"),
                "outcome": e.get("outcome"),
                "results": e.get("results") or [],
                "cost": e.get("cost"),
                "reusable_artifacts": e.get("reusable_artifacts") or [],
                # What the researcher's TOOLS returned (ideas, analyses, concerns).
                # Without this the researcher reads only its own past reasoning and
                # decides blind — see record_move's tool_output note.
                "tool_output": e.get("tool_output") or {},
                "finding": e.get("finding"),
            }
        )
    return out


def run_study_move(
    study: Study,
    move: Any,
    *,
    finding: Optional[str] = None,
    invoke: Callable = None,
    runs_root: Path = Path("runs"),
) -> Any:
    """Run one move AS PART OF a study, then record it in the arc. The glue that
    makes chunks 1-3 one thing:

      - stamps the study's constraint (allowed_substrates) onto the move, so the
        goal-level restriction binds every run in the arc, not just one;
      - assigns the move a study-scoped run_id if it has none, so moves link to
        the study and never collide;
      - defaults the move's mode to the study's mode when the move left it at
        the dataclass default;
      - invokes it and appends the result to the arc.

    `invoke` is the move dispatcher (pi_agent.dispatch.invoke_move by default),
    injected so this is testable without a live subprocess. `finding` is an
    optional note recorded with the move; the PI will usually derive it from the
    result, but chunk 3 does not presume that logic — it just carries what it is
    given.
    """
    if invoke is None:
        from pi_agent.dispatch import invoke_move as invoke

    # The study's constraint is the OUTER BOUND of the whole arc; a move may
    # NARROW within it — the PI choosing a specific instrument for this move —
    # but never EXCEED it. A move that names a substrate outside the study's
    # set is refused loudly (that would breach the boundary the caller set); a
    # move that names a subset is honored (that is the PI picking its tool); a
    # move that names nothing inherits the study's full set.
    _apply_study_bounds(study, move)
    if not getattr(move, "run_id", None):
        move.run_id = next_move_run_id(study)

    result = invoke(move, runs_root=runs_root)
    record_move(study, result, finding=finding)
    return result


def _apply_study_bounds(study: "Study", move: Any) -> None:
    """Stamp the study's constraint and mode onto a move (shared by single moves
    and fan moves). The study's allowed_substrates is the OUTER BOUND: a move may
    NARROW within it (the PI picking a specific instrument) but a move naming a
    substrate outside it is refused loudly; a move naming none inherits the full
    set. The study's mode is carried unless the move deliberately set another."""
    if study.allowed_substrates:
        study_set = set(study.allowed_substrates)
        if move.allowed_substrates:
            outside = sorted(set(move.allowed_substrates) - study_set)
            if outside:
                raise ValueError(
                    f"move constrains substrates to {sorted(move.allowed_substrates)}, "
                    f"which reaches outside its study's bound {sorted(study.allowed_substrates)} "
                    f"— {outside} is not permitted by study {study.study_id!r}. A move may "
                    "narrow the study's constraint (pick a specific instrument) but never "
                    "widen it. Choose within the study's set, or open a study whose bound "
                    "includes it."
                )
            # Honor the move's narrower pick as-is (the PI's chosen instrument).
        else:
            move.allowed_substrates = list(study.allowed_substrates)
    if getattr(move, "mode", "auto") == "auto" and study.mode != "auto":
        move.mode = study.mode


def run_study_fan(
    study: "Study",
    moves: list,
    *,
    findings: Optional[list] = None,
    invoke: Callable = None,
    runs_root: Path = Path("runs"),
    max_parallel: int = 4,
) -> list:
    """Run several moves CONCURRENTLY as one fan, then record them in the arc in
    order — the PI testing competing sub-questions in parallel in a single cycle.

    Concurrency is made safe here, not left to luck: run-ids are pre-assigned
    sequentially (<study_id>-m<N>, distinct per move, so two runs never share a
    dir), the subprocess invokes run in a bounded thread pool (each move is an
    external process, so threads are the right tool), and the results are
    appended to arc.jsonl SEQUENTIALLY afterward, so the append-only arc is never
    written concurrently. A move that raises is caught and recorded as a failed
    result the PI reads next cycle — one bad run never sinks the fan. Returns the
    results in move order."""
    if invoke is None:
        from pi_agent.dispatch import invoke_move as invoke
    import concurrent.futures

    base = move_count(study) + 1
    prepared = []
    for i, move in enumerate(moves):
        _apply_study_bounds(study, move)
        move.run_id = f"{study.study_id}-m{base + i}"  # distinct, no collision
        prepared.append(move)

    results: list = [None] * len(prepared)

    def _one(i_and_move):
        i, move = i_and_move
        try:
            return i, invoke(move, runs_root=runs_root)
        except Exception as e:  # noqa: BLE001 — a failed run is a result, not a fan crash
            return i, {
                "move_type": getattr(getattr(move, "type", None), "value", "single"),
                "run_id": getattr(move, "run_id", None),
                "succeeded": False,
                "outcome": f"dispatch_error: {type(e).__name__}: {e}",
                "raw": {},
            }

    workers = max(1, min(max_parallel, len(prepared) or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for i, res in ex.map(_one, list(enumerate(prepared))):
            results[i] = res

    for i, result in enumerate(results):
        f = findings[i] if findings and i < len(findings) else None
        record_move(study, result, finding=f)
    return results
