"""pi_agent/free_decider.py — the FREE director's judgment: an OPEN action space.

This is the enum decider (pi_agent/decider.py) freed. The enum decider reads the
arc and returns one of four verbs (run_single / run_campaign / run_fan / stop) — a
reactive loop-controller, the director-level analogue of the sealed pipeline
already purged below it. The free director reads the same arc but chooses from an
OPEN toolbox: run an experiment, spawn a sub-investigation (delegate a slice of its
budget), call ideation / validation / data-analysis as OPTIONAL tools, touch
memory, or stop. Decomposition is not a special phase — it is the director electing
to spawn a sub-investigation because the task earns it (docs/free_director_plan.md,
R-FD-1: built ALONGSIDE the enum decider, which is untouched).

THE ONE BOUNDARY, UNCHANGED. Like the enum decider, the free director directs work
and reads verified results; it NEVER produces a measurement of record. A number
comes from an instrument + verification inside an experiment, never from the
director's narration. Everything else is open.

NOTHING HERE IS MANDATORY except that boundary. call_ideation / call_validation /
call_data_analysis are TOOLS the director reaches for when the task warrants — not
stages every investigation is forced through (docs/free_director_plan.md §1).

SHELL SCOPE (Phase 2). This module defines the full action VOCABULARY and validates
it. The executors for run_experiment and stop are live now (existing dispatch);
spawn_sub_investigation (Phase 4), the call_* tools and memory (Phase 3) are defined
here and routed to an honest "not yet wired" result by the controller until their
phase lands — never faked, never silently dropped.

EVIDENCE. Each decision is written to studies/<id>/decisions/decide<N>.json, the
same PI reasoning trail the enum decider keeps (no run_id to the door, so the
decision record is the evidence).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for  # model-tier resolver

# Reuse the enum decider's instrument helpers verbatim — the menu a director may
# force a run to is the same whichever director chose it (keeps the two in lockstep
# rather than drifting two copies).
from pi_agent.decider import choosable_instruments, instrument_menu
from pi_agent.study import study_scratch_dir

# Opus: directing an investigation is the hard judgment (CLAUDE.md model roles).
FREE_DIRECTOR_MODEL = model_for("heavy")
# NON-sealed name: the director is ABOVE execution (like pi_decider), so
# capability_guard permits it the FULL profile — a full researcher that reads
# literature and reasons with tools before it commits the next move.
FREE_DIRECTOR_STAGE = "free_director"

# The open action space. Each is one thing the director may do next. Budget
# allocation is NOT a separate action — it is the budget_moves a spawn hands its
# child (docs/free_director_plan.md: freedom in WHAT, the Budget bounds HOW MUCH).
ACTION_VALUES = (
    "run_experiment",          # dispatch one experiment run (spends one move)
    "spawn_sub_investigation", # delegate a slice of the budget to a child director
    "call_integration",        # verify the accumulated parts COMPOSE (joint check)
    "call_ideation",           # OPTIONAL tool: the hypothesis apparatus, on demand
    "call_validation",         # OPTIONAL tool: the heavy validation apparatus
    "call_data_analysis",      # OPTIONAL tool: analyze results gathered so far
    "read_memory",             # read prior studies' accumulated findings
    "write_memory",            # record a lesson for future studies
    "stop",                    # end the investigation (goal answered / converged)
)

_ENVELOPE_FIELDS = (
    "ack", "reading", "reasoning", "action",
    "domain", "instrument", "campaign", "budget_moves", "detail", "depth", "pool_size",
    "stop_reason",
)

# Ideation depth (R-FD-6). The hypothesis apparatus has two settings and the
# director picks: "quick" is one generation strategy, "full" is the whole
# Co-Scientist apparatus (four generation strategies, six review types, an Elo
# tournament, evolution, meta-review). Default quick — cheap by default, escalated
# by judgment when the IDEAS are the deliverable rather than a means to one.
DEPTH_VALUES = ("quick", "full")
DEFAULT_IDEATION_DEPTH = "quick"

SYSTEM_PROMPT = """You are the principal investigator of an autonomous research system, running unattended. You hold ONE goal for the whole investigation and drive it by choosing a sequence of actions, each following from what the last ones showed.

You are a FULL researcher above the execution layer: you may read literature, run code to sanity-check an idea, and reason with tools before you commit. The ONE thing you never do is produce or restate a measurement — a number of record comes from an instrument and its independent verification inside an experiment, never from you. Above that boundary you are free.

YOUR ACTION SPACE (choose exactly one per turn):
- "run_experiment": point one experiment run at a QUESTION ("domain"). Optionally force an "instrument" from the menu, or leave it null for the run to choose. Set "campaign": true for an iterated sweep instead of a single run. Spends one move of your budget.
- "spawn_sub_investigation": delegate a sub-question ("domain") to a child director with "budget_moves" of your budget carved off for it. Use this to DECOMPOSE — break a big goal into subsystems, each investigated on its own slice. The child cannot exceed the budget you hand it.
- "call_integration": run an experiment that checks whether the parts you have verified so far actually COMPOSE into a working whole, and measures the joint behavior. Spends one move. Use it after you decompose: subsystems that each pass on their own can still fail together (each locally optimal, the assembly incompatible), and re-running each part's number will never catch that — only assembling and measuring them jointly will. Put the joint criterion in "detail". Do NOT declare a decomposed goal answered until an integration check has stood.
- "call_ideation": invoke the hypothesis apparatus for a question when you want many candidate directions, not one. It returns ranked candidate hypotheses to YOU — you then decide what to do with them, so you may call it at any point in the investigation, not only at the start, and more than once. OPTIONAL — reach for it only when the task warrants; it is not a mandatory step. ASK IT THE OPEN QUESTION: do NOT narrow the request to your instrument menu, do not list the instruments in it, and do not ask only for hypotheses those tools can run. The menu is what YOU use when dispatching an experiment; pre-constraining ideation to it produces candidates shaped around existing tools, which are overwhelmingly the questions those tools' fields have already answered. Feasibility is judged after the ideas exist, by the reviews and by you. Set "depth": "quick" (the default) for one fast generation pass, or "depth": "full" for the whole apparatus — four competing generation strategies, six review types, an Elo tournament between hypotheses, evolution of the survivors, and a meta-review. "full" costs many model calls and takes far longer, so choose it when the IDEAS THEMSELVES are the deliverable, or when a quick pass came back thin or obvious; choose "quick" when you mainly need a direction to go test. Set "pool_size" to the NUMBER of candidate hypotheses you want — breadth is something you buy out of your token budget, so ask for a large pool when the ideas themselves are the deliverable and you can afford the reviews, and a small one when you just need a direction. Every candidate is reviewed, so cost scales with the pool.
- "call_validation": invoke heavy independent validation of results gathered so far, when the stakes warrant more than each experiment's own verification. OPTIONAL.
- "call_data_analysis": analyze the results the arc has accumulated. OPTIONAL.
- "read_memory" / "write_memory": read prior studies' findings, or record a lesson ("detail") for future ones.
- "stop": end the investigation. Choose it when the goal is answered, the arc has converged, or further moves are unlikely to help. Do not spend moves for their own sake.

YOUR BUDGET IS TOKENS, AND YOU DECIDE HOW TO SPEND THEM. When your budget carries a "token_budget", that is the real ceiling on this whole investigation — the move pool beside it is only a structural backstop. Read "tokens_remaining" every turn and scale your ambition to it, because the choices are yours: how many phases to run, whether to decompose into sub-investigations, whether to call ideation at "quick" or "full" depth, whether to scale a promising probe up or stop with what stands. Depth and thoroughness are things you buy.
Rough costs, measured: a substantive experiment run costs a few million to twenty-odd million tokens depending on how much work it does; a "full" ideation pass costs on the order of fifteen million; a "quick" one is far cheaper; your own decisions cost very little. A move count tells you almost nothing about cost — a two-move study has cost more than a four-move one — so plan in tokens, not moves. Spend generously while you have room and land the investigation cleanly before you run out: an arc that stops with a verified result and a written conclusion is worth more than one that spends its last tokens starting something it cannot finish.

MATCH THE SCALE OF THE WORK TO THE DIFFICULTY OF THE GOAL. Budget is not a target to hit. If a goal turns out to be easy, the right move is to go FURTHER — a harder version of the question, a real constraint, the next subsystem, the case that would actually break it — not to measure the same easy thing more ways. A measured failure to watch for: an investigation spent an enormous budget on a simple design by deriving one number through three independent routes, cross-validating them against each other, and sweeping robustness corners, because confirming was the only dimension left to be thorough in. That is effort, not progress. Redundant confirmation of something already established is the cheapest way to look busy and the most expensive way to learn nothing.
So read the difficulty honestly. When the arc has answered the question and the remaining budget is large, ask what the answer makes possible that was not possible before, and go do that. When you conclude, say plainly if the goal was easier than its budget assumed — that is useful information for whoever set it, and far better than padding.

DISCIPLINE. Work small-before-big: run a cheap experiment, read the VERIFIED result, then scale up, change tack, decompose, or stop — read that judgment off what you actually observed. Respect your budget: it is a hard ceiling on how much you may spend, and a sub-investigation's slice comes out of it. Decompose only when the goal genuinely has separable parts; a simple goal may need just one experiment and a stop.

Reply ONLY with JSON of the form {"ack": "<the study_id you were given>", "reading": "<one or two sentences: what the most recent action's result showed, and what it means for the goal; null only on the first turn when nothing has run>", "reasoning": "<1-3 sentences: why this action next>", "action": "run_experiment" | "spawn_sub_investigation" | "call_ideation" | "call_validation" | "call_data_analysis" | "read_memory" | "write_memory" | "stop", "domain": "<the exact question for run_experiment or spawn_sub_investigation, else null>", "instrument": "<a substrate_id from the menu to force, or null; for run_experiment or call_integration>", "campaign": <true|false, only meaningful for run_experiment; default false>, "budget_moves": <int moves to allocate to the child, required for spawn_sub_investigation, else null>, "detail": "<the request for call_* / write_memory, else null>", "depth": "<'quick' or 'full' for call_ideation, else null>", "pool_size": "<int candidate count for call_ideation, else null>", "stop_reason": "<why the investigation is complete, required for stop, else null>"} — no other fields anywhere."""

SCHEMA = {"required": ["ack", "reasoning", "action"]}


def make_action_validator(
    study_id: str, arc_len: int, choosable: tuple = ()
) -> Callable[[dict], list]:
    """The deep validator handed to the door. Envelope is exactly the ten fields;
    ack echoes study_id; action is in the vocabulary; reasoning is non-empty;
    per-action required fields are present; a named instrument is on the menu and
    only on a run_experiment; once a move has run, reading is non-empty. Plain
    errors, empty = valid — each is re-sent to the model inside the bounded loop."""

    def validator(parsed: dict) -> list:
        errors = [
            f"reply field {key!r} is not allowed — reply with exactly "
            f"{', '.join(_ENVELOPE_FIELDS)}, nothing else."
            for key in parsed
            if key not in _ENVELOPE_FIELDS
        ]
        if parsed.get("ack") != study_id:
            errors.append(f"ack must echo the study_id {study_id!r}; got {parsed.get('ack')!r}.")

        action = parsed.get("action")
        if action not in ACTION_VALUES:
            errors.append(
                f"action must be one of {', '.join(ACTION_VALUES)}; got {action!r}."
            )

        reasoning = parsed.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            errors.append("reasoning must be a non-empty string.")

        if action in ("run_experiment", "spawn_sub_investigation"):
            domain = parsed.get("domain")
            if not isinstance(domain, str) or not domain.strip():
                errors.append(
                    f"domain must be a non-empty question when the action is {action}."
                )

        if action == "spawn_sub_investigation":
            bm = parsed.get("budget_moves")
            if not isinstance(bm, int) or isinstance(bm, bool) or bm < 1:
                errors.append(
                    "budget_moves must be an integer >= 1 when the action is "
                    "spawn_sub_investigation (the moves carved off for the child)."
                )

        # pool_size: how many hypotheses to generate. Like depth, it is
        # call_ideation's dial and nothing else's, and it is what lets the
        # director BUY BREADTH out of its token budget rather than inheriting a
        # fixed env default.
        pool = parsed.get("pool_size")
        if pool is not None:
            if action != "call_ideation":
                errors.append(
                    f"pool_size must be null when the action is {action} (only "
                    "call_ideation takes a pool_size).")
            elif isinstance(pool, bool) or not isinstance(pool, int) or pool < 1:
                errors.append(
                    "pool_size must be a positive integer (the number of "
                    "candidate hypotheses to generate), or null for the default.")

        # depth: null is always valid (the tool's own default). A named depth must
        # be in the vocabulary AND only on call_ideation — it is that tool's dial,
        # and naming it elsewhere means the director has confused two actions.
        depth = parsed.get("depth")
        if depth is not None:
            if action != "call_ideation":
                errors.append(
                    f"depth must be null when the action is {action} (only "
                    "call_ideation takes a depth).")
            elif depth not in DEPTH_VALUES:
                errors.append(
                    f"depth must be one of {', '.join(DEPTH_VALUES)} (or null for "
                    f"{DEFAULT_IDEATION_DEPTH}); got {depth!r}.")

        if action in ("call_ideation", "call_validation", "call_data_analysis", "write_memory"):
            detail = parsed.get("detail")
            # call_ideation's request may be carried by `domain` instead — the
            # executor already reads `domain or detail`, and rejecting a reply that
            # said what to ask, in the other field, cost two re-asks live for
            # nothing. Either field satisfies it; both empty is still an error.
            alt = parsed.get("domain") if action == "call_ideation" else None
            has_request = (isinstance(detail, str) and detail.strip()) or (
                isinstance(alt, str) and alt.strip())
            if not has_request:
                errors.append(
                    f"detail must be a non-empty string when the action is {action} "
                    "(what to ask the tool, or the lesson to record)."
                )

        if action == "stop":
            sr = parsed.get("stop_reason")
            if not isinstance(sr, str) or not sr.strip():
                errors.append("stop_reason must be a non-empty string when the action is stop.")

        # instrument: null is always valid; a named one must be on the menu AND
        # only on an action that DISPATCHES a run — run_experiment or
        # call_integration (both go through run_move). A spawned child chooses its
        # own; the pure tools, memory, and stop name no instrument.
        instrument = parsed.get("instrument")
        if instrument is not None:
            if action not in ("run_experiment", "call_integration"):
                errors.append(
                    f"instrument must be null when the action is {action} "
                    "(only run_experiment or call_integration may force an instrument)."
                )
            elif choosable and instrument not in choosable:
                errors.append(
                    f"instrument must be one of the menu {list(choosable)} "
                    f"(or null to let the run choose); got {instrument!r}."
                )

        if arc_len > 0:
            reading = parsed.get("reading")
            if not isinstance(reading, str) or not reading.strip():
                errors.append(
                    "reading must be a non-empty string once at least one action has run "
                    "(only the first decision, with an empty arc, may leave it null)."
                )
        return errors

    return validator


def _action_space_menu() -> list:
    """The vocabulary with one-line descriptions, so the director reasons over what
    each action DOES, not just its name. Pure; mirrors instrument_menu's role."""
    return [
        {"action": "run_experiment", "does": "point one experiment run at a question; spends one move"},
        {"action": "spawn_sub_investigation", "does": "delegate a sub-question to a child director with a slice of the budget"},
        {"action": "call_integration", "does": "run a joint check that the verified parts COMPOSE into a working whole; spends one move"},
        {"action": "call_ideation", "does": "OPTIONAL: invoke the hypothesis apparatus for many candidate directions; ask it the OPEN question, never narrowed to the instrument menu; depth 'quick' (default) = one generation pass, 'full' = four strategies + six reviews + Elo tournament + evolution + meta-review"},
        {"action": "call_validation", "does": "OPTIONAL: heavy independent validation beyond each experiment's own"},
        {"action": "call_data_analysis", "does": "OPTIONAL: analyze the results accumulated in the arc"},
        {"action": "read_memory", "does": "read prior studies' accumulated findings"},
        {"action": "write_memory", "does": "record a lesson for future studies"},
        {"action": "stop", "does": "end the investigation"},
    ]


def build_free_director_input(study: Any, arc: list, budget: dict) -> dict:
    """The exact input the free director reasons over. Pure over the study's disk
    state. Carries no run_id (PI-layer evidence, not a run's transcript)."""
    return {
        "study_id": study.study_id,
        "goal": study.goal,
        "instrument_constraint": study.allowed_substrates,  # null = unconstrained
        "instrument_menu": instrument_menu(study),
        "action_space": _action_space_menu(),
        "budget": budget,  # the Budget.report(): remaining / depth / max_depth
        "arc_so_far": arc,
    }


def decide_action(
    study: Any,
    arc: list,
    budget: dict,
    *,
    call: Callable = call_stage_model,
    model: str = FREE_DIRECTOR_MODEL,
) -> dict:
    """Make one free-director decision and record it under the study. `call` is the
    model door, injected so the loop is exercisable offline with fakes. Returns the
    validated action dict. Raises whatever the door raises after its bounded
    re-asks — the loop catches it and ends the study honestly."""
    stage_input = build_free_director_input(study, arc, budget)
    validator = make_action_validator(
        study.study_id, len(arc), choosable_instruments(study)
    )
    # Confine this FULL agent's tool cwd to the study's scratch dir so any file it
    # writes while reasoning stays out of the repo root (see study_scratch_dir).
    with agent_workspace(study_scratch_dir(study)):
        data, timing = call(
            FREE_DIRECTOR_STAGE,
            SYSTEM_PROMPT,
            stage_input,
            SCHEMA,
            model=model,
            extra_validator=validator,
            capabilities=FULL,
        )
    _record_decision(study, len(arc) + 1, stage_input, data, timing)
    return data


def _record_decision(study: Any, seq: int, stage_input: dict, decision: dict, timing: dict) -> None:
    """Write the decision to studies/<id>/decisions/decide<seq>.json — the free
    director's reasoning trail. Never raises: losing the evidence file must not lose
    the decision the loop is about to act on."""
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
