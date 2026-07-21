"""
test_b1_flip_promotion.py — THE PACKET B PHASE 1 FLIP (owner "start phase 1"
+ Phase-1.0 ruling line, 2026-07-17): sympy_symbolic_exact routable.

ZERO live model calls (constructed replies through the REAL
call_stage_model validation path — the Step-28/23.5 pattern); ZERO docker.
What is proven here, none of it argued:

  REGISTRY + WIRINGS — the row flip with its ruling record; the routable
  set is three in enrollment order (sympy MID-LIST); contract_for returns
  the substrates.py constant (assertIs) and the onboarding re-export is
  the same object; the §3 regime statement is present and its operation
  enum is DERIVED-checked against run_scipy.OPERATIONS (never retyped
  freely); the vocab record is the symbolic-result shape carrying
  SYMPY_REGIME whose operations ARE the wrapper's allowlist; the signature
  is the wrapper's own field constants and is DISJOINT from every other
  wired signature (the R-B-1 Phase-2 loud stop leans on overlap detection
  being real); all three dispatch maps resolve.

  TRI-STATE CARRIER — sympy_run_entry: solved_verified -> qoi_expression
  (the exact result string, never a float); unevaluated -> qoi_error
  carrying the wrapper's honest-non-answer diagnostics VERBATIM with
  state beside it (ruling item 3); error -> converged=false + qoi_error;
  every entry schema-valid; unknown state / valid-state contradiction /
  missing fields fail loud. `unevaluated` survives the stage-4->5
  boundary and into the composed stage-5 input unmangled, pinned at birth.

  BIRTH PINS — the new model-visible surfaces (stage-2 user turn, stage-3
  system prompt + user turn, stage-5 thought user turn) captured on
  canned sympy batons and pinned byte-identical (the ngspice_birth
  pattern; era record starts at birth).

  CHAIN CLOSE — hypothesis -> chooser record names sympy (constructed) ->
  the real gate/apply -> stage 2 composes under the sympy contract and
  its reply spec validates under the sympy vocabulary, regime enforced ->
  select_substrate agrees -> stage 3 verdicts -> the maturity hook fires
  (calibrating): sign-off pause in human mode, trust->defer in auto.
  (The cavity and ngspice twins are re-shown by tests/test_c235_chain.py,
  green unchanged beside this file.)

  ESCAPES, FIRED — a Reynolds-shaped regime block in a sympy spec rejects
  BY NAME on the production record; a sympy-shaped regime block in an
  ngspice spec rejects BY NAME (production record, ruling item 2); the
  cavity direction rejects loudly via its numeric-bounds complaint (NOT
  by name — cavity's validator body is recorded byte-equal pre-R-23.5-5;
  disclosed); a missing regime rejects; the maturity hook lists all three
  rungs on the real registry.

Run directly: venv/bin/python3 tests/test_b1_flip_promotion.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
import schemas
import substrates
import supervisor
from baton import Baton
from schemas import (
    validate_payload_post_gate1,
    validate_payload_post_stage2,
    validate_payload_post_stage4,
)
from stages import stage2_experiment_design as s2
from stages import stage2_spec
from stages import stage3_fidelity_gate as s3
from stages import stage5_thought_layer as s5
from tools import run_scipy
from tools import substrate_dispatch as dispatch
from tools import substrate_registry as registry
from tools import substrate_selection as selection
from tools.qoi_vocab import (
    SYMPY_REGIME,
    SymbolicResultVocab,
    vocab_for,
)
from tools.substrate_selection import select_substrate

FIX = Path(__file__).resolve().parent / "fixtures" / "sympy_birth"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


def _sympy_spec() -> dict:
    return json.loads(_fixture("sympy_full_spec.json"))


class _Captured(Exception):
    pass


# ---------------------------------------------------------------------------
# Registry + wirings
# ---------------------------------------------------------------------------

class TestFlipRegistry(unittest.TestCase):
    def test_row_flipped_with_ruling_record(self):
        rec = registry.get("sympy_symbolic_exact")
        self.assertTrue(rec.routable)
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertIn("Packet B Phase 1", rec.notes)
        self.assertIn("OperationSetRegime", rec.notes)

    def test_routable_set_in_enrollment_order(self):
        # widened again at the BIO Wave D.4 promotions (owner 2026-07-19):
        # rdkit/cobrapy/homology_search/mafft joined the Packet-B five
        # (enrollment order preserved, homology_search before mafft) — nine
        # routable ids now.
        self.assertEqual(
            registry.routable_ids(),
            ("cavity_2d_cfd", "calculix_cantilever_fea",
             "fenicsx_cantilever_elastic", "sympy_symbolic_exact",
             "ngspice_linear_passive", "rdkit", "cobrapy", "homology_search",
             "mafft", "python_experiment"),  # +code-execution, 2026-07-21
        )

    def test_contract_is_the_graduated_constant_single_source(self):
        self.assertIs(
            registry.contract_for("sympy_symbolic_exact"),
            substrates.SYMPY_SYMBOLIC_EXACT_CONTRACT,
        )
        # the onboarding re-export is the SAME object (assertIs, per the
        # 56e16d9 pattern) — reached through the wrapper's own path-loaded
        # contract module instance
        self.assertIs(
            run_scipy._contract.RUNTIME_CONTRACT_TEXT,
            substrates.SYMPY_SYMBOLIC_EXACT_CONTRACT,
        )

    def test_s3_regime_statement_present_and_derived_from_operations(self):
        text = substrates.SYMPY_SYMBOLIC_EXACT_CONTRACT
        self.assertIn("THIS INSTRUMENT'S REGIME", text)
        self.assertIn("R-23.5-5c", text)
        self.assertIn("Packet B Phase 1.0", text)
        # drift guard: the §3 enum is the wrapper's own allowlist, in the
        # wrapper's own order — whitespace-normalized (the text line-wraps)
        flat = re.sub(r"\s+", " ", text)
        enum = " | ".join(f'"{op}"' for op in run_scipy.OPERATIONS)
        self.assertIn(f'{{"operation": {enum}, "notes": "..."}}', flat)
        # §1's offered-operations line carries the same tuple verbatim
        self.assertIn(
            "Operations offered: " + ", ".join(run_scipy.OPERATIONS), flat
        )
        # and run_scipy.OPERATIONS IS the onboarding contract's S1 tuple
        self.assertIs(run_scipy.OPERATIONS, run_scipy._contract.OPERATIONS)

    def test_vocab_record_is_symbolic_result_with_wrapper_derived_regime(self):
        vocab = vocab_for("sympy_symbolic_exact")
        self.assertIsInstance(vocab, SymbolicResultVocab)
        self.assertIs(vocab.regime, SYMPY_REGIME)
        self.assertEqual(SYMPY_REGIME.operations, tuple(run_scipy.OPERATIONS))

    def test_signature_is_wrapper_derived_and_disjoint_from_every_wired(self):
        sig = selection.signature_for("sympy_symbolic_exact")
        expected = (
            frozenset(run_scipy.UNIVERSAL_REQUIRED_FIELDS)
            | frozenset(run_scipy.UNIVERSAL_OPTIONAL_FIELDS)
            | {
                name
                for fields in run_scipy.OP_FIELDS.values()
                for group in ("required", "optional")
                for name in fields[group]
            }
        )
        self.assertEqual(sig, expected)
        # THE OVERLAP-AWARE STATEMENT (truth-edited at the Packet B Phase 2
        # flip under R-B-1): sympy's signature stays disjoint from EVERY
        # other wired signature — including both cantilevers'. The one
        # deliberate overlap among wired signatures is the cantilever pair
        # itself (asserted exactly in tests/test_b2_flip_promotion.py:
        # FEA's seven a proper subset of fenicsx's eight); the R-B-1 loud
        # stop is what makes that overlap safe.
        for other in ("cavity_2d_cfd", "ngspice_linear_passive",
                      "calculix_cantilever_fea", "fenicsx_cantilever_elastic"):
            self.assertEqual(
                sig & selection.signature_for(other), frozenset(), other
            )

    def test_dispatch_maps_resolve(self):
        self.assertIs(
            dispatch.adapter_for("sympy_symbolic_exact"), dispatch._sympy_adapter
        )
        self.assertIs(
            dispatch.qoi_translation_for("sympy_symbolic_exact"),
            dispatch._sympy_qoi_translation,
        )
        self.assertIs(
            dispatch.run_entry_constructor_for("sympy_symbolic_exact"),
            dispatch.sympy_run_entry,
        )

    def test_only_the_bio_four_are_mature(self):
        # BIO Wave D.4 (owner 2026-07-19): sympy (this flip's subject) stays
        # non-mature; the MATURE substrates are exactly rdkit/cobrapy/mafft/
        # homology_search.
        self.assertFalse(registry.is_mature("sympy_symbolic_exact"))
        mature = {
            r.substrate_id for r in registry.all_substrates()
            if registry.is_mature(r.substrate_id)
        }
        self.assertEqual(
            mature,
            {"rdkit", "cobrapy", "mafft", "homology_search", "python_experiment"},
        )  # +code-execution promotion, 2026-07-21

    def test_full_spec_fixture_validates_under_the_production_vocab(self):
        errors = stage2_spec.validate_spec(
            _sympy_spec(), "hand-sympy", vocab_for("sympy_symbolic_exact")
        )
        self.assertEqual(errors, [])

    def test_selection_resolves_sympy_from_declared_names(self):
        self.assertEqual(select_substrate(_sympy_spec()), "sympy_symbolic_exact")


# ---------------------------------------------------------------------------
# The tri-state carrier
# ---------------------------------------------------------------------------

_SOLVED = {
    "valid": True, "state": "solved_verified", "result": "pi",
    "residual": 3.9e-11, "crosscheck": {"attempted": True, "agrees": True},
    "reason": None,
    "diagnostics": "integrate_definite on 'x*sin(x)': verified via "
                   "diff_back_substitution, residual=3.9e-11 <= 1e-09",
    "runtime_s": 0.71,
}

_UNEVAL = {
    "valid": True, "state": "unevaluated", "result": None,
    "residual": None, "crosscheck": None, "reason": None,
    "diagnostics": "integrate_indefinite: SymPy returned the operation "
                   "unevaluated (an Integral object survives in the output); "
                   "surviving form 'Integral(x**x, x)'. This is an honest "
                   "non-answer, not a failure.",
    "runtime_s": 0.94,
}

_ERROR = {
    "valid": False, "state": "error", "result": None,
    "residual": 0.5, "crosscheck": None, "reason": "verification_failed",
    "diagnostics": "diff: SymPy returned a closed form but verification did "
                   "not close — residual=0.5 via numeric_spot_check, "
                   "tolerance=1e-09.",
    "runtime_s": 0.66,
}


class TestSympyRunEntryTriState(unittest.TestCase):
    def entry_errors(self, entry):
        errors: list[str] = []
        schemas._check_execution_run_entry(entry, "runs[0]", errors)
        return errors

    def test_solved_verified_carries_qoi_expression_verbatim(self):
        entry = dispatch.sympy_run_entry(_SOLVED)
        self.assertEqual(
            entry,
            {"converged": True, "wall_clock_s": 0.71,
             "state": "solved_verified", "qoi_expression": "pi"},
        )
        self.assertEqual(self.entry_errors(entry), [])

    def test_unevaluated_is_converged_with_diagnostics_and_state(self):
        entry = dispatch.sympy_run_entry(_UNEVAL)
        # ruling item 3: qoi_error is the wrapper's own honest-non-answer
        # line VERBATIM; state carries the machine-readable truth beside it
        self.assertEqual(
            entry,
            {"converged": True, "wall_clock_s": 0.94, "state": "unevaluated",
             "qoi_error": _UNEVAL["diagnostics"]},
        )
        self.assertEqual(self.entry_errors(entry), [])

    def test_error_is_unconverged_with_diagnostics_and_state(self):
        entry = dispatch.sympy_run_entry(_ERROR)
        self.assertEqual(
            entry,
            {"converged": False, "wall_clock_s": 0.66, "state": "error",
             "qoi_error": _ERROR["diagnostics"]},
        )
        self.assertEqual(self.entry_errors(entry), [])

    def test_no_bool_overwrites_the_state(self):
        # the named failure of packet rule D.1, proven absent: both
        # valid=true states keep their DISTINCT state strings
        solved = dispatch.sympy_run_entry(_SOLVED)
        uneval = dispatch.sympy_run_entry(_UNEVAL)
        self.assertEqual(solved["converged"], uneval["converged"])  # both True
        self.assertNotEqual(solved["state"], uneval["state"])

    def test_unknown_state_fails_loud(self):
        bad = dict(_SOLVED, state="solved")
        with self.assertRaises(ValueError) as ctx:
            dispatch.sympy_run_entry(bad)
        self.assertIn("state must be one of", str(ctx.exception))

    def test_valid_state_contradiction_fails_loud(self):
        with self.assertRaises(ValueError):
            dispatch.sympy_run_entry(dict(_UNEVAL, valid=False))
        with self.assertRaises(ValueError):
            dispatch.sympy_run_entry(dict(_ERROR, valid=True))

    def test_missing_fields_fail_loud(self):
        with self.assertRaises(ValueError) as ctx:
            dispatch.sympy_run_entry({"valid": True, "state": "unevaluated"})
        self.assertIn("missing", str(ctx.exception))

    def test_solved_without_result_fails_loud(self):
        with self.assertRaises(ValueError):
            dispatch.sympy_run_entry(dict(_SOLVED, result=None))

    def test_non_answer_without_diagnostics_fails_loud(self):
        with self.assertRaises(ValueError):
            dispatch.sympy_run_entry(dict(_UNEVAL, diagnostics=""))

    def test_canned_stage4_results_entry_matches_stage5_fixture(self):
        # chain coherence: the constructor applied to the canned wrapper
        # summary reproduces the canned stage-5 baton's run entry exactly
        results = json.loads(_fixture("canned_stage4_results.json"))
        entry = dispatch.sympy_run_entry(results["runs"][0]["summary"])
        baton = json.loads(_fixture("canned_stage5_input.json"))
        self.assertEqual(
            entry, baton["payload"]["execution_results"]["runs"][0]
        )

    def test_unevaluated_survives_post_stage4_boundary(self):
        payload = json.loads(_fixture("canned_stage5_input.json"))["payload"]
        self.assertEqual(validate_payload_post_stage4(payload), [])
        self.assertEqual(
            payload["execution_results"]["runs"][0]["state"], "unevaluated"
        )


# ---------------------------------------------------------------------------
# Birth pins — the new model-visible surfaces
# ---------------------------------------------------------------------------

def _capture_stage(module, baton_fixture, materialize_results=False):
    baton = Baton.from_json(_fixture(baton_fixture))
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="b1_birth_")
    try:
        os.chdir(tmp)
        if materialize_results:
            d = Path("runs") / baton.run_id / "stage4"
            d.mkdir(parents=True)
            shutil.copy(FIX / "canned_stage4_results.json", d / "results.json")
        with patch.dict(os.environ, {"BLANK_MEMORY": "1"}):
            with patch.object(module, "call_stage_model", side_effect=_capture):
                try:
                    module.run(baton)
                except _Captured:
                    pass
                else:
                    raise AssertionError(
                        "call_stage_model was never reached — assembly did not run"
                    )
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    return captured["system_prompt"], json.dumps(captured["stage_input"])


class TestSympyBirthPins(unittest.TestCase):
    def test_stage2_user_turn_byte_identical(self):
        _, user_turn = _capture_stage(s2, "canned_stage2_input.json")
        self.assertEqual(user_turn, _fixture("stage2_user_turn.txt"))
        sent = json.loads(user_turn)
        self.assertEqual(
            sent["substrate_contract"], substrates.SYMPY_SYMBOLIC_EXACT_CONTRACT
        )
        self.assertNotIn("substrate_id", sent)

    def test_stage3_pair_byte_identical(self):
        system_prompt, user_turn = _capture_stage(s3, "canned_stage3_input.json")
        self.assertEqual(system_prompt, _fixture("stage3_system_prompt.txt"))
        self.assertEqual(user_turn, _fixture("stage3_user_turn.txt"))
        # the frozen judgment prompt is substrate-independent
        self.assertIs(system_prompt, s3.SYSTEM_PROMPT)
        parsed = json.loads(user_turn)
        self.assertEqual(
            parsed["substrate_contract"],
            substrates.SYMPY_SYMBOLIC_EXACT_CONTRACT,
        )

    def test_stage5_user_turn_byte_identical_with_tri_state_unmangled(self):
        _, user_turn = _capture_stage(
            s5, "canned_stage5_input.json", materialize_results=True
        )
        self.assertEqual(user_turn, _fixture("thought_user_turn.txt"))
        sent = json.loads(user_turn)
        # `unevaluated` reaches the composed stage-5 input VERBATIM, in
        # both the conclusions entry and the full wrapper summary
        entry = sent["execution_results"]["runs"][0]
        self.assertEqual(entry["state"], "unevaluated")
        self.assertEqual(
            entry["qoi_error"],
            json.loads(_fixture("canned_stage4_results.json"))
            ["runs"][0]["summary"]["diagnostics"],
        )
        self.assertEqual(sent["stage4_summaries"][0]["state"], "unevaluated")

    def test_birth_composition_deterministic(self):
        self.assertEqual(
            _capture_stage(s3, "canned_stage3_input.json"),
            _capture_stage(s3, "canned_stage3_input.json"),
        )

    def test_stage3_selection_agrees_on_the_real_registry(self):
        baton = Baton.from_json(_fixture("canned_stage3_input.json"))
        self.assertEqual(
            select_substrate(baton.payload["experiment_spec"]),
            "sympy_symbolic_exact",
        )


# ---------------------------------------------------------------------------
# Chain close (the c235 machinery, sympy twin)
# ---------------------------------------------------------------------------

class TestChainCloseSympy(unittest.TestCase):
    maxDiff = None

    def close_chain(self, mode):
        spec = _sympy_spec()
        run_id = f"b1-chain-sympy-{mode}"
        old_cwd = os.getcwd()
        tmp = tempfile.mkdtemp(prefix="b1_chain_")
        try:
            os.chdir(tmp)
            run_dir = Path("runs") / run_id
            run_dir.mkdir(parents=True)
            baton = Baton(
                run_id=run_id,
                created_at="2026-07-17T00:00:00+00:00",
                mode=mode,
                payload={
                    "domain": "exact symbolic evaluation of closed-form integrals",
                    "hypotheses": [
                        {"id": "hand-sympy",
                         "statement": "The definite integral of x*sin(x) over "
                                      "[0, pi] equals pi exactly.",
                         "rationale": "constructed"}
                    ],
                    "hypotheses_ranked": True,
                },
            )
            logger = supervisor.Logger(run_dir / "log.txt")

            with patch.object(
                supervisor.gate1_chooser,
                "choose_hypothesis",
                lambda rid, hyps, rdir: {
                    "chosen_id": "hand-sympy",
                    "substrate_id": "sympy_symbolic_exact",
                    "reasoning": "constructed chain-close record",
                    "fallback": False,
                },
            ):
                outcome = supervisor.run_gate1(logger, baton, "auto")
            self.assertEqual(outcome, ("select", 1, "sympy_symbolic_exact"))
            supervisor.apply_gate1_selection(
                logger, baton, "auto", 1, run_dir, substrate_id=outcome[2]
            )
            self.assertEqual(validate_payload_post_gate1(baton.payload), [])

            stage2_reply = json.dumps({"ack_run_id": run_id, "spec": spec})
            stage3_reply = json.dumps(
                {"ack_run_id": run_id,
                 "verdict": {"label": "trust",
                             "rationale": "constructed chain-close verdict",
                             "right_instrument": "yes"}}
            )
            composed: dict = {}

            def transport(system_prompt, user_turn, model):
                if "Experiment-Design stage" in system_prompt:
                    composed.setdefault("stage2_user_turn", user_turn)
                    return stage2_reply
                composed.setdefault("stage3_user_turn", user_turn)
                return stage3_reply

            ledger: list = []
            with patch.dict(os.environ, {"BLANK_MEMORY": "1"}), patch.object(
                model_call, "_invoke_transport", transport
            ), patch.object(s3, "fidelity_append", lambda **kw: ledger.append(kw)):
                baton = s2.run(baton)
                self.assertEqual(validate_payload_post_stage2(baton.payload), [])
                self.assertEqual(
                    select_substrate(baton.payload["experiment_spec"]),
                    baton.payload["substrate_id"],
                )
                baton = s3.run(baton)
                supervisor.apply_substrate_maturity_hook(logger, baton, mode)

            return baton, composed, ledger, (run_dir / "log.txt").read_text()
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sympy_chain_closes_with_hook(self):
        for mode, expected_label in (("human", "trust"), ("auto", "defer")):
            with self.subTest(mode=mode):
                baton, composed, ledger, log = self.close_chain(mode)
                # stage 2 composed with the sympy contract (the graduated
                # constant); the reply spec validated under the sympy
                # vocabulary — regime enforced — on attempt 1 (a re-ask
                # would have hit the queue-less transport a second time)
                sent = json.loads(composed["stage2_user_turn"])
                self.assertEqual(
                    sent["substrate_contract"],
                    substrates.SYMPY_SYMBOLIC_EXACT_CONTRACT,
                )
                self.assertNotIn("substrate_id", sent)
                # maturity hook fires at calibrating: pause / downgrade
                self.assertEqual(
                    baton.payload["fidelity_verdict"]["label"], expected_label
                )
                signoff = getattr(baton, "_maturity_signoff", None)
                self.assertTrue(signoff and signoff.get("required"))
                self.assertEqual(
                    signoff["substrates"],
                    ["cavity_2d_cfd@provisional",
                     "calculix_cantilever_fea@calibrating",
                     "fenicsx_cantilever_elastic@calibrating",
                     "sympy_symbolic_exact@calibrating",
                     "ngspice_linear_passive@calibrating"],
                )
                if mode == "human":
                    self.assertIn("NEEDS_HUMAN_SIGNOFF", log)
                    self.assertNotIn("MATURITY_DOWNGRADE", log)
                else:
                    self.assertIn("MATURITY_DOWNGRADE [auto]", log)
                self.assertEqual(len(ledger), 1)


# ---------------------------------------------------------------------------
# Escapes, fired on the production records
# ---------------------------------------------------------------------------

class TestProductionEscapes(unittest.TestCase):
    def test_reynolds_block_in_sympy_spec_rejects_by_name(self):
        spec = _sympy_spec()
        spec["regime"] = {"reynolds_min": 100, "reynolds_max": 200, "notes": "n"}
        errors = stage2_spec.validate_spec(
            spec, "hand-sympy", vocab_for("sympy_symbolic_exact")
        )
        named = [e for e in errors if "not part of this substrate's regime" in e]
        self.assertEqual(len(named), 2)
        for e in named:
            self.assertIn("not a Reynolds band and not a circuit analysis", e)

    def test_analysis_type_block_in_sympy_spec_rejects_by_name(self):
        spec = _sympy_spec()
        spec["regime"] = {"analysis_type": "op", "notes": "n"}
        errors = stage2_spec.validate_spec(
            spec, "hand-sympy", vocab_for("sympy_symbolic_exact")
        )
        self.assertTrue(
            any("regime field 'analysis_type' is not part of" in e for e in errors)
        )

    def test_sympy_operation_key_in_ngspice_regime_rejects_by_name(self):
        errors: list[str] = []
        stage2_spec._validate_regime(
            {"operation": "diff", "notes": "n"},
            vocab_for("ngspice_linear_passive"),
            errors,
        )
        self.assertTrue(
            any("regime field 'operation' is not part of" in e for e in errors)
        )

    def test_sympy_regime_in_cavity_spec_rejects_loudly_not_by_name(self):
        # DISCLOSED asymmetry (Phase-1.0 ruling item 2): cavity's validator
        # body is recorded byte-equal pre-R-23.5-5, so the rejection is its
        # generic numeric-bounds complaint — loud, but not by name.
        errors: list[str] = []
        stage2_spec._validate_regime(
            {"operation": "diff", "notes": "n"},
            vocab_for("cavity_2d_cfd"),
            errors,
        )
        self.assertTrue(errors)
        self.assertTrue(
            any("reynolds_min and reynolds_max must be numbers" in e
                for e in errors)
        )

    def test_missing_regime_rejects(self):
        spec = _sympy_spec()
        del spec["regime"]
        errors = stage2_spec.validate_spec(
            spec, "hand-sympy", vocab_for("sympy_symbolic_exact")
        )
        self.assertTrue(any("regime" in e and "missing" in e for e in errors))

    def test_machine_keys_from_both_grammars_reject_in_sympy_qoi(self):
        spec = _sympy_spec()
        spec["qoi"] = dict(spec["qoi"], kind="node_voltage", field="U")
        errors = stage2_spec.validate_spec(
            spec, "hand-sympy", vocab_for("sympy_symbolic_exact")
        )
        self.assertTrue(
            any("different substrate class's QoI grammar" in e for e in errors)
        )

    def test_adapter_rejects_unknown_params_by_name(self):
        with self.assertRaises(ValueError) as ctx:
            dispatch._sympy_adapter(
                "sympy_symbolic_exact",
                {"operation": "diff", "mesh_resolution": 64},
                "case", {}, {"symbolic_result": True},
            )
        self.assertIn("mesh_resolution", str(ctx.exception))

    def test_qoi_translation_accepts_prose_and_refuses_non_object(self):
        request, refusal = dispatch._sympy_qoi_translation(
            _sympy_spec()["qoi"], vocab_for("sympy_symbolic_exact")
        )
        self.assertEqual(request, {"symbolic_result": True})
        self.assertIsNone(refusal)
        request, refusal = dispatch._sympy_qoi_translation(
            "free text", vocab_for("sympy_symbolic_exact")
        )
        self.assertIsNone(request)
        self.assertIn("must be an object", refusal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
