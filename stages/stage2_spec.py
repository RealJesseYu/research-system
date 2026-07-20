"""
stage2_spec.py — the typed experiment-spec schema and its validator.

Pure functions, zero model calls. stage2_experiment_design.py imports
validate_spec and runs it as call_stage_model's extra_validator: the model
is asked for a spec, checked with validate_spec, and the error strings are
sent back as guided corrections until the spec is clean.

validate_spec(spec, chosen_id, vocab) is the deep check: every rule returns
a plain-language error string phrased so it can be sent straight back to the
model as a correction. An empty list means the spec is valid. It never
raises on bad input — malformed structure becomes error strings too. The
vocab argument is REQUIRED (R-23.5-5a): a missing/None vocabulary raises,
never a silent cavity resolution.
"""

from __future__ import annotations

from typing import Any

# D.3: the wrapper's own QoI vocabularies stay the single source of truth,
# now reached through the per-substrate lookup (tools/qoi_vocab.py — the sole
# sanctioned import site of run_cfd's vocabulary objects) instead of a direct
# run_cfd import. The record is shape-tagged (field-reduction vs
# named-quantity) and the qoi checks dispatch on the shape, never on a
# substrate name.
from tools.qoi_vocab import (
    ANALYSIS_TYPE,
    DESCRIPTOR_COMPUTATION,
    FBA_STEADY_STATE,
    FIELD_REDUCTION,
    FIXED_SUMMARY,
    HOMOLOGY_SEARCH,
    MSA_ALIGNMENT,
    NAMED_QUANTITY,
    OPERATION_SET,
    REYNOLDS_BAND,
    STATIC_SMALL_DEFLECTION,
    SYMBOLIC_RESULT,
)

REQUIRED_SPEC_FIELDS = (
    "hypothesis_id",
    "title",
    "objective",
    "parameters",
    "qoi",
    "success_criterion",
    "regime",
    "mini_experiment",
    "full_experiment",
)

# Phase-1 Lane-2: OPTIONAL additive fields. Absent (the current state of every
# on-disk spec) leaves validation byte-identical — the unknown-field check below
# tolerates these names but nothing requires them, and NO stage-2 prompt asks a
# model to emit them (the prompt is frozen). `control_block` carries a null-twin
# control experiment: {description, params, expected_null_outcome} — the design
# under which the hypothesized effect should VANISH, so a downstream comparison
# (tools/null_twin.py) can catch an artifact that reproduces the effect anyway.
#
# `qois` (Multi-QoI build, part B) carries a LIST of qoi objects — the same
# shape as the single `qoi`, each entry additionally permitted a `mask`. It
# rides alongside the existing single `qoi`, never replacing it: absent leaves
# validation byte-identical, and no stage-2 prompt asks for it (frozen). A spec
# that requests a masked or interior extremum declares it here; the eventual
# stage-4 translation to the wrapper's `qois=[...]` vector is a later build.
OPTIONAL_SPEC_FIELDS = (
    "control_block",
    "qois",
)

QOI_REQUIRED_FIELDS = ("name", "units", "definition", "how_extracted")

MIN_MINI_RUNS = 1
MAX_MINI_RUNS = 3


def _is_number(value: Any) -> bool:
    """True for int/float but NOT bool (bool is an int subclass in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_parameters(params: Any, errors: list[str]) -> tuple[dict, dict, set]:
    """Check the parameters list; return (sweep_ranges, fixed_values,
    derived_names) for the entries that validated, so the mini_experiment
    checks only test against declarations that are themselves sound.
    """
    sweep_ranges: dict[str, tuple[float, float]] = {}
    fixed_values: dict[str, Any] = {}
    derived_names: set[str] = set()

    if not isinstance(params, list):
        errors.append("parameters must be a list of parameter objects.")
        return sweep_ranges, fixed_values, derived_names

    for idx, p in enumerate(params):
        label = f"parameters[{idx}]"
        if not isinstance(p, dict):
            errors.append(f"{label} must be an object with name, role, and units.")
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{label} is missing a non-empty string 'name'.")
            continue
        if "units" not in p:
            errors.append(f"parameter '{name}' is missing 'units'.")

        role = p.get("role")
        if role == "sweep":
            lo, hi = p.get("min"), p.get("max")
            if not _is_number(lo) or not _is_number(hi):
                errors.append(
                    f"sweep parameter '{name}' must carry numeric 'min' and 'max'; "
                    f"got min={lo!r}, max={hi!r}."
                )
            elif not lo < hi:
                errors.append(
                    f"sweep parameter '{name}' must have min strictly less than max; "
                    f"got min={lo} and max={hi}."
                )
            else:
                sweep_ranges[name] = (lo, hi)
        elif role == "fixed":
            # Step-15 docket, candidate 3: a fixed parameter is a numeric
            # quantity — prose or other non-numeric content is not a value.
            if "value" not in p:
                errors.append(f"fixed parameter '{name}' must carry a 'value'.")
            elif not _is_number(p["value"]):
                errors.append(
                    f"fixed parameter '{name}' must carry a numeric 'value'; got "
                    f"{p['value']!r} — non-numeric content is not a parameter "
                    f"value (describe it in the qoi definition or regime notes "
                    f"instead)."
                )
            else:
                fixed_values[name] = p["value"]
        elif role == "derived":
            # Step-15 docket, candidate 2: a derived parameter must state its
            # rule. Undeclared derivations are NOT detected here — the case
            # builder's consistency halt owns that side.
            derived_from = p.get("derived_from")
            if not isinstance(derived_from, str) or not derived_from.strip():
                errors.append(
                    f"derived parameter '{name}' must carry a non-empty "
                    f"'derived_from' string stating the rule it is computed by "
                    f"(e.g. \"Re = lid_velocity * cavity_length / "
                    f"kinematic_viscosity\")."
                )
            else:
                derived_names.add(name)
        else:
            errors.append(
                f"parameter '{name}' has role {role!r}; role must be \"sweep\", "
                f"\"fixed\", or \"derived\"."
            )

    return sweep_ranges, fixed_values, derived_names


def _validate_mask(mask: Any, vocab, errors: list[str], label: str) -> None:
    """Optional spatial mask on a qoi (Multi-QoI build, part B). Present-only
    light check, control_block precedent. Shape: {type, params} — type one of
    the vocabulary's mask types (the wrapper's MASK_TYPES via the injected
    record), params an object carrying that mask's numeric bounds (e.g.
    {radius_frac} for corner_exclusion). The exact bound keys are not
    deep-checked here; the wrapper is the authority on those.
    """
    if not isinstance(mask, dict):
        errors.append(
            f"{label} mask, when present, must be an object with 'type' and 'params'."
        )
        return
    if mask.get("type") not in vocab.mask_types:
        errors.append(
            f"{label} mask type must be one of {sorted(vocab.mask_types)}; "
            f"got {mask.get('type')!r}."
        )
    if not isinstance(mask.get("params"), dict):
        errors.append(
            f"{label} mask must carry a 'params' object of the mask's numeric bounds."
        )


def _validate_qoi(qoi: Any, vocab, errors: list[str], label: str = "qoi") -> None:
    if isinstance(qoi, list):
        errors.append(
            f"{label} must be a single object, never a list — pick the one quantity "
            "of interest this experiment is about."
        )
        return
    if not isinstance(qoi, dict):
        errors.append(f"{label} must be an object with name, units, definition, and how_extracted.")
        return
    for field in QOI_REQUIRED_FIELDS:
        if field not in qoi:
            errors.append(f"{label} is missing '{field}'.")

    # D.3 two-shape dispatch: the OTHER shape's machine keys are rejected
    # loudly — a request in the wrong grammar must never pass silently as
    # "not extractable". Unreachable by any real pre-D.3 spec (no cavity
    # spec ever carried named-quantity keys); required by the two-shape
    # proof so each record rejects the other grammar.
    alien = [k for k in vocab.alien_keys if k in qoi]
    if alien:
        errors.append(
            f"{label} carries the key(s) {', '.join(repr(k) for k in alien)}, "
            f"which belong to a different substrate class's QoI grammar — this "
            f"substrate's machine-readable keys follow its own vocabulary; "
            f"remove them."
        )

    if vocab.shape == FIELD_REDUCTION:
        _validate_qoi_field_reduction(qoi, vocab, errors, label)
    elif vocab.shape == NAMED_QUANTITY:
        _validate_qoi_named_quantity(qoi, vocab, errors, label)
    elif vocab.shape == SYMBOLIC_RESULT:
        _validate_qoi_symbolic_result(qoi, vocab, errors, label)
    elif vocab.shape == FIXED_SUMMARY:
        _validate_qoi_fixed_summary(qoi, vocab, errors, label)
    else:  # a vocab record with an unknown shape is a broken invariant
        raise ValueError(f"unknown QoI vocabulary shape {vocab.shape!r}")


def _validate_qoi_field_reduction(qoi: dict, vocab, errors: list[str], label: str) -> None:
    """The field-reduction (cavity-class) machine-key checks — the pre-D.3
    body verbatim, vocabulary members read from the injected record. Error
    strings are model-visible behavior (the d3 retry-surface captures) and
    stay byte-identical."""
    # Optional machine-readable extraction keys: absent (all three) is valid —
    # it declares the QoI not extractable by the substrate. Any that are
    # present must use exactly the wrapper's vocabulary, and a partial set is
    # not a request the wrapper can serve: field and operation travel together.
    machine_keys = [k for k in ("field", "operation", "component") if k in qoi]
    if machine_keys:
        for needed in ("field", "operation"):
            if needed not in qoi:
                errors.append(
                    f"{label} carries the machine-readable key(s) "
                    f"{', '.join(repr(k) for k in machine_keys)} but is missing "
                    f"'{needed}' — an extractable qoi must carry both 'field' and "
                    f"'operation' ('component' stays optional); either add "
                    f"'{needed}' or omit all machine-readable keys."
                )
    if "field" in qoi:
        name = qoi["field"]
        if not isinstance(name, str) or not vocab.field_re.match(name):
            errors.append(
                f"{label} field must be the exact name of a field the case already "
                f"writes — a plain identifier (letters, digits, underscore, dot, "
                f"starting with a letter); got {name!r}."
            )
    if "operation" in qoi and qoi["operation"] not in vocab.operations:
        errors.append(
            f"{label} operation must be one of {sorted(vocab.operations)}; "
            f"got {qoi['operation']!r}."
        )
    if "component" in qoi and qoi["component"] not in vocab.components:
        # AWKWARD SEAM, preserved deliberately: this string hardcodes the
        # component list ("mag" or 0|1|2) in prose instead of rendering it
        # from vocab.components — a future component-vocabulary change would
        # desync the prose. Kept verbatim because the string is model-visible
        # behavior (d3 captures); rewording is its own recorded change.
        errors.append(
            f"{label} component must be \"mag\" or 0|1|2 (or omitted entirely); "
            f"got {qoi['component']!r}."
        )
    # Optional spatial mask (Multi-QoI build, part B): present-only.
    if "mask" in qoi:
        _validate_mask(qoi["mask"], vocab, errors, label)


def _validate_qoi_named_quantity(qoi: dict, vocab, errors: list[str], label: str) -> None:
    """The named-quantity (ngspice/FEA-class) machine-key checks: enumerated
    kinds x target-name grammar x enumerated reductions, mirroring the
    field-reduction rules' style — optional as a set, but kind, target, and
    reduction travel together."""
    machine_keys = [k for k in ("kind", "target", "reduction") if k in qoi]
    if machine_keys:
        for needed in ("kind", "target", "reduction"):
            if needed not in qoi:
                errors.append(
                    f"{label} carries the machine-readable key(s) "
                    f"{', '.join(repr(k) for k in machine_keys)} but is missing "
                    f"'{needed}' — an extractable qoi must carry 'kind', 'target', "
                    f"and 'reduction' together; either add '{needed}' or omit all "
                    f"machine-readable keys."
                )
    if "kind" in qoi and qoi["kind"] not in vocab.kinds:
        errors.append(
            f"{label} kind must be one of {sorted(vocab.kinds)}; "
            f"got {qoi['kind']!r}."
        )
    if "target" in qoi:
        name = qoi["target"]
        if not isinstance(name, str) or not vocab.target_re.match(name):
            errors.append(
                f"{label} target must be the exact name of a node or source the "
                f"netlist declares; got {name!r}."
            )
    if "reduction" in qoi and qoi["reduction"] not in vocab.reductions:
        errors.append(
            f"{label} reduction must be one of {sorted(vocab.reductions)}; "
            f"got {qoi['reduction']!r}."
        )


def _validate_qoi_symbolic_result(qoi: dict, vocab, errors: list[str], label: str) -> None:
    """The symbolic-result (exact-CAS class) checks: this shape has NO
    machine-readable extraction vocabulary — the wrapper takes no QoI
    request, and the QoI is the operation's own verified result. The prose
    fields are checked by the common code above; machine keys from either
    other grammar are rejected there too, by name, via the record's
    alien_keys. Nothing further to validate is itself the shape's fact,
    stated here rather than left implicit."""


def _validate_qoi_fixed_summary(qoi: dict, vocab, errors: list[str], label: str) -> None:
    """The fixed-summary (cantilever-class) machine-key check: the wrapper
    takes no QoI request and returns a fixed set of named numbers every
    valid run, so the ONE machine key is "quantity" — which of those
    numbers is THE quantity of interest, membership-checked against the
    wrapper's own imported name set. Absent is valid: it declares the QoI
    not extractable (the honest qoi_error fallback path), mirroring the
    cavity grammar's absent-machine-keys semantics. Foreign grammars'
    machine keys are rejected by name by the common alien-key check above.

    THE EXCEPTION (2026-07-20): when the record sets quantity_required, the
    wrapper threads `quantity` as a typed input and cannot run without one,
    so an absent key is an unexecutable spec, NOT an honest not-extractable
    declaration. Caught here, the existing re-ask loop repairs it in-run in
    seconds; left to execution it surfaced as an uncaught adapter ValueError
    after the fidelity gate had already spent a trust verdict on it."""
    if getattr(vocab, "quantity_required", False) and "quantity" not in qoi:
        errors.append(
            f"{label} is missing the machine-readable 'quantity' key, which "
            f"this instrument requires: it takes the quantity as a typed "
            f"input and cannot run without one. Set {label}.quantity to one "
            f"of {sorted(vocab.names)}. Note this is a SEPARATE key from "
            f"{label}.name — the prose name does not select the quantity."
        )
    if "quantity" in qoi and qoi["quantity"] not in vocab.names:
        errors.append(
            f"{label} quantity must be one of {sorted(vocab.names)} — the "
            f"named numbers this instrument returns on every valid run; "
            f"got {qoi['quantity']!r}."
        )


def _validate_qois(qois: Any, vocab, errors: list[str]) -> None:
    """Optional VECTOR of qoi objects (Multi-QoI build, part B). Present-only;
    each entry is validated exactly like the single `qoi` (same required
    fields, same machine-key rules, plus the optional `mask`). Rides alongside
    the single `qoi`, never replacing it — absent is valid.
    """
    if not isinstance(qois, list):
        errors.append("qois, when present, must be a list of qoi objects.")
        return
    if not qois:
        errors.append(
            "qois, when present, must be a non-empty list of qoi objects — "
            "omit it entirely instead of sending an empty list."
        )
        return
    for idx, entry in enumerate(qois):
        _validate_qoi(entry, vocab, errors, label=f"qois[{idx}]")


def _validate_success_criterion(sc: Any, errors: list[str]) -> None:
    if not isinstance(sc, dict):
        errors.append(
            "success_criterion must be an object with statement, threshold, and direction."
        )
        return
    if "statement" not in sc:
        errors.append("success_criterion is missing 'statement'.")
    if not _is_number(sc.get("threshold")):
        errors.append(
            f"success_criterion threshold must be a number; got {sc.get('threshold')!r}."
        )
    if sc.get("direction") not in ("above", "below"):
        errors.append(
            f"success_criterion direction must be \"above\" or \"below\"; "
            f"got {sc.get('direction')!r}."
        )
    # Step-15 docket, candidate 5: OPTIONAL two-sided expectation. When the
    # design genuinely predicts a numeric QoI value, expected_value and
    # tolerance travel together; threshold and direction stay required
    # regardless. No stage-4/5 consumer is wired yet, deliberately — the
    # field accumulates data for Step 16/21 design.
    has_expected = "expected_value" in sc
    has_tolerance = "tolerance" in sc
    if has_expected != has_tolerance:
        present, missing = (
            ("expected_value", "tolerance") if has_expected else ("tolerance", "expected_value")
        )
        errors.append(
            f"success_criterion carries '{present}' but not '{missing}' — the "
            f"two-sided expectation must carry both 'expected_value' and "
            f"'tolerance', or neither."
        )
    if has_expected and not _is_number(sc["expected_value"]):
        errors.append(
            f"success_criterion expected_value must be a number; "
            f"got {sc['expected_value']!r}."
        )
    if has_tolerance and (not _is_number(sc["tolerance"]) or sc["tolerance"] <= 0):
        errors.append(
            f"success_criterion tolerance must be a number greater than zero; "
            f"got {sc['tolerance']!r}."
        )


def _validate_regime(regime: Any, vocab, errors: list[str]) -> None:
    """R-23.5-5: 'regime' remains REQUIRED in every spec; its MEANING is
    per-substrate. Dispatch on the vocabulary record's regime-semantics
    shape — the same lookup family as the QoI checks, never a substrate
    name (R-28H-1). An unknown shape is a broken invariant, not a model
    error, and raises exactly as the QoI dispatch does."""
    if vocab.regime.shape == REYNOLDS_BAND:
        _validate_regime_reynolds_band(regime, errors)
    elif vocab.regime.shape == ANALYSIS_TYPE:
        _validate_regime_analysis_type(regime, vocab.regime, errors)
    elif vocab.regime.shape == OPERATION_SET:
        _validate_regime_operation_set(regime, vocab.regime, errors)
    elif vocab.regime.shape in (
        STATIC_SMALL_DEFLECTION,
        # BIO Wave D.4 (owner, 2026-07-19): three single-regime shapes that
        # share the cantilevers' {"notes": "..."} grammar exactly — no
        # per-case regime axis; the other shapes' keys rejected by name via
        # the record's own alien_keys. One validator, four shapes.
        DESCRIPTOR_COMPUTATION,
        FBA_STEADY_STATE,
        MSA_ALIGNMENT,
        HOMOLOGY_SEARCH,
    ):
        _validate_regime_static_small_deflection(regime, vocab.regime, errors)
    else:
        raise ValueError(f"unknown regime vocabulary shape {vocab.regime.shape!r}")


def _validate_regime_reynolds_band(regime: Any, errors: list[str]) -> None:
    """Cavity-class regime semantics: the pre-R-23.5-5 _validate_regime body
    byte-equal — same checks, same rejection strings (pinned exact by
    tests/test_r2355_captures.py)."""
    if not isinstance(regime, dict):
        errors.append("regime must be an object with reynolds_min, reynolds_max, and notes.")
        return
    if "notes" not in regime:
        errors.append("regime is missing 'notes'.")
    re_min, re_max = regime.get("reynolds_min"), regime.get("reynolds_max")
    if not _is_number(re_min) or not _is_number(re_max):
        errors.append(
            f"regime reynolds_min and reynolds_max must be numbers; "
            f"got reynolds_min={re_min!r}, reynolds_max={re_max!r}."
        )
    elif not (0 < re_min <= re_max):
        errors.append(
            f"regime must satisfy 0 < reynolds_min <= reynolds_max; "
            f"got reynolds_min={re_min} and reynolds_max={re_max}."
        )


def _validate_regime_analysis_type(regime: Any, reg, errors: list[str]) -> None:
    """Named-analysis regime semantics (ngspice class, R-23.5-5): the regime
    is DECLARED AS ONE OF THE WRAPPER'S OWN ANALYSIS TYPES —
    reg.analysis_types is derived from tools/run_ngspice.py's
    _ANALYSIS_FIELDS, never invented here. The cavity shape's keys are
    rejected BY NAME (reg.alien_keys) so a Reynolds-shaped regime block
    fails with a per-substrate reason, not a bare missing-key complaint."""
    allowed = ", ".join(reg.analysis_types)
    if not isinstance(regime, dict):
        errors.append("regime must be an object with analysis_type and notes.")
        return
    for key in reg.alien_keys:
        if key in regime:
            errors.append(
                f"regime field '{key}' is not part of this substrate's regime "
                f"vocabulary — this instrument's regime is not a Reynolds band; "
                f"declare 'analysis_type' (one of: {allowed}) and 'notes'."
            )
    if "notes" not in regime:
        errors.append("regime is missing 'notes'.")
    if "analysis_type" not in regime:
        errors.append(
            f"regime is missing 'analysis_type' — this substrate's regime is "
            f"declared as one of its analysis types: {allowed}."
        )
    elif regime["analysis_type"] not in reg.analysis_types:
        errors.append(
            f"regime analysis_type must be one of: {allowed}; "
            f"got {regime['analysis_type']!r}."
        )


def _validate_regime_operation_set(regime: Any, reg, errors: list[str]) -> None:
    """Operation-set regime semantics (exact-CAS class, Packet B Phase 1.0
    ruling item 1): the regime is DECLARED AS ONE OF THE WRAPPER'S OWN
    ALLOWLISTED OPERATIONS — reg.operations is derived from the owning
    wrapper's imported allowlist, never invented here. The other shapes'
    keys are rejected BY NAME (reg.alien_keys) so a Reynolds-shaped or
    analysis-shaped regime block fails with a per-substrate reason, not a
    bare missing-key complaint."""
    allowed = ", ".join(reg.operations)
    if not isinstance(regime, dict):
        errors.append("regime must be an object with operation and notes.")
        return
    for key in reg.alien_keys:
        if key in regime:
            errors.append(
                f"regime field '{key}' is not part of this substrate's regime "
                f"vocabulary — this instrument's regime is not a Reynolds band "
                f"and not a circuit analysis; declare 'operation' (one of: "
                f"{allowed}) and 'notes'."
            )
    if "notes" not in regime:
        errors.append("regime is missing 'notes'.")
    if "operation" not in regime:
        errors.append(
            f"regime is missing 'operation' — this substrate's regime is "
            f"declared as one of its allowlisted operations: {allowed}."
        )
    elif regime["operation"] not in reg.operations:
        errors.append(
            f"regime operation must be one of: {allowed}; "
            f"got {regime['operation']!r}."
        )


def _validate_regime_static_small_deflection(regime: Any, reg, errors: list[str]) -> None:
    """Static-small-deflection regime semantics (cantilever class, Packet B
    Phase 2.0 option R1, ruled by the build chat under the owner's standing
    delegation, 2026-07-17): these instruments serve exactly ONE physics
    regime by construction, so there is no per-case regime axis to declare —
    the spec's regime object is {"notes": "..."}, a statement of why the
    case sits inside the card's ruled bounds (which are gate judgments the
    contract §3 states, never typed inputs). ALL three other shapes' keys
    are rejected BY NAME (reg.alien_keys) so a wrong-grammar regime block
    fails with a per-substrate reason, not a bare missing-key complaint."""
    if not isinstance(regime, dict):
        errors.append("regime must be an object with notes.")
        return
    for key in reg.alien_keys:
        if key in regime:
            errors.append(
                f"regime field '{key}' is not part of this substrate's regime "
                f"vocabulary — this instrument's regime is not a Reynolds "
                f"band, not a circuit analysis, and not a symbolic operation; "
                f"it serves exactly one physics regime by construction — "
                f"declare 'notes' stating why the case sits inside the "
                f"contract's stated bounds."
            )
    if "notes" not in regime:
        errors.append("regime is missing 'notes'.")


def _validate_mini_experiment(
    mini: Any,
    sweep_ranges: dict,
    fixed_values: dict,
    derived_names: set,
    errors: list[str],
) -> None:
    if not isinstance(mini, dict):
        errors.append("mini_experiment must be an object with runs and expected_observation.")
        return
    if "expected_observation" not in mini:
        errors.append("mini_experiment is missing 'expected_observation'.")

    runs = mini.get("runs")
    if not isinstance(runs, list) or not MIN_MINI_RUNS <= len(runs) <= MAX_MINI_RUNS:
        errors.append(
            f"mini_experiment runs must be a list of {MIN_MINI_RUNS} to {MAX_MINI_RUNS} "
            "dicts of parameter values."
        )
        return

    declared_names = sorted(set(sweep_ranges) | set(fixed_values) | derived_names)
    for idx, run in enumerate(runs, start=1):
        if not isinstance(run, dict):
            errors.append(f"mini_experiment run {idx} must be a dict of parameter values.")
            continue
        for name in run:
            if name not in declared_names:
                errors.append(
                    f"mini_experiment run {idx} sets '{name}', which is not a declared "
                    f"parameter name — the declared parameter names are: "
                    f"{', '.join(declared_names)}."
                )
        for name, (lo, hi) in sweep_ranges.items():
            if name not in run:
                errors.append(
                    f"mini_experiment run {idx} is missing a value for sweep parameter "
                    f"'{name}' — every run must assign every sweep parameter."
                )
            elif not _is_number(run[name]) or not lo <= run[name] <= hi:
                errors.append(
                    f"mini_experiment run {idx} sets sweep parameter '{name}' to "
                    f"{run[name]!r}, outside its declared range [{lo}, {hi}]."
                )
        for name, value in fixed_values.items():
            if name not in run:
                errors.append(
                    f"mini_experiment run {idx} is missing a value for fixed parameter "
                    f"'{name}' — every run must assign every fixed parameter."
                )
            elif run[name] != value:
                errors.append(
                    f"mini_experiment run {idx} sets fixed parameter '{name}' to "
                    f"{run[name]!r}, but its declared value is {value!r} — fixed "
                    "parameters must keep their declared value in every run."
                )


def _validate_full_experiment(full: Any, errors: list[str]) -> None:
    if not isinstance(full, dict):
        errors.append("full_experiment must be an object with design and estimated_run_count.")
        return
    if "design" not in full:
        errors.append("full_experiment is missing 'design'.")
    count = full.get("estimated_run_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        errors.append(
            f"full_experiment estimated_run_count must be a positive integer; got {count!r}."
        )


def _validate_control_block(cb: Any, errors: list[str]) -> None:
    """Optional null-twin control block (Phase-1 Lane-2). Only checked when
    present; absent is valid. Shape: {description (str), params (dict),
    expected_null_outcome (str)} — the control experiment under which the
    hypothesized effect should disappear.
    """
    if not isinstance(cb, dict):
        errors.append(
            "control_block, when present, must be an object with description, "
            "params, and expected_null_outcome."
        )
        return
    if not isinstance(cb.get("description"), str) or not cb.get("description"):
        errors.append("control_block is missing a non-empty string 'description'.")
    if not isinstance(cb.get("params"), dict):
        errors.append("control_block 'params' must be an object of parameter values.")
    if not isinstance(cb.get("expected_null_outcome"), str) or not cb.get("expected_null_outcome"):
        errors.append(
            "control_block is missing a non-empty string 'expected_null_outcome' "
            "(what the QoI should show when the hypothesized effect is absent)."
        )


def validate_spec(spec: Any, chosen_id: str, vocab: Any) -> list[str]:
    """Deep-check one stage-2 spec against the schema rules. Returns a list of
    plain-language error strings — empty means valid. Each string is phrased
    so it can be sent straight back to the model as a guided correction.

    `vocab` is the substrate's QoI-vocabulary record (tools/qoi_vocab.py);
    the qoi machine-key checks and the regime check (R-23.5-5) dispatch on
    its shapes. REQUIRED at every call site (R-23.5-5a rider, owner
    2026-07-17): the old None-defaults-to-cavity resolution is REMOVED —
    validation must never guess a substrate, so an absent or None vocab
    raises instead of silently resolving to cavity. Callers obtain the
    record via tools.qoi_vocab.vocab_for(substrate_id), whose own loud
    raises cover unknown/unwired substrates.
    """
    if vocab is None:
        raise TypeError(
            "validate_spec requires the substrate's QoI-vocabulary record "
            "(R-23.5-5a): pass tools.qoi_vocab.vocab_for(<substrate_id>) — "
            "there is no default and no cavity fallback."
        )
    if not isinstance(spec, dict):
        return ["the spec must be a single JSON object."]

    errors: list[str] = []

    for field in REQUIRED_SPEC_FIELDS:
        if field not in spec:
            errors.append(f"required field '{field}' is missing — add it.")
    for field in spec:
        if field not in REQUIRED_SPEC_FIELDS and field not in OPTIONAL_SPEC_FIELDS:
            errors.append(f"field '{field}' is not part of the spec schema — remove it.")

    if "hypothesis_id" in spec and spec["hypothesis_id"] != chosen_id:
        errors.append(
            f"hypothesis_id must be exactly '{chosen_id}' (the hypothesis chosen at "
            f"the gate); got {spec['hypothesis_id']!r}."
        )

    sweep_ranges: dict = {}
    fixed_values: dict = {}
    derived_names: set = set()
    if "parameters" in spec:
        sweep_ranges, fixed_values, derived_names = _validate_parameters(
            spec["parameters"], errors
        )
    if "qoi" in spec:
        _validate_qoi(spec["qoi"], vocab, errors)
    if "qois" in spec:
        _validate_qois(spec["qois"], vocab, errors)
    if "success_criterion" in spec:
        _validate_success_criterion(spec["success_criterion"], errors)
    if "regime" in spec:
        _validate_regime(spec["regime"], vocab, errors)
    if "mini_experiment" in spec:
        _validate_mini_experiment(
            spec["mini_experiment"], sweep_ranges, fixed_values, derived_names, errors
        )
    if "full_experiment" in spec:
        _validate_full_experiment(spec["full_experiment"], errors)
    if "control_block" in spec:
        _validate_control_block(spec["control_block"], errors)

    return errors
