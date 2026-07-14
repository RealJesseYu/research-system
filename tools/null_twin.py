"""
null_twin.py — deterministic comparison of a main experiment against its
null/control twin.

Pure functions, ZERO model calls. A null twin (declared in a spec's optional
`control_block`, stage2_spec.py) is the same experiment with the hypothesized
CAUSE removed — the QoI should show no effect. If it shows the effect anyway,
the effect is an artifact of the setup rather than of the manipulated variable,
and `compare` catches that self-inflicted false positive.

`compare(main_results, null_results, criterion) -> {effect_in_null: bool,
notes: [str]}`. It reads the numeric QoI out of stage-4-style execution results
(`{status, runs: [{converged, qoi_value|qoi_error, ...}]}`; a bare list of run
dicts or of numbers is also accepted) and applies `criterion` to the NULL twin:

  criterion = {
    "kind": "threshold" | "relative",
    "field": "qoi_value",          # numeric key to read from each run (default)
    "reduce": "last"|"first"|"max"|"min"|"mean"|"absmax",  # default "last"
    # kind == "threshold":
    "threshold": <number>, "direction": "above" | "below",
    # kind == "relative":
    "min_effect_fraction": <number in (0,1]>,   # null counts as "effect
    #   present" when |null| >= fraction * |main|
  }

Honest by construction: if the null QoI can't be extracted (qoi_error, missing,
non-numeric), the effect cannot be confirmed present, so effect_in_null is False
with a note saying WHY — absence of evidence, reported as such, never a silent
pass.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_FIELD = "qoi_value"
_DEFAULT_REDUCE = "last"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _runs_of(results: Any) -> list:
    """Coerce accepted result shapes to a list of per-run entries."""
    if isinstance(results, dict):
        runs = results.get("runs")
        return runs if isinstance(runs, list) else []
    if isinstance(results, list):
        return results
    return []


def _extract_values(results: Any, field: str) -> list[float]:
    """Numeric `field` values across runs, in order. A run may itself be a
    number (bare-number shape); otherwise `field` is read from the run dict.
    Non-numeric / missing / error entries are skipped (they are handled as
    'not extractable' by the caller when the whole list comes back empty).
    """
    values: list[float] = []
    for run in _runs_of(results):
        if _is_number(run):
            values.append(float(run))
        elif isinstance(run, dict) and _is_number(run.get(field)):
            values.append(float(run[field]))
    return values


def _reduce(values: list[float], how: str) -> float | None:
    if not values:
        return None
    if how == "last":
        return values[-1]
    if how == "first":
        return values[0]
    if how == "max":
        return max(values)
    if how == "min":
        return min(values)
    if how == "mean":
        return sum(values) / len(values)
    if how == "absmax":
        return max(values, key=abs)
    return None


def compare(main_results: Any, null_results: Any, criterion: Any) -> dict:
    """Assess whether the hypothesized effect appears in the NULL twin.

    Returns {"effect_in_null": bool, "notes": [str]}. Deterministic and numeric;
    never raises on malformed input — every failure mode becomes a note and a
    conservative effect_in_null=False.
    """
    notes: list[str] = []
    if not isinstance(criterion, dict):
        return {"effect_in_null": False, "notes": ["criterion is not an object; nothing to compare"]}

    field = criterion.get("field", _DEFAULT_FIELD)
    how = criterion.get("reduce", _DEFAULT_REDUCE)
    kind = criterion.get("kind", "threshold")

    main_vals = _extract_values(main_results, field)
    null_vals = _extract_values(null_results, field)
    main_r = _reduce(main_vals, how)
    null_r = _reduce(null_vals, how)

    notes.append(f"main {how}({field})={main_r!r} from {len(main_vals)} run(s)")
    notes.append(f"null {how}({field})={null_r!r} from {len(null_vals)} run(s)")

    if null_r is None:
        notes.append(
            "null QoI not extractable (missing / qoi_error / non-numeric) — "
            "cannot confirm the effect in the null twin; reporting effect_in_null=False"
        )
        return {"effect_in_null": False, "notes": notes}

    if kind == "threshold":
        threshold = criterion.get("threshold")
        direction = criterion.get("direction")
        if not _is_number(threshold) or direction not in ("above", "below"):
            notes.append(
                "threshold criterion needs numeric 'threshold' and direction "
                "'above'|'below'; cannot evaluate"
            )
            return {"effect_in_null": False, "notes": notes}
        effect_in_null = null_r > threshold if direction == "above" else null_r < threshold
        main_effect = (
            None if main_r is None
            else (main_r > threshold if direction == "above" else main_r < threshold)
        )
        notes.append(
            f"threshold {direction} {threshold}: null effect={effect_in_null}, "
            f"main effect={main_effect}"
        )
        if effect_in_null:
            notes.append(
                "ARTIFACT: the null twin crosses the success threshold too — the "
                "effect is not attributable to the manipulated variable"
            )
        return {"effect_in_null": bool(effect_in_null), "notes": notes}

    if kind == "relative":
        frac = criterion.get("min_effect_fraction")
        if not _is_number(frac) or not (0 < frac <= 1):
            notes.append("relative criterion needs 'min_effect_fraction' in (0, 1]; cannot evaluate")
            return {"effect_in_null": False, "notes": notes}
        if main_r is None:
            notes.append("relative criterion needs a main QoI as reference; main not extractable")
            return {"effect_in_null": False, "notes": notes}
        threshold_mag = abs(main_r) * frac
        effect_in_null = abs(null_r) >= threshold_mag
        notes.append(
            f"relative: |null|={abs(null_r):.6g} vs {frac:g}*|main|={threshold_mag:.6g} "
            f"-> effect_in_null={effect_in_null}"
        )
        if effect_in_null:
            notes.append(
                "ARTIFACT: the null twin retains a comparable-magnitude signal — "
                "the effect is not attributable to the manipulated variable"
            )
        return {"effect_in_null": bool(effect_in_null), "notes": notes}

    notes.append(f"unknown criterion kind {kind!r}; expected 'threshold' or 'relative'")
    return {"effect_in_null": False, "notes": notes}
