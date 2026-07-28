"""free_paper.py — write up a FREE run as a paper (optional route).

WHY NOT stage6_paper. The old paper stage is bound to the deleted pipeline's
outputs — a stage-3 fidelity verdict and a stage-5 "thought" object read from
disk — and it emits no figures. A free run has neither, so bolting it on would
mean fabricating inputs it was never meant to have. This is the paper route for
the FREE architecture instead.

WHAT IT DOES. A fresh FULL agent (a separate pass — it did not run the
investigation, so it is not grading and writing its own work in one breath)
writes the manuscript from the run's WALL-VERIFIED findings (never the agent's
self-report) and the artifacts in the run's workspace, generating figures from
that data. It keeps stage6_paper's one genuinely load-bearing habit — a
mandatory "What a human must still validate" section — sourced from exactly what
the wall could and could not reproduce.

Best-effort: a failed write-up returns an error and never raises into the
caller. A paper is a deliverable, not a gate; a good run is not undone because
the write-up stumbled.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for  # model-tier resolver

PAPER_MODEL = model_for("heavy")
PAPER_STAGE_NAME = "free_paper"

SYSTEM_PROMPT = """You are writing a short scientific paper from a COMPLETED investigation you did not run. You are given the GOAL, the VERIFIED FINDINGS — numbers an independent, no-model re-run has already reproduced (these, and ONLY these, are trustworthy results) — and the UNVERIFIED findings (things that did not reproduce or could not be checked). Your current working directory is the run's workspace: it holds the code and artifacts that produced the findings. Read them, and run code (e.g. matplotlib) to GENERATE FIGURES from that data where a figure genuinely helps.

Write a self-contained paper to a file named paper.md in your workspace, in Markdown, with sections: Abstract, Background, Method, Results, Limitations. RESULTS must report ONLY the verified numbers you were given, each noted as independently reproduced. If a figure clarifies a result, generate it (save a .png in the workspace) and embed it with ![caption](figure.png). Do NOT invent numbers. Do NOT present any unverified finding as established — those go in Limitations.

END with a section "## What a human must still validate": one bullet per claim or assumption a human should check before trusting this paper — every unverified finding belongs here, plus any modelling assumption you relied on.

Return ONLY JSON: {"paper_file": "paper.md", "figures": ["<png files you generated>"], "human_must_validate": ["<bullet>", ...]} — no other fields."""

SCHEMA = {"required": ["paper_file", "human_must_validate"]}


def _validate(data: dict) -> list:
    errs = []
    if not str(data.get("paper_file") or "").strip():
        errs.append("'paper_file' must name the markdown file you wrote.")
    if not isinstance(data.get("human_must_validate"), list):
        errs.append("'human_must_validate' must be a list (may be empty).")
    return errs


def write_free_paper(run_id, *, call=None) -> dict:
    """Write runs/<run_id>/paper.md from the run's wall-verified findings.

    Reads verification.json (the AUTHORITATIVE results) and free_investigation.json
    (for the goal), hosts a fresh FULL agent in the run's workspace to draft the
    paper + figures, and copies its paper.md up to runs/<run_id>/paper.md.
    Returns {paper_path, human_must_validate} on success, else {error}. `call` is
    injected in tests. Never raises."""
    call = call or call_stage_model
    run_dir = Path("runs") / str(run_id)
    if not run_dir.is_dir():
        return {"error": f"no run dir for {run_id!r}"}
    workspace = (run_dir / "workspace")
    workspace.mkdir(exist_ok=True)
    workspace_abs = workspace.resolve()

    try:
        vsummary = json.loads((run_dir / "verification.json").read_text())
    except (OSError, ValueError):
        vsummary = {"verdicts": []}
    verdicts = vsummary.get("verdicts") or []
    verified = [v for v in verdicts if v.get("verified")]
    unverified = [v for v in verdicts if not v.get("verified")]

    try:
        inv = json.loads((run_dir / "free_investigation.json").read_text())
    except (OSError, ValueError):
        inv = {}

    stage_input = {
        "goal": inv.get("goal") or "",
        "investigation_summary": inv.get("summary") or "",
        "verified_findings": [
            {"label": v.get("label"), "value": v.get("reproduced")} for v in verified
        ],
        "unverified_findings": [
            {"label": v.get("label"), "reason": v.get("reason")} for v in unverified
        ],
    }

    with agent_workspace(workspace_abs):
        try:
            data, _timing = call(
                PAPER_STAGE_NAME, SYSTEM_PROMPT, stage_input, SCHEMA,
                model=PAPER_MODEL, extra_validator=_validate, capabilities=FULL)
        except Exception as e:  # noqa: BLE001 — a paper is a deliverable, not a gate
            return {"error": f"paper write-up failed: {type(e).__name__}: {e}"}

    paper_file = data.get("paper_file") or "paper.md"
    # CONTAINED, because paper_file is MODEL-AUTHORED and pathlib lets an
    # absolute right operand win: "/etc/passwd" or "../../.env" escaped the
    # scratch/workspace root and was COPIED INTO THE DELIVERABLE. Figures already
    # get a filename guard; this did not. A bare filename is all a paper needs.
    _root = Path(workspace_abs).resolve()
    src = (_root / paper_file).resolve()
    if not src.is_relative_to(_root):
        return {"error": f"agent reported paper_file {paper_file!r}, which "
                          "resolves outside its own working directory; refusing "
                          "to copy it into the deliverable"}
    if not src.is_file():
        return {"error": f"agent reported {paper_file!r} but no such file was written"}
    dest = run_dir / "paper.md"
    shutil.copyfile(src, dest)
    return {"paper_path": str(dest),
            "human_must_validate": data.get("human_must_validate") or [],
            "figures": data.get("figures") or []}
