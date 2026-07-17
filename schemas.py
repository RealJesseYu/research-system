"""
schemas.py — the locked baton-payload schemas, one validator per boundary.

LOCKED AT STEP 15. Changes require a recorded ruling (same discipline as
frozen prompts).
Ruled change, Step 16: optional prior_thought at post-gate-1 (loop-back
re-entry), persists through pass-2 boundaries — every boundary tolerates
it, and when present it must be a valid thought shape.
Ruled change, D.5 (R1 option 4, 2026-07-17): execution run entries admit
an optional per-substrate `state` key (non-empty string when present).
The required set is unchanged — {converged, wall_clock_s, and exactly one
of qoi_value | qoi_error} — and an entry without `state` validates
byte-identically, so every cavity entry is untouched. Allowed `state`
VALUES are contract-§3 material per substrate (e.g. run_scipy's tri-state
solved_verified | unevaluated | error), never enumerated here: schemas.py
stays substrate-neutral.
Deferred candidates and wake conditions:
  - candidate 1 (categorical parameter role): wake on a second live
    categorical occurrence or a downstream mis-read;
  - candidate 4 (coupled/redundant sweep declaration): wake on a
    consistent-redundant sweep misleading a downstream stage.
Rejected: instrument-extension-request field (the halt->thought->journal
path carries it; no consumer).

Every validator is a documented pure function in validate_spec's style:
it takes a baton payload, returns a list of plain-language error strings,
and an empty list means valid. It never raises on bad input — malformed
structure becomes error strings too. The shapes are not invented here:
each is derived from the Step-15 chunk-1 evidence runs read from disk
(RUN A 20260706T044214Z, RUN B handfeed4-20260706T045314Z, RUN C
handfeed4-20260706T045429Z) and cited per validator below.

The supervisor calls these at each boundary and halts loudly on any
non-empty result — a malformed baton is a broken invariant, not a model
error, so there is no re-ask and no correction loop here.
"""

from __future__ import annotations

from typing import Any

from stages.stage2_spec import validate_spec
from stages.stage5_thought_layer import (
    DECISION_VALUES,
    THOUGHT_FIELDS,
    TRIAGE_VALUES,
)

VERDICT_LABELS = ("trust", "refine", "defer")
EXECUTION_STATUSES = ("executed", "skipped_defer", "halted_synthesis")

# R-23.5-4 (owner, 2026-07-17): the post-gate-1 payload is exactly
# {domain, chosen_hypothesis, substrate_id} — the decided instrument travels
# the payload (it enters NO composed prompt anywhere) so stages 3 and 4 can
# compare it against select_substrate's spec-derived answer. The downstream
# boundaries widen BY DERIVATION (build-chat ruling on the 2d/3c split: a
# schema shape is atomic across its boundaries — every boundary that
# validates the payload requires the key; no boundary where it is optional).
POST_GATE1_KEYS = ("domain", "chosen_hypothesis", "substrate_id")
POST_STAGE2_KEYS = POST_GATE1_KEYS + ("experiment_spec",)
POST_STAGE3_KEYS = POST_STAGE2_KEYS + ("fidelity_verdict",)
POST_STAGE4_KEYS = POST_STAGE3_KEYS + ("execution_results",)
POST_STAGE5_KEYS = POST_STAGE4_KEYS + ("thought", "iterate_decision")

CHOSEN_HYPOTHESIS_KEYS = ("id", "statement", "rationale")
FIDELITY_VERDICT_KEYS = ("label", "rationale", "right_instrument")

# The SINGLE source for the run-entry key set (D.5 census: schemas.py is the
# one production site enforcing this shape — never a second key list).
# `state` is the D.5-ruled optional (R1 option 4); the other four are the
# locked Step-15 required set.
RUN_ENTRY_KEYS = ("converged", "wall_clock_s", "qoi_value", "qoi_error", "state")


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    """True for int/float but NOT bool (bool is an int subclass in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


OPTIONAL_PAYLOAD_KEYS = ("prior_thought",)  # ruled Step 16, every boundary


def _check_exact_keys(
    obj: dict, allowed: tuple, boundary: str, errors: list[str]
) -> None:
    """The payload at a boundary carries exactly its boundary's keys —
    nothing missing, nothing extra — plus the ruled optional keys
    (prior_thought, Step 16), which may be present at any boundary."""
    for key in allowed:
        if key not in obj:
            errors.append(
                f"the {boundary} payload is missing required field '{key}'."
            )
    for key in obj:
        if key not in allowed and key not in OPTIONAL_PAYLOAD_KEYS:
            errors.append(
                f"payload field '{key}' is not part of the {boundary} payload — "
                f"it carries exactly: {', '.join(allowed)} (plus optionally "
                f"{', '.join(OPTIONAL_PAYLOAD_KEYS)})."
            )


def _check_domain(payload: dict, errors: list[str]) -> None:
    if "domain" in payload and not _is_non_empty_str(payload["domain"]):
        errors.append(
            f"payload domain must be a non-empty string; got {payload['domain']!r}."
        )


def _check_chosen_hypothesis(payload: dict, errors: list[str]) -> None:
    if "chosen_hypothesis" not in payload:
        return
    chosen = payload["chosen_hypothesis"]
    if not isinstance(chosen, dict):
        errors.append(
            "chosen_hypothesis must be an object with exactly id, statement, "
            "and rationale."
        )
        return
    for key in CHOSEN_HYPOTHESIS_KEYS:
        if not _is_non_empty_str(chosen.get(key)):
            errors.append(
                f"chosen_hypothesis {key} must be a non-empty string; "
                f"got {chosen.get(key)!r}."
            )
    for key in chosen:
        if key not in CHOSEN_HYPOTHESIS_KEYS:
            errors.append(
                f"chosen_hypothesis field '{key}' is not allowed — it carries "
                f"exactly: {', '.join(CHOSEN_HYPOTHESIS_KEYS)}."
            )


def _check_substrate_id(payload: dict, errors: list[str]) -> None:
    """R-23.5-4 (owner, 2026-07-17): substrate_id is a non-empty string —
    checked in code, never a prompt. Routable membership is the registry's
    judgment at the consuming sites (gate validator, stages 3/4), not a
    schema concern. A missing key is reported by _check_exact_keys."""
    if "substrate_id" not in payload:
        return
    if not _is_non_empty_str(payload["substrate_id"]):
        errors.append(
            f"substrate_id must be a non-empty string; "
            f"got {payload['substrate_id']!r}."
        )


def _check_experiment_spec(payload: dict, errors: list[str]) -> None:
    """Defer to validate_spec for the spec's internals — never duplicated
    here. The hypothesis-id pin comes from the payload's own
    chosen_hypothesis; when that id is itself broken, the errors already
    say so and the pin check is skipped rather than guessed."""
    if "experiment_spec" not in payload:
        return
    chosen = payload.get("chosen_hypothesis")
    chosen_id = chosen.get("id") if isinstance(chosen, dict) else None
    if _is_non_empty_str(chosen_id):
        errors.extend(validate_spec(payload["experiment_spec"], chosen_id))


def _check_fidelity_verdict(payload: dict, errors: list[str]) -> None:
    if "fidelity_verdict" not in payload:
        return
    verdict = payload["fidelity_verdict"]
    if not isinstance(verdict, dict):
        errors.append(
            "fidelity_verdict must be an object with exactly label, rationale, "
            "and right_instrument."
        )
        return
    if verdict.get("label") not in VERDICT_LABELS:
        errors.append(
            f"fidelity_verdict label must be exactly one of "
            f"{' | '.join(VERDICT_LABELS)}; got {verdict.get('label')!r}."
        )
    for key in ("rationale", "right_instrument"):
        if not _is_non_empty_str(verdict.get(key)):
            errors.append(
                f"fidelity_verdict {key} must be a non-empty string; "
                f"got {verdict.get(key)!r}."
            )
    for key in verdict:
        if key not in FIDELITY_VERDICT_KEYS:
            errors.append(
                f"fidelity_verdict field '{key}' is not allowed — it carries "
                f"exactly: {', '.join(FIDELITY_VERDICT_KEYS)}."
            )


def _check_execution_run_entry(entry: Any, label: str, errors: list[str]) -> None:
    """One conclusions-only run entry: {converged, wall_clock_s, and exactly
    one of qoi_value | qoi_error} — the shape stage 4 writes (RUN B) — plus
    the D.5-ruled optional `state` (non-empty string; per-substrate values
    are contract material, not checked here)."""
    if not isinstance(entry, dict):
        errors.append(f"{label} must be an object.")
        return
    if not isinstance(entry.get("converged"), bool):
        errors.append(
            f"{label} converged must be true or false; got {entry.get('converged')!r}."
        )
    if not _is_number(entry.get("wall_clock_s")):
        errors.append(
            f"{label} wall_clock_s must be a number; got {entry.get('wall_clock_s')!r}."
        )
    has_value = "qoi_value" in entry
    has_error = "qoi_error" in entry
    if has_value == has_error:
        errors.append(
            f"{label} must carry exactly one of qoi_value or qoi_error; "
            f"got {'both' if has_value else 'neither'}."
        )
    if has_value and not _is_number(entry["qoi_value"]):
        errors.append(
            f"{label} qoi_value must be a number; got {entry['qoi_value']!r}."
        )
    if has_error and not _is_non_empty_str(entry["qoi_error"]):
        errors.append(
            f"{label} qoi_error must be a non-empty string; got {entry['qoi_error']!r}."
        )
    if "state" in entry and not _is_non_empty_str(entry["state"]):
        errors.append(
            f"{label} state, when present, must be a non-empty string; "
            f"got {entry['state']!r}."
        )
    for key in entry:
        if key not in RUN_ENTRY_KEYS:
            errors.append(
                f"{label} field '{key}' is not allowed — a run entry carries "
                f"exactly converged, wall_clock_s, and qoi_value or qoi_error, "
                f"plus the optional state."
            )


def _check_execution_results(payload: dict, errors: list[str]) -> None:
    """Shape-per-status as found ON DISK across the Step-15 chunk-1 runs:

      skipped_defer    -> exactly {status}                (RUN A
                          20260706T044214Z/baton_after_stage_4.json)
      executed         -> {status, runs non-empty}        (RUN B
                          handfeed4-20260706T045314Z/baton_after_stage_4.json)
      halted_synthesis -> {status, runs (may be empty), reason}  (RUN C
                          handfeed4-20260706T045429Z/baton_after_stage_4.json)

    The refine flag key is named exactly 'flag'. Its presence rule is what
    disk and stage-4 code show — required iff the verdict label is refine
    AND the status is not skipped_defer: RUN C carries it on
    halted_synthesis (refine verdict), RUN B (trust, executed) and RUN A
    (defer, skipped_defer) do not. NOTE: this is broader than 'refine and
    executed' — the halted evidence decided it.
    """
    if "execution_results" not in payload:
        return
    results = payload["execution_results"]
    if not isinstance(results, dict):
        errors.append(
            "execution_results must be an object with a status of "
            f"{' | '.join(EXECUTION_STATUSES)}."
        )
        return
    status = results.get("status")
    if status not in EXECUTION_STATUSES:
        errors.append(
            f"execution_results status must be exactly one of "
            f"{' | '.join(EXECUTION_STATUSES)}; got {status!r}."
        )
        return

    verdict = payload.get("fidelity_verdict")
    verdict_label = verdict.get("label") if isinstance(verdict, dict) else None
    flag_required = verdict_label == "refine" and status != "skipped_defer"
    allowed = {"status"}
    if status == "executed":
        allowed |= {"runs"}
    elif status == "halted_synthesis":
        allowed |= {"runs", "reason"}
    if flag_required:
        allowed |= {"flag"}

    if status == "skipped_defer":
        pass  # exactly {status}: extra-key sweep below enforces it (RUN A)
    else:
        runs = results.get("runs")
        if not isinstance(runs, list):
            errors.append(
                f"execution_results runs must be a list of run entries; got {runs!r}."
            )
        else:
            if status == "executed" and not runs:
                errors.append(
                    "execution_results with status executed must carry at "
                    "least one run entry."
                )
            for n, entry in enumerate(runs, start=1):
                _check_execution_run_entry(
                    entry, f"execution_results run {n}", errors
                )
        if status == "halted_synthesis" and not _is_non_empty_str(
            results.get("reason")
        ):
            errors.append(
                "execution_results with status halted_synthesis must carry a "
                f"non-empty string reason; got {results.get('reason')!r}."
            )

    if flag_required and not _is_non_empty_str(results.get("flag")):
        errors.append(
            "execution_results must carry a non-empty string 'flag' when the "
            "fidelity verdict is refine and something was attempted; "
            f"got {results.get('flag')!r}."
        )
    for key in results:
        if key not in allowed:
            errors.append(
                f"execution_results field '{key}' is not allowed for status "
                f"{status}{' with a refine verdict' if flag_required else ''} — "
                f"allowed: {', '.join(sorted(allowed))}."
            )


def _check_thought_shape(thought: Any, label: str, errors: list[str]) -> None:
    """One thought-shaped object: exactly the five fields, non-empty strings,
    both enums valid. Shared by the payload's thought and (Step 16, ruled)
    the optional prior_thought carried back on loop-back re-entry."""
    if not isinstance(thought, dict):
        errors.append(
            f"{label} must be an object with exactly: "
            + ", ".join(THOUGHT_FIELDS)
            + "."
        )
        return
    for field in THOUGHT_FIELDS:
        if not _is_non_empty_str(thought.get(field)):
            errors.append(
                f"{label} {field} must be a non-empty string; "
                f"got {thought.get(field)!r}."
            )
    if thought.get("surprise_triage") not in TRIAGE_VALUES:
        errors.append(
            f"{label} surprise_triage must be exactly one of "
            f"{' | '.join(TRIAGE_VALUES)}; "
            f"got {thought.get('surprise_triage')!r}."
        )
    if thought.get("iterate_decision") not in DECISION_VALUES:
        errors.append(
            f"{label} iterate_decision must be exactly one of "
            f"{' | '.join(DECISION_VALUES)}; "
            f"got {thought.get('iterate_decision')!r}."
        )
    for key in thought:
        if key not in THOUGHT_FIELDS:
            errors.append(
                f"{label} field '{key}' is not allowed — the {label} "
                f"carries exactly: {', '.join(THOUGHT_FIELDS)}."
            )


def _check_prior_thought(payload: dict, errors: list[str]) -> None:
    """Ruled Step 16: prior_thought is OPTIONAL at every boundary; when
    present it must be a valid thought shape."""
    if "prior_thought" in payload:
        _check_thought_shape(payload["prior_thought"], "prior_thought", errors)


def _check_thought_and_decision(payload: dict, errors: list[str]) -> None:
    if "thought" in payload:
        thought = payload["thought"]
        _check_thought_shape(thought, "thought", errors)
        if (
            isinstance(thought, dict)
            and "iterate_decision" in payload
            and payload["iterate_decision"] != thought.get("iterate_decision")
        ):
            errors.append(
                f"payload iterate_decision must match thought."
                f"iterate_decision exactly; got payload "
                f"{payload['iterate_decision']!r} vs thought "
                f"{thought.get('iterate_decision')!r}."
            )
    if (
        "iterate_decision" in payload
        and payload["iterate_decision"] not in DECISION_VALUES
    ):
        errors.append(
            f"payload iterate_decision must be exactly one of "
            f"{' | '.join(DECISION_VALUES)}; got {payload['iterate_decision']!r}."
        )


def _as_payload(payload: Any) -> tuple[dict | None, list[str]]:
    if not isinstance(payload, dict):
        return None, ["the payload must be a JSON object."]
    return payload, []


def validate_payload_post_gate1(payload: Any) -> list[str]:
    """Boundary gate 1 -> stage 2: exactly {domain, chosen_hypothesis,
    substrate_id} (R-23.5-4, owner 2026-07-17); chosen_hypothesis exactly
    {id, statement, rationale}, non-empty strings; substrate_id a non-empty
    string. Pre-23.5 evidence of the two-key era:
    runs/20260706T044214Z/baton_after_gate_1.json (RUN A)."""
    payload, errors = _as_payload(payload)
    if payload is None:
        return errors
    _check_exact_keys(payload, POST_GATE1_KEYS, "post-gate-1", errors)
    _check_prior_thought(payload, errors)
    _check_domain(payload, errors)
    _check_chosen_hypothesis(payload, errors)
    _check_substrate_id(payload, errors)
    return errors


def validate_payload_post_stage2(payload: Any) -> list[str]:
    """Boundary stage 2 -> stage 3: the post-gate-1 payload plus
    experiment_spec (internals deferred to validate_spec — called, never
    duplicated). Evidence: runs/20260706T044214Z/baton_after_stage_2.json."""
    payload, errors = _as_payload(payload)
    if payload is None:
        return errors
    _check_exact_keys(payload, POST_STAGE2_KEYS, "post-stage-2", errors)
    _check_prior_thought(payload, errors)
    _check_domain(payload, errors)
    _check_chosen_hypothesis(payload, errors)
    _check_substrate_id(payload, errors)
    _check_experiment_spec(payload, errors)
    return errors


def validate_payload_post_stage3(payload: Any) -> list[str]:
    """Boundary stage 3 -> stage 4: the post-stage-2 payload plus
    fidelity_verdict exactly {label in trust|refine|defer, rationale,
    right_instrument}, non-empty strings.
    Evidence: runs/20260706T044214Z/baton_after_stage_3.json."""
    payload, errors = _as_payload(payload)
    if payload is None:
        return errors
    _check_exact_keys(payload, POST_STAGE3_KEYS, "post-stage-3", errors)
    _check_prior_thought(payload, errors)
    _check_domain(payload, errors)
    _check_chosen_hypothesis(payload, errors)
    _check_substrate_id(payload, errors)
    _check_experiment_spec(payload, errors)
    _check_fidelity_verdict(payload, errors)
    return errors


def validate_payload_post_stage4(payload: Any) -> list[str]:
    """Boundary stage 4 -> stage 5: the post-stage-3 payload plus
    execution_results, shape-per-status as read from disk (statuses and the
    refine-flag rule documented on _check_execution_results, with the source
    run cited for each status)."""
    payload, errors = _as_payload(payload)
    if payload is None:
        return errors
    _check_exact_keys(payload, POST_STAGE4_KEYS, "post-stage-4", errors)
    _check_prior_thought(payload, errors)
    _check_domain(payload, errors)
    _check_chosen_hypothesis(payload, errors)
    _check_substrate_id(payload, errors)
    _check_experiment_spec(payload, errors)
    _check_fidelity_verdict(payload, errors)
    _check_execution_results(payload, errors)
    return errors


def validate_payload_post_stage5(payload: Any) -> list[str]:
    """Boundary stage 5 -> stage 6: the post-stage-4 payload plus thought
    (five non-empty string fields, both enums re-checked) and a top-level
    iterate_decision matching thought.iterate_decision exactly.
    Evidence: runs/20260706T044214Z/baton_after_stage_5.json (RUN A);
    executed-path shape runs/handfeed4-20260706T045314Z (RUN B)."""
    payload, errors = _as_payload(payload)
    if payload is None:
        return errors
    _check_exact_keys(payload, POST_STAGE5_KEYS, "post-stage-5", errors)
    _check_prior_thought(payload, errors)
    _check_domain(payload, errors)
    _check_chosen_hypothesis(payload, errors)
    _check_substrate_id(payload, errors)
    _check_experiment_spec(payload, errors)
    _check_fidelity_verdict(payload, errors)
    _check_execution_results(payload, errors)
    _check_thought_and_decision(payload, errors)
    return errors
