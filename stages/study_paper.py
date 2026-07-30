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

TWO DOCUMENTS, AND A SHAPE THAT IS ENFORCED. It writes paper.md (short: the
opening "Bottom line" block, then a readable skeleton) and report.md (the
supplement: the arc, the full specification, per-phase detail, the artifact
inventory). The either/or that produced a design document with no abstract
anywhere is gone — both goal types now get both files. And the shape is checked
by harness/study_lint.py INSIDE the writer's own bounded re-ask loop, because the
prompt has always asked for structure and a real study came back in 15 sections
with no table of contents and no abstract. Asking is not enforcement.

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

from harness.study_lint import (DOCUMENT_KINDS, infer_document_kind,
                                lint_errors_as_text, lint_study_paper,
                                lint_study_supplement)
from model_call import FULL, agent_workspace, call_stage_model
from models import model_for

PAPER_MODEL = model_for("heavy")
PAPER_STAGE_NAME = "study_paper"

# Bounds on what travels into the prompt, so a long study cannot grow it without
# limit. The study's own arc stays complete on disk either way.
MAX_FINDINGS = 60
MAX_PHASES = 40

SYSTEM_PROMPT = """You are writing up a COMPLETED multi-phase investigation you did not run. A director held one GOAL and drove an arc of phases — some of them experiments, some delegated sub-investigations, some integration checks that tested whether the parts compose. You are given what that arc produced.

You are given VERIFIED FINDINGS — numbers an independent, no-model re-run has already reproduced. These, and ONLY these, are trustworthy results. You are also given UNVERIFIED findings (things that did not reproduce or could not be checked), the ARC (which phase produced what), and any REUSABLE ARTIFACTS the study built, each as a re-runnable producer.

YOU WRITE TWO FILES, NOT ONE. Your current working directory is a private scratch directory. Write both files there, in Markdown:

  paper.md   — THE SHORT READABLE ONE. A reader gets through it in minutes. It carries the opening block below, then every finding stated clearly and positioned clearly against what was already known. Nothing else.
  report.md  — THE SUPPLEMENT. As long as it needs to be: the arc narrative phase by phase, the FULL specification, the per-phase detail, the artifact inventory, the working, the dead ends. Everything that would bloat paper.md lives here instead of being cut. Nothing is lost — it moves.

paper.md must link to report.md near the top, by that bare filename, so a reader who wants the detail knows where it went.

=== THE OPENING BLOCK — MANDATORY, WHATEVER THE GOAL TYPE ===

paper.md OPENS with this section, before anything else, exactly this heading and exactly these four bold labels, in this order:

## Bottom line

**What was accomplished** — the result, in plain language, first. One short paragraph. Not what you set out to do, not what the document contains: what is now true that was not true before.

**What it is worth** — the impact, quantified, in units a reader of this field actually cares about (dollars, tonnes, hours, percent, watts, lives, inches of material). If the honest answer is a range or an order of magnitude, say that. If nothing was quantified, say that plainly rather than reaching for a number.

**What you can do with it now** — the CONCRETE entry point. Name the file to open or the command to type, in backticks. Not "the work is reproducible" — `python3 evidence/verify_findings.py`, or `deliverable/README.md`, or the artifact's own filename. A reader must be able to act within a minute of reading this line.

**What is not established** — one line. The boundary, up front, so nobody has to hunt for it.

Keep the whole block to one screen. This is not decoration: a reader must learn what was accomplished, what it is worth, what to do next and where the boundary is WITHOUT SEARCHING, and that is what this block is for.

LEADING WITH THE ACCOMPLISHMENT MUST NEVER BECOME LEADING WITH A CLAIM THE WALL DID NOT VERIFY. If the honest headline is "the incumbent is convicted; the successor is drafted, not certified", then THAT is the headline, stated plainly and up front. An unmarked over-claim is disqualifying. An honest negative or partial result, stated first and clearly, is a good opening block.

=== THE REST OF paper.md ===

After the opening block, use the skeleton that fits the goal — you declare which you used in your reply:
- document_kind "research" (the goal asked a research question, or asked what something achieves): Abstract, Introduction, Methods, Results, Conclusions, Limitations.
- document_kind "design" (the goal asked you to DESIGN or BUILD something): Abstract, What was built, How it performs, How to build it, Limitations. Lead with the THING — what it is, its parameters, what it does — not with the investigation that produced it.

Both kinds get an Abstract. A goal that said "build the replacement end to end" is still a piece of work whose result a reader must be able to grasp in a paragraph.

NAVIGATION. Put a "## Contents" table of contents in ANY document that grows past the standard skeleton — more than eight sections — and that will usually mean report.md. A long document with no way to navigate it is a document nobody reads to the end. Put it IMMEDIATELY AFTER the opening block, never before: nothing precedes the result, not even a table of contents.

STATE EVERY NEW FINDING CLEARLY AND POSITION IT AGAINST WHAT WAS ALREADY KNOWN. A number with no baseline is not a finding. Say what the prior state of knowledge or practice was, and what this changes.

=== CONSTRAINTS THAT MAKE THIS TRUSTWORTHY — THEY APPLY TO BOTH FILES ===

Report ONLY the verified numbers you were given as results, each noted as independently reproduced. Results carries independently reproduced numbers and nothing else; every unverified finding goes to Limitations and is NEVER presented as established.

MARK THE PROVENANCE OF EVERY SPECIFIED VALUE. A specification is dangerous precisely because it reads as authoritative: an airfoil choice, a dihedral angle, a spar dimension all look as solid as a number that was independently reproduced, and they are not. So when you present a design, tag each element as one of:
- VERIFIED — a number in the verified list, independently reproduced by the no-model re-run;
- COMPUTED — derived during the investigation but not independently re-run;
- JUDGEMENT — chosen by the investigation with nothing checking it.
A table with a provenance column is usually the clearest way. Never present a JUDGEMENT element as though it were established.

THE ARTIFACTS ARE PART OF THE DELIVERABLE. You are given the reusable artifacts this study produced, each as a re-runnable producer. If the study built a thing, that thing belongs in the write-up: regenerate it (run the producer), describe it fully in report.md, and DRAW it where it has a shape — a planform, a schematic, a layout, a structure. A reader should be able to see what was made, not only the numbers measured about it.

FIGURES: where a figure genuinely clarifies a result, generate it — run python with matplotlib, save a .png beside paper.md, and embed it with ![caption](figure.png). Build figures only from the numbers you were given. Do not fabricate data to make a figure look fuller.

Do NOT invent numbers.

END paper.md with a section "## What a human must still validate": one bullet per claim or assumption a human should check before trusting this. Every unverified finding belongs here, plus any modelling assumption the investigation relied on, plus anything the arc asserted but never measured.

Return ONLY JSON: {"paper_file": "paper.md", "supplement_file": "report.md", "document_kind": "research"|"design", "figures": ["<png files you generated>"], "human_must_validate": ["<bullet>", ...]} — no other fields."""

SCHEMA = {"required": ["paper_file", "supplement_file", "document_kind",
                       "human_must_validate"]}


def _validate(data: dict) -> list:
    errs = []
    if not str(data.get("paper_file") or "").strip():
        errs.append("'paper_file' must name the short primary markdown file you wrote.")
    if not str(data.get("supplement_file") or "").strip():
        errs.append("'supplement_file' must name the supplement markdown file you "
                    "wrote (the long one carrying the arc, the full specification, "
                    "the per-phase detail and the artifact inventory).")
    if data.get("document_kind") not in DOCUMENT_KINDS:
        errs.append("'document_kind' must be exactly one of "
                    f"{' | '.join(DOCUMENT_KINDS)} — which skeleton paper.md uses.")
    if not isinstance(data.get("human_must_validate"), list):
        errs.append("'human_must_validate' must be a list (may be empty).")
    return errs


def _structural_validator(scratch: Path):
    """The shape lint, wired into the writer's OWN bounded re-ask loop.

    This is the load-bearing difference between asking for structure and getting
    it. The prompt above has always asked; a real study came back 9,296 words in
    15 sections with no table of contents, no abstract, and an opening section
    that told a reader nothing about what to DO next. So the lint runs on the
    files as actually written, inside call_stage_model's correction loop, and a
    paper missing its opening block is sent back before it is ever saved.

    Returns a callable(parsed_reply) -> plain-language errors, closing over the
    scratch dir because the lint reads FILES, not the JSON reply."""
    def check(data: dict) -> list:
        errs = _validate(data)
        if errs:
            return errs  # shape of the reply first; the files are checked next
        root = Path(scratch).resolve()
        out: list = []
        for key, linter, what in (
                ("paper_file", lambda t: lint_study_paper(t, data["document_kind"]),
                 "paper"),
                ("supplement_file", lint_study_supplement, "supplement")):
            name = str(data.get(key))
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                out.append(f"'{key}' names {name!r}, but no such file exists in "
                           "your working directory — write it before replying.")
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError) as e:
                out.append(f"{name} could not be read back: {e}")
                continue
            out.extend(f"{what} ({name}): {msg}"
                       for msg in lint_errors_as_text(linter(text)))
        return out
    return check


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
        # The PRODUCERS travel, not just the names. The writer was previously
        # given a bare filename list, so it could mention that a design existed
        # but never open it, describe it, or draw it — which is a large part of
        # why a design study came out reading as an analysis. With the producer
        # it can regenerate the artifact in its scratch dir and work from the
        # real thing.
        "reusable_artifacts": [
            {"name": f.get("name"), "producer": f.get("producer")} for f in files
        ],
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
                model=PAPER_MODEL, extra_validator=_structural_validator(scratch),
                capabilities=FULL)
        except Exception as e:  # noqa: BLE001
            # SALVAGE. The structural lint runs inside the re-ask loop, so a
            # writer that will not produce an opening block exhausts the loop and
            # raises — and the paper it DID write is sitting in the scratch dir.
            # Throwing that away would mean a study loses its whole write-up over
            # a missing table of contents, which is a worse outcome than an
            # imperfectly shaped paper carrying a visible, Python-written notice
            # of exactly what it is missing. Enforcement, not destruction.
            salvaged = _salvage(scratch, study, f"{type(e).__name__}: {e}")
            if salvaged:
                return salvaged
            return {"error": f"paper write-up failed: {type(e).__name__}: {e}"}

    paper_file = data.get("paper_file") or "paper.md"
    # CONTAINED, because paper_file is MODEL-AUTHORED and pathlib lets an
    # absolute right operand win: "/etc/passwd" or "../../.env" escaped the
    # scratch/workspace root and was COPIED INTO THE DELIVERABLE. Figures already
    # get a filename guard; this did not. A bare filename is all a paper needs.
    _root = Path(scratch).resolve()
    src = (_root / paper_file).resolve()
    if not src.is_relative_to(_root):
        return {"error": f"agent reported paper_file {paper_file!r}, which "
                          "resolves outside its own working directory; refusing "
                          "to copy it into the deliverable"}
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
        supplement = _copy_supplement(data.get("supplement_file"), _root, study.dir)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not save the paper: {type(e).__name__}: {e}"}

    # Which skeleton the writer declared, recorded beside the paper so a later
    # lint holds it to the same standard it was written against instead of
    # guessing from the headings.
    try:
        (study.dir / "paper_meta.json").write_text(json.dumps(
            {"document_kind": data.get("document_kind"),
             "supplement": "report.md" if supplement else None,
             "figures": figures}, indent=2))
    except OSError:
        pass

    return {"paper_path": str(dest),
            "supplement_path": supplement,
            "document_kind": data.get("document_kind"),
            "human_must_validate": data.get("human_must_validate") or [],
            "figures": figures,
            "unsupported_claims": flagged}


def _copy_supplement(name: Any, scratch_root: Path, dest_dir: Path):
    """Copy the supplement up beside the paper as report.md. Contained exactly
    like the paper is — the filename is model-authored. Returns the destination
    path, or None when the file is absent (the lint has already objected; a
    missing supplement must not also cost the reader the paper)."""
    if not isinstance(name, str) or not name.strip():
        return None
    src = (Path(scratch_root) / name).resolve()
    if not src.is_relative_to(Path(scratch_root).resolve()) or not src.is_file():
        return None
    dest = Path(dest_dir) / "report.md"
    shutil.copyfile(src, dest)
    return str(dest)


def _salvage(scratch: Path, study: Any, reason: str) -> Optional[dict]:
    """Rescue a paper the writer wrote but could not get past the shape lint.

    The notice is written by PYTHON, not by a model: a statement that a document
    failed its own structural check must not be authored by the writer that
    failed it. Returns None when there is nothing to rescue."""
    src = Path(scratch) / "paper.md"
    if not src.is_file():
        return None
    try:
        text = src.read_text()
        # The declared kind is unavailable (the reply never validated), so the
        # notice is written against whichever skeleton the draft is closest to —
        # holding it to the other one would list misses that are not real.
        failures = (lint_study_paper(text, infer_document_kind(text))
                    if text.strip() else [])
        notice = ["\n\n---\n\n## Structural check — this document does not meet the "
                  "deliverable standard\n\n",
                  "The write-up agent could not produce a conforming document "
                  f"within its correction budget ({reason}). This paper is saved "
                  "anyway rather than discarded, but a reader should know it is "
                  "missing the following, and that the opening block a reader "
                  "normally relies on may not be present:\n\n"]
        for f in failures:
            notice.append(f"- [{f['code']}] {f['message']}\n")
        (study.dir / "paper.md").write_text(text + "".join(notice))
        figures = _copy_figures(
            [p.name for p in Path(scratch).glob("*.png")], scratch, study.dir)
        supplement = _copy_supplement("report.md", Path(scratch), study.dir)
    except Exception:  # noqa: BLE001
        return None
    return {"paper_path": str(study.dir / "paper.md"),
            "supplement_path": supplement,
            "document_kind": None,
            "human_must_validate": [],
            "figures": figures,
            "unsupported_claims": [],
            "structural_failures": [f["code"] for f in failures],
            "salvaged": True}


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
