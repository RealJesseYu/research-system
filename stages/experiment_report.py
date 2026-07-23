"""experiment_report.py — the honest write-up of a routed exact-tool run.

Phase 3, R-ROUTE-5 (docs/memo_phase3_routing.md). The static pipeline's paper
(stages/stage6_paper.py) is grounded in the thought layer, the fidelity verdict,
and execution_results — a routed exact-tool run has NONE of those (there was no
thought layer, and fidelity was a non-question). Reusing that stage would mean
fabricating its inputs, which is exactly the "pretend a stage ran" move the
project forbids.

So a routed run's write-up is generated DETERMINISTICALLY from the verified
investigation itself — no model anywhere in this path. That is not a limitation,
it is the point: a report assembled by code from run_composition's verified
numbers structurally CANNOT narrate a value it did not compute. It reports only
what reproduced; a probe that failed to verify is listed as NOT claimed.

A model-narrated paper over a routed result (intro/discussion prose) is a later
enhancement and would carry the same propose/verify discipline — it may only
describe numbers the verifier reproduced. This deterministic report is the honest
floor that ships first.
"""

from __future__ import annotations

import json
from pathlib import Path


def _fmt_recipe(recipe: dict) -> list[str]:
    """One readable line per recipe step plus the combine. Pure formatting of
    the recorded wiring — never the intermediate values (the recipe records
    wiring, not numbers; R-COMP-3)."""
    lines = []
    for step in recipe.get("steps", []):
        sid = step.get("step_id", "?")
        if step.get("kind") == "substrate":
            typed = step.get("typed_input") or {}
            args = ", ".join(f"{k}={v}" for k, v in typed.items())
            lines.append(f"  - `{sid}`: {step.get('substrate_id')}({args})"
                         f" -> {step.get('quantity')}")
        else:  # code
            lines.append(f"  - `{sid}`: code -> {step.get('quantity')}")
    combine = recipe.get("combine") or {}
    lines.append(f"  - combine -> `{combine.get('quantity')}` "
                 f"over {combine.get('inputs')}")
    return lines


def _measurement_block(m: dict) -> list[str]:
    """The report block for one probe. A number is stated ONLY when the probe
    verified — an unreproduced probe is named as not claimed, never given a
    value the record cannot stand behind."""
    lines = [f"### Probe {m.get('iteration')}"]
    if m.get("reasoning"):
        lines.append(f"_Rationale:_ {m['reasoning']}")
    lines.append("")
    lines.append("Recipe:")
    lines.extend(_fmt_recipe(m.get("recipe") or {}))
    lines.append("")
    if m.get("verified"):
        lines.append(f"**Verified result: {m.get('value')}** "
                     f"(reproduced, rel_error {m.get('rel_error')}).")
        if m.get("predicted") is not None:
            lines.append(f"Predicted {m['predicted']} "
                         f"(abs error {m.get('prediction_abs_error')}); the "
                         "prediction is compared, never recorded as the result.")
    else:
        why = m.get("produce_error") or m.get("reason") or "did not reproduce"
        lines.append(f"**NOT claimed** — {why}. This probe produced no "
                     "number of record.")
    lines.append("")
    return lines


def render_report(result: dict) -> str:
    """Deterministic markdown for a routed exact-tool run. `result` is
    run_exact_investigation's return value {fidelity, investigation,
    publishable}. No model in this function."""
    fidelity = result.get("fidelity") or {}
    inv = result.get("investigation") or {}
    measurements = inv.get("measurements") or []
    verified = [m for m in measurements if m.get("verified")]
    unverified = [m for m in measurements if not m.get("verified")]

    lines = ["# Investigation report (exact-tool route)", ""]
    lines.append("## Method")
    lines.append(
        "This run used the experimenter loop on exact instruments. The fidelity "
        "gate did not fire: " + (fidelity.get("reason") or
        "exact-tool investigation — re-running is the check.") )
    lines.append("")
    lines.append(
        "Every number below was produced by a composition recipe and "
        "independently reproduced by re-running that recipe with no model in the "
        "loop. Numbers that did not reproduce are listed but not claimed.")
    lines.append("")

    lines.append("## Result")
    if result.get("publishable"):
        lines.append(f"**Publishable.** {len(verified)} of {len(measurements)} "
                     "probe(s) reproduced; every probe that ran reproduced.")
    else:
        if not measurements:
            lines.append("**Does not stand.** No probe ran — there is nothing "
                         "to report.")
        else:
            lines.append(f"**Does not stand.** {len(verified)} of "
                         f"{len(measurements)} probe(s) reproduced; a run resting "
                         "on an unreproduced number does not stand.")
    if inv.get("stop_reason"):
        lines.append(f"\nStopped: {inv['stop_reason']}")
    lines.append("")

    if verified:
        lines.append("## Verified results")
        lines.append("")
        for m in verified:
            lines.extend(_measurement_block(m))
    if unverified:
        lines.append("## Probes that did not reproduce (not claimed)")
        lines.append("")
        for m in unverified:
            lines.extend(_measurement_block(m))

    return "\n".join(lines).rstrip() + "\n"


def build_verification(result: dict) -> dict:
    """Map a routed exact-tool investigation into the SAME shape the static
    pipeline's verification.json uses (read by pi_agent.dispatch._read_verification),
    so the PI director reads a routed run's verified findings exactly as it reads a
    static run's. Pure and deterministic — the verification already happened inside
    the experimenter loop (each probe re-run with no model); this only surfaces it
    in the standard file so the director's arc is evidence-driven, not blind.

    _read_verification takes value = reproduced when verified else original, so a
    verified probe carries its reproduced number and an unreproduced one is still
    surfaced (as `original`) rather than silently dropped."""
    inv = result.get("investigation") or {}
    measurements = inv.get("measurements") or []
    verdicts = []
    for m in measurements:
        combine = (m.get("recipe") or {}).get("combine") or {}
        label = combine.get("quantity") or f"probe {m.get('iteration')}"
        verified = bool(m.get("verified"))
        verdicts.append({
            "label": label,
            "verified": verified,
            "reproduced": m.get("value") if verified else None,
            "original": m.get("value"),
            "reason": (f"reproduced (rel_error {m.get('rel_error')})" if verified
                       else (m.get("produce_error") or m.get("reason")
                             or "did not reproduce")),
        })
    return {
        "verdicts": verdicts,
        "publishable": bool(result.get("publishable")),
        "verified": sum(1 for m in measurements if m.get("verified")),
        "total": len(measurements),
    }


def write_report(result: dict, run_id: str) -> Path | None:
    """Render the routed-run report and write it to
    runs/<run_id>/exact_route_report.md. Returns the path, or None when the run
    dir does not exist (nothing to write against). Deterministic; no model."""
    if not run_id:
        return None
    run_dir = Path("runs") / str(run_id)
    if not run_dir.is_dir():
        return None
    path = run_dir / "exact_route_report.md"
    path.write_text(render_report(result))
    # A machine-readable sibling too, so a later reader (or the PI) consumes the
    # verified facts without re-parsing prose.
    (run_dir / "exact_route_report.json").write_text(json.dumps(result, indent=2))
    # verification.json in the STATIC pipeline's shape, so the PI director reads a
    # routed run's verified findings through the same channel it already uses —
    # the fix for the "director is blind to results" gap (2026-07-22 live run).
    (run_dir / "verification.json").write_text(
        json.dumps(build_verification(result), indent=2))
    return path
