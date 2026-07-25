"""pi_agent/dispatch.py — make a run callable, and make every move uniform.

THE PROBLEM THIS SOLVES. Today the top of the system is a fixed script:
supervisor.main() runs six stages and TERMINATES THE PROCESS — it returns None
and sys.exit()s on every terminal path (gate halt, crash, schema violation,
clean completion). A controller cannot call it and read what happened. For a PI
that runs many experiments toward one goal, "a run" has to become a thing you
invoke and get an ANSWER from.

THE APPROACH — SUBPROCESS, ON PURPOSE. A run is dispatched as its own process
and its result is read back from the evidence it leaves on disk. This is a
deliberate choice over converting the supervisor's five sys.exit() sites into
returned values: those exits ARE the loud-halt doctrine (the system stops
rather than fake a result), the most safety-critical convention in the repo.
Running each run as a subprocess leaves that doctrine untouched and
byte-identical — the run still exits loudly, and the controller reads the exit
plus the record the supervisor already writes. The system was built to leave
honest records precisely so someone could read them afterward; this is that
someone.

WHAT COMES BACK. Every terminal path in the supervisor journals a run_record
whose `extras` already carry the structured outcome (how_far, iterate_decision,
verification{publishable,verified,total}, needs_human_signoff,
allowed_substrates). That record, plus verification.json and the paper's
existence in the run dir, IS the structured result — assembled deterministically
by the supervisor, no baton-internals parsing. When NO run_record exists, that
is itself a signal: the run died without journaling (the watched external-kill
scenario), and read_run_result reports has_run_record=False rather than
inventing an outcome.

THE MOVE MENU. A PI dispatches two kinds of move through one interface:
  - SINGLE   — one whole free-agent run.
  - CAMPAIGN — the same run with the campaign loop enabled (an env flag on
               the same subprocess; NOT a different code path here).
  (The old in-process CHAIN move — one experiment spanning two REGISTERED
  substrates via the deleted stage pipeline — was PURGED 2026-07-23 with the
  free-agent purge. A free agent that needs several tools just calls them
  directly; a caged chain of registered substrates is strictly less than that.)

THE ONE BOUNDARY THIS LAYER KEEPS. It decides WHICH run to start and reads WHAT
came back. It never reaches inside a run to touch a measurement — the sealed
execution path and the sealed judges are unchanged and unreachable from here.
This layer is above execution, never inside it.

RUN-VENUE NOTE. CLAUDE.md's absolute rule: real runs launch from a plain
Terminal under caffeinate, never from a builder-session background task. This
module is the library that dispatches; WHERE the dispatching process itself runs
is the caller's responsibility and is not enforced in code.

No model call is made anywhere in this module. Determinism is not claimed —
dispatch_run starts a process that does whatever a run does — but the reading
and the env/arg construction are pure and are tested as such.
"""

from __future__ import annotations

import enum
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# The repo root: this file's parent's parent (pi_agent/dispatch.py -> root).
_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# The structured result of one whole run.
# --------------------------------------------------------------------------

@dataclass
class RunResult:
    """What a dispatched run leaves behind, read back into one object a
    decision-maker can branch on.

    `outcome` is the supervisor's own how_far string ("completed", "halted at
    gate after_stage_2", "halted_barren_budget_spent", "crashed at ...", ...).
    `publishable` is the verification verdict: True/False when the run reached
    verification, None when it never got that far. `has_run_record` is False
    only when the run left no journal record at all — a run that died without
    journaling, which the caller must treat as an incomplete run, not a success.
    """

    run_id: str
    exit_code: int
    run_dir: str
    has_run_record: bool
    outcome: Optional[str] = None
    iterate_decision: Optional[str] = None
    publishable: Optional[bool] = None
    verified: Optional[int] = None
    total: Optional[int] = None
    needs_human_signoff: bool = False
    allowed_substrates: Optional[list] = None
    paper_path: Optional[str] = None
    findings: list = field(default_factory=list)
    # The run's own model spend ({calls, tokens}), persisted by the run into its
    # run_record because a parent cannot see a subprocess's in-process cost meter
    # (free-director Phase 1). None when the run left no record — the same
    # has_run_record=False case where every other extras-derived field is None.
    cost: Optional[dict] = None
    # Reusable FILE artifacts the run produced and that REPRODUCED — each
    # {name, producer} (cross-run file hand-off, increment 3). A file crosses as
    # its re-runnable producer, never as bytes; only reproduced ones appear here.
    reusable_artifacts: list = field(default_factory=list)

    @property
    def completed(self) -> bool:
        """The run reached a clean, non-halted completion. NOT the same as
        publishable: a run can complete and still fail verification."""
        return self.exit_code == 0 and (self.outcome or "").startswith("completed")

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "exit_code": self.exit_code,
            "run_dir": self.run_dir,
            "has_run_record": self.has_run_record,
            "outcome": self.outcome,
            "iterate_decision": self.iterate_decision,
            "publishable": self.publishable,
            "verified": self.verified,
            "total": self.total,
            "needs_human_signoff": self.needs_human_signoff,
            "allowed_substrates": self.allowed_substrates,
            "paper_path": self.paper_path,
            "findings": self.findings,
            "cost": self.cost,
            "reusable_artifacts": self.reusable_artifacts,
            "completed": self.completed,
        }


def read_run_result(
    run_dir: Path,
    run_id: str,
    exit_code: int,
    run_record: Optional[dict],
) -> RunResult:
    """Assemble a RunResult from a finished run's evidence. PURE — no process,
    no journal read (the caller supplies the already-fetched run_record so this
    stays a testable pure function). Never raises: a malformed or missing piece
    becomes an absent field, because reading a result must not fail.

    The run_record's `extras` are the primary source (the supervisor assembled
    them deterministically at the terminal path). verification.json and the
    paper file are read from the run dir as corroboration and to fill the paper
    path. A None run_record means the run journaled nothing — has_run_record is
    False and every extras-derived field stays None.
    """
    run_dir = Path(run_dir)
    extras = {}
    outcome = None
    if isinstance(run_record, dict):
        extras = run_record.get("extras") or {}
        outcome = extras.get("how_far")

    verification = extras.get("verification") if isinstance(extras, dict) else None
    publishable = verified = total = None
    if isinstance(verification, dict):
        publishable = verification.get("publishable")
        verified = verification.get("verified")
        total = verification.get("total")

    # verification.json carries the per-claim VERDICTS — the measured values and
    # whether each one reproduced. The run_record extras carry only the summary
    # counts, so the actual FINDINGS (the data the PI reads to decide the next
    # move) are read from disk. Falls back to the summary counts too when the
    # record lacked them.
    findings, disk_summary = _read_verification(run_dir)
    if publishable is None and disk_summary:
        publishable = disk_summary.get("publishable")
        verified = disk_summary.get("verified")
        total = disk_summary.get("total")

    paper = run_dir / "stage6" / "paper.md"
    paper_path = str(paper) if paper.is_file() else None

    reusables = _read_reusable_artifacts(run_dir)

    return RunResult(
        run_id=run_id,
        exit_code=exit_code,
        run_dir=str(run_dir),
        has_run_record=isinstance(run_record, dict),
        outcome=outcome,
        iterate_decision=extras.get("iterate_decision") if isinstance(extras, dict) else None,
        publishable=publishable,
        verified=verified,
        total=total,
        needs_human_signoff=bool(extras.get("needs_human_signoff")) if isinstance(extras, dict) else False,
        allowed_substrates=extras.get("allowed_substrates") if isinstance(extras, dict) else None,
        paper_path=paper_path,
        findings=findings,
        cost=extras.get("cost") if isinstance(extras, dict) else None,
        reusable_artifacts=reusables,
    )


# The PI reads FINDINGS, not raw measurements. A finding is a value that already
# came out of the deterministic wrapper and was independently re-run by the
# verification pass — reading it is not touching a measurement, it is reading a
# result that already survived reproduction. The `verified` flag on each finding
# is the load-bearing signal: a value that did NOT reproduce is surfaced too, so
# the PI can see a shaky result rather than have it silently dropped.
_MAX_FINDINGS = 40


def _read_verification(run_dir: Path) -> tuple:
    """(findings, summary) from runs/<id>/verification.json, or ([], None) when
    the run never reached verification. Never raises — reading a result must not
    fail. Each finding is {label, value, verified, reason}, value being the
    reproduced number when it verified else the originally recorded one."""
    import json

    vpath = Path(run_dir) / "verification.json"
    if not vpath.is_file():
        return [], None
    try:
        vdata = json.loads(vpath.read_text())
    except Exception:  # noqa: BLE001
        return [], None

    findings = []
    for v in (vdata.get("verdicts") or [])[:_MAX_FINDINGS]:
        if not isinstance(v, dict):
            continue
        verified = bool(v.get("verified"))
        value = v.get("reproduced") if verified else v.get("original")
        findings.append(
            {
                "label": v.get("label"),
                "value": value,
                "verified": verified,
                "reason": v.get("reason"),
            }
        )
    summary = {
        "publishable": vdata.get("publishable"),
        "verified": vdata.get("verified"),
        "total": vdata.get("total"),
    }
    return findings, summary


def _read_reusable_artifacts(run_dir: Path) -> list:
    """The run's REPRODUCED reusable file artifacts, read from
    runs/<id>/free_investigation.json (cross-run file hand-off, increment 3). Only
    verified ones — a file may cross a run boundary only as a producer that
    re-emitted it. Never raises: a missing/malformed file is simply no artifacts.
    Each returned entry is {name, producer}, the minimum a downstream step inlines."""
    import json

    fpath = Path(run_dir) / "free_investigation.json"
    if not fpath.is_file():
        return []
    try:
        data = json.loads(fpath.read_text())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for ra in (data.get("reusable_artifacts") or [])[:_MAX_FINDINGS]:
        if isinstance(ra, dict) and ra.get("verified") and ra.get("name") and ra.get("producer"):
            out.append({"name": ra["name"], "producer": ra["producer"]})
    return out


# --------------------------------------------------------------------------
# Dispatching a whole run as a subprocess.
# --------------------------------------------------------------------------

def build_run_env(
    base_env: Optional[dict] = None,
    allowed_substrates: Optional[list] = None,
    campaign: bool = False,
    campaign_max_iters: Optional[int] = None,
    extra_env: Optional[dict] = None,
) -> dict:
    """The environment for a dispatched run. PURE. Starts from base_env (the
    caller's os.environ by default), then layers the move's knobs on top:

      - allowed_substrates -> ALLOWED_SUBSTRATES (the run-scoped constraint);
      - campaign=True       -> RESEARCH_CAMPAIGN=1 (the campaign loop);
      - campaign_max_iters  -> CAMPAIGN_MAX_ITERS.

    A None/empty allow-set leaves ALLOWED_SUBSTRATES exactly as inherited (the
    caller may already have set it); an explicit list REPLACES it, so a
    controller can scope each run independently. extra_env is applied last for
    anything a move needs that this function does not model.
    """
    env = dict(os.environ if base_env is None else base_env)
    if allowed_substrates:
        env["ALLOWED_SUBSTRATES"] = ",".join(allowed_substrates)
    if campaign:
        env["RESEARCH_CAMPAIGN"] = "1"
    if campaign_max_iters is not None:
        env["CAMPAIGN_MAX_ITERS"] = str(campaign_max_iters)
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    return env


def _default_command(run_id: str, domain: str, mode: str) -> list:
    """The argv for a real supervisor subprocess."""
    return [
        sys.executable,
        str(_ROOT / "supervisor.py"),
        "--mode", mode,
        "--domain", domain,
        "--run-id", run_id,
    ]


def _mint_run_id() -> str:
    """A fresh run id in the supervisor's exact format. Imported rather than
    re-derived, so the two never drift."""
    from supervisor import make_run_id

    return make_run_id()


def _fetch_run_record(run_id: str) -> Optional[dict]:
    """The most recent run_record for this run, or None. Best-effort: the
    journal is the shared store, read-only here."""
    try:
        from memory.journal import journal_search

        records = journal_search(run_id=run_id)
        for entry in records:  # journal_search returns most-recent-first
            if entry.get("kind") == "run_record":
                return entry
    except Exception:  # noqa: BLE001 — a missing record is a signal, not a crash
        pass
    return None


def dispatch_run(
    domain: str,
    mode: str = "auto",
    *,
    run_id: Optional[str] = None,
    allowed_substrates: Optional[list] = None,
    campaign: bool = False,
    campaign_max_iters: Optional[int] = None,
    extra_env: Optional[dict] = None,
    runs_root: Path = Path("runs"),
    timeout: Optional[float] = None,
    command_builder: Callable[[str, str, str], list] = _default_command,
    record_reader: Callable[[str], Optional[dict]] = _fetch_run_record,
) -> RunResult:
    """Run one whole relay as a subprocess and return its structured result.

    Mints a run id (unless given), builds the child env and argv, runs it to
    completion, then reads the result from runs_root/<run_id>/ plus the run's
    journal record. The child's sys.exit() is captured as exit_code — the
    loud-halt doctrine is preserved, not bypassed.

    `command_builder` and `record_reader` are injection seams for testing
    against a stub run without spending a live pipeline; production uses the
    real supervisor subprocess and the real journal.

    `runs_root` defaults to "runs" to match the supervisor's own hardcoded run
    dir; a test points both the stub and the reader at a tmp dir.

    Raises subprocess.TimeoutExpired if `timeout` is set and exceeded — a real
    research run is long, so timeout defaults to None (the PI's budget governs
    spend, not a wall clock here).
    """
    rid = run_id or _mint_run_id()
    env = build_run_env(
        allowed_substrates=allowed_substrates,
        campaign=campaign,
        campaign_max_iters=campaign_max_iters,
        extra_env=extra_env,
    )
    command = command_builder(rid, domain, mode)
    completed = subprocess.run(
        command,
        cwd=str(_ROOT),
        env=env,
        timeout=timeout,
    )
    run_dir = Path(runs_root) / rid
    run_record = record_reader(rid)
    return read_run_result(run_dir, rid, completed.returncode, run_record)


# --------------------------------------------------------------------------
# The uniform move interface.
# --------------------------------------------------------------------------

class MoveType(str, enum.Enum):
    """The kinds of move a PI can dispatch. A str-enum so it logs and journals
    as its plain name."""

    SINGLE = "single"
    CAMPAIGN = "campaign"


@dataclass
class Move:
    """One move request. The fields used depend on `type`:

      SINGLE / CAMPAIGN — domain (required), mode, allowed_substrates,
        campaign_max_iters (CAMPAIGN only), extra_env, optional run_id.

    Validation is deferred to invoke_move so a Move can be constructed and
    inspected before it is run.
    """

    type: MoveType
    domain: Optional[str] = None
    mode: str = "auto"
    allowed_substrates: Optional[list] = None
    campaign_max_iters: Optional[int] = None
    extra_env: Optional[dict] = None
    run_id: Optional[str] = None


@dataclass
class MoveResult:
    """The uniform envelope every move returns. `raw` carries the move-specific
    structured result (a RunResult.as_dict() for run moves); `outcome` and
    `succeeded` are the normalized read a decision-maker branches on without
    knowing the move type."""

    move_type: str
    run_id: str
    succeeded: bool
    outcome: Optional[str]
    raw: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "move_type": self.move_type,
            "run_id": self.run_id,
            "succeeded": self.succeeded,
            "outcome": self.outcome,
            "raw": self.raw,
        }


def invoke_move(
    move: Move,
    *,
    runs_root: Path = Path("runs"),
    dispatch: Callable[..., RunResult] = dispatch_run,
) -> MoveResult:
    """Run any move through one interface and return one envelope.

    SINGLE / CAMPAIGN dispatch a subprocess run. `dispatch` is an injection seam
    for testing the run moves without a live subprocess.

    Raises ValueError on a malformed move (a run move with no domain) — a
    controller error, caught loudly here rather than producing an empty or
    fabricated result.
    """
    if move.type in (MoveType.SINGLE, MoveType.CAMPAIGN):
        if not move.domain:
            raise ValueError(f"a {move.type.value} move requires a domain.")
        result = dispatch(
            move.domain,
            move.mode,
            run_id=move.run_id,
            allowed_substrates=move.allowed_substrates,
            campaign=(move.type == MoveType.CAMPAIGN),
            campaign_max_iters=move.campaign_max_iters,
            extra_env=move.extra_env,
            runs_root=runs_root,
        )
        # A run move "succeeded" as a MOVE if it produced a standing paper;
        # a halt or an unpublishable paper is a real outcome the PI reads, not
        # a dispatch failure — but it is not a success to build the arc on.
        succeeded = bool(result.publishable)
        return MoveResult(
            move_type=move.type.value,
            run_id=result.run_id,
            succeeded=succeeded,
            outcome=result.outcome,
            raw=result.as_dict(),
        )

    raise ValueError(f"unknown move type: {move.type!r}")
