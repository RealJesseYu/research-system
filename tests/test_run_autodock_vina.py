"""
test_run_autodock_vina.py — the AutoDock Vina wrapper (BIO Wave D.2, DEFERRED).

Vina is re-tiered T2 -> DEFERRED: no aarch64 build (no bioconda package, no pip
wheel), so it will not install on this host. The docking §3A / determinism /
convergence-jail proof is produced at provisioning on an x86 host. Proven NOW:
  * PURE input jails (no tool) — the failure-honesty that does not depend on the
    binary; and
  * the honest DEFERRED preflight (vina-prod absent -> a clear un-defer message),
    when docker is up.

Run directly: venv/bin/python3 tests/test_run_autodock_vina.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_autodock_vina
from tools.run_autodock_vina import (
    LIGAND_ALLOWLIST, QOI_FIELDS, RECEPTOR_ALLOWLIST, VINA_SEED,
    VinaInputError, _validate_input, run_autodock_vina as run,
)

_GOODBOX = {"center_x": 0.0, "center_y": 0.0, "center_z": 0.0,
            "size_x": 20.0, "size_y": 20.0, "size_z": 20.0}
_DOCKER_UP = run_autodock_vina.preflight() != "docker CLI not found on PATH"


def _spec(**over):
    base = {"receptor": "demo_receptor", "ligand": "demo_ligand",
            "box": dict(_GOODBOX), "quantity": "docking_score"}
    base.update(over)
    return base


class PureInputJails(unittest.TestCase):
    def test_clean_input_passes(self):
        out = _validate_input(_spec())
        self.assertEqual(out["receptor"], "demo_receptor")
        self.assertEqual(out["box"]["size_x"], 20.0)

    def test_bad_receptor_and_ligand_rejected(self):
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(receptor="7abc"))
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(ligand="xyz"))

    def test_box_non_numeric_center_rejected(self):
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(box={**_GOODBOX, "center_x": "near"}))

    def test_box_non_positive_or_oversized_size_rejected(self):
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(box={**_GOODBOX, "size_x": 0}))
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(box={**_GOODBOX, "size_y": 500}))

    def test_box_missing_field_rejected(self):
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(box={"center_x": 0.0}))

    def test_bad_quantity_rejected(self):
        with self.assertRaises(VinaInputError):
            _validate_input(_spec(quantity="affinity"))

    def test_bad_input_fails_loud_through_run(self):
        r = run(_spec(receptor="7abc"))
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("input rejected", r["diagnostics"])

    def test_seed_is_fixed_for_determinism(self):
        self.assertIsInstance(VINA_SEED, int)

    def test_vocabularies(self):
        self.assertEqual(RECEPTOR_ALLOWLIST, ("demo_receptor",))
        self.assertEqual(LIGAND_ALLOWLIST, ("demo_ligand",))
        self.assertEqual(QOI_FIELDS, ("docking_score",))


@unittest.skipUnless(_DOCKER_UP, "docker not available")
class DeferredState(unittest.TestCase):
    def test_valid_input_returns_deferred_not_a_score(self):
        # Vina has no aarch64 build: a valid input reaches preflight and returns
        # the honest DEFERRED failure (no vina-prod), never a docking score here.
        r = run(_spec())
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("vina-prod", r["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
