"""
test_flip_promotion.py — the R2/R3 promotion flip, proven on the REAL
registry (owner rulings, 2026-07-17). Call-free: no model calls, no docker,
no subprocess (wrappers are spied).

Unlike tests/test_substrate_selection.py's CONSTRUCTED two-routable
registries (the D.2 pre-flip proofs, kept verbatim), everything here runs
against the real post-flip registry:

  P2 (Step 28's done-when, live): an ngspice-only spec selects
      ngspice_linear_passive; the maturity hook FIRES on the trust decision
      (NEEDS_HUMAN_SIGNOFF in human mode with the verdict untouched;
      trust -> defer downgrade in auto mode) — asserted, not assumed. A
      cavity spec selects cavity, deterministically.
  P3 (fail-loud): a spec no routable substrate can serve raises at
      selection — at stage 3's _selected_contract AND at stage 4's run()
      guard (no results.json, no wrapper call) — escape-failing; an unknown
      id raises KeyError; never a cavity fallback.
  Wiring identity: every flipped map entry IS the single-source object —
      the graduated substrates.NGSPICE_LINEAR_PASSIVE_CONTRACT (and the
      onboarding re-export IS that object), run_ngspice's _REQUIRED_FIELDS
      / _QOI_KINDS / _NAME_RE / _REDUCTIONS, the D.4 adapter, the D.5 entry
      constructor — never a copy.
  Stage-4 e2e: run() on an ngspice trust baton executes through the
      registered adapter (wrapper spied) and builds its run entries via
      ngspice_run_entry ({converged, wall_clock_s, qoi_value|qoi_error});
      evidence keeps the wrapper summary VERBATIM.

Run directly: venv/bin/python3 tests/test_flip_promotion.py
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
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import substrates
import supervisor
from baton import Baton
from stages import stage3_fidelity_gate as s3
from stages import stage4_simulation as s4
from tools import qoi_vocab
from tools import run_ngspice
from tools import substrate_dispatch as dispatch
from tools import substrate_registry as registry
from tools import substrate_selection as selection

DIVIDER_BODY = "V1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k"


def _spec_with(*names: str) -> dict:
    return {"parameters": [{"name": n} for n in names]}


def _ngspice_spec() -> dict:
    return {
        "parameters": [{"name": "netlist_body"}, {"name": "analysis"}],
        "qoi": {
            "name": "divider output voltage",
            "units": "V",
            "definition": "operating-point voltage at node out",
            "how_extracted": "op solve, v(out)",
            "kind": "node_voltage",
            "target": "out",
            "reduction": "op_value",
        },
        "mini_experiment": {
            "runs": [
                {"netlist_body": DIVIDER_BODY, "analysis": {"type": "op"}}
            ]
        },
    }


def _trust_baton(mode: str, spec: dict, run_id: str) -> Baton:
    b = Baton(run_id=run_id, created_at="2026-07-17T00:00:00Z", mode=mode)
    # Truth-edited Step 23.5 (R-23.5-4): the payload carries the
    # gate-decided substrate_id; these constructed batons agree with their
    # spec's own structural selection, keeping each proof on its original
    # subject (mismatch escapes live in test_c235_chain). For an
    # unserveable spec the stage raises at selection BEFORE the agreement
    # check, so the placeholder id is never read.
    try:
        sid = selection.select_substrate(spec)
    except Exception:
        sid = "unserveable-constructed"
    b.payload = {
        "domain": "circuits",
        "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
        "substrate_id": sid,
        "experiment_spec": spec,
        "fidelity_verdict": {
            "label": "trust",
            "rationale": "constructed flip-proof baton",
            "right_instrument": "constructed",
        },
    }
    return b


class CaptureLogger:
    def __init__(self):
        self.lines: list[str] = []

    def log(self, line: str) -> None:
        self.lines.append(line)


class TestP2DoneWhenLive(unittest.TestCase):
    def test_ngspice_only_spec_selects_ngspice_real_registry(self):
        self.assertEqual(
            selection.select_substrate(_spec_with("netlist_body", "analysis")),
            "ngspice_linear_passive",
        )

    def test_hook_fires_human_mode_signoff_verdict_untouched(self):
        b = _trust_baton("human", _ngspice_spec(), "flip-p2-human")
        logger = CaptureLogger()
        supervisor.apply_substrate_maturity_hook(logger, b, "human")
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "trust")
        joined = "\n".join(logger.lines)
        self.assertIn("NEEDS_HUMAN_SIGNOFF", joined)
        self.assertIn("ngspice_linear_passive@calibrating", joined)
        self.assertTrue(b._maturity_signoff["required"])

    def test_hook_fires_auto_mode_trust_downgraded_to_defer(self):
        b = _trust_baton("auto", _ngspice_spec(), "flip-p2-auto")
        logger = CaptureLogger()
        supervisor.apply_substrate_maturity_hook(logger, b, "auto")
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "defer")
        joined = "\n".join(logger.lines)
        self.assertIn("MATURITY_DOWNGRADE [auto]", joined)
        self.assertIn("ngspice_linear_passive@calibrating", joined)

    def test_cavity_spec_selects_cavity_deterministic(self):
        spec = _spec_with("lid_velocity", "end_time")
        first = selection.select_substrate(spec)
        second = selection.select_substrate(spec)
        self.assertEqual(first, "cavity_2d_cfd")
        self.assertEqual(first, second)


class TestP3FailLoudRealRegistry(unittest.TestCase):
    def test_unserveable_spec_raises_at_selection_escape_failed(self):
        # the inner assertion only runs if a fallback is wrongly returned
        with self.assertRaises(LookupError):
            got = selection.select_substrate(
                _spec_with("warp_coil_inductance_map")
            )
            self.assertNotIn(got, registry.routable_ids())

    def test_unserveable_spec_raises_at_stage3_selected_contract(self):
        with self.assertRaises(LookupError) as ctx:
            s3._selected_contract(_spec_with("warp_coil_inductance_map"))
        self.assertIn("no routable substrate can serve", str(ctx.exception))

    def test_unserveable_spec_raises_at_stage4_guard_nothing_executed(self):
        spec = _ngspice_spec()
        spec["parameters"].append({"name": "warp_coil_inductance_map"})
        baton = _trust_baton("auto", spec, "flip-p3-unserveable")
        wrapper_calls: list = []
        old_cwd = os.getcwd()
        tmp = tempfile.mkdtemp(prefix="flip_p3_")
        try:
            os.chdir(tmp)
            with mock.patch.object(
                run_ngspice, "run_ngspice",
                lambda typed: wrapper_calls.append(typed),
            ):
                with self.assertRaises(LookupError):
                    s4.run(baton)
            self.assertEqual(wrapper_calls, [])
            self.assertFalse(
                (Path("runs") / baton.run_id / "stage4" / "results.json").exists()
            )
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_id_raises_keyerror_on_every_flipped_map(self):
        for fn in (
            registry.contract_for,
            selection.signature_for,
            qoi_vocab.vocab_for,
            dispatch.adapter_for,
            dispatch.qoi_translation_for,
            dispatch.run_entry_constructor_for,
        ):
            with self.assertRaises(KeyError):
                fn("no_such_substrate")


class TestFlipWiringIsSingleSourced(unittest.TestCase):
    def test_contract_is_the_graduated_constant(self):
        self.assertIs(
            registry.contract_for("ngspice_linear_passive"),
            substrates.NGSPICE_LINEAR_PASSIVE_CONTRACT,
        )

    def test_onboarding_reexport_is_the_same_object(self):
        # F1: one source — the onboarding module re-exports substrates.py's
        # constant (the generate_calibration_cases.py import path)
        path = ROOT / "onboarding" / "ngspice_linear_passive" / "contract.py"
        spec = importlib.util.spec_from_file_location("_flip_contract_check", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIs(
            mod.NGSPICE_LINEAR_PASSIVE_CONTRACT,
            substrates.NGSPICE_LINEAR_PASSIVE_CONTRACT,
        )

    def test_signature_is_the_wrapper_required_fields(self):
        self.assertEqual(
            selection.signature_for("ngspice_linear_passive"),
            frozenset(run_ngspice._REQUIRED_FIELDS),
        )

    def test_vocab_members_are_the_wrapper_objects(self):
        vocab = qoi_vocab.vocab_for("ngspice_linear_passive")
        self.assertIs(vocab.kinds, run_ngspice._QOI_KINDS)
        self.assertIs(vocab.target_re, run_ngspice._NAME_RE)
        self.assertIs(vocab.reductions, run_ngspice._REDUCTIONS)

    def test_adapter_translation_and_constructor_resolve(self):
        self.assertIs(
            dispatch.adapter_for("ngspice_linear_passive"),
            dispatch._ngspice_adapter,
        )
        self.assertIs(
            dispatch.qoi_translation_for("ngspice_linear_passive"),
            dispatch._ngspice_qoi_translation,
        )
        self.assertIs(
            dispatch.run_entry_constructor_for("ngspice_linear_passive"),
            dispatch._ngspice_run_entry_with_fallback,
        )

    def test_cavity_constructor_is_the_moved_entry_builder(self):
        self.assertIs(
            dispatch.run_entry_constructor_for("cavity_2d_cfd"),
            dispatch._cavity_run_entry,
        )


class TestStage4NgspiceEndToEnd(unittest.TestCase):
    def _drive(self, summary: dict) -> dict:
        baton = _trust_baton("auto", _ngspice_spec(), "flip-e2e-ngspice")
        wrapper_calls: list = []

        def spy(typed):
            wrapper_calls.append(typed)
            return summary

        old_cwd = os.getcwd()
        tmp = tempfile.mkdtemp(prefix="flip_e2e_")
        try:
            os.chdir(tmp)
            with mock.patch.object(run_ngspice, "run_ngspice", spy):
                out = s4.run(baton)
            results = json.loads(
                (Path("runs") / baton.run_id / "stage4" / "results.json")
                .read_text()
            )
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmp, ignore_errors=True)
        return {
            "payload": out.payload,
            "results": results,
            "wrapper_calls": wrapper_calls,
            "history_note": out.history[-1]["note"],
        }

    def test_valid_summary_becomes_d5_entry_and_verbatim_evidence(self):
        summary = {
            "valid": True, "qoi": 6.6667,
            "diagnostics": "op solve ok", "runtime_s": 0.26,
        }
        got = self._drive(summary)
        # the typed wrapper input carried the translated named-quantity QoI
        self.assertEqual(len(got["wrapper_calls"]), 1)
        self.assertEqual(
            got["wrapper_calls"][0]["qoi"],
            {"kind": "node_voltage", "target": "out", "reduction": "op_value"},
        )
        # the conclusions-only entry is D.5's mapping, exactly
        self.assertEqual(
            got["payload"]["execution_results"]["runs"],
            [{"converged": True, "wall_clock_s": 0.26, "qoi_value": 6.6667}],
        )
        # evidence keeps the wrapper summary VERBATIM
        self.assertEqual(got["results"]["runs"][0]["summary"], summary)
        self.assertEqual(
            got["history_note"],
            "executed 1 mini-run(s): 1 converged, 1 QoI extracted",
        )

    def test_invalid_summary_maps_to_qoi_error_never_a_number(self):
        summary = {
            "valid": False, "qoi": None,
            "diagnostics": "failure marker: no DC path to ground",
            "runtime_s": 0.21,
        }
        got = self._drive(summary)
        entry = got["payload"]["execution_results"]["runs"][0]
        self.assertEqual(
            entry,
            {
                "converged": False,
                "wall_clock_s": 0.21,
                "qoi_error": "failure marker: no DC path to ground",
            },
        )
        self.assertNotIn("qoi_value", entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
