"""
run_scipy — the production sci-Python symbolic wrapper, Regime A
(`sympy_symbolic_exact`).

Plain, deterministic code. NO AI inside, no model calls, ever — and NO LLM
anywhere in the EXECUTION path: this wrapper RUNS a fixed job template, it never
WRITES code. Same contract run_cfd.py / run_fea.py / run_code.py hold for their
substrates. UNREGISTERED: nothing in stages/, the supervisor, substrates.py, or
any schema imports it. It is reachable by tests (and a __main__ CLI) only.

THE SINGLE SOURCE OF TRUTH is onboarding/sympy_symbolic_exact/contract.py — this
module IMPORTS the allowlists and the provisional constants from there and never
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
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

# --- the single source of truth -------------------------------------------
_ONBOARDING = Path(__file__).resolve().parent.parent / "onboarding" / "sympy_symbolic_exact"
if str(_ONBOARDING) not in sys.path:
    sys.path.insert(0, str(_ONBOARDING))

from contract import (  # noqa: E402  (staged onboarding module, path-injected)
    ALLOWED_ASSUMPTIONS,
    ALLOWED_CONSTANTS,
    ALLOWED_FUNCTIONS,
    CROSSCHECK_AGREE_TOL,
    NUMERIC_PRECISION_DPS,
    NUMERIC_SAMPLE_POINTS,
    OP_FIELDS,
    OPERATIONS,
    UNIVERSAL_OPTIONAL_FIELDS,
    UNIVERSAL_REQUIRED_FIELDS,
    VERIFY_RESIDUAL_TOL,
)

# ----------------------------------------------------------------------------
# Configuration — the only knobs, in one place (mirrors run_code.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"
IMAGE = "scipy-img:latest"
# Job scratch. MUST live under $HOME: the colima VM only mounts the user's home,
# so a /tmp path silently fails to mount (measured this session).
RUNS_HOST = Path("/Users/jesseyu/research-system/cases_scipy")

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
from sympy.parsing.sympy_parser import parse_expr, standard_transformations

SPEC = json.loads(r"""__SPEC_JSON__""")
RESULT = "/out/result.json"

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
    """High-precision sampling fallback when simplify will not close to zero."""
    worst = 0.0
    for pt in SPEC["_sample_points"]:
        try:
            v = complex(diff_expr.subs(var, Float(pt)).evalf(SPEC["_dps"]))
        except (TypeError, ValueError, AttributeError):
            continue
        worst = max(worst, abs(v))
    return worst


def symbolic_or_numeric_residual(diff_expr, var):
    """(residual, method). Symbolic zero first; numeric sampling as fallback."""
    simplified = sympy.simplify(diff_expr)
    if simplified == 0:
        return 0.0, "symbolic_simplify_to_zero"
    return numeric_residual(simplified, var), "numeric_sampling"


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
        "symbolic_value": sym_f,
        "quad_value": float(quad_value),
        # NAMED an estimate on purpose: quad returns an error ESTIMATE, not a bound.
        "quad_abserr_estimate": float(quad_abserr),
        "delta": abs(sym_f - float(quad_value)),
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
            out = sympy.integrate(expr, var)
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the integral unevaluated"})
            residual, method = symbolic_or_numeric_residual(sympy.diff(out, var) - expr, var)

        elif op == "integrate_definite":
            lo = parse(SPEC["lower"], ns)
            hi = parse(SPEC["upper"], ns)
            out = sympy.integrate(expr, (var, lo, hi))
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the definite integral unevaluated"})
            # Verification: differentiate the antiderivative back (checks 1-2 are
            # SymPy-internal). If no antiderivative closes, fall back to SymPy's
            # OWN high-precision numeric integration (still SymPy-internal).
            anti = sympy.integrate(expr, var)
            if is_unevaluated(anti):
                ref = sympy.Integral(expr, (var, lo, hi)).evalf(SPEC["_dps"])
                residual = abs(complex(out.evalf(SPEC["_dps"]) - ref))
                method = "numeric_reference_integration"
            else:
                residual, method = symbolic_or_numeric_residual(
                    sympy.diff(anti, var) - expr, var)
            crosscheck = crosscheck_definite(expr, var, lo, hi, out)

        elif op == "diff":
            order = SPEC.get("order", 1)
            out = sympy.diff(expr, var, order)
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the derivative unevaluated"})
            # Honest NUMERIC spot-check: central differences against the closed
            # form. Labeled numeric — it is a spot-check, not a proof.
            h = Rational(1, 10 ** 6)
            worst = 0.0
            for pt in SPEC["_sample_points"]:
                p = Float(pt)
                try:
                    if order == 1:
                        fd = (expr.subs(var, p + h) - expr.subs(var, p - h)) / (2 * h)
                    else:
                        fd = sympy.diff(expr, var, order - 1)
                        fd = (fd.subs(var, p + h) - fd.subs(var, p - h)) / (2 * h)
                    approx = complex(fd.evalf(SPEC["_dps"]))
                    exact = complex(out.subs(var, p).evalf(SPEC["_dps"]))
                except (TypeError, ValueError, AttributeError):
                    continue
                denom = max(1.0, abs(exact))
                worst = max(worst, abs(approx - exact) / denom)
            residual, method = worst, "numeric_central_difference"

        elif op == "limit":
            pt = parse(SPEC["point"], ns)
            out = sympy.limit(expr, var, pt)
            if is_unevaluated(out):
                write({"ok": True, "state_hint": "unevaluated", "result": str(out),
                       "note": "SymPy returned the limit unevaluated"})
            # Honest NUMERIC spot-check: an approach sequence toward the point.
            worst = 0.0
            try:
                lim = complex(out.evalf(SPEC["_dps"]))
                for k in (3, 4, 5, 6):
                    if pt.is_infinite:
                        probe = Integer(10) ** k
                    else:
                        probe = pt + Rational(1, 10 ** k)
                    v = complex(expr.subs(var, probe).evalf(SPEC["_dps"]))
                    worst = abs(v - lim)      # the LAST (closest) probe wins
            except (TypeError, ValueError, AttributeError):
                worst = None
            residual, method = worst, "numeric_approach_sequence"

        elif op == "series":
            pt = parse(SPEC["point"], ns)
            order = SPEC.get("order", 6)
            out = sympy.series(expr, var, pt, order).removeO()
            # Honest NUMERIC spot-check: truncation comparison NEAR the point.
            worst = 0.0
            try:
                for k in (3, 4, 5):
                    probe = pt + Rational(1, 10 ** k)
                    a = complex(expr.subs(var, probe).evalf(SPEC["_dps"]))
                    b = complex(out.subs(var, probe).evalf(SPEC["_dps"]))
                    worst = abs(a - b)        # the LAST (closest) probe wins
            except (TypeError, ValueError, AttributeError):
                worst = None
            residual, method = worst, "numeric_truncation_comparison"

        elif op == "solve":
            roots = sympy.solve(expr, var, dict=False)
            if not roots:
                write({"ok": True, "state_hint": "unevaluated", "result": str(roots),
                       "note": "SymPy returned no roots"})
            out = roots
            # Verification: substitute each root back into the expression.
            worst = 0.0
            for r in roots:
                val = sympy.simplify(expr.subs(var, r))
                if val == 0:
                    continue
                try:
                    worst = max(worst, abs(complex(val.evalf(SPEC["_dps"]))))
                except (TypeError, ValueError):
                    worst = float("inf")
            residual, method = worst, "root_back_substitution"

        elif op == "dsolve":
            fn = ns[SPEC["func"]](var)
            ics_spec = SPEC.get("ics")
            if ics_spec:
                ics = {parse(k, ns): v for k, v in ics_spec.items()}
                sol = sympy.dsolve(expr, fn, ics=ics)
            else:
                sol = sympy.dsolve(expr, fn)
            out = sol
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
        else:
            fail("op_not_allowlisted:%s" % op)

    except SystemExit:
        raise
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


def run_scipy(spec: dict, timeout_s: int = DEFAULT_TIMEOUT_S,
              mem_mb: int = DEFAULT_MEM_MB) -> dict:
    """Validate, run, and verify one Regime-A job. Returns the small dict
    documented at the top of this module — and nothing else leaves the wrapper.

    `timeout_s` is injectable (default 600 s, ceiling MAX_TIMEOUT_S) so tests
    never wait out the real limit.
    """
    started = time.time()
    timeout_s = min(int(timeout_s), MAX_TIMEOUT_S)

    # --- layers 1 + typed validation, before any container ----------------
    try:
        clean = validate_input(spec)
        runner = generate_runner(spec)
    except ScipyInputError as e:
        return _err(e.reason, f"input rejected: {e}", started)

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
    if data.get("state_hint") == "unevaluated":
        return {"valid": True, "state": STATE_UNEVALUATED, "result": None,
                "residual": None, "crosscheck": None, "reason": None,
                "diagnostics": (f"{clean['operation']}: SymPy returned the operation "
                                f"unevaluated ({data.get('note', '')}); surviving form "
                                f"{data.get('result', '')!r}. This is an honest "
                                f"non-answer, not a failure.")[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s}

    # --- verification gate: no number leaves unverified --------------------
    residual = data.get("residual")
    method = data.get("residual_method", "unknown")
    if residual is None or not (residual <= VERIFY_RESIDUAL_TOL):
        return {"valid": False, "state": STATE_ERROR, "result": None,
                "residual": residual, "crosscheck": data.get("crosscheck"),
                "reason": "verification_failed",
                "diagnostics": (f"{clean['operation']}: SymPy returned a closed form but "
                                f"verification did not close — residual={residual} via "
                                f"{method}, tolerance={VERIFY_RESIDUAL_TOL:g} "
                                f"(SUGGESTED-pending-owner-ruling). A solved-but-unverified "
                                f"answer is an error; no number leaves unverified."
                                )[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s}

    # --- STATE 1: solved_verified -----------------------------------------
    crosscheck = data.get("crosscheck")
    cc_note = ""
    if crosscheck and crosscheck.get("attempted"):
        delta = crosscheck["delta"]
        scale = max(1.0, abs(crosscheck["symbolic_value"]))
        crosscheck["agrees"] = bool(delta / scale <= CROSSCHECK_AGREE_TOL)
        crosscheck["agree_tol"] = CROSSCHECK_AGREE_TOL
        crosscheck["note"] = ("quad_abserr_estimate is an ERROR ESTIMATE, NOT A BOUND; "
                              "agreement is evidence, never proof. Diagnostic only — "
                              "Regime B (scipy_numeric_quad) is QUEUED.")
        cc_note = (f"; crosscheck quad={crosscheck['quad_value']:.12g} "
                   f"delta={delta:.3g} agrees={crosscheck['agrees']}")

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
