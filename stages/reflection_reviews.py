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
     correctness, identify invalidating elements, and classify each as
     FUNDAMENTAL (the core claim cannot survive it — sets fundamental_flaw)
     or ADDRESSABLE (a detail refinement or the experiment itself would
     resolve — recorded in addressable_notes, never fatal; Step 17-fix-A).
     This review runs WITHOUT retrieval, so an objection resting on a
     remembered numeric value is by definition addressable, never a kill.
     A fundamental flaw discards the hypothesis — that consequence is
     enforced deterministically by the orchestrator, not by prompt hope.
  4. observation_review — can the hypothesis account for existing
     observations (the same bounded retrieved snippets, plus journal leads
     when present — already framed leads-not-facts)? Is it a superior
     explanation for any of them?
  5. simulation_review — mentally simulate the proposed mechanism
     step-wise and surface the scenarios where it fails.
  6. recurrent_tournament_review — ACTIVE since Step 17-E: one Haiku call
     per survivor over the PRIOR ROUND's tournament results, which the
     iteration controller (stage1_ideation) resolves to plain hypothesis
     statements before they get here — raw cross-round ids never reach a
     review context, because canonical ids are reassigned every round.
     ADVISORY ONLY: its observations and carried concerns are recorded in
     the reflection evidence and influence NOTHING deterministic — the
     kill filter never reads them. tournament_state=None (round 1, or a
     prior round whose ranking was trivial) keeps the unit inert with no
     model call.

Discipline preserved (same as generation_strategies.py):
  - Every model call goes through call_stage_model — initial / full /
    observation / simulation reviews on Haiku (Step 18.7 downgrade), the
    recurrent/tournament review on its own Haiku pin (REVIEW6_MODEL,
    Step 17-E: advisory, no kill path), deep verification HELD on Sonnet
    (it feeds a deterministic kill with no judgment net) — same door, same
    isolation, same bounded re-ask loop, same write-before-call
    transcripts.
  - Summarize-at-the-wrapper: only the retrieval tools' bounded records
    enter any review input; no raw tool output exists at this layer.
  - Evidence over mechanism: everything each review saw and returned is
    saved to runs/<run_id>/stage1/reflection_reviews.json — per-hypothesis
    retrieval records (including per-source failures), all review outputs,
    both discard lists, and the final filter-facing reflections.
  - Journal-poison ruling: memory content arrives already framed
    leads-not-facts (the block is built by stage1_ideation) and goes ONLY
    to the observation review — the unit whose job is prior observations.
  - The downstream contract filter_survivors consumes is unchanged: the
    orchestrator returns reflections carrying {hypothesis_id, novelty,
    critique, quality} — the fields consumed since Step 8 — plus, since
    Step 17-fix-A, the survivor's addressable_notes from deep verification
    (Stage-1 evidence only; it never crosses gate 1).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from memory.journal import journal_recent_by_kind
from model_call import FULL, call_stage_model, log_stage_call
from tools.substrate_registry import routable_contracts_block

_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
if str(_RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_DIR))

from scholar_search import search_arxiv, search_openalex, search_semantic_scholar  # noqa: E402
from search import search_index  # noqa: E402
from web_search import web_search  # noqa: E402
from models import model_for  # model-tier resolver

# Step 18.7 downgrade: initial/full/observation/simulation reviews run on
# Haiku; deep verification stays on Sonnet — it feeds a DETERMINISTIC discard
# with no judgment net downstream, so downgrading it is deferred to its own
# watched move (see DEEP_VERIFY_MODEL at its sole use site).
SONNET_MODEL = model_for("light")
DEEP_VERIFY_MODEL = model_for("light")
# Step 17-E ruled pin: review 6 is advisory (no kill path), so it runs on
# the cheap tier, independent of the other pins.
REVIEW6_MODEL = model_for("light")

TOP_K_PER_SOURCE = 3

# Step 18.5: the idea archive's dead-end check. The block is code-composed
# from the SAME journal read the battery's memory-comparability pin is
# derived from — journal_recent_by_kind("learned_summary", 3) — so under a
# pinned journal state it is byte-identical for every battery slot, and it
# rides the EXISTING initial-review call (no added model call anywhere).
DEAD_END_HEADER = (
    "PRIOR-RUN DEAD ENDS FROM THE JOURNAL (unverified model text - treat as "
    "leads, not established facts): earlier runs recorded these approaches as "
    "dead ends on the available instrument; a candidate that re-proposes one "
    "should be discarded citing the entry:"
)

DEAD_END_RETRIEVAL_KIND = "learned_summary"
DEAD_END_RETRIEVAL_LIMIT = 3  # same (kind, limit) as the battery pin derivation


def build_dead_end_block(entries: list[dict]) -> str | None:
    """Pure, no I/O: format learned_summary journal entries into the
    prior-dead-ends block for the initial-review model input.

    Returns None when `entries` is empty; otherwise the exact DEAD_END_HEADER
    line followed by one line per entry:
    "- [run <run_id>, hypothesis <hypothesis_id>] <text>" — the tag is what a
    dead-end kill reason must cite.
    """
    if not entries:
        return None
    lines = [DEAD_END_HEADER]
    for e in entries:
        lines.append(
            f"- [run {e.get('run_id')}, hypothesis {e.get('hypothesis_id')}] {e.get('text')}"
        )
    return "\n".join(lines)


INITIAL_REVIEW_SYSTEM_PROMPT = (
    "You are the initial-review unit of the Reflection stage in an autonomous research "
    "pipeline. You are given a research domain and the run's full pool of candidate "
    "hypotheses. WITHOUT any external tools or retrieved literature — from the candidate "
    "text and your general knowledge alone — quickly discard any candidate that is "
    "obviously flawed on correctness (contradicts well-established physics), quality (too "
    "vague or not testable by a simulation), novelty (restates a textbook fact or classic "
    "well-established result), or preliminary safety (hazardous or unethical to pursue). "
    "When a prior_dead_ends block is present, it lists lessons earlier runs of this "
    "system recorded after their approach failed on the available instrument (unverified "
    "model text — treat as leads, not established facts): if a candidate re-proposes an "
    "approach one of those entries records as a dead end — the same inexpressible "
    "quantity, unbuildable geometry, or unsupported physics, even in new clothes — "
    "discard it, and the reason MUST cite the journal entry by its "
    "[run <run_id>, hypothesis <hypothesis_id>] tag; do not discard on a dead-end entry "
    "that merely touches the same topic without the same instrument limit. "
    "This is a fast gate before deeper grounded reviews: when genuinely in doubt, pass the "
    "candidate through. Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "reviews": '
    '[{"id": "<candidate id>", "verdict": "pass" or "discard", '
    '"promise": <integer 1-5, how worth the expensive review this candidate is: 5 = clearly the strongest in the pool, 1 = passes but is the weakest>, '
    '"reason": "<one sentence naming the dimension that decided it>"}, '
    "... exactly one such object per candidate]}."
)

_RETIRED_SOURCE = {
    "note": "retired: the review agent searches the web itself (FULL tools) "
            "— the keyword APIs cost latency, not signal"
}


def _is_checkable_citation(entry, valid_refs) -> bool:
    """True when a novelty citation is something a human can go look at: one of
    the pre-fetched ref ids, or a source the reviewer located and cited by a
    locator (URL, DOI, or arXiv id).

    This is the anti-hallucination discipline, re-sited. The old rule — 'must be
    one of the refs we handed you' — enforced honesty by making the reviewer
    blind, which is worse than the disease. The rule now is 'must be findable',
    which keeps a reviewer from inventing a paper while letting it read the
    actual literature. It cannot prove the source exists; the reviewer has
    WebFetch and is told never to cite what it has not seen."""
    if not isinstance(entry, str) or not entry.strip():
        return False
    if entry in valid_refs:
        return True
    low = entry.lower()
    return ("http://" in low or "https://" in low or "doi.org" in low
            or low.startswith("doi:") or "10." in low and "/" in low
            or "arxiv" in low)


FULL_REVIEW_SYSTEM_PROMPT = (
    "You are the full-review unit of the Reflection stage in an autonomous research "
    "pipeline, reviewing ONE candidate hypothesis. You are given the hypothesis plus some "
    "literature snippets that were pre-fetched for it, each tagged with a ref id.\n\n"
    "ESTABLISH THE PRIOR ART YOURSELF. The pre-fetched snippets are a STARTING POINT, not "
    "the boundary of what exists — they come from keyword APIs that frequently return "
    "little or nothing on target. You have web search and web fetch: USE THEM. Search for "
    "the actual prior work on this claim the way a researcher would — the standard method "
    "in that field, the canonical papers, the review articles, whoever did it first. If a "
    "technique is textbook or decades old in the hypothesis's domain, you are expected to "
    "find that and say so. Do NOT conclude 'novel' merely because the pre-fetched snippets "
    "failed to mention it; that is a statement about the search, not about the literature.\n\n"
    "Then judge NOVELTY: if prior work already establishes the hypothesis's claim, the "
    "verdict is 'known' and novelty_grounded_in MUST cite it; if the literature approaches "
    "but does not establish the claim, the verdict is 'novel' and novelty_grounded_in cites "
    "the closest work you found. EVERY citation must be checkable by a human — either a "
    "provided ref id, or a real source you located, given as a URL, DOI, or arXiv id. Never "
    "cite a paper you have not actually seen. Also judge correctness and "
    "quality for simulation-based study, informed by what you found.\n\n"
    "NOVELTY OF METHOD IS NOT THE SAME AS NOVELTY OF ANSWER, and only the second one "
    "decides whether an experiment is worth running. Almost every good applied hypothesis "
    "uses a well-established method — that is WHY it is likely to work. What matters is "
    "whether anyone has actually MEASURED THE ANSWER for this specific question in this "
    "specific setting. A textbook technique carried into a domain that has never applied "
    "it, where the size of the effect is genuinely unknown, is a GOOD hypothesis even "
    "though its novelty is 'known'. Set answer_established true ONLY when running the "
    "experiment would teach nothing because the result is already on record. Reply ONLY "
    "with JSON "
    'of the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"novelty": "novel" or "known", '
    '"answer_established": <true ONLY if prior work has already MEASURED THE ANSWER for '
    "this specific claim, in this specific setting, so running the experiment would "
    "teach nothing new; false if the method is well known but this particular question "
    'has not actually been answered>, '
    '"novelty_rationale": "<one to three sentences naming what the cited refs do and do '
    'not establish about this claim>", '
    '"novelty_grounded_in": ["<ref id>", ...], '
    '"critique": "<one sentence on correctness and quality>", '
    '"quality": <integer 1-5>}.'
)

# --- R-WIN-1: instrument-contract grounding (the h6 fix) + impact lens -------
# UNCONDITIONAL contract block (new-era baseline, not switched) and a
# switched IMPACT lens, both grounding the full review — the merit review
# that feeds the deterministic filter's novelty/quality/critique. Single
# source of truth: the block body IS the registry's routable_contracts_block —
# every routable contract verbatim, never a pasted copy (hard rule (a);
# R5, owner 2026-07-17). No new kill path: the lens and the
# contracts steer the quality/critique judgment, they add no discard branch.
INSTRUMENT_CONTRACT_HEADER = (
    "INSTRUMENT CONTRACTS (what the VALIDATED instruments measure — one part of "
    "what this run can reach, not the whole of it)"
)
# R-CAGE-1 (owner, 2026-07-26; docs/memo_reflection_cage_fix.md). The previous
# sentence read "Candidates whose test requires measurements outside every
# listed contract must be treated as weaker bets, stated in the reasoning."
# That penalized every hypothesis testable by anything the registry does not
# enroll — a public dataset (AlphaFold DB, PubChem, Materials Project), a
# connector, or plain code — and it did so in the merit review that feeds the
# deterministic quality filter, so such candidates could be scored down and
# dropped BEFORE the free experimenter ever saw them. That is the PRIME
# DIRECTIVE's cage in miniature: the registry bounding what may be thought,
# rather than offering tools that may be used.
#
# Generation already had this right (FEASIBILITY_NUDGE_INSTRUCTION: "a
# hypothesis is untestable only if NOTHING available could evaluate it — not
# merely if no named solver exposes it", and it names connectors explicitly).
# The two halves of ideation disagreed, and reflection was the wrong one. This
# makes them agree, in generation's direction.
INSTRUMENT_CONTRACT_INSTRUCTION = (
    "These contracts describe what the VALIDATED instruments measure. They are "
    "NOT the limit of what this run can reach: the experimenter also has code, "
    "a shell, the web, any configured connector, and any public dataset or API "
    "it can call (AlphaFold DB, PubChem, Materials Project and the like). "
    "Treat a candidate as a weaker bet only if NOTHING available could evaluate "
    "it — not merely because no listed contract covers it — and say which of "
    "those routes you considered when you do."
)


def instrument_contract_block() -> str:
    """The delimited instrument-contract block appended to grounded reviews.
    Body = the registry's all-routable contract block verbatim (single source
    of truth)."""
    # R5 (owner, 2026-07-17): Stage-1 surfaces carry ALL routable contracts —
    # the D.1.1 cavity pin is retired here; selection stays a Stage-2/Step-35
    # design (P8 pin unmoved).
    return (
        "\n\n" + INSTRUMENT_CONTRACT_HEADER + ":\n"
        + routable_contracts_block() + "\n"
        + INSTRUMENT_CONTRACT_INSTRUCTION
    )


CRITERIA_IMPACT_ENV = "CRITERIA_IMPACT"

IMPACT_LENS = (
    "Also apply an IMPACT lens: if this hypothesis were true, who would change "
    "what they do — whose decision or practice would shift? Let a hypothesis "
    "whose truth would concretely change what someone does weigh up in your "
    "quality judgment, and name this in your critique. "
)

_FULL_REVIEW_REPLY_MARKER = "Reply ONLY with JSON"


def compose_full_review_prompt() -> str:
    """R-WIN-1: the full-review system prompt grounded in the instrument
    contract (UNCONDITIONAL, appended) and — when CRITERIA_IMPACT=1 — carrying
    the IMPACT lens (inserted into the judging section before the reply spec).
    With the impact switch off the only difference from today's prompt is the
    appended contract block (asserted separately in the byte-identity test)."""
    prompt = FULL_REVIEW_SYSTEM_PROMPT
    if os.environ.get(CRITERIA_IMPACT_ENV, "0") == "1":
        idx = prompt.index(_FULL_REVIEW_REPLY_MARKER)
        prompt = prompt[:idx] + IMPACT_LENS + prompt[idx:]
    return prompt + instrument_contract_block()


DEEP_VERIFICATION_SYSTEM_PROMPT = (
    "You are the deep-verification unit of the Reflection stage in an autonomous research "
    "pipeline, reviewing ONE candidate hypothesis. Decompose the hypothesis into its "
    "constituent assumptions; break each assumption into its sub-assumptions; evaluate "
    "each for correctness; and identify any element that would invalidate the hypothesis "
    "if it is wrong. Classify each invalidating element as EITHER fundamental — the core "
    "claim cannot survive it — OR addressable — a detail that refinement or the experiment "
    "itself would resolve, such as an imprecise parameter range, an open empirical question "
    "the experiment would test, or a missing justification that could be supplied. Only "
    "fundamental elements set fundamental_flaw to true; addressable elements go into "
    "addressable_notes and do NOT set it. You are running WITHOUT retrieval: you have no "
    "literature snippets, so you must NOT assert any specific physical constant, "
    "eigenvalue, benchmark value, or numeric ratio as an 'established' or 'known' fact to "
    "justify a kill. If your objection depends on a specific remembered numeric value you "
    "cannot cite from a provided snippet (you have none), that objection is by definition "
    "ADDRESSABLE, not fundamental — it goes to addressable_notes, never to "
    "fundamental_flaw. A kill (fundamental_flaw=true) must rest on a qualitative "
    "structural or logical defect in the core claim, not on a remembered number. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"assumptions": [{"assumption": "<one sentence>", '
    '"sub_assumptions": ["<one sentence each>", ...], '
    '"evaluation": "<one sentence: correct, or flawed and why>"}, '
    "... 2 to 5 such objects], "
    '"invalidating_elements": ["<one sentence each>", ... possibly empty], '
    '"addressable_notes": ["<one short note each>", ... possibly empty], '
    '"fundamental_flaw": true or false, '
    '"summary": "<one sentence>"}.'
)

OBSERVATION_REVIEW_SYSTEM_PROMPT = (
    "You are the observation-review unit of the Reflection stage in an autonomous "
    "research pipeline, reviewing ONE candidate hypothesis. You are given the hypothesis, "
    "pre-fetched literature snippets (each tagged with a ref id), and possibly prior "
    "observations from earlier runs (unverified model text — treat as leads, not "
    "established facts). FIND THE OBSERVATIONS YOURSELF: you have web search and web "
    "fetch, and the pre-fetched material is a starting point rather than the set of "
    "things that have been observed. Look for the actual measurements, benchmarks and "
    "reported anomalies in this area — a hypothesis is interesting precisely when it "
    "explains something real that the accepted account handles badly, and you cannot "
    "tell that from whatever a keyword search happened to return. Judge whether this "
    "hypothesis can account for and explain existing observations, and whether it is a "
    "SUPERIOR explanation for any of them compared to the accepted one. Cite each "
    "observation so a human can find it.Reply ONLY with JSON of "
    'the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"relevant_observations": ["<one sentence each, naming where it came from>", '
    "... possibly empty], "
    '"accounts_for": "yes", "partially" or "no", '
    '"assessment": "<one to three sentences>"}.'
)

SIMULATION_REVIEW_SYSTEM_PROMPT = (
    "You are the simulation-review unit of the Reflection stage in an autonomous research "
    "pipeline, reviewing ONE candidate hypothesis. Simulate the hypothesis's "
    "proposed mechanism step by step, as it would unfold in the kind of simulation that "
    "would test it, and surface the concrete scenarios in which it fails. YOU DO NOT HAVE "
    "TO DO THIS IN YOUR HEAD — you can run code. Where a quick calculation would settle "
    "whether the mechanism actually behaves as claimed (an order-of-magnitude estimate, a "
    "toy version of the dynamics, a check that the effect survives realistic parameter "
    "values), write it and run it, and let the result drive your assessment. A failure "
    "scenario you demonstrated is worth more than one you imagined. Reply ONLY with "
    'JSON of the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"mental_simulation": ["<one step, one sentence>", ... 3 to 8 steps], '
    '"failure_scenarios": ["<one sentence each>", ... at most 5, possibly empty], '
    '"assessment": "<one sentence>"}.'
)

RECURRENT_TOURNAMENT_SYSTEM_PROMPT = (
    "You are the recurrent-tournament-review unit of the Reflection stage in an "
    "autonomous research pipeline, reviewing ONE candidate hypothesis. You are given "
    "the hypothesis and the previous round's tournament results, resolved to plain "
    "hypothesis statements: the final ranking and the matches played, with the "
    "judges' verdicts and reasons. From those results, note what tended to win or "
    "lose and why, and derive observations about how THIS hypothesis is likely to "
    "fare and the concerns it should carry into review and ranking. This review is "
    "ADVISORY: it informs the record; it does not discard anything. Reply ONLY with "
    'JSON of the form {"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"observations": ["<one sentence each>", ... at most 5, possibly empty], '
    '"carried_concerns": ["<one sentence each>", ... at most 5, possibly empty]}.'
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
    RAG and OpenAlex are REQUIRED — a failure there propagates (an honest
    stage failure that aborts the run; the kill-rate battery classifies it
    ABORTED and relaunches). OpenAlex is the PREFERRED novelty-grounding
    source (17-fix-B: it superseded arXiv, whose full-sentence all:-queries
    returned off-topic noise; hard-required by human ruling — grounding
    must fail loud, never silently thin out). A zero-hit OpenAlex [] is a
    valid outcome (no relevant citations found), not a failure. arXiv,
    Semantic Scholar and web search are best-effort: a RuntimeError from
    any is recorded in the evidence and retrieval proceeds without that
    source. Every record is already bounded by its wrapper (snippet caps);
    nothing raw exists at this layer. web_search is the one tool that
    needs run_id — its own transcript is written before its call fires.
    Ref ids R1..Rn are scoped to this hypothesis's reviews; the evidence
    dict is stored under the hypothesis's entry in reflection_reviews.json
    rather than a separate file per hypothesis.
    """
    query = hypothesis["statement"]
    corpus_records = [
        {"source": r["source"], "title": r["title"], "snippet": r["snippet"]}
        for r in search_index("literature", query, top_k=TOP_K_PER_SOURCE)
    ]
    # THE KEYWORD-API PRE-FETCH IS RETIRED HERE TOO (2026-07-25), and this path
    # was the worse offender: it ran PER HYPOTHESIS, so a 16-hypothesis pool paid
    # the throttled retries sixteen times over. The reviewer searches the
    # literature itself now (see FULL_REVIEW_SYSTEM_PROMPT) — better grounding,
    # and none of the latency. Evidence keys kept so the file's shape is stable.
    openalex_records: list = []
    arxiv_records: list = []
    s2_records: list = []
    arxiv_evidence: list | dict = _RETIRED_SOURCE
    s2_evidence: list | dict = _RETIRED_SOURCE

    # The web_search SUB-AGENT wrapper is RETIRED from this path (2026-07-25).
    # It existed because sealed stages held no tools, so a separate tool-holding
    # agent had to fetch results and hand back JSON snippets. The review units run
    # with FULL capabilities — they have WebSearch and WebFetch natively — so the
    # wrapper was an extra model call that could only lose information: in
    # study-20260725T073215Z it returned prose instead of JSON and silently
    # deleted an entire literature source. The reviewer now searches directly,
    # which is strictly better (it can follow up, refine the query, and read the
    # paper). The deterministic API sources above stay as a cheap starting point.
    web_records: list = []
    web_evidence: list | dict = {
        "note": "retired: the review agent searches the web itself (FULL tools)"
    }

    combined_refs = [
        {"ref": f"R{n}", **record}
        for n, record in enumerate(
            [*corpus_records, *openalex_records, *arxiv_records, *s2_records, *web_records],
            start=1,
        )
    ]

    evidence = {
        "query": query,
        "corpus": corpus_records,
        "openalex": _RETIRED_SOURCE,
        "arxiv": arxiv_evidence,
        "semantic_scholar": s2_evidence,
        "web": web_evidence,
        "combined_refs": combined_refs,
    }
    _log(
        run_id,
        f"STAGE1_REFLECTION_RETRIEVAL {hypothesis['id']} corpus={len(corpus_records)} "
        # Retired sources rendered as "error" here too — nothing ran, nothing
        # failed. See the note in generation_strategies' equivalent line.
        f"(keyword APIs retired; the reviewer searches the web itself) "
        f"-> {len(combined_refs)} pre-fetched refs",
    )
    return combined_refs, evidence


# --- Review 1: initial review (fast gate, NO external tools) -----------------


def initial_review(
    run_id: str, domain: str, hypotheses: list[dict], feedback_block: str | None = None
) -> list[dict]:
    """ONE Haiku call over the whole pool, no literature retrieval: quick
    pass/discard per candidate on correctness / quality / novelty /
    preliminary safety. Returns one {id, verdict, reason} per candidate; the
    validator enforces exactly one review per pool id, inside the re-ask
    loop. feedback_block (Step 17-E) is the composed meta-review feedback
    text, attached as its own input field when present. Step 18.5: the last
    3 learned_summary journal entries ride along as a prior_dead_ends block
    (deterministic journal read, zero added model calls) so re-proposed dead
    ends are discarded citing the journal entry."""
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
            # promise is a SOFT ranking signal, so it is validated when present
            # and defaulted when absent. Hard-requiring it would burn the whole
            # 3-attempt re-ask budget over a field that only orders a queue —
            # the funnel still caps correctly without it, it just falls back to
            # pool order.
            promise = r.get("promise")
            if promise is not None and (
                    isinstance(promise, bool) or not isinstance(promise, int)
                    or not 1 <= promise <= 5):
                errors.append(
                    f"review for {r.get('id')!r} has promise={promise!r}; it must "
                    "be an integer from 1 to 5, or omitted.")
            if r.get("verdict") not in ("pass", "discard"):
                errors.append(f"entry {n} verdict must be 'pass' or 'discard'.")
            reason = r.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"entry {n} reason must be a non-empty string.")
        if not errors and sorted(seen) != sorted(valid_ids):
            errors.append("reviews must cover every candidate id exactly once.")
        return errors

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "candidates": [
            {"id": h["id"], "statement": h["statement"], "rationale": h["rationale"]}
            for h in hypotheses
        ],
    }
    if feedback_block is not None:
        stage_input["meta_review_feedback"] = feedback_block
    # Step 18.5: dead-end check rides this existing call. Retrieval happens
    # HERE (not per hypothesis, not a new call) so every initial-review site
    # — reflect_on_pool AND Evolution's variant review — gets it for free.
    dead_end_entries = journal_recent_by_kind(
        DEAD_END_RETRIEVAL_KIND, DEAD_END_RETRIEVAL_LIMIT
    )
    dead_end_block = build_dead_end_block(dead_end_entries)
    if dead_end_block is not None:
        stage_input["prior_dead_ends"] = dead_end_block
    _log(
        run_id,
        f"STAGE1_DEADENDS {len(dead_end_entries)} journal dead-end entries "
        "provided to initial review",
    )
    data, timing = call_stage_model(
        "stage1_reflection_initial",
        INITIAL_REVIEW_SYSTEM_PROMPT,
        stage_input,
        {"required": ["ack_run_id", "reviews"]},
        model=SONNET_MODEL,
        extra_validator=validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, "initial_review")
    log_stage_call(run_id, "stage1_reflection_initial", timing)
    return [
        {"id": r["id"], "verdict": r["verdict"], "reason": r["reason"],
         "promise": r.get("promise", 3)}
        for r in data["reviews"]
    ]


# --- Review 2: full review (grounded correctness/quality/novelty) ------------


def full_review(
    run_id: str,
    domain: str,
    hypothesis: dict,
    refs: list[dict],
    feedback_block: str | None = None,
) -> dict:
    """One Haiku call per survivor WITH the retrieved snippets: the grounded
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
            # A citation is EITHER a provided ref id OR a source the reviewer
            # located itself, given as something a human can check (URL, DOI,
            # arXiv id). Rejecting anything outside the pre-fetched refs — as this
            # did until 2026-07-25 — WAS the cage: it forced 'novel' whenever the
            # keyword APIs missed, which is how a claim whose prior art dates to
            # the 1970s passed review with cited_refs None.
            unusable = [r for r in grounded if not _is_checkable_citation(r, valid_refs)]
            if unusable:
                errors.append(
                    f"novelty_grounded_in entries {unusable} are not checkable; each "
                    f"must be one of the provided ref ids {sorted(valid_refs)} OR a "
                    "source you actually located, cited so a human can find it "
                    "(a URL, a DOI, or an arXiv id)."
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

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_id": hypothesis["id"],
        "hypothesis_statement": hypothesis["statement"],
        "hypothesis_rationale": hypothesis["rationale"],
        "literature_snippets": refs,
    }
    if feedback_block is not None:
        stage_input["meta_review_feedback"] = feedback_block
    data, timing = call_stage_model(
        f"stage1_reflection_full_{hypothesis['id']}",
        compose_full_review_prompt(),
        stage_input,
        {
            "required": [
                "ack_run_id", "hypothesis_id", "novelty", "novelty_rationale",
                "novelty_grounded_in", "critique", "quality",
            ],
            "enums": {"novelty": ["novel", "known"]},
        },
        model=SONNET_MODEL,
        extra_validator=validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, f"full_review {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"full_review {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_full_{hypothesis['id']}", timing)
    return {
        "novelty": data["novelty"],
        # Absent => False: a review that does not assert the answer is on record
        # has not established that it is. Defaulting the other way would let a
        # missing field silently kill a hypothesis.
        "answer_established": bool(data.get("answer_established")),
        "novelty_rationale": data["novelty_rationale"],
        "novelty_grounded_in": data["novelty_grounded_in"],
        "critique": data["critique"],
        "quality": data["quality"],
    }


# --- Review 3: deep verification review ---------------------------------------


def deep_verification_review(
    run_id: str, domain: str, hypothesis: dict, feedback_block: str | None = None
) -> dict:
    """One Sonnet call per survivor, no retrieval: assumptions decomposed
    into sub-assumptions, each evaluated; invalidating elements named and
    classified fundamental-vs-addressable (Step 17-fix-A) — fundamental
    elements set fundamental_flaw, addressable ones land in
    addressable_notes and are never fatal; an objection resting on a
    remembered numeric value the model cannot cite is by definition
    addressable (the constant guard). The orchestrator (deterministic
    Python) discards on fundamental_flaw=true."""

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
        if not _is_str_list(data.get("addressable_notes")):
            errors.append(
                "addressable_notes must be a list of non-empty strings (possibly empty)."
            )
        if not isinstance(data.get("fundamental_flaw"), bool):
            errors.append("fundamental_flaw must be true or false.")
        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append("summary must be a non-empty string.")
        return errors

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_id": hypothesis["id"],
        "hypothesis_statement": hypothesis["statement"],
        "hypothesis_rationale": hypothesis["rationale"],
    }
    if feedback_block is not None:
        stage_input["meta_review_feedback"] = feedback_block
    data, timing = call_stage_model(
        f"stage1_reflection_deepverify_{hypothesis['id']}",
        DEEP_VERIFICATION_SYSTEM_PROMPT,
        stage_input,
        {"required": ["ack_run_id", "hypothesis_id", "assumptions",
                      "invalidating_elements", "addressable_notes",
                      "fundamental_flaw", "summary"]},
        model=DEEP_VERIFY_MODEL,
        extra_validator=validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, f"deep_verification {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"deep_verification {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_deepverify_{hypothesis['id']}", timing)
    return {
        "assumptions": data["assumptions"],
        "invalidating_elements": data["invalidating_elements"],
        "addressable_notes": data["addressable_notes"],
        "fundamental_flaw": data["fundamental_flaw"],
        "summary": data["summary"],
    }


# --- Review 4: observation review ---------------------------------------------


def observation_review(
    run_id: str,
    domain: str,
    hypothesis: dict,
    refs: list[dict],
    memory_block: str | None,
    feedback_block: str | None = None,
) -> dict:
    """One Haiku call per survivor: can the hypothesis account for existing
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
    if feedback_block is not None:
        stage_input["meta_review_feedback"] = feedback_block
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
        capabilities=FULL,
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


def simulation_review(
    run_id: str, domain: str, hypothesis: dict, feedback_block: str | None = None
) -> dict:
    """One Haiku call per survivor, no retrieval: step-wise mental
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

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_id": hypothesis["id"],
        "hypothesis_statement": hypothesis["statement"],
        "hypothesis_rationale": hypothesis["rationale"],
    }
    if feedback_block is not None:
        stage_input["meta_review_feedback"] = feedback_block
    data, timing = call_stage_model(
        f"stage1_reflection_simulation_{hypothesis['id']}",
        SIMULATION_REVIEW_SYSTEM_PROMPT,
        stage_input,
        {"required": ["ack_run_id", "hypothesis_id", "mental_simulation",
                      "failure_scenarios", "assessment"]},
        model=SONNET_MODEL,
        extra_validator=validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, f"simulation_review {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"simulation_review {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_simulation_{hypothesis['id']}", timing)
    return {
        "mental_simulation": data["mental_simulation"],
        "failure_scenarios": data["failure_scenarios"],
        "assessment": data["assessment"],
    }


# --- Review 6: recurrent / tournament review (ACTIVE since Step 17-E) ---------


def recurrent_tournament_review(
    run_id: str, hypothesis: dict, tournament_state: dict | None = None
) -> dict:
    """Review 6 — recurrent/tournament review, ACTIVE since Step 17-E.

    tournament_state is the PRIOR ROUND's tournament results, already
    resolved to plain hypothesis statements by the iteration controller
    (stage1_ideation.resolve_tournament_to_statements) — raw cross-round
    ids must never reach this context, because canonical ids are
    reassigned every round. When present, ONE Haiku call derives advisory
    observations and carried concerns for this hypothesis from what won
    and lost last round and why. ADVISORY ONLY: the output is recorded in
    the reflection evidence and feeds no deterministic consequence — the
    kill filter never reads it. When tournament_state is None (round 1 of
    a run, or a prior round whose ranking was trivial so no matches were
    played) the unit is inert and makes NO model call.
    """
    if tournament_state is None:
        return {
            "status": "inert",
            "reason": (
                "no prior-round tournament results exist to review against "
                "(first round of this run, or the prior round ranked trivially)"
            ),
        }

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        for field in ("observations", "carried_concerns"):
            value = data.get(field)
            if not _is_str_list(value) or (isinstance(value, list) and len(value) > 5):
                errors.append(
                    f"{field} must be a list of at most 5 non-empty strings "
                    "(possibly empty)."
                )
        return errors

    data, timing = call_stage_model(
        f"stage1_reflection_tournament_{hypothesis['id']}",
        RECURRENT_TOURNAMENT_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "hypothesis_id": hypothesis["id"],
            "hypothesis_statement": hypothesis["statement"],
            "hypothesis_rationale": hypothesis["rationale"],
            "prior_tournament_results": tournament_state,
        },
        {"required": ["ack_run_id", "hypothesis_id", "observations", "carried_concerns"]},
        model=REVIEW6_MODEL,
        extra_validator=validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, f"tournament_review {hypothesis['id']}")
    _check_hypothesis_id(
        data, run_id, hypothesis["id"], f"tournament_review {hypothesis['id']}"
    )
    log_stage_call(run_id, f"stage1_reflection_tournament_{hypothesis['id']}", timing)
    _log(
        run_id,
        f"STAGE1_REVIEW6 {hypothesis['id']}: observations={len(data['observations'])} "
        f"carried_concerns={len(data['carried_concerns'])}",
    )
    return {
        "status": "active",
        "observations": data["observations"],
        "carried_concerns": data["carried_concerns"],
    }


# --- Orchestrator ---------------------------------------------------------------


# How many hypotheses are reviewed at once. Bounded: each worker holds a model
# call that may itself run an agentic tool loop, so an unbounded pool would
# hammer the transport and blow a rate-limit window in seconds. Override with
# RESEARCH_REVIEW_CONCURRENCY when a bigger pool warrants it.
# How many candidates get the EXPENSIVE review chain. Each survivor costs four
# separate agentic model calls, so this is the single biggest lever on ideation
# cost — bigger than pool size, which is cheap to generate and expensive only
# because everything generated was being deep-reviewed.
# ---------------------------------------------------------------------------
# SCRUTINY — deep verification + observation + simulation in ONE call.
#
# OWNER RULING 2026-07-27: "having 4 agentic calls for each hypothesis is a bit
# weird. the whole point is to have more hypotheses, i'd rather reduce the
# filtration part and get more hypotheses."
#
# Right, and the old shape was backwards. Generating hypotheses is CHEAP — seven
# calls produce the whole pool, and the bulk triage reads all of them in ONE
# call, so a pool of 100 costs barely more to screen than a pool of 25. What was
# expensive was FOUR separate agentic sessions per surviving candidate, which
# made breadth cost linearly and capped the pool at a size that defeated the
# purpose.
#
# These three reviews all reason about the SAME hypothesis and, unlike the full
# review, none of them needs literature retrieval — deep verification runs
# without it by design (so an objection resting on a remembered value is
# addressable, never a kill), and the other two reason from the hypothesis
# itself. Three separate contexts bought separation that a single call with
# three labelled sections gives just as well, at a third of the cost.
#
# The sub-shapes are UNCHANGED, so everything downstream — the deterministic
# fundamental_flaw kill, addressable_notes, the evidence file — reads exactly
# what it always did.
# ---------------------------------------------------------------------------

SCRUTINY_SYSTEM_PROMPT = (
    "You are the scrutiny unit of the Reflection stage in an autonomous research "
    "pipeline, examining ONE candidate hypothesis from three angles in a single "
    "pass. Do all three; they are separate judgments and must not blur into each "
    "other.\n\n"
    "1. DEEP VERIFICATION. Decompose the hypothesis into its constituent "
    "assumptions, break each into sub-assumptions, and evaluate each for "
    "correctness. Identify anything that would invalidate it. Classify every "
    "objection as FUNDAMENTAL (the core claim cannot survive it — this discards "
    "the hypothesis) or ADDRESSABLE (a detail, or something the experiment "
    "itself would resolve). You have no retrieved literature here, so an "
    "objection resting on a remembered numeric value is by definition "
    "ADDRESSABLE, never a kill.\n\n"
    "2. OBSERVATIONS. Can this hypothesis account for observations that already "
    "exist, and is it a SUPERIOR explanation for any of them than the accepted "
    "account? You may search the web to find what has actually been measured in "
    "this area — a hypothesis is interesting precisely when it explains "
    "something real the accepted account handles badly, and you cannot tell that "
    "without looking. Cite each observation so a human can find it.\n\n"
    "3. SIMULATION. Walk the proposed mechanism step by step as it would unfold "
    "in the experiment that would test it, and surface the concrete scenarios "
    "where it fails. You can run code: where a quick calculation would settle "
    "whether the mechanism behaves as claimed, write it and run it. A failure "
    "scenario you demonstrated is worth more than one you imagined.\n\n"
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"deep_verification": {"assumptions": [{"assumption": "<one sentence>", '
    '"sub_assumptions": ["<one sentence>", ...], "evaluation": "<correct, '
    'uncertain, or wrong, and why>"}, ...], "invalidating_elements": '
    '["<one sentence each>", ...], "addressable_notes": ["<one sentence each>", '
    '...], "fundamental_flaw": <true|false>, "summary": "<one to three '
    'sentences>"}, '
    '"observation": {"relevant_observations": ["<one sentence each, naming where '
    'it came from>", ...], "accounts_for": "yes" or "partially" or "no", '
    '"assessment": "<one to three sentences>"}, '
    '"simulation": {"mental_simulation": ["<one step each>", ...], '
    '"failure_scenarios": ["<one sentence each>", ...], "assessment": "<one to '
    'three sentences>"}}.'
)


def _validate_scrutiny(data: dict) -> list:
    """Structural only: each section must carry the fields its consumers read.
    The fundamental_flaw boolean is load-bearing — it drives a deterministic
    discard — so it is required rather than defaulted."""
    errors: list[str] = []
    deep = data.get("deep_verification")
    if not isinstance(deep, dict):
        errors.append("'deep_verification' must be an object.")
    else:
        if not isinstance(deep.get("fundamental_flaw"), bool):
            errors.append("deep_verification.fundamental_flaw must be true or false.")
        if not str(deep.get("summary") or "").strip():
            errors.append("deep_verification.summary must be a non-empty string.")
        for key in ("assumptions", "invalidating_elements", "addressable_notes"):
            if not isinstance(deep.get(key), list):
                errors.append(f"deep_verification.{key} must be a list.")
    obs = data.get("observation")
    if not isinstance(obs, dict):
        errors.append("'observation' must be an object.")
    elif obs.get("accounts_for") not in ("yes", "partially", "no"):
        errors.append("observation.accounts_for must be yes, partially or no.")
    sim = data.get("simulation")
    if not isinstance(sim, dict):
        errors.append("'simulation' must be an object.")
    else:
        for key in ("mental_simulation", "failure_scenarios"):
            if not isinstance(sim.get(key), list):
                errors.append(f"simulation.{key} must be a list.")
    return errors


def scrutiny_review(run_id: str, domain: str, hypothesis: dict,
                    memory_block: str | None = None,
                    feedback_block: str | None = None) -> dict:
    """One call replacing deep_verification + observation + simulation. Returns
    the three sub-objects under their original keys, so every downstream reader
    is untouched."""
    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_id": hypothesis["id"],
        "hypothesis_statement": hypothesis["statement"],
        "hypothesis_rationale": hypothesis["rationale"],
    }
    if memory_block is not None:
        stage_input["prior_observations"] = memory_block
    if feedback_block is not None:
        stage_input["meta_review_feedback"] = feedback_block

    data, timing = call_stage_model(
        f"stage1_reflection_scrutiny_{hypothesis['id']}",
        SCRUTINY_SYSTEM_PROMPT,
        stage_input,
        {"required": ["ack_run_id", "hypothesis_id", "deep_verification",
                      "observation", "simulation"]},
        model=DEEP_VERIFY_MODEL,
        extra_validator=_validate_scrutiny,
        capabilities=FULL,
    )
    _check_ack(data, run_id, f"scrutiny {hypothesis['id']}")
    _check_hypothesis_id(data, run_id, hypothesis["id"], f"scrutiny {hypothesis['id']}")
    log_stage_call(run_id, f"stage1_reflection_scrutiny_{hypothesis['id']}", timing)
    deep = dict(data["deep_verification"])
    deep.setdefault("addressable_notes", [])
    return {"deep_verification": deep,
            "observation": data["observation"],
            "simulation": data["simulation"]}


def _max_deep_review() -> int:
    raw = os.environ.get("RESEARCH_DEEP_REVIEW_MAX", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return 6


def _review_concurrency() -> int:
    raw = os.environ.get("RESEARCH_REVIEW_CONCURRENCY", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return min(int(raw), 16)
    return 6


def _review_pool_concurrently(run_id: str, survivors: list, review_one) -> list:
    """Review every survivor concurrently, returning results IN POOL ORDER so
    evidence files and logs stay deterministic regardless of completion order.

    A hypothesis whose review chain raises does not take the pool down with it:
    the exception is re-raised here, once, after the pool drains — the same
    honest-failure discipline the rest of the system uses, but without leaving
    other workers running into a half-torn state."""
    if len(survivors) <= 1:
        return [review_one(h) for h in survivors]

    from concurrent.futures import ThreadPoolExecutor

    workers = min(_review_concurrency(), len(survivors))
    try:
        _log(run_id,
             f"STAGE1_REFLECTION reviewing {len(survivors)} hypotheses "
             f"{workers} at a time")
    except OSError:
        pass          # a progress line must never sink the pool it describes
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(review_one, h) for h in survivors]
        return [f.result() for f in futures]


def reflect_on_pool(
    run_id: str,
    domain: str,
    hypotheses: list[dict],
    memory_block: str | None,
    run_dir: Path,
    tournament_state: dict | None = None,
    feedback_block: str | None = None,
) -> tuple[list[dict], dict]:
    """Apply the six review types to the candidate pool, in the paper's
    sequence: the cheap no-tools initial review gates first, then each
    survivor gets per-hypothesis retrieval plus the full / deep-verification
    / observation / simulation reviews and — when the iteration controller
    supplies the prior round's statement-resolved tournament results — the
    recurrent/tournament review (advisory only; inert on round 1 or after a
    trivial prior ranking). feedback_block (Step 17-E) is the composed
    meta-review feedback text for the reflection family, attached to all
    five reviewing calls' inputs. Deterministic consequences, no model in
    them:
      - initial verdict 'discard' → candidate exits before any tool spend;
      - deep verification fundamental_flaw=true → candidate exits;
      - everything else becomes a reflection {hypothesis_id, novelty,
        critique, quality, addressable_notes} — novelty/critique/quality
        from the grounded full review are exactly the fields the existing
        downstream filter consumes; addressable_notes (Step 17-fix-A)
        carries deep verification's non-fatal concerns with the survivor
        as Stage-1 evidence and never crosses gate 1.
    All evidence — per-candidate initial verdicts, per-hypothesis retrieval
    records, all review outputs, both discard lists, and the final
    reflections — is saved to runs/<run_id>/stage1/reflection_reviews.json.
    Returns (reflections, summary counts). Raises RuntimeError when zero
    candidates survive reviewing — an honest halt, never padded.
    """
    if tournament_state is None:
        _log(
            run_id,
            "STAGE1_REVIEW6 inert — no prior-round tournament results to review against",
        )
    initial = initial_review(run_id, domain, hypotheses, feedback_block)
    verdict_by_id = {r["id"]: r for r in initial}
    passed = [h for h in hypotheses if verdict_by_id[h["id"]]["verdict"] == "pass"]
    # THE GATE MUST ACTUALLY GATE (2026-07-27). Measured: it passed 21 of 25 and
    # 11 of 16 — 84% and 69%, which is a formality, not triage. Every survivor
    # then costs FOUR separate agentic model calls (full, deep-verify,
    # observation, simulation), so a pool of 25 queued ~84 review calls per
    # round; at ~127 s each that was four hours of reflection. The expensive
    # chain is for CANDIDATES WORTH IT, so the initial review now also scores
    # promise and only the top MAX_DEEP_REVIEW proceed. The rest are recorded as
    # triaged — kept in the evidence, never silently dropped.
    survivors = sorted(
        passed, key=lambda h: (-verdict_by_id[h["id"]].get("promise", 3),
                               [c["id"] for c in hypotheses].index(h["id"])),
    )[:_max_deep_review()]
    triaged = [verdict_by_id[h["id"]] for h in passed if h not in survivors]
    if triaged:
        _log(run_id,
             f"STAGE1_REFLECTION triage: {len(survivors)} of {len(passed)} passing "
             f"candidates get the full review chain; {len(triaged)} held back as "
             "lower promise (recorded, not discarded)")
    discarded_initial = [
        verdict_by_id[h["id"]] for h in hypotheses
        if verdict_by_id[h["id"]]["verdict"] == "discard"
    ]
    _log(
        run_id,
        f"STAGE1_REFLECTION initial review: {len(survivors)} of {len(hypotheses)} "
        "candidates passed the no-tools gate",
    )

    def _review_one(h: dict) -> dict:
        """Every review of ONE hypothesis. Nothing here reads another
        hypothesis's result, which is what makes the pool parallelisable."""
        refs, retrieval_evidence = gather_review_refs(run_id, h)
        scrutiny = scrutiny_review(run_id, domain, h, memory_block, feedback_block)
        return {
            "hypothesis_id": h["id"],
            "retrieval": retrieval_evidence,
            "full_review": full_review(run_id, domain, h, refs, feedback_block),
            "deep_verification": scrutiny["deep_verification"],
            "observation": scrutiny["observation"],
            "simulation": scrutiny["simulation"],
            "tournament": recurrent_tournament_review(run_id, h, tournament_state),
        }

    # REVIEW THE POOL CONCURRENTLY (2026-07-27). Measured on a live run: 157
    # ideation calls at a mean of 127 SECONDS each, entirely serial — a pool of
    # 25 over 2 rounds is ~200 review calls, so ideation alone was heading for
    # eight hours before a single experiment ran. Each hypothesis's reviews are
    # independent of every other hypothesis's, so the whole pool is
    # embarrassingly parallel and nothing was exploiting it. This is what made
    # "buy a bigger pool" cost wall-clock linearly.
    #
    # Threads, not processes: these calls are I/O-bound on the model transport,
    # and the same pattern is already used by run_study_fan. Order is restored
    # afterwards so evidence and logs stay deterministic in pool order.
    ordered = _review_pool_concurrently(run_id, survivors, _review_one)

    reflections: list[dict] = []
    discarded_fundamental: list[dict] = []
    reviews_evidence: list[dict] = list(ordered)
    for h, ev in zip(survivors, ordered):
        full = ev["full_review"]
        deep = ev["deep_verification"]
        observation = ev["observation"]
        simulation = ev["simulation"]
        _log(
            run_id,
            f"STAGE1_REFLECTION {h['id']}: novelty={full['novelty']} "
            f"answer_established={full.get('answer_established')} "
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
                # The filter kills on THIS, not on novelty: a known method
                # applied where nobody has measured the answer is a good
                # hypothesis (see FULL_REVIEW_SYSTEM_PROMPT).
                "answer_established": full.get("answer_established", False),
                "critique": full["critique"],
                "quality": int(full["quality"]),
                # Step 17-fix-A: deep verification's non-fatal concerns
                # travel with the survivor (Stage-1 evidence only — the
                # payload hypotheses are rebuilt {id, statement, rationale}
                # downstream, so this never crosses gate 1).
                "addressable_notes": deep["addressable_notes"],
            }
        )

    evidence = {
        "pool_size": len(hypotheses),
        "initial_review": initial,
        "initial_survivor_count": len(survivors),
        "triaged_lower_promise": triaged,
        "discarded_by_initial_review": discarded_initial,
        "reviews": reviews_evidence,
        "discarded_by_deep_verification": discarded_fundamental,
        "tournament_review_status": (
            "inert — no prior-round tournament results "
            "(first round, or the prior round ranked trivially)"
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
