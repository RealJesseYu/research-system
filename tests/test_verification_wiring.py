"""test_verification_wiring.py — the artifact channel and the verification gate.

stages/verification.py could always re-run an artifact; nothing emitted one, so
it had no caller and no proof it fit anything real. These tests pin the wiring
that closed that gap:

  * the dispatch boundary records the invocation it actually made,
  * stage 4 harvests it per point without disturbing results.json's pinned shape,
  * claims are rebuilt from evidence with the value read by the substrate's own
    run-entry constructor,
  * and the supervisor's pass FAILS CLOSED — an unverified paper is never
    recorded as a verified one.

rdkit is the instrument of record here: real, enrolled, deterministic, and fast
enough to re-run twice in a unit test. The reproduction assertions are therefore
genuine re-executions of a real wrapper, not fakes agreeing with themselves.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages import stage4_simulation as s4  # noqa: E402
from stages.verification import (  # noqa: E402
    ArtifactError,
    claims_from_run,
    rerun_artifact,
    verify_claim,
    verify_run,
)
from tools import substrate_dispatch as dispatch  # noqa: E402

RDKIT_QOI = {"quantity": "MolWt"}
ETHANOL_MOLWT = 46.069


@contextlib.contextmanager
def _tmp_cwd():
    """Evidence is written into a throwaway tree — runs/ is append-only and no
    test may pollute it."""
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(previous)


def _run_rdkit_point(run_id="v1", index=1, params=None, case_name=None):
    """One real rdkit point through the real run_one_point and real adapter."""
    return s4.run_one_point(
        run_id, index, 1, params if params is not None else {"smiles": "CCO"},
        substrate_id="rdkit",
        adapter=dispatch.adapter_for("rdkit"),
        entry_constructor=dispatch.run_entry_constructor_for("rdkit"),
        parameter_roles={},
        qoi_request=RDKIT_QOI,
        qoi_error_fallback=None,
        case_name=case_name,
    )


class TestDispatchRecording(unittest.TestCase):
    """The artifact describes the call that was actually made."""

    def setUp(self):
        dispatch.clear_dispatch_record()

    def test_take_is_none_when_nothing_dispatched(self):
        self.assertIsNone(dispatch.take_dispatch_record())

    def test_record_is_the_typed_input_handed_to_the_wrapper(self):
        summary = dispatch.adapter_for("rdkit")(
            "rdkit", {"smiles": "CCO"}, "case", {}, RDKIT_QOI)
        record = dispatch.take_dispatch_record()
        self.assertTrue(summary["valid"])
        self.assertEqual(record["kind"], "substrate")
        self.assertEqual(record["substrate_id"], "rdkit")
        self.assertEqual(record["call_style"], dispatch.CALL_TYPED_DICT)
        # the threaded quantity is part of the typed input, exactly as the
        # adapter built it — not reconstructed here
        self.assertEqual(record["typed_input"],
                         {"smiles": "CCO", "quantity": "MolWt"})

    def test_taking_pops_so_an_artifact_is_harvested_once(self):
        dispatch.adapter_for("rdkit")("rdkit", {"smiles": "CCO"}, "c", {}, RDKIT_QOI)
        self.assertIsNotNone(dispatch.take_dispatch_record())
        self.assertIsNone(dispatch.take_dispatch_record())

    def test_clear_prevents_a_stale_artifact_being_attributed_to_a_later_point(self):
        dispatch.adapter_for("rdkit")("rdkit", {"smiles": "CCO"}, "c", {}, RDKIT_QOI)
        dispatch.clear_dispatch_record()
        self.assertIsNone(dispatch.take_dispatch_record())


class TestStage4Harvest(unittest.TestCase):
    """run_one_point attaches the artifact; the pinned shapes are undisturbed."""

    def test_point_carries_an_artifact_that_regenerates_it(self):
        with _tmp_cwd():
            (Path("runs") / "v1").mkdir(parents=True)
            evidence, payload, halt = _run_rdkit_point()
        self.assertIsNone(halt)
        artifact = evidence["artifact"]
        self.assertEqual(artifact["substrate_id"], "rdkit")
        self.assertEqual(artifact["quantity"], "MolWt")
        self.assertEqual(payload["qoi_value"], ETHANOL_MOLWT)
        # the artifact genuinely re-runs
        self.assertEqual(rerun_artifact(artifact)["value"], ETHANOL_MOLWT)

    def test_an_adapter_that_never_dispatched_yields_an_unrecorded_artifact(self):
        """A measurement nothing can regenerate is RECORDED as such, never
        omitted — an omission would shrink verification's denominator."""
        def fake_adapter(sid, params, case_name, roles, qreq):
            return {"valid": True, "qoi": 1.0, "diagnostics": "fake", "runtime_s": 0.1}

        with _tmp_cwd():
            (Path("runs") / "v1").mkdir(parents=True)
            evidence, _payload, _halt = s4.run_one_point(
                "v1", 1, 1, {"smiles": "CCO"},
                substrate_id="rdkit", adapter=fake_adapter,
                entry_constructor=dispatch.run_entry_constructor_for("rdkit"),
                parameter_roles={}, qoi_request=RDKIT_QOI,
                qoi_error_fallback=None,
            )
        self.assertTrue(evidence["artifact"]["unrecorded"])
        verdict = verify_claim({"value": 1.0, "artifact": evidence["artifact"]})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "unrunnable_artifact")

    def test_split_artifacts_leaves_the_pinned_results_shape_alone(self):
        runs = [{"run_index": 1, "case": "c1", "params": {}, "summary": {"valid": True},
                 "artifact": {"kind": "substrate", "substrate_id": "rdkit"}}]
        records = s4.split_artifacts(runs)
        self.assertEqual(records[0]["run_index"], 1)
        self.assertEqual(records[0]["artifact"]["substrate_id"], "rdkit")
        # the evidence run no longer carries it, so the two files cannot
        # disagree about what was dispatched
        self.assertNotIn("artifact", runs[0])
        self.assertEqual(sorted(runs[0]), ["case", "params", "run_index", "summary"])

    def test_artifacts_file_is_written_even_when_nothing_was_recorded(self):
        with _tmp_cwd() as tmp:
            stage_dir = Path(tmp) / "stage4"
            stage_dir.mkdir()
            s4.write_artifacts(stage_dir, [{"run_index": 1, "case": "c", "artifact": None}])
            data = json.loads((stage_dir / "artifacts.json").read_text())
        self.assertEqual(data["runs"][0]["artifact"], None)


class TestClaimsFromRun(unittest.TestCase):
    """Claims are rebuilt from evidence as {value, artifact, label}."""

    def _write_run(self, run_id, summary, artifact):
        stage_dir = Path("runs") / run_id / "stage4"
        stage_dir.mkdir(parents=True)
        (stage_dir / "results.json").write_text(json.dumps(
            {"status": "executed",
             "runs": [{"run_index": 1, "case": "c1", "params": {}, "summary": summary}]}))
        (stage_dir / "artifacts.json").write_text(json.dumps(
            {"runs": [{"run_index": 1, "case": "c1", "artifact": artifact}]}))

    def test_joins_the_two_evidence_files_on_run_index(self):
        artifact = {"kind": "substrate", "substrate_id": "rdkit",
                    "call_style": dispatch.CALL_TYPED_DICT,
                    "typed_input": {"smiles": "CCO", "quantity": "MolWt"},
                    "quantity": "MolWt", "qoi_request": RDKIT_QOI}
        summary = {"valid": True, "qoi": ETHANOL_MOLWT, "diagnostics": "d",
                   "runtime_s": 0.5}
        with _tmp_cwd():
            self._write_run("r1", summary, artifact)
            claims = claims_from_run("r1")
        self.assertEqual(len(claims), 1)
        self.assertEqual(sorted(claims[0]), ["artifact", "label", "value"])
        self.assertEqual(claims[0]["value"], ETHANOL_MOLWT)
        self.assertIn("MolWt", claims[0]["label"])

    def test_a_failed_run_makes_no_claim(self):
        """Nothing was measured, so there is nothing to claim — and nothing to
        verify. This is not the same as an unverifiable claim."""
        summary = {"valid": False, "qoi": None,
                   "diagnostics": "input rejected: missing required field(s): model",
                   "runtime_s": 0.0}
        with _tmp_cwd():
            self._write_run("r2", summary, {"kind": "substrate", "substrate_id": "rdkit"})
            claims = claims_from_run("r2")
        self.assertEqual(claims, [])

    def test_missing_evidence_yields_no_claims_rather_than_raising(self):
        with _tmp_cwd():
            self.assertEqual(claims_from_run("nope"), [])


class TestVerificationVerdicts(unittest.TestCase):
    """The three verdicts that matter, against a real instrument."""

    def _artifact(self, smiles="CCO"):
        return {"kind": "substrate", "substrate_id": "rdkit",
                "call_style": dispatch.CALL_TYPED_DICT,
                "typed_input": {"smiles": smiles, "quantity": "MolWt"},
                "quantity": "MolWt", "qoi_request": RDKIT_QOI}

    def test_a_true_value_reproduces(self):
        verdict = verify_claim({"value": ETHANOL_MOLWT, "artifact": self._artifact(),
                                "label": "MolWt"})
        self.assertTrue(verdict["verified"])
        self.assertEqual(verdict["reason"], "reproduced")

    def test_a_fabricated_value_is_caught(self):
        verdict = verify_claim({"value": 99.9, "artifact": self._artifact()})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "mismatch")
        self.assertEqual(verdict["reproduced"], ETHANOL_MOLWT)

    def test_a_value_with_no_artifact_is_refused(self):
        verdict = verify_claim({"value": 1.23, "artifact": None})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "no_artifact")

    def test_an_unknown_artifact_kind_cannot_support_a_claim(self):
        with self.assertRaises(ArtifactError):
            rerun_artifact({"kind": "vibes", "value": 1})

    def test_run_is_publishable_only_when_every_claim_reproduced(self):
        good = {"value": ETHANOL_MOLWT, "artifact": self._artifact(), "label": "good"}
        bad = {"value": 1.0, "artifact": None, "label": "bare number"}
        self.assertTrue(verify_run([good])["publishable"])
        mixed = verify_run([good, bad])
        self.assertFalse(mixed["publishable"])
        self.assertEqual(mixed["verified"], 1)
        self.assertEqual(mixed["total"], 2)

    def test_a_run_with_no_claims_is_not_publishable(self):
        """A paper with no verifiable numbers has nothing to stand on, so the
        empty case must not read as a clean pass."""
        summary = verify_run([])
        self.assertFalse(summary["publishable"])
        self.assertIn("note", summary)


class TestSupervisorGateFailsClosed(unittest.TestCase):
    """The gate the supervisor actually runs. A gate that fails open is not a
    gate — the desk screen already taught this project that once."""

    def _logger(self):
        class L:
            def __init__(self):
                self.lines = []

            def log(self, line):
                self.lines.append(line)
        return L()

    def _baton(self, run_id="v9"):
        class B:
            pass
        b = B()
        b.run_id = run_id
        return b

    def test_broken_pass_is_not_publishable(self):
        import supervisor

        logger, baton = self._logger(), self._baton()
        # run_verification_pass imports at call time, so patching the module
        # attribute here is what the pass will actually reach.
        import stages.verification as verification
        broken = verification.claims_from_run

        def explode(_run_id):
            raise RuntimeError("evidence unreadable")

        verification.claims_from_run = explode
        try:
            summary = supervisor.run_verification_pass(logger, baton)
        finally:
            verification.claims_from_run = broken

        self.assertFalse(summary["publishable"])
        self.assertIn("error", summary)
        self.assertTrue(any("NOT publishable" in line for line in logger.lines))

    def test_unverified_run_says_so_loudly_and_is_stamped_on_the_baton(self):
        import supervisor

        logger, baton = self._logger(), self._baton()
        with _tmp_cwd():
            summary = supervisor.run_verification_pass(logger, baton)
        self.assertFalse(summary["publishable"])
        self.assertIs(baton._verification, summary)
        self.assertTrue(
            any("DOES NOT STAND" in line for line in logger.lines),
            f"the failure must be loud; got {logger.lines}",
        )

    def test_a_verified_run_reports_the_paper_as_standing(self):
        import supervisor

        logger, baton = self._logger(), self._baton("v10")
        artifact = {"kind": "substrate", "substrate_id": "rdkit",
                    "call_style": dispatch.CALL_TYPED_DICT,
                    "typed_input": {"smiles": "CCO", "quantity": "MolWt"},
                    "quantity": "MolWt", "qoi_request": RDKIT_QOI}
        with _tmp_cwd():
            stage_dir = Path("runs") / "v10" / "stage4"
            stage_dir.mkdir(parents=True)
            (stage_dir / "results.json").write_text(json.dumps({"runs": [
                {"run_index": 1, "case": "c", "params": {},
                 "summary": {"valid": True, "qoi": ETHANOL_MOLWT,
                             "diagnostics": "d", "runtime_s": 0.1}}]}))
            (stage_dir / "artifacts.json").write_text(json.dumps({"runs": [
                {"run_index": 1, "case": "c", "artifact": artifact}]}))
            summary = supervisor.run_verification_pass(logger, baton)
            written = json.loads((Path("runs") / "v10" / "verification.json").read_text())

        self.assertTrue(summary["publishable"])
        self.assertEqual(written["verified"], 1)
        self.assertTrue(any("stand" in line for line in logger.lines))


if __name__ == "__main__":
    unittest.main()
