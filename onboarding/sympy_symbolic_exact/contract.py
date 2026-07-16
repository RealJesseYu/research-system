"""
contract.py — THE single runtime source of truth for the `sympy_symbolic_exact`
substrate (sci-Python, Regime A).

ONE runtime source of truth for contract text (standing doctrine). Three
consumers, zero copies:

  * `docs/envelope_card_sympy_symbolic_exact.md` POINTS AT this file by path —
    it never pastes the contract text.
  * `onboarding/sympy_symbolic_exact/generate_cases.py` GENERATES
    `harness/calibration_cases_sympy_symbolic_exact.json` FROM this file.
  * `tools/run_scipy.py` IMPORTS this file — the allowlists it enforces are
    these objects, not a second list that could drift.

Never a third copy of any text below.

STAGING NOTE: this module lives under onboarding/ deliberately. The substrate is
UNREGISTERED and UNROUTABLE — nothing in `stages/`, the supervisor,
`substrates.py`, or any schema imports it. Registration is a separate owner
ruling; the Wave Guide merges the staged fragments serially.

PROVISIONAL CONSTANTS: `VERIFY_RESIDUAL_TOL` and `CROSSCHECK_AGREE_TOL` are
labeled SUGGESTED-pending-owner-ruling. They gate the wrapper's
`solved_verified` state provisionally so the machinery is exercisable now; the
card marks both TODO-HUMAN (slots S2 and S6). A provisional constant that gates
behavior is honest only while it is labeled as one — do not quietly promote
either by deleting its label.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
SUBSTRATE_ID = "sympy_symbolic_exact"

REGIME_DESCRIPTION = (
    "Exact symbolic computer algebra over a single closed-form expression, "
    "evaluated by SymPy inside an ephemeral, no-network, memory-capped "
    "container. One operation per job, on one expression typed as text, over "
    "symbols the caller declares explicitly. The substrate answers questions "
    "ABOUT THE EXPRESSION AS TYPED and nothing else: it manipulates the "
    "symbols it was given under the assumptions it was given. It is exact "
    "where it succeeds — a returned antiderivative is a real antiderivative, "
    "checked by differentiating it back — and it is honest where it fails, "
    "because SymPy frequently returns an operation UNEVALUATED rather than "
    "wrong. That third outcome is neither an answer nor an error and is "
    "carried as its own state. What the substrate cannot see is whether the "
    "expression as typed is the right model of the question the caller meant "
    "to ask, or whether the declared assumption set matches the caller's "
    "intent; SymPy's defaults are COMPLEX, so sqrt(x**2) does not simplify to "
    "x unless positivity or realness was declared."
)

# ---------------------------------------------------------------------------
# S1 (SUGGESTED-pending-owner-ruling) — the operation allowlist.
# ---------------------------------------------------------------------------
OPERATIONS: tuple[str, ...] = (
    "integrate_definite",
    "integrate_indefinite",
    "diff",
    "limit",
    "series",
    "solve",
    "dsolve",
)

# Per-operation required / optional typed fields, BEYOND the universal
# `operation` / `expression` / `symbols` (+ optional `assumptions`).
# The wrapper derives its field checks from this table — the table IS the
# vocabulary, not a description of one kept elsewhere.
OP_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "integrate_definite": {"required": ("var", "lower", "upper"), "optional": ()},
    "integrate_indefinite": {"required": ("var",), "optional": ()},
    "diff": {"required": ("var",), "optional": ("order",)},
    "limit": {"required": ("var", "point"), "optional": ()},
    "series": {"required": ("var", "point"), "optional": ("order",)},
    "solve": {"required": ("var",), "optional": ()},
    # `ics` is an ADDITION to the build prompt's suggested field vocabulary.
    # Reason (recorded, debrief S12): the proposed slate's case A4 is worded
    # "y' + 2y = 0, y(0)=3" — the initial condition is part of the ruled case,
    # and without an `ics` field it is not expressible, so A4 could only ever
    # test the general solution. Shape: {"y(0)": 3} — each KEY is an expression
    # string that goes through the SAME layer-1 AST allowlist as `expression`,
    # each VALUE is a plain number.
    "dsolve": {"required": ("var", "func"), "optional": ("ics",)},
}

UNIVERSAL_REQUIRED_FIELDS: tuple[str, ...] = ("operation", "expression", "symbols")
UNIVERSAL_OPTIONAL_FIELDS: tuple[str, ...] = ("assumptions",)

# ---------------------------------------------------------------------------
# The math-function allowlist. A `Name` in the expression AST is legal only if
# it is a declared symbol or a member of this set; a `Call` is legal only if its
# callee is a plain `Name` in this set. Everything else is rejected BY NAME.
#
# These names are bound, inside the jail, to the corresponding SymPy objects in
# a RESTRICTED parse namespace. SymPy's default parse namespace is
# `from sympy import *` — which is exactly why it must be overridden.
# ---------------------------------------------------------------------------
ALLOWED_FUNCTIONS: tuple[str, ...] = (
    # elementary transcendental
    "sin", "cos", "tan", "cot", "sec", "csc",
    "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "exp", "log", "sqrt", "Abs",
    # special / combinatorial
    "gamma", "erf", "factorial",
    # structural
    "Derivative", "Integral", "Function",
    # constants (bare Names, not calls)
    "pi", "E", "I", "oo", "zoo", "nan",
)

# Names that are CONSTANTS rather than callables — legal as bare `Name`s but
# never as a `Call` callee. Kept as a subset of ALLOWED_FUNCTIONS so there is
# one membership test, not two lists to drift apart.
ALLOWED_CONSTANTS: tuple[str, ...] = ("pi", "E", "I", "oo", "zoo", "nan")

# ---------------------------------------------------------------------------
# S5-adjacent — the assumption allowlist. Declaring an assumption changes the
# MATHEMATICAL MEANING of the job (sqrt(x**2) is x under positive=True and
# Abs(x) under the complex default), so the vocabulary is small and closed.
# Whether the declared set matches the caller's INTENT is the known gap (S5):
# it lives nowhere the gate can read.
# ---------------------------------------------------------------------------
ALLOWED_ASSUMPTIONS: tuple[str, ...] = (
    "real", "positive", "negative", "nonnegative", "nonzero",
    "integer", "rational", "complex", "finite",
)

# ---------------------------------------------------------------------------
# The three-state semantics — the paragraph the fidelity gate will eventually
# read. Verbatim; the card points here rather than restating it.
# ---------------------------------------------------------------------------
THREE_STATE_SEMANTICS = (
    "Every job returns exactly one of three states, and they are never "
    "collapsed into two.\n\n"
    "solved_verified — SymPy found a closed form AND the wrapper independently "
    "verified it (an antiderivative is differentiated back and compared to the "
    "integrand; a root is substituted back; an ODE solution goes through "
    "checkodesol; a derivative/limit/series is spot-checked numerically). The "
    "result is the expression as a string. This state is the ONLY one that "
    "carries a number or an expression out of the wrapper.\n\n"
    "unevaluated — SymPy returned the operation without performing it: an "
    "Integral, Derivative, or Limit object survived in the output, or solve "
    "returned no roots. This is an HONEST NON-ANSWER, not a failure. The "
    "canonical instance is the indefinite integral of x**x, which has no "
    "closed form in elementary terms; SymPy correctly declines rather than "
    "inventing one. The result field is null. An unevaluated result must NEVER "
    "leak as a QoI and must NEVER be dressed up as an error — the substrate "
    "worked correctly and the honest report is that this question has no "
    "closed-form answer here.\n\n"
    "error — the job did not produce a trustworthy result: invalid or "
    "malformed input, an expression rejected by the AST allowlist, a container "
    "kill (memory cap or timeout), or — critically — verification_failed, "
    "meaning SymPy DID return a closed form but the wrapper could not confirm "
    "it. A solved-but-unverified answer is an error, not a result: no number "
    "leaves this wrapper unverified. The result field is null and a named "
    "reason states which failure occurred."
)

# ---------------------------------------------------------------------------
# PROVISIONAL CONSTANTS — SUGGESTED-pending-owner-ruling.
# ---------------------------------------------------------------------------

# S2. The residual below which a back-substitution check counts as passing.
# SUGGESTED-pending-owner-ruling. Justification is empirical, from this
# session's measured self-checks (see the card §3A): symbolic checks close to
# EXACTLY zero (simplify returns the zero object), and the numeric fallbacks
# measured residuals at or below ~1e-10. 1e-9 sits above the measured numeric
# noise floor and far below any physically meaningful discrepancy. It is a
# provisional gate on `solved_verified`, and the card marks it TODO-HUMAN.
VERIFY_RESIDUAL_TOL: float = 1e-9
VERIFY_RESIDUAL_TOL_STATUS = "SUGGESTED-pending-owner-ruling"

# S6-adjacent. The relative agreement below which the SciPy `quad` cross-check
# is reported as agreeing with the symbolic closed form.
# SUGGESTED-pending-owner-ruling.
# HONEST LIMIT, stated where the constant lives: quad returns an error
# ESTIMATE, not a bound. Agreement within this tolerance is EVIDENCE the
# symbolic answer is right, never a proof. The cross-check is a DIAGNOSTIC
# ONLY (owner ruling 2026-07-16: Regime B — scipy_numeric_quad — is QUEUED, and
# no SciPy number may ever surface as a result).
CROSSCHECK_AGREE_TOL: float = 1e-8
CROSSCHECK_AGREE_TOL_STATUS = "SUGGESTED-pending-owner-ruling"

# Numeric-fallback sampling: when `simplify` will not close a symbolic residual
# to zero, the wrapper samples the difference at these points.
NUMERIC_SAMPLE_POINTS: tuple[float, ...] = (0.37, 1.13, 2.71, 4.19, 6.53)
NUMERIC_PRECISION_DPS: int = 50

# ---------------------------------------------------------------------------
# The dsolve INDEPENDENT arm (scipy.integrate.solve_ivp). Mechanics only — this
# arm is DIAGNOSTIC, exactly like the quad arm, and gates nothing. Its agreement
# verdict is reported against CROSSCHECK_AGREE_TOL (card slot S6), which is why
# no new provisional constant is introduced here.
#
# The interval is STATED, not implicit: the ODE is integrated numerically from
# the declared initial point x0 across [x0, x0 + ODE_CROSSCHECK_SPAN] and the
# numeric trajectory is compared to the closed form at ODE_CROSSCHECK_SAMPLES
# equally-spaced points.
#
# rtol/atol are solve_ivp's error CONTROLS, NOT guaranteed bounds — the same
# honest limit quad's abserr carries, stated where the constants live.
# ---------------------------------------------------------------------------
ODE_CROSSCHECK_SPAN: float = 1.0
ODE_CROSSCHECK_SAMPLES: int = 5
ODE_CROSSCHECK_RTOL: float = 1e-10
ODE_CROSSCHECK_ATOL: float = 1e-12

# The finite-difference step for the lambdify+numpy derivative spot-check.
# 1e-6 sits near the float64 central-difference optimum (~eps**(1/3)): large
# enough that the 1/h roundoff amplification stays small, small enough that the
# O(h**2) truncation term stays small.
NUMERIC_DIFF_STEP: float = 1e-6

# ---------------------------------------------------------------------------
# Rejection-reason taxonomy — machine-greppable, stable strings. The wrapper
# emits EXACTLY these prefixes; the calibration slate greps them.
# ---------------------------------------------------------------------------
REJECTION_REASONS: tuple[str, ...] = (
    "missing_field:<name>",
    "unknown_field:<name>",
    "op_not_allowlisted:<op>",
    "undefined_symbol:<name>",
    "parse_error",
    "ast_node_disallowed:<NodeType>",
    "function_not_allowlisted:<name>",
    "assumption_not_allowlisted:<name>",
    "timeout",
    "container_killed:<detail>",
    "verification_failed",
)

# ---------------------------------------------------------------------------
# The bundled contract object. `generate_cases.py` reads THIS; the card points
# at this module; the wrapper imports the pieces.
# ---------------------------------------------------------------------------
SYMPY_SYMBOLIC_EXACT_CONTRACT: dict = {
    "substrate_id": SUBSTRATE_ID,
    "regime_description": REGIME_DESCRIPTION,
    "operations": OPERATIONS,
    "op_fields": OP_FIELDS,
    "universal_required_fields": UNIVERSAL_REQUIRED_FIELDS,
    "universal_optional_fields": UNIVERSAL_OPTIONAL_FIELDS,
    "allowed_functions": ALLOWED_FUNCTIONS,
    "allowed_constants": ALLOWED_CONSTANTS,
    "allowed_assumptions": ALLOWED_ASSUMPTIONS,
    "three_state_semantics": THREE_STATE_SEMANTICS,
    "rejection_reasons": REJECTION_REASONS,
    "ode_crosscheck": {
        "arm": "scipy.integrate.solve_ivp (RK45)",
        "span": ODE_CROSSCHECK_SPAN,
        "samples": ODE_CROSSCHECK_SAMPLES,
        "rtol": ODE_CROSSCHECK_RTOL,
        "atol": ODE_CROSSCHECK_ATOL,
        "agreement_slot": "S6 (CROSSCHECK_AGREE_TOL)",
    },
    "provisional_constants": {
        "VERIFY_RESIDUAL_TOL": {
            "value": VERIFY_RESIDUAL_TOL,
            "status": VERIFY_RESIDUAL_TOL_STATUS,
            "card_slot": "S2",
        },
        "CROSSCHECK_AGREE_TOL": {
            "value": CROSSCHECK_AGREE_TOL,
            "status": CROSSCHECK_AGREE_TOL_STATUS,
            "card_slot": "S6",
        },
    },
}


# ---------------------------------------------------------------------------
# The model-visible contract TEXT. This is the paragraph a fidelity gate would
# be shown — the analogue of substrates.CAVITY_2D_CONTRACT, generated FROM the
# structured data above so the two can never disagree.
#
# It is a FUNCTION, not a constant, precisely so no copy of the text exists at
# rest: every reader renders it from the same objects the wrapper enforces.
# ---------------------------------------------------------------------------

def substrate_text() -> str:
    """The short 'what the instrument is' paragraph, for the calibration slate."""
    return (
        f"SUBSTRATE: {SUBSTRATE_ID} (sci-Python, Regime A). "
        f"{REGIME_DESCRIPTION} "
        f"Allowlisted operations: {', '.join(OPERATIONS)}. "
        f"Typed input fields: operation, expression, symbols, optional "
        f"assumptions, plus per-operation fields (var, lower, upper, point, "
        f"order, func). Every free name in the expression must be declared in "
        f"symbols — SymPy silently auto-creates symbols for typos, so the "
        f"wrapper checks this itself. Unknown fields are rejected by name. "
        f"One operation per job; the expression is parsed in a restricted "
        f"namespace inside an ephemeral no-network, memory-capped container."
    )


def envelope_text() -> str:
    """The 'what is validated, and what is not' paragraph, for the slate.

    Rendered from THREE_STATE_SEMANTICS plus the declared known gaps, so the
    envelope the gate is shown is literally the contract the wrapper enforces.
    """
    return (
        "VALIDATED: a result is returned ONLY in the state solved_verified, "
        "which requires that SymPy found a closed form AND the wrapper "
        "independently verified it by back-substitution (differentiate an "
        "antiderivative and compare to the integrand; substitute roots; "
        "checkodesol for ODEs; numeric spot-checks evaluated by numpy for "
        "diff/series and at arbitrary precision for limit), with residual "
        "within the provisional tolerance "
        f"VERIFY_RESIDUAL_TOL = {VERIFY_RESIDUAL_TOL:g} "
        f"({VERIFY_RESIDUAL_TOL_STATUS}). "
        "A solved-but-unverified answer is returned as error:verification_failed "
        "— no number leaves the wrapper unverified.\n\n"
        + THREE_STATE_SEMANTICS
        + "\n\nHOW INDEPENDENT THE VERIFICATION ACTUALLY IS — three tiers, and "
        "the difference matters. (1) SYMBOLIC-INTERNAL: back-substitution, "
        "checkodesol and the limit approach-sequence are SymPy checking SymPy's "
        "own work with SymPy's own evaluator; a shared bug is invisible to "
        "them. (2) NUMERIC-PARTIAL: the diff and series spot-checks — and "
        "solve's fallback when an exact symbolic zero does not close — evaluate "
        "the expression through sympy.lambdify onto numpy, so the ARITHMETIC is "
        "numpy's while the TRANSLATION from the SymPy tree to a numpy callable "
        "is still SymPy's; independence is PARTIAL. (3) INDEPENDENT ALGORITHM: "
        "definite integrals are re-computed by scipy.integrate.quad, and ODEs "
        "with a declared initial condition are re-integrated by "
        "scipy.integrate.solve_ivp (RK45) from that condition and compared to "
        "the closed form at sampled points across a stated interval. These two "
        "arms run a genuinely different ALGORITHM that never consults the "
        "symbolic answer — but they too reach numpy through SymPy's lambdify, "
        "so NO arm is independent of SymPy's translation layer. Both are "
        "DIAGNOSTIC ONLY and never a result: quad's abserr is an ERROR ESTIMATE "
        "and solve_ivp's rtol/atol are error CONTROLS — neither is a BOUND, so "
        "agreement is evidence, never proof. diff, limit, series and solve have "
        "NO independent-algorithm arm.\n\n"
        "WHY limit IS NOT ON THE NUMPY ARM (measured, not assumed): a limit "
        "spot-check evaluates an indeterminate form arbitrarily close to its "
        "singularity, where catastrophic cancellation is the rule. Moving it to "
        "float64 was tried and reverted — (1-cos(x))/x**2 probed at x=1e-6 "
        "measured residual 4.445e-05 on numpy against 4.169e-14 at 50-digit "
        "precision, which would REJECT a correct limit. Arbitrary precision is "
        "load-bearing there, so that arm stays symbolic-internal.\n\n"
        "A KNOWN WEAKNESS OF THE limit ARM, stated plainly: its residual is the "
        "distance |f(probe) - L| at a FINITE probe, which is not a verification "
        "error but the function's genuine remaining distance from its limit. It "
        "therefore only closes for limits that converge quadratically or "
        "faster: sin(x)/x verifies (residual 1.7e-13) while (exp(x)-1)/x and "
        "atan(x) as x -> oo are REJECTED as verification_failed at ~5e-07 and "
        "~1e-06 despite SymPy being exactly right. This fails CLOSED — it "
        "withholds correct answers rather than certifying wrong ones — but a "
        "limit reported as verification_failed may mean the arm is too weak to "
        "confirm it, not that the answer is wrong.\n\n"
        "THE CENTRAL LIMIT — what is NOT validated. The result is trustworthy "
        "as a statement about THE EXPRESSION AS TYPED, and about nothing else. "
        "Whether that expression models the question the caller actually meant "
        "is a SEPARATE claim this substrate cannot adjudicate: an exactly "
        "correct integral of sin(x) over [0, pi] is a worthless answer to a "
        "question about the MEAN value of sin(x), and sin(30) is exactly "
        "correct in radians while being the wrong model of a claim about "
        "degrees. Both cases return solved_verified with a true number.\n\n"
        "KNOWN GAP — assumptions and branch cuts. SymPy's default assumptions "
        "are COMPLEX: sqrt(x**2) does not simplify to x unless realness or "
        "positivity is declared, and log/sqrt carry branch cuts. The wrapper "
        f"validates that declared assumptions are in the allowlist "
        f"({', '.join(ALLOWED_ASSUMPTIONS)}) but CANNOT check that the "
        "declared set matches the caller's intent — that information exists "
        "nowhere the wrapper or the gate can read it.\n\n"
        "No internal diagnostic checks whether the expression models the "
        "intended question, or whether the assumption set is the intended one. "
        "The wrapper confirms only that the operation ran, produced a closed "
        "form, and that the closed form survived back-substitution."
    )
