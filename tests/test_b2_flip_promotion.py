"""
test_b2_flip_promotion.py — THE PACKET B PHASE 2 FLIP (owner "start phase 1"
pair unit + R-B-1 + the Phase-2.0 ruling line, build chat under the owner's
standing delegation, 2026-07-17): the cantilever pair routable.

ZERO live model calls (constructed replies through the REAL
call_stage_model validation path — the b1/Step-28/23.5 pattern); ZERO
docker (every wrapper touch below rejects at _validate_input, before any
container call). What is proven here, none of it argued:

  REGISTRY + WIRINGS — both row flips with their ruling records and battery
  evidence lines; the routable set is FIVE in enrollment order; contract_for
  returns the substrates.py constants (assertIs); the fenicsx graduated
  contract is COMPOSED from the onboarding module's own section constants
  (path-loaded — one source; the battery-facing composed constants stay
  byte-identical, proven against a fresh load of the module); both §3
  regime statements present, derivation-tested against the wrappers' own
  constants (QOI_FIELDS names, the FEA seven / fenicsx eight); calculix §3
  carries C3D8I and the v2.23-docs-vs-v2.17-solver honesty; fenicsx §3
  carries G5 and the G1<->G5 tension; all three dispatch maps resolve for
  both ids.

  THE OVERLAP + THE TIE (R-B-1 / E3) — the ONE deliberate overlap among
  wired signatures asserted exactly (FEA's seven a proper subset of
  fenicsx's eight, difference == {element_degree}); an 8-field spec
  deterministically resolves fenicsx; the 7-field spec stops LOUDLY at
  BOTH decision twins (stage 3 before routing, stage 4 before execution) —
  reported as the correct outcome, not worked around; a synthetic mature
  candidate resolves the tie on the REAL registry (Step 28's first half,
  nothing really promoted); calculix's machinery is proven sound
  end-to-end in a constructed registry where it is the SOLE cantilever.

  FIXED-SUMMARY ENTRY CONSTRUCTOR — converged := valid; the additive
  qoi_request names which of the two returned numbers becomes qoi_value;
  no-request files honestly under the fallback; valid=false carries the
  wrapper's own diagnostics; every malformed summary fails loud; entries
  schema-valid; the canned chain fixtures cohere.

  BIRTH PINS — the new model-visible surfaces (fenicsx stage-2 user turn,
  stage-3 pair, stage-5 thought user turn; calculix stage-2 user turn)
  captured on canned batons and pinned byte-identical. Calculix has NO
  stage-3 birth pin BY DESIGN: its 7-field spec stops at selection under
  R-B-1, so no production stage-3 surface exists to pin.

  CHAIN CLOSE (E2) — fenicsx closes end-to-end call-free: chooser record ->
  real gate/apply -> stage 2 composes under the graduated contract ->
  reply spec validates under the fixed-summary vocabulary, regime
  enforced -> select_substrate agrees -> stage 3 verdicts -> the maturity
  hook fires at calibrating with FIVE rungs (sign-off pause in human,
  trust->defer in auto). Calculix runs to the loud stop. Cavity, ngspice,
  and sympy twins are re-shown by their own suites, green unchanged.

  ESCAPES, FIRED (E5) — alien regime blocks reject BY NAME in every ruled
  direction on the production records; missing regime rejects; foreign
  machine keys reject; unknown quantity refuses; adapters reject unknown
  params by name; missing typed fields come back as the wrappers' OWN
  named rejections through the adapters (docker-free); no cavity fallback
  anywhere.

Run directly: venv/bin/python3 tests/test_b2_flip_promotion.py
"""

from __future__ import annotations

import importlib.util
import json
import os
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
from stages import stage4_simulation as s4
from stages import stage5_thought_layer as s5
from tools import run_fea
from tools import run_fenicsx
from tools import substrate_dispatch as dispatch
from tools import substrate_registry as registry
from tools import substrate_selection as selection
from tools.qoi_vocab import (
    FixedSummaryVocab,
    StaticSmallDeflectionRegime,
    vocab_for,
)
from tools.substrate_selection import select_substrate

FEA = "calculix_cantilever_fea"
FENICSX = "fenicsx_cantilever_elastic"
FIVE_RUNGS = [
    "cavity_2d_cfd@provisional",
    "calculix_cantilever_fea@calibrating",
    "fenicsx_cantilever_elastic@calibrating",
    "sympy_symbolic_exact@calibrating",
    "ngspice_linear_passive@calibrating",
]

FX_FIX = Path(__file__).resolve().parent / "fixtures" / "fenicsx_birth"
FEA_FIX = Path(__file__).resolve().parent / "fixtures" / "fea_birth"


def _fx(name: str) -> str:
    return (FX_FIX / name).read_text()


def _fea(name: str) -> str:
    return (FEA_FIX / name).read_text()


def _fenicsx_spec() -> dict:
    return json.loads(_fx("fenicsx_full_spec.json"))


def _fea_spec() -> dict:
    return json.loads(_fea("fea_full_spec.json"))


class _Captured(Exception):
    pass


# ---------------------------------------------------------------------------
# Registry + wirings
# ---------------------------------------------------------------------------

class TestFlipRegistry(unittest.TestCase):
    def test_rows_flipped_with_ruling_records(self):
        for sid, battery in (
            (FEA, "calibration_calculix_cantilever_fea_20260716T053643Z.json"),
            (FENICSX,
             "calibration_fenicsx_cantilever_elastic_20260717T125837Z.json"),
        ):
            rec = registry.get(sid)
            self.assertTrue(rec.routable, sid)
            self.assertEqual(rec.maturity, registry.CALIBRATING, sid)
            self.assertIn("Packet B Phase 2", rec.notes)
            self.assertIn("R-B-1", rec.notes)
            self.assertIn("StaticSmallDeflectionRegime", rec.notes)
            self.assertIn(battery, rec.notes)

    def test_routable_set_in_enrollment_order(self):
        # BIO Wave D.4 (owner 2026-07-19): rdkit/cobrapy/homology_search/mafft
        # joined the Packet-B five (enrollment order preserved, homology_search
        # before mafft) — nine routable ids now.
        self.assertEqual(
            registry.routable_ids(),
            ("cavity_2d_cfd", FEA, FENICSX, "sympy_symbolic_exact",
             "ngspice_linear_passive", "rdkit", "cobrapy", "homology_search",
             "mafft", "python_experiment"),  # +code-execution, 2026-07-21
        )

    def test_contract_for_returns_the_graduated_constants(self):
        self.assertIs(
            registry.contract_for(FEA),
            substrates.CALCULIX_CANTILEVER_FEA_CONTRACT,
        )
        self.assertIs(
            registry.contract_for(FENICSX),
            substrates.FENICSX_CANTILEVER_ELASTIC_CONTRACT,
        )

    def test_fenicsx_contract_composed_from_the_onboarding_sections(self):
        # ONE SOURCE: the graduated contract embeds the path-loaded
        # onboarding module's own section constants VERBATIM (assertIs on
        # substrates' loaded module handle; assertIn on the composed text)…
        m = substrates._fenicsx_sections
        for section in (m._INSTRUMENT, m._CASE_DEFINITION, m._RETURNS,
                        m._LIMITS, m._VOCABULARY):
            self.assertIn(section, substrates.FENICSX_CANTILEVER_ELASTIC_CONTRACT)

    def test_battery_composed_constants_byte_identical_to_fresh_load(self):
        # …and the four battery-composed constants are byte-identical to a
        # FRESH load of the onboarding module (binding Phase-2 ruling
        # constraint 5: the executed battery's text is unmoved — the §3
        # additions land OUTSIDE the composed constants).
        path = (Path(__file__).resolve().parent.parent / "onboarding"
                / "fenicsx_cantilever_elastic" / "contract.py")
        spec = importlib.util.spec_from_file_location("_b2_fresh_contract", path)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        m = substrates._fenicsx_sections
        self.assertEqual(m.SUBSTRATE_TEXT, fresh.SUBSTRATE_TEXT)
        self.assertEqual(m.ENVELOPE_TEXT, fresh.ENVELOPE_TEXT)
        # the §3 additions are NOT in either battery-facing composition
        self.assertNotIn("THIS INSTRUMENT'S REGIME", fresh.SUBSTRATE_TEXT)
        self.assertNotIn("THIS INSTRUMENT'S REGIME", fresh.ENVELOPE_TEXT)

    def test_section3_regime_statements_present_and_derivation_tested(self):
        for sid, contract, qoi_fields in (
            (FEA, substrates.CALCULIX_CANTILEVER_FEA_CONTRACT,
             run_fea.QOI_FIELDS),
            (FENICSX, substrates.FENICSX_CANTILEVER_ELASTIC_CONTRACT,
             run_fenicsx.QOI_FIELDS),
        ):
            self.assertIn("THIS INSTRUMENT'S REGIME", contract, sid)
            self.assertIn("R-23.5-5c", contract, sid)
            self.assertIn('{"notes": "..."}', contract, sid)
            # the quantity enum is DERIVED from the wrapper's own constant,
            # never retyped freely: both names must appear in §3's text
            for name in qoi_fields:
                self.assertIn(name, contract, sid)
            self.assertIn('"quantity"', contract, sid)

    def test_calculix_section3_carries_c3d8i_and_version_skew(self):
        c = substrates.CALCULIX_CANTILEVER_FEA_CONTRACT
        self.assertIn("C3D8I", c)
        self.assertIn("v2.23", c)
        self.assertIn("v2.17", c)

    def test_fenicsx_section3_carries_g5_and_the_tension(self):
        c = substrates.FENICSX_CANTILEVER_ELASTIC_CONTRACT
        self.assertIn("ELEMENT-ORDER BOUND (G5)", c)
        self.assertIn("element_degree >= 2", c)
        self.assertIn("routing to this substrate is unsafe", c)
        # the G1<->G5 tension, un-glossed
        self.assertIn("both are true at once", c)

    def test_vocab_records_are_fixed_summary_with_wrapper_names(self):
        for sid, wrapper_fields in (
            (FEA, run_fea.QOI_FIELDS), (FENICSX, run_fenicsx.QOI_FIELDS)
        ):
            vocab = vocab_for(sid)
            self.assertIsInstance(vocab, FixedSummaryVocab, sid)
            self.assertIsInstance(vocab.regime, StaticSmallDeflectionRegime, sid)
            # tuple(t) of a tuple IS the tuple — single source by identity
            self.assertIs(vocab.names, wrapper_fields, sid)

    def test_signatures_wrapper_derived_with_the_one_ruled_overlap(self):
        fea_sig = selection.signature_for(FEA)
        fx_sig = selection.signature_for(FENICSX)
        self.assertEqual(fea_sig, frozenset(run_fea._REQUIRED_FIELDS))
        self.assertEqual(fx_sig, frozenset(run_fenicsx._REQUIRED_FIELDS))
        # THE OVERLAP, exactly: FEA's seven a PROPER SUBSET of fenicsx's
        # eight; the one extra name is the regime-boundary field.
        self.assertEqual(fea_sig - fx_sig, frozenset())
        self.assertEqual(fx_sig - fea_sig, frozenset({"element_degree"}))
        # and both stay disjoint from every OTHER wired signature
        for other in ("cavity_2d_cfd", "sympy_symbolic_exact",
                      "ngspice_linear_passive"):
            other_sig = selection.signature_for(other)
            self.assertEqual(fea_sig & other_sig, frozenset(), other)
            self.assertEqual(fx_sig & other_sig, frozenset(), other)

    def test_dispatch_maps_resolve_for_both(self):
        self.assertIs(dispatch.adapter_for(FEA), dispatch._fea_adapter)
        self.assertIs(dispatch.adapter_for(FENICSX), dispatch._fenicsx_adapter)
        self.assertIs(
            dispatch.qoi_translation_for(FEA),
            dispatch._fixed_summary_qoi_translation,
        )
        self.assertIs(
            dispatch.run_entry_constructor_for(FENICSX),
            dispatch.fixed_summary_run_entry,
        )

    def test_full_spec_fixtures_validate_under_the_production_vocabs(self):
        self.assertEqual(
            stage2_spec.validate_spec(_fenicsx_spec(), "hand-fenicsx",
                                      vocab_for(FENICSX)),
            [],
        )
        self.assertEqual(
            stage2_spec.validate_spec(_fea_spec(), "hand-fea", vocab_for(FEA)),
            [],
        )

    def test_only_the_bio_four_are_mature(self):
        # BIO Wave D.4 (owner 2026-07-19): the cantilever pair (this flip's
        # subject) stays non-mature; the MATURE substrates are exactly
        # rdkit/cobrapy/mafft/homology_search.
        self.assertFalse(registry.is_mature(FEA))
        self.assertFalse(registry.is_mature(FENICSX))
        mature = {
            r.substrate_id for r in registry.all_substrates()
            if registry.is_mature(r.substrate_id)
        }
        self.assertEqual(
            mature,
            {"rdkit", "cobrapy", "mafft", "homology_search", "python_experiment"},
        )  # +code-execution promotion, 2026-07-21


# ---------------------------------------------------------------------------
# The tie (E3): deterministic where determinable, loudly stopped where not
# ---------------------------------------------------------------------------

class TestTheTie(unittest.TestCase):
    def test_eight_field_spec_deterministically_resolves_fenicsx(self):
        self.assertEqual(select_substrate(_fenicsx_spec()), FENICSX)

    def test_seven_field_spec_stops_loudly_at_selection(self):
        with self.assertRaises(LookupError) as ctx:
            select_substrate(_fea_spec())
        msg = str(ctx.exception)
        self.assertIn("ambiguous (R-B-1", msg)
        self.assertIn(f"{FEA}@calibrating", msg)
        self.assertIn(f"{FENICSX}@calibrating", msg)
        self.assertIn("stopping before routing", msg)

    def test_stage3_twin_stops_before_routing(self):
        # decision twin 1: the calculix chain's stage 3 raises at selection
        # BEFORE any model call — the correct outcome, not worked around.
        baton = Baton.from_json(_fea("canned_stage2_input.json"))
        payload = dict(baton.payload)
        payload["experiment_spec"] = _fea_spec()
        baton.payload = payload
        with self.assertRaises(LookupError) as ctx:
            s3.run(baton)
        self.assertIn("ambiguous (R-B-1", str(ctx.exception))

    def test_stage4_twin_stops_before_execution(self):
        # decision twin 2: stage 4 with a forced-trust verdict raises at
        # its re-derivation, before any adapter/wrapper touch.
        baton = Baton.from_json(_fea("canned_stage2_input.json"))
        payload = dict(baton.payload)
        payload["experiment_spec"] = _fea_spec()
        payload["fidelity_verdict"] = {
            "label": "trust", "rationale": "constructed twin-stop fixture",
            "right_instrument": "yes",
        }
        baton.payload = payload
        old_cwd = os.getcwd()
        tmp = tempfile.mkdtemp(prefix="b2_twin_")
        try:
            os.chdir(tmp)
            (Path("runs") / baton.run_id).mkdir(parents=True)
            with self.assertRaises(LookupError) as ctx:
                s4.run(baton)
            self.assertIn("ambiguous (R-B-1", str(ctx.exception))
            # nothing executed: no case dirs, no results.json survived
            self.assertFalse(
                (Path("runs") / baton.run_id / "stage4" / "results.json").exists()
            )
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_synthetic_mature_candidate_resolves_on_the_real_registry(self):
        # Step 28's first half on the REAL registry: patch maturity only —
        # the mature cantilever uniquely resolves the 7-field pool and the
        # raise does not fire. Nothing really promoted, both directions.
        for mature_one in (FEA, FENICSX):
            with patch.object(registry, "is_mature",
                              side_effect=lambda sid: sid == mature_one):
                self.assertEqual(
                    select_substrate(_fea_spec()), mature_one, mature_one
                )

    def test_calculix_sound_as_sole_cantilever_in_a_constructed_registry(self):
        # E2: calculix's machinery proven end-to-end (call-free) in a
        # registry where it is the SOLE cantilever — selection resolves it
        # uniquely, stage 3's composition carries ITS contract, and the
        # entry constructor lands its measured number as qoi_value.
        four_ids = ("cavity_2d_cfd", FEA, "sympy_symbolic_exact",
                    "ngspice_linear_passive")
        with patch.object(registry, "routable_ids", return_value=four_ids):
            self.assertEqual(select_substrate(_fea_spec()), FEA)
            sid, contract_text = s3._selected_contract(_fea_spec())
            self.assertEqual(sid, FEA)
            self.assertIs(
                contract_text, substrates.CALCULIX_CANTILEVER_FEA_CONTRACT
            )
        # the card §3A mesh-8 measured numbers, in the wrapper's own shape
        summary = {
            "valid": True,
            "qoi": {"tip_displacement": 0.003002929, "max_von_mises": 2.521e7},
            "diagnostics": "ccx C3D8I mesh 8x1x1 (36 nodes, 8 elements); "
                           "solver completed, 36 displacement rows parsed",
            "runtime_s": 0.201,
        }
        request, refusal = dispatch._fixed_summary_qoi_translation(
            _fea_spec()["qoi"], vocab_for(FEA)
        )
        self.assertIsNone(refusal)
        entry = dispatch.fixed_summary_run_entry(summary, None, request)
        self.assertEqual(
            entry,
            {"converged": True, "wall_clock_s": 0.201,
             "qoi_value": 0.003002929},
        )
        errors: list[str] = []
        schemas._check_execution_run_entry(entry, "runs[0]", errors)
        self.assertEqual(errors, [])


# ---------------------------------------------------------------------------
# The fixed-summary entry constructor
# ---------------------------------------------------------------------------

_VALID_SUMMARY = {
    "valid": True,
    "qoi": {"tip_displacement": 0.003007857, "max_von_mises": 4.246e7},
    "diagnostics": "dolfinx 0.11.0.post0 Lagrange degree 2 hex mesh 8x1x1 "
                   "(8 cells, 425 dofs); scalar=float64; von Mises "
                   "interpolated into DG1; solve 0.024s",
    "runtime_s": 0.705,
}

_INVALID_SUMMARY = {
    "valid": False,
    "qoi": None,
    "diagnostics": "input rejected: missing required field(s): element_degree",
    "runtime_s": 0.001,
}


class TestFixedSummaryRunEntry(unittest.TestCase):
    def entry_errors(self, entry):
        errors: list[str] = []
        schemas._check_execution_run_entry(entry, "runs[0]", errors)
        return errors

    def test_request_picks_the_requested_number(self):
        for quantity, value in (("tip_displacement", 0.003007857),
                                ("max_von_mises", 4.246e7)):
            entry = dispatch.fixed_summary_run_entry(
                _VALID_SUMMARY, None, {"quantity": quantity}
            )
            self.assertEqual(
                entry,
                {"converged": True, "wall_clock_s": 0.705, "qoi_value": value},
                quantity,
            )
            self.assertEqual(self.entry_errors(entry), [])

    def test_no_request_files_honestly_under_the_fallback(self):
        entry = dispatch.fixed_summary_run_entry(
            _VALID_SUMMARY, "QoI 'tip displacement' not extractable by "
                            "contract: no quantity key", None
        )
        self.assertEqual(entry["converged"], True)
        self.assertIn("not extractable", entry["qoi_error"])
        self.assertNotIn("qoi_value", entry)
        self.assertEqual(self.entry_errors(entry), [])

    def test_invalid_run_carries_the_wrappers_own_named_rejection(self):
        entry = dispatch.fixed_summary_run_entry(
            _INVALID_SUMMARY, None, {"quantity": "tip_displacement"}
        )
        self.assertEqual(
            entry,
            {"converged": False, "wall_clock_s": 0.001,
             "qoi_error": _INVALID_SUMMARY["diagnostics"]},
        )
        self.assertEqual(self.entry_errors(entry), [])

    def test_missing_fields_fail_loud(self):
        with self.assertRaises(ValueError) as ctx:
            dispatch.fixed_summary_run_entry({"valid": True}, None, None)
        self.assertIn("missing", str(ctx.exception))

    def test_requested_quantity_absent_from_qoi_fails_loud(self):
        broken = dict(_VALID_SUMMARY, qoi={"tip_displacement": 0.003})
        with self.assertRaises(ValueError) as ctx:
            dispatch.fixed_summary_run_entry(
                broken, None, {"quantity": "max_von_mises"}
            )
        self.assertIn("refusing to substitute", str(ctx.exception))

    def test_non_numeric_quantity_fails_loud(self):
        broken = dict(_VALID_SUMMARY,
                      qoi={"tip_displacement": "big", "max_von_mises": 1.0})
        with self.assertRaises(ValueError):
            dispatch.fixed_summary_run_entry(
                broken, None, {"quantity": "tip_displacement"}
            )

    def test_neither_request_nor_fallback_fails_loud(self):
        with self.assertRaises(ValueError) as ctx:
            dispatch.fixed_summary_run_entry(_VALID_SUMMARY, None, None)
        self.assertIn("refusing to pick a number silently", str(ctx.exception))

    def test_canned_stage4_results_entry_matches_stage5_fixture(self):
        results = json.loads(_fx("canned_stage4_results.json"))
        entry = dispatch.fixed_summary_run_entry(
            results["runs"][0]["summary"], None, results["qoi_request"]
        )
        baton = json.loads(_fx("canned_stage5_input.json"))
        self.assertEqual(
            entry, baton["payload"]["execution_results"]["runs"][0]
        )

    def test_qoi_value_survives_post_stage4_boundary(self):
        payload = json.loads(_fx("canned_stage5_input.json"))["payload"]
        self.assertEqual(validate_payload_post_stage4(payload), [])
        self.assertEqual(
            payload["execution_results"]["runs"][0]["qoi_value"], 0.003007857
        )


# ---------------------------------------------------------------------------
# Birth pins — the new model-visible surfaces
# ---------------------------------------------------------------------------

def _capture_stage(module, fixture_dir, baton_fixture, materialize_results=False):
    baton = Baton.from_json((fixture_dir / baton_fixture).read_text())
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="b2_birth_")
    try:
        os.chdir(tmp)
        if materialize_results:
            d = Path("runs") / baton.run_id / "stage4"
            d.mkdir(parents=True)
            shutil.copy(fixture_dir / "canned_stage4_results.json",
                        d / "results.json")
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


class TestCantileverBirthPins(unittest.TestCase):
    def test_fenicsx_stage2_user_turn_byte_identical(self):
        _, user_turn = _capture_stage(s2, FX_FIX, "canned_stage2_input.json")
        self.assertEqual(user_turn, _fx("stage2_user_turn.txt"))
        sent = json.loads(user_turn)
        self.assertEqual(
            sent["substrate_contract"],
            substrates.FENICSX_CANTILEVER_ELASTIC_CONTRACT,
        )
        self.assertNotIn("substrate_id", sent)

    def test_fea_stage2_user_turn_byte_identical(self):
        _, user_turn = _capture_stage(s2, FEA_FIX, "canned_stage2_input.json")
        self.assertEqual(user_turn, _fea("stage2_user_turn.txt"))
        sent = json.loads(user_turn)
        self.assertEqual(
            sent["substrate_contract"],
            substrates.CALCULIX_CANTILEVER_FEA_CONTRACT,
        )
        self.assertNotIn("substrate_id", sent)

    def test_fenicsx_stage3_pair_byte_identical(self):
        system_prompt, user_turn = _capture_stage(
            s3, FX_FIX, "canned_stage3_input.json"
        )
        self.assertEqual(system_prompt, _fx("stage3_system_prompt.txt"))
        self.assertEqual(user_turn, _fx("stage3_user_turn.txt"))
        self.assertIs(system_prompt, s3.SYSTEM_PROMPT)
        parsed = json.loads(user_turn)
        self.assertEqual(
            parsed["substrate_contract"],
            substrates.FENICSX_CANTILEVER_ELASTIC_CONTRACT,
        )

    def test_fenicsx_stage5_user_turn_byte_identical(self):
        _, user_turn = _capture_stage(
            s5, FX_FIX, "canned_stage5_input.json", materialize_results=True
        )
        self.assertEqual(user_turn, _fx("thought_user_turn.txt"))
        sent = json.loads(user_turn)
        entry = sent["execution_results"]["runs"][0]
        self.assertEqual(entry["qoi_value"], 0.003007857)
        # the full wrapper summary (both numbers) reaches stage 5 too
        self.assertEqual(
            sent["stage4_summaries"][0]["qoi"]["max_von_mises"], 4.246e7
        )

    def test_birth_composition_deterministic(self):
        self.assertEqual(
            _capture_stage(s3, FX_FIX, "canned_stage3_input.json"),
            _capture_stage(s3, FX_FIX, "canned_stage3_input.json"),
        )

    def test_fenicsx_stage3_selection_agrees_on_the_real_registry(self):
        baton = Baton.from_json(_fx("canned_stage3_input.json"))
        self.assertEqual(
            select_substrate(baton.payload["experiment_spec"]), FENICSX
        )

    def test_calculix_has_no_stage3_birth_pin_by_design(self):
        # A production calculix stage-3 surface DOES NOT EXIST: the 7-field
        # spec stops at selection (R-B-1) before composition. The absence
        # of the fixture is the record, asserted so it cannot rot silently.
        self.assertFalse((FEA_FIX / "stage3_user_turn.txt").exists())
        abbreviated = {
            "parameters": [{"name": n} for n in run_fea._REQUIRED_FIELDS]
        }
        with self.assertRaises(LookupError):
            s3._selected_contract(abbreviated)


# ---------------------------------------------------------------------------
# Chain close (E2, the fenicsx twin) + the hook at five rungs (E7)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Escapes, fired on the production records (E5)
# ---------------------------------------------------------------------------

class TestProductionEscapes(unittest.TestCase):
    def test_reynolds_block_rejects_by_name_in_both_cantilever_specs(self):
        for spec_fn, sid in ((_fea_spec, FEA), (_fenicsx_spec, FENICSX)):
            spec = spec_fn()
            spec["regime"] = {"reynolds_min": 100, "reynolds_max": 200,
                             "notes": "n"}
            errors = stage2_spec.validate_spec(
                spec, spec["hypothesis_id"], vocab_for(sid)
            )
            named = [e for e in errors
                     if "not part of this substrate's regime" in e]
            self.assertEqual(len(named), 2, sid)
            for e in named:
                self.assertIn("not a Reynolds band", e)
                self.assertIn("not a circuit analysis", e)
                self.assertIn("not a symbolic operation", e)

    def test_analysis_and_operation_keys_reject_by_name(self):
        for key, value in (("analysis_type", "op"), ("operation", "diff")):
            spec = _fenicsx_spec()
            spec["regime"] = {key: value, "notes": "n"}
            errors = stage2_spec.validate_spec(
                spec, "hand-fenicsx", vocab_for(FENICSX)
            )
            self.assertTrue(
                any(f"regime field '{key}' is not part of" in e
                    for e in errors),
                key,
            )

    def test_missing_regime_rejects(self):
        spec = _fea_spec()
        del spec["regime"]
        errors = stage2_spec.validate_spec(spec, "hand-fea", vocab_for(FEA))
        self.assertTrue(any("regime" in e and "missing" in e for e in errors))

    def test_machine_keys_from_both_grammars_reject_in_cantilever_qoi(self):
        spec = _fenicsx_spec()
        spec["qoi"] = dict(spec["qoi"], kind="node_voltage", field="U")
        errors = stage2_spec.validate_spec(
            spec, "hand-fenicsx", vocab_for(FENICSX)
        )
        self.assertTrue(
            any("different substrate class's QoI grammar" in e for e in errors)
        )

    def test_unknown_quantity_rejects_on_the_production_record(self):
        spec = _fea_spec()
        spec["qoi"] = dict(spec["qoi"], quantity="strain_energy")
        errors = stage2_spec.validate_spec(spec, "hand-fea", vocab_for(FEA))
        self.assertTrue(any("quantity must be one of" in e for e in errors))

    def test_adapters_reject_unknown_params_by_name(self):
        for adapter in (dispatch._fea_adapter, dispatch._fenicsx_adapter):
            with self.assertRaises(ValueError) as ctx:
                adapter(
                    FEA, {"length": 1.0, "mesh_resolution": 64}, "case", {},
                    {"quantity": "tip_displacement"},
                )
            self.assertIn("mesh_resolution", str(ctx.exception))

    def test_missing_typed_fields_reject_by_name_through_the_adapters(self):
        # docker-free: both wrappers reject missing fields at
        # _validate_input, BEFORE any container/preflight call, and the
        # adapters pass the wrapper's own named rejection through as an
        # honest valid=false summary.
        summary = dispatch._fea_adapter(
            FEA, {"length": 1.0, "width": 0.05}, "case", {}, None
        )
        self.assertFalse(summary["valid"])
        self.assertIn("missing required field(s)", summary["diagnostics"])
        self.assertIn("tip_load", summary["diagnostics"])
        summary = dispatch._fenicsx_adapter(
            FENICSX,
            {"length": 1.0, "width": 0.05, "height": 0.05, "E": 210e9,
             "nu": 0.3, "tip_load": 1000.0, "mesh_density": 8},
            "case", {}, None,
        )
        self.assertFalse(summary["valid"])
        self.assertIn("element_degree", summary["diagnostics"])

    def test_qoi_translation_refusals(self):
        vocab = vocab_for(FENICSX)
        request, refusal = dispatch._fixed_summary_qoi_translation(
            {"name": "x", "units": "m", "definition": "d",
             "how_extracted": "h"}, vocab
        )
        self.assertIsNone(request)
        self.assertIn("no machine-readable 'quantity' key", refusal)
        self.assertIn("tip_displacement", refusal)
        request, refusal = dispatch._fixed_summary_qoi_translation(
            "free text", vocab
        )
        self.assertIsNone(request)
        self.assertIn("must be an object", refusal)
        request, refusal = dispatch._fixed_summary_qoi_translation(
            {"quantity": "strain_energy"}, vocab
        )
        self.assertIsNone(request)
        self.assertIn("strain_energy", refusal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
