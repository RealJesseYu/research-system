"""
substrates.py — the substrate contract: a plain-language description of what
each simulation instrument actually is, needs, returns, and cannot do.

This file sits AT the tool-wrapper level, so it is the one place above raw
tool code where a specific solver may be named. Upper layers (stages) never
import solver names from here — when this contract is eventually shown to a
stage, it is the whole point that the stage sees an honest capability
description rather than discovering limits by crashing into them.

Drafted this chunk from two READ-ONLY references in the spike
(~/research-spike/tools/run_cfd.py and ~/research-spike/SPIKE_CONCLUSION.md).
Nothing imports this file yet.
"""

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


# ---------------------------------------------------------------------------
# ngspice_linear_passive — GRADUATED out of onboarding/ngspice_linear_passive/
# contract.py at the R2 promotion flip (owner ruling, 2026-07-17), per that
# module's own STAGING note and its MERGE_NOTES.md ('moves to substrates.py').
# ONE source: the onboarding module now re-exports this constant; the
# battery-facing SUBSTRATE_TEXT / ENVELOPE constants stay onboarding-side —
# different artifacts with different readers (see that module's docstring).
# Every number in the text was MEASURED on ngspice-42 through
# tools/run_ngspice.py; citations live beside the onboarding evidence files.
# ---------------------------------------------------------------------------

NGSPICE_LINEAR_PASSIVE_CONTRACT = """\
SUBSTRATE CONTRACT: ngspice_linear_passive

1. WHAT THE INSTRUMENT IS
This substrate solves ideal lumped linear passive networks: circuits built from
resistors, inductors, capacitors, ideal independent voltage/current sources, and
linear controlled sources. The solver is ngspice 42 running inside a container,
driven through the run_ngspice wrapper — deterministic Python with no AI inside,
which composes the whole deck (the caller supplies element lines only), runs it,
and reads the resulting log. The validated envelope comes from this substrate's
own self-checks: a resistive divider, a single-pole RC low-pass (tau = 1 ms,
corner ~1 kHz), and a series RLC at damping ratio zeta = 0.2, each agreeing with
closed-form circuit theory. Cases near that class are proven; anything far
outside it is unproven, not impossible.
Analyses offered: .op, .dc, .ac, .tran. An analysis outside that set (noise, pz,
disto, and the rest of ngspice's reach) is out of this regime by ruling.

2. WHAT A CASE MUST DEFINE
A case is a typed request, not a file. It must define:
  - netlist_body: the circuit's element lines ONLY. No dot-commands and no
    .control block — the wrapper owns all of those, including the analysis
    statement itself. A netlist line beginning with '.' is rejected.
  - analysis: exactly one of
      {"type": "op"}
      {"type": "dc",   "source", "start", "stop", "step"}
      {"type": "ac",   "variation": "dec"|"lin"|"oct", "n", "fstart", "fstop"}
      {"type": "tran", "tstep", "tstop", "tmax"}
  - qoi: {"kind": "node_voltage" | "vsource_current", "target": <node or source
    name>, "reduction": <see section 3>, "at": <float or null>}
Allowed element letters, first character of the line, case-insensitive:
    R  resistor                     L  inductor
    C  capacitor                    V  independent voltage source
    I  independent current source   E  linear voltage-controlled voltage source
    F  linear current-controlled current source
    G  linear voltage-controlled current source
    H  linear current-controlled voltage source
Banned element letters, each rejected by letter and line number pre-solve:
    D Q M J B T O U S W A X K N P, and any unknown letter.
K (coupled inductors) is excluded from v1 DELIBERATELY: mutual coupling is
linear and would fit this regime, but it is untested here. That is an OPEN CARD
QUESTION, not an oversight.
An R/L/C line must be EXACTLY '<name> <node+> <node-> <value>' — four tokens,
with a value that parses as a SPICE number and is strictly positive. On E/F/G/H
lines the POLY, TABLE and value= forms are rejected. A '{' anywhere in the body
is rejected. Component values accept the SPICE suffixes f p n u m mil k meg g t,
where m is MILLI and meg is 1e6.

3. WHAT run_ngspice RETURNS TODAY
On a run that completes, a small fixed summary — never the full solver log:
  - valid: true or false. False means NO number is reported, for any reason.
  - qoi: ONE scalar per run, or null. The reduction is applied in Python, never
    in ngspice measurement scripting:
      op_value    — the single operating-point value (.op only)
      final       — the value at the last solved point
      max | min   — the extremum over all solved points
      value_at    — the value interpolated at "at" (time for .tran, frequency
                    for .ac, sweep value for .dc); linear in the sweep variable,
                    log-frequency for .ac
      corner_3db  — the -3 dB corner frequency (.ac only), by log-frequency
                    interpolation at |H| = |H_dc|/sqrt(2); the returned
                    diagnostics carry the run's own estimated fstart bias
  - diagnostics: a bounded, honest, human-readable line (<= 800 characters).
    Never the raw deck or log.
  - runtime_s: wall-clock seconds.
A QoI is NEVER returned when any failure marker appears in the log, when the
output file is missing or empty, when the requested vector does not exist, or
when the extracted value is not finite. The instrument does not fabricate a
number: the exit code alone is not trusted, because a broken circuit can exit 0
(see section 4).
Indicative cost, measured on this substrate: 0.19-0.85 s of wall clock per solve
(median 0.26 s, n=31), dominated by container-exec overhead rather than by the
solve — the circuits themselves solve in milliseconds, and a 30,023-row
transient differs from a 3-element steady solve by well under 3x. Runs are
killed after 600 seconds and reported as a failure; nothing in this regime has
approached that.
How this summary maps to an upstream stage-4 run entry (ruled R1 option 4,
2026-07-17): converged := (valid is true). For this substrate, converged means
the run COMPLETED AND PARSED — the deck ran, no failure marker fired, and one
finite scalar was extracted. It does NOT mean an iterative-residual criterion
was met: this instrument has none — a linear network solve either completes or
it does not, and agreement with circuit theory is judged separately (section 4).
valid=false maps to converged=false with the diagnostics line carried as
qoi_error, and no number. This substrate carries no optional `state` value: the
summary has no state vocabulary of its own beyond the boolean valid.
THIS INSTRUMENT'S REGIME (ruled R-23.5-5, 2026-07-17): not a Reynolds band —
the regime of a linear passive network is which analysis it lives in. An
experiment spec's required "regime" object for this substrate is
  {"analysis_type": "op" | "dc" | "ac" | "tran", "notes": "..."}
where the four analysis types are the wrapper's own typed analysis set
(section 2) — the same set whose boundary section 1 declares out of regime by
ruling. A regime block carrying Reynolds fields, an analysis_type outside
that set, or a missing analysis_type is rejected by the per-substrate
validator before anything runs.

4. HONEST LIMITS
  - Ideal linear passive only. There are no semiconductor device models, no
    behavioral sources, no transmission lines, no subcircuits, and no
    nonlinearity of any kind. A hypothesis whose physics needs them is outside
    this instrument, and the regime screen rejects the netlist rather than
    silently approximating it.
  - QoI values characterize the ideal netlist exactly as provided; no physical-
    board effects (trace parasitics, component tolerance, ESR, non-ideal ground)
    are represented. A result here is a statement about a schematic, not about a
    manufactured board.
  - The solver's exit code is NOT a sufficient failure signal, and two measured
    failures prove it. (i) A floating node (no DC path to ground) fails the
    operating-point solve, falls through gmin and source stepping, then succeeds
    at a transient operating point, prints a plausible voltage, and EXITS 0. The
    wrapper catches this by scanning the log for failure markers. (ii) A
    zero-valued resistor emits NO marker at all, exits 0, and reports a
    fabricated 1000 A through the short; only the pre-solve value screen catches
    it. A third, found by screening ngspice's own shipped test suite: a trailing
    per-analysis override (`R1 in out 1k ac=100k`) runs clean and silently
    simulates a value other than the one written, which is why R/L/C arity is
    fixed at four tokens.
  - ONE scalar QoI per run. There is no vector of QoIs, no time series, no field
    export, and no second quantity from the same solve — a second quantity means
    a second run.
  - An extremum QoI (max/min) is a discretization-artifact suspect and must be
    screened before it is trusted: the value is only meaningful if it is stable
    as the timestep tightens. MEASURED example on this substrate, series RLC at
    zeta = 0.2 (analytic peak 1.5266236763): max(v_out) overshoots the analytic
    peak by 4.84e-03 ABSOLUTE (3.17e-03 relative) at tmax = 10 us, 5.57e-05
    (3.65e-05 rel) at 1 us, and 4.74e-07 (3.10e-07 rel) at 0.1 us — a monotone
    settle onto the closed-form answer, so this particular extremum IS
    trustworthy at tmax <= 1 us. An extremum whose gap does NOT shrink this way
    is tracking the grid, not the physics. Note the units: the settle figures
    above are absolute gaps; the reproduction tolerance is relative.
  - For .tran, tmax is the refinement lever, not tstep — and it is a ONE-WAY
    lever. MEASURED: tmax is a CEILING on the solver's step, not a target, so a
    tmax coarser than ngspice's own adaptive error control is simply inert
    (every tmax from 4e-5 to 2e-4 on the zeta=0.2 RLC returns the identical peak
    1.52415539 from an identical 144 data rows). A .tran run cannot be coarsened
    past its adaptive floor — only refined. MEASURED further: tstep does not
    control the written grid at all; wrdata emits one row per INTERNAL timestep
    (row count ~ tstop/tmax), unchanged across a 50x tstep range, so an extremum
    is always sampled on the solver's grid and never on the print grid.
    Consequently the band where tmax binds but is still too coarse is narrow,
    and inside it the peak error is NON-MONOTONE and flips sign — the monotone-
    settle screen is only meaningful on a ladder wholly inside the fine region.
    MEASURED, RC step at tau = 1 ms: the relative error at t = tau falls
    4.97e-05 -> 6.71e-07 -> 2.80e-07 as tmax tightens 50 us -> 5 us -> 0.5 us,
    and the worst error over [0, 5*tau] falls 2.60e-03 -> 2.88e-05 -> 4.79e-06.
  - A corner_3db QoI carries a systematic bias set by fstart, NOT by the
    frequency grid. |H_dc| is proxied by the magnitude at the lowest solved
    frequency, which biases a one-pole corner HIGH by a relative
    (fstart/fcorner)^2. MEASURED: +9.94e-05 at fstart = 10 Hz, +9.96e-07 at
    1 Hz, +7.51e-09 at 0.1 Hz, against a predicted 1e-04 / 1e-06 / 1e-08.
    Refining the grid from 10 to 100 points per decade moved the same corner by
    only 3.79e-06 relative — roughly 26x LESS than the fstart bias it sat inside.
    Reading the grid-density delta as the corner's error bar understates it by
    that factor; start the sweep at least three decades below the expected
    corner. Each corner_3db run reports its own estimated bias in diagnostics.
  - Convergence is not this instrument's risk; agreement with closed-form theory
    is. A linear network has an exact answer, so a result that disagrees with
    circuit theory means the request was mis-posed or under-resolved, not that
    the physics is subtle.
  - Whether a case's regime assumptions are themselves trustworthy is NOT
    checked anywhere in this contract; that open axis belongs to the fidelity
    gate's future work, and nothing here should be read as covering it.

5. CANONICAL PARAMETER VOCABULARY
Unlike the cavity substrate, this instrument takes no named physical-parameter
dictionary: the circuit itself is the parameterization, written as element lines
in netlist_body. The wrapper honors exactly these typed keys:
  - netlist_body   (string)  — circuit element lines only, <= 200 lines / 20 kB
  - analysis.type  (enum)    — op | dc | ac | tran
  - analysis.*     (numbers) — the fields listed in section 2 for that type
  - qoi.kind       (enum)    — node_voltage | vsource_current
  - qoi.target     (name)    — a node name, or a voltage-source name for current
  - qoi.reduction  (enum)    — op_value | final | max | min | value_at | corner_3db
  - qoi.at         (number)  — required for value_at, forbidden otherwise
Every field is validated by name pre-solve; a missing, unknown, or ill-typed
field is rejected before anything runs. Component values live inside
netlist_body in SPICE notation, not as separate parameters.
"""
