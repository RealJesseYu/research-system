"""build_critic.py — "could I actually build this today?", asked before a human does.

WHY THIS EXISTS, AND WHY IT IS NOT THE REFEREE. stages/referee.py reviews the
paper's WORDS against its ARTIFACTS: does the code do what the prose says, is the
baseline really the stated baseline, does a sentence claim more than its number
established. That is a correctness lens and it works.

This is a different lens, and it was found the way most good checks are — a human
pasted a finished study into a fresh chat and asked "can I build this today?".
The reply named six things the whole apparatus had missed, none of which were
correctness failures: no structural check, no pitch axis, no cut files, a
performance figure that was a prediction rather than a promise, a handling
hazard, and an autopilot that only closed one loop. Every one was true. Every one
was invisible to a verifier, because nothing was WRONG — things were ABSENT.

So this asks the practitioner's question. Not "is this right" but "if I took this
and tried to use it tomorrow, what stops me, what bites me, and what do I still
have to work out myself?"

IT RENDERS NO VERDICT AND GATES NOTHING. Like the referee, findings are filed,
never enforced — but unlike the referee they are ROUTED BACK TO THE DIRECTOR for
a response, because most of them are answerable: the director can say "that axis
is genuinely out of scope", or "that is a real gap, here is what it would take",
or spend remaining budget closing it. The critique and the response both land in
the record, so a reader sees the challenge AND what the investigation said to it.

MODEL. Runs on its own tier (`critic`, default the `heavy` model) so it can be
pointed at a different model from the one that did the work — an outside reader
is worth more than the author's own second opinion. Kill switch: BUILD_CRITIC=0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for

CRITIC_MODEL = model_for("critic")
CRITIC_STAGE = "build_critic"
RESPONSE_STAGE = "director_response"

# Bounded so one critique cannot flood the paper or the next decision.
MAX_FINDINGS = 10

SYSTEM_PROMPT = """You are an experienced practitioner in whatever field this work belongs to, reading a finished piece of work someone is about to hand over. You have the deliverable, the evidence behind it, and the workspace files it produced.

Ask ONE question and answer it honestly: **if I took this and tried to actually use it — build it, deploy it, run it, act on it — starting tomorrow, what would happen?**

You are NOT checking whether the numbers are right; an independent re-run already did that, and a separate reviewer already checked the prose against the code. You are looking for what is MISSING, which no verifier can see because nothing is wrong — things are simply absent:
- an axis nobody checked that determines whether the thing works at all (loads and margins, stability and trim, thermal or power or timing budgets, the interfaces between parts);
- a step you would have to work out yourself before you could start — drawings you cannot cut from, a component nobody sized, a calibration nobody specified;
- a number presented as a result that is really a prediction resting on an assumption nobody validated;
- a hazard or failure mode a practitioner would want warned about;
- a scope boundary that is defensible in the abstract but leaves the deliverable unusable in practice (a controller that closes one loop when flying needs three).

Be concrete and be fair. Name the specific thing, say why it matters in practice, and say what it would take to close it. If something is genuinely fine, do not manufacture a complaint — a short honest list beats a long padded one. Where the work already discloses a limitation honestly, say so and do not re-file it as a finding.

Reply ONLY with JSON: {"verdict": "<one or two sentences: could a competent person use this tomorrow, and what is the single biggest thing standing in the way>", "usable_today": <true|false>, "findings": [{"issue": "<the specific gap>", "why_it_matters": "<what actually goes wrong in practice>", "what_would_close_it": "<the concrete step>", "severity": "high"|"medium"|"low"}]} — no other fields."""

RESPONSE_PROMPT = """You are the principal investigator who directed the investigation being critiqued. An outside practitioner has read your finished work and asked whether it could actually be used, then filed the gaps they found.

Answer them as a researcher, not as a defendant. For each finding, say plainly which it is:
- ACCEPTED — a real gap. Say what it would take to close, and whether it was a deliberate scope choice or an oversight. An oversight honestly named costs you nothing; one dressed up as a scope decision costs you the reader's trust.
- OUT OF SCOPE — genuinely outside what was asked. Say what the boundary was and why it was reasonable, and be honest about whether the deliverable is still usable without it.
- ALREADY ADDRESSED — the work already discloses or handles this. Point to where.

Then say what you would do next if the investigation continued, in priority order. This response is recorded beside the critique so a reader sees both.

Reply ONLY with JSON: {"responses": [{"issue": "<the finding, restated briefly>", "disposition": "accepted"|"out_of_scope"|"already_addressed", "reasoning": "<one to three sentences>"}], "next_priorities": ["<what you would do next, most important first>"], "overall": "<one or two sentences: what this critique changes about how the work should be read>"} — no other fields."""


def _enabled() -> bool:
    return os.environ.get("BUILD_CRITIC", "").strip() != "0"


def _validate_critique(data: dict) -> list:
    errs = []
    if not str(data.get("verdict") or "").strip():
        errs.append("'verdict' must be a non-empty string.")
    if not isinstance(data.get("usable_today"), bool):
        errs.append("'usable_today' must be a boolean.")
    findings = data.get("findings")
    if not isinstance(findings, list):
        errs.append("'findings' must be a list (may be empty).")
        return errs
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errs.append(f"findings[{i}] must be an object.")
            continue
        for key in ("issue", "why_it_matters", "what_would_close_it"):
            if not str(f.get(key) or "").strip():
                errs.append(f"findings[{i}] needs a non-empty {key!r}.")
        if f.get("severity") not in ("high", "medium", "low"):
            errs.append(f"findings[{i}] severity must be high, medium or low.")
    return errs


def _validate_response(data: dict) -> list:
    errs = []
    responses = data.get("responses")
    if not isinstance(responses, list):
        errs.append("'responses' must be a list.")
        return errs
    for i, r in enumerate(responses):
        if not isinstance(r, dict):
            errs.append(f"responses[{i}] must be an object.")
            continue
        if r.get("disposition") not in ("accepted", "out_of_scope", "already_addressed"):
            errs.append(
                f"responses[{i}] disposition must be accepted, out_of_scope or "
                "already_addressed.")
        if not str(r.get("reasoning") or "").strip():
            errs.append(f"responses[{i}] needs a non-empty 'reasoning'.")
    if not isinstance(data.get("next_priorities"), list):
        errs.append("'next_priorities' must be a list (may be empty).")
    return errs


def _paper_text(study_dir: Path) -> str:
    try:
        return (study_dir / "paper.md").read_text()
    except OSError:
        return ""


def critique_study(study: Any, *, call=None) -> dict:
    """Read the finished study as a practitioner would and file what is missing.

    Returns {verdict, usable_today, findings, response} on success, else {error}.
    Never raises: a critique is a service to the reader, not a gate."""
    if not _enabled():
        return {"error": "build critic disabled (BUILD_CRITIC=0)"}
    call = call or call_stage_model

    paper = _paper_text(study.dir)
    if not paper.strip():
        return {"error": "no paper.md to critique"}

    try:
        from stages.study_paper import collect_study_evidence
        evidence = collect_study_evidence(study)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not read the study: {type(e).__name__}: {e}"}

    stage_input = {
        "goal": study.goal,
        "deliverable": paper[:60000],
        "verified_findings": evidence.get("verified_findings"),
        "unverified_findings": evidence.get("unverified_findings"),
        "artifacts_produced": evidence.get("reusable_artifacts"),
        "workspace_note": "the study's workspaces hold the code and files behind "
                          "this; read them if a gap turns on what was actually built",
    }

    from pi_agent.study import study_scratch_dir
    try:
        scratch = study_scratch_dir(study)
        scratch.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        scratch = None

    with agent_workspace(scratch):
        try:
            data, _t = call(CRITIC_STAGE, SYSTEM_PROMPT, stage_input,
                            {"required": ["verdict", "usable_today", "findings"]},
                            model=CRITIC_MODEL, extra_validator=_validate_critique,
                            capabilities=FULL)
        except Exception as e:  # noqa: BLE001
            return {"error": f"critique failed: {type(e).__name__}: {e}"}

    out = {
        "verdict": data.get("verdict"),
        "usable_today": bool(data.get("usable_today")),
        "findings": (data.get("findings") or [])[:MAX_FINDINGS],
        "model": CRITIC_MODEL,
    }
    try:
        (study.dir / "build_critique.json").write_text(json.dumps(out, indent=2))
    except OSError:
        pass
    return out


def director_response(study: Any, critique: dict, *, call=None) -> dict:
    """Give the critique back to the director and record what it says. One round,
    not a loop: the point is that the challenge is answered on the record, not
    that the work is rewritten until the critic is satisfied. Never raises."""
    call = call or call_stage_model
    findings = critique.get("findings") or []
    if not findings:
        return {"responses": [], "next_priorities": [],
                "overall": "no findings to answer"}

    stage_input = {
        "goal": study.goal,
        "critic_verdict": critique.get("verdict"),
        "critic_says_usable_today": critique.get("usable_today"),
        "findings": findings,
    }
    from pi_agent.study import study_scratch_dir
    try:
        scratch = study_scratch_dir(study)
    except Exception:  # noqa: BLE001
        scratch = None
    with agent_workspace(scratch):
        try:
            data, _t = call(RESPONSE_STAGE, RESPONSE_PROMPT, stage_input,
                            {"required": ["responses", "next_priorities"]},
                            model=model_for("heavy"),
                            extra_validator=_validate_response, capabilities=FULL)
        except Exception as e:  # noqa: BLE001
            return {"error": f"director response failed: {type(e).__name__}: {e}"}
    return data


def _block(critique: dict, response: dict) -> str:
    """The section appended to paper.md. Written by Python, not by a model: a
    record of a challenge and its answer must not be authored by either party."""
    lines = ["\n\n---\n\n## Build critique — could this be used today?\n\n",
             f"An outside practitioner review ({critique.get('model')}) read this "
             "deliverable and asked whether a competent person could actually use "
             "it. Its findings and the investigation's response are both recorded "
             "here, unedited; neither party wrote this section.\n\n",
             f"**Verdict:** {critique.get('verdict')}\n\n",
             f"**Usable today:** {'yes' if critique.get('usable_today') else 'not without further work'}\n\n"]
    by_issue = {r.get("issue", ""): r for r in (response.get("responses") or [])}
    for i, f in enumerate(critique.get("findings") or [], start=1):
        lines.append(f"**{i}. {f.get('issue')}** *({f.get('severity')})*\n\n")
        lines.append(f"- Why it matters: {f.get('why_it_matters')}\n")
        lines.append(f"- What would close it: {f.get('what_would_close_it')}\n")
        match = next((r for k, r in by_issue.items()
                      if k and (k[:40].lower() in str(f.get('issue')).lower()
                                or str(f.get('issue'))[:40].lower() in k.lower())), None)
        if match:
            lines.append(f"- **Investigation's response — {match.get('disposition')}:** "
                         f"{match.get('reasoning')}\n")
        lines.append("\n")
    if response.get("next_priorities"):
        lines.append("**What the investigation would do next:**\n\n")
        for pri in response["next_priorities"]:
            lines.append(f"- {pri}\n")
        lines.append("\n")
    if response.get("overall"):
        lines.append(f"**How to read this work in light of the critique:** "
                     f"{response['overall']}\n")
    return "".join(lines)


def critique_and_respond(study_id: str, *, studies_root: Optional[Path] = None,
                         call=None) -> dict:
    """The whole pass: critique, director response, both appended to the paper and
    saved beside it. Never raises."""
    from pi_agent.study import STUDIES_ROOT, load_study
    try:
        study = load_study(study_id, studies_root=studies_root or STUDIES_ROOT)
    except Exception as e:  # noqa: BLE001
        return {"error": f"no such study {study_id!r}: {type(e).__name__}: {e}"}

    critique = critique_study(study, call=call)
    if critique.get("error"):
        return critique
    response = director_response(study, critique, call=call)

    try:
        paper = study.dir / "paper.md"
        if paper.is_file():
            paper.write_text(paper.read_text() + _block(critique, response))
        (study.dir / "build_critique.json").write_text(
            json.dumps({"critique": critique, "response": response}, indent=2))
    except OSError:
        pass
    return {"critique": critique, "response": response,
            "findings": len(critique.get("findings") or [])}
