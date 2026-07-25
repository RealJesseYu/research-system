"""test_reusable_artifacts.py — the cross-run file hand-off reproducibility gate.

Proves the gate ACCEPTS a producer that re-emits its file and REJECTS every way a
producer can fail to, using an injected step executor (verification._run_one_step
is exercised live elsewhere; here we test the gate's decision logic offline).

Run directly: venv/bin/python3 tests/test_reusable_artifacts.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.reusable_artifacts import as_producer_step, validate_reusable_artifact  # noqa: E402


def _code_producer(name="seq.fasta"):
    return {
        "kind": "code",
        "quantity": "n",
        "emits": [name],
        "code": f"open({name!r},'w').write('>s\\nACGT\\n'); metrics = {{'n': 1}}",
    }


def _emitting_run(name="seq.fasta", value=1.0, content=b">s\nACGT\n"):
    """A fake _run_one_step that emits `name`."""
    def run(step, consumed):
        return {"value": value, "error": None}, {name: content}
    return run


class TestReproducibilityGate(unittest.TestCase):
    def test_a_producer_that_re_emits_its_file_is_accepted(self):
        desc = {"name": "seq.fasta", "producer": _code_producer()}
        self.assertEqual(validate_reusable_artifact(desc, run=_emitting_run()), [])

    def test_missing_producer_is_rejected(self):
        self.assertTrue(validate_reusable_artifact({"name": "seq.fasta"}, run=_emitting_run()))

    def test_bad_name_is_rejected(self):
        desc = {"name": "sub/seq.fasta", "producer": _code_producer("sub/seq.fasta")}
        self.assertTrue(validate_reusable_artifact(desc, run=_emitting_run("sub/seq.fasta")))

    def test_producer_not_declaring_the_emit_is_rejected(self):
        prod = _code_producer()
        prod["emits"] = ["other.txt"]
        errs = validate_reusable_artifact({"name": "seq.fasta", "producer": prod}, run=_emitting_run())
        self.assertTrue(any("emits" in e for e in errs))

    def test_code_producer_without_quantity_is_rejected(self):
        prod = _code_producer()
        del prod["quantity"]
        errs = validate_reusable_artifact({"name": "seq.fasta", "producer": prod}, run=_emitting_run())
        self.assertTrue(any("quantity" in e for e in errs))

    def test_producer_that_errors_is_rejected_not_crashed(self):
        def failing_run(step, consumed):
            return {"value": None, "error": "boom in the sandbox"}, {}
        errs = validate_reusable_artifact(
            {"name": "seq.fasta", "producer": _code_producer()}, run=failing_run)
        self.assertTrue(any("did not run cleanly" in e for e in errs))

    def test_producer_that_does_not_emit_the_file_is_rejected(self):
        def no_emit(step, consumed):
            return {"value": 1.0, "error": None}, {}  # ran, emitted nothing
        errs = validate_reusable_artifact(
            {"name": "seq.fasta", "producer": _code_producer()}, run=no_emit)
        self.assertTrue(any("did not emit" in e for e in errs))

    def test_producer_that_emits_an_empty_file_is_rejected(self):
        errs = validate_reusable_artifact(
            {"name": "seq.fasta", "producer": _code_producer()},
            run=_emitting_run(content=b""))
        self.assertTrue(any("empty" in e for e in errs))

    def test_a_raising_producer_is_a_rejection_not_a_crash(self):
        def boom(step, consumed):
            raise RuntimeError("unexpected")
        errs = validate_reusable_artifact(
            {"name": "seq.fasta", "producer": _code_producer()}, run=boom)
        self.assertTrue(any("raised while reproducing" in e for e in errs))


class TestAsProducerStep(unittest.TestCase):
    def test_stamps_a_step_id_for_inlining(self):
        desc = {"name": "seq.fasta", "producer": _code_producer()}
        step = as_producer_step(desc, "frame_geom")
        self.assertEqual(step["step_id"], "frame_geom")
        self.assertEqual(step["emits"], ["seq.fasta"])
        # the original is untouched (pure)
        self.assertNotIn("step_id", desc["producer"])


if __name__ == "__main__":
    unittest.main()
