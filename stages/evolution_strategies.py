"""
evolution_strategies.py — the Co-Scientist Evolution agent for Step 17-D.
Called only by stages/stage1_ideation.py at the ruled seam: after the
survivors.json write, before tournament sizing. Everything upstream
(Generation, Reflection, the deterministic filter) and the tournament
machinery itself (stages/tournament.py) are untouched.

Evolution takes the run's FINALIZED parents (the filter's survivors) and
emits up to EVOLUTION_MAX_VARIANTS candidate variants, each via ONE Sonnet
call (EVOLUTION_MODEL — an explicit ruled pin, independent of Generation's
Step-18.7 Haiku downgrade), through the same call_stage_model door as every
other stage-1 call. The four strategies (faithful to Co-Scientist's
Evolution agent):
  - simplification — the parent's core claim stripped to its simplest,
    most directly testable form. ALWAYS variant 1, on the top parent.
  - grounding_enhancement — tighten the parent's claim toward what live
    retrieved literature actually supports. Retrieval is BEST-EFFORT
    OpenAlex (a ruled exception: unlike Generation/Reflection, where
    OpenAlex is hard-required, Evolution retrieval NEVER aborts a run —
    failure or zero hits means no grounding delta, recorded in the log).
  - combination — one coherent hypothesis drawing on the two top parents'
    strongest elements. Needs >= 2 parents.
  - out_of_box — the parent's core idea taken in a genuinely unexpected
    direction (inverted assumption, different regime, cross-domain analogy).

Runtime policy (exact, ruled): variant 1 is ALWAYS simplification of the
top parent; variant 2's strategy rotates deterministically over
[grounding_enhancement, combination, out_of_box] using an INDEPENDENT RNG,
random.Random(f"{run_id}:evolution") — never the tournament RNG (seeded
run_id alone). If rotation lands on combination with fewer than 2 parents,
variant 2 falls back to out_of_box and the fallback is logged.

Variants get new ids ev1, ev2 — the "ev" prefix can never collide with the
pool's canonical h1..hN parent ids — and each record carries provenance
{parent_ids, strategy, model}. Emitted variants are then reviewed by the
SAME Reflection machinery Generation output goes through (imported from
stages/reflection_reviews.py, zero edits there): initial review over the
variant mini-pool, then per initial survivor the full chain —
gather_review_refs, full_review, deep_verification_review,
observation_review, simulation_review — on their existing model pins, then
the same deterministic consequences (fundamental_flaw discards; the
filter's novelty rule: 'known' discards).

EVOLUTION MUST NEVER CRASH A RUN: an emission failure or a review failure
(including reflection retrieval's hard-required sources failing) degrades
to a recorded rejection in stage1/evolution_variants.json — one record per
emitted variant carrying the 7 survivor fields (review-derived fields null
where review didn't reach them) + provenance + accepted + reject_reason.
ZERO-ACCEPT TOLERANCE: when no variant survives, the run proceeds over the
parents alone — recorded, never raised (filter_survivors' raise-on-empty
applies to Generation survivors only). Accepted variants join an IN-MEMORY
tournament pool in stage1_ideation; survivors_full and survivors.json are
never mutated.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from model_call import FULL, call_stage_model, log_stage_call
from stages.reflection_reviews import (
    deep_verification_review,
    full_review,
    gather_review_refs,
    initial_review,
    observation_review,
    simulation_review,
)

_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
if str(_RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_DIR))

from scholar_search import search_openalex  # noqa: E402

# Explicit ruled pin: Evolution emits on Sonnet regardless of Generation's
# Step-18.7 Haiku downgrade — variant authorship is judged worth the tier.
EVOLUTION_MODEL = "claude-opus-4-8"
EVOLUTION_MAX_VARIANTS = 2

# Variant 2's strategy rotates over these; variant 1 is always simplification.
ROTATION_STRATEGIES = ("grounding_enhancement", "combination", "out_of_box")

TOP_K_PER_SOURCE = 3

# Sibling of generation_strategies.NO_INVENTED_NUMBERS_INSTRUCTION, adapted
# to Evolution's inputs: a variant's numeric support is its PARENT (already
# reviewed) or, for grounding_enhancement, a provided snippet — never a
# freshly remembered figure.
NO_NEW_NUMBERS_INSTRUCTION = (
    "Do NOT state a specific numeric value (an exponent, threshold, ratio, percentage, or "
    "dimensioned constant) unless the parent hypothesis or a provided literature snippet "
    "already states that exact value. If you have no such support for a number, express "
    "the claim qualitatively or directionally (e.g. 'increases with', 'is smaller than') "
    "instead of inventing a figure. "
)

_REPLY_FORMAT = (
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"statement": "<one sentence>", "rationale": "<one sentence>"}.'
)

SIMPLIFICATION_SYSTEM_PROMPT = (
    "You are the simplification evolution strategy inside the Ideation stage of an "
    "autonomous research pipeline. You are given a research domain and ONE parent "
    "hypothesis that already survived review. Produce exactly ONE simplified variant of "
    "it: keep the parent's core claim but strip it to its simplest, most directly "
    "testable form — drop compound conditions, secondary mechanisms, and qualifiers a "
    "single simulation cannot resolve, so the claim can be tested more cleanly than the "
    "parent. The variant must remain concrete enough to be tested by a simulation and "
    "must not collapse into a trivial restatement of textbook fact. "
    + NO_NEW_NUMBERS_INSTRUCTION
    + _REPLY_FORMAT
)

GROUNDING_SYSTEM_PROMPT = (
    "You are the grounding-enhancement evolution strategy inside the Ideation stage of "
    "an autonomous research pipeline. You are given a research domain, ONE parent "
    "hypothesis that already survived review, and literature snippets retrieved live for "
    "it, each tagged with a ref id (the list may be empty). Produce exactly ONE variant "
    "that strengthens the parent's grounding: tighten its claim toward what the provided "
    "snippets actually support and sharpen its testable content, keeping it concrete "
    "enough to be tested by a simulation. When the snippet list is empty, sharpen the "
    "parent's testable grounding qualitatively without inventing citations or results. "
    + NO_NEW_NUMBERS_INSTRUCTION
    + _REPLY_FORMAT
)

COMBINATION_SYSTEM_PROMPT = (
    "You are the combination evolution strategy inside the Ideation stage of an "
    "autonomous research pipeline. You are given a research domain and TWO OR MORE "
    "parent hypotheses that already survived review. Produce exactly ONE variant that "
    "combines the parents' strongest elements into a single coherent hypothesis — one "
    "claim about one mechanism drawing on both parents, not a conjunction of their "
    "claims — concrete enough to be tested by a single simulation. "
    + NO_NEW_NUMBERS_INSTRUCTION
    + _REPLY_FORMAT
)

OUT_OF_BOX_SYSTEM_PROMPT = (
    "You are the out-of-the-box evolution strategy inside the Ideation stage of an "
    "autonomous research pipeline. You are given a research domain and ONE parent "
    "hypothesis that already survived review. Produce exactly ONE variant that takes "
    "the parent's core idea in a genuinely unexpected direction — invert one of its "
    "assumptions, move it to a different regime, or apply an analogy from another "
    "physical setting — while staying within the research domain and concrete enough "
    "to be tested by a simulation. "
    + NO_NEW_NUMBERS_INSTRUCTION
    + _REPLY_FORMAT
)

# The 7 survivor fields every evolution_variants.json record carries
# (survivors.json's exact field set; review-derived ones stay null when
# review didn't reach them).
_SURVIVOR_FIELDS = (
    "id", "statement", "rationale", "novelty", "critique", "quality",
    "addressable_notes",
)


def _log(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt.

    Mirrors stage1_ideation._log — stages and their helpers never hold the
    supervisor's Logger object, so the run-log path is rebuilt from run_id
    alone, same as model_call.py / generation_strategies.py /
    reflection_reviews.py do.
    """
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def _check_ack(data: dict, run_id: str, what: str) -> None:
    """Raise on ack_run_id mismatch; log the pass — same pattern as every
    existing stage-1 ack check."""
    if data["ack_run_id"] != run_id:
        raise RuntimeError(
            f"stage1 evolution {what}: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {run_id!r}"
        )
    _log(run_id, f"STAGE1_ACK_CHECK evolution {what}: ack_run_id passed")


def _variant_validator(data: dict) -> list[str]:
    """Shared shape check for every emission reply: statement and rationale
    must be non-empty strings (the same field checks Generation's
    _entry_field_errors applies, on a single object)."""
    errors: list[str] = []
    for field in ("statement", "rationale"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string.")
    return errors


def _parent_view(parent: dict) -> dict:
    """What an emission strategy sees of one parent: id, statement,
    rationale — never critique/quality (review internals stay out of
    authorship inputs, same altitude as the tournament's _judge_view)."""
    return {
        "id": parent["id"],
        "statement": parent["statement"],
        "rationale": parent["rationale"],
    }


# --- The four strategies ------------------------------------------------------


def simplification(run_id: str, domain: str, parent: dict) -> dict:
    """One Sonnet call: the parent's core claim in its simplest, most
    directly testable form. Returns {statement, rationale}."""
    data, timing = call_stage_model(
        "stage1_evolution_simplification",
        SIMPLIFICATION_SYSTEM_PROMPT,
        {"run_id": run_id, "domain": domain, "parent_hypothesis": _parent_view(parent)},
        {"required": ["ack_run_id", "statement", "rationale"]},
        model=EVOLUTION_MODEL,
        extra_validator=_variant_validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, "simplification")
    log_stage_call(run_id, "stage1_evolution_simplification", timing)
    return {"statement": data["statement"], "rationale": data["rationale"]}


def grounding_enhancement(
    run_id: str, domain: str, parent: dict, refs: list[dict]
) -> dict:
    """One Sonnet call: the parent tightened toward what the provided
    ref-tagged snippets actually support (refs may be empty — the
    best-effort retrieval found nothing). Returns {statement, rationale}."""
    data, timing = call_stage_model(
        "stage1_evolution_grounding",
        GROUNDING_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "domain": domain,
            "parent_hypothesis": _parent_view(parent),
            "literature_snippets": refs,
        },
        {"required": ["ack_run_id", "statement", "rationale"]},
        model=EVOLUTION_MODEL,
        extra_validator=_variant_validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, "grounding_enhancement")
    log_stage_call(run_id, "stage1_evolution_grounding", timing)
    return {"statement": data["statement"], "rationale": data["rationale"]}


def combination(run_id: str, domain: str, parents: list[dict]) -> dict:
    """One Sonnet call: one coherent hypothesis drawing on the parents'
    strongest elements. Requires >= 2 parents — the runtime policy
    (plan_variants) guarantees this; the guard is honesty, not control
    flow. Returns {statement, rationale}."""
    if len(parents) < 2:
        raise ValueError(
            f"combination needs >= 2 parents, got {len(parents)} — plan_variants "
            "should have fallen back to out_of_box"
        )
    data, timing = call_stage_model(
        "stage1_evolution_combination",
        COMBINATION_SYSTEM_PROMPT,
        {
            "run_id": run_id,
            "domain": domain,
            "parent_hypotheses": [_parent_view(p) for p in parents],
        },
        {"required": ["ack_run_id", "statement", "rationale"]},
        model=EVOLUTION_MODEL,
        extra_validator=_variant_validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, "combination")
    log_stage_call(run_id, "stage1_evolution_combination", timing)
    return {"statement": data["statement"], "rationale": data["rationale"]}


def out_of_box(run_id: str, domain: str, parent: dict) -> dict:
    """One Sonnet call: the parent's core idea taken in a genuinely
    unexpected direction. Returns {statement, rationale}."""
    data, timing = call_stage_model(
        "stage1_evolution_out_of_box",
        OUT_OF_BOX_SYSTEM_PROMPT,
        {"run_id": run_id, "domain": domain, "parent_hypothesis": _parent_view(parent)},
        {"required": ["ack_run_id", "statement", "rationale"]},
        model=EVOLUTION_MODEL,
        extra_validator=_variant_validator,
        capabilities=FULL,
    )
    _check_ack(data, run_id, "out_of_box")
    log_stage_call(run_id, "stage1_evolution_out_of_box", timing)
    return {"statement": data["statement"], "rationale": data["rationale"]}


# --- Runtime policy (pure, no model, no I/O) ----------------------------------


def choose_rotation(run_id: str) -> str:
    """Variant 2's strategy, deterministic from run_id via an INDEPENDENT
    RNG seeded f"{run_id}:evolution" — never the tournament RNG (which is
    seeded run_id alone; the ':evolution' suffix keeps the two streams
    decoupled forever)."""
    return random.Random(f"{run_id}:evolution").choice(list(ROTATION_STRATEGIES))


def plan_variants(run_id: str, parents: list[dict]) -> list[dict]:
    """Pure: the exact ruled runtime policy as a plan. Entry shape:
    {slot, strategy, parent_ids} plus fallback_from when rotation landed on
    combination with fewer than 2 parents (the fallback is out_of_box).
    Variant 1 is ALWAYS simplification of the top parent; combination uses
    the top two parents; every other strategy uses the top parent."""
    plan = [
        {
            "slot": 1,
            "strategy": "simplification",
            "parent_ids": [parents[0]["id"]],
        }
    ]
    chosen = choose_rotation(run_id)
    if chosen == "combination" and len(parents) < 2:
        plan.append(
            {
                "slot": 2,
                "strategy": "out_of_box",
                "parent_ids": [parents[0]["id"]],
                "fallback_from": "combination",
            }
        )
    elif chosen == "combination":
        plan.append(
            {
                "slot": 2,
                "strategy": "combination",
                "parent_ids": [p["id"] for p in parents[:2]],
            }
        )
    else:
        plan.append({"slot": 2, "strategy": chosen, "parent_ids": [parents[0]["id"]]})
    return plan[:EVOLUTION_MAX_VARIANTS]


# --- Best-effort grounding retrieval ------------------------------------------


def gather_grounding_refs(run_id: str, parent: dict) -> list[dict]:
    """BEST-EFFORT OpenAlex retrieval for grounding_enhancement — the ruled
    exception to the hard-required OpenAlex policy of Generation/Reflection
    retrieval: Evolution retrieval never aborts a run. The try/except is
    exactly the arXiv best-effort pattern in
    generation_strategies.gather_literature_evidence. Failure or zero hits
    -> [] (no grounding delta), recorded in the log; the strategy proceeds
    without snippets."""
    try:
        records = search_openalex(parent["statement"], top_k=TOP_K_PER_SOURCE)
    except RuntimeError as e:
        _log(
            run_id,
            "STAGE1_EVOLUTION grounding retrieval openalex failed (best-effort, "
            f"no grounding delta, proceeding): {str(e).splitlines()[0]}",
        )
        return []
    _log(
        run_id,
        f"STAGE1_EVOLUTION grounding retrieval openalex={len(records)}"
        + (" — zero hits, no grounding delta" if not records else ""),
    )
    return [{"ref": f"R{n}", **r} for n, r in enumerate(records, start=1)]


def _emit(run_id: str, domain: str, entry: dict, parents_by_id: dict) -> dict:
    """Dispatch one plan entry to its strategy call. Returns
    {statement, rationale}; any exception is the caller's recorded
    rejection, never a crash."""
    strategy = entry["strategy"]
    entry_parents = [parents_by_id[pid] for pid in entry["parent_ids"]]
    if strategy == "simplification":
        return simplification(run_id, domain, entry_parents[0])
    if strategy == "grounding_enhancement":
        refs = gather_grounding_refs(run_id, entry_parents[0])
        return grounding_enhancement(run_id, domain, entry_parents[0], refs)
    if strategy == "combination":
        return combination(run_id, domain, entry_parents)
    return out_of_box(run_id, domain, entry_parents[0])


# --- Orchestrator: emit, review, record ----------------------------------------


def evolve_and_review(
    run_id: str,
    domain: str,
    survivors_full: list[dict],
    memory_block: str | None,
    run_dir: Path,
) -> list[dict]:
    """Emit up to EVOLUTION_MAX_VARIANTS variants from the finalized parents,
    review them with the SAME Reflection machinery Generation output goes
    through, write stage1/evolution_variants.json (the complete record of
    Evolution's output — every run where Evolution runs), and return the
    accepted variants as survivor-shaped dicts ready to join the in-memory
    tournament pool. NEVER raises on emission or review failure — those
    degrade to recorded rejections; zero accepted variants returns [] and
    the run proceeds over the parents alone. `survivors_full` is read-only
    here: parents are never mutated and survivors.json is never rewritten.
    """
    parent_ids = [p["id"] for p in survivors_full]
    parents_by_id = {p["id"]: p for p in survivors_full}
    plan = plan_variants(run_id, survivors_full)
    fallback = plan[1].get("fallback_from") if len(plan) > 1 else None
    _log(
        run_id,
        f"STAGE1_EVOLUTION start parents={parent_ids} seed={run_id}:evolution "
        f"variant1=simplification variant2={plan[1]['strategy'] if len(plan) > 1 else 'none'}"
        + (
            f" (rotation landed on {fallback} with {len(parent_ids)} parent(s) — fell back)"
            if fallback
            else ""
        ),
    )

    records: list[dict] = []
    for entry in plan:
        vid = f"ev{entry['slot']}"
        record = {
            "id": vid,
            "statement": None,
            "rationale": None,
            "novelty": None,
            "critique": None,
            "quality": None,
            "addressable_notes": None,
            "provenance": {
                "parent_ids": entry["parent_ids"],
                "strategy": entry["strategy"],
                "model": EVOLUTION_MODEL,
            },
            "accepted": False,
            "reject_reason": None,
        }
        try:
            emitted = _emit(run_id, domain, entry, parents_by_id)
            record["statement"] = emitted["statement"]
            record["rationale"] = emitted["rationale"]
            _log(
                run_id,
                f"STAGE1_EVOLUTION emitted {vid} strategy={entry['strategy']} "
                f"parents={entry['parent_ids']}",
            )
        except Exception as e:
            record["reject_reason"] = "emission_failed"
            _log(
                run_id,
                f"STAGE1_EVOLUTION emission failed {vid} strategy={entry['strategy']} "
                f"(recorded rejection, run proceeds): {str(e).splitlines()[0]}",
            )
        records.append(record)

    record_by_id = {r["id"]: r for r in records}
    mini_pool = [
        {"id": r["id"], "statement": r["statement"], "rationale": r["rationale"]}
        for r in records
        if r["statement"] is not None
    ]

    if mini_pool:
        try:
            initial = initial_review(run_id, domain, mini_pool)
        except Exception as e:
            initial = None
            for v in mini_pool:
                record_by_id[v["id"]]["reject_reason"] = (
                    f"review_failed: {str(e).splitlines()[0]}"
                )
            _log(
                run_id,
                "STAGE1_EVOLUTION initial review failed (recorded rejections, "
                f"run proceeds): {str(e).splitlines()[0]}",
            )
        if initial is not None:
            verdict_by_id = {r["id"]: r for r in initial}
            for v in mini_pool:
                record = record_by_id[v["id"]]
                verdict = verdict_by_id[v["id"]]
                if verdict["verdict"] == "discard":
                    record["reject_reason"] = (
                        f"initial_review_discard: {verdict['reason']}"
                    )
                    continue
                try:
                    refs, _retrieval_evidence = gather_review_refs(run_id, v)
                    full = full_review(run_id, domain, v, refs)
                    deep = deep_verification_review(run_id, domain, v)
                    observation = observation_review(
                        run_id, domain, v, refs, memory_block
                    )
                    simulation = simulation_review(run_id, domain, v)
                except Exception as e:
                    record["reject_reason"] = (
                        f"review_failed: {str(e).splitlines()[0]}"
                    )
                    _log(
                        run_id,
                        f"STAGE1_EVOLUTION review failed {v['id']} (recorded "
                        f"rejection, run proceeds): {str(e).splitlines()[0]}",
                    )
                    continue
                record["novelty"] = full["novelty"]
                record["critique"] = full["critique"]
                record["quality"] = int(full["quality"])
                record["addressable_notes"] = deep["addressable_notes"]
                _log(
                    run_id,
                    f"STAGE1_EVOLUTION review {v['id']}: novelty={full['novelty']} "
                    f"quality={full['quality']} fundamental_flaw={deep['fundamental_flaw']} "
                    f"accounts_for={observation['accounts_for']} "
                    f"failure_scenarios={len(simulation['failure_scenarios'])}",
                )
                # Deterministic consequences — the same rules Generation
                # candidates face: a fundamental flaw discards; then the
                # filter's novelty rule ('known' discards).
                if deep["fundamental_flaw"]:
                    record["reject_reason"] = f"fundamental_flaw: {deep['summary']}"
                elif full["novelty"] != "novel":
                    record["reject_reason"] = "judged_known"
                else:
                    record["accepted"] = True

    for r in records:
        _log(
            run_id,
            f"STAGE1_EVOLUTION outcome {r['id']} accepted={r['accepted']}"
            + (f" reject_reason={r['reject_reason']}" if r["reject_reason"] else ""),
        )

    (run_dir / "evolution_variants.json").write_text(json.dumps(records, indent=2))

    accepted = [
        {field: r[field] for field in _SURVIVOR_FIELDS}
        for r in records
        if r["accepted"]
    ]
    if not accepted:
        _log(
            run_id,
            "STAGE1_EVOLUTION zero variants accepted — proceeding over parents alone",
        )
    return accepted
