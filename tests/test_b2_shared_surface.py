"""
test_b2_shared_surface.py — Packet B Phase 2 commit 2 proofs (pre-flip).

THE THREE CLAIMS THIS FILE PROVES, each by firing (a check that cannot fail
is not a proof):

  1. THE R-B-1 STOP (ruled S1, strict; owner-delegated 2026-07-17). When
     more than one wired candidate serves a spec after the mature-preferred
     filter, selection STOPS LOUDLY naming all candidates with their
     maturity rungs and the declared parameter names — the silent
     enrollment-order pick is RETIRED. Deterministic where determinable:
     an element_degree-bearing spec uniquely resolves fenicsx; a synthetic
     mature candidate uniquely resolves (Step 28's first half, nothing
     really promoted); loudly stopped where not — never both, never silent
     order. Fired here on a CONSTRUCTED overlap (the two cantilever
     signatures imported from THEIR single sources — the wrappers'
     _REQUIRED_FIELDS — per this module's registry-patching discipline)
     and, for the S1 nothing-declaring cases, on the REAL registry.

  2. THE ADDITIVE CONSTRUCTOR WIDENING (ruled option V-A). qoi_request
     joined the uniform run-entry-constructor signature as a third,
     None-defaulted parameter; cavity/ngspice/sympy constructors ignore it
     and their entries are BYTE-IDENTICAL with and without it — proven by
     exact-dict asserts.

  3. THE TWO NEW SHAPES (ruled option R1 + V-A). StaticSmallDeflectionRegime
     (notes-only spec regime object; all three other shapes' keys rejected
     by name) and FixedSummaryVocab (one machine key, "quantity",
     membership-checked; regime member REQUIRED with no default). No
     production _VOCABS instance exists yet — instances are wired at the
     flip, alongside the routability ruling, never before.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stages import stage2_spec  # noqa: E402
from tools import qoi_vocab  # noqa: E402
from tools import substrate_dispatch as dispatch  # noqa: E402
from tools import substrate_registry as registry  # noqa: E402
from tools import substrate_selection as selection  # noqa: E402
from tools.qoi_vocab import (  # noqa: E402
    FIXED_SUMMARY,
    STATIC_SMALL_DEFLECTION,
    FixedSummaryVocab,
    StaticSmallDeflectionRegime,
)
from tools.run_fea import _REQUIRED_FIELDS as FEA_FIELDS  # noqa: E402
from tools.run_fenicsx import _REQUIRED_FIELDS as FENICSX_FIELDS  # noqa: E402

FEA = "calculix_cantilever_fea"
FENICSX = "fenicsx_cantilever_elastic"


def _spec_with(*names: str) -> dict:
    return {"parameters": [{"name": n} for n in names]}


def _both_cantilevers_registry():
    """A CONSTRUCTED registry with cavity + both cantilevers routable —
    signatures imported from the wrappers' own _REQUIRED_FIELDS (their
    single sources), contracts constructed strings (the established
    unwired-subject patching pattern). The real rows supply maturity
    (both cantilevers really are calibrating)."""
    return (
        mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", FEA, FENICSX),
        ),
        mock.patch.dict(
            registry._CONTRACTS,
            {
                FEA: "SUBSTRATE CONTRACT: constructed (b2 test)",
                FENICSX: "SUBSTRATE CONTRACT: constructed (b2 test)",
            },
        ),
        mock.patch.dict(
            selection._SIGNATURES,
            {
                FEA: frozenset(FEA_FIELDS),
                FENICSX: frozenset(FENICSX_FIELDS),
            },
        ),
    )


class TestRB1StopOnConstructedOverlap(unittest.TestCase):
    """Claim 1: the loud multi-candidate stop, fired on the real subset
    overlap the flip will create (FEA's 7 names are a proper subset of
    fenicsx's 8)."""

    def test_seven_field_spec_stops_loudly_naming_both(self):
        patches = _both_cantilevers_registry()
        with patches[0], patches[1], patches[2]:
            with self.assertRaises(LookupError) as ctx:
                selection.select_substrate(_spec_with(*FEA_FIELDS))
        msg = str(ctx.exception)
        self.assertIn("substrate selection is ambiguous (R-B-1", msg)
        self.assertIn(f"{FEA}@calibrating", msg)
        self.assertIn(f"{FENICSX}@calibrating", msg)
        # cavity does NOT serve the beam names and must not be named a candidate
        self.assertNotIn("cavity_2d_cfd@", msg)
        # the declared parameter names are named, sorted
        for name in FEA_FIELDS:
            self.assertIn(name, msg)
        self.assertIn("enrollment-order pick", msg)
        self.assertIn("RETIRED", msg)
        self.assertIn("stopping before routing", msg)

    def test_eight_field_spec_uniquely_resolves_fenicsx(self):
        # Deterministic where determinable: element_degree is served by
        # exactly one signature — no stop, no model judgment involved.
        patches = _both_cantilevers_registry()
        with patches[0], patches[1], patches[2]:
            self.assertEqual(
                selection.select_substrate(_spec_with(*FENICSX_FIELDS)),
                FENICSX,
            )

    def test_synthetic_mature_candidate_uniquely_resolves(self):
        # Step 28's first half, proven synthetically: the mature-preferred
        # filter collapses the two-candidate pool to ONE and the raise does
        # not fire. Nothing real is promoted — maturity is patched. Both
        # directions, so the resolution is the RUNG, not a hidden order.
        for mature_one in (FEA, FENICSX):
            patches = _both_cantilevers_registry()
            with patches[0], patches[1], patches[2], mock.patch.object(
                registry, "is_mature", side_effect=lambda sid: sid == mature_one
            ):
                self.assertEqual(
                    selection.select_substrate(_spec_with(*FEA_FIELDS)),
                    mature_one,
                    mature_one,
                )

    def test_stop_reaches_both_decision_twins_identically(self):
        # The stop lives INSIDE select_substrate, upstream of both reach
        # paths — stage 3's _selected_contract and stage 4's re-derivation
        # both hit the same LookupError before any model call or execution.
        from stages import stage3_fidelity_gate

        patches = _both_cantilevers_registry()
        with patches[0], patches[1], patches[2]:
            with self.assertRaises(LookupError):
                stage3_fidelity_gate._selected_contract(_spec_with(*FEA_FIELDS))


class TestRB1StrictS1OnTheRealRegistry(unittest.TestCase):
    """Claim 1, the S1 half: a nothing-declaring spec stops loudly on the
    REAL registry — live before any flip (all three routable substrates
    serve an empty name set). The retired convention's residual (a silent
    cavity pick) is the exact escape these fire."""

    def test_none_spec_stops_loudly(self):
        # BIO Wave D.4 CHANGE (owner 2026-07-19): with rdkit/cobrapy/mafft/
        # homology_search MATURE, the mature-preferred L2 filter narrows the
        # nothing-declaring pool to exactly those four — the loud stop now
        # names the MATURE set (not cavity/sympy/ngspice). Still a loud stop,
        # still never a silent pick.
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate(None)
        msg = str(ctx.exception)
        self.assertIn("ambiguous (R-B-1", msg)
        for sid in ("rdkit", "cobrapy", "mafft", "homology_search"):
            self.assertIn(f"{sid}@mature", msg)
        self.assertNotIn("cavity_2d_cfd@provisional", msg)

    def test_zero_change_for_every_wired_substrate_spec(self):
        # The stop changes NOTHING for real single-candidate selections:
        # each wired substrate's own vocabulary still uniquely resolves it.
        self.assertEqual(
            selection.select_substrate(_spec_with("lid_velocity")),
            "cavity_2d_cfd",
        )
        self.assertEqual(
            selection.select_substrate(
                _spec_with("netlist_body", "analysis", "qoi")
            ),
            "ngspice_linear_passive",
        )
        self.assertEqual(
            selection.select_substrate(
                _spec_with("operation", "expression", "symbols")
            ),
            "sympy_symbolic_exact",
        )


class TestConstructorWideningByteIdentity(unittest.TestCase):
    """Claim 2: exact-dict asserts — the three existing constructors return
    BYTE-IDENTICAL entries with and without the additive third argument."""

    def test_cavity_entry_ignores_qoi_request(self):
        summary = {
            "converged": True,
            "runtime": {"wall_clock_s": 1.5},
            "qoi": {"name": "volAverage(mag(U))", "value": 0.4168179},
        }
        expected = {"converged": True, "wall_clock_s": 1.5, "qoi_value": 0.4168179}
        self.assertEqual(dispatch._cavity_run_entry(summary, None), expected)
        self.assertEqual(
            dispatch._cavity_run_entry(summary, None, {"field": "U"}), expected
        )
        err = {"converged": False, "runtime": {"wall_clock_s": 2.0},
               "qoi_error": "postProcess wrote no output"}
        expected_err = {"converged": False, "wall_clock_s": 2.0,
                        "qoi_error": "postProcess wrote no output"}
        self.assertEqual(dispatch._cavity_run_entry(err, None), expected_err)
        self.assertEqual(
            dispatch._cavity_run_entry(err, None, {"field": "U"}), expected_err
        )

    def test_ngspice_entry_ignores_qoi_request(self):
        summary = {"valid": True, "qoi": 3.3, "diagnostics": "ok",
                   "runtime_s": 0.2}
        expected = {"converged": True, "wall_clock_s": 0.2, "qoi_value": 3.3}
        self.assertEqual(
            dispatch._ngspice_run_entry_with_fallback(summary, None), expected
        )
        self.assertEqual(
            dispatch._ngspice_run_entry_with_fallback(
                summary, None, {"kind": "node_voltage"}
            ),
            expected,
        )

    def test_sympy_entry_ignores_qoi_request(self):
        summary = {"valid": True, "state": "solved_verified", "result": "pi/2",
                   "reason": None, "diagnostics": "verified", "runtime_s": 0.5}
        expected = {"converged": True, "wall_clock_s": 0.5,
                    "state": "solved_verified", "qoi_expression": "pi/2"}
        self.assertEqual(dispatch.sympy_run_entry(summary, None), expected)
        self.assertEqual(
            dispatch.sympy_run_entry(summary, None, {"symbolic_result": True}),
            expected,
        )


class TestStaticSmallDeflectionRegimeShape(unittest.TestCase):
    """Claim 3, regime half: the notes-only shape, its alien rejections
    fired one by one."""

    VOCAB = FixedSummaryVocab(
        names=("tip_displacement", "max_von_mises"),
        regime=StaticSmallDeflectionRegime(),
    )

    def _regime_errors(self, regime) -> list[str]:
        errors: list[str] = []
        stage2_spec._validate_regime(regime, self.VOCAB, errors)
        return errors

    def test_shape_tag_and_alien_keys(self):
        reg = StaticSmallDeflectionRegime()
        self.assertEqual(reg.shape, STATIC_SMALL_DEFLECTION)
        self.assertEqual(
            reg.alien_keys,
            ("reynolds_min", "reynolds_max", "analysis_type", "operation"),
        )

    def test_notes_only_block_is_valid(self):
        self.assertEqual(
            self._regime_errors({"notes": "slender beam, small deflection"}),
            [],
        )

    def test_each_alien_key_rejected_by_name_individually(self):
        for key in ("reynolds_min", "reynolds_max", "analysis_type", "operation"):
            errors = self._regime_errors({"notes": "n", key: 1})
            self.assertEqual(len(errors), 1, key)
            self.assertIn(f"regime field '{key}'", errors[0])
            self.assertIn("not a Reynolds band", errors[0])
            self.assertIn("not a circuit analysis", errors[0])
            self.assertIn("not a symbolic operation", errors[0])
            self.assertIn("exactly one physics regime by construction", errors[0])

    def test_reynolds_shaped_block_rejects_with_named_reasons(self):
        errors = self._regime_errors(
            {"reynolds_min": 100, "reynolds_max": 300, "notes": "n"}
        )
        self.assertEqual(len(errors), 2)

    def test_missing_notes_rejected(self):
        self.assertEqual(self._regime_errors({}), ["regime is missing 'notes'."])

    def test_non_dict_rejected(self):
        self.assertEqual(
            self._regime_errors("laminar"), ["regime must be an object with notes."]
        )


class TestFixedSummaryVocabShape(unittest.TestCase):
    """Claim 3, vocab half: the one machine key 'quantity', membership-
    checked; regime member required with no default; foreign grammars
    rejected by name."""

    VOCAB = TestStaticSmallDeflectionRegimeShape.VOCAB

    def _qoi_errors(self, qoi) -> list[str]:
        errors: list[str] = []
        stage2_spec._validate_qoi(qoi, self.VOCAB, errors)
        return errors

    @staticmethod
    def _prose_qoi(**extra) -> dict:
        return {
            "name": "tip deflection",
            "units": "m",
            "definition": "max |u_z| over the displacement dofs",
            "how_extracted": "returned by the wrapper on every valid run",
            **extra,
        }

    def test_record_requires_regime_no_default(self):
        # A record without regime semantics cannot exist (R-23.5-5).
        with self.assertRaises(TypeError):
            FixedSummaryVocab(names=("tip_displacement",))

    def test_shape_tag(self):
        self.assertEqual(self.VOCAB.shape, FIXED_SUMMARY)

    def test_quantity_member_valid(self):
        self.assertEqual(
            self._qoi_errors(self._prose_qoi(quantity="tip_displacement")), []
        )
        self.assertEqual(
            self._qoi_errors(self._prose_qoi(quantity="max_von_mises")), []
        )

    def test_quantity_non_member_rejected_naming_the_set(self):
        errors = self._qoi_errors(self._prose_qoi(quantity="strain_energy"))
        self.assertEqual(len(errors), 1)
        self.assertIn("quantity must be one of", errors[0])
        self.assertIn("max_von_mises", errors[0])
        self.assertIn("tip_displacement", errors[0])
        self.assertIn("'strain_energy'", errors[0])

    def test_absent_quantity_is_valid_not_extractable(self):
        # Absent machine key = the honest qoi_error fallback path downstream,
        # mirroring the cavity grammar's absent-machine-keys semantics.
        self.assertEqual(self._qoi_errors(self._prose_qoi()), [])

    def test_foreign_machine_keys_rejected_by_name(self):
        for key in ("field", "operation", "component", "mask",
                    "kind", "target", "reduction"):
            errors = self._qoi_errors(self._prose_qoi(**{key: "x"}))
            self.assertTrue(errors, key)
            self.assertIn("different substrate class's QoI grammar", errors[0])

    def test_unwired_set_carries_no_vocab_instance(self):
        # Instances are wired at the flip alongside the routability ruling,
        # never before — at commit 2 this asserted the CANTILEVERS absent;
        # since the Phase 2 flip they are wired, and the statement moves to
        # the remaining unwired set (code_sklearn_eval, web_search).
        self.assertIn(FEA, qoi_vocab._VOCABS)
        self.assertIn(FENICSX, qoi_vocab._VOCABS)
        self.assertNotIn("code_sklearn_eval", qoi_vocab._VOCABS)
        self.assertNotIn("web_search", qoi_vocab._VOCABS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
