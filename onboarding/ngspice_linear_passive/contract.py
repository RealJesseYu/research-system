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

STAGING — RESOLVED at the R2 promotion flip (owner ruling, 2026-07-17).
The runtime CONTRACT constant has graduated to substrates.py (its canonical
home; re-exported below so CONTRACT_IMPORT keeps working) and is wired into
the registry's _CONTRACTS map alongside routable=True at maturity
`calibrating` (R3). The two battery-facing constants (SUBSTRATE_TEXT,
ENVELOPE) stay HERE — they are battery inputs, not runtime artifacts. See
registry_row_fragment.py and MERGE_NOTES.md for the staged history.
"""

# ---------------------------------------------------------------------------
# 1. The RUNTIME contract — merge/registry artifact. NOT battery-facing.
# ---------------------------------------------------------------------------

# MOVED at the R2 promotion flip (owner ruling, 2026-07-17): the runtime
# contract now lives in substrates.py — its canonical home per this module's
# own STAGING note and MERGE_NOTES.md — and is RE-EXPORTED here so the
# generator import path (CONTRACT_IMPORT) and every historical reference
# stay valid. ONE source; this is an import, never a second copy.
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from substrates import NGSPICE_LINEAR_PASSIVE_CONTRACT  # noqa: E402


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
