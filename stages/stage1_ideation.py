"""
stage1_ideation.py — real Ideation stage: Generation + Reflection + a
deterministic novelty/quality filter + Ranking, backed by Sonnet for
Generation/Reflection and Opus for Ranking (a hard judgment call, per
CLAUDE.md's model roles).

Generation (rebuilt in Step 17 to faithfully match Co-Scientist's four
generation strategies — see stages/generation_strategies.py) produces a
combined candidate pool via: (1) literature exploration grounded in the
corpus RAG plus live arXiv/Semantic Scholar/web search, (2) a bounded
simulated scientific debate among expert personas converging on one
refined hypothesis, (3) iterative assumptions identification aggregated
into hypotheses, and (4) research expansion into directions the run's
existing candidates left unexplored. All retrieval passes through the
wrappers' bounded records, and every record a run used is saved under
runs/<run_id>/stage1/ as evidence. Reflection (rebuilt in Step 17 to
faithfully match Co-Scientist's six review types — see
stages/reflection_reviews.py) applies to that pool: (1) a fast no-tools
initial review that gates the pool before any tool spend, then per survivor
(2) a full review grounded in live per-hypothesis retrieval (corpus + arXiv
required, Semantic Scholar + web best-effort) whose novelty verdict must
cite the refs actually shown, (3) a deep-verification review decomposing
assumptions (a fundamental flaw discards deterministically), (4) an
observation review against retrieved snippets and journal leads, (5) a
step-wise simulation review surfacing failure scenarios, and (6) a
recurrent/tournament review (active since Step 17-E) over the prior
round's tournament results resolved to plain statements — advisory only,
inert on round 1 or after a trivially-ranked prior round. The result
per surviving candidate is the same reflection object as always:
{hypothesis_id, novelty, critique, quality}. A pure-Python filter (no model
call) then discards anything judged "known" and keeps at most four survivors
by quality, ties broken by generation order. Ranking (rebuilt in Step 17-C
as an Elo tournament — pure math in stages/tournament.py, Opus judgments
here) plays every unordered pair of survivors once, most-similar pairs first
(TF-IDF proximity), with A/B presentation randomized per match from a
run_id-seeded RNG: a match between the current top-2 by live Elo is a full
two-ordering three-turn debate (advocate A, advocate B, judge — twice with
A/B swapped; agreeing verdicts score 1.0, disagreeing draw at 0.5), any
other match is one single-turn judge call. Elo (K=32, init 1200) updates
after each match in deterministic order; final rank is Elo descending, ties
broken by the survivors' existing (quality, generation) order, and near-
duplicate survivors (cosine >= 0.85) are flagged deduped_by their higher-
ranked sibling in the evidence — never removed.

Full generation/reflection/survivor/ranking records are evidence on disk
under runs/<run_id>/stage1/; only {id, statement, rationale} for the
survivors, in ranked order, ever reaches the baton payload.

Iteration controller (Step 17-E): run() loops the whole Generation →
Reflection → filter → Evolution → Ranking relay up to ROUNDS times
(default 2; the kill-rate battery passes rounds=1, so scored battery runs
stay baseline-comparable single passes unless flagged). Memory retrieval
stays OUTSIDE the loop — one journal read per run, which is what the
battery's memory-comparability md5 pin has always meant. Each round works
in stage1/round<N>/ and, on success, its files are copied up to stage1/ —
so the canonical stage1 files are always the LAST SUCCESSFUL round's.
stage1/rounds.json is the per-run round audit trail (one appended entry
per round: pool statements, k, the ranking resolved to statements, the
full meta-review critique, termination_reason); stage1/
research_overview.json is rewritten at every round boundary and the last
round's version is the end-of-run synthesis — it never enters the baton
(the gate-1 payload wall is untouched). Meta-review
(stages/meta_review.py, one Opus call) runs at EVERY round boundary,
including after the final round: the final round's critique is recorded in
rounds.json but has no next round to consume it — recorded-but-unconsumed,
deliberately. Between rounds the critique feeds per-family feedback blocks
(meta_review.compose_feedback_block) into Generation (framed for selective
use, plus the prior round's research-overview directions), Reflection
(framed as recurring factors every future review must definitively
address), and the tournament judge family (plain-labeled); the prior
round's tournament results, resolved to plain statements
(resolve_tournament_to_statements — canonical ids are reassigned every
round, so raw ids must never cross a round boundary), feed Reflection's
review 6. Termination is by round budget and the MAX_SURVIVORS count cap
ONLY; ranking-stability detection is deliberately deferred — cross-round
ids are unstable, so an id-based stability test would be meaningless. A
zero-survivor raise in round 1 crashes honestly exactly as the single-pass
stage always did; in round >= 2 it is caught, the loop terminates, and the
run stands on the last successful round (recorded in rounds.json). Rounds
with a single tournament candidate write a trivial-marker
tournament_state.json so stale multi-candidate state never lies beside an
empty ranking. Exactly ONE history entry is added per run() regardless of
rounds.

Journal read-side (Step 14): before Generation, deterministic stage code
reads the last 3 learned_summary journal entries, saves them verbatim to
runs/<run_id>/stage1/retrieved_memory.json, and (when any exist) appends a
framed prior-observations block as an explicit field of the Generation and
Reflection inputs — through the call's own arguments, preserving
construction-level isolation. Within Generation the block goes to the two
hypothesis-proposing strategies that historically saw it (literature
exploration, as old Generation's descendant, and research expansion, whose
job is steering); debate and assumptions stay memory-free. Within Reflection
(since Step 17) it goes only to the observation review — the unit whose job
is prior observations. Ranking and every other stage get nothing.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import shutil
from pathlib import Path

from baton import Baton
from memory.journal import journal_recent_by_kind
from model_call import FULL, call_stage_model, log_stage_call
from stages import tournament
from stages.evolution_strategies import evolve_and_review
from stages.generation_strategies import (
    gather_literature_evidence,
    generate_candidate_pool,
    strategy_literature_exploration,
)
from stages.meta_review import (
    append_rounds_entry,
    build_meta_review,
    compose_feedback_block,
    compose_round_record,
    empty_feedback,
)
from stages.reflection_reviews import reflect_on_pool
from models import model_for  # model-tier resolver

OPUS_MODEL = model_for("heavy")

RANKING_SYSTEM_PROMPT_V2 = (
    "You are a comparative-judge stage in an autonomous research pipeline, evaluating two "
    "candidate hypotheses proposed for a given research domain. Judge which of the two is "
    "the more promising next simulation experiment as a scientific comparison on three "
    "axes: novelty (does it go beyond what is already established), correctness (is the "
    "proposed mechanism physically sound), and testability (can a simulation actually "
    "resolve and measure what it claims). Each hypothesis may carry addressable_notes — "
    "concerns already identified during review that its proposer would need to address "
    "downstream; weigh them as carried concerns, not automatic disqualifiers. The order in "
    "which the two hypotheses are presented to you carries no information about which is "
    "better. In your reason, refer to hypotheses only by their ids — never by position or "
    "order words such as 'first', 'second', 'former', or 'latter'. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"winner_id": "<the id of the hypothesis you judge more promising>", '
    '"reason": "<one decisive sentence>"}.'
)

DEBATE_ADVOCATE_SYSTEM_PROMPT = (
    "You are one advocate turn in a two-hypothesis ranking debate inside an autonomous "
    "research pipeline. Two candidate hypotheses are competing for rank; advocate_for "
    "names the one you must argue for. Read both hypotheses and the debate so far, then "
    "make the strongest honest scientific case for your assigned hypothesis on novelty, "
    "correctness, and testability — rebutting the debate so far where it attacked your "
    "side. Each hypothesis may carry addressable_notes — concerns already identified "
    "during review; weigh and answer them as carried concerns, not automatic "
    "disqualifiers. Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"argument": "<two to four sentences>"}.'
)

DEBATE_JUDGE_SYSTEM_PROMPT = (
    "You are the judge turn concluding a two-hypothesis ranking debate inside an "
    "autonomous research pipeline. Read both hypotheses and both advocates' arguments, "
    "then judge which hypothesis is the more promising next simulation experiment as a "
    "scientific comparison on three axes: novelty (does it go beyond what is already "
    "established), correctness (is the proposed mechanism physically sound), and "
    "testability (can a simulation actually resolve and measure what it claims). Each "
    "hypothesis may carry addressable_notes — concerns already identified during review; "
    "weigh them as carried concerns, not automatic disqualifiers. The order in which the "
    "hypotheses and arguments are presented to you carries no information about which is "
    "better. In your reason, refer to hypotheses only by their ids — never by position or "
    "order words such as 'first', 'second', 'former', or 'latter'. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"winner_id": "<the id of the hypothesis you judge more promising>", '
    '"reason": "<one decisive sentence>"}.'
)

# --- R-WIN-1 (R-18-2): toggleable rubric 18.6 criteria for tournament judges.
# IMPACT and ALIGNMENT are each a separately switched axis added to the judge
# rubric (the RANKING and DEBATE-JUDGE prompts). Both default OFF; with both
# off, compose_judge_prompt returns the base prompt BYTE-IDENTICAL (proven by
# tests/test_rwin1_prompts.py). When on, the criterion sentence is inserted
# into the judging section (before the "Reply ONLY with JSON" reply spec), so
# the judge weighs it in the verdict reason, id-referenced per the standing
# id-hygiene rule. NO new kill path: these steer comparative verdicts only.
CRITERIA_IMPACT_ENV = "CRITERIA_IMPACT"
CRITERIA_ALIGNMENT_ENV = "CRITERIA_ALIGNMENT"

IMPACT_CRITERION = (
    "Also weigh IMPACT: if this hypothesis were true, who would change what they "
    "do — whose decision or practice would shift? Prefer the hypothesis whose "
    "truth would more concretely change what someone does, and reference this "
    "axis by hypothesis id in your reason when it bears on the verdict. "
)

ALIGNMENT_CRITERION = (
    "Also weigh ALIGNMENT: does the hypothesis answer what the research domain "
    "actually asked, rather than an easier or adjacent question? Prefer the "
    "better-aligned hypothesis, and reference this axis by hypothesis id in your "
    "reason when it bears on the verdict. "
)

_JUDGE_REPLY_MARKER = "Reply ONLY with JSON"


def _env_on(name: str) -> bool:
    """R-WIN-1 switch read: env var == '1' turns the criterion on; anything
    else (unset, '0') leaves it off. Read at call time, not import time."""
    return os.environ.get(name, "0") == "1"


def compose_judge_prompt(base: str) -> str:
    """R-WIN-1: return the judge system prompt with the enabled rubric-18.6
    criteria (IMPACT / ALIGNMENT) inserted before the reply-format spec.
    With both switches off, returns `base` unchanged and byte-identical."""
    additions = ""
    if _env_on(CRITERIA_IMPACT_ENV):
        additions += IMPACT_CRITERION
    if _env_on(CRITERIA_ALIGNMENT_ENV):
        additions += ALIGNMENT_CRITERION
    if not additions:
        return base
    idx = base.index(_JUDGE_REPLY_MARKER)
    return base[:idx] + additions + base[idx:]


MAX_SURVIVORS = 4

# Step 17-E iteration controller: rounds per run. The supervisor's default;
# the kill-rate battery overrides to 1 so scored runs stay single-pass and
# baseline-comparable. Termination is round budget + the MAX_SURVIVORS count
# cap only (see the module docstring for the deferred stability criterion).
ROUNDS = 2

# The two zero-survivor raises (reflect_on_pool's and filter_survivors')
# are identified by these message markers — their raise sites are frozen
# (the deterministic kill rules), so the controller matches message text
# rather than editing frozen code to raise a dedicated exception class.
_ZERO_SURVIVOR_MARKERS = ("Zero survivors", "Zero reviewed hypotheses")

MEMORY_HEADER = (
    "PRIOR OBSERVATIONS FROM EARLIER RUNS (unverified model text - treat "
    "as leads, not established facts):"
)


def build_memory_block(entries: list[dict]) -> str | None:
    """Pure, no I/O: format journal entries into the prior-observations block.

    Returns None when `entries` is empty; otherwise the exact MEMORY_HEADER
    line followed by one line per entry:
    "- [run <run_id>, hypothesis <hypothesis_id>] <text>". The framing marks
    the content as unverified model text — leads, not established facts.
    """
    if not entries:
        return None
    lines = [MEMORY_HEADER]
    for e in entries:
        lines.append(
            f"- [run {e.get('run_id')}, hypothesis {e.get('hypothesis_id')}] {e.get('text')}"
        )
    return "\n".join(lines)


def _log(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt.

    Mirrors model_call.log_stage_call's own path reconstruction — stages
    never hold the supervisor's Logger object, so this is the second place
    (after model_call.py) that path gets rebuilt from run_id alone.
    """
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def filter_survivors(reflections: list[dict]) -> list[dict]:
    """Pure-Python, no model call: discard hypotheses whose ANSWER is already on
    record, keep at most MAX_SURVIVORS by quality (highest first), ties broken by
    original (generation) order.

    THE PREDICATE CHANGED 2026-07-25, on live evidence. This used to discard every
    reflection with novelty == "known", which was survivable only while the
    reviewer was blind: it could not search, so it returned "novel" by default and
    the filter almost never fired. The moment the reviewer could actually read the
    literature, all 16 of 16 hypotheses came back "known" and the run halted with
    zero survivors — the gate went from never firing to always firing, and neither
    is a judgment.

    The category error is that novelty of METHOD is not novelty of ANSWER, and only
    the second decides whether running an experiment teaches anything. Almost every
    good applied hypothesis uses an established method — that is why it is likely
    to work. A textbook technique carried into a domain that has never applied it,
    where the effect size is genuinely unknown, is a GOOD hypothesis that this
    filter used to delete. So the kill is now `answer_established`: prior work has
    already measured this specific claim in this specific setting, so there is
    nothing to learn. Novelty survives as a ranking signal, not a veto.

    Raises RuntimeError only when EVERY hypothesis is already answered — still an
    honest failure, but now one that means what it says.
    """
    live = [(i, r) for i, r in enumerate(reflections)
            if not r.get("answer_established")]
    if not live:
        # NEVER HALT THE RUN (2026-07-25). This raised twice live, on the two
        # successive predicates, and killing a run is the pipeline overriding the
        # researcher — precisely the caged behaviour the PRIME DIRECTIVE forbids.
        # A chat handed sixteen already-answered ideas does not refuse to
        # continue; it says so and decides what to do. So do that: pass the
        # best-ranked candidates up, each still carrying answer_established=True,
        # and let the DIRECTOR — which can see the flag in its arc and can
        # re-ideate with a different framing, reframe the goal, or proceed
        # knowingly — make the call. A screening stage reports; it does not veto.
        live = list(enumerate(reflections))
    # Rank: unanswered-and-novel first, then unanswered-but-known-method, each by
    # quality. A known method whose answer is open still competes; it just does not
    # outrank an equally good hypothesis that is also methodologically new.
    live.sort(key=lambda pair: (pair[1].get("novelty") != "novel",
                                -pair[1]["quality"], pair[0]))
    return [r for _, r in live[:MAX_SURVIVORS]]


def _judge_view(s: dict) -> dict:
    """J6: what a tournament judge/advocate sees of one hypothesis — id,
    statement, rationale, and addressable_notes (carried concerns to weigh) —
    NOT critique, NOT quality."""
    return {
        "id": s["id"],
        "statement": s["statement"],
        "rationale": s["rationale"],
        "addressable_notes": s.get("addressable_notes", []),
    }


def _live_top2(ratings: dict[str, float], survivors_full: list[dict]) -> set[str]:
    """J2 tier check: the ids currently ranked top-2 by live Elo; equal Elo
    breaks by survivors_full's existing order — the same J9 tiebreak
    tournament.final_ranking applies at the end."""
    order = sorted(
        range(len(survivors_full)),
        key=lambda i: (-ratings[survivors_full[i]["id"]], i),
    )
    return {survivors_full[i]["id"] for i in order[:2]}


def _check_verdict(data: dict, run_id: str, h_a: dict, h_b: dict, context: str) -> None:
    """Mirror of the pre-17-C ranking checks: ack_run_id must echo the run,
    winner_id must be one of the two presented ids (already enum-pinned in
    the schema; this is the same belt-and-suspenders re-check as before)."""
    if data["ack_run_id"] != run_id:
        raise RuntimeError(
            f"stage1_ideation {context}: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {run_id!r}"
        )
    _log(run_id, f"STAGE1_ACK_CHECK {context}: ack_run_id passed")
    winner_id = data["winner_id"]
    if winner_id not in (h_a["id"], h_b["id"]):
        raise RuntimeError(
            f"stage1_ideation {context}: winner_id {winner_id!r} is not "
            f"one of the presented ids ({h_a['id']!r}, {h_b['id']!r})"
        )
    _log(run_id, f"STAGE1_ACK_CHECK {context}: winner_id valid ({winner_id})")


def _single_turn_judge(
    run_id: str, domain: str, h_a: dict, h_b: dict, feedback_block: str | None = None
) -> dict:
    """One Opus judge call for a non-top-2 match (J2), presented in the
    (h_a, h_b) order the caller randomized. feedback_block (Step 17-E) is
    the ranking family's composed meta-review feedback, attached as its own
    input field when present. Returns a verdict in ranking.json's exact
    historical shape: {pair, ack_run_id, winner_id, reason}."""
    pair_name = f"{h_a['id']}_vs_{h_b['id']}"
    rank_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_a": _judge_view(h_a),
        "hypothesis_b": _judge_view(h_b),
    }
    if feedback_block is not None:
        rank_input["meta_review_feedback"] = feedback_block
    rank_schema = {
        "required": ["ack_run_id", "winner_id", "reason"],
        "enums": {"winner_id": [h_a["id"], h_b["id"]]},
    }
    rank_data, rank_timing = call_stage_model(
        "stage1_tournament_judge",
        compose_judge_prompt(RANKING_SYSTEM_PROMPT_V2),
        rank_input,
        rank_schema,
        model=OPUS_MODEL,
        capabilities=FULL,
    )
    _check_verdict(rank_data, run_id, h_a, h_b, f"tournament judge {pair_name}")
    log_stage_call(run_id, "stage1_tournament_judge", rank_timing)
    return {
        "pair": [h_a["id"], h_b["id"]],
        "ack_run_id": rank_data["ack_run_id"],
        "winner_id": rank_data["winner_id"],
        "reason": rank_data["reason"],
    }


def _debate_once(
    run_id: str, domain: str, h_a: dict, h_b: dict, feedback_block: str | None = None
) -> dict:
    """One full three-turn debate at the presented (h_a, h_b) ordering
    (J4), following generation_strategies.strategy_simulated_debate's
    construction pattern: three independent Opus calls, the structured
    debate-so-far passed inside stage_input's own arguments — never a
    transcript. Turn 1 advocates for hypothesis_a, turn 2 advocates for
    hypothesis_b (sees turn 1), turn 3 judges (sees both) with the same
    verdict schema as a single-turn match. The caller runs this twice with
    A/B swapped (J5). Returns the judge's verdict in ranking.json's shape."""

    def argument_validator(data: dict) -> list[str]:
        if not isinstance(data.get("argument"), str) or not data["argument"].strip():
            return ["argument must be a non-empty string."]
        return []

    pair_name = f"{h_a['id']}_vs_{h_b['id']}"
    debate_so_far: list[dict] = []
    for turn, advocate in ((1, h_a), (2, h_b)):
        stage_input = {
            "run_id": run_id,
            "domain": domain,
            "advocate_for": advocate["id"],
            "turn": turn,
            "of_turns": 3,
            "hypothesis_a": _judge_view(h_a),
            "hypothesis_b": _judge_view(h_b),
            "debate_so_far": debate_so_far,
        }
        if feedback_block is not None:
            stage_input["meta_review_feedback"] = feedback_block
        data, timing = call_stage_model(
            f"stage1_tournament_debate_turn{turn}",
            DEBATE_ADVOCATE_SYSTEM_PROMPT,
            stage_input,
            {"required": ["ack_run_id", "argument"]},
            model=OPUS_MODEL,
            extra_validator=argument_validator,
            capabilities=FULL,
        )
        if data["ack_run_id"] != run_id:
            raise RuntimeError(
                f"stage1_ideation debate {pair_name} turn {turn}: ack_run_id "
                f"mismatch — got {data['ack_run_id']!r}, expected {run_id!r}"
            )
        _log(run_id, f"STAGE1_ACK_CHECK debate {pair_name} turn {turn}: ack_run_id passed")
        log_stage_call(run_id, f"stage1_tournament_debate_turn{turn}", timing)
        debate_so_far.append(
            {"turn": turn, "advocate_for": advocate["id"], "argument": data["argument"]}
        )

    judge_input = {
        "run_id": run_id,
        "domain": domain,
        "turn": 3,
        "of_turns": 3,
        "hypothesis_a": _judge_view(h_a),
        "hypothesis_b": _judge_view(h_b),
        "debate_so_far": debate_so_far,
    }
    if feedback_block is not None:
        judge_input["meta_review_feedback"] = feedback_block
    judge_schema = {
        "required": ["ack_run_id", "winner_id", "reason"],
        "enums": {"winner_id": [h_a["id"], h_b["id"]]},
    }
    judge_data, judge_timing = call_stage_model(
        "stage1_tournament_debate_turn3",
        compose_judge_prompt(DEBATE_JUDGE_SYSTEM_PROMPT),
        judge_input,
        judge_schema,
        model=OPUS_MODEL,
        capabilities=FULL,
    )
    _check_verdict(judge_data, run_id, h_a, h_b, f"debate judge {pair_name}")
    log_stage_call(run_id, "stage1_tournament_debate_turn3", judge_timing)
    return {
        "pair": [h_a["id"], h_b["id"]],
        "ack_run_id": judge_data["ack_run_id"],
        "winner_id": judge_data["winner_id"],
        "reason": judge_data["reason"],
    }


def resolve_tournament_to_statements(state: dict, statements_by_id: dict[str, str]) -> dict:
    """Pure: a tournament state (tournament.build_state's shape) with every
    hypothesis id replaced by its statement. Canonical ids are reassigned
    every round, so raw ids must never cross a round boundary — this
    resolved view is what review 6 and meta-review receive."""
    return {
        "final_ranking": [
            {"statement": statements_by_id[e["id"]], "elo": e["elo"]}
            for e in state["final_ranking"]
        ],
        "matches": [
            {
                "statements": [statements_by_id[pid] for pid in m["pair"]],
                "tier": m["tier"],
                "winner_statements": [statements_by_id[w] for w in m["verdicts"]],
                "reasons": m["reasons"],
            }
            for m in state["match_log"]
        ],
        "dedup_flags": [
            {
                "statements": [statements_by_id[pid] for pid in f["pair"]],
                "similarity": f["similarity"],
            }
            for f in state["proximity"]["dedup_flags"]
        ],
    }


def _is_zero_survivor_error(exc: Exception) -> bool:
    """True when `exc` is one of the two zero-survivor raises (identified
    by the frozen raise sites' message markers — see _ZERO_SURVIVOR_MARKERS)."""
    text = str(exc)
    return any(marker in text for marker in _ZERO_SURVIVOR_MARKERS)


def _run_round(
    run_id: str,
    domain: str,
    memory_block: str | None,
    round_dir: Path,
    round_index: int,
    gen_block: str,
    refl_block: str,
    rank_block: str,
    prior_tournament_resolved: dict | None,
) -> dict:
    """One full Generation → Reflection → filter → Evolution → Ranking pass,
    writing every per-round artifact into round_dir (stage1/round<N>/); the
    caller promotes a successful round's files to the canonical stage1/ set.
    Raises exactly like the single-pass stage always did — the caller
    decides what a raise means for the loop (round 1: honest crash;
    round >= 2 zero-survivor: recorded termination)."""

    # --- Generation (Step 17: the four Co-Scientist strategies; every model
    # call, retrieval, evidence write, and the pool's canonical h1..hN ids
    # live in stages/generation_strategies.py; gen_block is the composed
    # meta-review feedback for the generation family, Step 17-E) ---
    pool = generate_candidate_pool(
        run_id, domain, memory_block, round_dir, meta_review_feedback=gen_block
    )
    hypotheses = [
        {"id": c["id"], "statement": c["statement"], "rationale": c["rationale"]}
        for c in pool
    ]

    # --- Reflection (Step 17: the six Co-Scientist review types; every model
    # call, per-hypothesis retrieval, evidence write, and both deterministic
    # discard rules live in stages/reflection_reviews.py; the returned
    # reflection objects keep the exact {hypothesis_id, novelty, critique,
    # quality} contract the filter below has consumed since Step 8. Step
    # 17-E: refl_block is the reflection family's feedback; the prior
    # round's statement-resolved tournament results feed review 6) ---
    reflections, review_summary = reflect_on_pool(
        run_id,
        domain,
        hypotheses,
        memory_block,
        round_dir,
        tournament_state=prior_tournament_resolved,
        feedback_block=refl_block,
    )
    (round_dir / "reflections.json").write_text(json.dumps(reflections, indent=2))

    # --- Deterministic filter (no model) ---
    survivor_reflections = filter_survivors(reflections)

    hyp_by_id = {h["id"]: h for h in hypotheses}
    survivors_full = [
        {
            "id": r["hypothesis_id"],
            "statement": hyp_by_id[r["hypothesis_id"]]["statement"],
            "rationale": hyp_by_id[r["hypothesis_id"]]["rationale"],
            "novelty": r["novelty"],
            "critique": r["critique"],
            "quality": r["quality"],
            # Step 17-fix-A follow-up: deep verification's non-fatal
            # concerns travel with the survivor into ranking evidence
            # (survivors.json). Stage-1 evidence only — the payload below
            # is rebuilt {id, statement, rationale}, so this never crosses
            # gate 1.
            "addressable_notes": r.get("addressable_notes", []),
        }
        for r in survivor_reflections
    ]
    (round_dir / "survivors.json").write_text(json.dumps(survivors_full, indent=2))

    # --- Evolution (Step 17-D: up to 2 variants from the finalized parents,
    # emitted and reviewed by the same Reflection machinery in
    # stages/evolution_strategies.py — never raises; zero accepted variants
    # means the run proceeds over the parents alone). Accepted variants join
    # the tournament pool IN MEMORY ONLY: survivors_full and survivors.json
    # are never mutated, and the battery's k stays len(survivors.json). ---
    accepted_variants = evolve_and_review(
        run_id, domain, survivors_full, memory_block, round_dir
    )
    tournament_pool = survivors_full + accepted_variants

    # --- Ranking (Step 17-C: Elo tournament — pure math in
    # stages/tournament.py, Opus judgments through the helpers above;
    # since Step 17-D everything below keys off tournament_pool) ---
    k = len(tournament_pool)
    verdicts: list[dict] = []

    if k == 1:
        _log(run_id, "STAGE1_RANKING ranking trivial (k=1)")
        ranked_survivors = tournament_pool
        ranking_note = "ranking trivial (k=1)"
        # Step 17-E: the trivial marker. Rounds overwrite the canonical
        # stage1 files, so a k=1 round must overwrite tournament_state.json
        # too — otherwise a stale multi-candidate state from an earlier
        # round would lie beside this round's empty ranking.
        (round_dir / "tournament_state.json").write_text(
            json.dumps(
                {
                    "trivial": True,
                    "round": round_index,
                    "reason": (
                        "ranking trivial (k=1) — no matches were played this "
                        "round; this marker replaces any stale multi-candidate "
                        "state from an earlier round"
                    ),
                    "final_ranking": [{"id": tournament_pool[0]["id"]}],
                },
                indent=2,
            )
        )
        tournament_resolved = None
        ranking_resolved = [{"statement": tournament_pool[0]["statement"]}]
    else:
        # Round 1 keeps the historical seed (byte-comparable with every
        # pre-17-E run); later rounds get an independent stream.
        rng_seed = run_id if round_index == 1 else f"{run_id}:round{round_index}"
        rng = random.Random(rng_seed)
        _log(
            run_id,
            f"STAGE1_TOURNAMENT rng_seed={rng_seed} "
            f"elo_init={tournament.ELO_INIT} k_factor={tournament.K_FACTOR}",
        )

        ratings = {s["id"]: tournament.ELO_INIT for s in tournament_pool}
        ids = [s["id"] for s in tournament_pool]
        matrix = tournament.proximity_matrix(tournament_pool)
        flags = tournament.dedup_flags(matrix)
        for fi, fj, sim in flags:
            _log(
                run_id,
                f"STAGE1_TOURNAMENT dedup_flag {ids[fi]}_vs_{ids[fj]} sim={sim:.3f}",
            )
        matches = tournament.order_matches(
            list(itertools.combinations(range(k), 2)), matrix
        )

        match_log: list[dict] = []
        debate_count = 0
        for i, j in matches:
            h_i, h_j = tournament_pool[i], tournament_pool[j]
            pair_ids = [h_i["id"], h_j["id"]]
            # Randomized A/B presentation, reproducible from the logged seed.
            h_a, h_b = (h_i, h_j) if rng.random() < 0.5 else (h_j, h_i)

            top2 = _live_top2(ratings, tournament_pool)
            tier = (
                "debate"
                if h_i["id"] in top2 and h_j["id"] in top2
                else "single_turn"
            )
            elo_before = {pid: ratings[pid] for pid in pair_ids}

            if tier == "debate":
                debate_count += 1
                v1 = _debate_once(run_id, domain, h_a, h_b, rank_block)
                v2 = _debate_once(run_id, domain, h_b, h_a, rank_block)
                match_verdicts = [v1, v2]
                orderings = [[h_a["id"], h_b["id"]], [h_b["id"], h_a["id"]]]
                score_a = tournament.debate_score(
                    h_a["id"], h_b["id"], v1["winner_id"], v2["winner_id"]
                )
            else:
                v1 = _single_turn_judge(run_id, domain, h_a, h_b, rank_block)
                match_verdicts = [v1]
                orderings = [[h_a["id"], h_b["id"]]]
                score_a = 1.0 if v1["winner_id"] == h_a["id"] else 0.0

            verdicts.extend(match_verdicts)
            ratings[h_a["id"]], ratings[h_b["id"]] = tournament.elo_update(
                ratings[h_a["id"]], ratings[h_b["id"]], score_a
            )
            elo_after = {pid: ratings[pid] for pid in pair_ids}

            match_log.append(
                tournament.build_match_record(
                    pair_ids,
                    tier,
                    orderings,
                    [v["winner_id"] for v in match_verdicts],
                    [v["reason"] for v in match_verdicts],
                    elo_before,
                    elo_after,
                )
            )
            _log(
                run_id,
                f"STAGE1_TOURNAMENT match {pair_ids[0]}_vs_{pair_ids[1]} tier={tier} "
                f"orderings={orderings} verdicts={[v['winner_id'] for v in match_verdicts]} "
                f"elo_before={elo_before} elo_after={elo_after}",
            )

        ranked_survivors = tournament.final_ranking(ratings, tournament_pool, flags)
        state = tournament.build_state(
            rng_seed, ratings, match_log, ids, matrix, flags, ranked_survivors
        )
        (round_dir / "tournament_state.json").write_text(json.dumps(state, indent=2))
        _log(run_id, f"STAGE1_TOURNAMENT final_elo: {ratings}")
        ranking_note = (
            f"ranked via Elo tournament: {len(matches)} matches "
            f"({debate_count} debate, {len(matches) - debate_count} single-turn)"
        )
        statements_by_id = {s["id"]: s["statement"] for s in tournament_pool}
        tournament_resolved = resolve_tournament_to_statements(state, statements_by_id)
        ranking_resolved = tournament_resolved["final_ranking"]

    (round_dir / "ranking.json").write_text(json.dumps(verdicts, indent=2))

    return {
        "hypotheses": hypotheses,
        "review_summary": review_summary,
        "survivors_full": survivors_full,
        "accepted_variants": accepted_variants,
        "ranked_survivors": ranked_survivors,
        "ranking_note": ranking_note,
        "tournament_resolved": tournament_resolved,
        "ranking_resolved": ranking_resolved,
    }


def _run_quick(baton: Baton) -> Baton:
    """QUICK ideation (depth='quick') — the cheap path. ONE generation strategy
    (literature_exploration) delivered directly, with NO reflection, tournament,
    evolution, or rounds. The full Co-Scientist apparatus is depth='full' and is
    chosen only when the PI or the human asks for the spend
    (docs/architecture_collapse_manifest.md §2/§4). Same delivered contract
    {hypotheses, hypotheses_ranked} so gate 1 and everything downstream are
    unchanged; the order is generation order — a cheap ordering, not a tournament
    ranking. Memory read and literature grounding mirror the full path exactly."""
    domain = baton.payload["domain"]
    run_dir = Path("runs") / baton.run_id / "stage1"
    run_dir.mkdir(parents=True, exist_ok=True)

    memory_entries = journal_recent_by_kind("learned_summary", 3)
    (run_dir / "retrieved_memory.json").write_text(json.dumps(memory_entries, indent=2))
    memory_block = build_memory_block(memory_entries)
    _log(
        baton.run_id,
        f"STAGE1_MEMORY retrieved {len(memory_entries)} learned_summary entries",
    )

    literature_refs = gather_literature_evidence(baton.run_id, domain, run_dir)
    candidates, _number_warnings = strategy_literature_exploration(
        baton.run_id, domain, literature_refs, memory_block
    )
    hypotheses = [
        {"id": f"h{n}", "statement": c["statement"], "rationale": c["rationale"]}
        for n, c in enumerate(candidates, start=1)
    ]
    (run_dir / "quick_ideation.json").write_text(
        json.dumps({"domain": domain, "depth": "quick", "hypotheses": hypotheses}, indent=2)
    )
    _log(
        baton.run_id,
        f"STAGE1_QUICK depth=quick: {len(hypotheses)} literature-grounded "
        "hypotheses (one strategy; no reflection/tournament/evolution/rounds)",
    )

    baton.payload["hypotheses"] = hypotheses
    baton.payload["hypotheses_ranked"] = True
    baton.add_history(
        "stage1_ideation",
        f"quick ideation (depth=quick): {len(hypotheses)} literature-grounded "
        "hypotheses, no reflection/tournament/evolution",
    )
    return baton


def run(baton: Baton, rounds: int | None = None, depth: str = "full") -> Baton:
    """depth='full' (default) runs the whole Co-Scientist apparatus; depth='quick'
    runs one literature-grounded generation and delivers it directly (the PI or
    the human chooses per docs/architecture_collapse_manifest.md). The default
    stays 'full' so existing callers/tests are byte-behaviour-unchanged; the
    supervisor/PI wiring that makes 'quick' the runtime default is the next step."""
    if depth not in ("quick", "full"):
        raise ValueError(f"depth must be 'quick' or 'full', got {depth!r}")
    if depth == "quick":
        return _run_quick(baton)

    rounds = ROUNDS if rounds is None else rounds
    domain = baton.payload["domain"]
    run_dir = Path("runs") / baton.run_id / "stage1"
    run_dir.mkdir(parents=True, exist_ok=True)

    # --- Journal read-side (deterministic, before any model call; ONCE per
    # run, OUTSIDE the round loop — the battery's memory-comparability md5
    # pin means exactly this single read) ---
    memory_entries = journal_recent_by_kind("learned_summary", 3)
    (run_dir / "retrieved_memory.json").write_text(json.dumps(memory_entries, indent=2))
    memory_block = build_memory_block(memory_entries)
    _log(
        baton.run_id,
        f"STAGE1_MEMORY retrieved {len(memory_entries)} learned_summary entries",
    )

    # --- Iteration controller (Step 17-E; see the module docstring) ---
    prior_critique: dict | None = None
    prior_overview: dict | None = None
    prior_tournament_resolved: dict | None = None
    last_round: dict | None = None
    rounds_completed = 0
    termination_reason = None

    for round_index in range(1, rounds + 1):
        _log(baton.run_id, f"STAGE1_ROUNDS round {round_index} of {rounds} begins")
        round_dir = run_dir / f"round{round_index}"
        round_dir.mkdir(parents=True, exist_ok=True)

        gen_block = compose_feedback_block(
            "generation",
            prior_critique["feedback_to_generation"] if prior_critique else [],
            round_index,
            overview=prior_overview,
        )
        refl_block = compose_feedback_block(
            "reflection",
            prior_critique["feedback_to_reflection"] if prior_critique else [],
            round_index,
        )
        rank_block = compose_feedback_block(
            "ranking",
            prior_critique["feedback_to_ranking"] if prior_critique else [],
            round_index,
        )

        try:
            round_result = _run_round(
                baton.run_id,
                domain,
                memory_block,
                round_dir,
                round_index,
                gen_block,
                refl_block,
                rank_block,
                prior_tournament_resolved,
            )
        except RuntimeError as exc:
            if round_index == 1 or not _is_zero_survivor_error(exc):
                # Round 1 crashes honestly exactly as the single-pass stage
                # always did; any non-zero-survivor failure crashes in every
                # round — the tolerance is ONLY for a later round finding
                # nothing when an earlier round already stands.
                raise
            termination_reason = "zero_survivors_terminated"
            _log(
                baton.run_id,
                f"STAGE1_ROUNDS round {round_index} produced zero survivors — "
                f"terminating, standing on round {rounds_completed}: "
                f"{str(exc).splitlines()[0]}",
            )
            append_rounds_entry(
                run_dir,
                {
                    "round": round_index,
                    "pool_statements": [],
                    "k": 0,
                    "ranking": [],
                    "meta_review": None,
                    "termination_reason": termination_reason,
                },
            )
            break

        # Round succeeded: promote its artifacts to the canonical stage1/
        # set (canonical files = LAST SUCCESSFUL round, so a later failed
        # round can never corrupt what downstream and the battery read).
        for artifact in sorted(round_dir.glob("*.json")):
            shutil.copy2(artifact, run_dir / artifact.name)
        rounds_completed = round_index
        last_round = round_result

        # --- Meta-review, at EVERY round boundary including the final one
        # (the final round's critique is recorded but unconsumed — the
        # final overview is the end-of-run synthesis). The whole feedback
        # path is under the never-crash rule: a composition failure — like
        # a call failure inside build_meta_review — degrades to the empty
        # feedback object, logged and recorded, never a dead run. ---
        try:
            reviews_path = round_dir / "reflection_reviews.json"
            variants_path = round_dir / "evolution_variants.json"
            reflection_evidence = (
                json.loads(reviews_path.read_text()) if reviews_path.exists() else {}
            )
            evolution_records = (
                json.loads(variants_path.read_text()) if variants_path.exists() else []
            )
            round_record = compose_round_record(
                round_index,
                domain,
                round_result["hypotheses"],
                reflection_evidence,
                [s["id"] for s in round_result["survivors_full"]],
                evolution_records,
                round_result["tournament_resolved"],
            )
            critique = build_meta_review(baton.run_id, round_index, round_record)
        except Exception as exc:
            reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            _log(
                baton.run_id,
                f"STAGE1_METAREVIEW round {round_index} composition FAILED "
                f"(recorded, empty feedback, run proceeds): {reason}",
            )
            critique = empty_feedback(f"round-record composition failed: {reason}")
        (run_dir / "research_overview.json").write_text(
            json.dumps(
                {"round": round_index, **critique["research_overview"]}, indent=2
            )
        )

        if round_index == rounds:
            termination_reason = "round_budget_exhausted"
        elif len(round_result["survivors_full"]) >= MAX_SURVIVORS:
            termination_reason = "survivor_count_cap"

        append_rounds_entry(
            run_dir,
            {
                "round": round_index,
                "pool_statements": [h["statement"] for h in round_result["hypotheses"]],
                "k": len(round_result["survivors_full"]),
                "ranking": round_result["ranking_resolved"],
                "meta_review": critique,
                "termination_reason": termination_reason,
            },
        )

        if termination_reason:
            _log(
                baton.run_id,
                f"STAGE1_ROUNDS terminated after round {round_index}: {termination_reason}",
            )
            break

        prior_critique = critique
        prior_overview = critique["research_overview"]
        prior_tournament_resolved = round_result["tournament_resolved"]

    # The delivered object comes from the LAST SUCCESSFUL round — identical
    # shape to every pre-17-E run.
    lr = last_round
    baton.payload["hypotheses"] = [
        {"id": s["id"], "statement": s["statement"], "rationale": s["rationale"]}
        for s in lr["ranked_survivors"]
    ]
    baton.payload["hypotheses_ranked"] = True

    baton.add_history(
        "stage1_ideation",
        f"{rounds_completed} round(s), termination {termination_reason}; "
        f"final round: generated {len(lr['hypotheses'])} across 4 strategies, "
        f"{lr['review_summary']['initial_pass']} passed initial review, "
        f"{lr['review_summary']['reflected']} exited six-review reflection, "
        f"{len(lr['survivors_full'])} survived filter, {lr['ranking_note']}",
    )
    return baton
