"""
stage2_experiment_design.py — real Experiment-Design stage: ONE isolated
Sonnet call turns the gate-1 chosen hypothesis into a typed experiment spec.

The stage reads the baton payload ({domain, chosen_hypothesis,
substrate_id} since Step 23.5, R-23.5-4) plus the contract of the payload's
gate-decided substrate (read from the registry — the D.1.1 cavity pin is
retired at this surface) plus,
since Step 18.5, the last 3 learned_summary journal entries, code-composed
into a substrate-capability lessons block (evidence at
runs/<run_id>/stage2/retrieved_memory.json; loop-back re-entry re-reads, so
a fresh lesson informs the redesigned spec). The
reply is enforced in Python, not trusted: a shallow envelope schema, then
validate_spec running as call_stage_model's extra_validator, whose
plain-language errors go back to the model as guided corrections inside the
same bounded 3-attempt loop. On success the validated spec becomes evidence
at runs/<run_id>/stage2/spec.json, the payload becomes
{domain, chosen_hypothesis, experiment_spec}, and the single history note is
written by code from validated fields — never model-authored narration.
"""

from __future__ import annotations

import json
from pathlib import Path

from baton import Baton
from memory.journal import journal_recent_by_kind
from model_call import call_stage_model, log_stage_call
from stages.stage2_spec import validate_spec
from tools.qoi_vocab import vocab_for
from tools.substrate_registry import contract_for

SONNET_MODEL = "claude-sonnet-4-6"

# Step 18.5: memory reaches Stage 2. The block is code-composed from journal
# entries — never model-authored — and framed as instrument lessons, keeping
# the leads-not-facts journal-poison ruling.
LESSONS_HEADER = (
    "SUBSTRATE-CAPABILITY LESSONS FROM PRIOR RUNS (unverified model text - "
    "treat as leads, not established facts): prior runs learned these "
    "instrument limits - design within them or justify routing elsewhere:"
)


def build_substrate_lessons_block(entries: list[dict]) -> str | None:
    """Pure, no I/O: format learned_summary journal entries into the
    substrate-capability lessons block for the Stage-2 model input.

    Returns None when `entries` is empty; otherwise the exact LESSONS_HEADER
    line followed by one line per entry:
    "- [run <run_id>, hypothesis <hypothesis_id>] <text>" — the same line
    shape as stage 1's build_memory_block, so journal entries read the same
    everywhere they surface.
    """
    if not entries:
        return None
    lines = [LESSONS_HEADER]
    for e in entries:
        lines.append(
            f"- [run {e.get('run_id')}, hypothesis {e.get('hypothesis_id')}] {e.get('text')}"
        )
    return "\n".join(lines)

SYSTEM_PROMPT = (
    "You are the Experiment-Design stage of an autonomous research pipeline: you turn "
    "the one chosen hypothesis you are given into a concrete, typed experiment "
    "specification, grounded in the substrate contract that accompanies it. "
    "Design the experiment this hypothesis actually needs — do NOT self-censor the "
    "quantity of interest down to what the wrapper extracts today, because instrument "
    "feasibility is a later gate's judgment, not yours — but be honest in regime.notes "
    "about anything uncertain, including any mismatch you see between the design and "
    "the substrate's declared limits. "
    "Choose exactly one quantity of interest, declare every parameter with role "
    '"sweep" (numeric min and max) or "fixed" (a value), and make every value '
    "physically sensible for the regime you state. "
    "When, and only when, the quantity of interest is genuinely extractable per the "
    "substrate contract — an existing field the case already writes, one of the "
    "contract's allowed operations, optional component — the qoi object MUST "
    'additionally carry the machine-readable keys "field", "operation", and '
    'optionally "component", using exactly the contract\'s vocabulary; when the '
    "quantity of interest is NOT extractable, those keys MUST be omitted (the "
    "free-text qoi name, definition, and how_extracted remain either way). "
    "When more than one quantity of interest could genuinely test the hypothesis, "
    "prefer one the substrate contract can extract. "
    "When the design genuinely predicts a numeric value for the quantity of "
    'interest, the success_criterion should additionally carry "expected_value" '
    '(the predicted number) and "tolerance" (a positive number: the acceptable '
    "absolute deviation); when it does not, omit both. "
    "If the spec declares a parameter whose value is derived from other "
    'parameters, give it role "derived" and state the rule in a "derived_from" '
    "string. "
    "When prior_thought is present, the previous design for this hypothesis "
    "failed for the reasons it states — the new spec must directly address that "
    "assessment and justification, and must not resubmit an unchanged design. "
    "When a substrate_capability_lessons block is present, it lists instrument "
    "limits that earlier runs of this system learned the hard way (unverified "
    "model text — treat as leads, not established facts): design within those "
    "limits, and if the hypothesis genuinely requires exceeding one of them, say "
    "so explicitly in regime.notes rather than designing around it silently. "
    "Use the substrate contract's canonical parameter name whenever the physical "
    "quantity you are declaring matches one; parameters with no canonical "
    "equivalent keep their natural names — this is a naming convention, not a "
    "restriction on what may be designed. "
    "The mini_experiment is a cheap preview of 1 to 3 runs; every run must assign "
    "every declared parameter by name, keep fixed parameters at their declared "
    "values, and stay inside the declared sweep bounds. "
    'Reply ONLY with JSON of the form {"ack_run_id": "<the run_id you were given>", '
    '"spec": {"hypothesis_id": "<the id of the chosen hypothesis>", '
    '"title": "<short title>", "objective": "<one sentence>", '
    '"parameters": [{"name": "...", "role": "sweep", "units": "...", "min": <number>, '
    '"max": <number>} or {"name": "...", "role": "fixed", "units": "...", '
    '"value": <value>}, ...], "qoi": {"name": "...", "units": "...", '
    '"definition": "...", "how_extracted": "...", and the machine-readable keys '
    "only in the extractable case}, \"success_criterion\": "
    '{"statement": "...", "threshold": <number>, "direction": "above" or "below"}, '
    '"regime": <this substrate\'s regime declaration: an object with the '
    "regime fields the substrate contract states for this instrument "
    '(where the contract states none, the Reynolds band — "reynolds_min" '
    'and "reynolds_max" as numbers), plus "notes": "...">, '
    '"mini_experiment": {"runs": [{"<parameter name>": <value>, ...}, ...], '
    '"expected_observation": "..."}, "full_experiment": {"design": "...", '
    '"estimated_run_count": <positive integer>}}} — no other fields anywhere.'
)

SCHEMA = {"required": ["ack_run_id", "spec"]}

ENVELOPE_FIELDS = ("ack_run_id", "spec")


def _make_extra_validator(chosen_id: str, vocab):
    """Deep validator handed to call_stage_model: the reply envelope must be
    exactly {ack_run_id, spec}, and the spec must pass validate_spec for the
    chosen hypothesis under the substrate's OWN QoI vocabulary (R-23.5-4:
    resolved from the payload's gate-decided substrate_id — the cavity
    vocab is the same record the old bare call resolved to, so cavity
    retry surfaces are byte-identical). Returns plain-language error
    strings, empty = valid.
    """

    def check(parsed: dict) -> list[str]:
        errors = [
            f"reply field '{key}' is not allowed — reply with exactly "
            '"ack_run_id" and "spec", nothing else.'
            for key in parsed
            if key not in ENVELOPE_FIELDS
        ]
        errors.extend(validate_spec(parsed["spec"], chosen_id, vocab))
        return errors

    return check


def _log_line(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt (same path rule as log_stage_call)."""
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def run(baton: Baton) -> Baton:
    domain = baton.payload["domain"]
    chosen = baton.payload["chosen_hypothesis"]

    # Step 16 (loop-back): prior_thought is the thought layer's verdict on a
    # previous design of this same hypothesis (None on pass 1); it enters the
    # model input so the redesign can address it, and stays in the payload so
    # pass-2 boundaries and evidence keep the context.
    prior_thought = baton.payload.get("prior_thought")

    # Step 18.5: journal read-side into Stage 2 (deterministic, before the
    # model call; the SAME recency-only top-3 learned_summary read stage 1
    # uses — no similarity retrieval exists yet, disclosed limitation). On a
    # loop-back re-entry this re-read picks up the learned_summary stage 5
    # just journaled, so the redesigned spec sees the fresh instrument lesson.
    # Evidence mirrors stage 1's pattern: stage2/retrieved_memory.json
    # (overwritten on re-entry, same as spec.json).
    memory_entries = journal_recent_by_kind("learned_summary", 3)
    stage_dir = Path("runs") / baton.run_id / "stage2"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "retrieved_memory.json").write_text(json.dumps(memory_entries, indent=2))
    lessons_block = build_substrate_lessons_block(memory_entries)
    _log_line(
        baton.run_id,
        f"STAGE2_MEMORY retrieved {len(memory_entries)} learned_summary entries",
    )

    # R-23.5-4 (owner, 2026-07-17): the composition is grounded in the
    # contract of the payload's gate-decided substrate_id — a structural
    # key read, never a string literal, never a name parse. contract_for
    # fails loud on an unknown (KeyError) or contractless (LookupError)
    # id — NEVER a cavity fallback. For a cavity payload this returns the
    # same imported constant object as the retired literal pin, so the
    # composed bytes are identical (d1 pins hold with zero fixture edits).
    stage_input = {
        "run_id": baton.run_id,
        "domain": domain,
        "chosen_hypothesis": chosen,
        "substrate_contract": contract_for(baton.payload["substrate_id"]),
        "prior_thought": prior_thought,
    }
    if lessons_block is not None:
        stage_input["substrate_capability_lessons"] = lessons_block
    data, timing = call_stage_model(
        "stage2_experiment_design",
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=SONNET_MODEL,
        extra_validator=_make_extra_validator(
            chosen["id"], vocab_for(baton.payload["substrate_id"])
        ),
    )

    if data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage2_experiment_design: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {baton.run_id!r}"
        )
    _log_line(
        baton.run_id,
        f"ECHO_CHECK stage=stage2_experiment_design ack_run_id={data['ack_run_id']} "
        "matches run_id",
    )

    spec = data["spec"]
    (stage_dir / "spec.json").write_text(json.dumps(spec, indent=2))

    n_sweep = sum(1 for p in spec["parameters"] if p["role"] == "sweep")
    n_fixed = sum(1 for p in spec["parameters"] if p["role"] == "fixed")
    n_mini = len(spec["mini_experiment"]["runs"])
    note = (
        f"spec for {spec['hypothesis_id']}: {n_sweep} sweep + {n_fixed} fixed "
        f"parameters, QoI {spec['qoi']['name']}, mini-experiment of {n_mini} "
        f"run{'s' if n_mini != 1 else ''}"
    )

    baton.payload = {
        "domain": domain,
        "chosen_hypothesis": chosen,
        "experiment_spec": spec,
        # R-23.5-4 (owner, 2026-07-17): the gate-decided instrument travels
        # the payload untouched — it enters NO composed prompt; a payload
        # without it fails loud here, never defaults.
        "substrate_id": baton.payload["substrate_id"],
    }
    if prior_thought is not None:
        baton.payload["prior_thought"] = prior_thought
    baton.add_history("stage2_experiment_design", note)
    log_stage_call(baton.run_id, "stage2_experiment_design", timing)
    return baton
