"""
test_null_twin.py — the optional control_block schema tolerance and the
tools/null_twin.py comparison helper.

Zero model calls. Proves: (a) a real on-disk spec WITHOUT control_block
validates byte-identically (the additive field changed nothing for existing
specs); (b) a spec WITH a well-formed control_block still validates, and a
malformed one is caught only when present; (c) null-twin comparison catches an
artifact in both directions.

Run directly: python3 tests/test_null_twin.py
"""

from __future__ import annotations

import copy
import glob
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage2_spec import validate_spec
from tools.null_twin import compare

ROOT = Path(__file__).resolve().parent.parent


def _a_clean_on_disk_spec() -> tuple[dict, str]:
    """Return (spec, hypothesis_id) for a real spec that validates cleanly."""
    for f in sorted(glob.glob(str(ROOT / "runs/**/stage2/spec.json"), recursive=True)):
        spec = json.loads(Path(f).read_text())
        hid = spec.get("hypothesis_id", "")
        if validate_spec(spec, hid) == []:
            return spec, hid
    raise unittest.SkipTest("no clean on-disk spec found")


class SchemaBackCompat(unittest.TestCase):
    def test_real_spec_without_control_block_unchanged(self):
        spec, hid = _a_clean_on_disk_spec()
        self.assertNotIn("control_block", spec)
        # still valid, still exactly zero errors — the additive optional field
        # left existing specs byte-identical in validation outcome.
        self.assertEqual(validate_spec(spec, hid), [])

    def test_wellformed_control_block_validates(self):
        spec, hid = _a_clean_on_disk_spec()
        spec = copy.deepcopy(spec)
        spec["control_block"] = {
            "description": "Zero lid velocity: no forcing, so no recirculation.",
            "params": {"lid_velocity": 0.0},
            "expected_null_outcome": "mean flow speed ~0; the effect must vanish.",
        }
        self.assertEqual(validate_spec(spec, hid), [])

    def test_malformed_control_block_caught_only_when_present(self):
        spec, hid = _a_clean_on_disk_spec()
        spec = copy.deepcopy(spec)
        spec["control_block"] = {"params": {"lid_velocity": 0.0}}  # missing two fields
        errs = validate_spec(spec, hid)
        self.assertTrue(any("description" in e for e in errs))
        self.assertTrue(any("expected_null_outcome" in e for e in errs))

    def test_control_block_not_a_dict(self):
        spec, hid = _a_clean_on_disk_spec()
        spec = copy.deepcopy(spec)
        spec["control_block"] = "not an object"
        errs = validate_spec(spec, hid)
        self.assertTrue(any("control_block" in e for e in errs))


class NullTwinThreshold(unittest.TestCase):
    def _results(self, *values):
        return {"status": "executed", "runs": [{"converged": True, "qoi_value": v} for v in values]}

    def test_effect_absent_in_null_is_clean(self):
        main = self._results(0.1, 0.42)          # last value 0.42 > 0.3
        null = self._results(0.02, 0.05)         # last value 0.05, no effect
        crit = {"kind": "threshold", "threshold": 0.3, "direction": "above"}
        out = compare(main, null, crit)
        self.assertFalse(out["effect_in_null"])
        self.assertFalse(any("ARTIFACT" in n for n in out["notes"]))

    def test_effect_present_in_null_is_artifact(self):
        main = self._results(0.1, 0.42)
        null = self._results(0.35, 0.40)         # last value 0.40 > 0.3 -> effect present!
        crit = {"kind": "threshold", "threshold": 0.3, "direction": "above"}
        out = compare(main, null, crit)
        self.assertTrue(out["effect_in_null"])
        self.assertTrue(any("ARTIFACT" in n for n in out["notes"]))

    def test_null_qoi_not_extractable_reports_false_with_reason(self):
        main = self._results(0.42)
        null = {"status": "executed", "runs": [{"converged": True, "qoi_error": "no field"}]}
        crit = {"kind": "threshold", "threshold": 0.3, "direction": "above"}
        out = compare(main, null, crit)
        self.assertFalse(out["effect_in_null"])
        self.assertTrue(any("not extractable" in n for n in out["notes"]))


class NullTwinRelative(unittest.TestCase):
    def _results(self, *values):
        return {"runs": [{"qoi_value": v} for v in values]}

    def test_relative_effect_absent_clean(self):
        # null magnitude far below 50% of main -> clean
        out = compare(self._results(1.0), self._results(0.05),
                      {"kind": "relative", "reduce": "last", "min_effect_fraction": 0.5})
        self.assertFalse(out["effect_in_null"])

    def test_relative_effect_present_artifact(self):
        # null retains 90% of main's magnitude -> artifact
        out = compare(self._results(1.0), self._results(0.9),
                      {"kind": "relative", "reduce": "last", "min_effect_fraction": 0.5})
        self.assertTrue(out["effect_in_null"])
        self.assertTrue(any("ARTIFACT" in n for n in out["notes"]))


class NullTwinRobustness(unittest.TestCase):
    def test_bad_criterion_never_raises(self):
        self.assertEqual(compare({}, {}, None)["effect_in_null"], False)
        self.assertEqual(compare({}, {}, {"kind": "nonsense"})["effect_in_null"], False)


if __name__ == "__main__":
    unittest.main()
