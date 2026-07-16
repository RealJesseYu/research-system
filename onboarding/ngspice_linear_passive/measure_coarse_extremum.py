"""measure_coarse_extremum.py — the G10 setting, MEASURED not guessed.

WHY THIS EXISTS
G10 is the calibration slate's N2/N4 consequence case: an RLC peak claimed at a
timestep setting coarse enough that the extremum is under-resolved, where the
gate should answer `refine` rather than `trust`. A case like that is only
honest if its stated setting and its stated gap were MEASURED. This script is
that measurement, kept next to its output so the number can be re-derived
rather than trusted.

It re-uses the check-(e) series RLC from selfcheck_evidence.json verbatim
(zeta = 0.2, analytic peak 1.5266236763247512) and sweeps the two candidate
refinement levers against it.

WHAT IT FOUND (see coarse_extremum_evidence.json for the numbers)

1. `tmax` is a CEILING on the solver's step, NOT a target. ngspice's adaptive
   local-truncation-error control already chooses ~2e-5 steps on this circuit,
   so every tmax ABOVE that is inert: tmax 4e-5 .. 2e-4 all return the identical
   peak (1.52415539) from an identical 144 data rows. A .tran run cannot be
   coarsened past its own adaptive floor — it can only be refined. This sharpens
   the contract's existing "tmax is the refinement lever, not tstep" line: tmax
   is a one-way lever.

2. `tstep` does NOT control the written grid at all. wrdata emits one row per
   INTERNAL timestep (30023 rows at tmax=1e-7 ~ tstop/tmax), so the row count
   tracks tmax and is unchanged by tstep across a 50x range (5e-5 .. 1e-6 all
   give 30023 rows and a bit-identical peak). An extremum read off wrdata is
   therefore sampled on the solver's grid, never on the print grid.

3. Consequence for the extremum: the only band where tmax both BINDS and is
   still too coarse is roughly 3e-5 .. 1e-5, and inside it the peak error is
   NON-MONOTONE and SIGN-FLIPPING (it lands alternately above and below the
   analytic peak as sample points shift around it) — the textbook signature of
   an extremum tracking the grid rather than the physics. The reachable error
   on this circuit is bounded at ~1.1%, which is why the pre-registered guess
   of "10% to 50% at tmax=1e-4" is falsified by one to two orders of magnitude.

4. G10's setting: tmax = 2e-5 is the ONE point on the swept ladder whose gap
   exceeds N2's 1% relative bar (1.0995e-02). It is a knife-edge — its
   neighbours at 3e-5 (9.94e-03) and 1.5e-5 (1.72e-03) both sit UNDER the bar —
   and that is disclosed rather than smoothed over. It is nonetheless
   well-founded: it is outside the validated ladder (tmax <= 1e-6) AND over the
   N2 bar, two independent reasons agreeing.

UNITS WARNING (a real trap, recorded here because it bit this measurement):
selfcheck_evidence.json check (e) reports `gap_to_analytic_peak` as an ABSOLUTE
difference (4.844e-03 at tmax=1e-5), while N2's tolerance is RELATIVE (1%).
This script reports BOTH and never mixes them.

Run: python onboarding/ngspice_linear_passive/measure_coarse_extremum.py
Requires the ngspice-prod container to be up. ~20 real solver runs, ~10 s.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.run_ngspice import run_ngspice  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / "coarse_extremum_evidence.json"

# The check-(e) series RLC, verbatim from selfcheck_evidence.json.
VIN, R, L, C = 1.0, 12.649, 1e-3, 1e-6
ANALYTIC_PEAK = 1.5266236763247512
TSTOP = 3e-3
VALIDATED_TMAX = 1e-7  # the finest point check (e) validated

NETLIST = (
    f"V1 in 0 PWL(0 0 1n {VIN} 1 {VIN})\n"
    f"R1 in mid {R}\n"
    f"L1 mid out {L}\n"
    f"C1 out 0 {C}\n"
)

N2_RELATIVE_TOLERANCE = 0.01

TMAX_LADDER = [2e-4, 1.5e-4, 1e-4, 8e-5, 6e-5, 5e-5, 4e-5, 3e-5,
               2.5e-5, 2e-5, 1.5e-5, 1.2e-5, 1e-5, 5e-6, 1e-6]
TSTEP_LADDER = [5e-5, 4e-5, 3e-5, 2e-5, 1e-5, 5e-6, 1e-6]


def _peak(tstep: float, tmax: float) -> dict:
    res = run_ngspice({
        "netlist_body": NETLIST,
        "analysis": {"type": "tran", "tstep": tstep, "tstop": TSTOP, "tmax": tmax},
        "qoi": {"kind": "node_voltage", "target": "out", "reduction": "max"},
    })
    if not res["valid"]:
        return {"tstep_s": tstep, "tmax_s": tmax, "valid": False,
                "diagnostics": res["diagnostics"]}
    peak = res["qoi"]
    abs_gap = peak - ANALYTIC_PEAK
    return {
        "tstep_s": tstep,
        "tmax_s": tmax,
        "valid": True,
        "peak_measured": peak,
        "peak_analytic": ANALYTIC_PEAK,
        "gap_abs": abs_gap,
        "gap_rel": abs(abs_gap) / ANALYTIC_PEAK,
        "overshoots": abs_gap > 0,
        "exceeds_n2_1pct_relative": abs(abs_gap) / ANALYTIC_PEAK > N2_RELATIVE_TOLERANCE,
        "data_rows": int(res["diagnostics"].split(";")[1].strip().split()[0]),
        "runtime_s": res["runtime_s"],
    }


def main() -> int:
    tmax_rows = [_peak(1e-6, t) for t in TMAX_LADDER]
    tstep_rows = [_peak(ts, VALIDATED_TMAX) for ts in TSTEP_LADDER]

    ok = [r for r in tmax_rows if r["valid"]]
    # The saturation plateau: consecutive coarse points returning one peak.
    plateau = sorted({r["peak_measured"] for r in ok},
                     key=lambda p: -sum(1 for r in ok if r["peak_measured"] == p))
    plateau_peak = plateau[0]
    plateau_pts = [r["tmax_s"] for r in ok if r["peak_measured"] == plateau_peak]

    over = [r for r in ok if r["exceeds_n2_1pct_relative"]]
    # Monotone check over the BINDING region only (tmax at/below the plateau floor).
    binding = [r for r in ok if r["tmax_s"] < min(plateau_pts)]
    binding_monotone = all(binding[i]["gap_rel"] >= binding[i + 1]["gap_rel"]
                           for i in range(len(binding) - 1))
    fine = [r for r in ok if r["tmax_s"] <= 1e-5]
    fine_monotone = all(fine[i]["gap_rel"] >= fine[i + 1]["gap_rel"]
                        for i in range(len(fine) - 1))

    tstep_ok = [r for r in tstep_rows if r["valid"]]
    tstep_inert = (len({r["peak_measured"] for r in tstep_ok}) == 1
                   and len({r["data_rows"] for r in tstep_ok}) == 1)

    g10 = min(over, key=lambda r: r["gap_rel"]) if over else None

    doc = {
        "measurement": "G10 coarse-extremum setting (series RLC peak)",
        "purpose": ("establish, by measurement, a tmax at which the RLC peak's "
                    "gap to analytic exceeds N2's 1% RELATIVE tolerance, so the "
                    "G10 `refine` calibration case rests on a measured setting"),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "onboarding/ngspice_linear_passive/measure_coarse_extremum.py",
        "environment": {
            "container": "ngspice-prod",
            "solver": "ngspice-42 (dpkg 42+ds-3build1), aarch64, KLU",
            "wrapper": "tools/run_ngspice.py",
        },
        "circuit": {
            "source": "selfcheck_evidence.json check (e), verbatim",
            "vin": VIN, "r": R, "l": L, "c": C,
            "zeta": 0.19999825061734913,
            "tstop_s": TSTOP,
            "analytic_peak": ANALYTIC_PEAK,
            "qoi": "max of v(out) across C",
        },
        "units_warning": (
            "selfcheck_evidence.json check (e) reports gap_to_analytic_peak as an "
            "ABSOLUTE difference; N2's tolerance is RELATIVE. Both are reported "
            "here and never mixed. Check (e)'s 4.844e-03 absolute at tmax=1e-5 is "
            "3.173e-03 relative."
        ),
        "n2_relative_tolerance": N2_RELATIVE_TOLERANCE,
        "validated_ladder_from_check_e": [1e-5, 1e-6, 1e-7],
        "tmax_sweep": tmax_rows,
        "tstep_sweep": tstep_rows,
        "findings": {
            "tmax_is_a_ceiling_not_a_target": {
                "holds": len(plateau_pts) > 1,
                "plateau_tmax_s": sorted(plateau_pts),
                "plateau_peak": plateau_peak,
                "plateau_data_rows": sorted({r["data_rows"] for r in ok
                                             if r["peak_measured"] == plateau_peak}),
                "note": ("every tmax in the plateau returns one identical peak from "
                         "an identical row count: the request is inert because "
                         "ngspice's adaptive error control already steps finer than "
                         "it asks. A .tran cannot be coarsened past its adaptive "
                         "floor, only refined."),
            },
            "tstep_does_not_control_the_written_grid": {
                "holds": tstep_inert,
                "distinct_peaks": len({r["peak_measured"] for r in tstep_ok}),
                "distinct_row_counts": len({r["data_rows"] for r in tstep_ok}),
                "row_count": tstep_ok[0]["data_rows"] if tstep_ok else None,
                "note": ("wrdata writes one row per INTERNAL timestep, so the row "
                         "count tracks tmax (~tstop/tmax) and tstep is inert. An "
                         "extremum read off wrdata is sampled on the solver's grid, "
                         "never on the print grid."),
            },
            "error_is_non_monotone_in_the_binding_coarse_band": {
                "binding_region_monotone": binding_monotone,
                "fine_region_monotone_tmax_le_1e-5": fine_monotone,
                "note": ("check (e)'s monotone settle holds over its own ladder "
                         "(tmax <= 1e-5). In the binding-but-coarse band the error "
                         "is non-monotone and flips sign as sample points shift "
                         "around the true peak — the signature of an extremum "
                         "tracking the grid. The N4 monotone-settle screen is "
                         "therefore only meaningful on a ladder wholly inside the "
                         "fine region."),
            },
            "reachable_error_is_bounded": {
                "max_gap_rel_observed": max(r["gap_rel"] for r in ok),
                "note": ("because tmax saturates, the worst reachable peak error on "
                         "this circuit is ~1.1% — so no setting produces a "
                         "decisively-over-tolerance extremum here."),
            },
            "pre_registration": {
                "predicted": "tmax=1e-4 gap lands between 10% and 50%",
                "measured_at_1e-4_rel": next(r["gap_rel"] for r in ok if r["tmax_s"] == 1e-4),
                "verdict": "FALSIFIED",
                "why": ("tmax=1e-4 is inert (above the adaptive floor), so it returns "
                        "the plateau peak, not a coarse one. The guess assumed tmax "
                        "was a target the solver would honour."),
            },
        },
        "g10_selected_setting": (
            {
                "tstep_s": g10["tstep_s"],
                "tmax_s": g10["tmax_s"],
                "tstop_s": TSTOP,
                "peak_measured": g10["peak_measured"],
                "gap_rel": g10["gap_rel"],
                "gap_abs": g10["gap_abs"],
                "data_rows": g10["data_rows"],
                "exceeds_n2_1pct_relative": True,
                "knife_edge_disclosure": (
                    "the ONLY swept point over the 1% bar; its neighbours at 3e-5 "
                    "(9.94e-03) and 1.5e-5 (1.72e-03) sit UNDER it. Marginal by "
                    "construction — see reachable_error_is_bounded."
                ),
                "why_well_founded": (
                    "two independent reasons agree: the setting is outside the "
                    "validated ladder (tmax <= 1e-6), and its measured gap exceeds "
                    "N2's 1% relative bar."
                ),
            }
            if g10 else None
        ),
        "all_runs_valid": all(r["valid"] for r in tmax_rows + tstep_rows),
    }

    OUT_PATH.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n")
    print(f"wrote {OUT_PATH}")
    print(f"  tmax plateau: {sorted(plateau_pts)} -> peak {plateau_peak}")
    print(f"  tstep inert: {tstep_inert}")
    print(f"  binding-band monotone: {binding_monotone} | fine-region monotone: {fine_monotone}")
    if g10:
        print(f"  G10: tmax={g10['tmax_s']:g} gap_rel={g10['gap_rel']:.4e} "
              f"rows={g10['data_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
