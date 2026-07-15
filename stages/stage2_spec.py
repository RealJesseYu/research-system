"""
stage2_spec.py — the typed experiment-spec schema and its validator.

Pure functions, zero model calls. stage2_experiment_design.py imports
validate_spec and runs it as call_stage_model's extra_validator: the model
is asked for a spec, checked with validate_spec, and the error strings are
sent back as guided corrections until the spec is clean.

validate_spec(spec, chosen_id) is the deep check: every rule returns a
plain-language error string phrased so it can be sent straight back to the
model as a correction. An empty list means the spec is valid. It never
raises on bad input — malformed structure becomes error strings too.
"""

from __future__ import annotations

from typing import Any

# The wrapper's own QoI vocabularies are the single source of truth — imported,
# never redefined here. (_QOI_FIELD_RE is the wrapper's field-identifier rule;
# MASK_TYPES is the wrapper's spatial-mask vocabulary for multi-QoI extraction.)
from tools.run_cfd import QOI_COMPONENTS, QOI_OPERATIONS, MASK_TYPES, _QOI_FIELD_RE

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


def _validate_mask(mask: Any, errors: list[str], label: str) -> None:
    """Optional spatial mask on a qoi (Multi-QoI build, part B). Present-only
    light check, control_block precedent. Shape: {type, params} — type one of
    the wrapper's MASK_TYPES, params an object carrying that mask's numeric
    bounds (e.g. {radius_frac} for corner_exclusion). The exact bound keys are
    not deep-checked here; the wrapper is the authority on those.
    """
    if not isinstance(mask, dict):
        errors.append(
            f"{label} mask, when present, must be an object with 'type' and 'params'."
        )
        return
    if mask.get("type") not in MASK_TYPES:
        errors.append(
            f"{label} mask type must be one of {sorted(MASK_TYPES)}; "
            f"got {mask.get('type')!r}."
        )
    if not isinstance(mask.get("params"), dict):
        errors.append(
            f"{label} mask must carry a 'params' object of the mask's numeric bounds."
        )


def _validate_qoi(qoi: Any, errors: list[str], label: str = "qoi") -> None:
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
        if not isinstance(name, str) or not _QOI_FIELD_RE.match(name):
            errors.append(
                f"{label} field must be the exact name of a field the case already "
                f"writes — a plain identifier (letters, digits, underscore, dot, "
                f"starting with a letter); got {name!r}."
            )
    if "operation" in qoi and qoi["operation"] not in QOI_OPERATIONS:
        errors.append(
            f"{label} operation must be one of {sorted(QOI_OPERATIONS)}; "
            f"got {qoi['operation']!r}."
        )
    if "component" in qoi and qoi["component"] not in QOI_COMPONENTS:
        errors.append(
            f"{label} component must be \"mag\" or 0|1|2 (or omitted entirely); "
            f"got {qoi['component']!r}."
        )
    # Optional spatial mask (Multi-QoI build, part B): present-only.
    if "mask" in qoi:
        _validate_mask(qoi["mask"], errors, label)


def _validate_qois(qois: Any, errors: list[str]) -> None:
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
        _validate_qoi(entry, errors, label=f"qois[{idx}]")


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


def _validate_regime(regime: Any, errors: list[str]) -> None:
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


def validate_spec(spec: Any, chosen_id: str) -> list[str]:
    """Deep-check one stage-2 spec against the schema rules. Returns a list of
    plain-language error strings — empty means valid. Each string is phrased
    so it can be sent straight back to the model as a guided correction.
    """
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
        _validate_qoi(spec["qoi"], errors)
    if "qois" in spec:
        _validate_qois(spec["qois"], errors)
    if "success_criterion" in spec:
        _validate_success_criterion(spec["success_criterion"], errors)
    if "regime" in spec:
        _validate_regime(spec["regime"], errors)
    if "mini_experiment" in spec:
        _validate_mini_experiment(
            spec["mini_experiment"], sweep_ranges, fixed_values, derived_names, errors
        )
    if "full_experiment" in spec:
        _validate_full_experiment(spec["full_experiment"], errors)
    if "control_block" in spec:
        _validate_control_block(spec["control_block"], errors)

    return errors
