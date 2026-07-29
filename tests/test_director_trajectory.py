"""test_director_trajectory.py — A2 (2026-07-29): the director sees its own
trajectory.

It planned with almost no self-knowledge: moves and tokens, never dollars,
never agentic turns spent, never its own decision cap (free_director's cap
could end the study invisibly). Item C (a1b7dae) already records usd/turns on
every arc entry's cost — the data existed and was simply not surfaced. This is
display only: no new collection, no new constraint, and the view degrades to an
honest "unknown" rather than lying (a partial sum is labelled partial).

Offline; no model calls.

Run directly: venv/bin/python3 tests/test_director_trajectory.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.free_director as FD  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from pi_agent.free_director import free_investigate  # noqa: E402


def _entry(cost=None):
    return {"move_type": "single", "outcome": "completed", "cost": cost}


class TestTrajectoryView(unittest.TestCase):
    def test_old_signature_is_unchanged_no_trajectory_key(self):
        v = FD._budget_view(Budget(6), 0, None)
        self.assertNotIn("trajectory", v)

    def test_dollars_and_turns_are_summed_from_the_arc(self):
        arc = [_entry({"usd": 1.25, "turns": 70, "calls": 3, "tokens": 100}),
               _entry({"usd": 2.00, "turns": 84, "calls": 3, "tokens": 100})]
        v = FD._budget_view(Budget(6), 0, None, arc=arc, decisions=3,
                            decision_cap=28)
        t = v["trajectory"]
        self.assertEqual(t["usd_spent"], 3.25)
        self.assertEqual(t["agentic_turns_spent"], 154)
        # full coverage: no partial-sum caveat needed.
        self.assertNotIn("usd_note", t)

    def test_partial_coverage_is_said_out_loud_not_passed_off_as_total(self):
        arc = [_entry({"usd": 1.0, "turns": 10}), _entry(None), _entry(None)]
        t = FD._budget_view(Budget(6), 0, None, arc=arc)["trajectory"]
        self.assertEqual(t["usd_spent"], 1.0)
        self.assertIn("1 of 3", t["usd_note"])
        self.assertIn("true total is higher", t["usd_note"])

    def test_no_recorded_dollars_reads_unknown_never_zero(self):
        arc = [_entry(None), _entry(None)]
        t = FD._budget_view(Budget(6), 0, None, arc=arc)["trajectory"]
        self.assertIn("unknown", t["usd_spent"])

    def test_the_decision_runway_is_visible(self):
        t = FD._budget_view(Budget(6), 0, None, arc=[], decisions=5,
                            decision_cap=28)["trajectory"]
        self.assertEqual(t["this_is_decision"], 5)
        self.assertEqual(t["decision_cap"], 28)
        self.assertEqual(t["decisions_remaining_after_this"], 23)

    def test_an_empty_arc_and_no_cap_shows_nothing_rather_than_noise(self):
        v = FD._budget_view(Budget(6), 0, None, arc=[])
        self.assertNotIn("trajectory", v)

    def test_trajectory_never_raises_it_degrades_honestly(self):
        class Evil:
            def get(self, *a, **k):
                raise RuntimeError("torn")
        t = FD._trajectory_view([Evil()], 1, 10)
        # either a computed view or the honest failure note — never an exception.
        self.assertIsInstance(t, dict)


class TestTheLoopFeedsTheDirectorItsTrajectory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_decider_receives_trajectory_with_runway_and_arc_dollars(self):
        seen = []

        def decide(study, arc, budget):
            seen.append(budget)
            if len(seen) == 1:
                return {"ack": "s", "reading": "r", "reasoning": "b",
                        "action": "run_experiment", "domain": "q"}
            return {"ack": "s", "reading": "r", "reasoning": "b",
                    "action": "stop", "stop_reason": "done"}

        def run_move(study, move, finding=None, runs_root=None):
            import pi_agent.study as S
            return S.record_move(
                study,
                MoveResult("single", move.run_id or "s-m1", True, "completed",
                           {"publishable": True,
                            "cost": {"calls": 3, "tokens": 100,
                                     "usd": 4.5, "turns": 77}}),
                finding=finding)

        free_investigate("g", budget=Budget(4), studies_root=self.root,
                         decide_action=decide, run_move=run_move, study_id="s")
        # turn 1: nothing run yet — runway present, no spend rows.
        self.assertEqual(seen[0]["trajectory"]["this_is_decision"], 1)
        # turn 2: the move's recorded dollars and turns are in front of it.
        t2 = seen[1]["trajectory"]
        self.assertEqual(t2["usd_spent"], 4.5)
        self.assertEqual(t2["agentic_turns_spent"], 77)
        self.assertEqual(t2["this_is_decision"], 2)
        self.assertEqual(t2["decision_cap"], 4 * 3 + 10)


if __name__ == "__main__":
    unittest.main()
