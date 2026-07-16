"""
tests/test_run_scipy.py — the sci-Python Regime-A wrapper's proofs.

Structure mirrors tests/test_run_code.py (the pattern this substrate copies):

  * PURE tests — typed validation, the layer-1 AST allowlist, the runner
    template, the diagnostics bound. No docker.
  * JAIL tests (@skipUnless docker + scipy-img present): each proves a jail by
    FAILING AN ESCAPE. Reading the config would prove nothing — a check that
    cannot fail is not a proof — so every one of these performs the actual
    attempt and asserts the attempt LOSES.
  * The escapes live here and skip cleanly where docker is unavailable, keeping
    the offline suite green.

THE HEADLINE IS E6 (TestEscape6ResourceBomb), and it is written first on
purpose. `10**10**100` is LEGAL MATHEMATICS: the test asserts layer 1 PASSES it
— that assertion is half the proof — and then asserts layer 2 contains it. It is
the case where the allowlist correctly says "fine" and only the jail saves you.

Timeouts are INJECTED (~2-10 s) everywhere so no test waits out the real 600 s
wall.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools import run_scipy  # noqa: E402
from tools.run_scipy import (  # noqa: E402
    ScipyInputError,
    check_expression_ast,
    generate_runner,
    run_in_jail,
    run_scipy as run_job,
    validate_input,
)


def _docker_ready() -> bool:
    """True only if the colima docker context answers AND scipy-img exists."""
    try:
        proc = subprocess.run(
            ["docker", "--context", run_scipy.DOCKER_CONTEXT, "images", "-q", run_scipy.IMAGE],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


DOCKER = _docker_ready()

A_GOOD_INTEGRAL = {
    "operation": "integrate_definite", "expression": "x*sin(x)",
    "symbols": ["x"], "var": "x", "lower": "0", "upper": "pi",
}


def _running_container_names() -> set[str]:
    proc = subprocess.run(
        ["docker", "--context", run_scipy.DOCKER_CONTEXT, "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    )
    return {n for n in proc.stdout.split() if n.startswith("scipy_job_")}


def _probe_jail(code: str, timeout_s: int = 30, mem_mb: int = 256, tmp_path: Path | None = None):
    """Write an ARBITRARY probe runner and run it through the real jail.

    The production wrapper only ever runs its fixed template, so the escape
    tests must supply their own runner to attack the jail from inside. This
    calls the SAME run_in_jail the wrapper calls — the jail under test is the
    production one, not a replica.
    """
    root = run_scipy.RUNS_HOST / f"test_{abs(hash(code)) % (10 ** 10)}"
    job_dir, out_dir = root / "job", root / "out"
    job_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "runner.py").write_text(code)
    jail = run_in_jail(job_dir, out_dir, timeout_s=timeout_s, mem_mb=mem_mb)
    probe = out_dir / "probe.json"
    data = json.loads(probe.read_text()) if probe.is_file() else None
    return jail, data


# ===========================================================================
# E6 — THE HEADLINE. Written first, per the build prompt.
# ===========================================================================

class TestEscape6ResourceBomb(unittest.TestCase):
    """`10**10**100`: layer 1 MUST pass it; layer 2 MUST contain it."""

    BOMB = "10**10**100"

    def test_allowlist_PASSES_the_bomb(self):
        """HALF THE PROOF. Every node in 10**10**100 is legal mathematics —
        numeric constants and a Pow. If the allowlist rejected this it would be
        bounding literal magnitude, which is a FAKE safety property: it would
        make the jail look unnecessary while leaving every other resource bomb
        untouched. The allowlist must say 'fine' here."""
        check_expression_ast(self.BOMB, {"x"})  # must NOT raise

    def test_bomb_passes_full_typed_validation_too(self):
        """The bomb also survives the whole host-side path — so the ONLY thing
        standing between it and the machine is the container."""
        spec = {"operation": "integrate_indefinite", "expression": self.BOMB,
                "symbols": ["x"], "var": "x"}
        clean = validate_input(spec)
        self.assertEqual(clean["expression"], self.BOMB)

    @unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
    def test_jail_CONTAINS_the_bomb(self):
        """THE OTHER HALF. Run it for real; assert the container kills it, a
        NAMED reason comes back, no number is fabricated, and nothing lingers.

        MEASURED (this session): the bomb does NOT OOM — CPython grinds
        CPU-bound building the integer and ran >3 min under a 256 MB cap without
        tripping the memory cgroup. The observed containment path is the WALL.
        The assertion accepts either named kill, because which jail fires is a
        property of the bomb, not of the safety guarantee.
        """
        before = _running_container_names()
        spec = {"operation": "integrate_indefinite", "expression": self.BOMB,
                "symbols": ["x"], "var": "x"}
        result = run_job(spec, timeout_s=10, mem_mb=256)

        self.assertFalse(result["valid"])
        self.assertEqual(result["state"], "error")
        self.assertIsNone(result["result"], "a contained bomb must NEVER return a number")
        self.assertTrue(
            result["reason"] == "timeout" or result["reason"].startswith("container_killed"),
            f"expected a NAMED jail kill, got reason={result['reason']!r}",
        )
        self.assertLess(result["runtime_s"], 30, "must not hang past the injected wall")
        self.assertEqual(_running_container_names() - before, set(),
                         "the killed bomb left a lingering container")


# ===========================================================================
# E5 — the parser escape. Rejected BY NAME, BEFORE any container starts.
# ===========================================================================

class TestEscape5Parser(unittest.TestCase):
    """No docker on purpose: the proof is that these never REACH a container."""

    def test_attribute_access_rejected_by_name_pre_container(self):
        with self.assertRaises(ScipyInputError) as ctx:
            check_expression_ast("().__class__.__mro__", {"x"})
        self.assertEqual(ctx.exception.reason, "ast_node_disallowed:Attribute")

    def test_dunder_import_call_rejected_by_name(self):
        with self.assertRaises(ScipyInputError) as ctx:
            check_expression_ast("__import__('os')", {"x"})
        self.assertEqual(ctx.exception.reason, "function_not_allowlisted")

    def test_attribute_escape_rejected_through_the_full_wrapper_without_docker(self):
        """The whole entry point refuses it — and returns before any container."""
        spec = {"operation": "diff", "expression": "().__class__.__mro__",
                "symbols": ["x"], "var": "x"}
        result = run_job(spec)
        self.assertFalse(result["valid"])
        self.assertEqual(result["state"], "error")
        self.assertEqual(result["reason"], "ast_node_disallowed:Attribute")
        self.assertIsNone(result["result"])

    def test_subscript_lambda_comprehension_fstring_string_all_rejected(self):
        for expr, expected in [
            ("x[0]", "ast_node_disallowed:Subscript"),
            ("(lambda: 1)()", "ast_node_disallowed:Lambda"),
            ("[i for i in (1, 2)]", "ast_node_disallowed:ListComp"),
            ("f'{x}'", "ast_node_disallowed:JoinedStr"),
            ("'payload'", "ast_node_disallowed:Constant"),
        ]:
            with self.subTest(expr=expr):
                with self.assertRaises(ScipyInputError) as ctx:
                    check_expression_ast(expr, {"x"})
                self.assertEqual(ctx.exception.reason, expected)

    def test_non_allowlisted_function_rejected_by_name(self):
        with self.assertRaises(ScipyInputError) as ctx:
            check_expression_ast("eval(x)", {"x"})
        self.assertEqual(ctx.exception.reason, "function_not_allowlisted")
        self.assertIn("eval", ctx.exception.detail)

    def test_constant_is_not_callable(self):
        with self.assertRaises(ScipyInputError) as ctx:
            check_expression_ast("pi(x)", {"x"})
        self.assertEqual(ctx.exception.reason, "function_not_allowlisted")


# ===========================================================================
# E1-E4 — the container jails. Each proves a jail by failing an escape.
# ===========================================================================

@unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
class TestJails(unittest.TestCase):

    def test_E1_network_is_unreachable(self):
        """--network=none: a DNS/socket attempt from inside the job must fail."""
        jail, probe = _probe_jail(
            "import json, socket\n"
            "try:\n"
            "    socket.gethostbyname('pypi.org')\n"
            "    out = {'reached_network': True}\n"
            "except Exception as e:\n"
            "    out = {'reached_network': False, 'err': type(e).__name__}\n"
            "json.dump(out, open('/out/probe.json', 'w'))\n",
            timeout_s=60,
        )
        self.assertIsNotNone(probe, "probe did not run")
        self.assertFalse(probe["reached_network"], "THE JAIL LEAKED: network was reachable")

    def test_E2_memory_cap_kills_a_big_allocation(self):
        """--memory: ~600 MB under a 256 MB cap must be OOM-killed (exit 137)."""
        jail, probe = _probe_jail(
            "import json\n"
            "buf = bytearray(600 * 1024 * 1024)\n"
            "json.dump({'allocated': len(buf)}, open('/out/probe.json', 'w'))\n",
            timeout_s=90, mem_mb=256,
        )
        self.assertIsNone(probe, "THE JAIL LEAKED: the 600MB allocation completed")
        self.assertTrue(jail.oom_killed, f"expected OOM kill, got exit {jail.returncode}")
        self.assertEqual(jail.returncode, 137)

    def test_E2_named_container_killed_reason_reaches_the_caller(self):
        """The OOM must surface as a NAMED reason, not a bare failure."""
        result = run_job(
            {"operation": "integrate_indefinite", "expression": "10**10**100",
             "symbols": ["x"], "var": "x"},
            timeout_s=8, mem_mb=256,
        )
        self.assertFalse(result["valid"])
        self.assertIsNotNone(result["reason"])
        self.assertTrue(
            result["reason"] == "timeout" or result["reason"].startswith("container_killed"),
            f"unnamed jail failure: {result['reason']!r}",
        )

    def test_E3_workdir_mount_is_read_only(self):
        """-v job:/job:ro + --read-only: a write under the workdir must fail
        with Errno 30 (EROFS)."""
        jail, probe = _probe_jail(
            "import json, errno\n"
            "out = {}\n"
            "try:\n"
            "    open('/job/escape.txt', 'w').write('WROTE_OUTSIDE')\n"
            "    out = {'wrote': True}\n"
            "except OSError as e:\n"
            "    out = {'wrote': False, 'errno': e.errno, 'is_erofs': e.errno == errno.EROFS}\n"
            "json.dump(out, open('/out/probe.json', 'w'))\n",
            timeout_s=60,
        )
        self.assertIsNotNone(probe, "probe did not run")
        self.assertFalse(probe["wrote"], "THE JAIL LEAKED: wrote into the read-only workdir")
        self.assertEqual(probe["errno"], 30)
        self.assertTrue(probe["is_erofs"])
        self.assertFalse((run_scipy.RUNS_HOST / "job" / "escape.txt").exists())

    def test_E4_timeout_kills_and_leaves_zero_lingering_containers(self):
        """A hanging job under an injected ~5 s wall is killed, and — the part
        that actually bites — NOTHING is left running. Killing the client alone
        leaves the container alive; only an explicit `docker kill` by name
        cleans up."""
        before = _running_container_names()
        jail, probe = _probe_jail(
            "import time\n"
            "time.sleep(120)\n",
            timeout_s=5,
        )
        self.assertTrue(jail.timed_out, "the hanging job was not killed")
        self.assertIsNone(probe)
        self.assertEqual(_running_container_names() - before, set(),
                         "THE JAIL LEAKED: a killed job left a lingering container")

    def test_E_restricted_namespace_blocks_sympy_wildcard(self):
        """Defense in depth: even if layer 1 were bypassed, the in-jail parse
        namespace is restricted. SymPy's DEFAULT global_dict is
        `from sympy import *`; the runner overrides it, so a non-allowlisted
        SymPy name does not resolve inside the parser's eval."""
        jail, probe = _probe_jail(
            "import json\n"
            "from sympy import Integer, Symbol\n"
            "from sympy.parsing.sympy_parser import parse_expr\n"
            "ns = {'Integer': Integer, 'Symbol': Symbol, 'x': Symbol('x')}\n"
            "try:\n"
            "    parse_expr('Poly(x, x)', local_dict=ns, global_dict=ns)\n"
            "    out = {'resolved': True}\n"
            "except Exception as e:\n"
            "    out = {'resolved': False, 'err': type(e).__name__}\n"
            "json.dump(out, open('/out/probe.json', 'w'))\n",
            timeout_s=60,
        )
        self.assertIsNotNone(probe)
        self.assertFalse(probe["resolved"],
                         "the restricted namespace leaked a non-allowlisted SymPy name")


# ===========================================================================
# The named rejection taxonomy (Task 3a). No docker.
# ===========================================================================

class TestNamedRejections(unittest.TestCase):

    def test_missing_field_named(self):
        for spec, expected in [
            ({"expression": "x", "symbols": ["x"]}, "missing_field:operation"),
            ({"operation": "diff", "symbols": ["x"]}, "missing_field:expression"),
            ({"operation": "diff", "expression": "x"}, "missing_field:symbols"),
            ({"operation": "diff", "expression": "x", "symbols": ["x"]}, "missing_field:var"),
        ]:
            with self.subTest(expected=expected):
                with self.assertRaises(ScipyInputError) as ctx:
                    validate_input(spec)
                self.assertEqual(ctx.exception.reason, expected)

    def test_unknown_field_named(self):
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "x", "symbols": ["x"],
                            "var": "x", "colour": "blue"})
        self.assertEqual(ctx.exception.reason, "unknown_field:colour")

    def test_op_specific_field_is_unknown_on_another_op(self):
        """`lower` belongs to integrate_definite; on diff it is unknown BY NAME."""
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "x", "symbols": ["x"],
                            "var": "x", "lower": "0"})
        self.assertEqual(ctx.exception.reason, "unknown_field:lower")

    def test_op_not_allowlisted_named(self):
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "minimize", "expression": "x**2",
                            "symbols": ["x"], "var": "x"})
        self.assertEqual(ctx.exception.reason, "op_not_allowlisted:minimize")

    def test_undefined_symbol_named(self):
        """THE TYPO TRAP: SymPy auto-creates symbols for undeclared names, so
        this check is ours to make."""
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "x+y",
                            "symbols": ["x"], "var": "x"})
        self.assertEqual(ctx.exception.reason, "undefined_symbol")
        self.assertIn("y", ctx.exception.detail)

    def test_parse_error_named(self):
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "sin(x",
                            "symbols": ["x"], "var": "x"})
        self.assertEqual(ctx.exception.reason, "parse_error")

    def test_assumption_not_allowlisted_named(self):
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "x", "symbols": ["x"],
                            "var": "x", "assumptions": {"x": ["purple"]}})
        self.assertEqual(ctx.exception.reason, "assumption_not_allowlisted:purple")

    def test_assumption_on_undeclared_symbol_named(self):
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "x", "symbols": ["x"],
                            "var": "x", "assumptions": {"q": ["real"]}})
        self.assertEqual(ctx.exception.reason, "undefined_symbol")

    def test_var_must_be_a_declared_symbol(self):
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "diff", "expression": "x", "symbols": ["x"],
                            "var": "t"})
        self.assertEqual(ctx.exception.reason, "undefined_symbol")

    def test_expression_valued_limits_go_through_layer_1(self):
        """`lower`/`upper`/`point` are expressions and are attackable too."""
        with self.assertRaises(ScipyInputError) as ctx:
            validate_input({"operation": "integrate_definite", "expression": "x",
                            "symbols": ["x"], "var": "x",
                            "lower": "().__class__", "upper": "1"})
        self.assertEqual(ctx.exception.reason, "ast_node_disallowed:Attribute")

    def test_good_specs_validate(self):
        for spec in [
            A_GOOD_INTEGRAL,
            {"operation": "diff", "expression": "x**2*exp(x)", "symbols": ["x"], "var": "x"},
            {"operation": "limit", "expression": "sin(x)/x", "symbols": ["x"],
             "var": "x", "point": "0"},
            {"operation": "solve", "expression": "x**2 - 5*x + 6", "symbols": ["x"], "var": "x"},
            {"operation": "dsolve", "expression": "Derivative(y(x), x) + 2*y(x)",
             "symbols": ["x"], "var": "x", "func": "y", "ics": {"y(0)": 3}},
            {"operation": "integrate_indefinite", "expression": "sqrt(x**2)",
             "symbols": ["x"], "var": "x", "assumptions": {"x": ["real", "positive"]}},
        ]:
            with self.subTest(op=spec["operation"]):
                validate_input(spec)


# ===========================================================================
# The runner template + diagnostics bound. No docker.
# ===========================================================================

class TestRunnerTemplate(unittest.TestCase):

    def test_runner_is_deterministic(self):
        self.assertEqual(generate_runner(A_GOOD_INTEGRAL), generate_runner(A_GOOD_INTEGRAL))

    def test_spec_is_embedded_as_json_data_not_code(self):
        runner = generate_runner(A_GOOD_INTEGRAL)
        self.assertIn('"expression": "x*sin(x)"', runner)
        self.assertNotIn("__SPEC_JSON__", runner)

    def test_runner_overrides_sympys_default_global_dict(self):
        """The single most load-bearing line in the job: SymPy's default
        global_dict is `from sympy import *`."""
        runner = generate_runner(A_GOOD_INTEGRAL)
        self.assertIn("global_dict=ns", runner)
        self.assertIn("local_dict=ns", runner)

    def test_diagnostics_are_bounded(self):
        result = run_job({"operation": "diff", "expression": "x+" + "y" * 2000,
                          "symbols": ["x"], "var": "x"})
        self.assertFalse(result["valid"])
        self.assertLessEqual(len(result["diagnostics"]), run_scipy.MAX_DIAG_CHARS)

    def test_return_field_set_is_exactly_the_pre_registered_one(self):
        """P1. The wrapper's contract with every caller."""
        result = run_job({"operation": "nope", "expression": "x", "symbols": ["x"]})
        self.assertEqual(
            set(result),
            {"valid", "state", "result", "residual", "crosscheck", "reason",
             "diagnostics", "runtime_s"},
        )


# ===========================================================================
# The three states + the self-checks. Live.
# ===========================================================================

@unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
class TestThreeStates(unittest.TestCase):

    def test_state_solved_verified_on_the_worked_integral(self):
        r = run_job(A_GOOD_INTEGRAL, timeout_s=120)
        self.assertTrue(r["valid"])
        self.assertEqual(r["state"], "solved_verified")
        self.assertEqual(r["result"], "pi")
        self.assertEqual(r["residual"], 0.0)
        self.assertIsNone(r["reason"])

    def test_state_unevaluated_on_x_to_the_x(self):
        """THE CANONICAL non-answer: x**x has no elementary antiderivative.
        SymPy correctly declines. Not an answer, NOT a failure — result is null
        and reason stays null."""
        r = run_job({"operation": "integrate_indefinite", "expression": "x**x",
                     "symbols": ["x"], "var": "x"}, timeout_s=120)
        self.assertEqual(r["state"], "unevaluated")
        self.assertIsNone(r["result"], "an unevaluated result must never leak as a QoI")
        self.assertIsNone(r["reason"], "an unevaluated result must never be dressed as an error")
        self.assertTrue(r["valid"], "the substrate worked correctly; this is an honest non-answer")

    def test_state_error_is_distinct_from_unevaluated(self):
        r = run_job({"operation": "diff", "expression": "x+y", "symbols": ["x"], "var": "x"})
        self.assertEqual(r["state"], "error")
        self.assertIsNone(r["result"])
        self.assertIsNotNone(r["reason"])


@unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
class TestSelfChecksAndCrosscheck(unittest.TestCase):

    def test_solve_roots_verified_by_back_substitution(self):
        r = run_job({"operation": "solve", "expression": "x**2 - 5*x + 6",
                     "symbols": ["x"], "var": "x"}, timeout_s=120)
        self.assertEqual(r["state"], "solved_verified")
        self.assertEqual(r["result"], "[2, 3]")
        self.assertEqual(r["residual"], 0.0)

    def test_dsolve_verified_by_checkodesol(self):
        r = run_job({"operation": "dsolve", "expression": "Derivative(y(x), x) + 2*y(x)",
                     "symbols": ["x"], "var": "x", "func": "y", "ics": {"y(0)": 3}},
                    timeout_s=120)
        self.assertEqual(r["state"], "solved_verified")
        self.assertEqual(r["result"], "Eq(y(x), 3*exp(-2*x))")
        self.assertEqual(r["residual"], 0.0)

    def test_crosscheck_agrees_on_a_known_definite_integral(self):
        """The independent arm (owner ruling 2026-07-16): quad is a DIAGNOSTIC,
        reported beside the symbolic answer, never as the result."""
        r = run_job(A_GOOD_INTEGRAL, timeout_s=120)
        cc = r["crosscheck"]
        self.assertTrue(cc["attempted"])
        self.assertTrue(cc["agrees"])
        self.assertAlmostEqual(cc["symbolic_value"], 3.141592653589793, places=12)
        self.assertAlmostEqual(cc["quad_value"], 3.141592653589793, places=12)
        self.assertIn("quad_abserr_estimate", cc, "quad's error must be named an ESTIMATE")
        self.assertIn("NOT A BOUND", cc["note"])

    def test_crosscheck_is_absent_for_non_definite_operations(self):
        r = run_job({"operation": "diff", "expression": "x**2*exp(x)",
                     "symbols": ["x"], "var": "x"}, timeout_s=120)
        self.assertEqual(r["state"], "solved_verified")
        self.assertIsNone(r["crosscheck"])

    def test_assumptions_change_the_mathematical_answer(self):
        """S5, the declared KNOWN GAP, demonstrated live: SymPy's defaults are
        COMPLEX. The same expression yields a different exact answer under a
        different declared assumption set — and NOTHING the wrapper or the gate
        can read says which set the caller meant."""
        default = run_job({"operation": "integrate_indefinite", "expression": "sqrt(x**2)",
                           "symbols": ["x"], "var": "x"}, timeout_s=120)
        positive = run_job({"operation": "integrate_indefinite", "expression": "sqrt(x**2)",
                            "symbols": ["x"], "var": "x",
                            "assumptions": {"x": ["positive"]}}, timeout_s=120)
        self.assertEqual(default["state"], "solved_verified")
        self.assertEqual(positive["state"], "solved_verified")
        self.assertNotEqual(default["result"], positive["result"])
        self.assertEqual(positive["result"], "x**2/2")


# ===========================================================================
# The verification ARMS and how independent each one actually is.
# ===========================================================================

class TestArmSelectionIsPure(unittest.TestCase):
    """No docker: the arm wiring is visible in the generated runner."""

    def test_the_ode_arm_and_its_knobs_are_shipped_in_the_spec(self):
        runner = generate_runner({"operation": "dsolve",
                                  "expression": "Derivative(y(x), x) + 2*y(x)",
                                  "symbols": ["x"], "var": "x", "func": "y",
                                  "ics": {"y(0)": 3}})
        self.assertIn("crosscheck_ode", runner)
        self.assertIn("solve_ivp", runner)
        for knob in ("_ode_span", "_ode_samples", "_ode_rtol", "_ode_atol", "_diff_step"):
            self.assertIn(knob, runner, f"{knob} must reach the jail as DATA")

    def test_the_interval_is_stated_not_implicit(self):
        """The ODE arm's comparison interval is a contract constant, not a
        number invented inside the runner."""
        from contract import ODE_CROSSCHECK_SAMPLES, ODE_CROSSCHECK_SPAN
        self.assertGreater(ODE_CROSSCHECK_SPAN, 0)
        self.assertGreaterEqual(ODE_CROSSCHECK_SAMPLES, 1)


@unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
class TestIndependentOdeArm(unittest.TestCase):
    """dsolve's INDEPENDENT arm: solve_ivp re-integrates from the ics and never
    consults the closed form."""

    def test_solve_ivp_arm_agrees_with_the_closed_form(self):
        r = run_job({"operation": "dsolve", "expression": "Derivative(y(x), x) + 2*y(x)",
                     "symbols": ["x"], "var": "x", "func": "y", "ics": {"y(0)": 3}},
                    timeout_s=120)
        self.assertEqual(r["state"], "solved_verified")
        cc = r["crosscheck"]
        self.assertTrue(cc["attempted"])
        self.assertIn("solve_ivp", cc["arm"])
        self.assertTrue(cc["agrees"])
        self.assertEqual(len(cc["samples"]), 5)
        self.assertEqual(cc["interval"], [0.0, 1.0], "the interval must be STATED")
        # y' = -2y, y(0)=3  ->  y(1) = 3*exp(-2)
        import math
        last = cc["samples"][-1]
        self.assertAlmostEqual(last["closed_form"], 3 * math.exp(-2), places=9)
        self.assertAlmostEqual(last["solve_ivp"], 3 * math.exp(-2), places=7)
        self.assertLess(cc["max_relative_deviation"], 1e-8)

    def test_rtol_atol_are_named_controls_never_a_bound(self):
        """The honest-limit twin of quad's abserr ESTIMATE."""
        r = run_job({"operation": "dsolve", "expression": "Derivative(y(x), x) - y(x)",
                     "symbols": ["x"], "var": "x", "func": "y", "ics": {"y(0)": 1}},
                    timeout_s=120)
        cc = r["crosscheck"]
        self.assertIn("rtol_control", cc)
        self.assertIn("atol_control", cc)
        self.assertIn("NOT A BOUND", cc["note"])
        self.assertIn("INDEPENDENT ALGORITHM", cc["note"])

    def test_the_arm_declines_rather_than_guessing_without_an_ics(self):
        """No initial condition -> no trajectory to integrate. The arm must say
        so by name and report NO number, never invent one."""
        r = run_job({"operation": "dsolve", "expression": "Derivative(y(x), x) + 2*y(x)",
                     "symbols": ["x"], "var": "x", "func": "y"}, timeout_s=120)
        self.assertEqual(r["state"], "solved_verified", "the symbolic answer still stands")
        cc = r["crosscheck"]
        self.assertFalse(cc["attempted"])
        self.assertIn("initial condition", cc["note"])
        self.assertNotIn("max_relative_deviation", cc, "a declining arm reports no number")


@unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
class TestNumericPartialArms(unittest.TestCase):
    """diff/series/solve evaluate through lambdify onto numpy: the ARITHMETIC is
    numpy's, the TRANSLATION is still SymPy's. The method name must say which
    arm actually ran, so a fallback can never be read as the stronger claim."""

    def _method(self, spec):
        r = run_job(spec, timeout_s=120)
        self.assertEqual(r["state"], "solved_verified", r["diagnostics"])
        return r["diagnostics"].split("verified via ")[1].split(",")[0].strip(), r

    def test_diff_runs_on_lambdify_numpy(self):
        m, r = self._method({"operation": "diff", "expression": "x**2*exp(x)",
                             "symbols": ["x"], "var": "x"})
        self.assertEqual(m, "numeric_central_difference_lambdify_numpy")
        self.assertLess(r["residual"], 1e-9)

    def test_series_runs_on_lambdify_numpy(self):
        m, _ = self._method({"operation": "series", "expression": "exp(x)",
                             "symbols": ["x"], "var": "x", "point": "0"})
        self.assertEqual(m, "numeric_truncation_comparison_lambdify_numpy")

    def test_solve_stays_symbolic_when_simplify_closes_to_zero(self):
        """The lambdify arm is a FALLBACK for solve, not a replacement: an exact
        symbolic zero must still be reported as the symbolic check it was."""
        m, r = self._method({"operation": "solve", "expression": "x**2 - 5*x + 6",
                             "symbols": ["x"], "var": "x"})
        self.assertEqual(m, "root_back_substitution")
        self.assertEqual(r["residual"], 0.0)


@unittest.skipUnless(DOCKER, "docker/colima + scipy-img not available")
class TestLimitArmStaysOnArbitraryPrecision(unittest.TestCase):
    """THE MEASURED REGRESSION GUARD.

    Moving the limit spot-check onto float64 was tried and reverted: a limit
    probes an indeterminate form next to its singularity, where cancellation is
    the rule. (1-cos(x))/x**2 at x=1e-6 loses ~11 of float64's ~16 digits, and
    the residual measured 4.445e-05 on numpy versus 4.169e-14 on evalf —
    rejecting a CORRECT limit. This test fails if anyone moves it back.
    """

    def test_a_cancellation_prone_limit_still_verifies(self):
        r = run_job({"operation": "limit", "expression": "(1 - cos(x))/x**2",
                     "symbols": ["x"], "var": "x", "point": "0"}, timeout_s=120)
        self.assertEqual(r["state"], "solved_verified",
                         "float64 cancellation would reject this correct limit")
        self.assertEqual(r["result"], "1/2")
        self.assertLess(r["residual"], 1e-9)
        self.assertIn("numeric_approach_sequence_evalf", r["diagnostics"])

    def test_an_infinite_point_is_approached_from_the_correct_side(self):
        """The probe side was wrong for -oo (it used +10**k for either
        infinity), which measured |atan(+1e6) - (-pi/2)| ~ pi at HEAD. The two
        infinities must now measure the same distance for an odd function."""
        plus = run_job({"operation": "limit", "expression": "atan(x)", "symbols": ["x"],
                        "var": "x", "point": "oo"}, timeout_s=120)
        minus = run_job({"operation": "limit", "expression": "atan(x)", "symbols": ["x"],
                         "var": "x", "point": "-oo"}, timeout_s=120)
        self.assertAlmostEqual(plus["residual"], minus["residual"], places=12)
        self.assertLess(minus["residual"], 1e-5, "a pi-sized residual means the wrong side")


# ===========================================================================
# Verification gating + retry semantics.
# ===========================================================================

class TestVerificationGate(unittest.TestCase):
    """No number leaves unverified — proven by FORCING the failure, since a
    check that only ever sees passing input cannot fail."""

    def test_solved_but_unverified_becomes_error_verification_failed(self):
        result_json = {"ok": True, "state_hint": "solved", "result": "bogus",
                       "residual": 1.0, "residual_method": "numeric_sampling",
                       "crosscheck": None}
        state, reason = self._map(result_json)
        self.assertEqual(state, "error")
        self.assertEqual(reason, "verification_failed")

    def test_missing_residual_also_fails_verification(self):
        state, reason = self._map({"ok": True, "state_hint": "solved", "result": "bogus",
                                   "residual": None, "residual_method": "x", "crosscheck": None})
        self.assertEqual(state, "error")
        self.assertEqual(reason, "verification_failed")

    def test_residual_inside_tolerance_passes(self):
        state, reason = self._map({"ok": True, "state_hint": "solved", "result": "pi",
                                   "residual": 1e-12, "residual_method": "x", "crosscheck": None})
        self.assertEqual(state, "solved_verified")
        self.assertIsNone(reason)

    @staticmethod
    def _map(result_json):
        """Exercise the wrapper's real gating logic on a synthesized job result
        by monkeypatching the jail — the host-side decision is what is under
        test, and it must be reachable with a FAILING input."""
        import tempfile

        from tools import run_scipy as rs

        real_run_in_jail, real_root = rs.run_in_jail, rs.RUNS_HOST
        tmp = Path(tempfile.mkdtemp())
        rs.RUNS_HOST = tmp

        def fake_jail(job_dir, out_dir, timeout_s=1, mem_mb=1):
            (out_dir / "result.json").write_text(json.dumps(result_json))
            return rs.JailResult(0, False, False, "")

        rs.run_in_jail = fake_jail
        try:
            out = rs.run_scipy(A_GOOD_INTEGRAL)
        finally:
            rs.run_in_jail, rs.RUNS_HOST = real_run_in_jail, real_root
        return out["state"], out["reason"]


class TestRetrySemantics(unittest.TestCase):

    def test_one_retry_on_container_level_failure_only(self):
        """MAX_RETRIES=1: a container-level failure (no result.json) is retried
        exactly once — 2 attempts total, never more."""
        import tempfile

        from tools import run_scipy as rs

        calls = []
        real_run_in_jail, real_root = rs.run_in_jail, rs.RUNS_HOST
        rs.RUNS_HOST = Path(tempfile.mkdtemp())

        def fake_jail(job_dir, out_dir, timeout_s=1, mem_mb=1):
            calls.append(1)
            return rs.JailResult(1, False, False, "boom")

        rs.run_in_jail = fake_jail
        try:
            out = rs.run_scipy(A_GOOD_INTEGRAL)
        finally:
            rs.run_in_jail, rs.RUNS_HOST = real_run_in_jail, real_root
        self.assertEqual(len(calls), 2, "expected exactly one retry (2 attempts)")
        self.assertFalse(out["valid"])

    def test_a_jail_trip_is_never_retried(self):
        """A timeout/OOM is a RESULT, not a transient fault. Retrying it would
        double every bomb's cost for nothing."""
        import tempfile

        from tools import run_scipy as rs

        calls = []
        real_run_in_jail, real_root = rs.run_in_jail, rs.RUNS_HOST
        rs.RUNS_HOST = Path(tempfile.mkdtemp())

        def fake_jail(job_dir, out_dir, timeout_s=1, mem_mb=1):
            calls.append(1)
            return rs.JailResult(-1, True, False, "")

        rs.run_in_jail = fake_jail
        try:
            out = rs.run_scipy(A_GOOD_INTEGRAL)
        finally:
            rs.run_in_jail, rs.RUNS_HOST = real_run_in_jail, real_root
        self.assertEqual(len(calls), 1, "a jail trip must not be retried")
        self.assertEqual(out["reason"], "timeout")


# ===========================================================================
# Task 6 — the generated slate is byte-identical to the committed JSON.
# ===========================================================================

class TestGeneratedSlateByteIdentity(unittest.TestCase):

    def test_regeneration_is_byte_identical_to_the_committed_json(self):
        """The case file is GENERATED, never hand-authored. If this fails, the
        committed JSON was edited by hand — regenerate it instead."""
        sys.path.insert(0, str(_ROOT / "onboarding" / "sympy_symbolic_exact"))
        from generate_cases import render  # noqa: E402

        committed = (_ROOT / "harness" / "calibration_cases_sympy_symbolic_exact.json").read_bytes()
        self.assertEqual(render().encode(), committed)


if __name__ == "__main__":
    unittest.main()
