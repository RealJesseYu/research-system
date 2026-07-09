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
by quality, ties broken by generation order. Ranking then asks Opus to judge
every unordered pair of survivors once (round-robin); rank is win count,
descending, ties broken by reflection quality then generation order — pure
deterministic Python once the verdicts are in.

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
from pathlib import Path

from baton import Baton
from memory.journal import journal_recent_by_kind
from model_call import call_stage_model, log_stage_call
from stages.generation_strategies import generate_candidate_pool
from stages.reflection_reviews import reflect_on_pool

OPUS_MODEL = "claude-opus-4-8"

RANKING_SYSTEM_PROMPT = (
    "You are a comparative-judge stage in an autonomous research pipeline, evaluating two "
    "candidate hypotheses proposed for a given research domain. Judge only which of the two "
    "is the more promising next simulation experiment, weighing how well-grounded it is, how "
    "testable it is in simulation, and the insight it would yield if confirmed. The order in "
    "which the two hypotheses are presented to you carries no information about which is better. "
    "Reply ONLY with JSON of the form "
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


def _compute_rank(survivors_full: list[dict], verdicts: list[dict]) -> tuple[list[dict], dict]:
    """Pure Python, no model call: rank survivors by descending pairwise win
    count. Ties break by `survivors_full`'s existing order, which is already
    (reflection quality desc, generation order asc) from filter_survivors.
    """
    win_counts = {s["id"]: 0 for s in survivors_full}
    for v in verdicts:
        win_counts[v["winner_id"]] += 1
    order = sorted(range(len(survivors_full)), key=lambda i: (-win_counts[survivors_full[i]["id"]], i))
    return [survivors_full[i] for i in order], win_counts


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

    # --- Ranking (Opus, round-robin pairwise) ---
    k = len(survivors_full)
    verdicts: list[dict] = []

    if k == 1:
        _log(baton.run_id, "STAGE1_RANKING ranking trivial (k=1)")
        ranked_survivors = survivors_full
        ranking_note = "ranking trivial (k=1)"
    else:
        for i, j in itertools.combinations(range(k), 2):
            h_a = survivors_full[i]
            h_b = survivors_full[j]
            pair_name = f"{h_a['id']}_vs_{h_b['id']}"

            rank_input = {
                "run_id": baton.run_id,
                "domain": domain,
                "hypothesis_a": {"id": h_a["id"], "statement": h_a["statement"], "rationale": h_a["rationale"]},
                "hypothesis_b": {"id": h_b["id"], "statement": h_b["statement"], "rationale": h_b["rationale"]},
            }
            rank_schema = {
                "required": ["ack_run_id", "winner_id", "reason"],
                "enums": {"winner_id": [h_a["id"], h_b["id"]]},
            }
            rank_data, rank_timing = call_stage_model(
                f"stage1_ideation_ranking_{pair_name}",
                RANKING_SYSTEM_PROMPT,
                rank_input,
                rank_schema,
                model=OPUS_MODEL,
            )

            if rank_data["ack_run_id"] != baton.run_id:
                raise RuntimeError(
                    f"stage1_ideation ranking {pair_name}: ack_run_id mismatch — got "
                    f"{rank_data['ack_run_id']!r}, expected {baton.run_id!r}"
                )
            _log(baton.run_id, f"STAGE1_ACK_CHECK ranking {pair_name}: ack_run_id passed")

            winner_id = rank_data["winner_id"]
            if winner_id not in (h_a["id"], h_b["id"]):
                raise RuntimeError(
                    f"stage1_ideation ranking {pair_name}: winner_id {winner_id!r} is not "
                    f"one of the presented ids ({h_a['id']!r}, {h_b['id']!r})"
                )
            _log(baton.run_id, f"STAGE1_ACK_CHECK ranking {pair_name}: winner_id valid ({winner_id})")

            log_stage_call(baton.run_id, f"stage1_ideation_ranking_{pair_name}", rank_timing)

            verdicts.append(
                {
                    "pair": [h_a["id"], h_b["id"]],
                    "ack_run_id": rank_data["ack_run_id"],
                    "winner_id": winner_id,
                    "reason": rank_data["reason"],
                }
            )

        ranked_survivors, win_counts = _compute_rank(survivors_full, verdicts)
        _log(baton.run_id, f"STAGE1_RANKING win_counts: {win_counts}")
        ranking_note = f"ranked via {len(verdicts)} pairwise calls"

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
