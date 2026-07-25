"""test_pi_cli.py — Step ④.2a: the `python -m pi_agent` director CLI.

Proves the CLI wires argv through to the (already-tested) investigate() with the
right arguments and defaults, and parses --allowed-substrates into a list. The
investigation itself is patched — this is a wiring test, call-free (zero model
calls, zero subprocess runs).

Run directly: venv/bin/python3 tests/test_pi_cli.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.__main__ as cli  # noqa: E402
from pi_agent.loop import DEFAULT_MAX_MOVES  # noqa: E402

_FAKE_REPORT = {
    "study_id": "study-test",
    "goal": "g",
    "moves_run": 0,
    "termination": "pi_judged_complete",
}


class TestCliWiring(unittest.TestCase):
    def _run(self, argv):
        captured = {}

        def fake_investigate(**kwargs):
            captured.update(kwargs)
            return _FAKE_REPORT

        with patch.object(cli, "investigate", side_effect=fake_investigate):
            cli.main(argv)
        return captured

    def test_defaults(self):
        cap = self._run(["--goal", "predict solubility"])
        self.assertEqual(cap["goal"], "predict solubility")
        self.assertEqual(cap["mode"], "auto")  # 'walk away' default
        self.assertEqual(cap["max_moves"], DEFAULT_MAX_MOVES)
        self.assertIsNone(cap["allowed_substrates"])

    def test_all_flags(self):
        cap = self._run([
            "--goal", "g",
            "--mode", "human",
            "--max-moves", "3",
            "--allowed-substrates", "rdkit, cobrapy ,mafft",
        ])
        self.assertEqual(cap["mode"], "human")
        self.assertEqual(cap["max_moves"], 3)
        # comma-split and trimmed
        self.assertEqual(cap["allowed_substrates"], ["rdkit", "cobrapy", "mafft"])

    def test_goal_is_required(self):
        with self.assertRaises(SystemExit):
            self._run([])  # argparse exits when --goal is missing

    # ---- ceiling resolution (R-FD-2) -------------------------------------

    def test_default_ceiling_provenance(self):
        cap = self._run(["--goal", "g"])
        self.assertEqual(cap["max_moves"], DEFAULT_MAX_MOVES)
        self.assertEqual(cap["ceiling"], {"kind": "default", "max_moves": DEFAULT_MAX_MOVES})

    def test_explicit_max_moves_provenance(self):
        cap = self._run(["--goal", "g", "--max-moves", "4"])
        self.assertEqual(cap["max_moves"], 4)
        self.assertEqual(cap["ceiling"], {"kind": "max_moves", "max_moves": 4})

    def test_cost_cap_derives_move_ceiling(self):
        from pi_agent.budget import EST_COST_PER_MOVE_USD

        cap = self._run(["--goal", "g", "--cost-cap", "47"])
        expected_moves = int(47 // EST_COST_PER_MOVE_USD)
        self.assertEqual(cap["max_moves"], expected_moves)
        self.assertEqual(cap["ceiling"]["kind"], "cost_cap")
        self.assertEqual(cap["ceiling"]["cost_cap_usd"], 47.0)
        self.assertEqual(cap["ceiling"]["derived_max_moves"], expected_moves)

    def test_both_ceilings_is_an_error(self):
        with self.assertRaises(SystemExit):
            self._run(["--goal", "g", "--max-moves", "3", "--cost-cap", "50"])

    def test_cost_cap_too_small_is_an_error(self):
        from pi_agent.budget import EST_COST_PER_MOVE_USD

        with self.assertRaises(SystemExit):
            self._run(["--goal", "g", "--cost-cap", str(EST_COST_PER_MOVE_USD / 2)])

    # ---- director routing (R-FD-1: free path alongside, enum default) ----

    def test_default_director_is_the_enum_path(self):
        # No --director: the enum investigate() is called, not the free one.
        cap = self._run(["--goal", "g"])
        self.assertEqual(cap["max_moves"], DEFAULT_MAX_MOVES)  # enum kwarg present

    def test_free_director_is_routed_with_a_budget(self):
        import pi_agent.free_director as fd
        from pi_agent.budget import Budget

        captured = {}

        def fake_free(**kwargs):
            captured.update(kwargs)
            return _FAKE_REPORT

        with patch.object(fd, "free_investigate", side_effect=fake_free):
            cli.main(["--goal", "g", "--director", "free", "--max-moves", "4"])
        self.assertIn("budget", captured)
        self.assertIsInstance(captured["budget"], Budget)
        self.assertEqual(captured["budget"].remaining(), 4)
        self.assertEqual(captured["goal"], "g")


if __name__ == "__main__":
    unittest.main()
