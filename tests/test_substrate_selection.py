"""
test_substrate_selection.py — D.2. Call-free: no model calls, no network.

Proves signature-based selection (tools/substrate_selection.select_substrate),
which retires sole_routable_id() from production:

  (a) two-routable constructed registry, spec both can serve -> the MATURE
      one is selected even though it enrolls second;
  (b) spec only ngspice serves -> ngspice selected, AND the supervisor's
      maturity hook FIRES for the routable-non-mature pick (NEEDS_HUMAN_
      SIGNOFF; auto downgrade to defer) — proven, not assumed;
  (c) spec neither serves -> raises, proven by failing the escape (the
      assertion inside the assertRaises block only runs if a fallback
      substrate is wrongly returned);
  (d) determinism: same spec twice -> same pick; the tie-break IS the
      enrollment (routable_ids) order, proven by reversing it;
  plus the fail-loud wiring probes: a routable substrate missing its
  contract OR its signature raises AT SELECTION, before serve-ability.

Constructed registries follow the tests/test_contract_registry.py:39-49
precedent (mock-patched routable set; ngspice stays routable=False in the
real registry). Every vocabulary/contract used here is IMPORTED from its
single source — stage4_case_builder for cavity, tools/run_ngspice's
_REQUIRED_FIELDS and onboarding/ngspice_linear_passive/contract.py for
ngspice (importlib, the generate_calibration_cases.py pattern) — never
copied.

Run directly: venv/bin/python3 tests/test_substrate_selection.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import substrates
import supervisor
from baton import Baton
from stages.stage4_case_builder import BUILDABLE_PARAMS, REYNOLDS_KEY
from tools import run_ngspice
from tools import substrate_registry as registry
from tools import substrate_selection as selection

# ngspice's contract, imported from its single source (never copied) — the
# same importlib path generate_calibration_cases.py's CONTRACT_IMPORT uses.
_NGSPICE_CONTRACT_PATH = (
    ROOT / "onboarding" / "ngspice_linear_passive" / "contract.py"
)
_spec = importlib.util.spec_from_file_location(
    "_ngspice_contract_for_tests", _NGSPICE_CONTRACT_PATH
)
_ngspice_contract_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ngspice_contract_mod)
NGSPICE_CONTRACT = _ngspice_contract_mod.NGSPICE_LINEAR_PASSIVE_CONTRACT

# ngspice's typed-key vocabulary, imported from the wrapper that owns it.
NGSPICE_SIGNATURE = frozenset(run_ngspice._REQUIRED_FIELDS)

CANNED = (
    Path(__file__).resolve().parent / "fixtures" / "d2" / "canned_stage3_input.json"
)


def _spec_with(*names: str) -> dict:
    """A minimal spec shape: selection reads declared parameter names only."""
    return {"parameters": [{"name": n} for n in names]}


def _canned_cavity_spec() -> dict:
    return json.loads(CANNED.read_text())["payload"]["experiment_spec"]


def _v2_row(maturity: str) -> registry.SubstrateRecord:
    """A CONSTRUCTED second cavity-signature substrate (tests only — the real
    registry changes only by recorded ruling)."""
    return registry.SubstrateRecord(
        substrate_id="cavity_2d_cfd_v2",
        wrapper="tools/run_cfd.py",
        card_path="docs/envelope_card_cavity2d.md",
        maturity=maturity,
        routable=True,
        cost_tier="low",
        notes="CONSTRUCTED test row (test_substrate_selection.py)",
    )


def _two_cavity_registry(v2_maturity: str, order: tuple[str, ...]):
    """Context managers for a constructed two-routable registry: the real
    cavity row + a constructed v2 sharing cavity's signature OBJECT (imported,
    not copied)."""
    return (
        mock.patch.object(registry, "routable_ids", return_value=order),
        mock.patch.dict(registry._BY_ID, {"cavity_2d_cfd_v2": _v2_row(v2_maturity)}),
        mock.patch.dict(
            registry._CONTRACTS, {"cavity_2d_cfd_v2": substrates.CAVITY_2D_CONTRACT}
        ),
        mock.patch.dict(
            selection._SIGNATURES,
            {"cavity_2d_cfd_v2": selection._SIGNATURES["cavity_2d_cfd"]},
        ),
    )


def _cavity_ngspice_registry():
    """The (b)-case constructed registry: ngspice promoted routable IN THE
    TEST ONLY, wired from its single sources. Its real row (calibrating,
    routable=False) supplies maturity."""
    return (
        mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", "ngspice_linear_passive"),
        ),
        mock.patch.dict(
            registry._CONTRACTS, {"ngspice_linear_passive": NGSPICE_CONTRACT}
        ),
        mock.patch.dict(
            selection._SIGNATURES, {"ngspice_linear_passive": NGSPICE_SIGNATURE}
        ),
    )


class CaptureLogger:
    """Minimal stand-in for supervisor.Logger — the hook only calls .log()."""

    def __init__(self):
        self.lines: list[str] = []

    def log(self, line: str) -> None:
        self.lines.append(line)


def _trust_baton(mode: str) -> Baton:
    b = Baton(run_id="run-d2", created_at="2026-07-17T00:00:00Z", mode=mode)
    b.payload = {
        "domain": "circuits",
        "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
        "experiment_spec": _spec_with("netlist_body", "analysis"),
        "fidelity_verdict": {
            "label": "trust",
            "rationale": "the model's reasoning",
            "right_instrument": "the right instrument text",
        },
    }
    return b


class TestMaturePreference(unittest.TestCase):
    def test_a_mature_candidate_beats_enrollment_order(self):
        # (a) both can serve; cavity enrolls first but is provisional; the
        # constructed v2 is MATURE -> v2 is selected.
        patches = _two_cavity_registry(
            registry.MATURE, ("cavity_2d_cfd", "cavity_2d_cfd_v2")
        )
        with patches[0], patches[1], patches[2], patches[3]:
            self.assertEqual(
                selection.select_substrate(_spec_with("lid_velocity", "end_time")),
                "cavity_2d_cfd_v2",
            )


class TestNgspiceOnlySpec(unittest.TestCase):
    def test_b_ngspice_selected_for_ngspice_only_spec(self):
        # (b) the spec's names sit in ngspice's typed-key vocabulary only.
        patches = _cavity_ngspice_registry()
        with patches[0], patches[1], patches[2]:
            self.assertEqual(
                selection.select_substrate(_spec_with("netlist_body", "analysis")),
                "ngspice_linear_passive",
            )

    def test_b_hook_fires_auto_downgrade_for_non_mature_pick(self):
        # (b) proven, not assumed: the maturity hook sees the routable set
        # containing the non-mature pick and DOWNGRADES trust -> defer in auto.
        patches = _cavity_ngspice_registry()
        with patches[0], patches[1], patches[2]:
            b = _trust_baton("auto")
            logger = CaptureLogger()
            supervisor.apply_substrate_maturity_hook(logger, b, "auto")
            self.assertEqual(b.payload["fidelity_verdict"]["label"], "defer")
            joined = "\n".join(logger.lines)
            self.assertIn("NEEDS_HUMAN_SIGNOFF", joined)
            self.assertIn("ngspice_linear_passive@calibrating", joined)
            self.assertIn("MATURITY_DOWNGRADE [auto]", joined)
            self.assertTrue(b._maturity_signoff["required"])
            self.assertIn(
                "ngspice_linear_passive@calibrating",
                b._maturity_signoff["substrates"],
            )

    def test_b_hook_fires_human_signoff_verdict_untouched(self):
        patches = _cavity_ngspice_registry()
        with patches[0], patches[1], patches[2]:
            b = _trust_baton("human")
            logger = CaptureLogger()
            supervisor.apply_substrate_maturity_hook(logger, b, "human")
            self.assertEqual(b.payload["fidelity_verdict"]["label"], "trust")
            self.assertIn(
                "ngspice_linear_passive@calibrating", "\n".join(logger.lines)
            )
            self.assertTrue(b._maturity_signoff["required"])


class TestNoServerRaises(unittest.TestCase):
    def test_c_real_registry_never_falls_back_to_cavity(self):
        # (c) in the REAL registry (two routable since the R2 flip) a spec
        # whose parameter name sits in NEITHER signature has no server —
        # pre-flip this test used an ngspice-shaped spec, which now HAS a
        # server by design. Failing the escape: the inner assertion only
        # runs if a fallback substrate is wrongly returned.
        with self.assertRaises(LookupError):
            got = selection.select_substrate(
                _spec_with("warp_coil_inductance_map")
            )
            self.assertNotIn(got, registry.routable_ids())

    def test_c_message_names_the_unserved_parameters(self):
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate(_spec_with("warp_coil_inductance_map"))
        self.assertIn("no routable substrate can serve", str(ctx.exception))
        self.assertIn("warp_coil_inductance_map", str(ctx.exception))

    def test_c_two_routable_registry_still_raises_when_neither_serves(self):
        patches = _cavity_ngspice_registry()
        with patches[0], patches[1], patches[2]:
            with self.assertRaises(LookupError):
                got = selection.select_substrate(
                    _spec_with("warp_coil_inductance_map")
                )
                self.assertNotIn(
                    got, ("cavity_2d_cfd", "ngspice_linear_passive")
                )


class TestDeterminismAndTieBreak(unittest.TestCase):
    def test_d_same_spec_twice_same_pick_real_registry(self):
        spec = _canned_cavity_spec()
        first = selection.select_substrate(spec)
        second = selection.select_substrate(spec)
        self.assertEqual(first, second)
        self.assertEqual(first, "cavity_2d_cfd")

    def test_d_tie_stops_loudly_in_both_enrollment_orders(self):
        # R-B-1 (owner-delegated, 2026-07-17): both candidates provisional
        # (non-mature), both serve -> the enrollment-order pick is RETIRED
        # and selection STOPS LOUDLY naming both. Fired in BOTH orders so
        # the stop is provably order-independent — never a silent pick,
        # never a hidden preference for cavity.
        for order in (
            ("cavity_2d_cfd", "cavity_2d_cfd_v2"),
            ("cavity_2d_cfd_v2", "cavity_2d_cfd"),
        ):
            patches = _two_cavity_registry(registry.PROVISIONAL, order)
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(LookupError) as ctx:
                    selection.select_substrate(_spec_with("lid_velocity"))
            msg = str(ctx.exception)
            self.assertIn("ambiguous (R-B-1", msg)
            self.assertIn("cavity_2d_cfd@", msg)
            self.assertIn("cavity_2d_cfd_v2@", msg)
            self.assertIn("stopping before routing", msg)


class TestFailLoudWiring(unittest.TestCase):
    def test_routable_without_contract_raises_at_selection(self):
        # code_sklearn_eval is enrolled with NO contract and NO signature
        # (the subject migrated here at the Packet B Phase 2 flip — both
        # cantilevers are now wired); making it routable must fail loudly
        # at selection even for a cavity-only spec.
        with mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", "code_sklearn_eval"),
        ):
            with self.assertRaises(LookupError) as ctx:
                selection.select_substrate(_spec_with("lid_velocity"))
            self.assertIn("no fidelity contract wired", str(ctx.exception))

    def test_routable_without_signature_raises_at_selection(self):
        # contract wired but signature not: the signature probe fails loudly.
        # Post-Phase-2-flip BOTH cantilevers carry both in production, so
        # the subject is code_sklearn_eval (enrolled, wholly unwired) with
        # a contract patched in and the signature deliberately left missing.
        with mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", "code_sklearn_eval"),
        ):
            with mock.patch.dict(
                registry._CONTRACTS,
                {"code_sklearn_eval": "SUBSTRATE CONTRACT: constructed"},
            ):
                with self.assertRaises(LookupError) as ctx:
                    selection.select_substrate(_spec_with("lid_velocity"))
                self.assertIn(
                    "no parameter signature wired", str(ctx.exception)
                )

    def test_unknown_routable_id_raises_keyerror(self):
        with mock.patch.object(
            registry, "routable_ids", return_value=("no_such_substrate",)
        ):
            with self.assertRaises(KeyError):
                selection.select_substrate(_spec_with("lid_velocity"))


class TestSpecReading(unittest.TestCase):
    def test_cavity_signature_is_buildables_plus_reynolds(self):
        # the signature IS the imported vocabulary — never a third copy.
        self.assertEqual(
            selection.signature_for("cavity_2d_cfd"),
            frozenset(BUILDABLE_PARAMS) | {REYNOLDS_KEY},
        )

    def test_none_spec_stops_loudly_under_r_b_1(self):
        # S1 (ruled 2026-07-17): a None spec declares nothing, so EVERY
        # routable substrate serves it and selection stops loudly — the
        # pre-R-B-1 constrains-nothing convention (bare reads resolving to
        # cavity, a silent enrollment-order pick) is RETIRED. Fired on the
        # REAL registry. BIO Wave D.4 CHANGE (owner 2026-07-19): now that
        # rdkit/cobrapy/mafft/homology_search are MATURE, the mature-preferred
        # L2 filter narrows the nothing-declaring pool to exactly those FOUR,
        # so the loud stop names the MATURE set (not cavity) — still a loud
        # stop, still never a silent pick.
        self.assertEqual(selection.declared_parameter_names(None), frozenset())
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate(None)
        msg = str(ctx.exception)
        self.assertIn("ambiguous (R-B-1", msg)
        for sid in ("rdkit", "cobrapy", "mafft", "homology_search"):
            self.assertIn(f"{sid}@mature", msg)
        self.assertNotIn("cavity_2d_cfd@provisional", msg)
        self.assertIn("stopping before routing", msg)

    def test_empty_parameters_spec_stops_loudly_under_r_b_1(self):
        # The disclosed residual S1 exists to kill: a VALIDATABLE spec with
        # parameters: [] declares nothing — under S2 it would have silently
        # picked cavity by enrollment order (a cavity fallback). It now
        # stops loudly, proven by firing.
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate({"parameters": []})
        self.assertIn("ambiguous (R-B-1", str(ctx.exception))

    def test_canned_spec_names_are_all_buildable(self):
        names = selection.declared_parameter_names(_canned_cavity_spec())
        self.assertEqual(names, frozenset(BUILDABLE_PARAMS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
