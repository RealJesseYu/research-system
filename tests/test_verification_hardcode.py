"""
test_verification_hardcode.py — the hardcoded-constant tripwire in
stages/verification.py (2026-07-21).

WHY. verify_claim re-runs an artifact and accepts the claim if the number
reproduces. A number written straight into the source reproduces perfectly, so
reproduction alone passes a fabrication. hardcoded_metric_reason is the
model-free static tripwire that rejects a code metric which is only ever set to
a compile-time constant, while leaving genuinely computed metrics alone.

These tests exercise the pure AST classifier offline (no container). The live
integration — verify_claim returning reason 'hardcoded_constant' after a real
re-run — is proven separately against the container.

Run directly: venv/bin/python3 tests/test_verification_hardcode.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.verification import hardcoded_metric_reason  # noqa: E402


class Flagged(unittest.TestCase):
    """A bare constant metric — the fabrication a re-run cannot catch."""

    def test_subscript_literal(self):
        self.assertIsNotNone(
            hardcoded_metric_reason("metrics['auc'] = 0.99\n", "auc"))

    def test_dict_literal(self):
        self.assertIsNotNone(
            hardcoded_metric_reason("metrics = {'r2': 0.9}\n", "r2"))

    def test_integer_literal(self):
        self.assertIsNotNone(
            hardcoded_metric_reason("metrics['iters'] = 42\n", "iters"))

    def test_reason_names_the_metric(self):
        reason = hardcoded_metric_reason("metrics['auc'] = 0.99\n", "auc")
        self.assertIn("'auc'", reason)
        self.assertIn("not a measurement", reason)


class NotFlagged(unittest.TestCase):
    """Genuinely computed metrics, and honest tripwire limits, must pass."""

    def test_computed_via_call(self):
        code = ("import numpy as np\n"
                "metrics['m'] = float(np.mean(np.arange(6)))\n")
        self.assertIsNone(hardcoded_metric_reason(code, "m"))

    def test_computed_via_name(self):
        code = "result = expensive()\nmetrics['m'] = result\n"
        self.assertIsNone(hardcoded_metric_reason(code, "m"))

    def test_dict_literal_computed(self):
        code = ("from sklearn.model_selection import cross_val_score\n"
                "metrics = {'r2': float(cross_val_score(m, X, y).mean())}\n")
        self.assertIsNone(hardcoded_metric_reason(code, "r2"))

    def test_const_init_then_computed_is_benefit_of_doubt(self):
        # a const initialization followed by a real assignment must NOT flag
        code = "metrics['m'] = 0.0\nmetrics['m'] = compute()\n"
        self.assertIsNone(hardcoded_metric_reason(code, "m"))

    def test_augassign_counts_as_computed(self):
        code = "metrics['m'] = 0.0\nfor v in data:\n    metrics['m'] += step(v)\n"
        self.assertIsNone(hardcoded_metric_reason(code, "m"))

    def test_a_different_metric_is_not_examined(self):
        # 'other' is hardcoded but the claimed quantity 'm' is computed
        code = "metrics['other'] = 1.0\nmetrics['m'] = compute()\n"
        self.assertIsNone(hardcoded_metric_reason(code, "m"))

    def test_obfuscated_constant_is_an_honest_miss(self):
        # documented limit: a constant behind a call is NOT caught by the tripwire
        self.assertIsNone(
            hardcoded_metric_reason("metrics['m'] = float(0.99)\n", "m"))

    def test_unparseable_code_does_not_flag(self):
        self.assertIsNone(hardcoded_metric_reason("this is not python !!", "m"))

    def test_metric_never_assigned_does_not_flag(self):
        self.assertIsNone(hardcoded_metric_reason("x = 1\n", "m"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
