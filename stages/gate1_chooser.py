"""
gate1_chooser.py — Stage 1.5 (Step 23; instrument decision added Step 23.5):
the reasoned gate-1 chooser. ONE isolated Opus call over the ranked list,
the final Elo table, each survivor's addressable_notes, and the
research-overview directions emits {chosen_id, substrate_id, reasoning}.
Opus, per CLAUDE.md's model roles: which hypothesis to advance is a hard
judgment — auto mode's old rank-1 selection was a placeholder, never a
decision. R-23.5-1 (owner, 2026-07-17): instrument selection is decided at
gate 1 by the gate's decider; in auto mode this chooser's same single call
names the instrument (substrate_id, validated against the registry's LIVE
routable ids — never a hardcoded list).

The supervisor stays deterministic: it schedules this module exactly as it
schedules the six stages, and consumes only the typed record returned here.
Auto mode resolves gate 1 to the record's chosen_id; human mode displays
the record as a labeled advisory block (display-only — the human's integer
pick remains the decision, and CHOSEN_HYPOTHESIS_KEYS / payload order are
untouched).

The reply is enforced in Python, not trusted: envelope schema, then a deep
validator (chosen_id locked to the actual ranked ids, reasoning non-empty)
inside call_stage_model's bounded 3-attempt RE-ASK loop. FAILURE MODE IS
THE PLACEHOLDER: on transport exhaustion, repeated invalid choice, or any
other failure, choose_hypothesis falls back to rank 1 and records
fallback=true — it never crashes a run, because it replaces code that
could not crash. The record {chosen_id, reasoning, fallback} is written to
the run dir as gate1_chooser.json in both modes (the call was spent, so
the evidence lands on disk either way).

Evidence inputs are read best-effort from the canonical stage1/ files
(survivors.json, tournament_state.json, research_overview.json — the LAST
SUCCESSFUL round under the 17-E controller); a missing or malformed file
degrades to an absent section, never an error. Accepted Evolution variants
in the ranked list may carry no survivors.json entry — their
addressable_notes degrade to [] the same way.
"""

from __future__ import annotations

import json
from pathlib import Path

from model_call import FULL, call_stage_model, log_stage_call
from tools.substrate_registry import routable_contracts_block, routable_ids

# Step-23 ruled pin: the chooser is a hard judgment, so it rides Opus.
CHOOSER_MODEL = "claude-opus-4-8"

# --- R-WIN-1: instrument-contract grounding (the h6 fix), UNCONDITIONAL ------
# The chooser is grounded in what the instruments can actually measure so it
# does not advance a hypothesis whose test is out of contract. Single source
# of truth: the body IS the registry's routable_contracts_block — every
# routable contract verbatim, never a pasted copy (R5, owner 2026-07-17).
# No new failure path — the fallback-to-rank-1 contract is untouched.
INSTRUMENT_CONTRACT_HEADER = (
    "INSTRUMENT CONTRACTS (what the available instruments can actually measure)"
)
INSTRUMENT_CONTRACT_INSTRUCTION = (
    "Candidates whose test requires measurements outside every listed contract "
    "must be treated as weaker bets, stated in the reasoning."
)


def instrument_contract_block() -> str:
    """The delimited instrument-contract block appended to the chooser prompt.
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


def compose_chooser_prompt() -> str:
    """R-WIN-1: the chooser system prompt grounded in the instrument contract.
    Differs from today's SYSTEM_PROMPT only by the appended contract block
    (asserted in the byte-identity test)."""
    return SYSTEM_PROMPT + instrument_contract_block()

SYSTEM_PROMPT = """You are the gate-1 chooser for an autonomous research system. Stage 1 produced a ranked list of surviving hypotheses; the rank order came from a pairwise Elo tournament. Your job is one hard judgment: choose the single hypothesis this run should advance into experiment design.

You will be given the ranked hypotheses (id, statement, rationale, in rank order), and — when available — the final Elo table, each survivor's addressable_notes (concerns already identified during review; addressable, not fatal, but real costs the chosen hypothesis will carry), and the research overview's direction summaries. Judge only from what you are given plus your own knowledge of the science. Do not assume facts you were not told.

The rank order is evidence, not a command: rank 1 is the default, and you should depart from it only when the material you were given supports the departure — for example a near-tie in Elo where a lower-ranked hypothesis carries fewer or lighter addressable concerns, or aligns better with the research-overview directions.

Your same single judgment also decides the instrument: set substrate_id to exactly one id from the ROUTABLE SUBSTRATE headers in the INSTRUMENT CONTRACTS block below — the routable substrate whose contract can actually measure what testing your chosen hypothesis requires.

Reply ONLY with JSON of the form {"ack_run_id": "<the run_id you were given>", "chosen_id": "<the id of exactly one hypothesis from the ranked list>", "substrate_id": "<the id of exactly one routable substrate from the instrument-contract block>", "reasoning": "<2-4 sentences: the decisive comparison behind this choice>"} — no other fields anywhere."""

# R-23.5-1 (owner, 2026-07-17): instrument selection is decided at gate 1 by
# this chooser; the same single call names the instrument. The era move is
# confined to this prompt family (instruction text + retry-path
# envelope-error text) — every other model-visible surface stays
# byte-identical (C1/C3/C4 containment tripwires in test_c235_captures.py).
SCHEMA = {"required": ["ack_run_id", "chosen_id", "substrate_id", "reasoning"]}

ENVELOPE_FIELDS = ("ack_run_id", "chosen_id", "substrate_id", "reasoning")


def make_choice_validator(valid_ids: set) -> callable:
    """Deep validator handed to call_stage_model: the reply envelope must be
    exactly {ack_run_id, chosen_id, substrate_id, reasoning}, chosen_id must
    be one of the ranked list's actual ids, substrate_id must be one of the
    registry's LIVE routable ids, and reasoning must be a non-empty string.
    Returns plain-language error strings, empty = valid.
    """

    def validator(parsed: dict) -> list[str]:
        errors = [
            f"reply field '{key}' is not allowed — reply with exactly "
            '"ack_run_id", "chosen_id", "substrate_id", and "reasoning", '
            "nothing else."
            for key in parsed
            if key not in ENVELOPE_FIELDS
        ]
        if parsed.get("chosen_id") not in valid_ids:
            errors.append(
                f"chosen_id must be exactly one of {sorted(valid_ids)}; "
                f"got {parsed.get('chosen_id')!r}."
            )
        # R-23.5-1 (owner, 2026-07-17): membership is checked against
        # routable_ids() read LIVE from the registry at validation time —
        # never a hardcoded list (one runtime source of truth, no third copy).
        live_routable = routable_ids()
        if parsed.get("substrate_id") not in live_routable:
            errors.append(
                f"substrate_id must be exactly one of {list(live_routable)}; "
                f"got {parsed.get('substrate_id')!r}."
            )
        reasoning = parsed.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            errors.append("reasoning must be a non-empty string.")
        return errors

    return validator


def _read_json(path: Path):
    """Best-effort JSON read: missing or malformed returns None, never raises."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def gather_evidence(stage1_dir: Path, hypotheses: list) -> dict:
    """Assemble the chooser's evidence sections from the canonical stage1/
    files. Best-effort throughout: a missing or malformed file yields an
    empty section (the chooser then judges from the ranked list alone), and
    a ranked id absent from survivors.json — an accepted Evolution variant —
    yields addressable_notes []. Never raises.
    """
    elo_table = []
    state = _read_json(stage1_dir / "tournament_state.json")
    if isinstance(state, dict) and isinstance(state.get("final_ranking"), list):
        for entry in state["final_ranking"]:
            if isinstance(entry, dict) and entry.get("id"):
                elo_table.append({"id": entry.get("id"), "elo": entry.get("elo")})

    notes_by_id = {}
    survivors = _read_json(stage1_dir / "survivors.json")
    if isinstance(survivors, list):
        for record in survivors:
            if isinstance(record, dict) and record.get("id"):
                notes = record.get("addressable_notes")
                notes_by_id[record["id"]] = notes if isinstance(notes, list) else []
    addressable_notes = {
        h["id"]: notes_by_id.get(h["id"], []) for h in hypotheses if h.get("id")
    }

    directions = []
    overview = _read_json(stage1_dir / "research_overview.json")
    if isinstance(overview, dict) and isinstance(overview.get("directions"), list):
        for direction in overview["directions"]:
            summary = direction.get("summary") if isinstance(direction, dict) else None
            if summary:
                directions.append(summary)

    return {
        "elo_table": elo_table,
        "addressable_notes": addressable_notes,
        "research_overview_directions": directions,
    }


def choose_hypothesis(run_id: str, hypotheses: list, run_dir: Path) -> dict:
    """One Opus call choosing which ranked hypothesis to advance AND which
    instrument the run should execute on (R-23.5-1: the same single call
    names the instrument). NEVER raises: any failure — transport exhaustion,
    three invalid replies, an ack mismatch, even an evidence-read surprise —
    falls back to rank 1 with fallback=true, because this call replaces the
    rank-1 placeholder and must fail exactly as the placeholder behaved.
    R-23.5-2 (owner, 2026-07-17): the fallback record carries substrate_id
    null — NEVER a cavity default; in auto mode the supervisor stops the run
    loudly at the gate on a null instrument. Returns the record
    {chosen_id, substrate_id, reasoning, fallback} and writes it to
    <run_dir>/gate1_chooser.json (best-effort) in both modes.
    """
    run_dir = Path(run_dir)
    rank1_id = hypotheses[0]["id"]
    try:
        evidence = gather_evidence(run_dir / "stage1", hypotheses)
        stage_input = {
            "run_id": run_id,
            "ranked_hypotheses": [
                {
                    "rank": rank,
                    "id": h["id"],
                    "statement": h["statement"],
                    "rationale": h["rationale"],
                }
                for rank, h in enumerate(hypotheses, start=1)
            ],
            **evidence,
        }
        valid_ids = {h["id"] for h in hypotheses}
        data, timing = call_stage_model(
            "gate1_chooser",
            compose_chooser_prompt(),
            stage_input,
            SCHEMA,
            model=CHOOSER_MODEL,
            extra_validator=make_choice_validator(valid_ids),
            capabilities=FULL,
        )
        log_stage_call(run_id, "gate1_chooser", timing)
        if data["ack_run_id"] != run_id:
            raise RuntimeError(
                f"gate1_chooser: ack_run_id mismatch — got "
                f"{data['ack_run_id']!r}, expected {run_id!r}"
            )
        record = {
            "chosen_id": data["chosen_id"],
            "substrate_id": data["substrate_id"],
            "reasoning": data["reasoning"].strip(),
            "fallback": False,
        }
    except Exception as exc:
        reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        if len(reason) > 300:
            reason = reason[:300].rstrip() + "…"
        record = {
            "chosen_id": rank1_id,
            # R-23.5-2 (owner, 2026-07-17): the never-raise fallback carries
            # substrate_id null; a cavity default is forbidden. Auto mode
            # stops loudly at the gate on this null (supervisor.run_gate1).
            "substrate_id": None,
            "reasoning": f"fallback to rank 1: {reason}",
            "fallback": True,
        }
    try:
        (run_dir / "gate1_chooser.json").write_text(json.dumps(record, indent=2))
    except Exception:
        pass  # the record is still returned; a failed evidence write must not kill a run
    return record
