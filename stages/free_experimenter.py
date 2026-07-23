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

INDEPENDENT RE-VERIFICATION. After you finish, a deterministic pass with NO model in it re-runs each finding you mark verified and regenerates its number from the ARTIFACT you name — its verdict, not your say-so, decides what stands. So for every finding you mark "verified": true, give a re-runnable "artifact":
- computed in code: save a self-contained Python file in your workspace that assigns your value to a metrics dict — `metrics["<quantity>"] = <value>` (define `metrics = {}` yourself so the file also runs standalone; it must be deterministic and need no network) — and reference it as "artifact": {"file": "<name>.py", "quantity": "<quantity>"}. The file's computed value must equal the "value" you report.
- produced by a specialized tool from the catalogue: "artifact": {"substrate_id": "<id>", "typed_input": {<the exact typed inputs>}, "quantity": "<metric name>"}.
A finding you cannot back with a re-runnable artifact must be reported with "verified": false — an honest caveat is fine, it just is not counted as reproduced.

Return ONLY JSON of the form: {"summary": "<what you found and what it means for the question>", "findings": [{"label": "<what this measures>", "value": <number or short string>, "verified": <true ONLY if you supply a re-runnable artifact>, "reproduce": "<how / which saved file to re-run>", "artifact": {"file": "<name>.py", "quantity": "<name>"} }], "publishable": <true only if the question is answered and every kept finding reproduced>} — omit "artifact" only on findings you mark "verified": false; no other fields anywhere."""

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
        if f.get("verified") and not _has_rerunnable_artifact(f.get("artifact")):
            errors.append(
                f"findings[{i}] is marked verified but carries no re-runnable "
                "'artifact' ({file, quantity} for a saved code file, or "
                "{substrate_id, typed_input, quantity} for a tool) — an "
                "independent re-run must be able to regenerate the value.")
    if not isinstance(data.get("publishable"), bool):
        errors.append("'publishable' must be a boolean.")
    return errors


def _has_rerunnable_artifact(art) -> bool:
    """True when `art` names something the wall can independently re-run: a saved
    workspace code file (file + quantity) or a substrate call (substrate_id +
    quantity)."""
    if not isinstance(art, dict):
        return False
    if art.get("file") and art.get("quantity"):
        return True
    return bool(art.get("substrate_id") and art.get("quantity"))


def _finding_artifact(art, workspace) -> Optional[dict]:
    """Translate a finding's model-authored `artifact` into the verification
    wall's artifact shape, or None. A code file becomes a workspace_file artifact
    with its path resolved ABSOLUTE against the run's workspace (where run_id is
    known), so the wall's rerun stays a pure re-execution; a substrate artifact
    is passed straight to the substrate kind."""
    if not isinstance(art, dict):
        return None
    if art.get("file"):
        path = art["file"]
        if workspace is not None:
            path = str((Path(workspace) / art["file"]).resolve())
        return {"kind": "workspace_file", "path": path,
                "quantity": art.get("quantity")}
    if art.get("substrate_id"):
        out = {"kind": "substrate"}
        out.update({k: v for k, v in art.items()})
        return out
    return None


def _claims_from_findings(findings: list, workspace) -> list:
    """One wall claim per finding: {value, artifact, label}. A finding with no
    re-runnable artifact carries artifact None, which the wall reports as
    'no_artifact' rather than dropping (an unverifiable claim must be counted,
    not silently shrink the denominator)."""
    return [
        {
            "value": f.get("value"),
            "artifact": _finding_artifact(f.get("artifact"), workspace),
            "label": f.get("label"),
        }
        for f in findings
    ]


def run_free_investigation(goal, *, run_id=None, call=None, verify=None) -> dict:
    """Host a FREE FULL agent on `goal` and return its structured result. `call`
    and `verify` are injected for tests; production uses call_stage_model (FULL
    profile — every tool + connector) and stages.verification.verify_run. Writes
    runs/<run_id>/free_investigation.json and a director-readable
    verification.json when run_id names an existing run dir.

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
    run_dir = Path("runs") / str(run_id) if run_id else None
    workspace = None
    if run_dir is not None and run_dir.is_dir():
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
    if run_dir is not None and run_dir.is_dir():
        # CONTROLLER RE-VERIFY (the wall is authoritative). A deterministic,
        # no-model pass re-runs each finding's saved artifact and its verdict —
        # not the agent's self-report — sets `verified`. It can only REMOVE
        # trust: a number the agent claimed verified that does not reproduce
        # drops the run's `publishable`; an honest unverified finding is a
        # caveat, not a claim, and never gates. verify_run writes the
        # director-readable verification.json.
        if verify is None:
            from stages.verification import verify_run
            verify = verify_run
        # The CLAIMS are the findings the agent kept as verified; each must
        # reproduce. A finding marked verified:false is an honest caveat, not a
        # claim — it is left untouched and never gates publishability.
        claimed = [(i, f) for i, f in enumerate(result["findings"])
                   if f.get("verified")]
        claims = _claims_from_findings([f for _, f in claimed], workspace)
        summary = verify(claims, run_id=str(run_id))  # writes verification.json
        by_index = {v.get("claim_index"): v for v in summary.get("verdicts", [])}
        all_reproduce = True
        for claim_i, (finding_i, _f) in enumerate(claimed):
            wall_verified = bool(by_index.get(claim_i, {}).get("verified"))
            if not wall_verified:
                all_reproduce = False
            result["findings"][finding_i]["verified"] = wall_verified
        result["publishable"] = bool(result["publishable"]) and all_reproduce
        (run_dir / "free_investigation.json").write_text(
            json.dumps(result, indent=2))
    return result
