"""
pi_gate.py — a deterministic Buckingham-π sanity gate over a stage-2 spec.

Pure functions, ZERO model calls. This is substrate-side tooling (like
run_cfd.py), so naming physical quantities here is permitted; nothing above a
tool wrapper imports it, and it never enters a stage's context.

What it does: reads the concrete sweep points a spec declares in
`mini_experiment.runs` and re-derives a few dimensionless / stability facts the
design should already respect —

  (i)   Reynolds number per sweep point (U*L/nu), compared against any Re the
        spec declares for that point;
  (ii)  duplicate-Re detection within a sweep (~1% relative tolerance) — two
        points at the same Re are the same experiment;
  (iii) dimensional coherence of the parameters that feed Re, where unit
        metadata is present;
  (iv)  a Courant-number estimate (Co = U*dt/dx, dx = L/N) with a warning above
        ~0.5, where the mesh/time-step parameters are derivable.

Everything is computed ONLY from fields actually present. When a quantity can't
be identified unambiguously the point is reported "not checkable" for that axis
rather than guessed. The verdict is {pass | flag, reasons[]} plus a per-point
table — and v1 NEVER kills anything: `pi_report` and `pi_verdict` are advisory,
and `pi_enforce_verdict` (defined but wired NOWHERE) is the only thing that
would ever gate, deliberately left unconnected.

Field names are NOT hard-coded to one substrate: quantities are identified by
unit metadata first and by a small alias table second, so the gate reads the
canonical (lid_velocity/cavity_length/kinematic_viscosity) specs and the many
alias variants (nu, L, lid_speed, U_lid, dt, delta_t, mesh_N, ...) that appear
on disk.
"""

from __future__ import annotations

from typing import Any

# Relative tolerances.
RE_CONSISTENCY_TOL = 0.01   # computed-vs-declared Re agreement
DUPLICATE_RE_TOL = 0.01     # two points "the same experiment"
COURANT_WARN = 0.5          # Co above this earns a warning

# --- unit vocabulary -------------------------------------------------------
# Normalized unit string -> (length_exponent, time_exponent). Only the handful
# of forms that actually occur on disk are recognized; anything else -> None
# ("unit metadata absent/ambiguous"), which downgrades a check to not-checkable
# rather than producing a false flag.
_UNIT_DIMS: dict[str, tuple[int, int]] = {
    "m/s": (1, -1),
    "m s^-1": (1, -1),
    "m": (1, 0),
    "s": (0, 1),
    "m^2/s": (2, -1),
    "m2/s": (2, -1),
    "m^2 s^-1": (2, -1),
    "m^2s^-1": (2, -1),
}

# --- alias tables (lowercased names) ---------------------------------------
# A characteristic quantity is identified by unit dimension first; when several
# candidates share a dimension, these preference sets disambiguate. Absence of a
# clear winner is reported honestly, never guessed.
_VELOCITY_UNIT_DIM = (1, -1)
_LENGTH_UNIT_DIM = (1, 0)
_VISCOSITY_UNIT_DIM = (2, -1)
_TIME_UNIT_DIM = (0, 1)

_VELOCITY_NAME_PREF = (
    "lid_velocity", "lid_speed", "u_lid", "lid_mean_speed", "u_mean", "lid_speed",
)
_LENGTH_NAME_PREF = (
    "cavity_length", "cavity_side_length", "cavity_side", "cavity_width",
    "cavity_width_baseline", "cavity_depth", "cavity_depth_h", "cavity_height",
    "cavity_total_height", "l",
)
# Names that carry viscosity units but are NOT the momentum viscosity.
_VISCOSITY_NAME_EXCLUDE = ("diffusiv", "scalar", "thermal")
_VISCOSITY_NAME_PREF = (
    "kinematic_viscosity", "kinematic_viscosity_nu", "nu", "viscosity",
)
_DT_NAME_PREF = ("time_step", "delta_t", "dt")
_RE_NAMES = ("reynolds_number", "re", "reynolds")
_MESH_UNIT_HINTS = ("cells per side", "cells/side", "cells")


def _norm_units(u: Any) -> str:
    """Lowercase + collapse whitespace of a units string; '' for non-strings.

    Only the leading token before a parenthetical gloss is kept, so
    'dimensionless (kinematic viscosity / ...)' normalizes to 'dimensionless'.
    """
    if not isinstance(u, str):
        return ""
    head = u.split("(")[0]
    return " ".join(head.split()).lower()


def _unit_dim(u: Any) -> tuple[int, int] | None:
    """(length, time) exponents for a units string, or None if unrecognized."""
    return _UNIT_DIMS.get(_norm_units(u))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _build_param_meta(parameters: Any) -> dict[str, dict]:
    """name -> {units, role, dim} for well-formed parameter declarations."""
    meta: dict[str, dict] = {}
    if not isinstance(parameters, list):
        return meta
    for p in parameters:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name:
            continue
        meta[name] = {
            "units": p.get("units"),
            "role": p.get("role"),
            "dim": _unit_dim(p.get("units")),
        }
    return meta


def _pick_by_dim_and_pref(
    meta: dict[str, dict],
    want_dim: tuple[int, int],
    pref: tuple[str, ...],
    exclude_substrings: tuple[str, ...] = (),
) -> tuple[str | None, str]:
    """Choose the characteristic parameter of a quantity.

    Returns (name, note). Identification is NAME-alias first (an exact alias in
    `pref` wins regardless of its declared units — that is what lets the
    coherence check downstream catch a parameter declared with the WRONG units),
    then falls back to a unique parameter carrying `want_dim` units. Ambiguity or
    absence returns None with an honest note. Names containing any
    `exclude_substrings` are never chosen.
    """
    lower = {n.lower(): n for n in meta}
    for want in pref:
        if want in lower and not any(x in want for x in exclude_substrings):
            return lower[want], ""
    cands = [
        n for n, m in meta.items()
        if m["dim"] == want_dim
        and not any(x in n.lower() for x in exclude_substrings)
    ]
    if not cands:
        return None, "no name-alias match and no parameter carries the expected units"
    if len(cands) == 1:
        return cands[0], ""
    return None, f"ambiguous ({len(cands)} candidates: {', '.join(sorted(cands))})"


def _pick_re_name(meta: dict[str, dict]) -> str | None:
    """The parameter (if any) that declares Reynolds number for each point."""
    for n in meta:
        if n.lower() in _RE_NAMES:
            return n
    return None


def _pick_mesh_name(meta: dict[str, dict]) -> tuple[str | None, str]:
    """The single per-side mesh-count parameter, or None if none/ambiguous."""
    cands = []
    for n, m in meta.items():
        nl = n.lower()
        units_ok = _norm_units(m["units"]) in _MESH_UNIT_HINTS
        name_ok = "mesh" in nl and not any(
            axis in nl for axis in ("_x", "_y", "_z", "nx", "ny", "nz", "_height")
        )
        if units_ok and name_ok:
            cands.append(n)
    if len(cands) == 1:
        return cands[0], ""
    if not cands:
        return None, "no single per-side mesh-count parameter"
    return None, f"ambiguous mesh parameters ({', '.join(sorted(cands))})"


def _rel_close(a: float, b: float, tol: float) -> bool:
    denom = max(abs(a), abs(b))
    if denom == 0:
        return abs(a - b) <= tol
    return abs(a - b) / denom <= tol


def pi_report(spec: Any) -> dict:
    """Deterministic π report for one stage-2 spec.

    Returns {verdict: 'pass'|'flag', reasons: [str], points: [ {...} ],
    identified: {...}, checkable: {...}}. Never raises on malformed input —
    it degrades to a report that says what could not be checked.
    """
    reasons: list[str] = []
    if not isinstance(spec, dict):
        return {
            "verdict": "flag",
            "reasons": ["spec is not an object; nothing checkable"],
            "points": [],
            "identified": {},
            "checkable": {},
        }

    meta = _build_param_meta(spec.get("parameters"))
    vel_name, vel_note = _pick_by_dim_and_pref(meta, _VELOCITY_UNIT_DIM, _VELOCITY_NAME_PREF)
    len_name, len_note = _pick_by_dim_and_pref(meta, _LENGTH_UNIT_DIM, _LENGTH_NAME_PREF)
    visc_name, visc_note = _pick_by_dim_and_pref(
        meta, _VISCOSITY_UNIT_DIM, _VISCOSITY_NAME_PREF, _VISCOSITY_NAME_EXCLUDE
    )
    dt_name, dt_note = _pick_by_dim_and_pref(meta, _TIME_UNIT_DIM, _DT_NAME_PREF)
    re_name = _pick_re_name(meta)
    mesh_name, mesh_note = _pick_mesh_name(meta)

    identified = {
        "velocity": vel_name, "length": len_name, "viscosity": visc_name,
        "time_step": dt_name, "mesh_count": mesh_name, "declared_reynolds": re_name,
    }

    # (iii) dimensional coherence of the Re inputs, where all three unit-carry.
    coherence_checkable = all(
        n is not None and meta.get(n, {}).get("dim") is not None
        for n in (vel_name, len_name, visc_name)
    )
    if coherence_checkable:
        vL, vT = meta[vel_name]["dim"]
        lL, lT = meta[len_name]["dim"]
        nL, nT = meta[visc_name]["dim"]
        re_dim = (vL + lL - nL, vT + lT - nT)
        if re_dim != (0, 0):
            reasons.append(
                f"dimensional incoherence: U*L/nu has dimension {re_dim}, not "
                f"dimensionless — units {meta[vel_name]['units']!r} * "
                f"{meta[len_name]['units']!r} / {meta[visc_name]['units']!r}"
            )

    runs = None
    mini = spec.get("mini_experiment")
    if isinstance(mini, dict) and isinstance(mini.get("runs"), list):
        runs = mini["runs"]

    points: list[dict] = []
    re_used_by_point: list[tuple[int, float]] = []

    if runs is None:
        reasons.append("mini_experiment.runs is absent; no sweep points to check")
    else:
        for idx, run in enumerate(runs, start=1):
            pt: dict[str, Any] = {"index": idx, "notes": []}
            if not isinstance(run, dict):
                pt["notes"].append("run is not a dict; not checkable")
                points.append(pt)
                continue

            U = run.get(vel_name) if vel_name else None
            L = run.get(len_name) if len_name else None
            nu = run.get(visc_name) if visc_name else None
            declared_re = run.get(re_name) if re_name else None

            # (i) Reynolds number.
            computed_re = None
            if _is_number(U) and _is_number(L) and _is_number(nu) and nu != 0:
                computed_re = U * L / nu
            pt["computed_re"] = computed_re
            pt["declared_re"] = declared_re if _is_number(declared_re) else None

            if computed_re is None and pt["declared_re"] is None:
                pt["notes"].append("Re not checkable (U/L/nu not all identifiable)")

            if computed_re is not None and _is_number(declared_re):
                if not _rel_close(computed_re, declared_re, RE_CONSISTENCY_TOL):
                    reasons.append(
                        f"point {idx}: declared Re {declared_re} disagrees with "
                        f"computed U*L/nu = {computed_re:.6g} (>1%)"
                    )
                    pt["notes"].append("declared vs computed Re mismatch")

            re_used = computed_re if computed_re is not None else pt["declared_re"]
            pt["re_used"] = re_used
            if re_used is not None:
                re_used_by_point.append((idx, re_used))

            # (iv) Courant estimate.
            dt = run.get(dt_name) if dt_name else None
            N = run.get(mesh_name) if mesh_name else None
            courant = None
            if (
                _is_number(U) and _is_number(L) and _is_number(dt)
                and _is_number(N) and N != 0 and L != 0
            ):
                dx = L / N
                if dx != 0:
                    courant = abs(U) * abs(dt) / dx
            pt["courant"] = courant
            if courant is None:
                pt["notes"].append("Courant not checkable (U/L/dt/N not all identifiable)")
            elif courant > COURANT_WARN:
                reasons.append(
                    f"point {idx}: Courant estimate {courant:.3g} exceeds "
                    f"{COURANT_WARN} (U*dt/dx)"
                )
                pt["notes"].append("high Courant")

            points.append(pt)

    # (ii) duplicate-Re within the sweep.
    for i in range(len(re_used_by_point)):
        for j in range(i + 1, len(re_used_by_point)):
            ai, av = re_used_by_point[i]
            bj, bv = re_used_by_point[j]
            if _rel_close(av, bv, DUPLICATE_RE_TOL):
                reasons.append(
                    f"points {ai} and {bj} share Re ~{av:.6g} (within "
                    f"{DUPLICATE_RE_TOL:.0%}) — same experiment run twice"
                )

    checkable = {
        "reynolds": any(p.get("re_used") is not None for p in points),
        "duplicate_re": len(re_used_by_point) >= 2,
        "coherence": coherence_checkable,
        "courant": any(p.get("courant") is not None for p in points),
        "identification_notes": {
            k: v for k, v in {
                "velocity": vel_note, "length": len_note, "viscosity": visc_note,
                "time_step": dt_note, "mesh_count": mesh_note,
            }.items() if v
        },
    }

    return {
        "verdict": "flag" if reasons else "pass",
        "reasons": reasons,
        "points": points,
        "identified": identified,
        "checkable": checkable,
    }


def pi_verdict(spec: Any) -> dict:
    """Advisory verdict only: {verdict, reasons}. Never kills, never gates."""
    r = pi_report(spec)
    return {"verdict": r["verdict"], "reasons": r["reasons"]}


def format_report_lines(report: dict) -> list[str]:
    """Human-readable lines for the report: a verdict line, reasons, and a
    compact per-point table. Pure formatting, never raises.
    """
    lines: list[str] = []
    lines.append(f"π-GATE verdict: {report.get('verdict', '?').upper()}")
    ident = report.get("identified", {})
    lines.append(
        "π-GATE identified: U={velocity} L={length} nu={viscosity} "
        "dt={time_step} N={mesh_count} Re={declared_reynolds}".format(
            **{k: (ident.get(k) or "—") for k in
               ("velocity", "length", "viscosity", "time_step",
                "mesh_count", "declared_reynolds")}
        )
    )
    for reason in report.get("reasons", []):
        lines.append(f"π-GATE flag: {reason}")
    if not report.get("reasons"):
        lines.append("π-GATE flag: (none)")
    for pt in report.get("points", []):
        re_c = pt.get("computed_re")
        co = pt.get("courant")
        re_s = f"{re_c:.6g}" if isinstance(re_c, (int, float)) else "n/a"
        co_s = f"{co:.3g}" if isinstance(co, (int, float)) else "n/a"
        notes = "; ".join(pt.get("notes", []))
        lines.append(
            f"π-GATE point {pt.get('index')}: Re={re_s} Co={co_s}"
            + (f" [{notes}]" if notes else "")
        )
    return lines


def pi_enforce_verdict(spec: Any) -> tuple[bool, list[str]]:
    """ENFORCE-MODE stub — returns (allowed, reasons). This is the ONLY function
    that would ever gate a spec, and it is wired NOWHERE (v1 never kills). It
    exists so a future enforce mode has a single, obvious call site to adopt
    after evidence justifies it; until then nothing imports or calls it.
    """
    report = pi_report(spec)
    return report["verdict"] == "pass", report["reasons"]
