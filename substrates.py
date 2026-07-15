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
