"""
test_run_ngspice.py — call-free tests for the ngspice linear-passive wrapper.

ZERO model calls, ZERO docker: the solver is either bypassed (pure functions:
the number parser, the regime screen, wrdata parsing, the marker scan, the
analytic formulas) or replaced by a stub that simulates ngspice by writing
frozen REAL fixtures. Every log fixture below is text ngspice-42 actually
printed in ngspice-prod (aarch64) — captured, not invented.

Run directly:  venv/bin/python3 -m pytest tests/test_run_ngspice.py
"""

from __future__ import annotations

import math
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_ngspice  # noqa: E402

BASE_SPEC = {
    "netlist_body": "V1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k",
    "analysis": {"type": "op"},
    "qoi": {"kind": "node_voltage", "target": "out",
            "reduction": "op_value", "at": None},
}

# --- frozen REAL prod log fixtures -----------------------------------------
# Captured verbatim from ngspice-42 in ngspice-prod. The floating-node log is
# the load-bearing one: note "Transient op finished successfully" and exit 0.
LOG_FLOATING = """
Circuit: * p-float (no dc path)

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using SPARSE 1.3 as Direct Linear Solver
Warning: singular matrix:  check node mid

Note: Starting dynamic gmin stepping
Warning: Dynamic gmin stepping failed
Note: Starting true gmin stepping
Warning: True gmin stepping failed
Note: Starting source stepping
Warning: source stepping failed
Note: Transient op started
Note: Transient op finished successfully

No. of Data Rows : 1
v(mid) = 5.000000e-01
"""

LOG_UNDEFMODEL = """
warning, can't find model 'nosuchmodel' from line
    d1 a 0 nosuchmodel

Circuit: * p-undefmodel

Error on line 3 or its substitute:
  d1 a 0 nosuchmodel
could not find a valid modelname
    Simulation interrupted due to error!
"""

LOG_GARBAGE = """
Circuit: * p-garbage

Error on line 4 or its substitute:
  5r xx yy zz
 unknown device type - error
    Simulation interrupted due to error!
"""

LOG_NOVECTOR = """
Circuit: * p-badvec

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

No. of Data Rows : 1
Error: no such vector nosuchnode
  in term: v(nosuchnode)
"""

LOG_CLEAN_OP = """
Circuit: * p-divider (.op)

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using SPARSE 1.3 as Direct Linear Solver

No. of Data Rows : 1
v(out) = 6.666667e+00
Note: Simulation executed from .control section
"""

# --- frozen REAL wrdata fixtures (measured shapes) -------------------------
WRDATA_OP = " 1.00000000e+01  6.66666667e+00 \n"
WRDATA_AC = (" 1.00000000e+01  9.99900010e-01 -9.99900367e-03 \n"
             " 1.25892541e+01  9.99841536e-01 -1.25872637e-02 \n"
             " 1.58489319e+01  9.99748874e-01 -1.58449575e-02 \n")
WRDATA_TRAN = (" 0.00000000e+00  0.00000000e+00 \n"
               " 1.00000000e-11  9.99999990e-11 \n"
               " 2.00000000e-11  2.99999996e-10 \n")


class TestSpiceNumberParser(unittest.TestCase):
    """Every expectation here was verified against ngspice-42 itself by driving
    the resistor under test with a 1 A source and reading back v(a) == R."""

    def test_m_is_milli_and_meg_is_mega(self):
        # The trap: `m` is milli, `meg` is 1e6, and both are case-insensitive.
        self.assertEqual(run_ngspice.parse_spice_number("1m"), 1e-3)
        self.assertEqual(run_ngspice.parse_spice_number("1M"), 1e-3)
        self.assertEqual(run_ngspice.parse_spice_number("1meg"), 1e6)
        self.assertEqual(run_ngspice.parse_spice_number("1MEG"), 1e6)
        self.assertEqual(run_ngspice.parse_spice_number("1Meg"), 1e6)
        # 1M is a MILLIohm, not a megohm — nine orders apart.
        self.assertNotEqual(run_ngspice.parse_spice_number("1M"),
                            run_ngspice.parse_spice_number("1MEG"))

    def test_mil_is_not_milli(self):
        # `mil` = 25.4e-6; a parser that checked `m` first would return 1e-3.
        self.assertAlmostEqual(run_ngspice.parse_spice_number("1mil"), 25.4e-6, places=12)

    def test_engineering_suffixes(self):
        for tok, want in (("1f", 1e-15), ("1p", 1e-12), ("1n", 1e-9), ("1u", 1e-6),
                          ("1k", 1e3), ("1K", 1e3), ("1g", 1e9), ("1t", 1e12)):
            self.assertEqual(run_ngspice.parse_spice_number(tok), want, msg=tok)

    def test_trailing_alpha_noise_is_ignored(self):
        self.assertEqual(run_ngspice.parse_spice_number("1kohm"), 1e3)
        self.assertEqual(run_ngspice.parse_spice_number("1x"), 1.0)   # unknown suffix

    def test_exponent_and_decimal_forms(self):
        self.assertEqual(run_ngspice.parse_spice_number("1e3"), 1e3)
        self.assertEqual(run_ngspice.parse_spice_number("2.5k"), 2.5e3)
        self.assertEqual(run_ngspice.parse_spice_number("-1k"), -1e3)
        self.assertEqual(run_ngspice.parse_spice_number(".5"), 0.5)

    def test_non_numbers_return_none(self):
        for tok in ("rmodel", "", "abc", None):
            self.assertIsNone(run_ngspice.parse_spice_number(tok), msg=repr(tok))


class TestRegimeScreen(unittest.TestCase):
    def test_clean_netlists_pass(self):
        for body in (
            "V1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k",
            "V1 in 0 DC 0 AC 1\nR1 in out 1k\nC1 out 0 159.155n",
            "V1 in 0 PULSE(0 1 0 1n 1n 1 2)\nR1 in n1 12.649\nL1 n1 out 1m\nC1 out 0 1u",
            "V1 in 0 DC 1\nR1 in out 1k\nE1 b 0 out 0 2.0\nR2 b 0 1k",
            "* a comment\nV1 in 0 DC 1 ; inline comment\nR1 in 0 1k",
        ):
            self.assertEqual(run_ngspice.screen_netlist(body), [], msg=body)

    def test_each_banned_element_letter_is_rejected_by_letter(self):
        # One representative per banned class; the reason must name the letter.
        for letter, line in (
            ("D", "D1 a 0 dmod"), ("Q", "Q1 c b e qmod"), ("M", "M1 d g s b mmod"),
            ("J", "J1 d g s jmod"), ("B", "B1 a 0 V=v(b)*2"), ("T", "T1 a 0 b 0 Z0=50"),
            ("O", "O1 a 0 b 0 omod"), ("S", "S1 a 0 b 0 smod"), ("W", "W1 a 0 vc wmod"),
            ("A", "A1 [a] [b] amod"), ("X", "X1 a b subckt"), ("K", "K1 L1 L2 0.5"),
            ("U", "U1 a b umod"), ("N", "N1 a b nmod"), ("P", "P1 a 0 b 0 pmod"),
        ):
            body = f"V1 a 0 DC 1\nR1 a 0 1k\n{line}"
            reasons = run_ngspice.screen_netlist(body)
            self.assertTrue(reasons, msg=f"{letter} escaped the screen")
            self.assertIn(f"element letter '{letter}", " ".join(reasons))

    def test_every_dot_line_is_rejected(self):
        for dot in (".model dmod D", ".subckt x a b", ".include /etc/passwd",
                    ".lib foo.lib", ".param x=1", ".ic v(a)=1", ".options gmin=1e-9",
                    ".tran 1u 1m", ".ac dec 10 1 1k", ".op"):
            reasons = run_ngspice.screen_netlist(f"V1 a 0 DC 1\nR1 a 0 1k\n{dot}")
            self.assertTrue(reasons, msg=f"{dot!r} escaped the screen")
            self.assertIn("dot-commands are owned by the wrapper", " ".join(reasons))

    def test_nonlinear_controlled_source_forms_rejected(self):
        for line in ("E1 b 0 POLY(1) a 0 0 1 1",
                     "G1 b 0 TABLE {v(a)} = (0,0) (1,1)",
                     "E1 b 0 value={v(a)*v(a)}",
                     "F1 b 0 poly(2) v1 v2 0 1 1"):
            reasons = run_ngspice.screen_netlist(f"V1 a 0 DC 1\n{line}\nR1 b 0 1k")
            self.assertTrue(reasons, msg=f"{line!r} escaped the screen")

    def test_brace_anywhere_is_rejected(self):
        reasons = run_ngspice.screen_netlist("V1 a 0 DC 1\nR1 a 0 {rval*2}")
        self.assertTrue(any("expression interpolation" in r for r in reasons))

    def test_node_named_table_is_not_a_false_positive(self):
        # 'table' as a NODE name must survive: the ban is word-boundary matched
        # on controlled-source lines, not a blind substring scan.
        self.assertEqual(run_ngspice.screen_netlist("V1 table 0 DC 1\nR1 table 0 1k"), [])

    def test_non_positive_passive_values_rejected(self):
        for line in ("R1 a 0 0", "R1 a 0 -1k", "C1 a 0 0", "L1 a 0 -1m"):
            reasons = run_ngspice.screen_netlist(f"V1 a 0 DC 1\n{line}")
            self.assertTrue(reasons, msg=f"{line!r} escaped the screen")
            self.assertIn("not positive", " ".join(reasons))

    def test_unparseable_passive_value_rejected(self):
        reasons = run_ngspice.screen_netlist("V1 a 0 DC 1\nR1 a 0 rmodel")
        self.assertTrue(any("cannot parse" in r for r in reasons))

    def test_passive_trailing_token_rejected(self):
        # MEASURED: `R1 in out 1k ac=100k` runs clean, exits 0, no marker, and
        # silently simulates 100k. Only arity catches it.
        for line in ("R1 a 0 1k ac=100k", "R1 a 0 1k tc1=0.001",
                     "C1 a 0 1u ic=3", "L1 a 0 1m m=2", "R1 a 0 rmodel w=1u"):
            reasons = run_ngspice.screen_netlist(f"V1 a 0 DC 1\n{line}")
            self.assertTrue(reasons, msg=f"{line!r} escaped the screen")

    def test_size_caps(self):
        long_body = "\n".join(["R1 a 0 1k"] * (run_ngspice.MAX_NETLIST_LINES + 1))
        self.assertTrue(any("over the" in r for r in run_ngspice.screen_netlist(long_body)))

    def test_empty_body_rejected(self):
        self.assertTrue(run_ngspice.screen_netlist("   "))

    def test_reasons_name_the_line_number(self):
        reasons = run_ngspice.screen_netlist("V1 a 0 DC 1\nR1 a 0 1k\nD1 a 0 dmod")
        self.assertIn("line 3", reasons[0])


class TestFieldValidation(unittest.TestCase):
    def test_missing_fields_named(self):
        for drop in ("netlist_body", "analysis", "qoi"):
            spec = {k: v for k, v in BASE_SPEC.items() if k != drop}
            with self.assertRaises(run_ngspice.NgspiceInputError) as cm:
                run_ngspice._validate_input(spec)
            self.assertIn(drop, str(cm.exception))

    def test_unsupported_field_named(self):
        with self.assertRaises(run_ngspice.NgspiceInputError) as cm:
            run_ngspice._validate_input({**BASE_SPEC, "mesh_density": 8})
        self.assertIn("mesh_density", str(cm.exception))

    def test_bad_analysis_type_rejected(self):
        with self.assertRaises(run_ngspice.NgspiceInputError):
            run_ngspice._validate_input({**BASE_SPEC, "analysis": {"type": "noise"}})

    def test_analysis_missing_subfield_named(self):
        with self.assertRaises(run_ngspice.NgspiceInputError) as cm:
            run_ngspice._validate_input(
                {**BASE_SPEC, "analysis": {"type": "tran", "tstep": 1e-6, "tstop": 1e-3}})
        self.assertIn("tmax", str(cm.exception))

    def test_bad_qoi_kind_and_reduction_rejected(self):
        with self.assertRaises(run_ngspice.NgspiceInputError):
            run_ngspice._validate_input(
                {**BASE_SPEC, "qoi": {**BASE_SPEC["qoi"], "kind": "branch_power"}})
        with self.assertRaises(run_ngspice.NgspiceInputError):
            run_ngspice._validate_input(
                {**BASE_SPEC, "qoi": {**BASE_SPEC["qoi"], "reduction": "integral"}})

    def test_value_at_requires_at(self):
        spec = {**BASE_SPEC,
                "analysis": {"type": "tran", "tstep": 1e-5, "tstop": 5e-3, "tmax": 1e-6},
                "qoi": {"kind": "node_voltage", "target": "out",
                        "reduction": "value_at", "at": None}}
        with self.assertRaises(run_ngspice.NgspiceInputError) as cm:
            run_ngspice._validate_input(spec)
        self.assertIn("'at'", str(cm.exception))

    def test_op_requires_op_value_reduction(self):
        with self.assertRaises(run_ngspice.NgspiceInputError):
            run_ngspice._validate_input(
                {**BASE_SPEC, "qoi": {**BASE_SPEC["qoi"], "reduction": "max", "at": None}})

    def test_corner_3db_is_ac_only(self):
        spec = {**BASE_SPEC,
                "analysis": {"type": "tran", "tstep": 1e-5, "tstop": 5e-3, "tmax": 1e-6},
                "qoi": {"kind": "node_voltage", "target": "out",
                        "reduction": "corner_3db", "at": None}}
        with self.assertRaises(run_ngspice.NgspiceInputError):
            run_ngspice._validate_input(spec)

    def test_target_name_is_locked_before_shell(self):
        # A shell metacharacter in a target must never reach a docker exec.
        with self.assertRaises(run_ngspice.NgspiceInputError):
            run_ngspice._validate_input(
                {**BASE_SPEC, "qoi": {**BASE_SPEC["qoi"], "target": "out; rm -rf /"}})


class TestDeckComposition(unittest.TestCase):
    def test_deck_is_deterministic(self):
        self.assertEqual(run_ngspice.compose_deck(BASE_SPEC, "/tmp/o.dat"),
                         run_ngspice.compose_deck(dict(BASE_SPEC), "/tmp/o.dat"))

    def test_wrapper_owns_the_dot_commands(self):
        deck = run_ngspice.compose_deck(BASE_SPEC, "/tmp/o.dat")
        for required in (".control", ".endc", ".end", "wrdata /tmp/o.dat v(out)", "quit"):
            self.assertIn(required, deck)

    def test_tran_emits_tmax_as_the_refinement_lever(self):
        spec = {**BASE_SPEC,
                "analysis": {"type": "tran", "tstep": 1e-5, "tstop": 5e-3, "tmax": 5e-7},
                "qoi": {"kind": "node_voltage", "target": "out",
                        "reduction": "final", "at": None}}
        self.assertIn("tran 1e-05 0.005 0 5e-07", run_ngspice.compose_deck(spec, "/tmp/o.dat"))

    def test_analysis_command_forms(self):
        self.assertEqual(run_ngspice.analysis_command({"type": "op"}), "op")
        self.assertEqual(
            run_ngspice.analysis_command(
                {"type": "ac", "variation": "dec", "n": 10, "fstart": 10.0, "fstop": 1e5}),
            "ac dec 10 10 100000")
        self.assertEqual(
            run_ngspice.analysis_command(
                {"type": "dc", "source": "V1", "start": 0.0, "stop": 10.0, "step": 1.0}),
            "dc V1 0 10 1")

    def test_qoi_vector_names(self):
        self.assertEqual(run_ngspice.qoi_vector({"kind": "node_voltage", "target": "out"}),
                         "v(out)")
        self.assertEqual(run_ngspice.qoi_vector({"kind": "vsource_current", "target": "V1"}),
                         "i(V1)")


class TestFailureMarkerScan(unittest.TestCase):
    def test_floating_node_log_is_caught_despite_exit_zero(self):
        # THE load-bearing case: this log accompanies exit 0 and a printed value.
        reason = run_ngspice.scan_failure_markers(LOG_FLOATING)
        self.assertIsNotNone(reason)
        self.assertIn("DC path", reason)

    def test_gmin_marker_matches_both_ngspice_variants(self):
        for variant in ("Warning: Dynamic gmin stepping failed",
                        "Warning: True gmin stepping failed"):
            self.assertIsNotNone(run_ngspice.scan_failure_markers(variant))

    def test_error_logs_are_caught(self):
        for log in (LOG_UNDEFMODEL, LOG_GARBAGE, LOG_NOVECTOR):
            self.assertIsNotNone(run_ngspice.scan_failure_markers(log))

    def test_clean_log_is_not_a_false_positive(self):
        self.assertIsNone(run_ngspice.scan_failure_markers(LOG_CLEAN_OP))

    def test_scan_is_case_insensitive(self):
        self.assertIsNotNone(run_ngspice.scan_failure_markers("SINGULAR MATRIX: check node x"))


class TestWrdataParsing(unittest.TestCase):
    def test_op_shape_takes_the_last_column_not_the_scale(self):
        rows = run_ngspice.parse_wrdata(WRDATA_OP)
        self.assertEqual(len(rows), 1)
        # The scale column is v(in)=10.0, an artifact; the value is 6.667.
        value = run_ngspice.reduce_qoi(
            rows, {"reduction": "op_value", "at": None}, "op")
        self.assertAlmostEqual(value, 6.66666667, places=8)

    def test_ac_shape_is_complex_re_im_and_magnitude_is_computed(self):
        rows = run_ngspice.parse_wrdata(WRDATA_AC)
        self.assertEqual(len(rows[0]), 3)
        value = run_ngspice.reduce_qoi(rows, {"reduction": "final", "at": None}, "ac")
        self.assertAlmostEqual(value, math.hypot(9.99748874e-01, -1.58449575e-02), places=12)

    def test_tran_shape_is_xy(self):
        rows = run_ngspice.parse_wrdata(WRDATA_TRAN)
        self.assertEqual(len(rows[0]), 2)
        self.assertAlmostEqual(
            run_ngspice.reduce_qoi(rows, {"reduction": "final", "at": None}, "tran"),
            2.99999996e-10, places=18)

    def test_empty_wrdata_raises_not_fabricates(self):
        for text in ("", "   \n\n"):
            with self.assertRaises(ValueError):
                run_ngspice.parse_wrdata(text)

    def test_unparseable_wrdata_raises(self):
        with self.assertRaises(ValueError):
            run_ngspice.parse_wrdata("1.0 not_a_number\n")

    def test_ragged_wrdata_raises(self):
        with self.assertRaises(ValueError):
            run_ngspice.parse_wrdata("1.0 2.0\n1.0 2.0 3.0\n")

    def test_reductions(self):
        rows = [[0.0, 1.0], [1.0, 5.0], [2.0, 3.0]]
        for red, want in (("final", 3.0), ("max", 5.0), ("min", 1.0)):
            self.assertEqual(
                run_ngspice.reduce_qoi(rows, {"reduction": red, "at": None}, "tran"), want)

    def test_value_at_interpolates_linearly(self):
        rows = [[0.0, 0.0], [2.0, 10.0]]
        self.assertAlmostEqual(
            run_ngspice.reduce_qoi(rows, {"reduction": "value_at", "at": 1.0}, "tran"),
            5.0, places=12)

    def test_value_at_outside_range_raises(self):
        rows = [[0.0, 0.0], [2.0, 10.0]]
        with self.assertRaises(ValueError):
            run_ngspice.reduce_qoi(rows, {"reduction": "value_at", "at": 99.0}, "tran")


class TestAnalyticFunctions(unittest.TestCase):
    """Each expectation is an INDEPENDENT closed form, written out here rather
    than re-calling the function under test."""

    def test_divider(self):
        # 10 V across 1k + 2k, tapped at 2k -> 10 * 2/3.
        self.assertAlmostEqual(run_ngspice.analytic_divider_vout(10.0, 1e3, 2e3),
                               20.0 / 3.0, places=12)
        # A symmetric divider halves its input.
        self.assertAlmostEqual(run_ngspice.analytic_divider_vout(5.0, 1e3, 1e3),
                               2.5, places=12)

    def test_rc_corner(self):
        # R=1k, C=159.155n is the textbook ~1 kHz corner.
        self.assertAlmostEqual(run_ngspice.analytic_rc_corner_hz(1e3, 159.155e-9),
                               1.0 / (2.0 * math.pi * 1e3 * 159.155e-9), places=9)
        self.assertAlmostEqual(run_ngspice.analytic_rc_corner_hz(1e3, 159.155e-9),
                               1000.0, delta=0.01)

    def test_rc_step_at_one_tau_is_63_2_percent(self):
        v = run_ngspice.analytic_rc_step_v(1e-3, 1.0, 1e3, 1e-6)
        self.assertAlmostEqual(v, 1.0 - 1.0 / math.e, places=12)
        self.assertAlmostEqual(v, 0.6321205588, places=9)

    def test_rc_step_starts_at_zero_and_saturates(self):
        self.assertAlmostEqual(run_ngspice.analytic_rc_step_v(0.0, 1.0, 1e3, 1e-6),
                               0.0, places=12)
        self.assertAlmostEqual(run_ngspice.analytic_rc_step_v(50e-3, 1.0, 1e3, 1e-6),
                               1.0, places=9)

    def test_rlc_zeta(self):
        # R=12.649, L=1m, C=1u -> zeta = (R/2)*sqrt(C/L) = 0.2
        self.assertAlmostEqual(run_ngspice.rlc_zeta(12.649, 1e-3, 1e-6), 0.2, places=5)

    def test_rlc_step_peak_matches_second_order_overshoot(self):
        zeta = 0.2
        expected = 1.0 * (1.0 + math.exp(-zeta * math.pi / math.sqrt(1 - zeta ** 2)))
        got = run_ngspice.analytic_rlc_step_peak(1.0, 12.649, 1e-3, 1e-6)
        self.assertAlmostEqual(got, expected, places=4)
        self.assertGreater(got, 1.0)          # an underdamped step MUST overshoot

    def test_rlc_step_peak_raises_when_overdamped(self):
        # zeta >= 1 has no overshoot peak; returning the settled value would be a
        # fabricated answer to a question that has none.
        self.assertGreaterEqual(run_ngspice.rlc_zeta(1000.0, 1e-3, 1e-6), 1.0)
        with self.assertRaises(ValueError):
            run_ngspice.analytic_rlc_step_peak(1.0, 1000.0, 1e-3, 1e-6)

    def test_analytics_reject_non_positive_components(self):
        with self.assertRaises(ValueError):
            run_ngspice.analytic_divider_vout(10.0, 0.0, 1e3)
        with self.assertRaises(ValueError):
            run_ngspice.analytic_rc_corner_hz(1e3, 0.0)


class TestAcCornerExtraction(unittest.TestCase):
    def test_corner_of_a_synthetic_one_pole_response(self):
        # Build an EXACT one-pole magnitude response and confirm the extractor
        # recovers its known corner from the fstart the sweep actually starts at.
        fc = 1000.0
        rows = []
        for i in range(401):
            f = 10 ** (-1 + i * 5 / 400)      # 0.1 Hz .. 10 kHz
            h = 1.0 / math.sqrt(1 + (f / fc) ** 2)
            rows.append([f, h, 0.0])
        self.assertAlmostEqual(run_ngspice.ac_corner_hz(rows), fc, delta=fc * 1e-3)

    def test_corner_raises_when_the_sweep_never_crosses(self):
        rows = [[f, 1.0, 0.0] for f in (1.0, 10.0, 100.0)]   # flat: never hits -3 dB
        with self.assertRaises(ValueError):
            run_ngspice.ac_corner_hz(rows)


class _StubNgspice:
    """Replaces run_ngspice._run_ngspice_cmd. Scripted per-attempt outcomes; on
    'ok' it writes frozen fixtures into the case dir like real ngspice would."""

    def __init__(self, outcomes, shared_host: Path, log=LOG_CLEAN_OP, wrdata=WRDATA_OP):
        self.outcomes = outcomes        # "ok" | "transient" | "timeout" | "marker" | "nodata"
        self.shared_host = shared_host
        self.log = log
        self.wrdata = wrdata
        self.calls = 0

    def __call__(self, job: str):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        job_dir = self.shared_host / job
        job_dir.mkdir(parents=True, exist_ok=True)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="ngspice", timeout=run_ngspice.TIMEOUT_SECONDS)
        if outcome == "ok":
            (job_dir / "ngspice.log").write_text(self.log)
            (job_dir / "out.dat").write_text(self.wrdata)
            return (0, "")
        if outcome == "marker":
            # The floating-node reality: exit 0, plausible value, broken circuit.
            (job_dir / "ngspice.log").write_text(LOG_FLOATING)
            (job_dir / "out.dat").write_text(" 1.0e+00  5.000000e-01 \n")
            return (0, "")
        if outcome == "nodata":
            (job_dir / "ngspice.log").write_text(LOG_NOVECTOR)
            return (0, "")
        return (1, "Error response from daemon: container is not running")


class TestExecutionPaths(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._orig_host = run_ngspice.SHARED_HOST
        self._orig_cmd = run_ngspice._run_ngspice_cmd
        self._orig_preflight = run_ngspice.preflight
        self._tmp = tempfile.TemporaryDirectory()
        run_ngspice.SHARED_HOST = Path(self._tmp.name)
        run_ngspice.preflight = lambda: None      # bypass docker entirely

    def tearDown(self):
        run_ngspice.SHARED_HOST = self._orig_host
        run_ngspice._run_ngspice_cmd = self._orig_cmd
        run_ngspice.preflight = self._orig_preflight
        self._tmp.cleanup()

    def test_clean_run_returns_the_qoi(self):
        run_ngspice._run_ngspice_cmd = _StubNgspice(["ok"], run_ngspice.SHARED_HOST)
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["qoi"], 6.66666667, places=8)

    def test_marker_hit_never_returns_a_qoi_even_on_exit_zero(self):
        # The proof case: ngspice will happily hand back 0.5 V here.
        stub = _StubNgspice(["marker"], run_ngspice.SHARED_HOST)
        run_ngspice._run_ngspice_cmd = stub
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["qoi"])
        self.assertIn("DC path", result["diagnostics"])

    def test_missing_wrdata_returns_no_number(self):
        run_ngspice._run_ngspice_cmd = _StubNgspice(["nodata"], run_ngspice.SHARED_HOST)
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["qoi"])

    def test_retry_once_then_succeeds(self):
        stub = _StubNgspice(["transient", "ok"], run_ngspice.SHARED_HOST)
        run_ngspice._run_ngspice_cmd = stub
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertTrue(result["valid"])
        self.assertEqual(stub.calls, 2)                 # retried exactly once

    def test_timeout_path_returns_invalid(self):
        stub = _StubNgspice(["timeout", "timeout"], run_ngspice.SHARED_HOST)
        run_ngspice._run_ngspice_cmd = stub
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["qoi"])
        self.assertIn("timeout", result["diagnostics"].lower())
        self.assertEqual(stub.calls, 2)                 # tried, then retried once

    def test_bad_input_returns_invalid_without_running(self):
        stub = _StubNgspice(["ok"], run_ngspice.SHARED_HOST)
        run_ngspice._run_ngspice_cmd = stub
        result = run_ngspice.run_ngspice({**BASE_SPEC, "netlist_body": "D1 a 0 dmod"})
        self.assertFalse(result["valid"])
        self.assertEqual(stub.calls, 0)                 # never reached the solver

    def test_return_shape_and_no_raw_log_leak(self):
        run_ngspice._run_ngspice_cmd = _StubNgspice(["ok"], run_ngspice.SHARED_HOST)
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertEqual(set(result), {"valid", "qoi", "diagnostics", "runtime_s"})
        blob = repr(result)
        for tell in ("Doing analysis at TEMP", "SPARSE 1.3", "No. of Data Rows"):
            self.assertNotIn(tell, blob)
        self.assertLessEqual(len(result["diagnostics"]), run_ngspice.MAX_DIAG_CHARS)

    def test_diagnostics_are_bounded_on_failure(self):
        stub = _StubNgspice(["ok"], run_ngspice.SHARED_HOST,
                            log=LOG_FLOATING + "x" * 50_000)
        run_ngspice._run_ngspice_cmd = stub
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertLessEqual(len(result["diagnostics"]), run_ngspice.MAX_DIAG_CHARS)

    def test_preflight_failure_is_reported_without_running(self):
        run_ngspice.preflight = lambda: "container 'ngspice-prod' is not running"
        stub = _StubNgspice(["ok"], run_ngspice.SHARED_HOST)
        run_ngspice._run_ngspice_cmd = stub
        result = run_ngspice.run_ngspice(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIn("not running", result["diagnostics"])
        self.assertEqual(stub.calls, 0)


class TestCornerFstartBiasNote(unittest.TestCase):
    """The per-run fstart-bias honesty note on corner_3db extractions.

    The bias is (fstart/corner)^2 relative and it DOMINATES grid density ~26x on
    the self-checked RC, so a caller reading a grid-refinement delta as the
    error bar understates it by that factor. These tests pin the arithmetic
    against the three points measured on ngspice-42 in ngspice-prod
    (onboarding/ngspice_linear_passive/selfcheck_evidence.json check c).
    """

    # MEASURED: fstart -> predicted (fstart/fc)^2, analytic corner 999.9996 Hz.
    MEASURED = [(10.0, 1.0000007151284615e-04),
                (1.0, 1.0000007151284616e-06),
                (0.1, 1.0000007151284618e-08)]

    def test_bias_matches_the_measured_predictions(self):
        for fstart, predicted in self.MEASURED:
            got = run_ngspice.corner_fstart_bias(fstart, 999.9996424359609)
            self.assertAlmostEqual(got, predicted, delta=predicted * 1e-6)

    def test_bias_is_the_square_of_the_ratio(self):
        self.assertAlmostEqual(run_ngspice.corner_fstart_bias(10.0, 1000.0), 1e-4)
        self.assertAlmostEqual(run_ngspice.corner_fstart_bias(100.0, 1000.0), 1e-2)

    def test_bias_refuses_a_nonpositive_corner_rather_than_inventing_one(self):
        for bad in (0.0, -1000.0):
            with self.assertRaises(ValueError):
                run_ngspice.corner_fstart_bias(10.0, bad)
        with self.assertRaises(ValueError):
            run_ngspice.corner_fstart_bias(0.0, 1000.0)

    def test_note_carries_the_number_the_decades_and_the_grid_warning(self):
        note = run_ngspice.corner_fstart_bias_note(1.0, 1000.0)
        self.assertIn("1.00e-06", note)
        self.assertIn("3.0 decades", note)
        self.assertIn("HIGH", note)
        self.assertIn("grid", note)

    def test_note_never_raises_on_a_degenerate_corner(self):
        # Diagnostics must never be what fails an otherwise good run.
        note = run_ngspice.corner_fstart_bias_note(10.0, 0.0)
        self.assertIn("not estimable", note)

    def test_corner_run_appends_the_note_to_diagnostics(self):
        # End-to-end through run_ngspice with the solver stubbed: an ac corner
        # run's diagnostics must carry the bias note; the QoI is unchanged.
        spec = {
            "netlist_body": "V1 in 0 AC 1\nR1 in out 1k\nC1 out 0 159.155n",
            "analysis": {"type": "ac", "variation": "dec", "n": 10,
                         "fstart": 10.0, "fstop": 100000.0},
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "corner_3db", "at": None},
        }
        result = _run_with_stub_ac(spec)
        self.assertTrue(result["valid"], result["diagnostics"])
        self.assertIn("corner_3db of v(out)", result["diagnostics"])
        self.assertIn("estimated fstart bias", result["diagnostics"])
        self.assertIn("HIGH", result["diagnostics"])

    def test_non_corner_run_does_not_get_the_note(self):
        # Additive means additive: a max/final/op_value run's diagnostics are
        # byte-for-byte what they were before this change.
        spec = {
            "netlist_body": "V1 in 0 AC 1\nR1 in out 1k\nC1 out 0 159.155n",
            "analysis": {"type": "ac", "variation": "dec", "n": 10,
                         "fstart": 10.0, "fstop": 100000.0},
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "max", "at": None},
        }
        result = _run_with_stub_ac(spec)
        self.assertTrue(result["valid"], result["diagnostics"])
        self.assertNotIn("fstart bias", result["diagnostics"])


def _run_with_stub_ac(spec: dict) -> dict:
    """Run one ac spec with the solver replaced by a stub writing a synthetic
    single-pole sweep. No docker, no model."""
    import math as _math

    original_cmd = run_ngspice._run_ngspice_cmd
    original_preflight = run_ngspice.preflight

    def stub(job: str):
        case_dir = run_ngspice.SHARED_HOST / job
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "ngspice.log").write_text("ngspice-42 stub: ac sweep ok\n")
        lines = []
        for i in range(41):  # 10 Hz -> 100 kHz, 10/decade
            f = 10.0 * (10 ** (i / 10.0))
            h = 1.0 / complex(1.0, f / 999.9996424359609)
            lines.append(f"{f:.10g}\t{h.real:.10g}\t{h.imag:.10g}")
        (case_dir / "out.dat").write_text("\n".join(lines) + "\n")
        return 0, ""

    run_ngspice._run_ngspice_cmd = stub
    run_ngspice.preflight = lambda: None
    try:
        return run_ngspice.run_ngspice(spec)
    finally:
        run_ngspice._run_ngspice_cmd = original_cmd
        run_ngspice.preflight = original_preflight


class TestMarkerScanLayerIsWhereTheFloatingNodeIsCaught(unittest.TestCase):
    """W01's ruling rests on a premise; this proves it.

    The calibration battery's wrapper track calls _validate_input only (no
    model, no container), so it structurally cannot reach a POST-SOLVE defense.
    The floating-node netlist is syntactically valid and the validator correctly
    accepts it — the marker scan is what catches it. That is why the slate's W01
    slot is the dot-line layer instead, and why the floating-node defense is
    proven HERE.
    """

    FLOATING = {
        "netlist_body": "V1 in 0 1.0\nC1 in mid 1u\nC2 mid out 1u",
        "analysis": {"type": "op"},
        "qoi": {"kind": "node_voltage", "target": "mid",
                "reduction": "op_value", "at": None},
    }

    def test_validator_accepts_the_floating_node_netlist(self):
        # NOT a bug: no pre-solve screen can know the DC-path topology, and
        # pretending otherwise is what the battery slate would have encoded.
        cleaned = run_ngspice._validate_input(self.FLOATING)
        self.assertEqual(cleaned["qoi"]["target"], "mid")

    def test_marker_scan_catches_the_singular_matrix_ngspice_exits_0_on(self):
        # The REAL ngspice-42 text: it fails the OP solve, falls through gmin
        # and source stepping, prints a plausible voltage, and exits 0.
        log = ("Warning: singular matrix:  check node mid\n"
               "Warning: Dynamic gmin stepping failed\n"
               "Warning: source stepping failed\n")
        reason = run_ngspice.scan_failure_markers(log)
        self.assertTrue(reason, "the marker scan must not pass a singular matrix")
        self.assertIn("singular matrix", reason)

    def test_a_clean_log_is_not_flagged(self):
        # The escape: if the scan flagged everything it would be no proof at all.
        self.assertFalse(run_ngspice.scan_failure_markers("ngspice-42 op ok\n"))


class TestDocsIndex(unittest.TestCase):
    def test_search_ngspice_docs_finds_transient_analysis(self):
        if not run_ngspice.NGSPICE_DOCS_INDEX.exists():
            self.skipTest("ngspice_docs index not built")
        hits = run_ngspice.search_ngspice_docs("transient analysis maximum timestep", top_k=3)
        self.assertTrue(hits)
        self.assertTrue(all("ngspice" in h["title"] for h in hits))
        self.assertTrue(all(0.0 < h["score"] <= 1.0 for h in hits))


if __name__ == "__main__":
    unittest.main()
