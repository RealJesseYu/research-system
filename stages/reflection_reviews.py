"""
reflection_reviews.py — the six Co-Scientist Reflection review types for the
Step-17 Ideation rebuild. Called only by stages/stage1_ideation.py's
Reflection portion; Generation (stages/generation_strategies.py) and
everything downstream of Reflection (the deterministic filter, Ranking, the
delivered object) are untouched and live where they always did.

The six review types (faithful to the Co-Scientist Reflection agent):
  1. initial_review — the fast gate, NO external tools: ONE call over the
     whole candidate pool, quick-discarding candidates that are obviously
     flawed on correctness, quality, novelty, or preliminary safety. Runs
     FIRST so the expensive grounded reviews are never spent on candidates
     that fail the cheap gate.
  2. full_review — the grounded correctness/quality/novelty review, one
     call per initial-gate survivor, WITH live per-hypothesis retrieval
     (corpus RAG + arXiv REQUIRED, their failures propagate; Semantic
     Scholar + web search best-effort, failures recorded and proceeded
     past — same source policy as Generation). THE NOVELTY CALL IS THE
     THING UNDER WATCH this chunk: its verdict must cite ref ids from the
     snippets actually shown (validated inside the re-ask loop; a "known"
     verdict must cite at least one ref), and verdict + rationale + cited
     refs are saved per hypothesis so the novelty-check's grounding is
     inspectable from evidence alone.
  3. deep_verification_review — decompose the hypothesis into constituent
     assumptions, break each into sub-assumptions, evaluate each for
     correctness, identify invalidating elements, and judge whether any
     flawed assumption is FUNDAMENTAL. A non-fundamental flaw does not
     kill a hypothesis; a fundamental one discards it — that consequence
     is enforced deterministically by the orchestrator, not by prompt hope.
  4. observation_review — can the hypothesis account for existing
     observations (the same bounded retrieved snippets, plus journal leads
     when present — already framed leads-not-facts)? Is it a superior
     explanation for any of them?
  5. simulation_review — mentally simulate the proposed mechanism
     step-wise and surface the scenarios where it fails.
  6. recurrent_tournament_review — SEAM ONLY this chunk: in Co-Scientist
     this review adapts to accumulated tournament results, but the Ranking
     tournament DOES NOT EXIST YET (later chunk). The None-defaulted
     tournament_state parameter is where its results will attach; when
     None (always, this chunk) the unit records itself inert and makes NO
     model call — same pattern as Generation's meta_review_feedback seam.
     No tournament input is invented.

Discipline preserved (same as generation_strategies.py):
  - Every model call is Sonnet through call_stage_model (review/critique
    is not a hard judgment) — same door, same isolation, same bounded
    re-ask loop, same write-before-call transcripts.
  - Summarize-at-the-wrapper: only the retrieval tools' bounded records
    enter any review input; no raw tool output exists at this layer.
  - Evidence over mechanism: everything each review saw and returned is
    saved to runs/<run_id>/stage1/reflection_reviews.json — per-hypothesis
    retrieval records (including per-source failures), all review outputs,
    both discard lists, and the final filter-facing reflections.
  - Journal-poison ruling: memory content arrives already framed
    leads-not-facts (the block is built by stage1_ideation) and goes ONLY
    to the observation review — the unit whose job is prior observations.
  - The downstream contract is unchanged: the orchestrator returns
    reflections shaped exactly {hypothesis_id, novelty, critique, quality},
    the fields filter_survivors has consumed since Step 8.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from model_call import call_stage_model, log_stage_call

_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
if str(_RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_DIR))

from scholar_search import search_arxiv, search_semantic_scholar  # noqa: E402
from search import search_index  # noqa: E402
from web_search import web_search  # noqa: E402

# Same value as stage1_ideation.SONNET_MODEL (importing it from there would
# be circular — stage1_ideation imports this module).
SONNET_MODEL = "claude-sonnet-4-6"

TOP_K_PER_SOURCE = 3


INITIAL_REVIEW_SYSTEM_PROMPT = (
    "You are the initial-review unit of the Reflection stage in an autonomous research "
    "pipeline. You are given a research domain and the run's full pool of candidate "
    "hypotheses. WITHOUT any external tools or retrieved literature — from the candidate "
    "text and your general knowledge alone — quickly discard any candidate that is "
    "obviously flawed on correctness (contradicts well-established physics), quality (too "
    "vague or not testable by a simulation), novelty (restates a textbook fact or classic "
    "well-established result), or preliminary safety (hazardous or unethical to pursue). "
    "This is a fast gate before deeper grounded reviews: when genuinely in doubt, pass the "
    "candidate through. Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "reviews": '
    '[{"id": "<candidate id>", "verdict": "pass" or "discard", '
    '"reason": "<one sentence naming the dimension that decided it>"}, '
    "... exactly one such object per candidate]}."
)

FULL_REVIEW_SYSTEM_PROMPT = (
    "You are the full-review unit of the Reflection stage in an autonomous research "
    "pipeline, reviewing ONE candidate hypothesis. You are given the hypothesis plus "
    "literature snippets retrieved live for it, each tagged with a ref id. Judge NOVELTY "
    "strictly against those snippets: if any retrieved work already establishes the "
    "hypothesis's claim, the verdict is 'known' and novelty_grounded_in MUST cite the ref "
    "id(s) showing so; if the retrieved literature approaches but does not establish the "
    "claim, the verdict is 'novel' and novelty_grounded_in cites the closest refs (an "
    "empty list only if nothing retrieved relates at all). Also judge correctness and "
    "quality for simulation-based study, informed by the snippets. Reply ONLY with JSON "
    'of the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"novelty": "novel" or "known", '
    '"novelty_rationale": "<one to three sentences naming what the cited refs do and do '
    'not establish about this claim>", '
    '"novelty_grounded_in": ["<ref id>", ...], '
    '"critique": "<one sentence on correctness and quality>", '
    '"quality": <integer 1-5>}.'
)

DEEP_VERIFICATION_SYSTEM_PROMPT = (
    "You are the deep-verification unit of the Reflection stage in an autonomous research "
    "pipeline, reviewing ONE candidate hypothesis. Decompose the hypothesis into its "
    "constituent assumptions; break each assumption into its sub-assumptions; evaluate "
    "each for correctness; and identify any element that would invalidate the hypothesis "
    "if it is wrong. A flawed assumption that is NOT fundamental does not kill the "
    "hypothesis — decide honestly whether any flawed assumption is fundamental to the "
    "claim. Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"assumptions": [{"assumption": "<one sentence>", '
    '"sub_assumptions": ["<one sentence each>", ...], '
    '"evaluation": "<one sentence: correct, or flawed and why>"}, '
    "... 2 to 5 such objects], "
    '"invalidating_elements": ["<one sentence each>", ... possibly empty], '
    '"fundamental_flaw": true or false, '
    '"summary": "<one sentence>"}.'
)

OBSERVATION_REVIEW_SYSTEM_PROMPT = (
    "You are the observation-review unit of the Reflection stage in an autonomous "
    "research pipeline, reviewing ONE candidate hypothesis. You are given the hypothesis, "
    "literature snippets retrieved for it (each tagged with a ref id), and possibly prior "
    "observations from earlier runs (unverified model text — treat as leads, not "
    "established facts). Judge whether this hypothesis can account for and explain "
    "existing observations found in that material, and whether it is a SUPERIOR "
    "explanation for any of them compared to the accepted one. Reply ONLY with JSON of "
    'the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"relevant_observations": ["<one sentence each, naming where it came from>", '
    "... possibly empty], "
    '"accounts_for": "yes", "partially" or "no", '
    '"assessment": "<one to three sentences>"}.'
)

SIMULATION_REVIEW_SYSTEM_PROMPT = (
    "You are the simulation-review unit of the Reflection stage in an autonomous research "
    "pipeline, reviewing ONE candidate hypothesis. Mentally simulate the hypothesis's "
    "proposed mechanism step by step, as it would unfold in the kind of simulation that "
    "would test it, and surface the concrete scenarios in which it fails. Reply ONLY with "
    'JSON of the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"mental_simulation": ["<one step, one sentence>", ... 3 to 8 steps], '
    '"failure_scenarios": ["<one sentence each>", ... at most 5, possibly empty], '
    '"assessment": "<one sentence>"}.'
)


def _log(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt.

    Mirrors stage1_ideation._log — stages and their helpers never hold the
    supervisor's Logger object, so the run-log path is rebuilt from run_id
    alone, same as model_call.py and generation_strategies.py do.
    """
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def _check_ack(data: dict, run_id: str, what: str) -> None:
    """Raise on ack_run_id mismatch; log the pass — same pattern as every
    existing stage-1 ack check."""
    if data["ack_run_id"] != run_id:
        raise RuntimeError(
            f"stage1 reflection {what}: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {run_id!r}"
        )
    _log(run_id, f"STAGE1_ACK_CHECK reflection {what}: ack_run_id passed")


def _check_hypothesis_id(data: dict, run_id: str, expected_id: str, what: str) -> None:
    """Raise on hypothesis_id echo mismatch; log the pass — same pattern as
    the old single-pass Reflection's check."""
    if data["hypothesis_id"] != expected_id:
        raise RuntimeError(
            f"stage1 reflection {what}: hypothesis_id mismatch — got "
            f"{data['hypothesis_id']!r}, expected {expected_id!r}"
        )
    _log(run_id, f"STAGE1_ACK_CHECK reflection {what}: hypothesis_id passed")


def _is_str_list(value, allow_empty: bool = True) -> bool:
    """True when value is a list whose entries are all non-empty strings.

    Local shape helper (small disclosed sibling of the one in
    generation_strategies — importing a private helper across stage modules
    would couple them for three lines of logic)."""
    if not isinstance(value, list):
        return False
    if not value:
        return allow_empty
    return all(isinstance(v, str) and v.strip() for v in value)


# --- Per-hypothesis retrieval for the grounded reviews -----------------------


def gather_review_refs(run_id: str, hypothesis: dict) -> tuple[list[dict], dict]:
    """Retrieve bounded literature records for ONE hypothesis (query = its
    statement) and return (combined ref-tagged list, evidence dict).

    Same source policy as Generation's gather_literature_evidence: corpus
    RAG and arXiv are REQUIRED — a failure there propagates (an honest
    stage failure). Semantic Scholar and web search are best-effort: a
    RuntimeError from either is recorded in the evidence and retrieval
    proceeds without that source. Every record is already bounded by its
    wrapper (snippet caps); nothing raw exists at this layer. web_search is
    the one tool that needs run_id — its own transcript is written before
    its call fires. Ref ids R1..Rn are scoped to this hypothesis's reviews;
    the evidence dict is stored under the hypothesis's entry in
    reflection_reviews.json rather than a separate file per hypothesis.
    """
    query = hypothesis["statement"]
    corpus_records = [
        {"source": r["source"], "title": r["title"], "snippet": r["snippet"]}
        for r in search_index("literature", query, top_k=TOP_K_PER_SOURCE)
    ]
    arxiv_records = search_arxiv(query, top_k=TOP_K_PER_SOURCE)

    try:
        s2_records = search_semantic_scholar(query, top_k=TOP_K_PER_SOURCE)
        s2_evidence: list | dict = s2_records
    except RuntimeError as e:
        s2_records = []
        s2_evidence = {"error": str(e)}
        _log(
            run_id,
            f"STAGE1_REFLECTION_RETRIEVAL {hypothesis['id']} semantic_scholar failed "
            f"(recorded, proceeding): {str(e).splitlines()[0]}",
        )

    try:
        web_records = web_search(query, run_id=run_id, top_k=TOP_K_PER_SOURCE)
        web_evidence: list | dict = web_records
    except RuntimeError as e:
        web_records = []
        web_evidence = {"error": str(e)}
        _log(
            run_id,
            f"STAGE1_REFLECTION_RETRIEVAL {hypothesis['id']} web_search failed "
            f"(recorded, proceeding): {str(e).splitlines()[0]}",
        )

    combined_refs = [
        {"ref": f"R{n}", **record}
        for n, record in enumerate(
            [*corpus_records, *arxiv_records, *s2_records, *web_records], start=1
        )
    ]

    evidence = {
        "query": query,
        "corpus": corpus_records,
        "arxiv": arxiv_records,
        "semantic_scholar": s2_evidence,
        "web": web_evidence,
        "combined_refs": combined_refs,
    }
    _log(
        run_id,
        f"STAGE1_REFLECTION_RETRIEVAL {hypothesis['id']} corpus={len(corpus_records)} "
        f"arxiv={len(arxiv_records)} "
        f"s2={len(s2_records) if isinstance(s2_evidence, list) else 'error'} "
        f"web={len(web_records) if isinstance(web_evidence, list) else 'error'} "
        f"-> {len(combined_refs)} combined refs",
    )
    return combined_refs, evidence


# --- Review 1: initial review (fast gate, NO external tools) -----------------


def initial_review(run_id: str, domain: str, hypotheses: list[dict]) -> list[dict]:
    """ONE Sonnet call over the whole pool, no retrieval: quick pass/discard
    per candidate on correctness / quality / novelty / preliminary safety.
    Returns one {id, verdict, reason} per candidate; the validator enforces
    exactly one review per pool id, inside the re-ask loop."""
    valid_ids = [h["id"] for h in hypotheses]

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        reviews = data.get("reviews")
        if not isinstance(reviews, list) or len(reviews) != len(valid_ids):
            return [
                f"reviews must be a list of exactly {len(valid_ids)} objects, "
                "one per candidate."
            ]
        seen: list[str] = []
        for n, r in enumerate(reviews, start=1):
            if not isinstance(r, dict):
                errors.append(f"entry {n} must be a JSON object.")
                continue
            cid = r.get("id")
            if cid not in valid_ids:
                errors.append(
                    f"entry {n} id {cid!r} is not a candidate id; "
                    f"candidate ids are {valid_ids}."
                )
            else:
                seen.append(cid)
            if r.get("verdict") not in ("pass", "discard"):
                errors.append(f"entry {n} verdict must be 'pass' or 'discard'.")
            reason = r.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"entry {n} reason must be a non-empty string.")
        if not errors and sorted(seen) != sorted(valid_ids):
            errors.append("reviews must cover every candidate id exactly once.")
        return errors

    data, timing = call_stage_model(
        "stage1_reflection_initial",
        INITIAL_REVIEW_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "domain": domain,
            "candidates": [
                {"id": h["id"], "statement": h["statement"], "rationale": h["rationale"]}
                for h in hypotheses
            ],
        },
        {"required": ["ack_run_id", "reviews"]},
        model=SONNET_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, "initial_review")
    log_stage_call(run_id, "stage1_reflection_initial", timing)
    return [
        {"id": r["id"], "verdict": r["verdict"], "reason": r["reason"]}
        for r in data["reviews"]
    ]


# --- Review 2: full review (grounded correctness/quality/novelty) ------------


def full_review(run_id: str, domain: str, hypothesis: dict, refs: list[dict]) -> dict:
    """One Sonnet call per survivor WITH the retrieved snippets: the grounded
    novelty verdict (cited refs validated against the refs actually shown —
    a 'known' verdict must cite at least one) plus the correctness/quality
    critique. This review supplies the novelty, critique, and quality fields
    the downstream deterministic filter has always consumed."""
    valid_refs = {r["ref"] for r in refs}

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        rationale = data.get("novelty_rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("novelty_rationale must be a non-empty string.")
        grounded = data.get("novelty_grounded_in")
        if not isinstance(grounded, list):
            errors.append("novelty_grounded_in must be a list of ref ids (possibly empty).")
        else:
            unknown = [r for r in grounded if r not in valid_refs]
            if unknown:
                errors.append(
                    f"novelty_grounded_in cites unknown refs {unknown}; "
                    f"the provided refs are {sorted(valid_refs)}."
                )
            if data.get("novelty") == "known" and not grounded:
                errors.append(
                    "a 'known' verdict must cite at least one ref id in "
                    "novelty_grounded_in showing the claim is already established."
                )
        critique = data.get("critique")
        if not isinstance(critique, str) or not critique.strip():
            errors.append("critique must be a non-empty string.")
        quality = data.get("quality")
        if isinstance(quality, bool) or not isinstance(quality, int) or not (1 <= quality <= 5):
            errors.append("quality must be an integer from 1 to 5.")
        return errors

    data, timing = call_stage_model(
        f"stage1_reflection_full_{hypothesis['id']}",
        FULL_REVIEW_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "domain": domain,
            "hypothesis_id": hypothesis["id"],
            "hypothesis_statement": hypothesis["statement"],
            "hypothesis_rationale": hypothesis["rationale"],
            "literature_snippets": refs,
        },
        {
            "required": [
                "ack_run_id", "hypothesis_id", "novelty", "novelty_rationale",
                "novelty_grounded_in", "critique", "quality",
            ],
            "enums": {"novelty": ["novel", "known"]},
        },
        model=SONNET_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, f"full_review {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"full_review {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_full_{hypothesis['id']}", timing)
    return {
        "novelty": data["novelty"],
        "novelty_rationale": data["novelty_rationale"],
        "novelty_grounded_in": data["novelty_grounded_in"],
        "critique": data["critique"],
        "quality": data["quality"],
    }


# --- Review 3: deep verification review ---------------------------------------


def deep_verification_review(run_id: str, domain: str, hypothesis: dict) -> dict:
    """One Sonnet call per survivor, no retrieval: assumptions decomposed
    into sub-assumptions, each evaluated; invalidating elements named; and
    the fundamental-or-not judgment on any flawed assumption. The
    orchestrator (deterministic Python) discards on fundamental_flaw=true."""

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        assumptions = data.get("assumptions")
        if not isinstance(assumptions, list) or not (2 <= len(assumptions) <= 5):
            return ["assumptions must be a list of 2 to 5 objects."]
        for n, a in enumerate(assumptions, start=1):
            if not isinstance(a, dict):
                errors.append(f"assumptions entry {n} must be a JSON object.")
                continue
            for field in ("assumption", "evaluation"):
                value = a.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"assumptions entry {n} field {field!r} must be a non-empty string."
                    )
            if not _is_str_list(a.get("sub_assumptions")):
                errors.append(
                    f"assumptions entry {n} sub_assumptions must be a list of "
                    "non-empty strings (possibly empty)."
                )
        if not _is_str_list(data.get("invalidating_elements")):
            errors.append(
                "invalidating_elements must be a list of non-empty strings (possibly empty)."
            )
        if not isinstance(data.get("fundamental_flaw"), bool):
            errors.append("fundamental_flaw must be true or false.")
        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append("summary must be a non-empty string.")
        return errors

    data, timing = call_stage_model(
        f"stage1_reflection_deepverify_{hypothesis['id']}",
        DEEP_VERIFICATION_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "domain": domain,
            "hypothesis_id": hypothesis["id"],
            "hypothesis_statement": hypothesis["statement"],
            "hypothesis_rationale": hypothesis["rationale"],
        },
        {"required": ["ack_run_id", "hypothesis_id", "assumptions",
                      "invalidating_elements", "fundamental_flaw", "summary"]},
        model=SONNET_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, f"deep_verification {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"deep_verification {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_deepverify_{hypothesis['id']}", timing)
    return {
        "assumptions": data["assumptions"],
        "invalidating_elements": data["invalidating_elements"],
        "fundamental_flaw": data["fundamental_flaw"],
        "summary": data["summary"],
    }


# --- Review 4: observation review ---------------------------------------------


def observation_review(
    run_id: str, domain: str, hypothesis: dict, refs: list[dict], memory_block: str | None
) -> dict:
    """One Sonnet call per survivor: can the hypothesis account for existing
    observations? Sees the SAME bounded refs the full review saw (no second
    retrieval) plus, when present, the journal leads — this is the one
    review unit that receives memory, because prior observations are its
    job; the block arrives already framed leads-not-facts."""

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        if not _is_str_list(data.get("relevant_observations")):
            errors.append(
                "relevant_observations must be a list of non-empty strings (possibly empty)."
            )
        assessment = data.get("assessment")
        if not isinstance(assessment, str) or not assessment.strip():
            errors.append("assessment must be a non-empty string.")
        return errors

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_id": hypothesis["id"],
        "hypothesis_statement": hypothesis["statement"],
        "hypothesis_rationale": hypothesis["rationale"],
        "literature_snippets": refs,
    }
    if memory_block is not None:
        stage_input["prior_observations"] = memory_block
    data, timing = call_stage_model(
        f"stage1_reflection_observation_{hypothesis['id']}",
        OBSERVATION_REVIEW_SYSTEM_PROMPT,
        stage_input,
        {
            "required": ["ack_run_id", "hypothesis_id", "relevant_observations",
                         "accounts_for", "assessment"],
            "enums": {"accounts_for": ["yes", "partially", "no"]},
        },
        model=SONNET_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, f"observation_review {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"observation_review {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_observation_{hypothesis['id']}", timing)
    return {
        "relevant_observations": data["relevant_observations"],
        "accounts_for": data["accounts_for"],
        "assessment": data["assessment"],
    }


# --- Review 5: simulation review ------------------------------------------------


def simulation_review(run_id: str, domain: str, hypothesis: dict) -> dict:
    """One Sonnet call per survivor, no retrieval: step-wise mental
    simulation of the proposed mechanism, surfacing failure scenarios."""

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        steps = data.get("mental_simulation")
        if not _is_str_list(steps, allow_empty=False) or not (3 <= len(steps) <= 8):
            errors.append("mental_simulation must be a list of 3 to 8 non-empty strings.")
        scenarios = data.get("failure_scenarios")
        if not _is_str_list(scenarios) or (isinstance(scenarios, list) and len(scenarios) > 5):
            errors.append(
                "failure_scenarios must be a list of at most 5 non-empty strings "
                "(possibly empty)."
            )
        assessment = data.get("assessment")
        if not isinstance(assessment, str) or not assessment.strip():
            errors.append("assessment must be a non-empty string.")
        return errors

    data, timing = call_stage_model(
        f"stage1_reflection_simulation_{hypothesis['id']}",
        SIMULATION_REVIEW_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "domain": domain,
            "hypothesis_id": hypothesis["id"],
            "hypothesis_statement": hypothesis["statement"],
            "hypothesis_rationale": hypothesis["rationale"],
        },
        {"required": ["ack_run_id", "hypothesis_id", "mental_simulation",
                      "failure_scenarios", "assessment"]},
        model=SONNET_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, f"simulation_review {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"simulation_review {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_simulation_{hypothesis['id']}", timing)
    return {
        "mental_simulation": data["mental_simulation"],
        "failure_scenarios": data["failure_scenarios"],
        "assessment": data["assessment"],
    }


# --- Review 6: recurrent / tournament review (seam only this chunk) -----------


def recurrent_tournament_review(
    run_id: str, hypothesis: dict, tournament_state: dict | None = None
) -> dict:
    """Review 6 — recurrent/tournament review.

    SEAM (later chunk): in Co-Scientist this review adapts to results
    accumulated across the Ranking tournament. The Elo tournament DOES NOT
    EXIST YET; tournament_state is where its accumulated results will
    attach once it does. When None (always, this chunk) this unit is
    inert: it records that fact in evidence and makes NO model call — no
    tournament input is invented before the producer is built (same
    pattern as Generation's meta_review_feedback seam). A non-None state
    raises rather than being silently ignored.
    """
    if tournament_state is None:
        return {
            "status": "inert",
            "reason": (
                "the Ranking tournament is not built yet (later chunk); "
                "no accumulated results exist to review against"
            ),
        }
    raise NotImplementedError(
        "recurrent_tournament_review: tournament_state was provided but the "
        "tournament-adapted review is not implemented yet — build it in the "
        "tournament chunk, not by accident here."
    )


# --- Orchestrator ---------------------------------------------------------------


def reflect_on_pool(
    run_id: str,
    domain: str,
    hypotheses: list[dict],
    memory_block: str | None,
    run_dir: Path,
    tournament_state: dict | None = None,
) -> tuple[list[dict], dict]:
    """Apply the six review types to the candidate pool, in the paper's
    sequence: the cheap no-tools initial review gates first, then each
    survivor gets per-hypothesis retrieval plus the full / deep-verification
    / observation / simulation reviews (the tournament review is an inert
    seam this chunk). Deterministic consequences, no model in them:
      - initial verdict 'discard' → candidate exits before any tool spend;
      - deep verification fundamental_flaw=true → candidate exits;
      - everything else becomes a reflection {hypothesis_id, novelty,
        critique, quality} — exactly the fields the existing downstream
        filter consumes (novelty/critique/quality from the grounded full
        review).
    All evidence — per-candidate initial verdicts, per-hypothesis retrieval
    records, all review outputs, both discard lists, and the final
    reflections — is saved to runs/<run_id>/stage1/reflection_reviews.json.
    Returns (reflections, summary counts). Raises RuntimeError when zero
    candidates survive reviewing — an honest halt, never padded.
    """
    initial = initial_review(run_id, domain, hypotheses)
    verdict_by_id = {r["id"]: r for r in initial}
    survivors = [h for h in hypotheses if verdict_by_id[h["id"]]["verdict"] == "pass"]
    discarded_initial = [
        verdict_by_id[h["id"]] for h in hypotheses
        if verdict_by_id[h["id"]]["verdict"] == "discard"
    ]
    _log(
        run_id,
        f"STAGE1_REFLECTION initial review: {len(survivors)} of {len(hypotheses)} "
        "candidates passed the no-tools gate",
    )

    reviews_evidence: list[dict] = []
    reflections: list[dict] = []
    discarded_fundamental: list[dict] = []
    for h in survivors:
        refs, retrieval_evidence = gather_review_refs(run_id, h)
        full = full_review(run_id, domain, h, refs)
        deep = deep_verification_review(run_id, domain, h)
        observation = observation_review(run_id, domain, h, refs, memory_block)
        simulation = simulation_review(run_id, domain, h)
        tournament = recurrent_tournament_review(run_id, h, tournament_state)

        reviews_evidence.append(
            {
                "hypothesis_id": h["id"],
                "retrieval": retrieval_evidence,
                "full_review": full,
                "deep_verification": deep,
                "observation": observation,
                "simulation": simulation,
                "tournament": tournament,
            }
        )
        _log(
            run_id,
            f"STAGE1_REFLECTION {h['id']}: novelty={full['novelty']} "
            f"quality={full['quality']} fundamental_flaw={deep['fundamental_flaw']} "
            f"accounts_for={observation['accounts_for']} "
            f"failure_scenarios={len(simulation['failure_scenarios'])}",
        )

        if deep["fundamental_flaw"]:
            discarded_fundamental.append({"id": h["id"], "reason": deep["summary"]})
            continue
        reflections.append(
            {
                "hypothesis_id": h["id"],
                "novelty": full["novelty"],
                "critique": full["critique"],
                "quality": int(full["quality"]),
            }
        )

    evidence = {
        "pool_size": len(hypotheses),
        "initial_review": initial,
        "initial_survivor_count": len(survivors),
        "discarded_by_initial_review": discarded_initial,
        "reviews": reviews_evidence,
        "discarded_by_deep_verification": discarded_fundamental,
        "tournament_review_status": (
            "inert — the Ranking tournament is not built yet (later chunk)"
            if tournament_state is None
            else "active"
        ),
        "final_reflections": reflections,
    }
    (run_dir / "reflection_reviews.json").write_text(json.dumps(evidence, indent=2))

    if not reflections:
        raise RuntimeError(
            f"stage1 reflection: all {len(hypotheses)} candidates were discarded "
            f"({len(discarded_initial)} at the initial review, "
            f"{len(discarded_fundamental)} on fundamental flaws at deep verification). "
            "Zero reviewed hypotheses remain — this run halts here rather than "
            "continuing on a hypothesis nobody vetted."
        )

    summary = {
        "pool": len(hypotheses),
        "initial_pass": len(survivors),
        "fundamental_flaw_discards": len(discarded_fundamental),
        "reflected": len(reflections),
    }
    return reflections, summary
