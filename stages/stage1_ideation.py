"""
stage1_ideation.py — real Ideation stage: Generation + Reflection + a
deterministic novelty/quality filter + Ranking, backed by Sonnet for
Generation/Reflection and Opus for Ranking (a hard judgment call, per
CLAUDE.md's model roles).

Generation asks Sonnet for six hypotheses grounded in three literature
snippets retrieved for the domain (deterministic TF-IDF search, no model
involved in retrieval itself). Reflection then asks Sonnet, once per
hypothesis and with three snippets retrieved for that hypothesis
specifically, to judge novelty and quality. A pure-Python filter (no model
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
construction-level isolation. Ranking and every other stage get nothing.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

from baton import Baton
from memory.journal import journal_recent_by_kind
from model_call import call_stage_model, log_stage_call

_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
if str(_RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_DIR))

from search import search_index  # noqa: E402 (path must be set up first)

SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-8"

GENERATION_SYSTEM_PROMPT = (
    "You are the Ideation stage of an autonomous research pipeline. You are given a "
    "research domain and a handful of literature snippets retrieved for it. Propose "
    "exactly six hypotheses that are grounded in that literature without merely "
    "restating it, each one concrete enough to be tested by a simulation. "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", "hypotheses": '
    '[{"id": "h1", "statement": "<one sentence>", "rationale": "<one sentence>"}, '
    "... exactly 6 such objects total]}."
)

GENERATION_SCHEMA = {"required": ["ack_run_id", "hypotheses"]}

REFLECTION_SYSTEM_PROMPT = (
    "You are a critical-reviewer stage in an autonomous research pipeline, judging one "
    "proposed hypothesis at a time. You are given that hypothesis plus literature "
    "snippets retrieved specifically for it. Judge its novelty strictly against those "
    "snippets and your own general knowledge, and rate its quality for simulation-based "
    "study from 1 (weak) to 5 (strong). "
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"hypothesis_id": "<the hypothesis id you were given>", '
    '"novelty": "novel" or "known", "critique": "<one sentence>", "quality": <integer 1-5>}.'
)

REFLECTION_SCHEMA = {
    "required": ["ack_run_id", "hypothesis_id", "novelty", "critique", "quality"],
    "enums": {"novelty": ["novel", "known"]},
}

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


def _format_snippets(results: list[dict]) -> list[dict]:
    """Reduce raw search_index() results to the fields worth showing a model."""
    return [{"title": r["title"], "source": r["source"], "snippet": r["snippet"]} for r in results]


def _validate_hypotheses_shape(hypotheses) -> None:
    if not isinstance(hypotheses, list) or len(hypotheses) != 6:
        raise RuntimeError(
            f"stage1_ideation generation: expected exactly 6 hypotheses, got {hypotheses!r}"
        )
    seen_ids = set()
    for h in hypotheses:
        if not isinstance(h, dict) or not all(k in h for k in ("id", "statement", "rationale")):
            raise RuntimeError(f"stage1_ideation generation: malformed hypothesis entry {h!r}")
        if h["id"] in seen_ids:
            raise RuntimeError(f"stage1_ideation generation: duplicate hypothesis id {h['id']!r}")
        seen_ids.add(h["id"])


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

    # --- Generation ---
    lit_snippets = search_index("literature", domain, top_k=3)
    gen_input = {
        "run_id": baton.run_id,
        "domain": domain,
        "literature_snippets": _format_snippets(lit_snippets),
    }
    if memory_block is not None:
        gen_input["prior_observations"] = memory_block
    gen_data, gen_timing = call_stage_model(
        "stage1_ideation_generation",
        GENERATION_SYSTEM_PROMPT,
        gen_input,
        GENERATION_SCHEMA,
        model=SONNET_MODEL,
    )

    if gen_data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage1_ideation generation: ack_run_id mismatch — got "
            f"{gen_data['ack_run_id']!r}, expected {baton.run_id!r}"
        )
    _log(baton.run_id, "STAGE1_ACK_CHECK generation: ack_run_id passed")
    log_stage_call(baton.run_id, "stage1_ideation_generation", gen_timing)

    hypotheses = gen_data["hypotheses"]
    _validate_hypotheses_shape(hypotheses)
    (run_dir / "generation.json").write_text(json.dumps(gen_data, indent=2))

    # --- Reflection ---
    reflections = []
    for h in hypotheses:
        ref_snippets = search_index("literature", h["statement"], top_k=3)
        ref_input = {
            "run_id": baton.run_id,
            "hypothesis_id": h["id"],
            "hypothesis_statement": h["statement"],
            "hypothesis_rationale": h["rationale"],
            "literature_snippets": _format_snippets(ref_snippets),
        }
        if memory_block is not None:
            ref_input["prior_observations"] = memory_block
        ref_data, ref_timing = call_stage_model(
            f"stage1_ideation_reflection_{h['id']}",
            REFLECTION_SYSTEM_PROMPT,
            ref_input,
            REFLECTION_SCHEMA,
            model=SONNET_MODEL,
        )

        if ref_data["ack_run_id"] != baton.run_id:
            raise RuntimeError(
                f"stage1_ideation reflection {h['id']}: ack_run_id mismatch — got "
                f"{ref_data['ack_run_id']!r}, expected {baton.run_id!r}"
            )
        _log(baton.run_id, f"STAGE1_ACK_CHECK reflection {h['id']}: ack_run_id passed")

        if ref_data["hypothesis_id"] != h["id"]:
            raise RuntimeError(
                f"stage1_ideation reflection {h['id']}: hypothesis_id mismatch — got "
                f"{ref_data['hypothesis_id']!r}, expected {h['id']!r}"
            )
        _log(baton.run_id, f"STAGE1_ACK_CHECK reflection {h['id']}: hypothesis_id passed")

        quality = ref_data["quality"]
        if isinstance(quality, bool) or not isinstance(quality, (int, float)) or not (1 <= quality <= 5):
            raise RuntimeError(
                f"stage1_ideation reflection {h['id']}: quality must be 1-5, got {quality!r}"
            )

        log_stage_call(baton.run_id, f"stage1_ideation_reflection_{h['id']}", ref_timing)

        reflections.append(
            {
                "hypothesis_id": h["id"],
                "novelty": ref_data["novelty"],
                "critique": ref_data["critique"],
                "quality": int(quality),
            }
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
        f"generated {len(hypotheses)}, {len(survivors_full)} survived reflection, {ranking_note}",
    )
    return baton
