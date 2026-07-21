"""
test_python_experiment_substrate.py — the code-execution instrument (owner-ruled
2026-07-21, "unblock everything").

WHAT THIS PROVES. python_experiment is a fully-wired, routable, mature instrument:
a complete code spec validates and routes UNIQUELY to it; its open-scalar QoI
admits any non-empty metric name (the experiment's code defines what it measures)
while foreign QoI grammars are refused; its regime carries the `code`; the
run-entry maps the wrapper's scalar summary honestly (valid=False -> qoi_error,
never a fabricated number); and the routable/mature growth is additive-only
against the pre-promotion snapshot. Cavity's frozen anchor is untouched.

No model call, no solver, no container run — the wrapper is exercised only
through the deterministic translation/validation/run-entry surfaces.

Run directly: venv/bin/python3 tests/test_python_experiment_substrate.py
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import substrates  # noqa: E402
from tools import substrate_registry as registry  # noqa: E402
from tools.substrate_selection import select_substrate, signature_for  # noqa: E402
from tools.qoi_vocab import OPEN_SCALAR, vocab_for  # noqa: E402
from tools.substrate_dispatch import (  # noqa: E402
    adapter_for,
    content_keys_for,
    qoi_translation_for,
    run_entry_constructor_for,
)
from stages.stage2_spec import validate_spec  # noqa: E402

SID = "python_experiment"

_CODE = (
    "import numpy as np\n"
    "from sklearn.linear_model import Ridge\n"
    "from sklearn.model_selection import cross_val_score\n"
    "rng = np.random.default_rng(0)\n"
    "X = rng.standard_normal((200, 5))\n"
    "y = X @ np.array([1.,2.,0.,-1.,.5]) + 0.1*rng.standard_normal(200)\n"
    "metrics = {'r2': float(cross_val_score(Ridge(1.0), X, y, cv=5).mean())}\n"
)


def _code_spec(quantity="r2"):
    return {
        "hypothesis_id": "h1",
        "title": "Ridge CV baseline on a linear synthetic set",
        "objective": "Measure the 5-fold cross-validated R2 of ridge regression.",
        "parameters": [],
        "regime": {"code": _CODE, "notes": "single deterministic seeded run; result is a named scalar"},
        "qoi": {
            "name": "cross-validated R2", "units": "dimensionless",
            "definition": "mean 5-fold CV R2 of Ridge(alpha=1)",
            "how_extracted": "read metric r2 from the metrics file",
            "quantity": quantity,
        },
        "success_criterion": {"statement": "the model explains most variance",
                              "threshold": 0.5, "direction": "above"},
        "mini_experiment": {"runs": [{}], "expected_observation": "R2 near 0.9"},
        "full_experiment": {"design": "sweep alpha and noise", "estimated_run_count": 5},
    }


class TestEnrollment(unittest.TestCase):
    def test_routable_and_mature(self):
        self.assertIn(SID, registry.routable_ids())
        self.assertTrue(registry.is_mature(SID))

    def test_all_six_surfaces_wired(self):
        self.assertTrue(registry.contract_for(SID).startswith("INSTRUMENT: python_experiment"))
        self.assertEqual(sorted(signature_for(SID)), ["code", "quantity"])
        self.assertEqual(vocab_for(SID).shape, OPEN_SCALAR)
        self.assertEqual(content_keys_for(SID), ("code",))
        self.assertTrue(adapter_for(SID))
        self.assertTrue(run_entry_constructor_for(SID))
        self.assertTrue(qoi_translation_for(SID))

    def test_contract_is_the_imported_constant_not_a_copy(self):
        self.assertIs(registry.contract_for(SID), substrates.PYTHON_EXPERIMENT_CONTRACT)


class TestRoutesUniquely(unittest.TestCase):
    def test_a_complete_code_spec_validates_and_routes_here(self):
        spec = _code_spec()
        self.assertEqual(validate_spec(spec, "h1", vocab_for(SID)), [])
        self.assertEqual(select_substrate(spec), SID)

    def test_the_open_scalar_qoi_admits_any_metric_name(self):
        # A different metric name is equally valid — the code defines it.
        for q in ("accuracy", "final_loss", "f1_macro", "runtime_s"):
            spec = _code_spec(quantity=q)
            self.assertEqual(validate_spec(spec, "h1", vocab_for(SID)), [], q)
            self.assertEqual(select_substrate(spec), SID, q)

    def test_a_missing_quantity_is_refused(self):
        spec = _code_spec()
        del spec["qoi"]["quantity"]
        errs = validate_spec(spec, "h1", vocab_for(SID))
        self.assertTrue(any("quantity" in e for e in errs))

    def test_a_foreign_qoi_grammar_is_rejected(self):
        # A field-reduction machine key must not pass the open-scalar grammar.
        spec = _code_spec()
        spec["qoi"]["operation"] = "volAverage"
        errs = validate_spec(spec, "h1", vocab_for(SID))
        self.assertTrue(any("different substrate class" in e or "operation" in e for e in errs))

    def test_a_regime_without_code_is_refused(self):
        spec = _code_spec()
        del spec["regime"]["code"]
        errs = validate_spec(spec, "h1", vocab_for(SID))
        self.assertTrue(any("code" in e for e in errs))


class TestTranslationAndRunEntry(unittest.TestCase):
    def test_open_scalar_translation_threads_the_metric_name(self):
        req, refusal = qoi_translation_for(SID)({"quantity": "r2"}, vocab_for(SID))
        self.assertIsNone(refusal)
        self.assertEqual(req, {"quantity": "r2"})

    def test_translation_refuses_an_empty_quantity(self):
        req, refusal = qoi_translation_for(SID)({"quantity": "  "}, vocab_for(SID))
        self.assertIsNone(req)
        self.assertIn("quantity", refusal)

    def test_run_entry_maps_a_valid_scalar_summary(self):
        entry = run_entry_constructor_for(SID)(
            {"valid": True, "qoi": 0.87, "diagnostics": "", "runtime_s": 1.2}
        )
        self.assertTrue(entry["converged"])
        self.assertEqual(entry["qoi_value"], 0.87)

    def test_run_entry_maps_a_failed_run_to_qoi_error_never_a_number(self):
        entry = run_entry_constructor_for(SID)(
            {"valid": False, "qoi": None, "diagnostics": "script wrote no 'r2' metric", "runtime_s": 0.3}
        )
        self.assertFalse(entry["converged"])
        self.assertNotIn("qoi_value", entry)
        self.assertIn("qoi_error", entry)


class TestAdditiveOnlyAndAnchor(unittest.TestCase):
    C235 = ROOT / "tests" / "fixtures" / "c235"

    def _ids(self, path):
        err = json.loads((self.C235 / path).read_text())["validation_error"]
        return set(eval(re.search(r"exactly one of (\[[^\]]*\])", err).group(1)))

    def test_chooser_id_list_grew_by_exactly_python_experiment(self):
        # The clean additive proof for THIS promotion: new minus the 9-routable
        # snapshot preserved append-only at capture time is exactly the one id.
        new = self._ids("chooser_retry_user_turn_v235.txt")
        prepy = self._ids("chooser_retry_user_turn_v235_prepy.txt")
        self.assertEqual(new - prepy, {"python_experiment"})
        self.assertEqual(prepy - new, set())

    def test_cavity_frozen_anchor_untouched(self):
        # Adding a routable instrument must not move cavity's model-visible
        # contract bytes.
        self.assertTrue(registry.contract_for("cavity_2d_cfd").startswith("SUBSTRATE CONTRACT: cavity_2d"))
        self.assertIs(registry.contract_for("cavity_2d_cfd"), substrates.CAVITY_2D_CONTRACT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
