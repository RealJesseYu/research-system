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
step-wise simulation review surfacing failure scenarios, and (6) an inert
recurrent/tournament-review seam awaiting the tournament chunk. The result
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
import random
from pathlib import Path

from baton import Baton
from memory.journal import journal_recent_by_kind
from model_call import call_stage_model, log_stage_call
from stages import tournament
from stages.generation_strategies import generate_candidate_pool
from stages.reflection_reviews import reflect_on_pool

OPUS_MODEL = "claude-opus-4-8"

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
    "better. Reply ONLY with JSON of the form "
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
    "better. Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"winner_id": "<the id of the hypothesis you judge more promising>", '
    '"reason": "<one decisive sentence>"}.'
)

MAX_SURVIVORS = 4

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
    """Pure-Python, no model call: discard 'known' reflections, keep at most
    MAX_SURVIVORS by quality (highest first), ties broken by original
    (generation) order. Raises RuntimeError if nothing survives — an honest
    failure, not padded with anything to keep the run alive.
    """
    novel = [(i, r) for i, r in enumerate(reflections) if r["novelty"] == "novel"]
    if not novel:
        raise RuntimeError(
            f"stage1_ideation: all {len(reflections)} hypotheses were judged 'known' "
            "against the literature. Zero survivors — there is no validated hypothesis "
            "to hand to experiment design, so this run halts here rather than continuing "
            "on a hypothesis nobody vetted as novel."
        )
    novel.sort(key=lambda pair: (-pair[1]["quality"], pair[0]))
    return [r for _, r in novel[:MAX_SURVIVORS]]


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


def _single_turn_judge(run_id: str, domain: str, h_a: dict, h_b: dict) -> dict:
    """One Opus judge call for a non-top-2 match (J2), presented in the
    (h_a, h_b) order the caller randomized. Returns a verdict in ranking.json's
    exact historical shape: {pair, ack_run_id, winner_id, reason}."""
    pair_name = f"{h_a['id']}_vs_{h_b['id']}"
    rank_input = {
        "run_id": run_id,
        "domain": domain,
        "hypothesis_a": _judge_view(h_a),
        "hypothesis_b": _judge_view(h_b),
    }
    rank_schema = {
        "required": ["ack_run_id", "winner_id", "reason"],
        "enums": {"winner_id": [h_a["id"], h_b["id"]]},
    }
    rank_data, rank_timing = call_stage_model(
        "stage1_tournament_judge",
        RANKING_SYSTEM_PROMPT_V2,
        rank_input,
        rank_schema,
        model=OPUS_MODEL,
    )
    _check_verdict(rank_data, run_id, h_a, h_b, f"tournament judge {pair_name}")
    log_stage_call(run_id, "stage1_tournament_judge", rank_timing)
    return {
        "pair": [h_a["id"], h_b["id"]],
        "ack_run_id": rank_data["ack_run_id"],
        "winner_id": rank_data["winner_id"],
        "reason": rank_data["reason"],
    }


def _debate_once(run_id: str, domain: str, h_a: dict, h_b: dict) -> dict:
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
        data, timing = call_stage_model(
            f"stage1_tournament_debate_turn{turn}",
            DEBATE_ADVOCATE_SYSTEM_PROMPT,
            stage_input,
            {"required": ["ack_run_id", "argument"]},
            model=OPUS_MODEL,
            extra_validator=argument_validator,
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
    judge_schema = {
        "required": ["ack_run_id", "winner_id", "reason"],
        "enums": {"winner_id": [h_a["id"], h_b["id"]]},
    }
    judge_data, judge_timing = call_stage_model(
        "stage1_tournament_debate_turn3",
        DEBATE_JUDGE_SYSTEM_PROMPT,
        judge_input,
        judge_schema,
        model=OPUS_MODEL,
    )
    _check_verdict(judge_data, run_id, h_a, h_b, f"debate judge {pair_name}")
    log_stage_call(run_id, "stage1_tournament_debate_turn3", judge_timing)
    return {
        "pair": [h_a["id"], h_b["id"]],
        "ack_run_id": judge_data["ack_run_id"],
        "winner_id": judge_data["winner_id"],
        "reason": judge_data["reason"],
    }


def run(baton: Baton) -> Baton:
    domain = baton.payload["domain"]
    run_dir = Path("runs") / baton.run_id / "stage1"
    run_dir.mkdir(parents=True, exist_ok=True)

    # --- Journal read-side (deterministic, before any model call) ---
    memory_entries = journal_recent_by_kind("learned_summary", 3)
    (run_dir / "retrieved_memory.json").write_text(json.dumps(memory_entries, indent=2))
    memory_block = build_memory_block(memory_entries)
    _log(
        baton.run_id,
        f"STAGE1_MEMORY retrieved {len(memory_entries)} learned_summary entries",
    )

    # --- Generation (Step 17: the four Co-Scientist strategies; every model
    # call, retrieval, evidence write, and the pool's canonical h1..hN ids
    # live in stages/generation_strategies.py) ---
    pool = generate_candidate_pool(baton.run_id, domain, memory_block, run_dir)
    hypotheses = [
        {"id": c["id"], "statement": c["statement"], "rationale": c["rationale"]}
        for c in pool
    ]

    # --- Reflection (Step 17: the six Co-Scientist review types; every model
    # call, per-hypothesis retrieval, evidence write, and both deterministic
    # discard rules live in stages/reflection_reviews.py; the returned
    # reflection objects keep the exact {hypothesis_id, novelty, critique,
    # quality} contract the filter below has consumed since Step 8) ---
    reflections, review_summary = reflect_on_pool(
        baton.run_id, domain, hypotheses, memory_block, run_dir
    )
    (run_dir / "reflections.json").write_text(json.dumps(reflections, indent=2))

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
    (run_dir / "survivors.json").write_text(json.dumps(survivors_full, indent=2))

    # --- Ranking (Step 17-C: Elo tournament — pure math in
    # stages/tournament.py, Opus judgments through the helpers above) ---
    k = len(survivors_full)
    verdicts: list[dict] = []

    if k == 1:
        _log(baton.run_id, "STAGE1_RANKING ranking trivial (k=1)")
        ranked_survivors = survivors_full
        ranking_note = "ranking trivial (k=1)"
    else:
        rng_seed = baton.run_id
        rng = random.Random(rng_seed)
        _log(
            baton.run_id,
            f"STAGE1_TOURNAMENT rng_seed={rng_seed} "
            f"elo_init={tournament.ELO_INIT} k_factor={tournament.K_FACTOR}",
        )

        ratings = {s["id"]: tournament.ELO_INIT for s in survivors_full}
        ids = [s["id"] for s in survivors_full]
        matrix = tournament.proximity_matrix(survivors_full)
        flags = tournament.dedup_flags(matrix)
        for fi, fj, sim in flags:
            _log(
                baton.run_id,
                f"STAGE1_TOURNAMENT dedup_flag {ids[fi]}_vs_{ids[fj]} sim={sim:.3f}",
            )
        matches = tournament.order_matches(
            list(itertools.combinations(range(k), 2)), matrix
        )

        match_log: list[dict] = []
        debate_count = 0
        for i, j in matches:
            h_i, h_j = survivors_full[i], survivors_full[j]
            pair_ids = [h_i["id"], h_j["id"]]
            # Randomized A/B presentation, reproducible from the logged seed.
            h_a, h_b = (h_i, h_j) if rng.random() < 0.5 else (h_j, h_i)

            top2 = _live_top2(ratings, survivors_full)
            tier = (
                "debate"
                if h_i["id"] in top2 and h_j["id"] in top2
                else "single_turn"
            )
            elo_before = {pid: ratings[pid] for pid in pair_ids}

            if tier == "debate":
                debate_count += 1
                v1 = _debate_once(baton.run_id, domain, h_a, h_b)
                v2 = _debate_once(baton.run_id, domain, h_b, h_a)
                match_verdicts = [v1, v2]
                orderings = [[h_a["id"], h_b["id"]], [h_b["id"], h_a["id"]]]
                score_a = tournament.debate_score(
                    h_a["id"], h_b["id"], v1["winner_id"], v2["winner_id"]
                )
            else:
                v1 = _single_turn_judge(baton.run_id, domain, h_a, h_b)
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
                baton.run_id,
                f"STAGE1_TOURNAMENT match {pair_ids[0]}_vs_{pair_ids[1]} tier={tier} "
                f"orderings={orderings} verdicts={[v['winner_id'] for v in match_verdicts]} "
                f"elo_before={elo_before} elo_after={elo_after}",
            )

        ranked_survivors = tournament.final_ranking(ratings, survivors_full, flags)
        (run_dir / "tournament_state.json").write_text(
            json.dumps(
                tournament.build_state(
                    rng_seed, ratings, match_log, ids, matrix, flags, ranked_survivors
                ),
                indent=2,
            )
        )
        _log(baton.run_id, f"STAGE1_TOURNAMENT final_elo: {ratings}")
        ranking_note = (
            f"ranked via Elo tournament: {len(matches)} matches "
            f"({debate_count} debate, {len(matches) - debate_count} single-turn)"
        )

    (run_dir / "ranking.json").write_text(json.dumps(verdicts, indent=2))

    baton.payload["hypotheses"] = [
        {"id": s["id"], "statement": s["statement"], "rationale": s["rationale"]}
        for s in ranked_survivors
    ]
    baton.payload["hypotheses_ranked"] = True

    baton.add_history(
        "stage1_ideation",
        f"generated {len(hypotheses)} across 4 strategies, "
        f"{review_summary['initial_pass']} passed initial review, "
        f"{review_summary['reflected']} exited six-review reflection, "
        f"{len(survivors_full)} survived filter, {ranking_note}",
    )
    return baton
