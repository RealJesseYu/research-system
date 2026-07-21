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

THE MOVE MENU. A PI dispatches three kinds of move through one interface:
  - SINGLE   — one whole relay run.
  - CAMPAIGN — the same relay with the campaign loop enabled (an env flag on
               the same subprocess; NOT a different code path here).
  - CHAIN    — one experiment spanning two substrates, run in-process via
               stages.chain_runner.run_chain. A chain's fidelity verdicts are a
               judgment, so run_chain demands a verdict_fn with NO default and
               this layer keeps that discipline: a CHAIN move MUST carry a
               verdict source; nothing is fabricated. Wiring that source to the
               live stage-3 gate is a later increment (it spends a model call
               per node and cannot be exercised offline).

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
    else:
        # Fall back to verification.json on disk if the record lacked it.
        vpath = run_dir / "verification.json"
        if vpath.is_file():
            try:
                import json

                vdata = json.loads(vpath.read_text())
                publishable = vdata.get("publishable")
                verified = vdata.get("verified")
                total = vdata.get("total")
            except Exception:  # noqa: BLE001 — reading a result must not fail
                pass

    paper = run_dir / "stage6" / "paper.md"
    paper_path = str(paper) if paper.is_file() else None

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
    )


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
    CHAIN = "chain"


@dataclass
class Move:
    """One move request. The fields used depend on `type`:

      SINGLE / CAMPAIGN — domain (required), mode, allowed_substrates,
        campaign_max_iters (CAMPAIGN only), extra_env.
      CHAIN — chain (the {nodes:[...]} object) and verdict_fn (REQUIRED, no
        default: a chain's verdicts are a judgment this layer will not
        manufacture), plus optional run_id / allowed_substrates.

    Validation is deferred to invoke_move so a Move can be constructed and
    inspected before it is run.
    """

    type: MoveType
    domain: Optional[str] = None
    mode: str = "auto"
    allowed_substrates: Optional[list] = None
    campaign_max_iters: Optional[int] = None
    extra_env: Optional[dict] = None
    chain: Optional[dict] = None
    verdict_fn: Optional[Callable] = None
    run_id: Optional[str] = None


@dataclass
class MoveResult:
    """The uniform envelope every move returns. `raw` carries the move-specific
    structured result (a RunResult.as_dict() for run moves, the chain record for
    a chain); `outcome` and `succeeded` are the normalized read a decision-maker
    branches on without knowing the move type."""

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

    SINGLE / CAMPAIGN dispatch a subprocess run; CHAIN runs in-process through
    stages.chain_runner.run_chain with the move's supplied verdict_fn. `dispatch`
    is an injection seam for testing the run moves without a live subprocess.

    Raises ValueError on a malformed move (a run move with no domain, a chain
    move with no chain or no verdict source) — a controller error, caught loudly
    here rather than producing an empty or fabricated result.
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

    if move.type == MoveType.CHAIN:
        if not isinstance(move.chain, dict):
            raise ValueError("a chain move requires a chain object {nodes: [...]}.")
        if move.verdict_fn is None:
            raise ValueError(
                "a chain move requires a verdict_fn: a chain's fidelity verdicts "
                "are a judgment, and this layer will not manufacture one — supply "
                "the verdict source (the live stage-3 gate adapter, or a test "
                "double). Same discipline run_chain itself holds."
            )
        rid = move.run_id or _mint_run_id()
        from stages import chain_runner

        record = chain_runner.run_chain(rid, move.chain, verdict_fn=move.verdict_fn)
        # A chain "succeeded" as a move when it executed both nodes (a halt is a
        # real, readable outcome, but not something the arc builds on).
        succeeded = record.get("status") == "executed"
        outcome = record.get("status")
        if succeeded and isinstance(record.get("chain_verdict"), dict):
            outcome = f"executed:{record['chain_verdict'].get('label')}"
        return MoveResult(
            move_type=move.type.value,
            run_id=rid,
            succeeded=succeeded,
            outcome=outcome,
            raw=record,
        )

    raise ValueError(f"unknown move type: {move.type!r}")
