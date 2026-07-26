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
from model_call import FULL, call_stage_model, log_stage_call
from tools.substrate_registry import routable_contracts_block
from tools.substrate_selection import capability_table

_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
if str(_RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_DIR))

from scholar_search import search_arxiv, search_openalex, search_semantic_scholar  # noqa: E402
from search import search_index  # noqa: E402
from web_search import web_search  # noqa: E402
from models import model_for  # model-tier resolver

# Step 18.7 downgrade: all four Generation strategies run on Haiku (the
# Sonnet proving batch locked the baseline; the kill-rate/k battery is the
# quality signal for this move).
SONNET_MODEL = model_for("light")

TOP_K_PER_SOURCE = 3

# --- R-WIN-1 (R-14-N1): feasibility-nudge seam, PLUMBING (default off).
# When FEASIBILITY_NUDGE=on, a FEASIBILITY NUDGE block is attached to EVERY
# Generation strategy that composes a generation prompt: literature_exploration
# and research_expansion (the two steering strategies, where memory_block also
# rides) AND simulated_debate + assumptions_identification (extended in the
# 19-lite/retry build per the R-WIN-1 nudge-seam audit — the nudge is about
# instrument feasibility, not journal memory, so unlike memory_block it is not
# scoped to strategies 1 and 4; a nudge that skipped half the pool would leave
# those hypotheses free to keep drifting infeasible). Body = the registry's
# routable_contracts_block (every routable contract verbatim — single source
# of truth; R5, owner 2026-07-17) + the most recent failure memo
# for this run when one exists + one instruction sentence. With the switch off
# no feasibility_nudge field is added, so composed inputs are byte-identical to
# today's. The retry-on-total-defer path (supervisor.py) forces the switch on
# for a single retried ideation pass; env is restored after.
FEASIBILITY_NUDGE_ENV = "FEASIBILITY_NUDGE"
FEASIBILITY_NUDGE_HEADER = "FEASIBILITY NUDGE"
FEASIBILITY_NUDGE_INSTRUCTION = (
    "TESTABILITY. Every hypothesis must be testable by something available to "
    "this run, and the instruments above are one way — if one of them fits, the "
    "experiment varies only parameter names on its 'can vary' line and measures "
    "one of its 'can measure' entries, so check both lines rather than assuming "
    "a knob exists because it would be physically sensible.\n\n"
    "BUT THE SPECIALIZED SOLVERS ARE NOT THE BOUNDARY OF WHAT YOU MAY PROPOSE — "
    "with one honest limit. `python_experiment` runs arbitrary code, and code "
    "can rigorously settle a claim about a METHOD: does this algorithm need "
    "fewer samples, converge faster, find better designs, degrade more "
    "gracefully than the standard practice it would replace? Simulate the "
    "setting, run both arms, measure. Sampling and measurement design, "
    "scheduling and logistics, sequential decision-making, geotechnical or "
    "survey planning, inventory and queueing — none has a named solver here and "
    "all are legitimately testable this way, because the claim under test is "
    "about the procedure, not about the world.\n\n"
    "WHAT CODE CANNOT DO is tell you a fact about physical reality you did not "
    "already encode. Whether a molecule binds, a protein folds, a cell "
    "responds, an alloy conducts — a hand-written simulation of those returns "
    "whatever its assumptions imply, which is not evidence. For those, use a "
    "real instrument: rdkit (cheminformatics), cobrapy (metabolic flux), mafft "
    "(alignment), homology_search (sequence similarity), the CFD/FEA/SPICE "
    "solvers, or a connector. Do not propose a hypothesis whose answer depends "
    "on physics or biology that only a hand-rolled model would supply.\n\n"
    "So a hypothesis is untestable only if NOTHING available could evaluate it "
    "— not merely if no named solver exposes it. When the test is simulated, "
    "say what the simulation assumes, because a method that wins only under "
    "assumptions chosen to favour it has not been shown to win.\n\n"
    "RANGE OVER THE DOMAIN, NOT JUST THE MECHANISM. The named solvers cover "
    "CFD, FEA, circuits, symbolic math, cheminformatics and metabolic models — "
    "the questions expressible in THEIR OWN parameters are largely the "
    "questions those fields have already answered, because that is what those "
    "knobs were built for. So hypotheses that only vary a listed solver knob "
    "tend to land on results already in the literature. The strongest "
    "cross-domain ideas usually live where no dedicated solver exists and the "
    "standard practice is a fixed rulebook rather than a computation. Reach "
    "there deliberately, and say which instrument OR what code you would write "
    "to test it."
)
FEASIBILITY_MEMO_CAP = 2000


def _feasibility_nudge_on() -> bool:
    """R-WIN-1 switch: env FEASIBILITY_NUDGE == 'off' turns the nudge OFF;
    anything else (unset, 'on') leaves it ON. Read at call time.

    DEFAULT FLIPPED TO ON, 2026-07-20. It shipped default-off as plumbing and
    stayed that way; the supervisor forced it on only for a retried ideation
    pass. There is no run for which ideation is better off NOT knowing what
    the instruments accept — an unnudged pool can only produce hypotheses
    that die later. Off remains reachable by env for the A/B the seam was
    built for."""
    return os.environ.get(FEASIBILITY_NUDGE_ENV, "on") != "off"


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
    """The FEASIBILITY NUDGE block: header + the registry's all-routable
    contract block (every routable contract verbatim — single source of
    truth) + THE MACHINE CAPABILITY TABLE + the most recent failure memo for
    this run when one exists + the instruction.

    THE TABLE JOINED THE BLOCK 2026-07-20. Contracts alone are prose: they
    describe what an instrument IS across paragraphs of caveats, and a
    hypothesis can read them cover to cover and still name a knob that does
    not exist (run 20260719T231117Z, glucose_lb/oxygen_lb on cobrapy). The
    table states the accepted parameter names and returnable quantities as
    the router itself sees them, so the hard edges are legible at a glance
    rather than inferable from nine contracts. Contracts still lead — they
    carry the judgment the table cannot.
    """
    # R5 (owner, 2026-07-17): Stage-1 surfaces carry ALL routable contracts —
    # the D.1.1 cavity pin is retired here; selection stays a Stage-2/Step-35
    # design (P8 pin unmoved).
    parts = [
        FEASIBILITY_NUDGE_HEADER + ":",
        routable_contracts_block(),
        capability_table(),
    ]
    memo = read_recent_failure_memo(run_id)
    if memo:
        parts.append("MOST RECENT FAILURE MEMO FOR THIS RUN:\n" + memo)
    parts.append(FEASIBILITY_NUDGE_INSTRUCTION)
    return "\n\n".join(parts)

# Per-strategy candidate counts. Pool = 15 + 1 + 5 + 4 = 25 candidates
# (owner ruling 2026-07-25: raised from 10 to 25 raw hypotheses; debate stays 1 —
# it is a single converged result of its 3-persona exchange). NOTE: this ~2.5x's
# the pool, and Reflection reviews EACH candidate, so per-run generation+review
# cost grows accordingly; the pre-existing kill-rate baselines were taken at
# pool=10 and would need re-baselining if compared numerically.
# POOL SIZE — the power of numbers (owner ruling 2026-07-25).
#
# Volume is what a chat structurally will not give you: asked for ideas it offers
# half a dozen, because that is what fits one answer. Generating scores of them
# and letting screening whittle is cheap relative to running the wrong experiment,
# and only one has to be good. These are the per-strategy counts (plus one
# converged hypothesis from the debate strategy).
#
# Each is env-overridable so a run can be dialled up toward ~100 for a goal where
# the ideas ARE the deliverable, or down for a cheap pass:
#   RESEARCH_IDEATION_LITERATURE / _ASSUMPTIONS / _EXPANSION
def _count(env_name: str, default: int) -> int:
    """Read a pool-size knob; a malformed or non-positive value falls back to the
    default rather than producing a degenerate pool."""
    import os
    raw = os.environ.get(env_name, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return default


LITERATURE_HYPOTHESIS_COUNT = _count("RESEARCH_IDEATION_LITERATURE", 30)
ASSUMPTION_HYPOTHESIS_COUNT = _count("RESEARCH_IDEATION_ASSUMPTIONS", 15)
EXPANSION_HYPOTHESIS_COUNT = _count("RESEARCH_IDEATION_EXPANSION", 12)

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
    "autonomous research pipeline. You are given a research domain and some literature "
    "snippets that were pre-fetched for it, each tagged with a ref id.\n\n"
    "READ THE LITERATURE YOURSELF. The pre-fetched snippets are a STARTING POINT, not the "
    "boundary of what exists — they come from keyword APIs that often return little or "
    "nothing on target. You have web search and web fetch: USE THEM. Search the way a "
    "researcher would before proposing anything: what is the standard method in this area, "
    "what has already been tried, where are the open problems, what would actually be new. "
    "Ideas grounded only in whatever the pre-fetch happened to return will be shallow.\n\n"
    "AIM FOR RANGE, NOT SAFETY. These hypotheses are screened later, so a bold idea that "
    "turns out to be wrong costs little, while a pool of obvious ones costs the whole run. "
    "Vary the angle: different subfields, different mechanisms, different scales, "
    "cross-domain transfers. Do not propose N restatements of the same safe idea.\n\n"
    f"Propose exactly {LITERATURE_HYPOTHESIS_COUNT} hypotheses, each concrete enough to be "
    "tested by a simulation, and each citing what grounds it — a provided ref id, or a "
    "source you located, cited so a human can find it (a URL, DOI, or arXiv id). "
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

    RULING 2026-07-25 (supersedes 17-fix-B's hard-required OpenAlex). EVERY
    network source is now BEST-EFFORT, including OpenAlex, and the
    web_search sub-agent is retired from this path. 17-fix-B made OpenAlex
    fail-loud because it was the ONLY novelty grounding the pipeline had —
    the generating and reviewing agents were forbidden to search, so if the
    pre-fetch thinned out, grounding vanished silently. That premise is
    gone: those agents now search the literature themselves with WebSearch
    and WebFetch (see LITERATURE_SYSTEM_PROMPT), which is strictly better
    grounding than a keyword API — it can refine a query, follow a
    citation, and read the paper. Aborting a run because a rate-limited
    third-party API returned nothing now costs breadth and buys nothing.

    These sources are also the run's wall-clock bottleneck, not a dollar
    cost: arXiv self-throttles at 1 request per 3 s and Semantic Scholar's
    keyless pool 429s through bounded retries, which is most of why
    stage1_generation_literature took 250 s in study-20260725T073215Z. The
    LOCAL corpus index stays required — it is instant, free, offline, and
    project-specific.

    Every record is already bounded by its wrapper (snippet caps); nothing
    raw exists at this layer.
    """
    corpus_records = [
        {"source": r["source"], "title": r["title"], "snippet": r["snippet"]}
        for r in search_index("literature", domain, top_k=TOP_K_PER_SOURCE)
    ]
    # THE KEYWORD-API PRE-FETCH IS RETIRED (2026-07-25). Making it best-effort was
    # not enough: the calls still ran, and still cost ~100 s of throttled retries
    # per run to contribute nothing. Live evidence from the very next run — arXiv
    # 503 then 429 then 429 then a read timeout, Semantic Scholar 429 four times,
    # OpenAlex 0 records, three corpus refs total — while the generation agent
    # itself made six WebSearch calls and cited a real located paper. The agent's
    # own search is strictly better (it refines the query, follows citations, and
    # reads the source) and these APIs were pure latency in front of it.
    #
    # The evidence keys are kept so the file's shape is stable for readers and
    # tests; each records why it is absent rather than silently vanishing.
    _RETIRED = {"note": "retired: the generation agent searches the web itself "
                        "(FULL tools) — the keyword APIs cost latency, not signal"}
    openalex_records: list = []
    arxiv_records: list = []
    s2_records: list = []
    openalex_evidence: list | dict = _RETIRED
    arxiv_evidence: list | dict = _RETIRED
    s2_evidence: list | dict = _RETIRED

    # The web_search SUB-AGENT is RETIRED here too (2026-07-25). It spawned a
    # whole extra model call just to run WebSearch and marshal JSON — scaffolding
    # from the era when these stages held no tools. The generation strategies run
    # FULL and search natively, so the wrapper added a call, a failure mode (it
    # returned prose and deleted a source in study-20260725T073215Z), and nothing
    # the agent cannot do better itself.
    web_records: list = []
    web_evidence: list | dict = {
        "note": "retired: the generation agent searches the web itself (FULL tools)"
    }

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
        "openalex": openalex_evidence,
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
                    f"entry {n} grounded_in must be a non-empty list citing what "
                    "grounds the hypothesis — a provided ref id, or a source you "
                    "located (URL, DOI, or arXiv id)."
                )
            else:
                # Uncaged 2026-07-25, same rule as the novelty review: a citation
                # must be CHECKABLE, not DRAWN FROM A FIXED LIST. Requiring every
                # citation to come from the pre-fetch meant the generator could
                # only build on whatever a throttled keyword API happened to
                # return, which is how a 58-hypothesis pool ends up shallow.
                from stages.reflection_reviews import _is_checkable_citation
                unusable = [r for r in grounded
                            if not _is_checkable_citation(r, valid_refs)]
                if unusable:
                    errors.append(
                        f"entry {n} grounded_in entries {unusable} are not "
                        f"checkable; each must be a provided ref id "
                        f"{sorted(valid_refs)} or a source you located, cited so a "
                        "human can find it (a URL, DOI, or arXiv id)."
                    )
                elif isinstance(h.get("statement"), str):
                    # WARN-ONLY (Step 17-fix-A): count numbers the cited
                    # snippets do not contain. Never touches `errors`.
                    # .get, not [r]: since the uncaging a citation may be a
                    # source the agent LOCATED (an arXiv id, DOI or URL) rather
                    # than a pre-fetched ref id, so it has no entry here. This
                    # warn-only signal simply has no snippet text to compare
                    # against for those — it must never crash the run, and a
                    # located citation is the behaviour we asked for.
                    unsupported = _unsupported_numbers(h["statement"], [
                        " ".join(
                            str(v) for v in (refs_by_id.get(r) or {}).values()
                            if isinstance(v, str)
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
        model=SONNET_MODEL,
        extra_validator=validator,
        capabilities=FULL,
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
            model=SONNET_MODEL,
            extra_validator=validator,
            capabilities=FULL,
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
        model=SONNET_MODEL,
        extra_validator=identify_validator,
        capabilities=FULL,
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
        model=SONNET_MODEL,
        extra_validator=aggregate_validator,
        capabilities=FULL,
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
        model=SONNET_MODEL,
        extra_validator=validator,
        capabilities=FULL,
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
