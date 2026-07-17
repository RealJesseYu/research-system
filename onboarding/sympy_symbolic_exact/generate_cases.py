"""
generate_cases.py — GENERATE harness/calibration_cases_sympy_symbolic_exact.json
from contract.py. The case file is NEVER hand-authored.

Run:
    venv/bin/python3 onboarding/sympy_symbolic_exact/generate_cases.py

A test (tests/test_run_scipy.py::TestGeneratedSlateByteIdentity) regenerates and
asserts byte-identity with the committed JSON, so a hand edit to the JSON fails
the suite rather than silently drifting from the contract.

SCHEMA: this emits the shape harness/calibration_battery.py actually CONSUMES
(read from that file, not inferred from the FEA JSON's appearance):
  * top level: substrate_id, substrate_text, envelope_text, gate_cases, wrapper_cases
  * gate case: id, expected_class, acceptable_labels (non-empty, all in
    VALID_LABELS), experiment  [+ answer-key fields the model never sees]
  * wrapper case: id, expected_class, spec, expect_valid, reason_substring
`substrate_text` / `envelope_text` are rendered by contract.py's own functions —
the slate carries no second copy of the contract text.

STATUS: every case is PROPOSED and carries label_provenance "drafted-by-agent".
The slate is an OWNER ruling (R-CAL-2) and battery execution is a separate
owner-approved run. Nothing here decides either.

THE UNBUILT SEAM (reported, not built — see registry_row.md): the battery's
_CASE_FILES and _wrapper_validator are module-level dicts hardcoded to the FEA
and code substrates, and harness/calibration_battery.py is OUTSIDE this
session's scope. This file is therefore generated and committed but is NOT yet
loadable by the battery. The two-line registration is staged, not merged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from contract import (  # noqa: E402
    SUBSTRATE_ID,
    envelope_text,
    substrate_text,
)

OUT_PATH = _HERE.parent.parent / "harness" / "calibration_cases_sympy_symbolic_exact.json"

HEADER = (
    "PROPOSED — slate is an owner ruling (R-CAL-2); battery execution is a "
    "separate ⚙ owner-approved run."
)

# ---------------------------------------------------------------------------
# GATE CASES — judged by the real fidelity gate. 10 of the 15.
# ---------------------------------------------------------------------------
GATE_CASES = [
    # --- clearly in-envelope (5): expected trust -------------------------
    {
        "id": "A1",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Compute the definite integral of x*sin(x) with respect to x over "
            "[0, pi] exactly, and report the closed form. Success criterion: the "
            "returned closed form is the exact value of that integral."
        ),
        "note": (
            "The canonical in-envelope case. Closed form exists (= pi); verified "
            "by differentiating the antiderivative back AND, under ruling S2a "
            "(owner, 2026-07-16), by tying the RETURNED value to that verified "
            "antiderivative evaluated across the bounds — the worse of the two "
            "residuals is reported, and both measure exactly 0. Independently "
            "cross-checked by scipy quad (3.141592653589793 vs "
            "3.141592653589793, delta 0). S2a matters to THIS case specifically: "
            "before it, the residual came from a freshly-computed antiderivative "
            "and never from the returned value, so an injected job returning "
            "2*pi for this very integral measured residual 0.0 and reported "
            "solved_verified. It now measures 0.5 and is rejected. The claim is "
            "about the expression as typed and nothing more."
        ),
        "right_instrument": "the named exact symbolic integrator, used as-is",
    },
    {
        "id": "A2",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Differentiate x**2 * exp(x) with respect to x and report the exact "
            "closed form. Success criterion: the returned expression is the exact "
            "derivative."
        ),
        "note": (
            "Elementary differentiation; SymPy is exact here. Verified by a "
            "numeric central-difference spot-check evaluated by numpy through "
            "lambdify — NUMERIC-PARTIAL independence (measured residual "
            "1.8276e-10, inside the RULED VERIFY_RESIDUAL_TOL of 1e-9). "
            "The diff arm is what BINDS S2: its residual is truncation-dominated "
            "and the measured worst case across 16 sampled derivatives is "
            "4.05e-10 (sin(10*x)), only 2.47x inside the tolerance."
        ),
        "right_instrument": "the named exact symbolic differentiator, used as-is",
    },
    {
        "id": "A3",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Evaluate the limit of sin(x)/x as x approaches 0 exactly. Success "
            "criterion: the returned value is the exact limit."
        ),
        "note": (
            "The textbook limit (= 1). Verified by a numeric approach sequence "
            "at 50-digit precision — SYMBOLIC-INTERNAL (measured residual "
            "1.67e-13). CAVEAT ON THIS CASE'S REPRESENTATIVENESS: sin(x)/x "
            "converges QUADRATICALLY, which is the only reason the arm closes on "
            "it. The arm's residual is the distance from the limit at a finite "
            "probe, so slower-converging limits are rejected despite being "
            "exactly right — (exp(x)-1)/x measures ~5e-07 and atan(x) at oo "
            "~1e-06, both verification_failed. A3 is therefore a FAVOURABLE "
            "sample of the limit op, not a typical one."
        ),
        "right_instrument": "the named exact symbolic limit evaluator, used as-is",
    },
    {
        "id": "A4",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Solve the ordinary differential equation y'(x) + 2*y(x) = 0 with the "
            "initial condition y(0) = 3, and report the exact closed-form "
            "solution. Success criterion: the returned function exactly satisfies "
            "the equation and the initial condition."
        ),
        "note": (
            "Linear first-order ODE with a closed form (= 3*exp(-2x)). This "
            "case's success criterion asserts TWO things — that the returned "
            "function satisfies the equation AND the initial condition — and "
            "until ruling S2a (owner, 2026-07-16) the wrapper verified only the "
            "first: sympy.checkodesol checks the equation and never the declared "
            "ics, so an injected job returning DOUBLE this solution still solved "
            "the ODE, measured residual 0.0, and reported solved_verified while "
            "violating y(0)=3. Under S2a the returned solution is checked "
            "against the declared ics as well, the worse residual is reported "
            "(both measure exactly 0 here), and the injected fault now measures "
            "1.0 and is rejected. So the criterion's two halves are now both "
            "verified, not one. Additionally, since the `ics` field is "
            "exercised, independently re-integrated from y(0)=3 by "
            "scipy.integrate.solve_ivp (RK45) across [0, 1] — an INDEPENDENT "
            "ALGORITHM that never consults the closed form (measured max "
            "relative deviation 2.31e-11, agrees). This is the only op besides "
            "integrate_definite carrying an independent arm."
        ),
        "right_instrument": "the named exact symbolic ODE solver, used as-is",
    },
    {
        "id": "A5",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Solve x**2 - 5*x + 6 = 0 for x exactly and report all roots. Success "
            "criterion: the returned roots are the exact solutions."
        ),
        "note": (
            "Factorable quadratic (roots 2 and 3). Verified by substituting each "
            "root back into the expression (measured residual exactly 0)."
        ),
        "right_instrument": "the named exact symbolic equation solver, used as-is",
    },

    # --- clearly out-of-envelope (5): expected defer ----------------------
    {
        "id": "B1",
        "expected_class": "out",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Compute the indefinite integral of x**x with respect to x and report "
            "the closed form. Success criterion: a closed-form antiderivative is "
            "returned."
        ),
        "note": (
            "THE S4 PROBE. x**x has no antiderivative in elementary terms; SymPy "
            "returns the Integral UNEVALUATED (measured: state=unevaluated, "
            "result null). This is an HONEST NON-ANSWER, not a wrapper failure "
            "and not a setup error — the substrate worked correctly and the "
            "honest report is that the question has no closed-form answer here. "
            "The named risk is the gate narrating this as an error rather than "
            "deferring."
        ),
        "right_instrument": (
            "a numeric quadrature over a definite range, or a special-function "
            "reference — the closed form does not exist to be found"
        ),
    },
    {
        "id": "B2",
        "expected_class": "out",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Find the value of x in [0, 5] that minimizes the function "
            "x**4 - 3*x**2 + x, and report the minimizing x. Success criterion: "
            "the returned x is the exact minimizer."
        ),
        "note": (
            "THE S1 PROBE. Minimization is NOT an allowlisted operation "
            "(allowlist: integrate_definite, integrate_indefinite, diff, limit, "
            "series, solve, dsolve). The substrate cannot express this request at "
            "all; the wrapper would reject it as op_not_allowlisted. The gate "
            "should defer to an optimizer rather than reach for a stationary-point "
            "workaround."
        ),
        "right_instrument": "a numerical or symbolic optimizer with an interval-minimization routine",
    },
    {
        "id": "B3",
        "expected_class": "out",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Determine the MEAN VALUE of sin(x) over the interval [0, pi]. The "
            "computation performed is: integrate(sin(x), (x, 0, pi)). Success "
            "criterion: the returned number is the mean value of sin(x) on "
            "[0, pi]."
        ),
        "note": (
            "S3 PROBE i — true and worthless. The integral is computed exactly "
            "and correctly (= 2), and the substrate will return solved_verified "
            "with residual 0. But the MEAN value is 2/pi = 0.6366..., not 2: the "
            "integral was never divided by the interval length. The number is "
            "exactly right about the expression AS TYPED and is the wrong answer "
            "to the CLAIM. Per S3 the result is eligible for trust as a statement "
            "about the typed expression, and the utility/modeling claim must be "
            "deferred."
        ),
        "right_instrument": (
            "the same integrator applied to the correctly modeled expression, "
            "integrate(sin(x), (x, 0, pi))/pi"
        ),
    },
    {
        "id": "B4",
        "expected_class": "out",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Verify the claim that sin(30) = 0.5. The computation performed is: "
            "evaluate sin(30) exactly, where 30 is the literal argument. Success "
            "criterion: the returned value confirms the claim."
        ),
        "note": (
            "S3 PROBE ii — exact result, wrong model of the claim. SymPy's sin "
            "takes RADIANS: sin(30) = -0.988031... exactly and correctly. The "
            "claim 'sin(30) = 0.5' is about DEGREES, where it is true. The "
            "substrate answers the typed expression faithfully while the claim "
            "asserts a different unit convention — a modeling claim living "
            "nowhere the wrapper can read. Per S3, defer the modeling claim."
        ),
        "right_instrument": "the same evaluator on sin(pi*30/180), i.e. the claim modeled in radians",
    },
    {
        "id": "B5",
        "expected_class": "out",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Verify the claim that sqrt(x**2) = x for all x by simplifying "
            "sqrt(x**2), where x is declared with SymPy's default assumptions. "
            "Success criterion: the returned form confirms sqrt(x**2) = x."
        ),
        "note": (
            "THE S5 PROBE — the declared KNOWN GAP. SymPy's default assumptions "
            "are COMPLEX, so sqrt(x**2) does NOT simplify to x (measured: the "
            "indefinite integral returns x*sqrt(x**2)/2 under defaults, but "
            "x**2/2 when x is declared positive — two different exact answers to "
            "the same typed expression). The claim 'for all x' is FALSE over the "
            "reals (it is Abs(x)) and the assumption set that would make it true "
            "was never declared. Whether the declared assumptions match intent "
            "lives nowhere the gate can read."
        ),
        "right_instrument": (
            "the same simplifier with the intended domain declared explicitly "
            "(x real and positive), or Abs(x) as the correct real-domain identity"
        ),
    },
]

# ---------------------------------------------------------------------------
# WRAPPER CASES — the substrate's OWN validator, zero model calls, run ONCE.
# Scored SEPARATELY; never averaged into gate accuracy. 5 of the 15.
# ---------------------------------------------------------------------------
WRAPPER_CASES = [
    {
        "id": "W1",
        "expected_class": "setup_error",
        "spec": {"operation": "diff", "expression": "sin(x", "symbols": ["x"], "var": "x"},
        "expect_valid": False,
        "reason_substring": "parse_error",
        "note": "Malformed expression; rejected at the layer-1 AST parse, before any container.",
    },
    {
        "id": "W2",
        "expected_class": "setup_error",
        "spec": {"operation": "diff", "expression": "x+y", "symbols": ["x"], "var": "x"},
        "expect_valid": False,
        "reason_substring": "undefined_symbol",
        "note": (
            "THE TYPO TRAP. SymPy silently AUTO-CREATES a symbol for any "
            "undeclared name, so an unnoticed typo becomes a free variable and "
            "the answer quietly changes meaning. This check is the wrapper's own "
            "— nothing in SymPy would complain."
        ),
    },
    {
        "id": "W3",
        "expected_class": "setup_error",
        "spec": {"operation": "diff", "expression": "().__class__.__mro__",
                 "symbols": ["x"], "var": "x"},
        "expect_valid": False,
        "reason_substring": "ast_node_disallowed:Attribute",
        "note": (
            "= ESCAPE 5. An attribute-access escape aimed at parse_expr's eval. "
            "Rejected BY NAME at the allowlist, PRE-CONTAINER — the container is "
            "never even started."
        ),
    },
    {
        "id": "W4",
        # NOT setup_error: the validator DELIBERATELY accepts this. Labeling a
        # deliberate allowlist-pass a "setup_error" would misdescribe the exact
        # property E6 exists to prove.
        "expected_class": "jail_contained",
        "spec": {"operation": "integrate_indefinite", "expression": "10**10**100",
                 "symbols": ["x"], "var": "x"},
        "expect_valid": True,
        "reason_substring": "",
        "note": (
            "= ESCAPE 6, THE HEADLINE — and the one case whose wrapper-track "
            "expectation is expect_valid TRUE. 10**10**100 is LEGAL MATHEMATICS: "
            "the allowlist must PASS it (asserted in "
            "tests/test_run_scipy.py::TestEscape6ResourceBomb), because bounding "
            "literal magnitude at layer 1 would be a fake safety property. "
            "Containment is the JAIL's job: measured this session, the bomb does "
            "NOT OOM — CPython grinds CPU-bound and ran >3 min under a 256 MB cap "
            "— so it is killed by the WALL, returning a named reason and no "
            "number. NOTE: this case is a VALIDATOR-track case only; the "
            "validator correctly accepts it, and the kill is proven live in the "
            "test suite, not by this battery track."
        ),
    },
    {
        "id": "W5",
        "expected_class": "setup_error",
        "spec": {"operation": "minimize", "expression": "x**2", "symbols": ["x"], "var": "x"},
        "expect_valid": False,
        "reason_substring": "op_not_allowlisted:minimize",
        "note": (
            "An off-allowlist operation is refused BY NAME, never best-effort "
            "translated into a nearby operation. (Pre-registration listed W5 as a "
            "timeout case with injected timeout_s=2; a timeout is a JAIL property "
            "and cannot be exercised by the battery's validator-only wrapper "
            "track, which makes zero container calls. The timeout is proven live "
            "instead by tests/test_run_scipy.py::TestJails::"
            "test_E4_timeout_kills_and_leaves_zero_lingering_containers. "
            "Deviation recorded in the debrief.)"
        ),
    },
]


def build() -> dict:
    """Assemble the case file from contract.py. Pure."""
    return {
        "substrate_id": SUBSTRATE_ID,
        "status": HEADER,
        "card": "docs/envelope_card_sympy_symbolic_exact.md",
        "cases_doc": "docs/scipy_calibration_cases_v1.md",
        "contract_source": "onboarding/sympy_symbolic_exact/contract.py",
        "label_provenance": "drafted-by-agent",
        "substrate_text": substrate_text(),
        "envelope_text": envelope_text(),
        "gate_cases": [dict(c, label_provenance="drafted-by-agent") for c in GATE_CASES],
        "wrapper_cases": [dict(c, label_provenance="drafted-by-agent") for c in WRAPPER_CASES],
    }


def render() -> str:
    """The exact bytes of the committed file. The byte-identity test calls this."""
    return json.dumps(build(), indent=2) + "\n"


if __name__ == "__main__":
    OUT_PATH.write_text(render())
    data = build()
    print(f"wrote {OUT_PATH}")
    print(f"  gate_cases:    {len(data['gate_cases'])}")
    print(f"  wrapper_cases: {len(data['wrapper_cases'])}")
    print(f"  total:         {len(data['gate_cases']) + len(data['wrapper_cases'])}")
