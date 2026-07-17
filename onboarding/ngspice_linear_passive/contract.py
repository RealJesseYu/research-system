"""
contract.py — the gate-facing text for ngspice_linear_passive.

THREE CONSTANTS, THREE JOBS. They are deliberately not one constant, because
this codebase already keeps two different artifacts under the word "contract"
and collapsing them would either bloat the battery's input or gut the runtime
contract:

  NGSPICE_LINEAR_PASSIVE_CONTRACT
      The RUNTIME contract — the CAVITY_2D_CONTRACT-shaped five-section text a
      stage sees when it judges a case against this substrate. This is the
      MERGE/REGISTRY artifact: it moves into substrates.py at merge and becomes
      the registry's _CONTRACTS value IF AND WHEN this substrate is ever ruled
      routable. It has NO consumer today and is NOT battery-facing. (Measured
      peer: substrates.py::CAVITY_2D_CONTRACT is 8622 chars.)

  NGSPICE_LINEAR_PASSIVE_SUBSTRATE_TEXT
      The BATTERY's `substrate_text` — the compact capability abstract the
      calibration gate reads, at the scale its already-calibrated peers use
      (MEASURED: FEA 303 chars, code 607 chars). This is the ngspice analogue
      of those, not a copy of the contract above.

  NGSPICE_LINEAR_PASSIVE_ENVELOPE
      The BATTERY's `envelope_text` — rulings N1-N6, each as criterion +
      consequence on BOTH sides. (MEASURED peers: FEA 1451, code 1547.)

THE BINDING BETWEEN THE SUMMARY AND THE CONTRACT (read before editing either).
SUBSTRATE_TEXT is an ABSTRACT of CONTRACT, held by hand, with NO mechanical
link — deliberately. A mechanical excerpt would let an unrelated contract edit
silently reshape the gate's input, which is the one thing a calibration battery
must not have happen mid-flight. The cost of the hand link is that the two can
drift apart. THE CONTROL IS: any edit to CONTRACT's sections 1-3 requires
re-reading SUBSTRATE_TEXT in the same change, and summary-vs-contract honesty
is a checked item at card review. Nothing here is a second source of truth for
the SAME text: they are different texts with different jobs and different
readers, exactly as FEA's and code's substrate_text are not their wrappers'
docstrings.

WHY THE SUMMARY IS NOT SIMPLY "AS SHORT AS POSSIBLE" (measured, 2026-07-16).
The received rationale was that battery cost scales with the text the gate
READS. It does not. On the two batteries on disk (harness/calibration_*_
20260716T0130*.json), input_tokens per gate call are IDENTICAL at 2095.0 for
both substrates, yet FEA averaged 17.99 s/call and code 5.50 s/call. The
separator is what the model WRITES: 922.6 output tokens/call for FEA vs 184.7
for code — a 5.0x output ratio against a 3.3x wall-clock ratio. FEA's fixed
text is in fact SHORTER than code's (1754 vs 2154 chars), i.e. the length story
is inverted by its own evidence. Cost tracks DELIBERATION, not reading. The
lever on deliberation is decisiveness — which is precisely R-CARD-2: code's
card states its consequences and its gate answered 9/9 defer at entropy 0;
FEA-F1 states a criterion with no consequence and its gate split. So these
constants are written to be DENSE AND DECISIVE, not merely short: a ruling's
criterion and consequence are never truncated to hit a character target.

Every number below was MEASURED on ngspice-42 (dpkg 42+ds-3build1) running
aarch64 in the ngspice-prod container, through tools/run_ngspice.py, and is
cited from selfcheck_evidence.json and coarse_extremum_evidence.json in this
directory.

STAGING. This file lives under onboarding/ and is imported by the calibration
case generator by the path in generate_calibration_cases.py's CONTRACT_IMPORT
constant. At merge the constants move to substrates.py and that ONE line
changes. The substrate enters at maturity `calibrating` = unroutable, and it
gets a registry ROW but deliberately NO _CONTRACTS entry — see
registry_row_fragment.py and MERGE_NOTES.md.
"""

# ---------------------------------------------------------------------------
# 1. The RUNTIME contract — merge/registry artifact. NOT battery-facing.
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


# ---------------------------------------------------------------------------
# 2. The BATTERY's substrate_text — compact capability abstract.
#    Peer scale, MEASURED: FEA 303 chars, code 607 chars.
#    Abstract of CONTRACT sections 1-3; see the module docstring's binding note.
# ---------------------------------------------------------------------------

NGSPICE_LINEAR_PASSIVE_SUBSTRATE_TEXT = """\
ngspice-42 (KLU, containerised) solving IDEAL LUMPED LINEAR PASSIVE networks: R, L, C, \
ideal V/I sources, and linear controlled sources (E/F/G/H) only. Analyses: .op, .dc, \
.ac, .tran. A case is a typed request — netlist_body (element lines only; the wrapper \
owns every dot-command), one analysis, one qoi — screened pre-solve by element letter, \
strict 4-token R/L/C arity, and positive parsed value. Returns ONE scalar per run \
(op_value | final | max | min | value_at | corner_3db), or valid=False with a named \
reason and NO number; never the deck or log. Results describe the idealized netlist \
EXACTLY AS TYPED: no board parasitics, tolerance, ESR, or ground effects; no \
semiconductor device models.\
"""


# ---------------------------------------------------------------------------
# 3. The BATTERY's envelope_text — rulings N1-N6, owner-RULED 2026-07-16.
#    Peer scale, MEASURED: FEA 1451 chars, code 1547 chars.
#    Each ruling states its criterion AND its consequence on BOTH sides
#    (R-CARD-2). Completeness outranks length here: consequence-stating is the
#    property under test, so no criterion or consequence is trimmed to fit.
# ---------------------------------------------------------------------------

NGSPICE_LINEAR_PASSIVE_ENVELOPE = """\
ENVELOPE — ngspice_linear_passive (rulings N1-N6).

N1 IN-REGIME ANALYSES. Criterion: the analysis type is one of {op, dc, ac, tran}. \
In the list -> eligible for trust. Any other analysis (noise, pz, disto, ...) -> DEFER: \
wrong instrument.

N2 ANALYTIC-REPRODUCTION TOLERANCE. Criterion: the measured-vs-analytic gap at the \
case's stated settings, 1% RELATIVE. Inside -> eligible for trust. Outside -> REFINE \
(tighten tmax; a corner needs a lower fstart), and DEFER only if refinement fails.

N3 NETLIST-VS-BOARD SPLIT. Criterion: does the claim text assert PHYSICAL-HARDWARE \
behavior? A netlist claim -> trust path. A board claim (a built PCB will measure X) -> \
TRUST THE NUMBER AND DEFER THE BOARD CLAIM; the verdict is defer. The instrument \
describes the netlist as typed and nothing else.

N4 TRANSIENT EXTREMUM. Criterion: reduction is max or min -> the case must meet N2 at \
its stated tmax. A screened, settling extremum meeting N2 -> eligible for trust. An \
extremum at an unvalidated setting -> REFINE. An UNSCREENED new extremum family -> \
reported-only, not trusted. Validated within family v1 under the timestep protocol: \
absolute gap 4.8e-3 -> 5.6e-5 -> 4.7e-7 as tmax tightens 1e-5 -> 1e-6 -> 1e-7, a \
monotone settle. Note tmax is a CEILING, not a target: a tmax above the solver's own \
adaptive step is inert, and in the narrow binding-but-coarse band the error is \
non-monotone and sign-flipping, so the monotone screen only means anything on a ladder \
wholly inside the fine region.

N5 DEVICE-MODEL HONESTY — KNOWN GAP, out of regime by construction. There is NO \
criterion the gate can read: silicon fidelity lives in datasheets and on the bench, \
outside every text here. Advisory consequence: any claim resting on device-model \
fidelity -> DEFER to a future expert-reviewed device-model card. The letter screen \
rejects every such element pre-solve, so this can never reach a number.

N6 R/L/C 4-TOKEN ARITY. Criterion: every R/L/C line is exactly '<name> <node+> <node-> \
<value>' with a positive parsed value, checked in code pre-solve. Conforming -> \
eligible for trust. Violating -> SETUP_ERROR, rejected by line before any solve. This \
closes the measured ac=/tc1=/ic=/model-name override family, where ngspice silently \
simulates a value other than the one written and exits 0.\
"""
