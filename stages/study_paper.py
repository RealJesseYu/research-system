"""study_paper.py — write up a whole STUDY as a paper (+figures).

WHY THIS EXISTS. stages/free_paper.py writes up ONE run. A study is the unit of
work that actually answers a goal: many phases, some of them spawned
sub-investigations, each contributing verified numbers and reusable artifacts,
plus an integration check that they compose. Until now a director-run study
produced NO paper at all — the director never invoked the run-level route, and
dispatch looked for a paper at runs/<id>/stage6/paper.md, a path from the
deleted six-stage pipeline that can never exist in a free run. So the system
could do excellent multi-phase work and emit nothing a human could read.

WHAT IT DOES. A fresh FULL agent — separate from every agent that did the
investigating, so nothing grades and writes its own work in one breath — reads
the study's whole arc and drafts paper.md with figures. It is given ONLY:
  - the goal,
  - the VERIFIED findings across every phase (the wall reproduced these),
  - the UNVERIFIED ones, separately, as caveats,
  - the reusable file artifacts, as re-runnable producers,
  - the shape of the arc (which phase produced what).
It keeps free_paper's one load-bearing habit — a mandatory "What a human must
still validate" section — sourced from exactly what the wall could not reproduce.

THE MEASUREMENT BOUNDARY HOLDS. Only verified numbers are presented as results;
narration never becomes a claim, and the agent is told not to invent numbers. It
writes into the study's own scratch dir (never the repo root).

Best-effort: a failed write-up returns an error and never raises into the caller.
A paper is a deliverable, not a gate — a good study is not undone because the
write-up stumbled.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for

PAPER_MODEL = model_for("heavy")
PAPER_STAGE_NAME = "study_paper"

# Bounds on what travels into the prompt, so a long study cannot grow it without
# limit. The study's own arc stays complete on disk either way.
MAX_FINDINGS = 60
MAX_PHASES = 40

SYSTEM_PROMPT = """You are writing a short scientific paper from a COMPLETED multi-phase investigation you did not run. A director held one GOAL and drove an arc of phases — some of them experiments, some delegated sub-investigations, some integration checks that tested whether the parts compose. You are given what that arc produced.

You are given VERIFIED FINDINGS — numbers an independent, no-model re-run has already reproduced. These, and ONLY these, are trustworthy results. You are also given UNVERIFIED findings (things that did not reproduce or could not be checked), the ARC (which phase produced what), and any REUSABLE ARTIFACTS the study built, each as a re-runnable producer.

Your current working directory is a private scratch directory. Write a self-contained paper to a file named paper.md there, in Markdown, with sections: Abstract, Background, Method, Results, Limitations. METHOD should describe the arc as an investigation — what was asked first, what each phase found, how later phases built on earlier ones, and what the integration check (if any) established that per-phase results could not. RESULTS must report ONLY the verified numbers you were given, each noted as independently reproduced.

FIGURES: where a figure genuinely clarifies a result, generate it — run python with matplotlib, save a .png beside paper.md, and embed it with ![caption](figure.png). Build figures only from the numbers you were given. Do not fabricate data to make a figure look fuller.

Do NOT invent numbers. Do NOT present any unverified finding as established — those belong in Limitations.

END with a section "## What a human must still validate": one bullet per claim or assumption a human should check before trusting this paper. Every unverified finding belongs here, plus any modelling assumption the investigation relied on, plus anything the arc asserted but never measured.

Return ONLY JSON: {"paper_file": "paper.md", "figures": ["<png files you generated>"], "human_must_validate": ["<bullet>", ...]} — no other fields."""

SCHEMA = {"required": ["paper_file", "human_must_validate"]}


def _validate(data: dict) -> list:
    errs = []
    if not str(data.get("paper_file") or "").strip():
        errs.append("'paper_file' must name the markdown file you wrote.")
    if not isinstance(data.get("human_must_validate"), list):
        errs.append("'human_must_validate' must be a list (may be empty).")
    return errs


def collect_study_evidence(study: Any) -> dict:
    """Everything the paper agent is allowed to see, read from the study's disk
    state. Pure. Verified and unverified findings are SEPARATED here, in Python,
    so the split can never depend on the writing agent's judgment — the same
    discipline free_paper uses at the run level.

    A finding's `verified` flag is the WALL's verdict by the time it reaches the
    arc (the run controller overwrote the agent's self-report with it), so this
    reads reproduction status, not a claim about it."""
    from pi_agent.free_director import _integration_context
    from pi_agent.study import study_findings

    verified, unverified, phases = [], [], []
    for entry in study_findings(study):
        label = entry.get("move_type")
        phases.append({
            "seq": entry.get("seq"),
            "phase": label,
            "run_id": entry.get("run_id"),
            "outcome": entry.get("outcome"),
            "why_this_phase": entry.get("finding"),
        })
        for f in entry.get("results", []) or []:
            if not isinstance(f, dict):
                continue
            row = {"label": f.get("label"), "value": f.get("value"),
                   "from_phase": entry.get("seq")}
            (verified if f.get("verified") else unverified).append(row)

    files = _integration_context(study)["files"]
    return {
        "goal": study.goal,
        "verified_findings": verified[:MAX_FINDINGS],
        "unverified_findings": unverified[:MAX_FINDINGS],
        "arc": phases[:MAX_PHASES],
        "reusable_artifacts": [{"name": f.get("name")} for f in files],
        "counts": {"verified": len(verified), "unverified": len(unverified),
                   "phases": len(phases)},
    }


def write_study_paper(study: Any, *, call=None) -> dict:
    """Write studies/<id>/paper.md from the study's whole arc.

    Returns {paper_path, human_must_validate, figures} on success, else {error}.
    `call` is injected in tests. Never raises."""
    call = call or call_stage_model
    try:
        evidence = collect_study_evidence(study)
    except Exception as e:  # noqa: BLE001 — a paper is a deliverable, not a gate
        return {"error": f"could not read the study arc: {type(e).__name__}: {e}"}

    if not evidence["verified_findings"]:
        # Honest refusal, not an empty paper. A study whose numbers did not
        # reproduce has nothing to report as a result, and saying so is the
        # truthful outcome — writing it up anyway would dress narration as
        # findings, which is the exact failure the wall exists to prevent.
        return {"error": "no verified findings in this study — nothing reproduced, "
                         "so there is nothing to write up as a result"}

    from pi_agent.study import study_scratch_dir
    scratch = study_scratch_dir(study)
    try:
        scratch.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not open a scratch dir: {type(e).__name__}: {e}"}

    with agent_workspace(scratch):
        try:
            data, _timing = call(
                PAPER_STAGE_NAME, SYSTEM_PROMPT, evidence, SCHEMA,
                model=PAPER_MODEL, extra_validator=_validate, capabilities=FULL)
        except Exception as e:  # noqa: BLE001
            return {"error": f"paper write-up failed: {type(e).__name__}: {e}"}

    paper_file = data.get("paper_file") or "paper.md"
    src = Path(scratch) / paper_file
    if not src.is_file():
        return {"error": f"agent reported {paper_file!r} but no such file was written"}

    dest = study.dir / "paper.md"
    try:
        text = src.read_text()
        # CITATION CHECK: the prompt forbids presenting an unverified finding as
        # established, but a prompt is not a guarantee. Any line that asserts
        # reproduction while citing a value the wall rejected gets a deterministic,
        # Python-written correction appended — the paper is never silently wrong.
        flagged = unsupported_reproduction_claims(
            text,
            [f.get("value") for f in evidence["verified_findings"]],
            [f.get("value") for f in evidence["unverified_findings"]],
        )
        if flagged:
            text = text + _correction_block(flagged)
        dest.write_text(text)
        figures = _copy_figures(data.get("figures") or [], scratch, study.dir)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not save the paper: {type(e).__name__}: {e}"}

    return {"paper_path": str(dest),
            "human_must_validate": data.get("human_must_validate") or [],
            "figures": figures,
            "unsupported_claims": flagged}


# --------------------------------------------------------------------------
# Citation check (found live, study-20260725T073215Z). The verified/unverified
# split is made in Python and the prompt forbids presenting an unverified finding
# as established — but nothing ENFORCED it, and a real run wrote an unverified
# ratio into Results labelled "independently reproduced" (the wall had rejected
# it: original 128.0, reproduced 127.49004). Prompts are not guarantees. This is
# the deterministic, no-model check that makes the guarantee real.
# --------------------------------------------------------------------------

# A claim of reproduction, as the paper is instructed to write it. Deliberately
# narrow: we only police sentences that ASSERT reproduction, because those are the
# ones a reader trusts. Prose that merely mentions a number is not a claim.
_REPRODUCED_MARKERS = ("independently reproduced", "reproduced by", "was reproduced")

# Phrases that DISCLAIM reproduction. A Limitations line honestly saying a number
# did not reproduce contains a marker substring ("reproduced by") but is the
# opposite of an over-claim — flagging it would punish exactly the honesty the
# paper is asked for. Checked before the markers.
_DISCLAIMERS = ("unverified", "not reproduce", "did not", "could not", "failed to",
                "does not reproduce", "no artifact")


def _numbers_in(text: str) -> list:
    """Every numeric literal in a line, as floats. Tolerant: bolding, units, and
    thousands separators are stripped. Never raises."""
    import re
    out = []
    for tok in re.findall(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?", text or ""):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def _matches_a_verified_value(value: float, verified: list, rel_tol: float = 1e-3) -> bool:
    """True when `value` is one of the wall's verified numbers. The tolerance is
    loose on purpose — a paper legitimately rounds (16.87314 -> 16.8731), and this
    check exists to catch a number the wall REJECTED being passed off as
    reproduced, not to police significant figures."""
    for v in verified:
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v == value:
            return True
        denom = max(abs(v), abs(value), 1e-12)
        if abs(v - value) / denom <= rel_tol:
            return True
    return False


def unsupported_reproduction_claims(paper_text: str, verified_values: list,
                                    unverified_values: list) -> list:
    """Lines that assert reproduction while citing a number the wall did NOT
    verify. Pure, deterministic, never raises.

    A line is flagged when it (a) asserts reproduction and (b) carries a number
    matching something the wall explicitly REJECTED. Requiring (b) keeps the check
    specific — an unmatched number might be a count, a dimension, or a year, and
    flagging those would drown the real finding in noise.

    DELIBERATELY NOT a third condition of "and carries no verified number". That
    exemption was tried and is unsound: the live failure line was "...at D=64 ...
    128x — independently reproduced", where 64 is a DIMENSION LABEL that happens to
    equal a verified ratio, so the exemption would have excused the exact defect
    this check exists to catch. Erring toward flagging is the right bias — a false
    positive appends a visible note whose literal claim (this value was not
    verified) is still true, while a false negative leaves a fabricated
    reproduction claim standing."""
    flagged = []
    for line in (paper_text or "").splitlines():
        low = line.lower()
        if any(d in low for d in _DISCLAIMERS):
            continue
        if not any(m in low for m in _REPRODUCED_MARKERS):
            continue
        rejected = [
            n for n in _numbers_in(line)
            # rejected somewhere AND verified nowhere. A study can measure the same
            # quantity in two phases and have it reproduce in one but not the
            # other (seen live: a converged mass verified at phase 4, unverified at
            # phase 3). Citing the value that DID reproduce is legitimate, so a
            # number vouched for anywhere in the arc is not an over-claim.
            if _matches_a_verified_value(n, unverified_values)
            and not _matches_a_verified_value(n, verified_values)
        ]
        if rejected:
            flagged.append({"line": line.strip()[:300], "values": rejected})
    return flagged


_CORRECTION_HEADER = "\n\n## Correction — claims the verification wall did not support\n\n"


def _correction_block(flagged: list) -> str:
    """The machine-written notice appended to a paper that over-claimed. Written by
    Python, not a model: a correction about a model's over-claim must not itself be
    model-authored."""
    lines = [_CORRECTION_HEADER,
             "The following line(s) assert independent reproduction while citing a "
             "value the verification wall REJECTED. This block was appended "
             "automatically by a deterministic check; the claims above it are NOT "
             "supported and must not be relied on.\n\n"]
    for f in flagged:
        vals = ", ".join(str(v) for v in f["values"])
        lines.append(f"- Unsupported value(s) {vals} in: \"{f['line']}\"\n")
    return "".join(lines)


def _copy_figures(names: list, scratch: Path, dest_dir: Path) -> list:
    """Copy the figures the agent generated up beside the paper, so paper.md's
    relative ![](fig.png) links resolve where a reader opens it. A named figure
    that was not actually written is skipped rather than faked."""
    out = []
    for name in names:
        if not isinstance(name, str) or "/" in name or name.startswith("."):
            continue  # a figure is a bare filename beside the paper, nothing else
        src = Path(scratch) / name
        if src.is_file():
            shutil.copyfile(src, Path(dest_dir) / name)
            out.append(name)
    return out


def write_study_paper_by_id(study_id: str, *, studies_root: Optional[Path] = None,
                            call=None) -> dict:
    """Convenience entry: load the study by id and write its paper. Never raises."""
    from pi_agent.study import STUDIES_ROOT, load_study
    try:
        study = load_study(study_id, studies_root=studies_root or STUDIES_ROOT)
    except Exception as e:  # noqa: BLE001
        return {"error": f"no such study {study_id!r}: {type(e).__name__}: {e}"}
    return write_study_paper(study, call=call)
