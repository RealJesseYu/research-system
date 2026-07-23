"""free_experimenter.py — the un-caged experimenter (PRIME DIRECTIVE).

See CLAUDE.md's PRIME DIRECTIVE and memory/substrates-are-tools-not-a-cage.md:
the experimenter is a FREE agent, NEVER limited to registered substrates. Given a
goal, a FULL agent investigates however it wants — writing and running code,
reaching for any tool or connector (CAD, web, a solver, a substrate wrapper) —
and returns findings plus how to reproduce them. Substrates, if used, are just
tools it may reach for; they never bound what it can do.

This is the 'add the free path' step (the repo's own M1 pattern): it runs
alongside the caged composition experimenter (tools/compose_agent.py, whose action
space is 'a scalar recipe over registered substrates'). Once validated live, it
REPLACES that path and the cage is purged.

Verification is NOT architecturally limiting (owner, 2026-07-23): the agent is
told to save the artifact/code that produced every kept result so it re-runs, and
a downstream deterministic pass may re-run the re-runnable claims. That discipline
applies to a KEPT number — it never restricts which tools the agent uses.
"""

from __future__ import annotations

import json
from pathlib import Path

from model_call import FULL, agent_workspace, call_stage_model

# Opus: the experimenter is the hard creative/analytic work (CLAUDE.md roles).
FREE_EXPERIMENTER_MODEL = "claude-opus-4-8"
# NON-sealed name on purpose: the free experimenter ROAMS (FULL profile). It is
# above measurement-judging; capability_guard permits it the FULL tools.
FREE_STAGE_NAME = "free_experimenter"

SYSTEM_PROMPT = """You are an autonomous experimenter with NO restriction on HOW you investigate. You have every tool: write and run code (Bash), read and write files in your workspace, search and fetch the web, and any connector available to you. Nothing limits which tools you reach for — use whatever answers the question best. There is no fixed menu of instruments; a registered scientific tool, if one helps, is just one option among all your tools, never a boundary. A catalogue of validated specialized tools you MAY (optionally) call is at the END of this prompt — reach for one only if it helps.

YOUR WORKSPACE: your current working directory is a private, initially-empty workspace for this run. Create and run every file there using relative paths (e.g. write "solve.py", run "python solve.py") — everything you save persists as this run's reproducible record. The specialized tools in the catalogue below remain importable from here exactly as shown (e.g. `from tools.run_rdkit import run_rdkit`).

Investigate the QUESTION in your input. Work small-before-big: run a cheap check, look at the actual result, then scale up, change approach, or stop when the question is answered — that judgment is yours, read off what you actually observed. DO REAL WORK: actually compute, build, run, or test. Do not just plan or describe.

EVERY result you KEEP must be reproducible: save the code or artifact that produced it into your workspace and say how to re-run it. A number or result you cannot reproduce, you must not claim — report it as unverified instead of dropping it. This is about honesty of a kept result; it never limits which tools you use to get there.

Return ONLY JSON of the form: {"summary": "<what you found and what it means for the question>", "findings": [{"label": "<what this measures>", "value": <number or short string>, "verified": <true if you reproduced it>, "reproduce": "<how / which saved file to re-run>"}], "publishable": <true only if the question is answered and every kept finding reproduced>} — no other fields anywhere."""

SCHEMA = {"required": ["summary", "findings", "publishable"]}


def _validate_free_result(data: dict) -> list[str]:
    """Plain-language errors (re-asked in the bounded loop). Structural only —
    it never second-guesses WHAT the agent investigated, only that the report is
    shaped so a director can read it and a kept claim names its reproduction."""
    errors: list[str] = []
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("'findings' must be a list (may be empty).")
        return errors
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}] must be an object.")
            continue
        if not str(f.get("label") or "").strip():
            errors.append(f"findings[{i}] needs a non-empty 'label'.")
        if "value" not in f:
            errors.append(f"findings[{i}] needs a 'value'.")
        if f.get("verified") and not str(f.get("reproduce") or "").strip():
            errors.append(
                f"findings[{i}] is marked verified but has no 'reproduce' — a "
                "kept result must say how to re-run it.")
    if not isinstance(data.get("publishable"), bool):
        errors.append("'publishable' must be a boolean.")
    return errors


def _verification_record(result: dict) -> dict:
    """Map the free result into the shape the PI director reads
    (pi_agent.dispatch._read_verification): {verdicts, publishable, verified,
    total}. So a free investigation feeds the director's arc exactly as any run."""
    findings = result.get("findings") or []
    verdicts = []
    for f in findings:
        verified = bool(f.get("verified"))
        verdicts.append({
            "label": f.get("label"),
            "verified": verified,
            "reproduced": f.get("value") if verified else None,
            "original": f.get("value"),
            "reason": f.get("reproduce"),
        })
    return {
        "verdicts": verdicts,
        "publishable": bool(result.get("publishable")),
        "verified": sum(1 for f in findings if f.get("verified")),
        "total": len(findings),
    }


def run_free_investigation(goal, *, run_id=None, call=None) -> dict:
    """Host a FREE FULL agent on `goal` and return its structured result. `call`
    is injected for tests; production uses call_stage_model with the FULL profile
    (every tool + connector). Writes runs/<run_id>/free_investigation.json and a
    director-readable verification.json when run_id names an existing run dir.

    NO substrate cage: the agent is not handed a substrate menu and is not
    constrained to a composition recipe — it investigates directly."""
    call = call or call_stage_model
    # Append the specialized-tools catalogue (PRIME DIRECTIVE: substrates are
    # OPTIONAL tools the agent may reach for, never a gate). Assembled at call
    # time so a newly-enrolled wrapper appears without editing this stage.
    from tools.substrate_registry import substrate_tools_catalog
    system_prompt = SYSTEM_PROMPT + "\n\n" + substrate_tools_catalog()
    stage_input = {"question": goal}
    # Per-run workspace: give the agent an isolated cwd (runs/<id>/workspace/) so
    # its artifacts land there, reproducible-in-place with the run evidence,
    # instead of polluting the repo root. Only when run_id names an existing run
    # dir; otherwise workspace stays None and the agent keeps the default cwd
    # (call-free tests are byte-identical). model_call sets PYTHONPATH to the
    # repo root under the workspace, so `from tools.run_X import ...` still works.
    workspace = None
    if run_id:
        run_dir = Path("runs") / str(run_id)
        if run_dir.is_dir():
            workspace = (run_dir / "workspace").resolve()
            workspace.mkdir(exist_ok=True)
    with agent_workspace(workspace):
        data, _timing = call(
            FREE_STAGE_NAME,
            system_prompt,
            stage_input,
            SCHEMA,
            model=FREE_EXPERIMENTER_MODEL,
            extra_validator=_validate_free_result,
            capabilities=FULL,
        )
    result = {
        "goal": goal,
        "summary": data.get("summary"),
        "findings": data.get("findings") or [],
        "publishable": bool(data.get("publishable")),
    }
    if run_id:
        run_dir = Path("runs") / str(run_id)
        if run_dir.is_dir():
            (run_dir / "free_investigation.json").write_text(
                json.dumps(result, indent=2))
            (run_dir / "verification.json").write_text(
                json.dumps(_verification_record(result), indent=2))
    return result
