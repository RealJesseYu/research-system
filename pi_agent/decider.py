"""pi_agent/decider.py — the PI's judgment: read the arc, choose the next move.

THIS IS THE MIND. Everything else in pi_agent is hands — a run you can call, a
study an arc accumulates under. The decider is the first thing that looks at
what an investigation has produced and DECIDES what to do next: run another
experiment, run an iterated campaign, or stop because the goal is answered or
further moves won't help. It is a real judgment, so it is a real model call —
one Opus turn per decision, through the same call_stage_model door every stage
uses (transcript discipline, bounded re-asks, cost attribution, isolation).

WHAT IT CHOOSES, AND WHAT IT DOES NOT. The decider picks the QUESTION to point
the next run at and the KIND of move. It does NOT pick the instrument — the run's
own gate-1 chooser does that, from the permitted set the study's constraint
allows — and it does NOT touch a measurement. It reads OUTCOMES (did the paper
stand, what did the arc show), which are the sealed judges' outputs, and decides
what to do about them. That keeps it firmly on the permitted side of
capability_guard: it is above execution, never inside it. "Revising the
hypothesis" is expressed as choosing a different next_domain — each run forms its
own hypotheses from the question it is given, so a new question IS a revision.

THE MENU, HONESTLY. v1 offers run_single and run_campaign. The chain move exists
at the dispatch layer (pi_agent.dispatch) but its fidelity verdicts need a live
stage-3 source that is not wired yet, so the decider is not offered a move it
cannot honestly dispatch. When that source lands, run_chain joins the menu here.

CAPABILITY. v1 runs SEALED: one reasoned turn over the arc it is given, no tools.
The tool-using research (literature, retrieval) happens INSIDE the moves it
dispatches — each run does its own grounded ideation. Giving the PI FULL so it
can read literature directly before choosing is the natural next expansion; it is
deliberately not taken here, to bound the highest-spend layer's first version.

EVIDENCE. Each decision is written to studies/<id>/decisions/decide<N>.json — the
PI's reasoning trail, kept with the study rather than in runs/. (A consequence:
the decider passes no run_id to the door, so the door writes no transcript and
its re-ask lines are not durably logged; the decision record is the evidence
instead. A deliberate trade to keep PI evidence under the study.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from model_call import SEALED, call_stage_model

# Opus: choosing the next move is a hard judgment (CLAUDE.md model roles).
PI_DECIDER_MODEL = "claude-opus-4-8"
# NOT a sealed-prefixed name: the decider is above execution, so it is allowed a
# profile — v1 simply chooses SEALED. The name records that it is the PI layer.
PI_DECIDER_STAGE = "pi_decider"

DECISION_VALUES = ("run_single", "run_campaign", "stop")

SYSTEM_PROMPT = """You are the principal investigator of an autonomous research system. You hold one goal for an entire investigation, and you drive it by choosing a sequence of experiments — an arc — where each experiment follows from what the last ones showed.

You will be given: the GOAL; the instrument CONSTRAINT (the substrates this investigation may use, or null for no restriction); your BUDGET (how many moves you have used and how many remain); and the ARC SO FAR (each move you have already run, with its outcome and whether its paper stood).

Each move you choose becomes a full pipeline run on its own. You do NOT design the experiment or pick the instrument — the run forms its own hypotheses from the QUESTION you give it and selects an instrument from the permitted set. Your job is the researcher's job above that: decide WHICH QUESTION to ask next and WHAT KIND of move to make, based on what the investigation has learned.

The moves available to you:
- "run_single": one experiment answering one question. Use it to open a line, or to test a specific new question raised by a previous result.
- "run_campaign": an iterated experiment that sweeps and refines around a question under its own budget. Use it when a question needs several related measurements, not one.
- "stop": end the investigation. Choose this when the goal is answered, when the arc has converged, or when further moves are unlikely to help (for example, repeated halts that a new question would not fix). Do not spend moves for their own sake.

CHOOSING THE INSTRUMENT. You are given an INSTRUMENT MENU: the substrates available to this study, and for each one what it can vary and what it can measure. For a run move you MAY name one instrument from that menu — set "instrument" to its substrate_id — when the result so far, or the nature of the question, tells you a particular tool is right (for example, a surprising result that points to a different measurement). If you leave "instrument" null, the run picks the instrument itself from the same menu. You may only name an instrument that is on the menu; naming one that is not is refused.

You read RESULTS, not raw measurements. Each arc entry carries the run's verified findings — the values it measured and whether each one independently reproduced — plus whether its paper stood. Reason over those. You never re-run or restate a number yourself: a measurement of record always comes from the instrument and its verification, never from you. "Revising the hypothesis" means asking a sharper next question: each run re-forms its hypotheses from the question you give it.

Reply ONLY with JSON of the form {"ack": "<the study_id you were given>", "reading": "<one or two sentences: what the most recent move's result showed, and what it means for the goal; null if no moves have run yet>", "decision": "run_single" | "run_campaign" | "stop", "rationale": "<1-3 sentences: why this next move, or why stop>", "next_domain": "<the exact question the next run should investigate; required unless the decision is stop, otherwise null>", "instrument": "<a substrate_id from the instrument menu to force for this move, or null to let the run choose; always null when the decision is stop>", "stop_reason": "<why the investigation is complete or should end; required only when the decision is stop, otherwise null>"} — no other fields anywhere."""

SCHEMA = {"required": ["ack", "reading", "decision", "rationale", "next_domain", "instrument", "stop_reason"]}

_ENVELOPE_FIELDS = ("ack", "reading", "decision", "rationale", "next_domain", "instrument", "stop_reason")


def make_decision_validator(
    study_id: str, arc_len: int, choosable_instruments: tuple = ()
) -> Callable[[dict], list]:
    """The deep validator handed to the door: envelope is exactly the seven
    fields, ack echoes the study_id, decision is in the enum, a run_* decision
    carries a non-empty next_domain, a stop carries a non-empty stop_reason,
    once at least one move has run the reading must be a non-empty string (turn 1
    may leave it null), and a named instrument must be one the study can reach.
    Plain-language errors, empty = valid."""

    def validator(parsed: dict) -> list:
        errors = [
            f"reply field {key!r} is not allowed — reply with exactly "
            f"{', '.join(_ENVELOPE_FIELDS)}, nothing else."
            for key in parsed
            if key not in _ENVELOPE_FIELDS
        ]
        if parsed.get("ack") != study_id:
            errors.append(f"ack must echo the study_id {study_id!r}; got {parsed.get('ack')!r}.")
        decision = parsed.get("decision")
        if decision not in DECISION_VALUES:
            errors.append(
                f"decision must be one of {', '.join(DECISION_VALUES)}; got {decision!r}."
            )
        rationale = parsed.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("rationale must be a non-empty string.")
        if decision in ("run_single", "run_campaign"):
            nd = parsed.get("next_domain")
            if not isinstance(nd, str) or not nd.strip():
                errors.append(
                    "next_domain must be a non-empty question when the decision is "
                    "run_single or run_campaign."
                )
        elif decision == "stop":
            sr = parsed.get("stop_reason")
            if not isinstance(sr, str) or not sr.strip():
                errors.append("stop_reason must be a non-empty string when the decision is stop.")
        # instrument: null (let the run choose) is always valid; a named one
        # must be on the menu the study can reach, and only for a run move.
        instrument = parsed.get("instrument")
        if instrument is not None:
            if decision == "stop":
                errors.append("instrument must be null when the decision is stop.")
            elif choosable_instruments and instrument not in choosable_instruments:
                errors.append(
                    f"instrument must be one of the menu {list(choosable_instruments)} "
                    f"(or null to let the run choose); got {instrument!r}."
                )
        if arc_len > 0:
            reading = parsed.get("reading")
            if not isinstance(reading, str) or not reading.strip():
                errors.append(
                    "reading must be a non-empty string once at least one move has run "
                    "(only the first decision, with an empty arc, may leave it null)."
                )
        return errors

    return validator


def choosable_instruments(study: Any) -> tuple:
    """The substrate ids this study's moves may name: the study's own set when
    it is constrained, else every routable id. The outer bound the PI chooses
    within."""
    from tools import substrate_registry as registry

    if study.allowed_substrates:
        return tuple(study.allowed_substrates)
    try:
        return registry.routable_ids()
    except Exception:  # noqa: BLE001
        return ()


def instrument_menu(study: Any) -> list:
    """What each choosable instrument can vary and measure — so the PI reasons
    over the tools, not just their names, when it picks one. Built from the same
    registry/signature/vocab the router uses; never raises (an instrument whose
    signature or vocab is unwired is simply skipped)."""
    from tools.substrate_selection import signature_for
    from tools.qoi_vocab import vocab_for

    menu = []
    for sid in choosable_instruments(study):
        try:
            varies = sorted(signature_for(sid))
        except Exception:  # noqa: BLE001
            continue
        try:
            names = getattr(vocab_for(sid), "names", None)
            measures = list(names) if names else []
        except Exception:  # noqa: BLE001
            measures = []
        menu.append({"substrate_id": sid, "can_vary": varies, "can_measure": measures})
    return menu


def build_decider_input(study: Any, arc: list, budget: dict) -> dict:
    """The exact input the decider reasons over. Pure over the study's disk
    state. Carries no run_id key on purpose (see the module docstring): the
    decision is PI-layer evidence, not a run's transcript."""
    return {
        "study_id": study.study_id,
        "goal": study.goal,
        "instrument_constraint": study.allowed_substrates,  # null = unconstrained
        "instrument_menu": instrument_menu(study),
        "available_move_types": ["run_single", "run_campaign"],
        "budget": budget,
        "arc_so_far": arc,
    }


def decide(
    study: Any,
    arc: list,
    budget: dict,
    *,
    call: Callable = call_stage_model,
    model: str = PI_DECIDER_MODEL,
) -> dict:
    """Make one decision and record it under the study. `call` is the model door
    (call_stage_model), injected so tests can drive the loop without spend.
    Returns the validated decision dict.

    Raises whatever the door raises after its bounded re-asks — the loop catches
    it and ends the study honestly rather than pretending a decision was made.
    """
    stage_input = build_decider_input(study, arc, budget)
    validator = make_decision_validator(
        study.study_id, len(arc), choosable_instruments(study)
    )
    data, timing = call(
        PI_DECIDER_STAGE,
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=model,
        extra_validator=validator,
        capabilities=SEALED,
    )
    _record_decision(study, len(arc) + 1, stage_input, data, timing)
    return data


def _record_decision(study: Any, seq: int, stage_input: dict, decision: dict, timing: dict) -> None:
    """Write the decision to studies/<id>/decisions/decide<seq>.json — the PI's
    reasoning trail, kept with the study. Never raises: losing the evidence file
    must not lose the decision the loop is about to act on."""
    try:
        ddir = study.dir / "decisions"
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / f"decide{seq}.json").write_text(
            json.dumps(
                {"seq": seq, "input": stage_input, "decision": decision, "timing": timing},
                indent=2,
            )
        )
    except Exception:  # noqa: BLE001 — evidence write must not sink the decision
        pass
