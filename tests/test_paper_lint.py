"""
test_paper_lint.py — standalone tests of harness/paper_lint.py (Step 22).
Deterministic, ZERO model calls: run dirs are assembled in a temp
runs_root from the tests/fixtures/paper/ fixture set and linted pure.

Run directly: venv/bin/python3 tests/test_paper_lint.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.paper_lint import lint_paper, validate_validation_items

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "paper"


class LintRunBuilder(unittest.TestCase):
    """Shared temp-runs_root machinery."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.runs_root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make_run(
        self,
        run_id: str,
        verdict: str | None,
        sidecar: str | dict | None,
        paper: str | None,
    ) -> str:
        """Assemble runs_root/<run_id> from fixture file names (or a raw
        sidecar dict); None omits that artifact entirely."""
        run_dir = self.runs_root / run_id
        (run_dir / "stage3").mkdir(parents=True)
        (run_dir / "stage6").mkdir(parents=True)
        if verdict is not None:
            shutil.copy(FIXTURES / verdict, run_dir / "stage3" / "verdict.json")
        if sidecar is not None:
            target = run_dir / "stage6" / "paper_validation.json"
            if isinstance(sidecar, dict):
                target.write_text(json.dumps(sidecar))
            else:
                shutil.copy(FIXTURES / sidecar, target)
        if paper is not None:
            shutil.copy(FIXTURES / paper, run_dir / "stage6" / "paper.md")
        return run_id

    def lint(self, run_id: str) -> list[dict]:
        return lint_paper(run_id, runs_root=self.runs_root)

    def codes(self, run_id: str) -> list[str]:
        return [f["code"] for f in self.lint(run_id)]


class TestValidFixturesPass(LintRunBuilder):
    def test_trust_passes(self):
        run_id = self.make_run("t", "verdict_trust.json", "sidecar_trust.json", "paper_trust.md")
        self.assertEqual(self.lint(run_id), [])

    def test_refine_passes(self):
        run_id = self.make_run("r", "verdict_refine.json", "sidecar_refine.json", "paper_refine.md")
        self.assertEqual(self.lint(run_id), [])

    def test_defer_passes(self):
        run_id = self.make_run("d", "verdict_defer.json", "sidecar_defer.json", "paper_defer.md")
        self.assertEqual(self.lint(run_id), [])


class TestBrokenVariantsFail(LintRunBuilder):
    def test_mismatched_class_caught(self):
        # Sidecar declares refine while the on-disk verdict says trust.
        run_id = self.make_run(
            "m", "verdict_trust.json", "sidecar_mismatched_class.json", "paper_trust.md"
        )
        failures = self.lint(run_id)
        self.assertEqual([f["code"] for f in failures], ["class_mismatch"])
        self.assertEqual(failures[0]["target"], "sidecar")

    def test_missing_heading_caught(self):
        run_id = self.make_run(
            "h", "verdict_trust.json", "sidecar_trust.json", "paper_missing_heading.md"
        )
        failures = self.lint(run_id)
        self.assertEqual([f["code"] for f in failures], ["heading_missing"])
        self.assertEqual(failures[0]["target"], "What Humans Must Validate")

    def test_empty_items_caught(self):
        run_id = self.make_run(
            "e", "verdict_defer.json", "sidecar_empty_items.json", "paper_defer.md"
        )
        self.assertEqual(self.codes(run_id), ["items_invalid"])

    def test_missing_sidecar_caught(self):
        run_id = self.make_run("s", "verdict_trust.json", None, "paper_trust.md")
        self.assertEqual(self.codes(run_id), ["sidecar_missing"])

    def test_unparseable_sidecar_caught(self):
        run_id = self.make_run("u", "verdict_trust.json", None, "paper_trust.md")
        sidecar_path = self.runs_root / run_id / "stage6" / "paper_validation.json"
        sidecar_path.write_text("{not json")
        self.assertEqual(self.codes(run_id), ["sidecar_unparseable"])

    def test_missing_paper_caught(self):
        run_id = self.make_run("p", "verdict_trust.json", "sidecar_trust.json", None)
        self.assertEqual(self.codes(run_id), ["paper_missing"])

    def test_missing_verdict_caught(self):
        run_id = self.make_run("v", None, "sidecar_trust.json", "paper_trust.md")
        self.assertEqual(self.codes(run_id), ["verdict_missing"])

    def test_invalid_fidelity_class_caught(self):
        run_id = self.make_run(
            "fc",
            "verdict_trust.json",
            {"fidelity_class": "maybe", "validation_items": []},
            "paper_trust.md",
        )
        self.assertEqual(self.codes(run_id), ["fidelity_class_invalid"])

    def test_sidecar_extra_key_caught(self):
        sidecar = json.loads((FIXTURES / "sidecar_trust.json").read_text())
        sidecar["surplus"] = True
        run_id = self.make_run("x", "verdict_trust.json", sidecar, "paper_trust.md")
        self.assertEqual(self.codes(run_id), ["sidecar_extra_key"])


class TestClassConditionalItemRules(unittest.TestCase):
    def test_trust_requires_exactly_one_none_required_item(self):
        item = {"kind": "none_required", "reason": "gate trusted the instrument."}
        self.assertEqual(validate_validation_items("trust", [item]), [])
        errors = validate_validation_items("trust", [item, item])
        self.assertTrue(any("exactly ONE" in e for e in errors))
        errors = validate_validation_items(
            "trust", [{"kind": "other", "reason": "r"}]
        )
        self.assertTrue(any("none_required" in e for e in errors))

    def test_refine_items_need_a_claim(self):
        self.assertEqual(
            validate_validation_items("refine", [{"claim": "confirm the QoI shift."}]),
            [],
        )
        errors = validate_validation_items("refine", [{"claim": ""}])
        self.assertTrue(any("claim" in e for e in errors))
        errors = validate_validation_items(
            "refine", [{"claim": "ok", "extra": "no"}]
        )
        self.assertTrue(any("'extra' is not allowed" in e for e in errors))

    def test_defer_items_need_full_test_spec(self):
        good = {
            "substrate": "scalar-transport solver",
            "conditions": "Re 200 cavity with tracer",
            "measurement": "variance decay rate",
        }
        self.assertEqual(validate_validation_items("defer", [good]), [])
        broken = dict(good)
        del broken["measurement"]
        errors = validate_validation_items("defer", [broken])
        self.assertTrue(any("measurement" in e for e in errors))

    def test_non_list_and_empty_items_rejected(self):
        self.assertTrue(validate_validation_items("trust", None))
        self.assertTrue(validate_validation_items("defer", []))
        self.assertTrue(validate_validation_items("refine", "not a list"))

    def test_non_dict_item_rejected(self):
        errors = validate_validation_items("refine", ["just a string"])
        self.assertTrue(any("must be an object" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
