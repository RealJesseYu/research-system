"""test_composition_artifacts.py — file-artifact hand-off between tools (R-ART-5).

docs/memo_phase4_artifacts.md. Proves the first genuine file hand-off: one code
step writes a FILE, a downstream code step consumes it, combined into one final
scalar — run once and then INDEPENDENTLY reproduced end-to-end, with EVERY FILE
RE-DERIVED (never a stored copy). This is the file analogue of R-COMP-4: running
a file-passing composition and re-running it are the same deterministic path, so
a number standing on a non-reproducible file is caught, never shipped.

The reproduction assertions are genuine re-executions in the sealed sandbox
(--network=none). The recipe-validation class is call-free (no docker).

Run directly: venv/bin/python3 tests/test_composition_artifacts.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.verification import (  # noqa: E402
    ArtifactError,
    run_composition,
    verify_claim,
)
from tools.run_python_experiment import run_python_experiment  # noqa: E402


def _handoff_recipe():
    """produce writes a vector file + a scalar; consume reads the file and sums
    it; combine ties both scalars into the final number (3 + 60 = 63)."""
    return {"kind": "composition",
            "steps": [
                {"step_id": "produce", "kind": "code",
                 "code": "open('vec.txt','w').write('10,20,30')\nmetrics['n']=3.0",
                 "quantity": "n", "emits": ["vec.txt"]},
                {"step_id": "consume", "kind": "code",
                 "code": ("vals=[float(x) for x in open('vec.txt').read().split(',')]\n"
                          "metrics['total']=sum(vals)"),
                 "quantity": "total",
                 "consumes": [{"step_id": "produce", "name": "vec.txt"}]},
            ],
            "combine": {"kind": "code",
                        "code": "metrics['out'] = inputs['produce'] + inputs['consume']",
                        "quantity": "out", "inputs": ["produce", "consume"]}}


class TestFileHandoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = run_python_experiment({"code": "metrics['x']=1.0", "quantity": "x"})
        if not probe["valid"]:
            raise unittest.SkipTest(f"code sandbox unavailable: {probe['diagnostics']}")

    def test_the_handoff_runs_and_the_number_is_right(self):
        out = run_composition(_handoff_recipe())
        self.assertIsNone(out["error"], out["error"])
        self.assertEqual(out["steps"]["produce"], 3.0)
        self.assertEqual(out["steps"]["consume"], 60.0)   # the file was read
        self.assertEqual(out["value"], 63.0)

    def test_it_independently_reproduces_with_every_file_re_derived(self):
        out = run_composition(_handoff_recipe())
        verdict = verify_claim({"value": out["value"], "artifact": out["artifact"]})
        self.assertTrue(verdict["verified"], verdict)
        self.assertEqual(verdict["reason"], "reproduced")
        self.assertLessEqual(verdict["rel_error"], 1e-6)

    def test_a_perturbed_composed_value_is_caught(self):
        out = run_composition(_handoff_recipe())
        verdict = verify_claim({"value": out["value"] * 1.1, "artifact": out["artifact"]})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "mismatch")

    def test_a_nondeterministic_file_producer_is_caught(self):
        """The file channel does not weaken verification: a producer that writes
        a different file each run makes the number un-reproducible, and that is
        caught — proof the consumer reads the RE-RUN file, not a stored one."""
        recipe = _handoff_recipe()
        recipe["steps"][0]["code"] = (
            "import random\nopen('vec.txt','w').write(str(random.random()))\n"
            "metrics['n']=3.0")
        out = run_composition(recipe)
        self.assertIsNone(out["error"], out["error"])
        verdict = verify_claim({"value": out["value"], "artifact": out["artifact"]})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "mismatch")

    def test_a_declared_emit_that_is_not_written_fails_loud(self):
        recipe = _handoff_recipe()
        # producer declares it emits vec.txt but never writes it
        recipe["steps"][0]["code"] = "metrics['n']=3.0"
        out = run_composition(recipe)
        self.assertIsNone(out["value"])
        self.assertIn("did not write it", out["error"])
        verdict = verify_claim({"value": 63.0, "artifact": recipe})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "rerun_failed")

    def test_a_normal_scalar_recipe_is_unaffected(self):
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "a", "kind": "code",
                             "code": "metrics['a']=2.0", "quantity": "a"}],
                  "combine": {"kind": "code",
                              "code": "metrics['out']=inputs['a']*3",
                              "quantity": "out", "inputs": ["a"]}}
        out = run_composition(recipe)
        self.assertEqual(out["value"], 6.0)


class TestRecipeValidation(unittest.TestCase):
    """Malformed hand-offs are re-asked at recipe validation — call-free, no
    container is touched."""

    def _bad(self, recipe, needle):
        with self.assertRaises(ArtifactError) as ctx:
            run_composition(recipe)   # _validate_recipe raises before any run
        self.assertIn(needle, str(ctx.exception))

    def test_consume_from_a_non_earlier_step_is_refused(self):
        self._bad({"kind": "composition",
                   "steps": [{"step_id": "a", "kind": "code",
                              "code": "metrics['a']=1.0", "quantity": "a",
                              "consumes": [{"step_id": "b", "name": "f.txt"}]},
                             {"step_id": "b", "kind": "code", "emits": ["f.txt"],
                              "code": "open('f.txt','w').write('x')\nmetrics['b']=1.0",
                              "quantity": "b"}],
                   "combine": {"kind": "code", "code": "metrics['o']=inputs['a']",
                               "quantity": "o", "inputs": ["a"]}},
                  "not an earlier step")

    def test_consume_a_name_the_upstream_does_not_emit_is_refused(self):
        self._bad({"kind": "composition",
                   "steps": [{"step_id": "a", "kind": "code", "emits": ["x.txt"],
                              "code": "open('x.txt','w').write('x')\nmetrics['a']=1.0",
                              "quantity": "a"},
                             {"step_id": "b", "kind": "code",
                              "code": "metrics['b']=1.0", "quantity": "b",
                              "consumes": [{"step_id": "a", "name": "y.txt"}]}],
                   "combine": {"kind": "code", "code": "metrics['o']=inputs['b']",
                               "quantity": "o", "inputs": ["b"]}},
                  "does not emit it")

    def test_a_substrate_step_may_not_emit_a_file(self):
        self._bad({"kind": "composition",
                   "steps": [{"step_id": "a", "kind": "substrate",
                              "substrate_id": "rdkit", "emits": ["x.txt"]}],
                   "combine": {"kind": "code", "code": "metrics['o']=inputs['a']",
                               "quantity": "o", "inputs": ["a"]}},
                  "only a code step may emit")

    def test_a_path_traversal_name_is_refused(self):
        self._bad({"kind": "composition",
                   "steps": [{"step_id": "a", "kind": "code",
                              "code": "metrics['a']=1.0", "quantity": "a",
                              "emits": ["../escape.txt"]}],
                   "combine": {"kind": "code", "code": "metrics['o']=inputs['a']",
                               "quantity": "o", "inputs": ["a"]}},
                  "bare filenames")


if __name__ == "__main__":
    unittest.main()
