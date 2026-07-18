"""
test_c235_chain.py — Step 23.5 Phase-3 proofs: the agreement check (3c),
the unserveable escapes (3d), and the chain-close twins (3e). ZERO live
model calls (transport patched with constructed replies — the Step-28
constructed pattern, run through the REAL call_stage_model validation
path); ZERO docker.

3c — at stage 3's selection site and stage 4's dispatch site, the
     spec-derived structural selection is compared against the payload's
     gate-decided substrate_id; a constructed mismatch stops loudly naming
     both values, BEFORE routing (no model call) / BEFORE execution
     (nothing built, nothing run). PROVEN BY FAILING.
3d — an id the registry can't serve reaches contract_for's existing raises
     FROM STAGE 2'S NEW FETCH: unknown id -> KeyError; enrolled-but-
     contractless id -> LookupError. Never cavity, and no model call is
     ever reached.
3e — chain-close, both twins, call-free on the real code path:
     circuit: chooser record {chosen_id, substrate_id ngspice} -> payload
     -> stage 2 composes with the ngspice contract and its reply spec
     validates under the ngspice vocab (attempt 1, no re-ask) ->
     select_substrate agrees -> stage 3 verdicts -> the maturity hook
     pauses for sign-off (human) / downgrades trust->defer (auto).
     cavity: the same path end-to-end; the composed stage-2 surface is
     byte-identical to the pre-23.5 literal-pin composition (the contract
     object IS the same imported constant), and the hook behaves exactly
     as before.

TRUTH-EDITED under R-23.5-5 (owner, 2026-07-17): the regime placeholder
limitation this docstring used to disclose is RESOLVED — regime meaning is
per-substrate (validation delegates to the vocabulary record), and the
circuit spec fixture now carries its honest named-analysis regime
{analysis_type, notes}. The placeholder-era fixture is preserved as
tests/fixtures/c235/ngspice_full_spec_pre2355.json.

Run directly: venv/bin/python3 tests/test_c235_chain.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
import supervisor
from baton import Baton
from schemas import validate_payload_post_gate1, validate_payload_post_stage2
from stages import stage2_experiment_design as s2
from stages import stage3_fidelity_gate as s3
from substrates import CAVITY_2D_CONTRACT, NGSPICE_LINEAR_PASSIVE_CONTRACT
from tools.substrate_selection import select_substrate

FIX = Path(__file__).resolve().parent / "fixtures" / "c235"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


def _cavity_spec() -> dict:
    return json.loads(
        (
            Path(__file__).resolve().parent.parent
            / "specs"
            / "handcrafted_baseline_qoi.json"
        ).read_text()
    )


def _ngspice_spec() -> dict:
    return json.loads(_fixture("ngspice_full_spec.json"))


class TmpCwdCase(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def make_run_dir(self, run_id: str) -> Path:
        run_dir = Path("runs") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir


class TestAgreementCheckMismatch(TmpCwdCase):
    """3c PROVEN BY FAILING: constructed spec-vs-payload mismatches."""

    def _post_stage2_baton(self, spec: dict, carried: str, run_id: str) -> Baton:
        return Baton(
            run_id=run_id,
            created_at="2026-07-17T00:00:00+00:00",
            mode="auto",
            payload={
                "domain": "constructed",
                "chosen_hypothesis": {
                    "id": spec.get("hypothesis_id", "h1"),
                    "statement": "s",
                    "rationale": "r",
                },
                "substrate_id": carried,
                "experiment_spec": spec,
            },
        )

    def test_stage3_mismatch_stops_before_routing_naming_both(self):
        run_id = "c235-mismatch-s3"
        self.make_run_dir(run_id)
        # An ngspice-selecting spec carried on a cavity-decided payload.
        baton = self._post_stage2_baton(_ngspice_spec(), "cavity_2d_cfd", run_id)
        calls = []
        with patch.object(
            s3, "call_stage_model", side_effect=lambda *a, **k: calls.append(1)
        ):
            with self.assertRaises(RuntimeError) as ctx:
                s3.run(baton)
        message = str(ctx.exception)
        self.assertIn("substrate agreement check failed", message)
        self.assertIn("'ngspice_linear_passive'", message)
        self.assertIn("'cavity_2d_cfd'", message)
        self.assertIn("before routing", message)
        self.assertEqual(calls, [])  # no model call was reached

    def test_stage4_mismatch_stops_before_execution_naming_both(self):
        from stages import stage4_simulation as s4
        from tools import run_cfd as run_cfd_module
        from tools import run_ngspice

        run_id = "c235-mismatch-s4"
        self.make_run_dir(run_id)
        spec = _ngspice_spec()
        baton = self._post_stage2_baton(spec, "cavity_2d_cfd", run_id)
        payload = dict(baton.payload)
        payload["fidelity_verdict"] = {
            "label": "trust",
            "rationale": "constructed",
            "right_instrument": "constructed",
        }
        baton.payload = payload
        wrapper_calls = []
        with patch.object(
            run_ngspice, "run_ngspice",
            side_effect=lambda typed: wrapper_calls.append(typed),
        ), patch.object(
            run_cfd_module, "run_cfd",
            side_effect=lambda case, qoi_request=None: wrapper_calls.append(case),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                s4.run(baton)
        message = str(ctx.exception)
        self.assertIn("substrate agreement check failed", message)
        self.assertIn("'ngspice_linear_passive'", message)
        self.assertIn("'cavity_2d_cfd'", message)
        self.assertIn("before execution", message)
        self.assertEqual(wrapper_calls, [])  # nothing executed
        self.assertFalse(list(Path("cases").glob("*")) if Path("cases").exists() else [])


class TestUnserveableEscapes(TmpCwdCase):
    """3d: the registry's raises fire from stage 2's NEW fetch — never
    cavity, and the model is never called."""

    def _baton(self, substrate_id: str, run_id: str) -> Baton:
        return Baton(
            run_id=run_id,
            created_at="2026-07-17T00:00:00+00:00",
            mode="auto",
            payload={
                "domain": "constructed",
                "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
                "substrate_id": substrate_id,
            },
        )

    def _run_expecting(self, substrate_id: str, exc_type, run_id: str):
        self.make_run_dir(run_id)
        calls = []
        with patch.dict(os.environ, {"BLANK_MEMORY": "1"}):
            with patch.object(
                s2, "call_stage_model", side_effect=lambda *a, **k: calls.append(1)
            ):
                with self.assertRaises(exc_type) as ctx:
                    s2.run(self._baton(substrate_id, run_id))
        self.assertEqual(calls, [])  # the fetch failed before any model call
        return str(ctx.exception)

    def test_unknown_id_raises_keyerror_from_the_new_fetch(self):
        message = self._run_expecting(
            "no_such_instrument", KeyError, "c235-escape-unknown"
        )
        self.assertIn("no_such_instrument", message)
        self.assertNotIn("cavity", message)

    def test_contractless_enrolled_id_raises_lookuperror(self):
        # web_search is enrolled (retrieval-provisional) but has no wired
        # fidelity contract — contract_for's LookupError names the ruling
        # path and forbids the cavity fallback.
        message = self._run_expecting(
            "web_search", LookupError, "c235-escape-contractless"
        )
        self.assertIn("no fidelity contract wired", message)
        self.assertIn("web_search", message)


def _transport_for(replies_by_stage: dict):
    """A fake model_call._invoke_transport keyed by reply queue: pops the
    next canned reply whose marker matches the system prompt. Replies pass
    through the REAL call_stage_model parse/schema/extra_validator path."""

    def fake(system_prompt, user_turn, model):
        for marker, queue in replies_by_stage.items():
            if marker in system_prompt:
                return queue.pop(0)
        raise AssertionError("no canned reply for this system prompt")

    return fake


class ChainCloseCase(TmpCwdCase):
    """3e machinery: drive gate 1 -> apply -> stage 2 -> boundary ->
    stage 3 -> maturity hook on the real code path with constructed
    replies; return the baton and collected evidence."""

    maxDiff = None

    def close_chain(self, *, hyp_id, statement, domain, substrate_id, spec, mode):
        run_id = f"c235-chain-{substrate_id}-{mode}"
        run_dir = self.make_run_dir(run_id)
        baton = Baton(
            run_id=run_id,
            created_at="2026-07-17T00:00:00+00:00",
            mode=mode,
            payload={
                "domain": domain,
                "hypotheses": [
                    {"id": hyp_id, "statement": statement, "rationale": "constructed"}
                ],
                "hypotheses_ranked": True,
            },
        )
        logger = supervisor.Logger(run_dir / "log.txt")

        # Gate 1: the chooser record is constructed (its own call machinery
        # is proven in test_gate1_chooser/test_c235_gate); the supervisor's
        # REAL gate/apply path consumes it.
        with patch.object(
            supervisor.gate1_chooser,
            "choose_hypothesis",
            lambda rid, hyps, rdir: {
                "chosen_id": hyp_id,
                "substrate_id": substrate_id,
                "reasoning": "constructed chain-close record",
                "fallback": False,
            },
        ):
            outcome = supervisor.run_gate1(logger, baton, "auto")
        self.assertEqual(outcome, ("select", 1, substrate_id))
        supervisor.apply_gate1_selection(
            logger, baton, "auto", 1, run_dir, substrate_id=outcome[2]
        )
        self.assertEqual(validate_payload_post_gate1(baton.payload), [])

        # Stage 2 with a constructed reply through the REAL validation path.
        stage2_reply = json.dumps({"ack_run_id": run_id, "spec": spec})
        stage3_reply = json.dumps(
            {
                "ack_run_id": run_id,
                "verdict": {
                    "label": "trust",
                    "rationale": "constructed chain-close verdict",
                    "right_instrument": "yes",
                },
            }
        )
        composed = {}

        real_transport = model_call._invoke_transport

        def capturing_transport(system_prompt, user_turn, model):
            if "Experiment-Design stage" in system_prompt:
                composed.setdefault("stage2_user_turn", user_turn)
                return stage2_reply
            composed.setdefault("stage3_user_turn", user_turn)
            return stage3_reply

        ledger = []
        with patch.dict(os.environ, {"BLANK_MEMORY": "1"}), patch.object(
            model_call, "_invoke_transport", capturing_transport
        ), patch.object(s3, "fidelity_append", lambda **kw: ledger.append(kw)):
            baton = s2.run(baton)
            self.assertEqual(validate_payload_post_stage2(baton.payload), [])
            self.assertEqual(select_substrate(baton.payload["experiment_spec"]),
                             baton.payload["substrate_id"])
            baton = s3.run(baton)
            supervisor.apply_substrate_maturity_hook(logger, baton, mode)

        return baton, composed, ledger, (run_dir / "log.txt").read_text()


class TestChainCloseCircuitTwin(ChainCloseCase):
    def test_ngspice_chain_closes_with_hook(self):
        for mode, expected_label in (("human", "trust"), ("auto", "defer")):
            with self.subTest(mode=mode):
                baton, composed, ledger, log = self.close_chain(
                    hyp_id="hand-ngspice",
                    statement="divider output matches R2/(R1+R2)",
                    domain="linear passive network characterization",
                    substrate_id="ngspice_linear_passive",
                    spec=_ngspice_spec(),
                    mode=mode,
                )
                # stage 2 composed with the ngspice contract (the graduated
                # constant), spec validated under the ngspice vocab on
                # attempt 1 (a re-ask would have hit the empty reply queue).
                sent = json.loads(composed["stage2_user_turn"])
                self.assertEqual(
                    sent["substrate_contract"], NGSPICE_LINEAR_PASSIVE_CONTRACT
                )
                self.assertNotIn("substrate_id", sent)
                # the maturity hook: ngspice is CALIBRATING (non-mature) —
                # human mode pauses for sign-off; auto downgrades to defer.
                self.assertEqual(
                    baton.payload["fidelity_verdict"]["label"], expected_label
                )
                signoff = getattr(baton, "_maturity_signoff", None)
                self.assertTrue(signoff and signoff.get("required"))
                if mode == "human":
                    self.assertIn("NEEDS_HUMAN_SIGNOFF", log)
                else:
                    self.assertIn("MATURITY_DOWNGRADE", log)
                self.assertEqual(len(ledger), 1)  # verdict entered the ledger


class TestChainCloseCavityTwin(ChainCloseCase):
    def test_cavity_chain_closes_byte_identically_with_hook_unchanged(self):
        spec = _cavity_spec()
        for mode, expected_label in (("human", "trust"), ("auto", "defer")):
            with self.subTest(mode=mode):
                baton, composed, ledger, log = self.close_chain(
                    hyp_id="hand-baseline",
                    statement="baseline cavity mean-speed characterization",
                    domain="baseline characterization of laminar lid-driven cavity flows",
                    substrate_id="cavity_2d_cfd",
                    spec=spec,
                    mode=mode,
                )
                sent = json.loads(composed["stage2_user_turn"])
                # BYTE-IDENTITY to the pre-23.5 literal-pin composition:
                # rebuilding the stage_input with the imported cavity
                # constant reproduces the composed user turn exactly.
                reference = dict(sent)
                reference["substrate_contract"] = CAVITY_2D_CONTRACT
                self.assertEqual(
                    composed["stage2_user_turn"], json.dumps(reference)
                )
                self.assertNotIn("substrate_id", sent)
                # hook behavior unchanged: cavity is provisional (non-mature)
                # — the pre-23.5 branch fires identically.
                self.assertEqual(
                    baton.payload["fidelity_verdict"]["label"], expected_label
                )
                if mode == "human":
                    self.assertIn("NEEDS_HUMAN_SIGNOFF", log)
                else:
                    self.assertIn("MATURITY_DOWNGRADE", log)
                self.assertEqual(len(ledger), 1)


if __name__ == "__main__":
    unittest.main()
