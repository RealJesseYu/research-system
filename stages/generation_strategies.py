"""
generation_strategies.py — the four Co-Scientist generation strategies for
the Step-17 Ideation rebuild. Called only by stages/stage1_ideation.py's
Generation portion; everything downstream of Generation (Reflection, the
deterministic filter, Ranking) is untouched and lives in stage1_ideation.py.

The four strategies (faithful to the Co-Scientist Generation agent):
  1. literature_exploration — hypotheses grounded in retrieved literature:
     the local corpus RAG plus LIVE arXiv (required), Semantic Scholar and
     web search (optional-preferred; their failures are recorded honestly
     and the strategy proceeds on the remaining sources).
  2. simulated_debate — a bounded multi-turn self-play exchange among
     simulated expert personas that converges on ONE refined hypothesis.
     This is a hypothesis-refinement engine, NOT the Ranking tournament.
  3. assumptions_identification — name testable intermediate assumptions
     via conditional reasoning, then aggregate them into hypotheses.
  4. research_expansion — review the run's existing candidates and steer
     toward unexplored directions. Prior feedback (Step 17-E: the
     meta_review_feedback parameter, LIVE since the Meta-review agent
     exists) is the composed feedback text block from the prior round's
     meta-review — code-framed for selective use and carrying the prior
     round's research-overview directions — attached to every strategy
     call's input; round 1 receives an explicit empty block.

Discipline preserved:
  - Every model call is Haiku through call_stage_model (Step 18.7
    downgrade: Generation is volume work, not a hard judgment) — same
    door, same isolation, same bounded re-ask loop, same
    write-before-call transcripts.
  - Summarize-at-the-wrapper: only the retrieval tools' bounded records
    ever enter a model input; no raw tool output exists at this layer.
  - Live-search non-determinism is answered by evidence, not mechanism:
    every retrieved record a run used is saved verbatim under
    runs/<run_id>/stage1/ (retrieved_literature.json, debate.json,
    assumptions.json, the pooled generation.json, and — Step 17-fix-A —
    generation_number_signals.json, the warn-only record of unsupported
    numeric literals in strategy 1's accepted hypotheses).
  - Journal-poison ruling: any memory content arrives already framed as
    leads-not-facts (MEMORY_HEADER, built by stage1_ideation) and is
    passed through unchanged — never elevated to fact here.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

import cost_meter
from model_call import call_stage_model, log_stage_call
from substrates import CAVITY_2D_CONTRACT

_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
if str(_RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_DIR))

from scholar_search import search_arxiv, search_openalex, search_semantic_scholar  # noqa: E402
from search import search_index  # noqa: E402
from web_search import web_search  # noqa: E402

# Step 18.7 downgrade: all four Generation strategies run on Haiku (the
# Sonnet proving batch locked the baseline; the kill-rate/k battery is the
# quality signal for this move).
HAIKU_MODEL = "claude-haiku-4-5-20251001"

TOP_K_PER_SOURCE = 3

# --- R-WIN-1 (R-14-N1): feasibility-nudge seam, PLUMBING (default off).
# When FEASIBILITY_NUDGE=on, a FEASIBILITY NUDGE block is attached to EVERY
# Generation strategy that composes a generation prompt: literature_exploration
# and research_expansion (the two steering strategies, where memory_block also
# rides) AND simulated_debate + assumptions_identification (extended in the
# 19-lite/retry build per the R-WIN-1 nudge-seam audit — the nudge is about
# instrument feasibility, not journal memory, so unlike memory_block it is not
# scoped to strategies 1 and 4; a nudge that skipped half the pool would leave
# those hypotheses free to keep drifting infeasible). Body = the imported
# CAVITY_2D_CONTRACT (single source of truth) + the most recent failure memo
# for this run when one exists + one instruction sentence. With the switch off
# no feasibility_nudge field is added, so composed inputs are byte-identical to
# today's. The retry-on-total-defer path (supervisor.py) forces the switch on
# for a single retried ideation pass; env is restored after.
FEASIBILITY_NUDGE_ENV = "FEASIBILITY_NUDGE"
FEASIBILITY_NUDGE_HEADER = "FEASIBILITY NUDGE"
FEASIBILITY_NUDGE_INSTRUCTION = "Prefer hypotheses this instrument can test as-is."
FEASIBILITY_MEMO_CAP = 2000


def _feasibility_nudge_on() -> bool:
    """R-WIN-1 switch: env FEASIBILITY_NUDGE == 'on' turns the nudge on;
    anything else (unset, 'off') leaves it off. Read at call time."""
    return os.environ.get(FEASIBILITY_NUDGE_ENV, "off") == "on"


def read_recent_failure_memo(run_id: str) -> str | None:
    """Best-effort read of the most recent failure memo for this run, if one
    exists (runs/<run_id>/*failure_memo*.txt, newest by mtime, length-capped).
    No producer writes this file this session — the AUTO wiring rides the
    frozen supervisor's retry-toggle build — so on a live run today this
    returns None; the seam is here so a future producer only drops a file."""
    try:
        memos = sorted(
            (Path("runs") / run_id).glob("*failure_memo*.txt"),
            key=lambda p: p.stat().st_mtime,
        )
        if not memos:
            return None
        text = memos[-1].read_text().strip()
        return text[:FEASIBILITY_MEMO_CAP] if text else None
    except Exception:
        return None


def build_feasibility_nudge(run_id: str) -> str:
    """The FEASIBILITY NUDGE block: header + the imported CAVITY_2D_CONTRACT
    (single source of truth) + the most recent failure memo for this run when
    one exists + one instruction sentence to prefer as-is-testable hypotheses."""
    parts = [FEASIBILITY_NUDGE_HEADER + ":", CAVITY_2D_CONTRACT]
    memo = read_recent_failure_memo(run_id)
    if memo:
        parts.append("MOST RECENT FAILURE MEMO FOR THIS RUN:\n" + memo)
    parts.append(FEASIBILITY_NUDGE_INSTRUCTION)
    return "\n\n".join(parts)

# Per-strategy candidate counts. Pool = 4 + 1 + 3 + 2 = 10 candidates.
LITERATURE_HYPOTHESIS_COUNT = 4
ASSUMPTION_HYPOTHESIS_COUNT = 3
EXPANSION_HYPOTHESIS_COUNT = 2

# Simulated debate: HARD CAP of one turn per persona, in this order; the
# final persona's hypothesis is the debate's converged result.
DEBATE_PERSONAS = (
    "theorist — argues from physical mechanisms and first principles",
    "computational scientist — argues from what a simulation can actually resolve and measure",
    "skeptical reviewer — attacks weak assumptions and pushes for a sharper, more falsifiable claim",
)
DEBATE_TURNS = len(DEBATE_PERSONAS)  # hard cap: 3 turns, never more

# Step 17-fix-A: shared no-invented-numbers instruction, appended to every
# hypothesis-producing strategy prompt. The chunk-4a diagnostic showed
# Generation inventing quantitative claims no retrieved snippet supports —
# and those invented specifics are exactly what deep verification then
# executes on.
NO_INVENTED_NUMBERS_INSTRUCTION = (
    "Do NOT state a specific numeric value (an exponent, threshold, ratio, percentage, or "
    "dimensioned constant) unless that exact value appears in one of the provided literature "
    "snippets and you cite its ref id. If you have no snippet for a number, express the "
    "claim qualitatively or directionally (e.g. 'increases with', 'is smaller than') instead "
    "of inventing a figure. A hypothesis with no supporting snippet must remain qualitative. "
)

# Loose numeric-literal extraction for strategy 1's WARN-ONLY scan (Step
# 17-fix-A). Matches plain integers/decimals ("1914", "0.036"), scientific
# notation ("1e-5", "3.6E-2"), and power-of-ten forms ("10^-5",
# "3.6 x 10^-2", "3.6×10^2"). A literal glued to a letter ("2D", "R3") is
# a label, not a numeric claim, and is skipped.
_PLAIN_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?!\w)")
_POWER_OF_TEN_RE = re.compile(r"(?:(\d+(?:\.\d+)?)\s*[x×*]\s*)?10\s*\^\s*([+-]?\d+)")


def _extract_numbers(text: str) -> set[float]:
    """Every numeric value stated in `text`, as floats. A value followed by
    '%' is recorded as its fraction (3.6% -> 0.036), so '3.6%' and '0.036'
    cross-match in either direction."""
    values: set[float] = set()
    power_spans: list[tuple[int, int]] = []
    for m in _POWER_OF_TEN_RE.finditer(text):
        mantissa = float(m.group(1)) if m.group(1) else 1.0
        values.add(mantissa * 10.0 ** int(m.group(2)))
        power_spans.append(m.span())
    for m in _PLAIN_NUMBER_RE.finditer(text):
        # skip literals that are part of a power-of-ten form (the "10" and
        # exponent digits of "10^-5" are not separate numeric claims)
        if any(start <= m.start() < end for start, end in power_spans):
            continue
        value = float(m.group(0))
        if text[m.end():m.end() + 1] == "%" or text[m.end():m.end() + 2] == " %":
            values.add(value / 100.0)
        else:
            values.add(value)
    return values


def _unsupported_numbers(statement: str, cited_texts: list[str]) -> list[float]:
    """The statement's numeric literals with no loose match in any cited
    snippet text. Deliberately tolerant (values compare within 0.1%
    relative, plus the '%' and power-of-ten normalizations above) so
    formatting differences do not fire the signal."""
    snippet_values: set[float] = set()
    for text in cited_texts:
        snippet_values |= _extract_numbers(text)
    return [
        v
        for v in sorted(_extract_numbers(statement))
        if not any(
            math.isclose(v, s, rel_tol=1e-3, abs_tol=1e-9) for s in snippet_values
        )
    ]


LITERATURE_SYSTEM_PROMPT = (
    "You are the literature-exploration generation strategy inside the Ideation stage of an "
    "autonomous research pipeline. You are given a research domain and literature snippets "
    "retrieved live for it, each tagged with a ref id. Propose exactly "
    f"{LITERATURE_HYPOTHESIS_COUNT} hypotheses that are grounded in those snippets without "
    "merely restating them, each one concrete enough to be tested by a simulation, and each "
    "citing the ref ids of the snippets that ground it. "
    + NO_INVENTED_NUMBERS_INSTRUCTION +
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "hypotheses": '
    '[{"statement": "<one sentence>", "rationale": "<one sentence>", '
    '"grounded_in": ["<ref id>", ...]}, '
    f"... exactly {LITERATURE_HYPOTHESIS_COUNT} such objects total]}}."
)

DEBATE_SYSTEM_PROMPT = (
    "You are one expert voice in a simulated scientific debate inside the Ideation stage of "
    "an autonomous research pipeline. The debate's purpose is to converge on ONE refined "
    "hypothesis for the given research domain. Adopt exactly the persona you are given. Read "
    "the literature snippets and the debate so far, then give your argument — agree, refute, "
    "or sharpen what came before — and your persona's current best version of the single "
    "hypothesis under debate, concrete enough to be tested by a simulation. On the final "
    "turn (turn number equals of_turns), your hypothesis is taken as the debate's converged "
    "result. "
    + NO_INVENTED_NUMBERS_INSTRUCTION +
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"argument": "<one to three sentences>", '
    '"hypothesis": {"statement": "<one sentence>", "rationale": "<one sentence>"}}.'
)

ASSUMPTIONS_IDENTIFY_SYSTEM_PROMPT = (
    "You are the assumptions-identification generation strategy inside the Ideation stage of "
    "an autonomous research pipeline. Given a research domain, reason conditionally about "
    "what would have to be true for interesting results to hold in it ('if X holds, then Y "
    "should be observable'), and name exactly 3 to 5 testable intermediate assumptions — "
    "each one checkable by a simulation. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "assumptions": '
    '[{"assumption": "<one sentence>", "testable_because": "<one sentence>"}, '
    "... 3 to 5 such objects total]}."
)

ASSUMPTIONS_AGGREGATE_SYSTEM_PROMPT = (
    "You are the assumptions-identification generation strategy inside the Ideation stage of "
    "an autonomous research pipeline. You are given a research domain and a numbered list of "
    "testable intermediate assumptions identified for it. Aggregate those assumptions into "
    f"exactly {ASSUMPTION_HYPOTHESIS_COUNT} complete hypotheses, each one concrete enough to "
    "be tested by a simulation, each building on one or more of the numbered assumptions and "
    "citing their numbers. "
    + NO_INVENTED_NUMBERS_INSTRUCTION +
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "hypotheses": '
    '[{"statement": "<one sentence>", "rationale": "<one sentence>", '
    '"built_on": [<assumption number>, ...]}, '
    f"... exactly {ASSUMPTION_HYPOTHESIS_COUNT} such objects total]}}."
)

EXPANSION_SYSTEM_PROMPT = (
    "You are the research-expansion generation strategy inside the Ideation stage of an "
    "autonomous research pipeline. You are given a research domain and the candidate "
    "hypotheses already generated this run by other strategies. Identify what directions "
    "within the domain those candidates have NOT explored, and propose exactly "
    f"{EXPANSION_HYPOTHESIS_COUNT} new hypotheses in unexplored directions, each one "
    "concrete enough to be tested by a simulation and clearly distinct from every existing "
    "candidate. "
    + NO_INVENTED_NUMBERS_INSTRUCTION +
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "hypotheses": '
    '[{"statement": "<one sentence>", "rationale": "<one sentence>", '
    '"unexplored_because": "<one sentence naming the gap this fills>"}, '
    f"... exactly {EXPANSION_HYPOTHESIS_COUNT} such objects total]}}."
)


def _log(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt.

    Mirrors stage1_ideation._log — the third place (after model_call.py and
    stage1_ideation.py) that rebuilds the run-log path from run_id alone;
    stages and their helpers never hold the supervisor's Logger object.
    """
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def _check_ack(data: dict, run_id: str, what: str) -> None:
    """Raise on ack_run_id mismatch; log the pass — same pattern as every
    existing stage-1 ack check."""
    if data["ack_run_id"] != run_id:
        raise RuntimeError(
            f"stage1 generation {what}: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {run_id!r}"
        )
    _log(run_id, f"STAGE1_ACK_CHECK generation {what}: ack_run_id passed")


def _entry_field_errors(entry, n: int, fields: tuple, errors: list[str]) -> bool:
    """Shared shape check: entry n must be an object whose `fields` are all
    non-empty strings. Returns False if entry is not even a dict."""
    if not isinstance(entry, dict):
        errors.append(f"entry {n} must be a JSON object.")
        return False
    for field in fields:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"entry {n} field {field!r} must be a non-empty string.")
    return True


def gather_literature_evidence(run_id: str, domain: str, run_dir: Path) -> list[dict]:
    """Retrieve bounded literature records for `domain` from all four
    sources, save them verbatim as evidence, and return the combined
    ref-tagged list the grounding strategies will see.

    Corpus RAG and OpenAlex are REQUIRED — a failure there propagates (an
    honest stage failure that aborts the run, never papered over; the
    kill-rate battery classifies it ABORTED and relaunches). OpenAlex is
    the PREFERRED novelty-grounding source (17-fix-B: it superseded arXiv,
    whose full-sentence all:-queries returned off-topic noise;
    hard-required by human ruling — grounding must fail loud, never
    silently thin out). A zero-hit OpenAlex [] is a valid outcome (no
    relevant citations found), not a failure. arXiv, Semantic Scholar and
    web search are best-effort: a RuntimeError from any is recorded in the
    evidence file and retrieval proceeds without that source (chunk-1
    proved S2's keyless pool 429s are a live failure mode). Every record
    is already bounded by its wrapper (snippet caps); nothing raw exists
    at this layer. web_search is the one tool that needs run_id — its own
    transcript is written before its call fires.
    """
    corpus_records = [
        {"source": r["source"], "title": r["title"], "snippet": r["snippet"]}
        for r in search_index("literature", domain, top_k=TOP_K_PER_SOURCE)
    ]
    openalex_records = search_openalex(domain, top_k=TOP_K_PER_SOURCE)

    try:
        arxiv_records = search_arxiv(domain, top_k=TOP_K_PER_SOURCE)
        arxiv_evidence: list | dict = arxiv_records
    except RuntimeError as e:
        arxiv_records = []
        arxiv_evidence = {"error": str(e)}
        _log(run_id, f"STAGE1_RETRIEVAL arxiv failed (recorded, proceeding): {str(e).splitlines()[0]}")

    try:
        s2_records = search_semantic_scholar(domain, top_k=TOP_K_PER_SOURCE)
        s2_evidence: list | dict = s2_records
    except RuntimeError as e:
        s2_records = []
        s2_evidence = {"error": str(e)}
        _log(run_id, f"STAGE1_RETRIEVAL semantic_scholar failed (recorded, proceeding): {str(e).splitlines()[0]}")

    try:
        web_records = web_search(domain, run_id=run_id, top_k=TOP_K_PER_SOURCE)
        web_evidence: list | dict = web_records
    except RuntimeError as e:
        web_records = []
        web_evidence = {"error": str(e)}
        _log(run_id, f"STAGE1_RETRIEVAL web_search failed (recorded, proceeding): {str(e).splitlines()[0]}")

    combined_refs = [
        {"ref": f"R{n}", **record}
        for n, record in enumerate(
            [*corpus_records, *openalex_records, *arxiv_records, *s2_records, *web_records],
            start=1,
        )
    ]

    evidence = {
        "query": domain,
        "corpus": corpus_records,
        "openalex": openalex_records,
        "arxiv": arxiv_evidence,
        "semantic_scholar": s2_evidence,
        "web": web_evidence,
        "combined_refs": combined_refs,
    }
    (run_dir / "retrieved_literature.json").write_text(json.dumps(evidence, indent=2))
    _log(
        run_id,
        f"STAGE1_RETRIEVAL corpus={len(corpus_records)} "
        f"openalex={len(openalex_records)} "
        f"arxiv={len(arxiv_records) if isinstance(arxiv_evidence, list) else 'error'} "
        f"s2={len(s2_records) if isinstance(s2_evidence, list) else 'error'} "
        f"web={len(web_records) if isinstance(web_evidence, list) else 'error'} "
        f"-> {len(combined_refs)} combined refs",
    )
    return combined_refs


# --- Strategy 1: literature exploration via search --------------------------


def strategy_literature_exploration(
    run_id: str,
    domain: str,
    literature_refs: list[dict],
    memory_block: str | None,
    meta_review_feedback: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """One Haiku call: hypotheses grounded in the combined retrieved
    snippets, each citing the ref ids that ground it (cited refs are
    validated against the refs actually provided — inside the re-ask loop).

    Step 17-fix-A: the validator ALSO scans each statement for numeric
    literals absent from its cited snippets — WARN-ONLY: each occurrence is
    counted as the cost_meter signal "generation_unsupported_number" and
    never appended to the errors list, so it can never trigger a re-ask or
    reject the hypothesis. Returns (candidates, number_warnings):
    number_warnings holds the ACCEPTED reply's offending literals, one
    record per offending hypothesis {entry, statement, unsupported_numbers}
    (each validator invocation overwrites the list, and the last invocation
    is the accepted reply, so rejected attempts never linger in it — the
    cost_meter count, by contrast, counts every attempt). The caller that
    owns canonical ids (generate_candidate_pool) maps entry -> id and
    writes the durable per-run artifact."""
    valid_refs = {r["ref"] for r in literature_refs}
    refs_by_id = {r["ref"]: r for r in literature_refs}
    number_warnings: list[dict] = []

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        invocation_warnings: list[dict] = []
        hyps = data.get("hypotheses")
        if not isinstance(hyps, list) or len(hyps) != LITERATURE_HYPOTHESIS_COUNT:
            return [
                f"hypotheses must be a list of exactly {LITERATURE_HYPOTHESIS_COUNT} objects."
            ]
        for n, h in enumerate(hyps, start=1):
            if not _entry_field_errors(h, n, ("statement", "rationale"), errors):
                continue
            grounded = h.get("grounded_in")
            if not isinstance(grounded, list) or not grounded:
                errors.append(
                    f"entry {n} grounded_in must be a non-empty list of ref ids "
                    "from the provided literature_snippets."
                )
            else:
                unknown = [r for r in grounded if r not in valid_refs]
                if unknown:
                    errors.append(
                        f"entry {n} grounded_in cites unknown refs {unknown}; "
                        f"the provided refs are {sorted(valid_refs)}."
                    )
                elif isinstance(h.get("statement"), str):
                    # WARN-ONLY (Step 17-fix-A): count numbers the cited
                    # snippets do not contain. Never touches `errors`.
                    unsupported = _unsupported_numbers(h["statement"], [
                        " ".join(
                            str(v) for v in refs_by_id[r].values() if isinstance(v, str)
                        )
                        for r in grounded
                    ])
                    for _value in unsupported:
                        cost_meter.record_signal("generation_unsupported_number")
                    if unsupported:
                        invocation_warnings.append(
                            {
                                "entry": n,
                                "statement": h["statement"],
                                "unsupported_numbers": unsupported,
                            }
                        )
        number_warnings[:] = invocation_warnings  # last invocation = accepted reply
        return errors

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "literature_snippets": literature_refs,
    }
    if memory_block is not None:
        stage_input["prior_observations"] = memory_block
    if meta_review_feedback is not None:
        stage_input["meta_review_feedback"] = meta_review_feedback
    if _feasibility_nudge_on():
        stage_input["feasibility_nudge"] = build_feasibility_nudge(run_id)
    data, timing = call_stage_model(
        "stage1_generation_literature",
        LITERATURE_SYSTEM_PROMPT,
        stage_input,
        {"required": ["ack_run_id", "hypotheses"]},
        model=HAIKU_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, "literature_exploration")
    log_stage_call(run_id, "stage1_generation_literature", timing)

    candidates = [
        {
            "strategy": "literature_exploration",
            "statement": h["statement"],
            "rationale": h["rationale"],
            "grounded_in": h["grounded_in"],
        }
        for h in data["hypotheses"]
    ]
    return candidates, number_warnings


# --- Strategy 2: simulated scientific debate --------------------------------


def strategy_simulated_debate(
    run_id: str,
    domain: str,
    literature_refs: list[dict],
    run_dir: Path,
    meta_review_feedback: str | None = None,
) -> list[dict]:
    """Bounded multi-turn self-play: one Haiku call per persona (hard cap
    DEBATE_TURNS), each seeing the same bounded literature refs plus the
    structured debate so far — construction-level input through the call's
    own arguments, exactly like every other stage-1 input; no transcript is
    ever fed back. The final persona's hypothesis is the converged result.
    The full debate is saved to debate.json as evidence."""

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        if not isinstance(data.get("argument"), str) or not data["argument"].strip():
            errors.append("argument must be a non-empty string.")
        hyp = data.get("hypothesis")
        if not isinstance(hyp, dict):
            errors.append("hypothesis must be an object with statement and rationale.")
        else:
            for field in ("statement", "rationale"):
                value = hyp.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"hypothesis {field} must be a non-empty string.")
        return errors

    debate_so_far: list[dict] = []
    for turn, persona in enumerate(DEBATE_PERSONAS, start=1):
        stage_input = {
            "run_id": run_id,
            "domain": domain,
            "persona": persona,
            "turn": turn,
            "of_turns": DEBATE_TURNS,
            "literature_snippets": literature_refs,
            "debate_so_far": debate_so_far,
        }
        if meta_review_feedback is not None:
            stage_input["meta_review_feedback"] = meta_review_feedback
        if _feasibility_nudge_on():
            stage_input["feasibility_nudge"] = build_feasibility_nudge(run_id)
        data, timing = call_stage_model(
            f"stage1_generation_debate_turn{turn}",
            DEBATE_SYSTEM_PROMPT,
            stage_input,
            {"required": ["ack_run_id", "argument", "hypothesis"]},
            model=HAIKU_MODEL,
            extra_validator=validator,
        )
        _check_ack(data, run_id, f"simulated_debate turn {turn}")
        log_stage_call(run_id, f"stage1_generation_debate_turn{turn}", timing)
        debate_so_far.append(
            {
                "turn": turn,
                "persona": persona,
                "argument": data["argument"],
                "hypothesis": data["hypothesis"],
            }
        )

    (run_dir / "debate.json").write_text(json.dumps(debate_so_far, indent=2))
    converged = debate_so_far[-1]["hypothesis"]
    return [
        {
            "strategy": "simulated_debate",
            "statement": converged["statement"],
            "rationale": converged["rationale"],
            "debate_turns": DEBATE_TURNS,
            "sources_shown": [r["ref"] for r in literature_refs],
        }
    ]


# --- Strategy 3: iterative assumptions identification ------------------------


def strategy_assumptions_identification(
    run_id: str, domain: str, run_dir: Path, meta_review_feedback: str | None = None
) -> list[dict]:
    """Two Haiku calls: (a) identify 3-5 testable intermediate assumptions
    via conditional reasoning, (b) aggregate them into complete hypotheses
    that cite the assumption numbers they build on. Pure reasoning from the
    domain — this strategy does not retrieve (faithful to Co-Scientist; the
    grounding strategies are 1 and, via shown snippets, 2). Both artifacts
    are saved to assumptions.json as evidence."""

    def identify_validator(data: dict) -> list[str]:
        errors: list[str] = []
        assumptions = data.get("assumptions")
        if not isinstance(assumptions, list) or not (3 <= len(assumptions) <= 5):
            return ["assumptions must be a list of 3 to 5 objects."]
        for n, a in enumerate(assumptions, start=1):
            _entry_field_errors(a, n, ("assumption", "testable_because"), errors)
        return errors

    identify_input = {"run_id": run_id, "domain": domain}
    if meta_review_feedback is not None:
        identify_input["meta_review_feedback"] = meta_review_feedback
    if _feasibility_nudge_on():
        identify_input["feasibility_nudge"] = build_feasibility_nudge(run_id)
    identify_data, identify_timing = call_stage_model(
        "stage1_generation_assumptions_identify",
        ASSUMPTIONS_IDENTIFY_SYSTEM_PROMPT,
        identify_input,
        {"required": ["ack_run_id", "assumptions"]},
        model=HAIKU_MODEL,
        extra_validator=identify_validator,
    )
    _check_ack(identify_data, run_id, "assumptions_identify")
    log_stage_call(run_id, "stage1_generation_assumptions_identify", identify_timing)

    numbered = [
        {"n": n, "assumption": a["assumption"], "testable_because": a["testable_because"]}
        for n, a in enumerate(identify_data["assumptions"], start=1)
    ]
    valid_numbers = {a["n"] for a in numbered}

    def aggregate_validator(data: dict) -> list[str]:
        errors: list[str] = []
        hyps = data.get("hypotheses")
        if not isinstance(hyps, list) or len(hyps) != ASSUMPTION_HYPOTHESIS_COUNT:
            return [
                f"hypotheses must be a list of exactly {ASSUMPTION_HYPOTHESIS_COUNT} objects."
            ]
        for n, h in enumerate(hyps, start=1):
            if not _entry_field_errors(h, n, ("statement", "rationale"), errors):
                continue
            built_on = h.get("built_on")
            if not isinstance(built_on, list) or not built_on:
                errors.append(
                    f"entry {n} built_on must be a non-empty list of assumption numbers."
                )
            else:
                bad = [b for b in built_on if not isinstance(b, int) or b not in valid_numbers]
                if bad:
                    errors.append(
                        f"entry {n} built_on cites unknown assumption numbers {bad}; "
                        f"valid numbers are {sorted(valid_numbers)}."
                    )
        return errors

    aggregate_input = {"run_id": run_id, "domain": domain, "assumptions": numbered}
    if meta_review_feedback is not None:
        aggregate_input["meta_review_feedback"] = meta_review_feedback
    if _feasibility_nudge_on():
        aggregate_input["feasibility_nudge"] = build_feasibility_nudge(run_id)
    aggregate_data, aggregate_timing = call_stage_model(
        "stage1_generation_assumptions_aggregate",
        ASSUMPTIONS_AGGREGATE_SYSTEM_PROMPT,
        aggregate_input,
        {"required": ["ack_run_id", "hypotheses"]},
        model=HAIKU_MODEL,
        extra_validator=aggregate_validator,
    )
    _check_ack(aggregate_data, run_id, "assumptions_aggregate")
    log_stage_call(run_id, "stage1_generation_assumptions_aggregate", aggregate_timing)

    (run_dir / "assumptions.json").write_text(
        json.dumps(
            {"assumptions": numbered, "hypotheses": aggregate_data["hypotheses"]},
            indent=2,
        )
    )

    return [
        {
            "strategy": "assumptions_identification",
            "statement": h["statement"],
            "rationale": h["rationale"],
            "built_on_assumptions": h["built_on"],
        }
        for h in aggregate_data["hypotheses"]
    ]


# --- Strategy 4: research expansion ------------------------------------------


def strategy_research_expansion(
    run_id: str,
    domain: str,
    existing_candidates: list[dict],
    memory_block: str | None,
    meta_review_feedback: str | None = None,
) -> list[dict]:
    """One Haiku call: review the run's existing candidates and propose
    hypotheses in unexplored directions.

    LIVE since Step 17-E: meta_review_feedback is the composed feedback
    text block from the prior round's meta-review (built by
    stages/meta_review.compose_feedback_block — code-framed for selective
    use, carrying the prior round's research-overview directions; an
    explicit empty block on round 1), attached to the call input as its
    own field alongside the run's existing hypotheses and the
    already-framed journal leads (memory_block).
    """

    def validator(data: dict) -> list[str]:
        errors: list[str] = []
        hyps = data.get("hypotheses")
        if not isinstance(hyps, list) or len(hyps) != EXPANSION_HYPOTHESIS_COUNT:
            return [
                f"hypotheses must be a list of exactly {EXPANSION_HYPOTHESIS_COUNT} objects."
            ]
        for n, h in enumerate(hyps, start=1):
            _entry_field_errors(
                h, n, ("statement", "rationale", "unexplored_because"), errors
            )
        return errors

    stage_input = {
        "run_id": run_id,
        "domain": domain,
        "existing_hypotheses": [
            {"statement": c["statement"], "rationale": c["rationale"]}
            for c in existing_candidates
        ],
    }
    if memory_block is not None:
        stage_input["prior_observations"] = memory_block
    if meta_review_feedback is not None:
        stage_input["meta_review_feedback"] = meta_review_feedback
    if _feasibility_nudge_on():
        stage_input["feasibility_nudge"] = build_feasibility_nudge(run_id)
    data, timing = call_stage_model(
        "stage1_generation_expansion",
        EXPANSION_SYSTEM_PROMPT,
        stage_input,
        {"required": ["ack_run_id", "hypotheses"]},
        model=HAIKU_MODEL,
        extra_validator=validator,
    )
    _check_ack(data, run_id, "research_expansion")
    log_stage_call(run_id, "stage1_generation_expansion", timing)

    return [
        {
            "strategy": "research_expansion",
            "statement": h["statement"],
            "rationale": h["rationale"],
            "unexplored_because": h["unexplored_because"],
        }
        for h in data["hypotheses"]
    ]


# --- Pool assembly -----------------------------------------------------------


def generate_candidate_pool(
    run_id: str,
    domain: str,
    memory_block: str | None,
    run_dir: Path,
    meta_review_feedback: str | None = None,
) -> list[dict]:
    """Run all four strategies in order and return the combined candidate
    pool with canonical ids h1..hN assigned deterministically (strategy
    order, then within-strategy order). The full pool with per-candidate
    strategy provenance is saved to generation.json; Reflection and
    everything downstream see only {id, statement, rationale}.

    meta_review_feedback (LIVE since Step 17-E) is the composed feedback
    text block for the generation family, threaded to ALL FOUR strategies
    and attached at each call as its own input field — the iteration
    controller composes it from the prior round's meta-review critique
    (an explicit empty block on round 1).
    """
    literature_refs = gather_literature_evidence(run_id, domain, run_dir)

    lit, lit_number_warnings = strategy_literature_exploration(
        run_id, domain, literature_refs, memory_block, meta_review_feedback
    )
    debate = strategy_simulated_debate(
        run_id, domain, literature_refs, run_dir, meta_review_feedback
    )
    assumptions = strategy_assumptions_identification(
        run_id, domain, run_dir, meta_review_feedback
    )
    expansion = strategy_research_expansion(
        run_id, domain, lit + debate + assumptions, memory_block, meta_review_feedback
    )

    pool = []
    for n, candidate in enumerate([*lit, *debate, *assumptions, *expansion], start=1):
        pool.append({"id": f"h{n}", **candidate})

    counts = {}
    for c in pool:
        counts[c["strategy"]] = counts.get(c["strategy"], 0) + 1
    (run_dir / "generation.json").write_text(
        json.dumps({"domain": domain, "strategy_counts": counts, "pool": pool}, indent=2)
    )

    # Step 17-fix-A follow-up: durable per-run record of WHICH numbers fired
    # the strategy-1 warn-only signal, with the canonical id each came from
    # (this function owns the entry->id mapping). Diagnostic evidence only —
    # written ALWAYS (an empty occurrences list is positive proof the scan
    # ran and found nothing), and never read back by any stage.
    lit_ids = [c["id"] for c in pool if c["strategy"] == "literature_exploration"]
    (run_dir / "generation_number_signals.json").write_text(
        json.dumps(
            {
                "signal": "generation_unsupported_number",
                "strategy": "literature_exploration",
                "occurrences": [
                    {
                        "hypothesis_id": lit_ids[w["entry"] - 1],
                        "unsupported_numbers": w["unsupported_numbers"],
                        "statement": w["statement"],
                    }
                    for w in lit_number_warnings
                ],
            },
            indent=2,
        )
    )
    _log(
        run_id,
        "STAGE1_GENERATION pool="
        + str(len(pool))
        + " ("
        + ", ".join(f"{k} {v}" for k, v in counts.items())
        + ")",
    )
    return pool
