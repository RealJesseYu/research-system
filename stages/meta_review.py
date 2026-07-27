"""
meta_review.py — the Co-Scientist Meta-review agent for Step 17-E. Called
only by stages/stage1_ideation.py's iteration controller, at every round
boundary (including after the final round — the last research overview is
the end-of-run synthesis).

build_meta_review fires ONE Opus call (META_REVIEW_MODEL — an explicit
ruled pin: synthesizing a whole round's reviews, debates, and evolution
outcomes into actionable critique is a hard judgment, per CLAUDE.md's model
roles) over a round_record COMPOSED BY CODE from the completed round:
per-hypothesis reflection outcomes (novelty/quality/kill reasons including
deep verification), tournament results with every id already RESOLVED TO
STATEMENTS (including the match log's verdict reasons and debate verdicts,
so recurring debate patterns are derivable from real debate content, not
just win/loss), evolution outcomes with reject reasons, dedup flags, and
the STANDING_PATTERN the pipeline's operators watch for. The output is the
round's meta-review critique: recurring patterns, per-family feedback
lists, and the research overview.

FEEDBACK MUST NEVER CRASH A RUN: a call failure or validation exhaustion is
logged and recorded, and build_meta_review returns the empty feedback
object — the next round simply proceeds with nothing to apply.

compose_feedback_block turns one family's feedback items into the
deterministic labeled text block the stages receive (code-authored framing
per family; round 1 gets an explicit empty block; Generation's block
additionally carries the prior round's research-overview directions).
The blocks are attached to model inputs as explicit fields through each
call's own arguments — construction-level isolation, never a transcript.
"""

from __future__ import annotations

import json
from pathlib import Path

from model_call import FULL, call_stage_model, log_stage_call
from models import model_for  # model-tier resolver

# Explicit ruled pin: meta-review is a hard judgment call (Opus), regardless
# of the Step-18.7 Haiku downgrades elsewhere in stage 1.
META_REVIEW_MODEL = model_for("heavy")

# The standing pattern, verbatim per the Step 17-E ruling — sent to the
# meta-review call as its own input field every round.
STANDING_PATTERN = (
    "the ranking judge deliberately never sees Reflection's critique; "
    "recurring consequences of that withhold are meta-review's kind of input."
)

# Bounded list sizes the validator enforces (and the prompt states).
MAX_PATTERN_ITEMS = 6
MAX_FEEDBACK_ITEMS = 6
MAX_DIRECTIONS = 4
MAX_DIRECTION_STATEMENTS = 6
MAX_DIRECTION_EXPERIMENTS = 4

# The critique's five list-valued fields, with their caps.
_LIST_FIELDS = (
    ("recurring_review_patterns", MAX_PATTERN_ITEMS),
    ("recurring_debate_patterns", MAX_PATTERN_ITEMS),
    ("feedback_to_generation", MAX_FEEDBACK_ITEMS),
    ("feedback_to_reflection", MAX_FEEDBACK_ITEMS),
    ("feedback_to_ranking", MAX_FEEDBACK_ITEMS),
)

META_REVIEW_SYSTEM_PROMPT = (
    "You are the meta-review stage of the Ideation loop in an autonomous research "
    "pipeline. You are given the complete record of one finished ideation round: "
    "per-hypothesis review outcomes, tournament results resolved to plain hypothesis "
    "statements (with the judges' verdict reasons and debate verdicts), evolution "
    "outcomes with their reject reasons, near-duplicate flags, and a standing pattern "
    "the pipeline's operators have asked you to watch for. Synthesize a critique of "
    "the ROUND, not of any single hypothesis: identify recurring patterns in the "
    "reviews and in the debate and judge reasons, and turn them into concrete "
    "feedback the next round's stages can act on. Feedback to generation should "
    "steer what kinds of hypotheses get proposed; feedback to reflection should name "
    "recurring factors future reviews must definitively address; feedback to ranking "
    "should name recurring judging patterns worth guarding against. Also produce a "
    "research overview: the most promising research directions this round surfaced, "
    "each with a justification, the hypothesis statements that best support it, and "
    "suggested next experiments. Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"recurring_review_patterns": ["<one sentence each>", ...], '
    '"recurring_debate_patterns": ["<one sentence each>", ...], '
    '"feedback_to_generation": ["<one actionable sentence each>", ...], '
    '"feedback_to_reflection": ["<one actionable sentence each>", ...], '
    '"feedback_to_ranking": ["<one actionable sentence each>", ...], '
    '"research_overview": {"directions": [{"summary": "<one sentence>", '
    '"justification": "<one to two sentences>", '
    '"top_statements": ["<hypothesis statement>", ...], '
    '"suggested_experiments": ["<one sentence each>", ...]}, ...]}}. '
    "Every list may be empty. Keep at most "
    f"{MAX_PATTERN_ITEMS} items per pattern list, {MAX_FEEDBACK_ITEMS} items per "
    f"feedback list, {MAX_DIRECTIONS} directions, and per direction at most "
    f"{MAX_DIRECTION_STATEMENTS} top_statements and {MAX_DIRECTION_EXPERIMENTS} "
    "suggested_experiments."
)

# Code-authored family framing lines (never model-authored).
GENERATION_FRAMING = (
    "Apply this guidance selectively: avoid over-fitting to review critiques "
    "while preventing recurrence of common problems."
)
REFLECTION_FRAMING = (
    "These are recurring factors every future review must definitively address:"
)

_FAMILIES = ("generation", "reflection", "ranking")


def _log(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt.

    Mirrors stage1_ideation._log — stages and their helpers never hold the
    supervisor's Logger object, so the run-log path is rebuilt from run_id
    alone, same as model_call.py and the other stage-1 helper modules do.
    """
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def _bounded_str_list_error(value, field: str, cap: int) -> str | None:
    """None when value is a list of at most `cap` non-empty strings
    (possibly empty); otherwise the plain-language error to re-ask with."""
    if (
        isinstance(value, list)
        and len(value) <= cap
        and all(isinstance(v, str) and v.strip() for v in value)
    ):
        return None
    return (
        f"{field} must be a list of at most {cap} non-empty strings "
        "(possibly empty)."
    )


def meta_review_validator(data: dict) -> list[str]:
    """Shape + bounded-size checks for the meta-review reply, written as
    plain-language errors for the re-ask loop (same style as every other
    stage-1 extra_validator)."""
    errors: list[str] = []
    for field, cap in _LIST_FIELDS:
        error = _bounded_str_list_error(data.get(field), field, cap)
        if error:
            errors.append(error)
    overview = data.get("research_overview")
    if not isinstance(overview, dict) or not isinstance(overview.get("directions"), list):
        errors.append(
            "research_overview must be an object with a directions list "
            "(possibly empty)."
        )
        return errors
    directions = overview["directions"]
    if len(directions) > MAX_DIRECTIONS:
        errors.append(
            f"research_overview.directions must hold at most {MAX_DIRECTIONS} entries."
        )
    for n, d in enumerate(directions, start=1):
        if not isinstance(d, dict):
            errors.append(f"direction {n} must be a JSON object.")
            continue
        for field in ("summary", "justification"):
            value = d.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"direction {n} field {field!r} must be a non-empty string.")
        for field, cap in (
            ("top_statements", MAX_DIRECTION_STATEMENTS),
            ("suggested_experiments", MAX_DIRECTION_EXPERIMENTS),
        ):
            error = _bounded_str_list_error(d.get(field), f"direction {n} {field}", cap)
            if error:
                errors.append(error)
    return errors


def empty_feedback(degraded_reason: str | None = None) -> dict:
    """The empty feedback object: every list empty, zero overview
    directions. Returned when meta-review fails (with `degraded_reason`
    recording why — the rounds.json audit trail carries it) and used by
    tests as the shape reference."""
    obj: dict = {field: [] for field, _cap in _LIST_FIELDS}
    obj["research_overview"] = {"directions": []}
    if degraded_reason is not None:
        obj["degraded"] = degraded_reason
    return obj


def compose_round_record(
    round_index: int,
    domain: str,
    pool: list[dict],
    reflection_evidence: dict,
    survivor_ids: list[str],
    evolution_records: list[dict],
    tournament_resolved: dict | None,
) -> dict:
    """Pure: compose the meta-review call's round_record from the completed
    round's own artifacts. Every hypothesis is presented by STATEMENT — the
    round-local h/ev ids never enter the meta-review context (ids are
    reassigned every round, so an id would be noise at best and a false
    cross-round identity at worst). `reflection_evidence` is the round's
    parsed reflection_reviews.json; `evolution_records` its parsed
    evolution_variants.json; `tournament_resolved` the id-free tournament
    results (None when ranking was trivial)."""
    stmt_by_id = {h["id"]: h["statement"] for h in pool}
    initial_by_id = {r["id"]: r for r in reflection_evidence.get("initial_review", [])}
    reviews_by_id = {
        r["hypothesis_id"]: r for r in reflection_evidence.get("reviews", [])
    }
    deep_kill_by_id = {
        d["id"]: d["reason"]
        for d in reflection_evidence.get("discarded_by_deep_verification", [])
    }

    reflection_outcomes = []
    for h in pool:
        entry: dict = {"statement": h["statement"]}
        iv = initial_by_id.get(h["id"])
        if iv is not None:
            entry["initial_review"] = {"verdict": iv["verdict"], "reason": iv["reason"]}
        rv = reviews_by_id.get(h["id"])
        if rv is not None:
            full = rv.get("full_review", {})
            deep = rv.get("deep_verification", {})
            entry["novelty"] = full.get("novelty")
            entry["novelty_rationale"] = full.get("novelty_rationale")
            entry["quality"] = full.get("quality")
            entry["critique"] = full.get("critique")
            entry["deep_verification"] = {
                "fundamental_flaw": deep.get("fundamental_flaw"),
                "summary": deep.get("summary"),
                "addressable_notes": deep.get("addressable_notes"),
            }
        if h["id"] in survivor_ids:
            entry["outcome"] = "survived_filter"
        elif iv is not None and iv["verdict"] == "discard":
            entry["outcome"] = "discarded_by_initial_review"
            entry["kill_reason"] = iv["reason"]
        elif h["id"] in deep_kill_by_id:
            entry["outcome"] = "discarded_by_deep_verification"
            entry["kill_reason"] = deep_kill_by_id[h["id"]]
        elif rv is not None and rv.get("full_review", {}).get("answer_established"):
            # THE LABEL HAS TO NAME THE ACTUAL CAUSE. This read
            # novelty == "known" and reported "judged_known_at_filter" — but the
            # filter stopped killing on novelty on 2026-07-25 (novelty of METHOD
            # is not novelty of ANSWER). So a known-method candidate that was
            # actually dropped by the MAX_SURVIVORS cap, or that survived and
            # simply lost the tournament, was reported to Opus as having been
            # killed for being unoriginal.
            #
            # This is the one place in the run where a wrong label compounds:
            # meta-review's critique becomes the next round's feedback to
            # Generation, Reflection and the judges. Feeding it a fabricated cause
            # teaches the whole apparatus to avoid a problem it does not have,
            # every round, cumulatively. The real kill is answer_established.
            entry["outcome"] = "dropped_answer_already_established"
        elif rv is not None:
            # Reviewed, not killed, not ranked — so it lost on RANK or fell
            # outside the survivor cap. Distinguished from never-reviewed below,
            # because "the tournament preferred others" and "we never looked at
            # it" call for opposite responses from a meta-reviewer.
            entry["outcome"] = "reviewed_not_selected"
            if rv.get("full_review", {}).get("novelty") == "known":
                # Kept as CONTEXT, never as the cause: it is a ranking signal now
                # (the director's novelty_priority decides its weight), so a
                # meta-reviewer may weigh it without being told it was fatal.
                entry["novelty"] = "known"
        else:
            entry["outcome"] = "not_reviewed"
        reflection_outcomes.append(entry)

    evolution_outcomes = [
        {
            "statement": r.get("statement"),
            "strategy": r.get("provenance", {}).get("strategy"),
            "parent_statements": [
                stmt_by_id.get(pid, pid)
                for pid in r.get("provenance", {}).get("parent_ids", [])
            ],
            "accepted": r.get("accepted"),
            "reject_reason": r.get("reject_reason"),
        }
        for r in evolution_records
    ]

    return {
        "round": round_index,
        "domain": domain,
        "reflection_outcomes": reflection_outcomes,
        "evolution_outcomes": evolution_outcomes,
        "tournament": (
            tournament_resolved
            if tournament_resolved is not None
            else {
                "note": (
                    "ranking was trivial this round (a single candidate); "
                    "no matches were played"
                )
            }
        ),
    }


def build_meta_review(run_id: str, round_index: int, round_record: dict) -> dict:
    """ONE Opus call producing the round's meta-review critique from the
    code-composed round_record (plus STANDING_PATTERN, verbatim). Returns
    the critique {recurring_review_patterns, recurring_debate_patterns,
    feedback_to_generation, feedback_to_reflection, feedback_to_ranking,
    research_overview}. NEVER raises for feedback: any failure — transport
    exhaustion, validation exhaustion, ack mismatch — is logged with a
    durable STAGE1_METAREVIEW line and degrades to the empty feedback
    object carrying the reason."""
    stage_input = {
        "run_id": run_id,
        "round_index": round_index,
        "round_record": round_record,
        "standing_pattern": STANDING_PATTERN,
    }
    try:
        data, timing = call_stage_model(
            "stage1_meta_review",
            META_REVIEW_SYSTEM_PROMPT,
            stage_input,
            {"required": ["ack_run_id", *(f for f, _cap in _LIST_FIELDS), "research_overview"]},
            model=META_REVIEW_MODEL,
            extra_validator=meta_review_validator,
            capabilities=FULL,
        )
        if data["ack_run_id"] != run_id:
            raise RuntimeError(
                f"stage1 meta-review: ack_run_id mismatch — got "
                f"{data['ack_run_id']!r}, expected {run_id!r}"
            )
        log_stage_call(run_id, "stage1_meta_review", timing)
    except Exception as e:
        reason = str(e).splitlines()[0] if str(e) else type(e).__name__
        _log(
            run_id,
            f"STAGE1_METAREVIEW round {round_index} FAILED (recorded, empty "
            f"feedback, run proceeds): {reason}",
        )
        return empty_feedback(f"meta-review failed: {reason}")

    critique = {field: data[field] for field, _cap in _LIST_FIELDS}
    critique["research_overview"] = data["research_overview"]
    _log(
        run_id,
        f"STAGE1_METAREVIEW round {round_index}: "
        f"review_patterns={len(critique['recurring_review_patterns'])} "
        f"debate_patterns={len(critique['recurring_debate_patterns'])} "
        f"feedback g/r/k={len(critique['feedback_to_generation'])}/"
        f"{len(critique['feedback_to_reflection'])}/"
        f"{len(critique['feedback_to_ranking'])} "
        f"directions={len(critique['research_overview']['directions'])}",
    )
    return critique


def compose_feedback_block(
    family: str,
    items: list[str],
    round_index: int,
    overview: dict | None = None,
) -> str:
    """Pure, deterministic: one family's labeled feedback text block.

    Round 1 returns an explicit empty block (no meta-review has run yet).
    From round 2 the block carries the code-authored family framing —
    Generation: apply selectively, avoid over-fitting while preventing
    recurrence; Reflection: recurring factors every future review must
    definitively address; Ranking: plain label, no framing — followed by
    the items, and (Generation only, via `overview`, which the controller
    passes None on round 1) the prior round's research-overview directions
    as a labeled subsection."""
    if family not in _FAMILIES:
        raise ValueError(f"unknown feedback family {family!r}; expected one of {_FAMILIES}")
    header = f"META-REVIEW FEEDBACK ({family}, entering round {round_index}):"
    if round_index <= 1:
        return header + " none — this is the first round; no meta-review has run yet."
    lines = [header]
    if family == "generation":
        lines.append(GENERATION_FRAMING)
    elif family == "reflection":
        lines.append(REFLECTION_FRAMING)
    if items:
        lines.extend(f"- {item}" for item in items)
    else:
        lines.append(
            "- (the prior round's meta-review produced no feedback items for this family)"
        )
    if overview is not None:
        lines.append("RESEARCH-OVERVIEW DIRECTIONS (the prior round's synthesis):")
        directions = overview.get("directions", [])
        if directions:
            lines.extend(
                f"- {d.get('summary')} (justification: {d.get('justification')})"
                for d in directions
            )
        else:
            lines.append("- (the prior round's overview named no directions)")
    return "\n".join(lines)


def append_rounds_entry(run_dir: Path, entry: dict) -> None:
    """Append one round's audit entry to stage1/rounds.json (a JSON list;
    created on first append). Deterministic file I/O, no model."""
    path = run_dir / "rounds.json"
    entries = json.loads(path.read_text()) if path.exists() else []
    entries.append(entry)
    path.write_text(json.dumps(entries, indent=2))
