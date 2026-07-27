"""referee.py — artifact review of the finished study paper.

WHY THIS EXISTS. The wall proves each kept number re-executes; study_paper then
writes only from wall-verified findings. What nothing checks is the LAYER OF
WORDS the paper adds on top: whether the code behind a claim does what the
paper says it does, whether a comparison's "baseline" is really the stated
baseline, whether the prose around a verified number asserts more than the
number established. The 2026-07-26 side-project experiment
(~/ai-scientist-reviewer/DEBRIEF.md) measured exactly this: an agent reviewing
a paper AGAINST ITS ARTIFACTS caught the fabrication-class flaws of
AI-generated papers at 88% with zero false alarms, while a text-only reader of
the same model was structurally blind to them.

WHY THIS MAY HOLD TOOLS WHEN desk_review MAY NOT. The sealed-only rule guards
stages that RENDER A JUDGMENT (a verdict can find its answer key, and a system
that reruns until a verdict flips optimizes for the judge). The referee renders
no verdict and gates nothing: it files findings, each carrying an evidence
pointer a human can check in under a minute, and the findings land in the
paper's own "must validate" territory. It is kin to the wall — a verification
pass over the deliverable — not to the desk gate. Reading the artifacts is not
a leak here; it is the entire job.

DISPOSITION (v1, expand on evidence). Findings never halt anything and trigger
no rewrite loop yet: high/med findings are APPENDED to paper.md as a
deterministic, Python-written "Referee findings" section (same idiom as
study_paper's correction block — the paper is never silently wrong, and never
silently rewritten either). referee.json + referee_report.md land beside the
paper. A failed review returns {error} and never raises: the referee is a
deliverable-checker, not a gate. Kill switch: REFEREE=0.

DELIBERATELY OUT OF v1: novelty/citation checks (need an S2_API_KEY ruling —
the side project measured keyless S2 as the reviewer's one systematic failure)
and any rewrite loop (add when a real study shows appended findings are not
enough). Number re-verification stays the wall's job alone."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for

REFEREE_MODEL = model_for("heavy")
REFEREE_STAGE_NAME = "study_referee"

# Bounds on the bundle written for the referee; the study's disk state stays
# complete either way — these cap only what is COPIED into the review bundle.
MAX_PAPER_CHARS = 60_000
MAX_CLAIM_ARTIFACTS = 24
MAX_CODE_CHARS = 8_000
MAX_FINDINGS_OUT = 24

CATEGORIES = ("mechanism_mismatch", "baseline_illegitimate",
              "transcription_error", "contradiction", "structural")

SYSTEM_PROMPT = """You are a referee reviewing a finished study write-up AGAINST THE ARTIFACTS that produced it. The numbers in the paper marked VERIFIED have already been independently re-executed — do not re-verify numbers. Your job is the layer the number-check cannot see: whether the WORDS are true of the artifacts.

Your working directory contains:
- paper.md — the write-up under review;
- claims.json — every wall-checked claim: its label, its value, its verdict, and the code that produced it;
- findings.json — the verified and unverified findings lists the writer was given.

Work these checks, in order:
1. MECHANISM: for each claim whose code is present, does the code implement what the paper says it does? Hardcoded "swept" parameters, named methods the code does not perform, measurements read from something other than what the text names.
2. BASELINE LEGITIMACY: for every comparison the paper makes, is the comparison condition's code genuinely the stated condition?
3. TRANSCRIPTION: does the prose around each verified number claim only what that number established? A verified value described with an unverified mechanism, scope, or cause is a finding.
4. INTERNAL CONSISTENCY & STRUCTURE: contradictions between sections, figures referenced but absent, placeholder text, provenance tags (VERIFIED/COMPUTED/JUDGEMENT) used contrary to the lists you were given.

Rules:
- Every finding needs evidence checkable in under a minute: a quoted code line vs a quoted paper sentence, a pair of conflicting statements, a missing file name. No evidence, no finding.
- Do not pad. Style is not a finding. A correct, dull paper must pass with zero findings.
- You may run code read-only to check something (python is available), but you change nothing: you are reviewing, not repairing.

Return ONLY JSON:
{"findings": [{"id": "R-01", "category": "mechanism_mismatch|baseline_illegitimate|transcription_error|contradiction|structural", "claim": "<one sentence>", "evidence": "<the checkable pointer>", "severity": "high|med|low", "confidence": <0.0-1.0>}, ...], "summary": "<2-4 sentences>"} — no other fields."""

SCHEMA = {"required": ["findings", "summary"]}


def _enabled() -> bool:
    return os.environ.get("REFEREE", "1") != "0"


def _validate(data: dict) -> list:
    errs = []
    if not isinstance(data.get("findings"), list):
        errs.append("'findings' must be a list (empty is a valid review).")
        return errs
    for i, f in enumerate(data["findings"]):
        if not isinstance(f, dict):
            errs.append(f"findings[{i}] must be an object")
            continue
        if f.get("category") not in CATEGORIES:
            errs.append(f"findings[{i}].category must be one of {CATEGORIES}")
        if f.get("severity") not in ("high", "med", "low"):
            errs.append(f"findings[{i}].severity must be high|med|low")
        if not str(f.get("evidence") or "").strip():
            errs.append(f"findings[{i}] has no evidence — a finding without a "
                        "checkable pointer must not be emitted")
    return errs


def _collect_claim_artifacts(study: Any) -> list:
    """Every wall-checked claim across the study's runs, with its code, read
    from the verification.json files the wall already wrote. Pure disk reads;
    a run without one contributes nothing (honest absence, not a guess)."""
    from pi_agent.study import study_findings
    rows = []
    for entry in study_findings(study):
        run_id = entry.get("run_id")
        if not run_id:
            continue
        vpath = Path("runs") / str(run_id) / "verification.json"
        try:
            summary = json.loads(vpath.read_text())
        except Exception:  # noqa: BLE001 — absence is data, not an error
            continue
        for v in summary.get("verdicts", []) or []:
            art = v.get("artifact") if isinstance(v, dict) else None
            code = ""
            if isinstance(art, dict) and art.get("kind") == "code":
                code = str(art.get("code") or "")[:MAX_CODE_CHARS]
            rows.append({
                "phase_seq": entry.get("seq"),
                "run_id": run_id,
                "label": v.get("label"),
                "value": v.get("value"),
                "wall_verdict": ("verified" if v.get("verified")
                                 else v.get("reason") or "not_reproduced"),
                "code": code,
            })
            if len(rows) >= MAX_CLAIM_ARTIFACTS:
                return rows
    return rows


def referee_study_paper(study: Any, *, call=None) -> dict:
    """Review studies/<id>/paper.md against the study's artifacts.

    Returns {report_path, findings, appended} on success, else {error}.
    `call` is injected in tests. Never raises."""
    if not _enabled():
        return {"error": "referee disabled (REFEREE=0)"}
    call = call or call_stage_model

    paper_path = study.dir / "paper.md"
    if not paper_path.is_file():
        return {"error": "no paper.md in this study — nothing to referee"}

    try:
        from stages.study_paper import collect_study_evidence
        evidence = collect_study_evidence(study)
        claim_rows = _collect_claim_artifacts(study)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not read the study's artifacts: "
                         f"{type(e).__name__}: {e}"}

    from pi_agent.study import study_scratch_dir
    bundle = study_scratch_dir(study) / "referee"
    try:
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "paper.md").write_text(paper_path.read_text()[:MAX_PAPER_CHARS])
        (bundle / "claims.json").write_text(json.dumps(claim_rows, indent=2))
        (bundle / "findings.json").write_text(json.dumps(
            {"verified": evidence["verified_findings"],
             "unverified": evidence["unverified_findings"]}, indent=2))
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not build the review bundle: "
                         f"{type(e).__name__}: {e}"}

    with agent_workspace(bundle):
        try:
            data, _timing = call(
                REFEREE_STAGE_NAME, SYSTEM_PROMPT,
                {"study_goal": study.goal, "n_claims": len(claim_rows)},
                SCHEMA, model=REFEREE_MODEL, extra_validator=_validate,
                capabilities=FULL)
        except Exception as e:  # noqa: BLE001
            return {"error": f"referee review failed: {type(e).__name__}: {e}"}

    findings = [f for f in (data.get("findings") or [])
                if isinstance(f, dict)][:MAX_FINDINGS_OUT]
    report = {"summary": data.get("summary") or "", "findings": findings}

    try:
        (study.dir / "referee.json").write_text(json.dumps(report, indent=2))
        report_path = study.dir / "referee_report.md"
        report_path.write_text(_render_report(report, study))
        appended = _append_to_paper(paper_path, findings)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not save the referee report: "
                         f"{type(e).__name__}: {e}"}

    return {"report_path": str(report_path), "findings": findings,
            "appended": appended}


def _render_report(report: dict, study: Any) -> str:
    lines = [f"# Referee report — {study.study_id}",
             "", report.get("summary") or "", "",
             f"## Findings ({len(report['findings'])})"]
    for f in report["findings"]:
        lines += ["",
                  f"### {f.get('id')} [{f.get('category')}] "
                  f"severity={f.get('severity')} confidence={f.get('confidence')}",
                  f"**Claim:** {f.get('claim')}",
                  f"**Evidence:** {f.get('evidence')}"]
    if not report["findings"]:
        lines += ["", "No findings. The words survived contact with the artifacts."]
    return "\n".join(lines) + "\n"


def _append_to_paper(paper_path: Path, findings: list) -> int:
    """Deterministically append high/med findings to the paper — the same idiom
    as study_paper's correction block: the paper is never silently wrong, and
    never silently rewritten. Low-severity findings stay in the report only.
    Returns how many findings were appended."""
    worth = [f for f in findings if f.get("severity") in ("high", "med")]
    if not worth:
        return 0
    lines = ["", "", "## Referee findings (artifact review)",
             "", "_An independent artifact-review pass checked this paper's "
             "words against the code and records that produced it. It found "
             "the following; each belongs on the must-validate list._", ""]
    for f in worth:
        lines.append(f"- **[{f.get('severity')}] {f.get('claim')}** — "
                     f"{f.get('evidence')}")
    paper_path.write_text(paper_path.read_text() + "\n".join(lines) + "\n")
    return len(worth)


def referee_study_paper_by_id(study_id: str, *,
                              studies_root: Optional[Path] = None,
                              call=None) -> dict:
    from pi_agent.study import STUDIES_ROOT, load_study
    try:
        study = load_study(study_id,
                           studies_root=studies_root or STUDIES_ROOT)
    except Exception as e:  # noqa: BLE001
        return {"error": f"no such study {study_id!r}: {type(e).__name__}: {e}"}
    return referee_study_paper(study, call=call)
