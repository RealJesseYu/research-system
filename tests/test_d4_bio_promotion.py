"""
test_d4_bio_promotion.py — THE BIO WAVE D.4 PROMOTION (owner-ruled 2026-07-19
on the calibration evidence: rdkit + mafft CLEAN at N=3; cobrapy on the N=7
wash-out — in-envelope 34 trust / 1 refine, out 35/35 defer). Three substrates
flip routable=False->True AND maturity=CALIBRATING->MATURE together, the FIRST
mature substrates. homology_search is HELD (a G03/G05 card fix, no promotion).

ZERO live model calls, ZERO docker (every adapter touch below rejects at the
structural screen or is mocked). What is proven here, none of it argued:

  REGISTRY + WIRINGS — three row flips (mature/routable) with their ruling
  records; the routable set is EIGHT in enrollment order; the first three
  MATURE substrates are exactly rdkit/cobrapy/mafft; contract_for returns the
  graduated substrates.py constants (assertIs) — the onboarding modules
  re-export them (one source); the vocab records are fixed_summary over each
  wrapper's own imported QOI_FIELDS with the three new single-regime shapes;
  the signature/adapter/qoi-translation/run-entry maps all resolve.

  PROOF (a) — NO NEW R-B-1 TIE — each bio spec (declaring its content param)
  routes to exactly ITS substrate; the existing five route unchanged; the one
  shared signature key ('quantity', in every wrapper's _REQUIRED_FIELDS) causes
  NO tie because specs declare the content param, not quantity — a bare
  quantity-only spec stops LOUDLY under R-B-1, proven by firing.

  THE THREADED ADAPTER + SCALAR ENTRY — unlike the cantilevers (no qoi input,
  dict-of-numbers return), these wrappers take `quantity` as a typed input and
  return a SCALAR qoi (the ngspice shape). The adapter THREADS the translated
  quantity into the wrapper input; the scalar constructor (reusing
  ngspice_run_entry) maps converged:=valid, qoi_value:=the scalar; unknown
  params reject by name; a missing quantity fails loud; invalid runs carry the
  wrapper's own diagnostics.

  PROOF (d) — ACCEPTANCE #6 — a trust verdict does NOT name a promoted MATURE
  substrate in the maturity-hook signoff set (it is excluded from the
  non-mature downgrade trigger on ITS account), in both modes.

  ESCAPES, FIRED — alien regime blocks reject BY NAME; an unknown quantity
  refuses; no cavity fallback anywhere.

  FIXTURES ADDITIVE-ONLY — the all-routable contract block gains the three new
  contracts verbatim and drops nothing (pred4 lines all still present); the
  chooser retry id list gains exactly the three ids.

Run directly: venv/bin/python3 tests/test_d4_bio_promotion.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import substrates
import supervisor
from baton import Baton
from stages.stage2_spec import _validate_qoi, _validate_regime
from tools import run_cobrapy, run_mafft, run_rdkit
from tools import substrate_dispatch as dispatch
from tools import substrate_registry as registry
from tools import substrate_selection as selection
from tools.qoi_vocab import (
    DescriptorComputationRegime,
    FbaSteadyStateRegime,
    FixedSummaryVocab,
    MsaAlignmentRegime,
    vocab_for,
)
from tools.substrate_selection import select_substrate

BIO = ("rdkit", "cobrapy", "mafft")
D1 = ROOT / "tests" / "fixtures" / "d1"
C235 = ROOT / "tests" / "fixtures" / "c235"

_WRAPPERS = {"rdkit": run_rdkit, "cobrapy": run_cobrapy, "mafft": run_mafft}
_CONTRACT_CONST = {
    "rdkit": "RDKIT_DESCRIPTOR_CONTRACT",
    "cobrapy": "COBRAPY_FBA_CONTRACT",
    "mafft": "MAFFT_CONTRACT",
}
_CONTENT_PARAM = {"rdkit": "smiles", "cobrapy": "model", "mafft": "sequences"}
_A_QUANTITY = {"rdkit": "MolWt", "cobrapy": "growth_rate",
               "mafft": "alignment_identity"}
_REGIME_CLASS = {
    "rdkit": DescriptorComputationRegime,
    "cobrapy": FbaSteadyStateRegime,
    "mafft": MsaAlignmentRegime,
}


def _min_spec(sid: str) -> dict:
    """A minimal routing-shaped spec: one content parameter, a {notes} regime,
    and a fixed-summary qoi naming a real quantity for `sid`."""
    return {
        "parameters": [{"name": _CONTENT_PARAM[sid]}],
        "regime": {"notes": "in-regime by construction"},
        "qoi": {"name": "q", "units": "u", "definition": "d",
                "how_extracted": "h", "quantity": _A_QUANTITY[sid]},
    }


class TestFlipRegistry(unittest.TestCase):
    def test_rows_flipped_mature_and_routable_with_records(self):
        for sid in BIO:
            rec = registry.get(sid)
            self.assertEqual(rec.maturity, registry.MATURE, sid)
            self.assertTrue(rec.routable, sid)
            self.assertTrue(registry.is_mature(sid), sid)
            self.assertIn("BIO Wave D.4 PROMOTION", rec.notes, sid)

    def test_routable_set_is_eight_in_enrollment_order(self):
        self.assertEqual(
            registry.routable_ids(),
            ("cavity_2d_cfd", "calculix_cantilever_fea",
             "fenicsx_cantilever_elastic", "sympy_symbolic_exact",
             "ngspice_linear_passive", "rdkit", "cobrapy", "mafft"),
        )

    def test_exactly_the_bio_three_are_mature(self):
        mature = {r.substrate_id for r in registry.all_substrates()
                  if registry.is_mature(r.substrate_id)}
        self.assertEqual(mature, set(BIO))

    def test_homology_search_stays_held_and_inert(self):
        rec = registry.get("homology_search")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertNotIn("homology_search", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("homology_search")

    def test_contract_for_returns_graduated_constants_single_source(self):
        for sid in BIO:
            self.assertIs(
                registry.contract_for(sid),
                getattr(substrates, _CONTRACT_CONST[sid]),
                sid,
            )

    def test_onboarding_modules_reexport_the_same_object(self):
        # the graduated constant's canonical home is substrates.py; the
        # onboarding contract module re-exports it (one source, never a copy).
        import importlib
        for sid in BIO:
            mod = importlib.import_module(f"onboarding.{sid}.contract")
            self.assertIs(
                getattr(mod, _CONTRACT_CONST[sid]),
                getattr(substrates, _CONTRACT_CONST[sid]),
                sid,
            )


class TestWirings(unittest.TestCase):
    def test_vocab_is_fixed_summary_with_wrapper_names_and_new_regime(self):
        for sid in BIO:
            vocab = vocab_for(sid)
            self.assertIsInstance(vocab, FixedSummaryVocab, sid)
            self.assertIs(vocab.names, tuple(_WRAPPERS[sid].QOI_FIELDS), sid)
            self.assertIsInstance(vocab.regime, _REGIME_CLASS[sid], sid)

    def test_signatures_are_wrapper_required_fields(self):
        for sid in BIO:
            self.assertEqual(
                selection.signature_for(sid),
                frozenset(_WRAPPERS[sid]._REQUIRED_FIELDS),
                sid,
            )

    def test_dispatch_maps_resolve_to_the_threaded_family(self):
        for sid in BIO:
            self.assertIs(
                dispatch.adapter_for(sid),
                {"rdkit": dispatch._rdkit_adapter,
                 "cobrapy": dispatch._cobrapy_adapter,
                 "mafft": dispatch._mafft_adapter}[sid],
                sid,
            )
            self.assertIs(
                dispatch.qoi_translation_for(sid),
                dispatch._fixed_summary_qoi_translation, sid,
            )
            self.assertIs(
                dispatch.run_entry_constructor_for(sid),
                dispatch._fixed_summary_scalar_run_entry, sid,
            )


class TestRoutingNoTie(unittest.TestCase):
    def test_each_bio_spec_routes_to_exactly_itself(self):
        for sid in BIO:
            spec = _min_spec(sid)
            # regime and qoi validate under the substrate's own vocab
            re_err: list[str] = []
            _validate_regime(spec["regime"], vocab_for(sid), re_err)
            self.assertEqual(re_err, [], sid)
            q_err: list[str] = []
            _validate_qoi(spec["qoi"], vocab_for(sid), q_err)
            self.assertEqual(q_err, [], sid)
            self.assertEqual(select_substrate(spec), sid, sid)

    def test_existing_five_route_unchanged(self):
        self.assertEqual(
            select_substrate({"parameters": [{"name": "reynolds_number"}]}),
            "cavity_2d_cfd",
        )

    def test_shared_quantity_key_is_only_a_signature_superset_no_tie(self):
        # 'quantity' is in all three signatures (each wrapper's required set),
        # but specs never DECLARE quantity as a parameter (it rides the qoi
        # block), so no real spec ties. A bare quantity-only spec, however,
        # sits inside all three -> the R-B-1 loud stop fires (proven).
        for sid in BIO:
            self.assertIn("quantity", selection.signature_for(sid), sid)
        with self.assertRaises(LookupError) as ctx:
            select_substrate({"parameters": [{"name": "quantity"}]})
        self.assertIn("ambiguous (R-B-1", str(ctx.exception))


class TestThreadedAdapterAndScalarEntry(unittest.TestCase):
    def _mock_wrapper(self, ret):
        captured = {}
        orig = dispatch.wrapper_callable

        def fake(sid):
            def _w(typed):
                captured["sid"] = sid
                captured["typed"] = typed
                return ret
            return _w
        dispatch.wrapper_callable = fake
        return captured, orig

    def test_adapter_threads_quantity_into_typed_input(self):
        captured, orig = self._mock_wrapper(
            {"valid": True, "qoi": 46.07, "diagnostics": "ok", "runtime_s": 0.01}
        )
        try:
            dispatch._rdkit_adapter(
                "rdkit", {"smiles": "CCO"}, "case", {}, {"quantity": "MolWt"}
            )
        finally:
            dispatch.wrapper_callable = orig
        self.assertEqual(captured["typed"], {"smiles": "CCO", "quantity": "MolWt"})

    def test_cobrapy_adapter_admits_optional_min_growth(self):
        captured, orig = self._mock_wrapper(
            {"valid": True, "qoi": 0.87, "diagnostics": "ok", "runtime_s": 0.02}
        )
        try:
            dispatch._cobrapy_adapter(
                "cobrapy", {"model": "e_coli_core", "min_growth": 0.1},
                "case", {}, {"quantity": "growth_rate"},
            )
        finally:
            dispatch.wrapper_callable = orig
        self.assertEqual(
            captured["typed"],
            {"model": "e_coli_core", "min_growth": 0.1, "quantity": "growth_rate"},
        )

    def test_scalar_run_entry_maps_valid_and_invalid(self):
        valid = {"valid": True, "qoi": 46.07, "diagnostics": "d", "runtime_s": 0.5}
        entry = dispatch._fixed_summary_scalar_run_entry(
            valid, None, {"quantity": "MolWt"}
        )
        self.assertEqual(
            entry, {"converged": True, "wall_clock_s": 0.5, "qoi_value": 46.07}
        )
        invalid = {"valid": False, "qoi": None,
                   "diagnostics": "unparseable SMILES", "runtime_s": 0.01}
        entry = dispatch._fixed_summary_scalar_run_entry(invalid, None, None)
        self.assertEqual(
            entry, {"converged": False, "wall_clock_s": 0.01,
                    "qoi_error": "unparseable SMILES"},
        )

    def test_adapter_rejects_unknown_params_by_name(self):
        with self.assertRaises(ValueError) as ctx:
            dispatch._rdkit_adapter(
                "rdkit", {"smiles": "CCO", "temperature": 300}, "c", {},
                {"quantity": "MolWt"},
            )
        self.assertIn("temperature", str(ctx.exception))

    def test_adapter_fails_loud_without_a_translated_quantity(self):
        with self.assertRaises(ValueError) as ctx:
            dispatch._mafft_adapter(
                "mafft", {"sequences": ["AAAA", "AAAT"]}, "c", {}, None
            )
        self.assertIn("quantity", str(ctx.exception))


class TestEscapes(unittest.TestCase):
    def test_alien_regime_key_rejects_by_name(self):
        for sid in BIO:
            errors: list[str] = []
            _validate_regime(
                {"reynolds_min": 1, "reynolds_max": 2, "notes": "x"},
                vocab_for(sid), errors,
            )
            self.assertTrue(
                any("not part of this substrate's regime" in e for e in errors),
                sid,
            )

    def test_unknown_quantity_rejects(self):
        for sid in BIO:
            spec_qoi = dict(_min_spec(sid)["qoi"], quantity="not_a_real_one")
            errors: list[str] = []
            _validate_qoi(spec_qoi, vocab_for(sid), errors)
            self.assertTrue(any("quantity must be one of" in e for e in errors), sid)


class TestAcceptance6(unittest.TestCase):
    """Proof (d): the maturity hook never names a promoted MATURE substrate in
    its signoff set — a trust verdict is not force-downgraded on ITS account.
    (The old non-mature five still gate the run; the hook stays global.)"""

    class _L:
        def __init__(self):
            self.lines: list[str] = []

        def log(self, m):
            self.lines.append(m)

    def test_mature_substrates_excluded_from_signoff_both_modes(self):
        for mode in ("human", "auto"):
            baton = Baton(
                run_id="acc6", created_at="t", mode=mode,
                payload={"fidelity_verdict": {
                    "label": "trust", "rationale": "r", "right_instrument": "yes"}},
            )
            supervisor.apply_substrate_maturity_hook(self._L(), baton, mode)
            signoff = getattr(baton, "_maturity_signoff", None)
            named = signoff["substrates"] if signoff else []
            for sid in BIO:
                self.assertFalse(
                    any(s.startswith(sid + "@") for s in named),
                    f"{sid} must not appear in the signoff set ({mode})",
                )


class TestFixturesAdditiveOnly(unittest.TestCase):
    def test_contract_block_gains_three_verbatim_drops_nothing(self):
        block = registry.routable_contracts_block()
        for sid in BIO:
            header = f"ROUTABLE SUBSTRATE: {sid}\n"
            self.assertIn(header + getattr(substrates, _CONTRACT_CONST[sid]), block)
        # additive-only at the fixture level: every pred4 line still present.
        pred4 = (D1 / "feasibility_nudge_pred4.txt").read_text().splitlines()
        current = set((D1 / "feasibility_nudge.txt").read_text().splitlines())
        missing = [ln for ln in pred4 if ln not in current]
        self.assertEqual(missing, [], "no pred4 line may be dropped")

    def test_chooser_retry_id_list_gains_exactly_the_three(self):
        import re

        def ids(path):
            err = json.loads((C235 / path).read_text())["validation_error"]
            return set(eval(re.search(r"exactly one of (\[[^\]]*\])", err).group(1)))
        old = ids("chooser_retry_user_turn_v235_pred4.txt")
        new = ids("chooser_retry_user_turn_v235.txt")
        self.assertEqual(new - old, set(BIO))
        self.assertEqual(old - new, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
