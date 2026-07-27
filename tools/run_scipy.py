"""
run_scipy — the production sci-Python symbolic wrapper, Regime A
(`sympy_symbolic_exact`).

Plain, deterministic code. NO AI inside, no model calls, ever — and NO LLM
anywhere in the EXECUTION path: this wrapper RUNS a fixed job template, it never
WRITES code. Same contract run_cfd.py / run_fea.py / run_code.py hold for their
substrates. UNREGISTERED: nothing in stages/, the supervisor, substrates.py, or
any schema imports it. It is reachable by tests (and a __main__ CLI) only.

THE SINGLE SOURCE OF TRUTH is onboarding/sympy_symbolic_exact/contract.py — this
module IMPORTS the allowlists and the ruled constants from there and never
restates them. The card points at that file; the calibration slate is generated
from it.

TWO LAYERS, AND WHY BOTH EXIST
------------------------------
SymPy's own documentation says `parse_expr` uses `eval` and is UNSAFE on
unsanitized input. So:

  * LAYER 1 — the AST allowlist (`check_expression_ast`), HOST-SIDE, before any
    container starts. `ast.parse(..., mode='eval')` parses without executing;
    the tree is then walked and every node/name checked against the contract's
    allowlists. This is the TRIPWIRE: it rejects attribute access, subscripts,
    lambdas, comprehensions, f-strings, string constants, dunders, and any
    non-allowlisted function BY NAME.
  * LAYER 2 — the container jail. The expression only ever reaches `parse_expr`
    INSIDE an ephemeral `docker run --rm` container with `--network=none`, a
    memory cap, a read-only rootfs, a READ-ONLY workdir mount, a hard timeout,
    and a pids limit. Inside, `parse_expr` is called with a RESTRICTED
    global_dict/local_dict — SymPy's default global_dict is `from sympy import *`
    and MUST be overridden.

The allowlist is the tripwire; the JAIL is what holds. Layer 1 deliberately does
NOT bound literal magnitude: `10**10**100` is legal mathematics and MUST pass
layer 1. Containing it is layer 2's job — that is the whole point of escape E6.

MEASURED (this session, not assumed): `10**10**100` under a 256 MB cap does NOT
OOM — CPython grinds CPU-bound building the integer and ran >3 minutes without
tripping the memory cgroup. It is contained by the TIMEOUT. Both kills are
named; the wrapper does not care which fires, but the card records that the
observed containment path is the wall, not the cap.

MOUNTS (mirrors run_code's two-mount split, adapted so the WORKDIR is read-only):
    -v <job>:/job:ro    the runner + spec — READ-ONLY, and it is the workdir
    -v <out>:/out:rw    the ONLY writable bind mount; result.json lands here
A write anywhere under /job fails with Errno 30 (EROFS) — proven by escape E3.

Typed input (validated field-by-field; rejections are NAMED and machine-greppable):
    run_scipy({"operation": "integrate_definite",
               "expression": "x*sin(x)",
               "symbols": ["x"],
               "var": "x", "lower": "0", "upper": "pi"})

Return (and ONLY this leaves the wrapper — raw container output NEVER escapes):
    {"valid": bool, "state": str, "result": str|None, "residual": float|None,
     "crosscheck": dict|None, "reason": str|None,
     "diagnostics": str (<=800 chars), "runtime_s": float}
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable

# --- the single source of truth -------------------------------------------
# Loaded by full path under a UNIQUE PRIVATE module name (the ngspice
# precedent): a bare `contract` in sys.modules collides across substrates in
# one process — Python holds one module per name, first loader wins.
_CONTRACT_PATH = (Path(__file__).resolve().parent.parent / "onboarding" /
                  "sympy_symbolic_exact" / "contract.py")
_spec = importlib.util.spec_from_file_location("_sympy_contract", _CONTRACT_PATH)
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)

ALLOWED_ASSUMPTIONS = _contract.ALLOWED_ASSUMPTIONS
ALLOWED_CONSTANTS = _contract.ALLOWED_CONSTANTS
ALLOWED_FUNCTIONS = _contract.ALLOWED_FUNCTIONS
CROSSCHECK_AGREE_TOL = _contract.CROSSCHECK_AGREE_TOL
NUMERIC_DIFF_STEP = _contract.NUMERIC_DIFF_STEP
NUMERIC_PRECISION_DPS = _contract.NUMERIC_PRECISION_DPS
NUMERIC_SAMPLE_POINTS = _contract.NUMERIC_SAMPLE_POINTS
ODE_CROSSCHECK_ATOL = _contract.ODE_CROSSCHECK_ATOL
ODE_CROSSCHECK_RTOL = _contract.ODE_CROSSCHECK_RTOL
ODE_CROSSCHECK_SAMPLES = _contract.ODE_CROSSCHECK_SAMPLES
ODE_CROSSCHECK_SPAN = _contract.ODE_CROSSCHECK_SPAN
OP_FIELDS = _contract.OP_FIELDS
OPERATIONS = _contract.OPERATIONS
UNIVERSAL_OPTIONAL_FIELDS = _contract.UNIVERSAL_OPTIONAL_FIELDS
UNIVERSAL_REQUIRED_FIELDS = _contract.UNIVERSAL_REQUIRED_FIELDS
VERIFY_RESIDUAL_TOL = _contract.VERIFY_RESIDUAL_TOL

# ----------------------------------------------------------------------------
# Configuration — the only knobs, in one place (mirrors run_code.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"
IMAGE = "scipy-img:latest"
# Job scratch. MUST live under $HOME: the colima VM only mounts the user's home,
# so a /tmp path silently fails to mount (measured this session).
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_HOST = _PROJECT_ROOT / "cases_scipy"

DEFAULT_TIMEOUT_S = 600          # the FEA shape's hard wall; INJECTABLE per call
DEFAULT_MEM_MB = 256             # mirrors the code jail's cap
MAX_TIMEOUT_S = 600
PIDS_LIMIT = 256
TMPFS_MB = 64
MAX_DIAG_CHARS = 800             # the FEA shape's diagnostics bound
MAX_RETRIES = 1                  # ONE retry, on container-level failure only

# The three states — never collapsed.
STATE_SOLVED = "solved_verified"
STATE_UNEVALUATED = "unevaluated"
STATE_ERROR = "error"


class ScipyInputError(ValueError):
    """The typed input is not a runnable Regime-A job. Carries a NAMED reason."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# ============================================================================
# LAYER 1 — the AST allowlist. Host-side, before any container starts.
# ============================================================================

# Node types that are structurally legal in an allowlisted math expression.
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
    ast.USub, ast.UAdd,
    ast.Constant,
    ast.Name, ast.Load,
    ast.Call,
    ast.Tuple,          # grouping where an op needs it, e.g. Integral(f, (x, a, b))
)


def check_expression_ast(expression: str, declared: set[str]) -> None:
    """LAYER 1. Parse `expression` and walk it; raise ScipyInputError with a
    NAMED reason on anything not allowlisted. Parsing alone executes nothing.

    `declared` is the set of names legal as bare identifiers: the caller's
    declared symbols, plus (for dsolve) the function name.

    DELIBERATELY DOES NOT BOUND LITERAL MAGNITUDE. `10**10**100` is legal
    mathematics and passes here by design; containing it is layer 2's job.
    A magnitude bound here would be a fake safety property — it would make the
    jail look unnecessary while leaving every other resource bomb untouched.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ScipyInputError("parse_error", "expression must be a non-empty string")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ScipyInputError("parse_error", f"{e.msg}")

    legal_names = declared | set(ALLOWED_FUNCTIONS)

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ScipyInputError(
                f"ast_node_disallowed:{type(node).__name__}",
                f"{type(node).__name__} is not permitted in an expression",
            )
        if isinstance(node, ast.Constant):
            # Numeric constants only. Strings/bytes are how an eval escape
            # smuggles a payload, so they are refused as a node-class.
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float, complex)):
                raise ScipyInputError(
                    "ast_node_disallowed:Constant",
                    f"only numeric constants are permitted, got {type(node.value).__name__}",
                )
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id.endswith("__"):
                raise ScipyInputError("function_not_allowlisted", node.id)
            if node.id not in legal_names:
                # A name that is neither a declared symbol nor an allowlisted
                # function. SymPy would AUTO-CREATE a symbol for it (that is
                # exactly the typo trap), so this check is ours to make.
                raise ScipyInputError("undefined_symbol", node.id)
        elif isinstance(node, ast.Call):
            if node.keywords:
                raise ScipyInputError("ast_node_disallowed:keyword", "keyword arguments are not permitted")
            for a in node.args:
                if isinstance(a, ast.Starred):
                    raise ScipyInputError("ast_node_disallowed:Starred", "starred arguments are not permitted")
            if not isinstance(node.func, ast.Name):
                raise ScipyInputError(
                    f"ast_node_disallowed:{type(node.func).__name__}",
                    "a call target must be a plain allowlisted function name",
                )
            name = node.func.id
            if name.startswith("__") or name.endswith("__"):
                raise ScipyInputError("function_not_allowlisted", name)
            if name in ALLOWED_CONSTANTS:
                raise ScipyInputError("function_not_allowlisted", f"{name} is a constant, not callable")
            if name not in legal_names:
                raise ScipyInputError("function_not_allowlisted", name)


# ============================================================================
# (a) Typed-input validation. Rejections NAMED. Pure — no I/O, no container.
# ============================================================================

def _check_symbol_name(name: str) -> None:
    if not isinstance(name, str) or not name.isidentifier():
        raise ScipyInputError("undefined_symbol", f"{name!r} is not a valid identifier")
    if name.startswith("__") or name.endswith("__"):
        raise ScipyInputError("undefined_symbol", f"{name!r} is not a valid symbol name")


def validate_input(spec: dict) -> dict:
    """Deeply validate a Regime-A job spec. Returns a clean copy or raises
    ScipyInputError with a NAMED, machine-greppable reason."""
    if not isinstance(spec, dict):
        raise ScipyInputError("parse_error", f"spec must be a dict, got {type(spec).__name__}")

    # --- universal required fields ----------------------------------------
    for field in UNIVERSAL_REQUIRED_FIELDS:
        if field not in spec:
            raise ScipyInputError(f"missing_field:{field}", f"{field} is required")

    operation = spec["operation"]
    if operation not in OPERATIONS:
        raise ScipyInputError(f"op_not_allowlisted:{operation}",
                              f"allowed: {', '.join(OPERATIONS)}")

    # --- the exact legal field set for THIS operation ----------------------
    op_required = OP_FIELDS[operation]["required"]
    op_optional = OP_FIELDS[operation]["optional"]
    legal = set(UNIVERSAL_REQUIRED_FIELDS) | set(UNIVERSAL_OPTIONAL_FIELDS) \
        | set(op_required) | set(op_optional)
    for field in spec:
        if field not in legal:
            raise ScipyInputError(f"unknown_field:{field}",
                                  f"not a field of operation {operation}")
    for field in op_required:
        if field not in spec:
            raise ScipyInputError(f"missing_field:{field}",
                                  f"{field} is required for operation {operation}")

    # --- symbols ----------------------------------------------------------
    symbols = spec["symbols"]
    if not isinstance(symbols, list) or not symbols:
        raise ScipyInputError("missing_field:symbols", "symbols must be a non-empty list")
    for s in symbols:
        _check_symbol_name(s)
    declared = set(symbols)

    # --- assumptions (optional) -------------------------------------------
    assumptions = spec.get("assumptions", {})
    if not isinstance(assumptions, dict):
        raise ScipyInputError("assumption_not_allowlisted",
                              "assumptions must be a dict of symbol -> list of assumptions")
    clean_assumptions: dict[str, list[str]] = {}
    for sym, assums in assumptions.items():
        if sym not in declared:
            raise ScipyInputError("undefined_symbol",
                                  f"assumptions names {sym!r}, which is not in symbols")
        if not isinstance(assums, list):
            raise ScipyInputError("assumption_not_allowlisted",
                                  f"assumptions[{sym!r}] must be a list")
        for a in assums:
            if a not in ALLOWED_ASSUMPTIONS:
                raise ScipyInputError(f"assumption_not_allowlisted:{a}",
                                      f"allowed: {', '.join(ALLOWED_ASSUMPTIONS)}")
        clean_assumptions[sym] = list(assums)

    # --- dsolve's function name is a legal bare name inside the expression --
    func = spec.get("func")
    if operation == "dsolve":
        if not isinstance(func, str) or not func.isidentifier():
            raise ScipyInputError("missing_field:func", "func must be a function name")
        declared = declared | {func}

    # --- LAYER 1 on the expression ----------------------------------------
    expression = spec["expression"]
    check_expression_ast(expression, declared)

    # --- var must be a declared symbol ------------------------------------
    var = spec.get("var")
    if var is not None:
        _check_symbol_name(var)
        if var not in set(symbols):
            raise ScipyInputError("undefined_symbol", f"var {var!r} is not in symbols")

    # --- expression-valued fields go through LAYER 1 too -------------------
    clean: dict = {
        "operation": operation,
        "expression": expression,
        "symbols": list(symbols),
        "assumptions": clean_assumptions,
    }
    for field in ("lower", "upper", "point"):
        if field in spec:
            value = spec[field]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = repr(value)
            if not isinstance(value, str):
                raise ScipyInputError("parse_error",
                                      f"{field} must be a number or an expression string")
            check_expression_ast(value, declared)
            clean[field] = value
    if "order" in spec:
        order = spec["order"]
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise ScipyInputError("parse_error", f"order must be a positive integer, got {order!r}")
        clean["order"] = order
    if var is not None:
        clean["var"] = var
    if operation == "dsolve":
        clean["func"] = func
        # ics keys are EXPRESSIONS (e.g. "y(0)") and go through layer 1 exactly
        # like `expression` — an initial condition is untrusted input too.
        if "ics" in spec:
            ics = spec["ics"]
            if not isinstance(ics, dict) or not ics:
                raise ScipyInputError("parse_error", "ics must be a non-empty dict")
            clean_ics: dict[str, float] = {}
            for key, value in ics.items():
                check_expression_ast(key, declared)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ScipyInputError("parse_error",
                                          f"ics[{key!r}] must be a number, got {value!r}")
                clean_ics[key] = value
            clean["ics"] = clean_ics

    return clean


# ============================================================================
# The job runner template. FIXED bytes; the ONLY per-job variable is a block of
# validated JSON DATA (never code). Deterministic: same spec -> same runner.
# ============================================================================

_SPEC_TOKEN = "__SPEC_JSON__"

RUNNER_TEMPLATE = r'''"""AUTO-GENERATED sci-Python job runner (Regime A). Do not edit.

Generated by tools/run_scipy.py from a FIXED template. The ONLY per-job variable
is the SPEC block below: validated, allowlisted JSON DATA — never code. This
script runs INSIDE the no-network, read-only, memory-capped container and writes
exactly one artifact: /out/result.json.
"""
import json

import sympy
from sympy import Float, Integer, Rational, Symbol
from sympy.core.function import AppliedUndef
from sympy.parsing.sympy_parser import parse_expr, standard_transformations

SPEC = json.loads(r"""__SPEC_JSON__""")
RESULT = "/out/result.json"


class OperationDeclined(Exception):
    """SymPy DECLINED to perform the operation — the `unevaluated` state.

    Card ruling S4a (owner, 2026-07-16): a NotImplementedError raised BY THE
    OPERATION CALL is SymPy declining, not the wrapper failing. It is the same
    honest non-answer as an `Integral` surviving in the output; the only
    difference is that SymPy signals it by RAISING instead of by RETURNING.

    Card ruling S4b (owner, 2026-07-16) ADDS EXACTLY ONE TYPE: sympy.PoleError.
    S4a drew the decline line at the exception TYPE, and that line did not track
    the semantic one — `series(gamma(x), x, oo)` raises PoleError whose message
    reads "Asymptotic expansion of gamma around [oo] is not implemented", which
    is a decline in every sense except its class. PoleError is NOT a subclass of
    NotImplementedError (its MRO is PoleError -> Exception), so admitting it
    takes a second, equally strict TYPE test. It is emphatically NOT a widening
    by message text: matching on "is not implemented" in a string would be far
    worse than the narrow type test, because any exception could carry that text.

    THE DECLINE SET IS EXACTLY {NotImplementedError, PoleError} AND NOTHING
    WIDER, and only when raised by the operation call itself (`call_op`). A
    decline exception from a VERIFICATION arm is not a decline — the operation
    did answer, and an unverifiable answer is an error (S2), not a non-answer.
    Every other exception type keeps its named `error` reason.
    """


# The RULED decline set. A tuple, so the ruling is one greppable object rather
# than a condition spread across except clauses.
DECLINE_EXCEPTIONS = (NotImplementedError, sympy.PoleError)


def call_op(fn, *args, **kwargs):
    """Invoke the primary SymPy operation, mapping its declines to S4a/S4b.

    This wraps ONLY the operation call. Verification arms are deliberately
    outside it: the three-state discipline used to be enforced for RETURNS and
    not for RAISES (card watch 9), and this closes exactly that hole — no wider.
    """
    try:
        return fn(*args, **kwargs)
    except DECLINE_EXCEPTIONS as exc:
        raise OperationDeclined("%s: %s" % (type(exc).__name__, exc))

# The allowlisted math names, bound to real SymPy objects. This dict IS the
# restricted namespace: SymPy's default global_dict is `from sympy import *`,
# which would expose the entire library to the parser's eval.
_SYMPY_NAMES = {
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan, "cot": sympy.cot,
    "sec": sympy.sec, "csc": sympy.csc,
    "asin": sympy.asin, "acos": sympy.acos, "atan": sympy.atan, "atan2": sympy.atan2,
    "sinh": sympy.sinh, "cosh": sympy.cosh, "tanh": sympy.tanh,
    "asinh": sympy.asinh, "acosh": sympy.acosh, "atanh": sympy.atanh,
    "exp": sympy.exp, "log": sympy.log, "sqrt": sympy.sqrt, "Abs": sympy.Abs,
    "gamma": sympy.gamma, "erf": sympy.erf, "factorial": sympy.factorial,
    "Derivative": sympy.Derivative, "Integral": sympy.Integral,
    "Function": sympy.Function,
    "pi": sympy.pi, "E": sympy.E, "I": sympy.I,
    "oo": sympy.oo, "zoo": sympy.zoo, "nan": sympy.nan,
}


def write(payload):
    with open(RESULT, "w") as fh:
        json.dump(payload, fh)
    raise SystemExit(0)


def fail(kind, detail=""):
    write({"ok": False, "error_kind": kind, "error": str(detail)[:400]})


def build_namespace():
    """Declared symbols (with assumptions) + allowlisted functions. NOTHING else.

    Integer/Float/Rational/Symbol are REQUIRED here, not a leak: SymPy's standard
    transformations rewrite `2` into `Integer(2)` and bare names into `Symbol(...)`
    before eval, so those constructors must resolve. (Measured: an empty
    global_dict raises NameError: name 'Integer' is not defined.)
    """
    ns = {"Integer": Integer, "Float": Float, "Rational": Rational, "Symbol": Symbol}
    ns.update(_SYMPY_NAMES)
    for name in SPEC["symbols"]:
        flags = {a: True for a in SPEC["assumptions"].get(name, [])}
        ns[name] = Symbol(name, **flags)
    if SPEC["operation"] == "dsolve":
        ns[SPEC["func"]] = sympy.Function(SPEC["func"])
    return ns


def parse(text, ns):
    return parse_expr(text, local_dict=ns, global_dict=ns,
                      transformations=standard_transformations, evaluate=True)


def is_unevaluated(obj):
    """SymPy returned the operation without performing it."""
    try:
        return bool(obj.has(sympy.Integral, sympy.Derivative, sympy.Limit))
    except AttributeError:
        return False


def numeric_residual(diff_expr, var):
    """High-precision sampling fallback when simplify will not close to zero.

    SYMBOLIC-INTERNAL: this is .evalf(), SymPy's own evaluator. It is reached
    only by the two integrate ops, whose numeric fallback was deliberately left
    on evalf (the lambdify+numpy move covers diff/limit/series/solve). Card 5
    records that.
    """
    # `worst is None` UNTIL A POINT ACTUALLY EVALUATES. Starting at 0.0 and
    # `continue`-ing past every failure meant a run where ZERO points evaluated
    # returned residual 0.0 — indistinguishable from a perfect check, and the
    # caller reports it as solved_verified. complex() raises whenever the
    # residual still carries a free symbol, which is every legal multi-symbol
    # job whose residual simplify would not close, so this was reachable by
    # ordinary input rather than by anything exotic.
    #
    # The module's own words: "a check that cannot fail is not a proof". The two
    # sibling arms (diff_residual_numpy's `seen`, limit_residual_evalf's
    # `worst is None`) already guard this; the two integrate arms did not.
    worst = None
    for pt in SPEC["_sample_points"]:
        try:
            v = complex(diff_expr.subs(var, Float(pt)).evalf(SPEC["_dps"]))
        except (TypeError, ValueError, AttributeError):
            continue
        worst = abs(v) if worst is None else max(worst, abs(v))
    return worst


def symbolic_or_numeric_residual(diff_expr, var):
    """(residual, method). Symbolic zero first; numeric sampling as fallback."""
    simplified = sympy.simplify(diff_expr)
    if simplified == 0:
        return 0.0, "symbolic_simplify_to_zero"
    return numeric_residual(simplified, var), "numeric_sampling_evalf"


# --- the lambdify+numpy spot-check arm -------------------------------------
# PARTIAL independence, and the label is exact in both directions: the
# ARITHMETIC is numpy's (a genuinely different evaluator from .evalf()), but the
# TRANSLATION from the SymPy expression tree to a numpy callable is SymPy's own
# lambdify. A bug in lambdify's translation is therefore invisible to these
# checks, exactly as a bug in .evalf() was invisible to the checks they replace.
# The step gained is evaluation-independence; translation-independence remains
# unbuilt (card 8).

def lambdify_numpy(args, expr):
    """A numpy callable for `expr`, or None if SymPy cannot translate it."""
    try:
        return sympy.lambdify(args, expr, "numpy")
    except Exception:
        return None


def _num(f, *vals):
    """Evaluate a lambdified callable to a python complex."""
    return complex(f(*vals))


def _to_float(expr):
    """Convert a SYMBOLIC CONSTANT (a sample point, a limit value) to float.

    This is evalf on a NUMBER, never on the expression under test: the points
    are built exactly and then converted, while the EXPRESSION's evaluation at
    those points is numpy's. Keeping the two apart is what makes the
    'numeric-partial' label honest rather than decorative.
    """
    return float(expr.evalf(30))


def diff_residual_numpy(base, closed_form, var):
    """Central differences on numpy floats: (residual, method), or None.

    `base` is the (order-1)-th derivative, so one central difference of it is
    compared against the closed form of the order-th derivative.
    """
    fb = lambdify_numpy(var, base)
    fc = lambdify_numpy(var, closed_form)
    if fb is None or fc is None:
        return None
    h = SPEC["_diff_step"]
    worst, seen = 0.0, False
    for pt in SPEC["_sample_points"]:
        try:
            approx = (_num(fb, pt + h) - _num(fb, pt - h)) / (2 * h)
            exact = _num(fc, pt)
        except Exception:
            continue
        seen = True
        worst = max(worst, abs(approx - exact) / max(1.0, abs(exact)))
    if not seen:
        return None
    return worst, "numeric_central_difference_lambdify_numpy"


def diff_residual_evalf(base, closed_form, var):
    """The pre-existing evalf central difference. FALLBACK only — used when
    SymPy cannot lambdify the expression, and LABELLED so the card's
    independence claim is never overstated for a job that silently fell back."""
    h = Rational(1, 10 ** 6)
    # None until a point evaluates — same reasoning as numeric_residual above.
    # Zero points evaluating used to return 0.0, which the gate reads as a clean
    # pass; a check that ran on nothing must decline, not pass.
    worst = None
    for pt in SPEC["_sample_points"]:
        p = Float(pt)
        try:
            fd = (base.subs(var, p + h) - base.subs(var, p - h)) / (2 * h)
            approx = complex(fd.evalf(SPEC["_dps"]))
            exact = complex(closed_form.subs(var, p).evalf(SPEC["_dps"]))
        except (TypeError, ValueError, AttributeError):
            continue
        rel = abs(approx - exact) / max(1.0, abs(exact))
        worst = rel if worst is None else max(worst, rel)
    return worst, "numeric_central_difference_evalf_fallback"


def _approach_probes(pt, ks):
    """The probe points approaching `pt`, built EXACTLY (symbolically).

    An infinite point is approached from the correct SIDE: +oo probes with
    +10**k and -oo with -10**k. (The implementation this replaces used +10**k
    for either infinity — corrected here, disclosed in the debrief.)
    """
    out = []
    for k in ks:
        try:
            if pt.is_infinite:
                sign = -1 if pt.could_extract_minus_sign() else 1
                out.append(sign * Integer(10) ** k)
            else:
                out.append(pt + Rational(1, 10 ** k))
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def limit_residual_evalf(expr, closed_form, var, pt):
    """Approach sequence at ARBITRARY PRECISION: (residual, method), or None.

    SYMBOLIC-INTERNAL, AND DELIBERATELY LEFT SO — this is the one spot-check the
    lambdify+numpy move was tried on and MEASURED to make worse, so it stayed on
    evalf.

    Why, precisely: a limit spot-check evaluates an indeterminate form
    arbitrarily close to its singularity, which is exactly where catastrophic
    cancellation is the rule rather than the exception. Measured this session:
    (1 - cos(x))/x**2 probed at x=1e-6 loses ~11 of float64's ~16 digits to the
    1 - cos(x) subtraction, and the residual jumps from 4.169e-14 (evalf, 50 dps)
    to 4.445e-05 (float64) — four orders of magnitude OUTSIDE S2, rejecting a
    CORRECT limit. No probe distance rescues it: cancellation grows as the probe
    shrinks and truncation grows as it widens, and float64's best case for that
    expression is ~1e-8, still outside S2. Only arbitrary precision holds a 1e-9
    gate here, and the only arbitrary-precision evaluator available is SymPy's
    own evalf. Independence lost to correctness; the gap is recorded in the
    card's section 5 rather than papered over.
    """
    try:
        lim = complex(closed_form.evalf(SPEC["_dps"]))
    except (TypeError, ValueError, AttributeError):
        return None
    worst = None
    for probe in _approach_probes(pt, (3, 4, 5, 6)):
        try:
            v = complex(expr.subs(var, probe).evalf(SPEC["_dps"]))
        except (TypeError, ValueError, AttributeError):
            continue
        worst = abs(v - lim)          # the LAST (closest) probe wins
    if worst is None:
        return None
    return worst, "numeric_approach_sequence_evalf"


def series_residual_numpy(expr, truncated, var, pt):
    """Truncation comparison evaluated by numpy: (residual, method), or None.

    The probe points are built exactly and then converted; the EXPRESSION's
    evaluation at them is numpy's, which is what the numeric-partial label
    claims and all it claims.

    PROBE BAND, AND WHY IT MOVED (session 1c, fault-injection measured). This
    arm used to probe 1e-3/1e-4/1e-5 and let THE CLOSEST probe win, i.e. it
    reported the difference at 1e-5 — where a correct truncation and a WRONG one
    are both indistinguishable from zero. Measured: a series whose x**2
    coefficient had been DOUBLED scored 5.0e-11 and PASSED a 1e-9 gate; a
    doubled x**5 coefficient scored 0.0 and passed. A check reporting ~0 whether
    or not the answer is right is not a check.

    Two changes, both method detail — THE GATE SEMANTICS ARE UNCHANGED (the
    ruled S2 residual tolerance of 1e-9 is untouched; only where this arm looks
    has moved):
      * the band moves out one decade to 1e-2/1e-3/1e-4, and
      * the WORST probe wins, not the closest — a truncation difference GROWS
        with distance from the expansion point, so the closest probe is the
        least informative one. (Every other arm already reports its worst.)
    Measured after: the doubled-x**2 fault scores 5.0e-05 and is CAUGHT, while a
    correct exp(x) series at the same probe sits at ~1e-15.

    THE BLIND SPOT THAT REMAINS, characterized rather than papered over: a wrong
    coefficient on the HIGHEST RETAINED term is not detectable at any honest
    probe distance. Catching a doubled x**5 in exp(x)'s order-6 series needs
    h > 0.0413; not REJECTING a correct log(1+x) series needs h < 0.0426. That
    overlap is a factor of 1.02 — any h inside it is fitted to those two
    expressions, not a property of the method. The arm therefore discriminates
    low- and mid-order coefficient errors and is BLIND to top-order ones. Card
    watch 7 records this.
    """
    f = lambdify_numpy(var, expr)
    g = lambdify_numpy(var, truncated)
    if f is None or g is None:
        return None
    worst = None
    for p in _approach_probes(pt, (2, 3, 4)):
        try:
            probe = _to_float(p)
            a, b = _num(f, probe), _num(g, probe)
        except Exception:
            continue
        d = abs(a - b)
        worst = d if worst is None else max(worst, d)   # the WORST probe wins
    if worst is None:
        return None
    return worst, "numeric_truncation_comparison_lambdify_numpy"


# --- S2a: the residual must verify the RETURNED OBJECT ----------------------
# Owner ruling S2a (2026-07-16), closing card watch 13. Two arms verified a
# DIFFERENT OBJECT than the one they returned, and fault injection measured both:
# integrate_definite's residual came from a FRESHLY-COMPUTED antiderivative and
# never from `out`, so a job made to return 2*pi for an integral equal to pi
# measured residual 0.0 and reported solved_verified; dsolve's checkodesol
# verifies the EQUATION and not the declared ics, so doubling the solution of
# y'+2y=0 still "verified" while violating y(0)=3. Both are now checked against
# the returned object, and THE RESIDUAL REPORTED IS THE WORSE OF THE TWO CHECKS.
#
# These arms DECLINE rather than guess on shapes they cannot read (the pattern
# the solve_ivp arm already uses), and every decline is named in the reported
# method — a skipped check must never be indistinguishable from a passed one.

def worse(r1, m1, r2, m2):
    """The worse of two residuals, with a method naming BOTH checks.

    None is worse than any number: a check that could not close leaves the
    result unverified, and the host gate reads a null residual as
    verification_failed. So None propagates rather than being skipped over.

    NaN IS TREATED AS None, and this guard is load-bearing rather than
    defensive-by-habit: EVERY comparison with NaN is False, so a bare `r2 > r1`
    would silently pick r1 and DISCARD a check that produced NaN — a check
    that failed to produce a number would read exactly like a check that
    passed. Measured during this session's S2a work: a divergent integral
    returning `oo` drove the bounds arm to inf/inf = NaN and the max() quietly
    reported the other arm's 0.0. A check that cannot fail is not a proof, and
    a check that can be erased by NaN is the same thing wearing a number.
    """
    method = "%s+%s" % (m1, m2)
    if r1 is None or r2 is None or r1 != r1 or r2 != r2:   # x != x  <=>  x is NaN
        return None, method
    return (r2 if r2 > r1 else r1), method


def value_at_bound(anti, var, bound):
    """The antiderivative's value at `bound` — or None if no usable value.

    Substitution first; a LIMIT where substitution lands on nan/zoo/±oo, which
    is exactly what an improper bound or a removable singularity means (the
    antiderivative of exp(-x) at +oo has no substitution value but a perfectly
    good limit of 0). Returning None means THE CHECK DECLINES — never that the
    job failed.
    """
    for get in (lambda: anti.subs(var, bound), lambda: sympy.limit(anti, var, bound)):
        try:
            val = get()
        except Exception:
            continue
        if val is None:
            continue
        try:
            if val.has(sympy.nan, sympy.zoo) or val.is_finite is False:
                continue
            if val.has(sympy.Integral, sympy.Limit, sympy.Derivative):
                continue
        except AttributeError:
            continue
        return val
    return None


def bounds_residual(anti, out, var, lo, hi):
    """S2a for integrate_definite: does the RETURNED value equal the VERIFIED
    antiderivative evaluated across the bounds? (residual, method), or None when
    the check declines.

    This is the half the diff-back check cannot see. Differentiating `anti` back
    to the integrand proves `anti` is an antiderivative; it says NOTHING about
    whether `out` is F(hi) - F(lo). Only this check ties the returned number to
    the verified object.

    Scaled by max(1, |out|) — the house convention already used by the diff and
    solve arms — so a large-magnitude integral is not failed for float noise.

    DECLINES on a non-finite returned value (`oo`, `-oo`, `nan`, `zoo`). SymPy
    returns those for genuinely divergent integrals and is RIGHT to — the
    integral of sec(x)**2 over [0, pi] really does diverge — but `oo` is not a
    number this arm can difference against F(hi) - F(lo), and forcing one out of
    it yields NaN, not a verdict. Declining by name is the honest report; the
    divergent-result question is card watch 14, not this arm's to decide.
    """
    try:
        if out.has(sympy.nan, sympy.zoo) or out.is_finite is False:
            return None
    except AttributeError:
        return None
    hi_val = value_at_bound(anti, var, hi)
    lo_val = value_at_bound(anti, var, lo)
    if hi_val is None or lo_val is None:
        return None
    try:
        diff = sympy.simplify(out - (hi_val - lo_val))
    except Exception:
        return None
    if diff == 0:
        return 0.0, "returned_value_vs_antiderivative_at_bounds_symbolic"
    try:
        num = abs(complex(diff.evalf(SPEC["_dps"])))
    except (TypeError, ValueError, AttributeError):
        return None
    try:
        scale = max(1.0, abs(complex(out.evalf(SPEC["_dps"]))))
    except (TypeError, ValueError, AttributeError):
        scale = 1.0
    return num / scale, "returned_value_vs_antiderivative_at_bounds_numeric"


def ics_residual(sol, fn, var, ns):
    """S2a for dsolve: does the RETURNED solution satisfy the DECLARED ics?
    (residual, method), or None when the check does not apply.

    checkodesol verifies the EQUATION. The declared initial condition is a
    SECOND claim it never looks at, which is why doubling the solution of
    y'+2y=0 passed it while violating y(0)=3. Residual is |y(x0) - y0| relative
    to max(1, |y0|).

    No ics declared -> None, and behavior is unchanged: the general solution is
    equation-verified only, exactly as the card says.

    THE TWO FAILURE DIRECTIONS ARE DELIBERATELY DIFFERENT. A shape this arm
    cannot READ (a solution that is not an explicit y(x) = ..., a condition that
    is not a value at a point) DECLINES — failing there would withhold correct
    answers, the false-negative disease the limit arm already carries. A shape it
    CAN read but whose arithmetic will not close returns a null residual and
    FAILS CLOSED — there the check applies and could not confirm the answer.
    """
    ics_spec = SPEC.get("ics")
    if not ics_spec:
        return None
    if not (isinstance(sol, sympy.Eq) and sol.lhs == fn):
        return None
    worst = 0.0
    for key, y0 in ics_spec.items():
        try:
            kexpr = parse(key, ns)
        except Exception:
            return None
        if not (isinstance(kexpr, AppliedUndef) and len(kexpr.args) == 1):
            return None
        try:
            got = sympy.simplify(sol.rhs.subs(var, kexpr.args[0]) - sympy.sympify(y0))
        except Exception:
            return None, "ics_back_substitution_did_not_close"
        if got == 0:
            continue
        try:
            num = abs(complex(got.evalf(SPEC["_dps"])))
        except (TypeError, ValueError, AttributeError):
            return None, "ics_back_substitution_did_not_close"
        worst = max(worst, num / max(1.0, abs(float(y0))))
    return worst, "ics_back_substitution"


def crosscheck_definite(integrand, var, lo, hi, symbolic_value):
    """The RULED-IN independent arm: scipy.integrate.quad, DIAGNOSTIC ONLY.

    Regime B (scipy_numeric_quad) is QUEUED (owner ruling 2026-07-16). SciPy is
    NOT exposed as an operation; its number appears only here and may never be
    returned as a result.
    """
    from scipy.integrate import quad

    try:
        lo_f = float(lo.evalf(30))
        hi_f = float(hi.evalf(30))
    except (TypeError, ValueError):
        return {"attempted": False, "note": "non-finite or symbolic limits; quad not applicable"}
    f = sympy.lambdify(var, integrand, "math")
    try:
        quad_value, quad_abserr = quad(f, lo_f, hi_f)
    except Exception as exc:
        return {"attempted": False, "note": "quad failed: %s" % type(exc).__name__}
    try:
        sym_f = float(symbolic_value.evalf(30))
    except (TypeError, ValueError):
        return {"attempted": False, "note": "symbolic value is not a finite number"}
    return {
        "attempted": True,
        "arm": "scipy.integrate.quad",
        "symbolic_value": sym_f,
        "quad_value": float(quad_value),
        # NAMED an estimate on purpose: quad returns an error ESTIMATE, not a bound.
        "quad_abserr_estimate": float(quad_abserr),
        "delta": abs(sym_f - float(quad_value)),
    }


def crosscheck_ode(ode_expr, sol, fn, var, ns):
    """The dsolve INDEPENDENT arm: scipy.integrate.solve_ivp, DIAGNOSTIC ONLY.

    Independence, stated precisely. solve_ivp integrates the ODE numerically
    from the DECLARED initial condition using an explicit Runge-Kutta stepper
    that is scipy's, not SymPy's, and it never looks at the closed form — it
    re-derives the trajectory from y' alone, so agreement is a real check of
    SymPy's dsolve rather than SymPy re-reading its own answer. What it is NOT
    independent of: the right-hand side reaches scipy through sympy.lambdify,
    and the closed form is lambdified too, so a translation bug is invisible
    here exactly as it is to the numeric-partial arms (card 5 / 8).

    COVERAGE, honestly bounded: explicit FIRST-ORDER ODEs with a single
    value-at-a-point initial condition. Anything else returns attempted=False
    with a named note rather than a number — the arm never guesses.

    rtol/atol are error CONTROLS, NOT guaranteed bounds. Reported as
    max_relative_deviation over sampled points across a STATED interval; the
    host adds the agreement verdict against S6's tolerance.
    """
    from scipy.integrate import solve_ivp

    ics_spec = SPEC.get("ics")
    if not ics_spec:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "no initial condition declared; the solve_ivp arm needs one"}
    if len(ics_spec) != 1:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the solve_ivp arm covers a single initial condition only"}

    # --- put the ODE in explicit form y' = rhs ----------------------------
    try:
        solved = sympy.solve(ode_expr, sympy.Derivative(fn, var))
    except Exception as exc:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "could not solve for y': %s" % type(exc).__name__}
    if len(solved) != 1:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "not explicitly solvable for a single first-order y'"}

    ydum = Symbol("_y")
    rhs = solved[0].subs(fn, ydum)
    if rhs.has(sympy.Derivative) or rhs.atoms(AppliedUndef):
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "higher-order or implicit ODE; the arm covers explicit first-order only"}
    if rhs.free_symbols - {var, ydum}:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the right-hand side carries undetermined symbols"}

    # --- the initial condition: a value at a point ------------------------
    (ic_key, ic_value), = ics_spec.items()
    try:
        kexpr = parse(ic_key, ns)
    except Exception:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the initial condition did not parse"}
    if not (isinstance(kexpr, AppliedUndef) and len(kexpr.args) == 1):
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the arm covers a value-at-a-point initial condition only"}
    try:
        x0, y0 = _to_float(kexpr.args[0]), float(ic_value)
    except (TypeError, ValueError, AttributeError):
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the initial condition is not a single numeric point"}

    # --- the closed form must be an explicit y(x) = ... -------------------
    if not (isinstance(sol, sympy.Eq) and sol.lhs == fn):
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the symbolic solution is not an explicit y(x) = ... equation"}
    closed = sol.rhs
    if closed.free_symbols - {var}:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "the closed form carries undetermined constants"}

    f = lambdify_numpy((var, ydum), rhs)
    g = lambdify_numpy(var, closed)
    if f is None or g is None:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "SymPy could not translate the ODE to a numpy callable"}

    span, n = SPEC["_ode_span"], SPEC["_ode_samples"]
    ts = [x0 + span * (i + 1) / n for i in range(n)]
    try:
        num = solve_ivp(lambda t, y: [float(f(t, y[0]))], (x0, x0 + span), [y0],
                        t_eval=ts, rtol=SPEC["_ode_rtol"], atol=SPEC["_ode_atol"],
                        method="RK45")
    except Exception as exc:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "solve_ivp failed: %s" % type(exc).__name__}
    if not num.success:
        return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                "note": "solve_ivp did not converge: %s" % str(num.message)[:120]}

    worst, samples = 0.0, []
    for t, y_num in zip(num.t, num.y[0]):
        try:
            y_sym = _num(g, float(t)).real
        except Exception:
            return {"attempted": False, "arm": "scipy.integrate.solve_ivp",
                    "note": "the closed form did not evaluate numerically"}
        worst = max(worst, abs(float(y_num) - y_sym) / max(1.0, abs(y_sym)))
        samples.append({"x": float(t), "closed_form": y_sym, "solve_ivp": float(y_num)})

    return {
        "attempted": True,
        "arm": "scipy.integrate.solve_ivp (RK45)",
        "interval": [x0, x0 + span],
        "samples": samples,
        "max_relative_deviation": worst,
        # NAMED controls on purpose: rtol/atol steer the stepper, they do not bound it.
        "rtol_control": SPEC["_ode_rtol"],
        "atol_control": SPEC["_ode_atol"],
    }


def main():
    ns = build_namespace()
    op = SPEC["operation"]
    try:
        expr = parse(SPEC["expression"], ns)
    except Exception as exc:
        fail("parse_error", "%s: %s" % (type(exc).__name__, exc))

    var = ns.get(SPEC.get("var"))
    crosscheck = None

    try:
        if op == "integrate_indefinite":
            out = call_op(sympy.integrate, expr, var)
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the integral unevaluated"})
            residual, method = symbolic_or_numeric_residual(sympy.diff(out, var) - expr, var)

        elif op == "integrate_definite":
            lo = parse(SPEC["lower"], ns)
            hi = parse(SPEC["upper"], ns)
            out = call_op(sympy.integrate, expr, (var, lo, hi))
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the definite integral unevaluated"})
            # Verification: differentiate the antiderivative back (checks 1-2 are
            # SymPy-internal). If no antiderivative closes, fall back to SymPy's
            # OWN high-precision numeric integration (still SymPy-internal).
            anti = sympy.integrate(expr, var)
            if is_unevaluated(anti):
                # This path ALREADY compares the RETURNED value against an
                # independently computed reference, so it satisfies S2a as it
                # stands and needs no second arm.
                ref = sympy.Integral(expr, (var, lo, hi)).evalf(SPEC["_dps"])
                residual = abs(complex(out.evalf(SPEC["_dps"]) - ref))
                method = "numeric_reference_integration"
            else:
                residual, method = symbolic_or_numeric_residual(
                    sympy.diff(anti, var) - expr, var)
                # S2a: the check above verifies the ANTIDERIVATIVE. It cannot see
                # a wrong RETURNED value — that is card watch 13, measured. Tie
                # `out` to the verified antiderivative and report THE WORSE.
                got = bounds_residual(anti, out, var, lo, hi)
                if got is None:
                    method += "+returned_value_check_declined"
                else:
                    residual, method = worse(residual, method, got[0], got[1])
            crosscheck = crosscheck_definite(expr, var, lo, hi, out)

        elif op == "diff":
            order = SPEC.get("order", 1)
            out = call_op(sympy.diff, expr, var, order)
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the derivative unevaluated"})
            # NUMERIC-PARTIAL spot-check: central differences against the closed
            # form, evaluated by numpy through lambdify. A spot-check, not a
            # proof — and not independent of SymPy's translation.
            base = expr if order == 1 else sympy.diff(expr, var, order - 1)
            got = diff_residual_numpy(base, out, var)
            if got is None:
                got = diff_residual_evalf(base, out, var)
            residual, method = got

        elif op == "limit":
            pt = parse(SPEC["point"], ns)
            out = call_op(sympy.limit, expr, var, pt)
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the limit unevaluated"})
            # SYMBOLIC-INTERNAL, deliberately: the numpy move was measured to
            # reject correct limits (see limit_residual_evalf). Arbitrary
            # precision is load-bearing here, not a leftover.
            got = limit_residual_evalf(expr, out, var, pt)
            residual, method = got if got else (None, "numeric_approach_sequence_failed")

        elif op == "series":
            pt = parse(SPEC["point"], ns)
            order = SPEC.get("order", 6)
            out = call_op(sympy.series, expr, var, pt, order).removeO()
            # NUMERIC-PARTIAL spot-check: truncation comparison NEAR the point,
            # evaluated by numpy through lambdify.
            got = series_residual_numpy(expr, out, var, pt)
            residual, method = got if got else (None, "numeric_truncation_comparison_failed")

        elif op == "solve":
            roots = call_op(sympy.solve, expr, var, dict=False)
            if not roots:
                write({"ok": True, "state_hint": "unevaluated", "result": str(roots),
                       "note": "SymPy returned no roots"})
            out = roots
            # Verification: substitute each root back into the expression.
            # SYMBOLIC-INTERNAL where simplify closes to exactly zero; where it
            # will not, the expression is evaluated at the root by numpy through
            # lambdify (NUMERIC-PARTIAL). The method name records which ran, so a
            # job that fell back is never reported as an exact symbolic check.
            worst, numeric_used, f = 0.0, False, None
            for r in roots:
                val = sympy.simplify(expr.subs(var, r))
                if val == 0:
                    continue
                if f is None:
                    f = lambdify_numpy(var, expr)
                done = False
                if f is not None:
                    try:
                        worst = max(worst, abs(_num(f, complex(r.evalf(30)))))
                        numeric_used, done = True, True
                    except Exception:
                        done = False
                if not done:
                    try:
                        worst = max(worst, abs(complex(val.evalf(SPEC["_dps"]))))
                        numeric_used = True
                    except (TypeError, ValueError):
                        worst = float("inf")
            residual = worst
            method = ("root_back_substitution_lambdify_numpy" if numeric_used
                      else "root_back_substitution")

        elif op == "dsolve":
            fn = ns[SPEC["func"]](var)
            ics_spec = SPEC.get("ics")
            if ics_spec:
                ics = {parse(k, ns): v for k, v in ics_spec.items()}
                sol = call_op(sympy.dsolve, expr, fn, ics=ics)
            else:
                sol = call_op(sympy.dsolve, expr, fn)
            out = sol
            # The INDEPENDENT arm: re-integrate the ODE numerically from the
            # declared ics and compare to the closed form. Diagnostic only — it
            # is reported beside checkodesol's verdict and gates nothing.
            crosscheck = crosscheck_ode(expr, sol, fn, var, ns)
            check = sympy.checkodesol(expr, sol, func=fn)
            ok = check[0] if isinstance(check, tuple) else False
            if ok:
                residual, method = 0.0, "checkodesol"
            else:
                rem = check[1] if isinstance(check, tuple) else None
                try:
                    residual = abs(complex(sympy.simplify(rem).evalf(SPEC["_dps"])))
                except (TypeError, ValueError, AttributeError):
                    residual = None
                method = "checkodesol_numeric_fallback"
            # S2a: checkodesol verified the EQUATION. The declared ics is a
            # SECOND claim it never looks at (card watch 13, measured). Report
            # THE WORSE of the two. `None` = the arm declined (no ics, or a shape
            # it cannot read) and behavior is unchanged; `(None, method)` = the
            # arm applied and could not close, which fails closed through worse().
            got = ics_residual(sol, fn, var, ns)
            if got is not None:
                residual, method = worse(residual, method, got[0], got[1])
        else:
            fail("op_not_allowlisted:%s" % op)

    except SystemExit:
        raise
    except OperationDeclined as exc:
        # S4a/S4b (owner rulings, 2026-07-16). SymPy declined BY RAISING rather
        # than by returning an unperformed object. Same state, same honesty: no
        # result, no reason, and never an error. Must precede `except Exception`.
        # `exc` already carries the raising type's name, so the decline message
        # is summarized rather than reclassified.
        write({"ok": True, "state_hint": "unevaluated", "result": None,
               "declined": True,
               "note": "SymPy DECLINED the operation — %s" % str(exc)[:300]})
    except MemoryError:
        fail("container_killed:MemoryError", "the job exhausted memory inside the jail")
    except Exception as exc:
        fail("evaluation_error", "%s: %s" % (type(exc).__name__, exc))

    write({
        "ok": True,
        "state_hint": "solved",
        "result": str(out),
        "residual": (None if residual is None else float(residual)),
        "residual_method": method,
        "crosscheck": crosscheck,
    })


if __name__ == "__main__":
    main()
'''


def generate_runner(spec: dict) -> str:
    """Fill the fixed template with the validated spec's JSON. Deterministic."""
    clean = validate_input(spec)
    payload = dict(clean)
    payload["_sample_points"] = list(NUMERIC_SAMPLE_POINTS)
    payload["_dps"] = NUMERIC_PRECISION_DPS
    payload["_diff_step"] = NUMERIC_DIFF_STEP
    payload["_ode_span"] = ODE_CROSSCHECK_SPAN
    payload["_ode_samples"] = ODE_CROSSCHECK_SAMPLES
    payload["_ode_rtol"] = ODE_CROSSCHECK_RTOL
    payload["_ode_atol"] = ODE_CROSSCHECK_ATOL
    spec_json = json.dumps(payload, sort_keys=True)
    # Belt-and-suspenders against breaking out of the r"""...""" data block.
    if '"""' in spec_json or "\\" in spec_json:
        raise ScipyInputError("parse_error", "spec serialized to an unsafe form")
    return RUNNER_TEMPLATE.replace(_SPEC_TOKEN, spec_json)


# ============================================================================
# LAYER 2 — the container jail. One ephemeral, fully-jailed run.
# ============================================================================

class JailResult:
    """Small typed outcome of one jailed run — no raw log leaves here."""

    __slots__ = ("returncode", "timed_out", "oom_killed", "stderr_excerpt")

    def __init__(self, returncode, timed_out, oom_killed, stderr_excerpt):
        self.returncode = returncode
        self.timed_out = timed_out
        self.oom_killed = oom_killed
        self.stderr_excerpt = stderr_excerpt


def _excerpt(text: str, limit: int = MAX_DIAG_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "...(truncated)... " + text[-(limit - 20):]


def _docker(*args: str) -> list[str]:
    return ["docker", "--context", DOCKER_CONTEXT, *args]


def run_in_jail(job_dir: Path, out_dir: Path, timeout_s: int = DEFAULT_TIMEOUT_S,
                mem_mb: int = DEFAULT_MEM_MB) -> JailResult:
    """Run /job/runner.py inside ONE ephemeral, fully-jailed container.

    Every jail is a container-CREATION-time property, which is why each job gets
    its own container. `timeout_s` is INJECTABLE so tests exercise the real kill
    path in seconds instead of waiting out the 600 s default.

    On the wall the container is `docker kill`ed BY NAME. That explicit kill is
    load-bearing and not decoration: killing only the client leaves the container
    running (measured this session — a probe leaked a live container exactly
    that way). `--rm` then removes it, leaving nothing.
    """
    name = f"scipy_job_{uuid.uuid4().hex[:12]}"
    cmd = _docker(
        "run", "--rm", "--name", name,
        "--network=none",
        f"--memory={mem_mb}m", f"--memory-swap={mem_mb}m",
        f"--pids-limit={PIDS_LIMIT}",
        "--read-only",
        f"--tmpfs=/tmp:size={TMPFS_MB}m",
        "-e", "HOME=/tmp",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "OMP_NUM_THREADS=1",
        "-e", "OPENBLAS_NUM_THREADS=1",
        "-e", "MKL_NUM_THREADS=1",
        "-v", f"{job_dir}:/job:ro",     # the WORKDIR — read-only
        "-v", f"{out_dir}:/out:rw",     # the ONLY writable bind mount
        "--workdir", "/job",
        IMAGE,
        "python", "/job/runner.py",
    )
    timed_out = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        returncode, stderr = proc.returncode, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        returncode = -1
        stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr) or ""
        subprocess.run(_docker("kill", name), capture_output=True, text=True)

    oom_killed = (returncode == 137) and not timed_out
    try:
        (out_dir / "stderr.log").write_text(stderr or "")
    except OSError:
        pass
    return JailResult(returncode, timed_out, oom_killed, _excerpt(stderr))


# ============================================================================
# The public entry point — validate, generate, run, verify, summarize.
# ============================================================================

def _err(reason: str, diagnostics: str, started: float) -> dict:
    return {"valid": False, "state": STATE_ERROR, "result": None, "residual": None,
            "crosscheck": None, "reason": reason,
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - started, 3)}


def _annotate_crosscheck(crosscheck: "dict | None") -> tuple:
    """Add S6's RULED agreement verdict to an attempted cross-check. Returns
    (crosscheck, summary_note).

    Applied wherever an arm actually ran — INCLUDING the verification_failed
    path. The arms are diagnostic by S6 and gate nothing, but a job whose
    residual gate rejected it is exactly a job whose diagnostics a human is
    about to read, and `agrees` is the field the card tells that human to read.
    Leaving the verdict uncomputed there would have shipped the evidence without
    the reading of it.
    """
    if not crosscheck or not crosscheck.get("attempted"):
        return crosscheck, ""
    # Both independent arms report against S6's RULED tolerance; only the
    # deviation they measure differs.
    if "solve_ivp" in crosscheck.get("arm", ""):
        dev = crosscheck["max_relative_deviation"]
        crosscheck["agrees"] = bool(dev <= CROSSCHECK_AGREE_TOL)
        crosscheck["agree_tol"] = CROSSCHECK_AGREE_TOL
        crosscheck["note"] = ("solve_ivp re-integrates the ODE from the declared "
                              "initial condition without consulting the closed form "
                              "— an INDEPENDENT ALGORITHM, though the right-hand side "
                              "still reaches it through SymPy's lambdify. rtol/atol "
                              "are error CONTROLS, NOT A BOUND; agreement is evidence, "
                              "never proof. Diagnostic only — Regime B "
                              "(scipy_numeric_quad) is QUEUED.")
        return crosscheck, (f"; crosscheck solve_ivp max_rel_dev={dev:.3g} "
                            f"agrees={crosscheck['agrees']}")
    delta = crosscheck["delta"]
    scale = max(1.0, abs(crosscheck["symbolic_value"]))
    crosscheck["agrees"] = bool(delta / scale <= CROSSCHECK_AGREE_TOL)
    crosscheck["agree_tol"] = CROSSCHECK_AGREE_TOL
    crosscheck["note"] = ("quad_abserr_estimate is an ERROR ESTIMATE, NOT A BOUND; "
                          "agreement is evidence, never proof. Diagnostic only — "
                          "Regime B (scipy_numeric_quad) is QUEUED.")
    return crosscheck, (f"; crosscheck quad={crosscheck['quad_value']:.12g} "
                        f"delta={delta:.3g} agrees={crosscheck['agrees']}")


def run_scipy(spec: dict, timeout_s: int = DEFAULT_TIMEOUT_S,
              mem_mb: int = DEFAULT_MEM_MB,
              _fault_injection: "Callable[[str], str] | None" = None) -> dict:
    """Validate, run, and verify one Regime-A job. Returns the small dict
    documented at the top of this module — and nothing else leaves the wrapper.

    `timeout_s` is injectable (default 600 s, ceiling MAX_TIMEOUT_S) so tests
    never wait out the real limit.

    `_fault_injection` is a TEST-ONLY SEAM and is None on every production path.
    It receives the generated runner source and returns a mutated copy, which is
    how tests corrupt a verification arm's input and prove the arm CATCHES the
    corruption. It exists because of the standing doctrine that a check which
    cannot fail is not a proof: without a way to feed each arm a deliberately
    wrong result, "the residual gate works" would be an assertion rather than a
    measurement. The underscore prefix and this paragraph are the honesty:
    nothing but tests may pass it, and it changes no default behavior.
    """
    started = time.time()
    timeout_s = min(int(timeout_s), MAX_TIMEOUT_S)

    # --- layers 1 + typed validation, before any container ----------------
    try:
        clean = validate_input(spec)
        runner = generate_runner(spec)
    except ScipyInputError as e:
        return _err(e.reason, f"input rejected: {e}", started)

    if _fault_injection is not None:
        runner = _fault_injection(runner)

    # --- lay out job/ (ro) + out/ (rw) ------------------------------------
    job_id = f"job_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{uuid.uuid4().hex[:8]}"
    root = RUNS_HOST / job_id
    job_dir, out_dir = root / "job", root / "out"
    job_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "runner.py").write_text(runner)
    (job_dir / "spec.json").write_text(json.dumps(clean, indent=2, sort_keys=True))
    result_path = out_dir / "result.json"

    # --- run, with ONE retry on a CONTAINER-LEVEL failure only ------------
    jail = None
    for attempt in range(MAX_RETRIES + 1):
        if result_path.exists():
            result_path.unlink()          # a retry can never read a stale result
        jail = run_in_jail(job_dir, out_dir, timeout_s=timeout_s, mem_mb=mem_mb)
        if jail.timed_out or jail.oom_killed:
            break                         # a jail trip is a RESULT, never retried
        if result_path.is_file():
            break
        if attempt < MAX_RETRIES:
            continue                      # container-level failure: retry once

    if jail.timed_out:
        return _err("timeout",
                    f"job exceeded the {timeout_s}s timeout and the container was killed",
                    started)
    if jail.oom_killed:
        return _err("container_killed:oom",
                    f"job exceeded the {mem_mb}MB memory cap and was OOM-killed (exit 137)",
                    started)
    if not result_path.is_file():
        return _err(f"container_killed:exit_{jail.returncode}",
                    f"job produced no result.json (exit {jail.returncode}). "
                    f"stderr: {jail.stderr_excerpt}", started)

    try:
        data = json.loads(result_path.read_text(errors="replace"))
    except json.JSONDecodeError as e:
        return _err("container_killed:unparseable_result",
                    f"job ran but result.json was unusable: {e}", started)

    if not data.get("ok"):
        kind = data.get("error_kind", "evaluation_error")
        return _err(kind, f"job reported failure: {data.get('error', 'unknown')}", started)

    runtime_s = round(time.time() - started, 3)

    # --- STATE 2: unevaluated — an honest non-answer, never an error -------
    # Two roads into this one state, and the diagnostics name which was taken:
    # SymPy RETURNED the operation unperformed, or (S4a) SymPy RAISED a
    # NotImplementedError from the operation call, i.e. declined by name.
    if data.get("state_hint") == "unevaluated":
        if data.get("declined"):
            # The note already carries the raising type's name, so the ruling is
            # cited generically: S4a admitted NotImplementedError, S4b added
            # PoleError, and the diagnostics must not miscite one as the other.
            diagnostics = (f"{clean['operation']}: {data.get('note', '')}. Per rulings "
                           f"S4a/S4b (owner, 2026-07-16) a decline raised by the "
                           f"operation call is a DECLINE, not a failure: the substrate "
                           f"worked correctly and this question has no closed-form "
                           f"answer here. An honest non-answer, not an error.")
        else:
            diagnostics = (f"{clean['operation']}: SymPy returned the operation "
                           f"unevaluated ({data.get('note', '')}); surviving form "
                           f"{data.get('result', '')!r}. This is an honest "
                           f"non-answer, not a failure.")
        return {"valid": True, "state": STATE_UNEVALUATED, "result": None,
                "residual": None, "crosscheck": None, "reason": None,
                "diagnostics": diagnostics[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s}

    # --- verification gate: no number leaves unverified --------------------
    residual = data.get("residual")
    method = data.get("residual_method", "unknown")
    crosscheck, cc_note = _annotate_crosscheck(data.get("crosscheck"))
    if residual is None or not (residual <= VERIFY_RESIDUAL_TOL):
        return {"valid": False, "state": STATE_ERROR, "result": None,
                "residual": residual, "crosscheck": crosscheck,
                "reason": "verification_failed",
                "diagnostics": (f"{clean['operation']}: SymPy returned a closed form but "
                                f"verification did not close — residual={residual} via "
                                f"{method}, tolerance={VERIFY_RESIDUAL_TOL:g} "
                                f"(RULED, owner 2026-07-16). A solved-but-unverified "
                                f"answer is an error; no number leaves unverified."
                                )[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s}

    # --- STATE 1: solved_verified -----------------------------------------
    return {"valid": True, "state": STATE_SOLVED, "result": data["result"],
            "residual": float(residual), "crosscheck": crosscheck, "reason": None,
            "diagnostics": (f"{clean['operation']} on {clean['expression']!r}: verified via "
                            f"{method}, residual={residual:.3g} <= "
                            f"{VERIFY_RESIDUAL_TOL:g}{cc_note}")[:MAX_DIAG_CHARS],
            "runtime_s": runtime_s}


# CLI:  venv/bin/python3 tools/run_scipy.py    (runs the canonical worked integral)
if __name__ == "__main__":
    default = {"operation": "integrate_definite", "expression": "x*sin(x)",
               "symbols": ["x"], "var": "x", "lower": "0", "upper": "pi"}
    print(json.dumps(run_scipy(default), indent=2))
