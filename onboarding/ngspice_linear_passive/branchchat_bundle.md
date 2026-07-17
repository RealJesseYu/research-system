# ngspice_linear_passive — branch-chat bundle

Assembled for the branch chat, which has no repo access. Every section below was
extracted programmatically from the file named in its header — nothing retyped,
so there is no transcription error to find.

**This file is a SNAPSHOT, not a source of truth.** Section 2 in particular is a
copy of a constant that lives in `substrates.py`; the runtime source of truth for
any contract text remains its own module. If this bundle and the repo ever
disagree, the repo wins and this file is stale.

| section | source | sha256 of the quoted text |
|---|---|---|
| 1 | `onboarding/ngspice_linear_passive/selfcheck_evidence.json` | `e2e6bbc8c85af33f71ccaaa9bd1ce67f35924e0ebf8f3e36343dcc3e62ddb342` |
| 2 | `substrates.py` lines 16-155 | `7fbd09fb8adee44c22fc28506bd1492dabe745e2498684eb60ed5820bf46f9fb` |
| 3 | `tools/run_ngspice.py` module docstring | `12a897bc0a8e19b72f719ba819d4bc8027224b04c81c65389ef3e0be50c0c1eb` |

Section 2's sha matches the `substrates.py` lines 16-155 digest reported in the
session-1 debrief (`7fbd09fb8ade…`), confirming the region is unchanged.

---

## 1. `selfcheck_evidence.json` (full contents, verbatim)

```json
{
  "substrate": "ngspice_linear_passive",
  "generated_utc": "2026-07-16T17:43:29Z",
  "environment": {
    "container": "ngspice-prod",
    "docker_context": "colima",
    "ngspice_version_verbatim": "******\n** ngspice-42 : Circuit level simulation program\n** Compiled with KLU Direct Linear Solver\n** The U. C. Berkeley CAD Group\n** Copyright 1985-1994, Regents of the University of California.\n** Copyright 2001-2023, The ngspice team.\n** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n** Creation Date: Sun Mar 31 20:15:14 UTC 2024\n******",
    "dpkg_version": "42+ds-3build1",
    "uname_m": "aarch64",
    "host": "macOS + colima"
  },
  "wrapper": {
    "module": "tools/run_ngspice.py",
    "returned_fields": [
      "valid",
      "qoi",
      "diagnostics",
      "runtime_s"
    ],
    "timeout_seconds": 600,
    "max_retries": 1,
    "max_diag_chars": 800
  },
  "total_wall_clock_s": 43.0,
  "checks": [
    {
      "name": "a. resistive divider, .op",
      "settings": {
        "vin": 10.0,
        "r1": 1000.0,
        "r2": 2000.0,
        "analysis": "op",
        "qoi": "op_value of v(out)"
      },
      "measured": 6.66666667,
      "analytic": 6.666666666666667,
      "rel_error": 4.999999081434225e-10,
      "valid": true,
      "runtime_s": 0.282,
      "diagnostics": "ngspice op on 3 element line(s); 1 data row(s); op_value of v(out)"
    },
    {
      "name": "b. resistive divider, .dc sweep",
      "settings": {
        "sweep": "V1 0->10 step 1",
        "r1": 1000.0,
        "r2": 2000.0,
        "fit_points": [
          0.0,
          2.0,
          4.0,
          6.0,
          8.0,
          10.0
        ]
      },
      "measured_slope": 0.6666666668571428,
      "analytic_slope": 0.6666666666666666,
      "rel_error": 2.8571428556389833e-10,
      "swept_values": [
        0.0,
        1.33333333,
        2.66666667,
        4.0,
        5.33333333,
        6.66666667
      ],
      "valid": true,
      "runtime_s_total": 1.535
    },
    {
      "name": "c. RC low-pass, .ac corner vs grid density",
      "settings": {
        "r": 1000.0,
        "c": 1.59155e-07,
        "sweep": "dec 10Hz..100kHz",
        "points_per_decade": [
          10,
          100
        ]
      },
      "analytic_corner_hz": 999.9996424359609,
      "per_grid": {
        "10": {
          "corner_hz": 1000.0952908498522,
          "valid": true,
          "runtime_s": 0.253,
          "rel_error_vs_analytic": 9.564844809168556e-05
        },
        "100": {
          "corner_hz": 1000.099080038621,
          "valid": true,
          "runtime_s": 0.256,
          "rel_error_vs_analytic": 9.943763821535565e-05
        }
      },
      "delta_abs_hz": 0.0037891887687919734,
      "delta_rel": 3.788827728177812e-06,
      "grid_sensitivity_note": "corner shifts by this much when the frequency grid is refined 10x; a corner that moved materially here would not be a trustworthy QoI",
      "fstart_sensitivity": {
        "10.0": {
          "corner_hz": 1000.099080038621,
          "rel_error_vs_analytic": 9.943763821535565e-05,
          "predicted_bias_fstart_over_fc_squared": 0.00010000007151284615
        },
        "1.0": {
          "corner_hz": 1000.0006383969074,
          "rel_error_vs_analytic": 9.959613026312779e-07,
          "predicted_bias_fstart_over_fc_squared": 1.0000007151284616e-06
        },
        "0.1": {
          "corner_hz": 999.9996499468248,
          "rel_error_vs_analytic": 7.51086652404935e-09,
          "predicted_bias_fstart_over_fc_squared": 1.0000007151284618e-08
        }
      },
      "dominant_error_finding": "The corner's error is NOT dominated by grid density. |H_dc| is proxied by |H| at fstart, biasing the corner high by a relative (fstart/fc)^2 \u2014 1e-4 at fstart=10Hz, confirmed to 3 digits by the fstart sweep above and by closed-form algebra (u = sqrt(1+2s^2)). That bias is ~26x LARGER than the 3.8e-6 grid delta measured at the same fstart. Reporting the grid delta as the corner's error bar would understate it by that factor."
    },
    {
      "name": "d. RC step, .tran convergence vs tmax",
      "settings": {
        "vin": 1.0,
        "r": 1000.0,
        "c": 1e-06,
        "tau_s": 0.001,
        "tstep_s": 1e-05,
        "tstop_s": 0.005,
        "tmax_s": [
          5e-05,
          5e-06,
          5e-07
        ],
        "error_grid": "50 points over [0, 5 tau]"
      },
      "table": [
        {
          "tmax_s": 5e-05,
          "v_at_tau_measured": 0.632089130834968,
          "v_at_tau_analytic": 0.6321205588285577,
          "rel_error_at_tau": 4.971835380251747e-05,
          "max_rel_error_0_to_5tau": 0.0025960950620469345,
          "max_rel_error_at_t_s": 0.0001,
          "runtime_s": 0.255
        },
        {
          "tmax_s": 5e-06,
          "v_at_tau_measured": 0.6321201344077108,
          "v_at_tau_analytic": 0.6321205588285577,
          "rel_error_at_tau": 6.714238937241311e-07,
          "max_rel_error_0_to_5tau": 2.880854824465454e-05,
          "max_rel_error_at_t_s": 0.0001,
          "runtime_s": 0.263
        },
        {
          "tmax_s": 5e-07,
          "v_at_tau_measured": 0.6321203819241193,
          "v_at_tau_analytic": 0.6321205588285577,
          "rel_error_at_tau": 2.798587007646952e-07,
          "max_rel_error_0_to_5tau": 4.789995234330059e-06,
          "max_rel_error_at_t_s": 0.0001,
          "runtime_s": 0.273
        }
      ],
      "monotone_shrinking": true
    },
    {
      "name": "e. series RLC step overshoot (D.5 discretization screen)",
      "settings": {
        "vin": 1.0,
        "r": 12.649,
        "l": 0.001,
        "c": 1e-06,
        "zeta": 0.19999825061734913,
        "tstep_s": 1e-06,
        "tstop_s": 0.003,
        "tmax_s": [
          1e-05,
          1e-06,
          1e-07
        ],
        "qoi": "max of v(out) across C"
      },
      "analytic_peak": 1.5266236763247512,
      "table": [
        {
          "tmax_s": 1e-05,
          "peak_measured": 1.531468,
          "peak_analytic": 1.5266236763247512,
          "gap_to_analytic_peak": 0.004844323675248896,
          "settled_measured": 1.0,
          "settled_analytic": 1.0,
          "settled_residual": 0.0,
          "runtime_s": 0.409
        },
        {
          "tmax_s": 1e-06,
          "peak_measured": 1.52667938,
          "peak_analytic": 1.5266236763247512,
          "gap_to_analytic_peak": 5.570367524887487e-05,
          "settled_measured": 1.0,
          "settled_analytic": 1.0,
          "settled_residual": 0.0,
          "runtime_s": 0.451
        },
        {
          "tmax_s": 1e-07,
          "peak_measured": 1.52662415,
          "peak_analytic": 1.5266236763247512,
          "gap_to_analytic_peak": 4.736752488021523e-07,
          "settled_measured": 1.0,
          "settled_analytic": 1.0,
          "settled_residual": 0.0,
          "runtime_s": 0.667
        }
      ],
      "monotone_settle": true,
      "screen_note": "max(v_out) is an EXTREMUM QoI and therefore a discretization-artifact suspect. The trend across tightening tmax is the screen: a peak that keeps climbing as the step shrinks is tracking the grid, not the physics."
    },
    {
      "name": "f. adversarial probes (jails proven by failing the escape)",
      "setup_errors": [
        {
          "probe": "floating node (no DC path)",
          "valid": false,
          "qoi": null,
          "diagnostics": "solver reported a failure (exit 0): singular matrix \u2014 a node has no DC path to ground [Warning: singular matrix:  check node mid | Warning: singular matrix:  check node mid | Warning: Dynamic gmin stepping failed | Warning: singular matrix:  check node mid]",
          "pass": true
        },
        {
          "probe": "undefined model",
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'D1 a 0 nosuchmodel' \u2014 element letter 'D' is outside the linear-passive regime (allowed: C E F G H I L R V)",
          "pass": true
        },
        {
          "probe": "zero-value resistor",
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'R1 a 0 0' \u2014 R value '0' parses to 0, which is not positive; ngspice would silently substitute a minimum value and return a fabricated result",
          "pass": true
        },
        {
          "probe": "garbage line",
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 3: '5R xx yy zz' \u2014 element letter '5' is outside the linear-passive regime (allowed: C E F G H I L R V)",
          "pass": true
        },
        {
          "probe": "missing analysis field",
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: missing required field(s): analysis",
          "pass": true
        }
      ],
      "regime_escapes": [
        {
          "probe": "diode line",
          "screen_reasons": [
            "line 2: 'D1 a 0 dmod' \u2014 element letter 'D' is outside the linear-passive regime (allowed: C E F G H I L R V)"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'D1 a 0 dmod' \u2014 element letter 'D' is outside the linear-passive regime (allowed: C E F G H I L R V)",
          "pass": true
        },
        {
          "probe": ".model line",
          "screen_reasons": [
            "line 3: '.model dmod D(is=1e-14)' \u2014 dot-commands are owned by the wrapper, not the caller; the netlist body carries circuit elements only"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 3: '.model dmod D(is=1e-14)' \u2014 dot-commands are owned by the wrapper, not the caller; the netlist body carries circuit elements only",
          "pass": true
        },
        {
          "probe": "B-source (behavioral)",
          "screen_reasons": [
            "line 2: 'B1 b 0 V=v(a)*v(a)' \u2014 element letter 'B' is outside the linear-passive regime (allowed: C E F G H I L R V)"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'B1 b 0 V=v(a)*v(a)' \u2014 element letter 'B' is outside the linear-passive regime (allowed: C E F G H I L R V)",
          "pass": true
        },
        {
          "probe": "POLY controlled source",
          "screen_reasons": [
            "line 2: 'E1 b 0 POLY(1) a 0 0 1 1' \u2014 'POLY' form on a controlled source is nonlinear/expression-valued; only the plain linear-gain form passes v1"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'E1 b 0 POLY(1) a 0 0 1 1' \u2014 'POLY' form on a controlled source is nonlinear/expression-valued; only the plain linear-gain form passes v1",
          "pass": true
        },
        {
          "probe": ".include line",
          "screen_reasons": [
            "line 3: '.include /etc/passwd' \u2014 dot-commands are owned by the wrapper, not the caller; the netlist body carries circuit elements only"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 3: '.include /etc/passwd' \u2014 dot-commands are owned by the wrapper, not the caller; the netlist body carries circuit elements only",
          "pass": true
        },
        {
          "probe": "brace expression",
          "screen_reasons": [
            "line 2: 'R1 a 0 {rval*2}' \u2014 '{' (expression interpolation) is not allowed in the linear-passive regime",
            "line 2: 'R1 a 0 {rval*2}' \u2014 cannot parse the R value '{rval*2}' as a SPICE number"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'R1 a 0 {rval*2}' \u2014 '{' (expression interpolation) is not allowed in the linear-passive regime | line 2: 'R1 a 0 {rval*2}' \u2014 cannot parse the R value '{rval*2}' as a SPICE number",
          "pass": true
        },
        {
          "probe": "K coupled inductors",
          "screen_reasons": [
            "line 5: 'K1 L1 L2 0.5' \u2014 element letter 'K' is outside the linear-passive regime (allowed: C E F G H I L R V)"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 5: 'K1 L1 L2 0.5' \u2014 element letter 'K' is outside the linear-passive regime (allowed: C E F G H I L R V)",
          "pass": true
        },
        {
          "probe": "negative resistor",
          "screen_reasons": [
            "line 2: 'R1 a 0 -1k' \u2014 R value '-1k' parses to -1000, which is not positive; ngspice would silently substitute a minimum value and return a fabricated result"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'R1 a 0 -1k' \u2014 R value '-1k' parses to -1000, which is not positive; ngspice would silently substitute a minimum value and return a fabricated result",
          "pass": true
        },
        {
          "probe": "per-analysis value override (ac=)",
          "screen_reasons": [
            "line 2: 'R1 a out 1k ac=100k' \u2014 R element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'ac=100k' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'R1 a out 1k ac=100k' \u2014 R element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'ac=100k' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here",
          "pass": true
        },
        {
          "probe": "temperature coefficient (tc1=)",
          "screen_reasons": [
            "line 2: 'R1 a 0 1k tc1=0.001' \u2014 R element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'tc1=0.001' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'R1 a 0 1k tc1=0.001' \u2014 R element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'tc1=0.001' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here",
          "pass": true
        },
        {
          "probe": "initial condition (ic=)",
          "screen_reasons": [
            "line 3: 'C1 b 0 1u ic=3' \u2014 C element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'ic=3' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 3: 'C1 b 0 1u ic=3' \u2014 C element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'ic=3' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here",
          "pass": true
        },
        {
          "probe": "model name on a passive",
          "screen_reasons": [
            "line 2: 'R1 a 0 rmodel w=1u' \u2014 R element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'w=1u' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here"
          ],
          "rejected_pre_solve": true,
          "valid": false,
          "qoi": null,
          "diagnostics": "input rejected: netlist rejected by the regime screen: line 2: 'R1 a 0 rmodel w=1u' \u2014 R element takes exactly '<name> <node+> <node-> <value>' in v1; the extra token(s) 'w=1u' select a model or a per-analysis/temperature value override, which can silently change the simulated value away from the one written here",
          "pass": true
        }
      ],
      "all_pass": true
    }
  ]
}
```

---

## 2. `CAVITY_2D_CONTRACT`, copied exactly from `substrates.py`

Exact source region, including the assignment line and the closing delimiter.
Verified by `ast.literal_eval`: the literal below evaluates to the identical
string object the module exposes as `CAVITY_2D_CONTRACT`.

```python
CAVITY_2D_CONTRACT = """\
SUBSTRATE CONTRACT: cavity_2d

1. WHAT THE INSTRUMENT IS
This substrate runs 2D incompressible laminar cavity-class cases: a closed
box of fluid driven by one or more moving walls (the classic lid-driven
cavity and its variants). The solver is OpenFOAM v12 running inside a
container, driven through the run_cfd wrapper — deterministic Python with no
AI inside, which launches the case's declared solver application and reads
the resulting log. The validated envelope comes from the spike: a 1 m square
cavity, 64x64 mesh, lid at 2 m/s, kinematic viscosity 0.01 m^2/s (Reynolds
number 200), laminar, converged. Cases near that class are proven; anything
far outside it is unproven, not impossible.

2. WHAT A CASE MUST DEFINE
A case is a complete, self-contained directory the solver can run as-is.
It must define:
  - geometry and mesh: the cavity shape and its cell resolution (a blockMesh
    description is built automatically if a mesh dictionary is present and
    no mesh exists yet);
  - boundary velocities: which walls move and how fast, and which are
    stationary no-slip walls;
  - the fluid's kinematic viscosity;
  - steady vs. transient treatment and an end time: the case's own control
    dictionary declares the solver application, the end time, and the time
    step — the wrapper reads these, it does not choose them.

3. WHAT run_cfd RETURNS TODAY
On a run that completes, a small fixed summary — never the full solver log:
  - converged: true or false. The EXACT definition: the run's final
    simulated time reached the case's declared end time (within one time
    step), AND every field residual recorded at the start of the final time
    step is below 1e-3. Both must hold; "finished cleanly" alone is not
    converged.
  - residuals: the per-field residuals from the final time step, as parsed
    from the solver log.
  - final time: the last simulated time the solver reached.
  - Courant number: the maximum reported Courant number.
  - continuity error: the last reported global continuity error.
  - runtime: solver execution time and wall-clock seconds.
  - qoi (OPTIONAL, on request): the wrapper can extract ONE quantity of
    interest per run from fields the case already wrote, at the latest
    written time, using the solver's own stock post-processing machinery.
    Supported operations: volAverage | min | max | volIntegrate over one
    existing field, with an optional component (e.g. mag for a vector's
    magnitude, or 0|1|2 for a single component). On success the summary
    gains qoi {name, field, operation, value, time}. QoI extraction
    requires the run to have reached its declared end time; convergence is
    reported separately, and a QoI from an unconverged run is reported
    without endorsement — judging whether such a value is usable is
    downstream judgment, not the wrapper's.
  - qoi_error: on ANY extraction failure (missing field, post-processing
    error, unparseable output) the summary carries qoi_error with an
    honest reason and NO qoi block — the instrument never fabricates a
    number.
  - qois (OPTIONAL, on request): instead of a single QoI, a VECTOR of
    quantities of interest may be extracted from ONE solved case in a single
    pass. Each entry names a reduction — min | max | volAverage — over an
    existing field (U or p; a vector component is chosen with mag for the
    magnitude or 0|1|2 for one component). Each reduction may additionally
    carry a deterministic spatial mask that restricts it to part of the
    domain: corner_exclusion {radius_frac} drops cells within that fraction
    of the domain size of any corner; boundary_exclusion {distance_frac}
    keeps only cells at least that fraction of the domain size away from any
    wall; box {x_min, x_max, y_min, y_max as domain fractions} keeps only the
    cells inside that fractional box. A masked result reports the number of
    cells masked and the total cell count beside its value. Each entry
    succeeds or fails independently, exactly as the single-QoI path does — a
    bad entry yields a per-entry qoi_error and NO number, never a fabricated
    value. Alongside the vector, a COMPACT FIELD EXPORT is written for
    offline analysis: cell centres and cell volumes plus the final U and p
    fields, saved as an on-disk array file, with only a small summary (its
    path, the field list, the cell count, and per-field min/max/mean)
    returned — the raw field arrays never cross back into any stage.
On a failed run: converged is false and only a bounded set of error lines
(at most 40) explaining the failure is returned. A run is killed after 600
seconds of wall-clock time and reported as a failure.
Indicative cost, measured on this substrate (64x64 mesh, transient): the
per-step solver rate is a RANGE of 2.3-4.1 ms/step, not a single fixed rate,
and wall-clock time scales with Reynolds number — measured points are ~9.2-9.3 s
for baseline short runs and 161-175 s for Re 100-1600 sweep runs (the latter
versus the ~95 s a stale single-rate estimate once predicted). Wall-clock
includes container exec, meshing, and log-parsing overhead.

4. HONEST LIMITS
  - 2D laminar flow only. There are no turbulence models; a case whose
    physics is actually turbulent will not be simulated correctly and the
    wrapper cannot detect that.
  - Field-derived QoIs come ONLY from fields the solved case actually
    wrote. For this substrate that means velocity- and pressure-field
    statistics (e.g. volume-averaged |U|, min/max/integral of p) YES;
    concentration fields NO: the incompressible laminar solve carries no
    scalar-transport / tracer physics, so no concentration field exists to
    read, and concentration-derived mixing QoIs remain unextractable. No
    new fields the case didn't write. A spec may still request an
    unservable QoI — judging whether the instrument can feasibly serve a
    spec is the fidelity gate's job, not stage 2's.
  - Post-processing reads the latest written time only: a single QoI or a
    whole VECTOR of QoIs (each optionally spatially masked) plus the compact
    field export are all taken from that one final written state. There is no
    time-series extraction, no probes, and no field sampling other than the
    volume reductions (masked or whole-domain) and the field export listed
    above — nothing before the final time can be read.
  - A masked extremum is only as trustworthy as its mask is honest, and two
    rules follow. (i) A masked extremum MUST state its mask type and its
    parameters in the spec — an extremum whose masking region is left
    unstated is not interpretable. (ii) A masked-extremum TREND should be
    demonstrated mask-insensitive — the value stays stable as the exclusion
    region grows — before it is relied on, because a mask that merely clips a
    boundary singularity by a little still reports that singularity. Measured
    example on this substrate: the interior minimum of p at Re 100 is -0.270
    with a corner-exclusion radius of 0.05 but only -0.141 at radius 0.10 — a
    roughly two-fold swing, so this particular extremum is NOT yet
    mask-insensitive and its trend must not be trusted without a
    wider-radius check.
  - Convergence is judged from residuals and end time only; it says the
    solver settled, not that the physics is resolved (mesh-independence is
    nobody's promise here).
  - Whether a case's regime assumptions are themselves trustworthy is NOT
    checked anywhere in this contract; that open axis belongs to the
    fidelity gate's future work, and nothing here should be read as
    covering it.

5. CANONICAL PARAMETER VOCABULARY
The case builder honors exactly these canonical parameter names; a run
whose parameters use them (with plain numeric values) can be synthesized
into a runnable case:
  - kinematic_viscosity  (m^2/s) — the fluid's kinematic viscosity
  - lid_velocity         (m/s)   — the moving-wall speed
  - cavity_length        (m)     — the cavity's side length (uniform scaling)
  - mesh_resolution      (cells per side) — N, meshed as N x N x 1
  - end_time             (s)     — simulated end time
  - time_step            (s)     — solver time step
Reynolds number is never buildable directly: specify lid_velocity,
cavity_length, and kinematic_viscosity, and Re may be stated as a derived
quantity (it will be verified against that decomposition, not honored on
its own). Parameters beyond this vocabulary remain fully legitimate when
the hypothesis genuinely requires them — but the current builder cannot
honor them and will halt loudly, by name, on any it does not know.
"""
```

---

## 3. Module docstring of `tools/run_ngspice.py`

The authoritative statement of the regime screen — the text the future contract
constant draws from.

```text

run_ngspice — the production ngspice (linear passive circuit) solver wrapper.

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_cfd.py holds for OpenFOAM and run_fea.py holds for CalculiX. This
wrapper is UNREGISTERED at build time: nothing in stages/, the supervisor,
substrates.py, or any schema imports it. It is reachable by tests (and a
__main__ CLI) only.

Shape mirrors run_fea:
  * a typed input is turned into a full ngspice deck by deterministic Python
    (no LLM anywhere in the execution step);
  * the deck runs inside the `ngspice-prod` container (bind-mounted
    cases_ngspice/, mirroring of12-prod / ccx-prod), with a hard timeout and
    ONE retry on transient failure;
  * ngspice's raw log and wrdata output are parsed down to a SMALL summary and
    the raw log NEVER leaves the wrapper.

Typed input:
    run_ngspice({
      "netlist_body": "V1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k",
      "analysis": {"type": "op"},
      "qoi": {"kind": "node_voltage", "target": "out",
              "reduction": "op_value", "at": None},
    })

Return (and ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}

WHO OWNS WHAT
-------------
The CALLER supplies circuit element lines ONLY. The WRAPPER owns every
dot-command, the .control block, the analysis statement, the wrdata call, and
the .end. This is why `.`-lines are rejected outright (see the screen below):
allowing them would let a caller redefine the analysis the wrapper believes it
ran, or pull in arbitrary files.

THE REGIME SCREEN (verbatim; this IS the regime boundary, enforced pre-solve)
----------------------------------------------------------------------------
Every rule below names the offending line and the reason. Rejection happens
BEFORE any solve, and a rejected input never reaches the container.

  1. SIZE.  netlist_body is capped at 200 lines / 20000 bytes.
  2. ALLOWED ELEMENT LETTERS (case-insensitive), first character of the line:
         R  resistor
         L  inductor
         C  capacitor
         V  independent voltage source
         I  independent current source
         E  linear voltage-controlled voltage source
         F  linear current-controlled current source
         G  linear voltage-controlled current source
         H  linear current-controlled voltage source
     Every other letter is rejected by letter and line, including:
         D Q M J B T O U S W A X K N P  and any unknown letter.
     K (coupled inductors) is excluded from v1 DELIBERATELY — mutual coupling
     is linear and would fit the regime, but it is untested here. It is an
     OPEN CARD QUESTION, not an oversight.
  3. DOT-LINES.  Any line whose first non-blank character is `.` is rejected.
     This bans .model, .subckt, .include, .lib, .param, .ic, .options, .tran,
     .ac, .dc, .op and everything else BY CONSTRUCTION rather than by listing.
  4. NONLINEAR / EXPRESSION FORMS.  On E/F/G/H lines the tokens POLY, TABLE,
     and `value=` are rejected (matched case-insensitively, on word
     boundaries, so a node merely named "table" is not a false positive).
     A `{` ANYWHERE in the body is rejected — braces are ngspice's expression
     interpolation syntax and admit arbitrary nonlinear behaviour.
  5. COMPONENT VALUES.  An R/L/C line must be EXACTLY
         <name> <node+> <node-> <value>
     — four tokens. The value is parsed with a deterministic SPICE number parser
     and must be > 0. A non-positive value, an unparseable value, or ANY extra
     trailing token (a model name, `ac=`, `temp=`, `tc1=`, `m=`, `ic=` ...) is
     rejected by name pre-solve. See "WHY RULE 5 IS LOAD-BEARING" below.
  6. COMMENTS.  `*` comment lines and in-line `;` comments are permitted and
     ignored by the screen; a `+` continuation line is rejected in v1 (the
     screen classifies lines independently and cannot see what it continues).

WHY RULE 5 IS LOAD-BEARING (two measured findings, not precautions)
------------------------------------------------------------------
Both were MEASURED on ngspice-42, aarch64, in ngspice-prod. Both produce a
confident, plausible, WRONG number with exit code 0 and a clean log, so nothing
downstream of the solve can catch either. The pre-solve screen is the only
defence, which is why it is in code here and not in any prompt.

  (i) ZERO VALUE.  `R1 a 0 0` does not warn, does not set a nonzero exit code,
      and emits NO log marker. ngspice silently substitutes a minimum
      resistance and reports `i(v1) = -1.00000e+03` — a fabricated 1000 A
      through a short.

 (ii) TRAILING VALUE OVERRIDE.  `R1 in out 1k ac=100k` runs cleanly and reports
      an RC corner of 10.0 Hz where the written 1k implies 1000 Hz. The deck's
      stated value is not the simulated value, and no marker fires. Found by
      screening ngspice's own shipped test suite, where
      tests/resistance/res_partition.cir uses exactly this form.

WHY THE MARKER SCAN EXISTS (also measured)
------------------------------------------
MEASURED: a floating node (no DC path to ground) makes ngspice fail its
operating-point solve, fall through gmin stepping and source stepping, then
succeed at a transient operating point and print a plausible-looking answer
with exit code 0. The exit code is NOT a sufficient failure signal. Any marker
hit forces valid=False and qoi=None — the wrapper never returns a QoI when a
marker fired.
```
