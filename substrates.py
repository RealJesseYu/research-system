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
On a failed run: converged is false and only a bounded set of error lines
(at most 40) explaining the failure is returned. A run is killed after 600
seconds of wall-clock time and reported as a failure.
Indicative cost, from the spike's surviving transient log (64x64 cavity,
endTime 20 s): solver ExecutionTime ~12.5 s to reach t=5 s and ~38 s to
t=20 s, ClockTime ~47 s; run_cfd wall-clock adds container and meshing
overhead on top. A steady-state solve of the same case was recorded in the
project journal at ~2 s, but no log of it survives on disk.

4. HONEST LIMITS
  - 2D laminar flow only. There are no turbulence models; a case whose
    physics is actually turbulent will not be simulated correctly and the
    wrapper cannot detect that.
  - Scalar-transport and mixing-field quantities (tracer concentration,
    mixing indices, anything requiring reading the solved fields) are NOT
    extractable by the current wrapper: it parses only residuals, Courant
    number, continuity error, and timing from the log. A spec may still
    request such a QoI — judging whether the instrument can feasibly serve
    a spec is the fidelity gate's job, not stage 2's — but as of today no
    field-derived quantity comes back through run_cfd.
  - No post-processing of any kind: no field sampling, no probes, no
    time-series of quantities other than what the solver prints on its own.
  - Convergence is judged from residuals and end time only; it says the
    solver settled, not that the physics is resolved (mesh-independence is
    nobody's promise here).
  - Whether a case's regime assumptions are themselves trustworthy is NOT
    checked anywhere in this contract; that open axis belongs to the
    fidelity gate's future work, and nothing here should be read as
    covering it.
"""
