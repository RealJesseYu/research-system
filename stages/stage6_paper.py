"""
stage6_paper.py — real Paper stage (Step 22): per-section Haiku drafting
with ONE self-reflection pass each, a SIDECAR-FIRST validation handoff,
and an in-process lint with bounded error-feedback regeneration. The
frozen signature run(baton: Baton) -> Baton is unchanged.

Inputs are EXACTLY three (ruled): the baton's stage-5 object (thought +
iterate_decision), journal_recent_by_kind("learned_summary", limit=3),
and the run's stage-3 verdict read from disk
(runs/<run_id>/stage3/verdict.json) — plus references obtained through
the ONE seam function gather_references (offline mode reads
tests/fixtures/refs_canned.json; live mode is best-effort scholarly
retrieval in the reflection_reviews gather_review_refs style, every
source best-effort — paper references are context, not novelty
grounding, so no source is hard-required here). No other payload field,
file, or transcript may enter any model input.

SIDECAR-FIRST: runs/<run_id>/stage6/paper_validation.json
{fidelity_class, validation_items} is drafted and WRITTEN before any
paper prose. fidelity_class is set by CODE from the verdict label — the
model never chooses it; the model drafts only the item text, from the
stage-3 rationale + stage-5 justification, and the class-conditional
item shape (trust -> exactly one none_required item with a reason;
refine -> >=1 item naming the QoI/claim needing downstream validation;
defer -> >=1 concrete test spec {substrate, conditions, measurement})
is enforced in Python by harness.paper_lint.validate_validation_items —
the SAME function the lint runs, so drafter and lint can never disagree
— inside call_stage_model's bounded re-ask loop. The "What Humans Must
Validate" section is generated FROM the written sidecar, never
independently.

The deliverable is markdown (ruled; TeX queued post-deadline):
runs/<run_id>/stage6/paper.md, assembled by code with code-authored
"## <section>" headings (the model writes bodies only, plus the "# "
title line in Title and Abstract). After assembly the lint
(harness/paper_lint.py — pure, deterministic, zero model calls) runs
in-process; on failure the machine-readable errors are fed back verbatim
and ONLY the failing pieces are regenerated (a sidecar failure also
regenerates What Humans Must Validate, since that section derives from
the sidecar), max 2 regeneration rounds; still failing -> what exists
stays on disk and the stage raises (honest crash, evidence kept).

Every model call is one bounded Haiku call through call_stage_model on
the explicit ruled pin STAGE6_MODEL, with per-call transcripts, durable
STAGE_MODEL_CALL lines, and an ack_run_id echo check.
"""

from __future__ import annotations

import re
import json
from pathlib import Path

from baton import Baton
from harness.paper_lint import (
    REQUIRED_HEADING,
    VERDICT_LABELS,
    lint_paper,
    validate_validation_items,
)
from memory.journal import journal_recent_by_kind
from stages.desk_review import MAX_DESK_REWRITES, desk_review
from model_call import call_stage_model, log_stage_call

STAGE6_MODEL = "claude-sonnet-4-6"  # explicit ruled pin (Step 22)

# The reference seam's mode: "live" (best-effort scholarly retrieval) or
# "offline" (the canned fixture). Tests and the smoke driver set this to
# "offline"; this worktree carries no .env by design.
REFS_MODE = "live"
REFS_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "refs_canned.json"
)
TOP_K_PER_SOURCE = 3

MAX_LINT_REGENERATIONS = 2

SECTION_NAMES = (
    "Title and Abstract",
    "Background",
    "Hypothesis",
    "Experiment Design",
    "Results",
    "Discussion",
    REQUIRED_HEADING,  # "What Humans Must Validate"
    "References",
)

_SECTION_SLUGS = {
    "Title and Abstract": "title_abstract",
    "Background": "background",
    "Hypothesis": "hypothesis",
    "Experiment Design": "experiment_design",
    "Results": "results",
    "Discussion": "discussion",
    REQUIRED_HEADING: "humans_validate",
    "References": "references",
}

_SECTION_GUIDANCE = {
    "Title and Abstract": (
        "Start with a single '# <title>' markdown line naming the finding, "
        "then one abstract paragraph summarizing the hypothesis outcome, the "
        "instrument's fidelity verdict, and the iterate decision."
    ),
    "Background": (
        "Context for the work, drawn from the provided learned_summaries and "
        "references only. Cite references by their ref ids in brackets, e.g. "
        "[R1]. Claim nothing the inputs do not support."
    ),
    "Hypothesis": (
        "State the hypothesis under investigation as far as the thought "
        "object describes it, and what would confirm or refute it."
    ),
    "Experiment Design": (
        "Describe the experiment as far as the thought object describes it. "
        "Do not invent parameters, solvers, or numbers absent from the inputs."
    ),
    "Results": (
        "Report what the thought's assessment says happened, including any "
        "validity concerns. Report no numbers absent from the inputs."
    ),
    "Discussion": (
        "Interpret the outcome: the surprise triage, the justification, what "
        "was learned, and why the iterate decision follows."
    ),
    REQUIRED_HEADING: (
        "Restate the provided validation_sidecar faithfully — one bullet per "
        "validation item, nothing added, nothing dropped. This section is "
        "generated FROM the sidecar; never invent validation work the sidecar "
        "does not carry."
    ),
    "References": (
        "A numbered markdown list of ONLY the references actually cited in "
        "this paper's body: ref id, source, title. A reference that is "
        "provided but not cited anywhere is NOT part of this paper's "
        "references and must be omitted — retrieval returns candidates, not a "
        "bibliography, and listing an uncited or off-topic source is a defect. "
        "If nothing was cited, state that honestly in one line."
    ),
}

SECTION_SCHEMA = {"required": ["ack_run_id", "section_markdown"]}
SIDECAR_SCHEMA = {"required": ["ack_run_id", "validation_items"]}

_SIDECAR_ITEM_RULES = {
    "trust": (
        "exactly ONE item, exactly "
        '{"kind": "none_required", "reason": "<one sentence stating why no '
        'further human validation is required>"}'
    ),
    "refine": (
        "one or more items, each exactly "
        '{"claim": "<the QoI or claim needing downstream validation>"}'
    ),
    "defer": (
        "one or more items, each exactly "
        '{"substrate": "<what instrument/apparatus>", "conditions": "<the '
        'concrete setup and regime>", "measurement": "<what to measure>"} — '
        "a concrete test spec another instrument could run"
    ),
}


def _log(run_id: str, line: str) -> None:
    """Print + append to runs/<run_id>/log.txt when the run dir exists —
    the same derivation and bare-call limitation as model_call's RE-ASK."""
    print(line)
    run_dir = Path("runs") / str(run_id)
    if run_dir.is_dir():
        with open(run_dir / "log.txt", "a") as f:
            f.write(line + "\n")


def _check_ack(data: dict, run_id: str, what: str) -> None:
    if data.get("ack_run_id") != run_id:
        raise RuntimeError(
            f"stage6_paper ({what}): ack_run_id mismatch — got "
            f"{data.get('ack_run_id')!r}, expected {run_id!r}"
        )


def gather_references(query: str, run_id: str) -> list[dict]:
    """The ONE reference-search seam. Offline mode (REFS_MODE == "offline")
    reads the canned fixture at tests/fixtures/refs_canned.json — used by
    all tests and this step's smoke. Live mode is best-effort scholarly
    retrieval (openalex / arxiv / semantic_scholar, the gather_review_refs
    pattern): a RuntimeError from ANY source is logged and retrieval
    proceeds without it — references here are context, not novelty
    grounding, so no source is hard-required. Records come back already
    bounded by their wrappers; each gains a ref id R1..Rn."""
    if REFS_MODE == "offline":
        records = json.loads(REFS_FIXTURE_PATH.read_text())
    else:
        records = _live_reference_search(query, run_id)
    return [{"ref": f"R{n}", **record} for n, record in enumerate(records, start=1)]


def _live_reference_search(query: str, run_id: str) -> list[dict]:
    """Live best-effort retrieval. Imports are lazy so offline mode (tests,
    the smoke, this .env-less worktree) never touches the retrieval stack."""
    import sys

    retrieval_dir = Path(__file__).resolve().parent.parent / "retrieval"
    if str(retrieval_dir) not in sys.path:
        sys.path.insert(0, str(retrieval_dir))
    from scholar_search import (  # noqa: E402
        search_arxiv,
        search_openalex,
        search_semantic_scholar,
    )

    sources = (
        ("openalex", search_openalex),
        ("arxiv", search_arxiv),
        ("semantic_scholar", search_semantic_scholar),
    )
    records: list[dict] = []
    for source_name, search in sources:
        try:
            records.extend(search(query, top_k=TOP_K_PER_SOURCE))
        except RuntimeError as e:
            _log(
                run_id,
                f"STAGE6_REFERENCES {source_name} failed (recorded, "
                f"proceeding): {str(e).splitlines()[0]}",
            )
    return records


def _load_verdict(run_id: str) -> dict:
    """The stage-3 verdict from disk — the sidecar's ground truth."""
    path = Path("runs") / str(run_id) / "stage3" / "verdict.json"
    if not path.is_file():
        raise RuntimeError(
            f"stage6_paper: no stage-3 verdict at {path} — cannot classify "
            "the validation sidecar."
        )
    verdict = json.loads(path.read_text())
    if not isinstance(verdict, dict) or verdict.get("label") not in VERDICT_LABELS:
        got = verdict.get("label") if isinstance(verdict, dict) else verdict
        raise RuntimeError(
            f"stage6_paper: stage-3 verdict label must be one of "
            f"{' | '.join(VERDICT_LABELS)}; got {got!r}."
        )
    return verdict


def _sidecar_prompt(fidelity_class: str) -> str:
    return (
        "You draft the validation sidecar of a research paper produced by an "
        "autonomous research pipeline. The pipeline's fidelity gate classified "
        f"this run's instrument fit as '{fidelity_class}' (that classification "
        "is fixed by code — do not restate or change it). From the given "
        "stage-3 rationale and stage-5 justification ONLY, draft the "
        "validation items a human must act on: for this class, "
        f"{_SIDECAR_ITEM_RULES[fidelity_class]}. Never invent facts, "
        "instruments, or numbers absent from the inputs. Reply ONLY with JSON "
        'of the form {"ack_run_id": "<the run_id you were given>", '
        '"validation_items": [<the items, exactly the shape above>]}.'
    )


def _draft_validation_items(
    run_id: str, fidelity_class: str, verdict: dict, thought: dict,
    lint_feedback: list[str] | None = None,
) -> list:
    """One bounded Haiku call drafting the sidecar's item text; the
    class-conditional shape is enforced by the SHARED validator inside the
    re-ask loop, so nothing malformed can come back."""
    stage_input = {
        "run_id": run_id,
        "task": "validation_sidecar",
        "fidelity_class": fidelity_class,
        "stage3_rationale": verdict["rationale"],
        "stage5_justification": thought["justification"],
    }
    if lint_feedback:
        stage_input["lint_errors_to_fix"] = lint_feedback

    def validator(data: dict) -> list[str]:
        return validate_validation_items(fidelity_class, data.get("validation_items"))

    stage_name = "stage6_paper_sidecar"
    data, timing = call_stage_model(
        stage_name,
        _sidecar_prompt(fidelity_class),
        stage_input,
        SIDECAR_SCHEMA,
        model=STAGE6_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, stage_name)
    log_stage_call(run_id, stage_name, timing)
    return data["validation_items"]


def _draft_prompt(section: str) -> str:
    heading_rule = (
        "Include the '# <title>' line described in the guidance"
        if section == "Title and Abstract"
        else "Do NOT include the section heading itself — the assembler "
        "writes headings in code"
    )
    return (
        "You draft ONE section of a short research paper for an autonomous "
        "research pipeline. Write in markdown, from ONLY the JSON inputs you "
        "are given — never invent citations, numbers, results, or apparatus "
        "absent from the inputs; when the inputs are thin, honest brevity "
        f"beats invention. Section to write: {section}. Guidance: "
        f"{_SECTION_GUIDANCE[section]} {heading_rule}. Reply ONLY with JSON "
        'of the form {"ack_run_id": "<the run_id you were given>", '
        '"section_markdown": "<the section body in markdown>"}.'
    )


def _reflect_prompt(section: str) -> str:
    return (
        "You are re-reading a research-paper section you just drafted "
        f"('{section}') for an autonomous research pipeline. Against the SAME "
        "JSON inputs, critique your draft_section_markdown — unsupported "
        "claims, invented numbers, dropped load-bearing facts, unclear "
        "prose — and reply with the IMPROVED final version (if the draft "
        "already holds up, return it with only minor polish). The guidance "
        f"still applies: {_SECTION_GUIDANCE[section]} Perform the critique "
        "SILENTLY: never write your analysis, findings, or change notes as "
        "output. Your ENTIRE reply must be exactly one JSON object of the "
        'form {"ack_run_id": "<the run_id you were given>", '
        '"section_markdown": "<the final section body in markdown>"} — '
        "no text before it, no text after it."
    )


def _validate_section(data: dict) -> list[str]:
    text = data.get("section_markdown")
    if not isinstance(text, str) or not text.strip():
        return ["section_markdown must be a non-empty markdown string."]
    return []


def _section_inputs(
    run_id: str, section: str, thought: dict, iterate_decision: str,
    verdict: dict, summaries: list, refs: list, sidecar: dict,
) -> dict:
    """Assemble one section's model input from EXACTLY the ruled inputs.
    References go only to the two sections that use them; the sidecar goes
    only to What Humans Must Validate (which derives from it)."""
    stage_input = {
        "run_id": run_id,
        "section": section,
        "thought": thought,
        "iterate_decision": iterate_decision,
        "fidelity_verdict": verdict,
        "learned_summaries": [entry.get("text", "") for entry in summaries],
    }
    if section in ("Background", "References"):
        stage_input["references"] = refs
    if section == REQUIRED_HEADING:
        stage_input["validation_sidecar"] = sidecar
    return stage_input


def _draft_section(
    run_id: str, section: str, base_inputs: dict,
    lint_feedback: list[str] | None = None,
) -> str:
    """Draft one section, then run its ONE self-reflection pass. Two bounded
    Haiku calls; the reflection's output is the section's final text."""
    slug = _SECTION_SLUGS[section]
    draft_inputs = dict(base_inputs)
    if lint_feedback:
        draft_inputs["lint_errors_to_fix"] = lint_feedback

    draft_stage = f"stage6_paper_{slug}_draft"
    data, timing = call_stage_model(
        draft_stage,
        _draft_prompt(section),
        draft_inputs,
        SECTION_SCHEMA,
        model=STAGE6_MODEL,
        extra_validator=_validate_section,
    )
    _check_ack(data, run_id, draft_stage)
    log_stage_call(run_id, draft_stage, timing)

    reflect_inputs = dict(draft_inputs)
    reflect_inputs["draft_section_markdown"] = data["section_markdown"]
    reflect_stage = f"stage6_paper_{slug}_reflect"
    data, timing = call_stage_model(
        reflect_stage,
        _reflect_prompt(section),
        reflect_inputs,
        SECTION_SCHEMA,
        model=STAGE6_MODEL,
        extra_validator=_validate_section,
    )
    _check_ack(data, run_id, reflect_stage)
    log_stage_call(run_id, reflect_stage, timing)
    return data["section_markdown"]


def cited_ref_ids(sections: dict) -> set[str]:
    """The ref ids actually cited in the paper BODY (every section except
    References itself). Ids are cited in brackets per the draft prompt, so a
    bare word boundary match on R<n> is the detection — deliberately generous,
    because over-detecting keeps a reference that is arguably used while
    under-detecting would delete a legitimate citation's entry."""
    body = "\n".join(
        text for name, text in sections.items()
        if name != "References" and isinstance(text, str)
    )
    return set(re.findall(r"\bR\d+\b", body))


def prune_uncited_references(sections: dict, refs: list) -> tuple[dict, list]:
    """Delete from the References section every entry the body never cites.

    Run 20260720T080610Z shipped an E. coli metabolic paper whose reference
    list was a CMS/LHCb dimuon-decay paper, an ATLAS detector-performance
    paper, and an IceCube/LIGO neutrino search — none cited anywhere in the
    body, and none related to the subject. They arrived because arXiv's
    full-sentence all: queries return off-topic noise (a KNOWN issue since
    Step 17 chunk 3) and the References prompt said to list every reference
    PROVIDED rather than every reference USED.

    This is code, not prompt text, because an irrelevant citation is a desk
    rejection on its own and 'anything we can't afford to have broken goes in
    code'. Returns (sections, dropped) — sections with a rebuilt References
    body, and the dropped records for the log. A paper citing nothing gets an
    honest one-line References section rather than a fabricated list.
    """
    cited = cited_ref_ids(sections)
    kept = [r for r in refs if r.get("ref") in cited]
    dropped = [r for r in refs if r.get("ref") not in cited]
    if not dropped:
        return sections, []
    sections = dict(sections)
    if kept:
        sections["References"] = "\n\n".join(
            f"{n}. {r.get('ref')} ({r.get('year', 'n.d.')}). "
            f"{r.get('source', '')}. {r.get('title', '')}".strip()
            for n, r in enumerate(kept, start=1)
        )
    else:
        sections["References"] = (
            "No references are cited in this paper: the retrieved literature "
            "was not relevant to the work reported here."
        )
    return sections, dropped


def _write_pruned(run_id: str, paper_path, sections: dict, refs: list) -> None:
    """Assemble and write the paper with uncited references pruned.

    Pruning happens at WRITE time and never mutates the working `sections`
    dict, so a lint regeneration always feeds back the model's own section
    text rather than a pruned copy of it.
    """
    pruned, dropped = prune_uncited_references(sections, refs)
    if dropped:
        _log(
            run_id,
            f"REFS_PRUNED {len(dropped)} uncited reference(s) dropped from the "
            f"paper: {', '.join(str(r.get('ref')) for r in dropped)}",
        )
    paper_path.write_text(assemble_paper(pruned))


def assemble_paper(sections: dict) -> str:
    """Code-authored assembly: Title and Abstract as-is (it carries its own
    '# ' title line), every other section under a code-written '## ' heading
    — so the mandatory heading can never depend on model formatting."""
    parts = [sections["Title and Abstract"].strip()]
    for name in SECTION_NAMES[1:]:
        parts.append(f"## {name}\n\n{sections[name].strip()}")
    return "\n\n".join(parts) + "\n"


def run(baton: Baton) -> Baton:
    run_id = baton.run_id
    thought = baton.payload["thought"]
    iterate_decision = baton.payload["iterate_decision"]
    verdict = _load_verdict(run_id)
    fidelity_class = verdict["label"]
    summaries = journal_recent_by_kind("learned_summary", limit=3)
    refs = gather_references(thought["learned_summary"], run_id)
    _log(
        run_id,
        f"STAGE6_PAPER inputs: fidelity_class={fidelity_class} "
        f"learned_summaries={len(summaries)} references={len(refs)} "
        f"refs_mode={REFS_MODE}",
    )

    stage_dir = Path("runs") / run_id / "stage6"
    stage_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = stage_dir / "paper_validation.json"
    paper_path = stage_dir / "paper.md"

    def write_sidecar(items: list) -> dict:
        sidecar = {"fidelity_class": fidelity_class, "validation_items": items}
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
        return sidecar

    # SIDECAR-FIRST: the validation handoff is written before any prose.
    sidecar = write_sidecar(
        _draft_validation_items(run_id, fidelity_class, verdict, thought)
    )

    def section_base(name: str) -> dict:
        return _section_inputs(
            run_id, name, thought, iterate_decision, verdict, summaries,
            refs, sidecar,
        )

    sections = {name: _draft_section(run_id, name, section_base(name))
                for name in SECTION_NAMES}
    _write_pruned(run_id, paper_path, sections, refs)

    # Lint-with-error-feedback: regenerate ONLY what failed, bounded.
    failures = lint_paper(run_id)
    regeneration = 0
    while failures and regeneration < MAX_LINT_REGENERATIONS:
        regeneration += 1
        _log(
            run_id,
            f"PAPER_LINT regeneration={regeneration} "
            f"failures={json.dumps(failures)}",
        )
        sidecar_errors = [f["message"] for f in failures if f["target"] == "sidecar"]
        targets = {f["target"] for f in failures if f["target"] in SECTION_NAMES}
        if sidecar_errors:
            sidecar = write_sidecar(
                _draft_validation_items(
                    run_id, fidelity_class, verdict, thought,
                    lint_feedback=sidecar_errors,
                )
            )
            # What Humans Must Validate derives from the sidecar: a sidecar
            # regeneration always regenerates it too.
            targets.add(REQUIRED_HEADING)
        for name in (s for s in SECTION_NAMES if s in targets):
            feedback = [
                f["message"] for f in failures
                if f["target"] in (name, "sidecar")
            ]
            sections[name] = _draft_section(
                run_id, name, section_base(name), lint_feedback=feedback
            )
        _write_pruned(run_id, paper_path, sections, refs)
        failures = lint_paper(run_id)

    if failures:
        _log(run_id, f"PAPER_LINT FINAL failures={json.dumps(failures)}")
        raise RuntimeError(
            f"stage6_paper: paper failed lint after {MAX_LINT_REGENERATIONS} "
            f"regeneration round(s); evidence kept at {stage_dir}. "
            f"Failures: {failures}"
        )

    # DESK-REJECTION SCREEN (owner-ruled 2026-07-20). The lint is mechanical —
    # headings present, sidecar well-formed. This asks the different question:
    # would a handling editor send this out for review? A manuscript defect
    # ("rewrite") is repaired here, bounded; a manuscript the experiment itself
    # cannot support ("redesign") is stashed for the supervisor, which owns
    # loop-backs. Both routes only ever fire on an actual reject.
    execution_results = baton.payload.get("execution_results") or {}
    review = desk_review(run_id, paper_path.read_text(), execution_results)
    rewrites = 0
    while (
        review["desk_reject"]
        and review["remedy"] == "rewrite"
        and rewrites < MAX_DESK_REWRITES
    ):
        rewrites += 1
        _log(run_id, f"DESK_REVIEW rewrite {rewrites}/{MAX_DESK_REWRITES}")
        for name in SECTION_NAMES:
            sections[name] = _draft_section(
                run_id, name, section_base(name),
                lint_feedback=[
                    "A journal editor desk-rejected the previous draft for: "
                    + "; ".join(review["reasons"])
                    + ". Fix this without overstating what was measured."
                ],
            )
        _write_pruned(run_id, paper_path, sections, refs)
        if lint_paper(run_id):
            break  # a rewrite that breaks the lint is worse; keep the lint-clean text
        review = desk_review(run_id, paper_path.read_text(), execution_results)

    (stage_dir / "desk_review.json").write_text(json.dumps(review, indent=2))
    if review["desk_reject"]:
        # NON-payload attribute (the payload schema is locked), same channel as
        # the barren diagnosis. The supervisor decides what to do about it.
        baton._desk_reject = review

    baton.add_history(
        "stage6_paper",
        f"paper written: fidelity_class={fidelity_class}, "
        f"{len(sidecar['validation_items'])} validation item(s), "
        f"{len(SECTION_NAMES)} sections, lint clean, "
        # Three states, never two: an UNSCREENED paper must never be recorded
        # as having passed the screen. That conflation is precisely how a
        # quality gate silently stops being one.
        f"desk_screen={'unscreened' if not review.get('checked') else ('reject' if review['desk_reject'] else 'pass')}",
    )
    return baton
