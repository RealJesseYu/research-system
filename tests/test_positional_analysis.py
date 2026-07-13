"""
test_positional_analysis.py — standalone tests for harness/positional_analysis.py
(QUEUE-14 offline positional-bias analysis). Zero model calls, zero disk
writes: every function under test is pure, exercised against a hand-built
fixture tournament state whose expected values are computed by hand below.

Run directly: python3 tests/test_positional_analysis.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.positional_analysis import (
    analyze_state,
    binomial_two_sided_all_one_way,
    classify_debate,
    elo_expected,
    is_trivial,
    single_turn_expectation,
    winner_position,
)


# A hand-built state. orderings are [first_presented, second_presented];
# position 2 == second == index 1.
#
#  m1 debate  [[a,b],[b,a]] verdicts [b,a] -> SPLIT, both winners at pos2
#  m2 debate  [[a,c],[c,a]] verdicts [a,a] -> AGREE (a wins), no signal
#  m3 debate  [[b,c],[c,b]] verdicts [b,c] -> SPLIT, both winners at pos1
#  m4 single  [[a,b]]       verdict [b]    -> pos2 win; elo a=1200,b=1200 -> E=0.5
#  m5 single  [[c,a]]       verdict [c]    -> pos1 win; elo c=1400,a=1200
#                                             E(pos2=a)=1/(1+10^((1400-1200)/400))
FIXTURE = {
    "match_log": [
        {"tier": "debate", "orderings": [["a", "b"], ["b", "a"]],
         "verdicts": ["b", "a"], "elo_before": {"a": 1200.0, "b": 1200.0}},
        {"tier": "debate", "orderings": [["a", "c"], ["c", "a"]],
         "verdicts": ["a", "a"], "elo_before": {"a": 1200.0, "c": 1200.0}},
        {"tier": "debate", "orderings": [["b", "c"], ["c", "b"]],
         "verdicts": ["b", "c"], "elo_before": {"b": 1200.0, "c": 1200.0}},
        {"tier": "single_turn", "orderings": [["a", "b"]],
         "verdicts": ["b"], "elo_before": {"a": 1200.0, "b": 1200.0}},
        {"tier": "single_turn", "orderings": [["c", "a"]],
         "verdicts": ["c"], "elo_before": {"c": 1400.0, "a": 1200.0}},
    ]
}

TRIVIAL = {"trivial": True, "round": 2, "final_ranking": [{"id": "h1"}]}


class TestPositionMapping(unittest.TestCase):
    def test_winner_position(self):
        self.assertEqual(winner_position(["a", "b"], "a"), 1)
        self.assertEqual(winner_position(["a", "b"], "b"), 2)

    def test_winner_position_raises_off_ballot(self):
        with self.assertRaises(ValueError):
            winner_position(["a", "b"], "z")


class TestClassifyDebate(unittest.TestCase):
    def test_split_both_pos2(self):
        c = classify_debate(FIXTURE["match_log"][0])
        self.assertTrue(c["is_split"])
        self.assertEqual(c["split_position"], 2)
        self.assertEqual(c["pos2_verdicts"], 2)
        self.assertEqual(c["pos1_verdicts"], 0)

    def test_agreed_no_signal(self):
        c = classify_debate(FIXTURE["match_log"][1])
        self.assertFalse(c["is_split"])
        self.assertIsNone(c["split_position"])
        # a wins both: pos1 in [a,c], pos2 in [c,a] -> one each
        self.assertEqual(c["pos2_verdicts"], 1)
        self.assertEqual(c["pos1_verdicts"], 1)

    def test_split_both_pos1(self):
        c = classify_debate(FIXTURE["match_log"][2])
        self.assertTrue(c["is_split"])
        self.assertEqual(c["split_position"], 1)
        self.assertEqual(c["pos1_verdicts"], 2)
        self.assertEqual(c["pos2_verdicts"], 0)


class TestEloExpectation(unittest.TestCase):
    def test_equal_ratings(self):
        self.assertAlmostEqual(elo_expected(1200.0, 1200.0), 0.5, places=4)

    def test_known_gap_to_4dp(self):
        # position 2 is the WEAKER (1200) vs first-presented 1400.
        # E = 1/(1+10^((1400-1200)/400)) = 1/(1+10^0.5) = 1/(1+3.1622776601)
        #   = 0.2402530734...  -> 0.2403 to 4dp
        self.assertAlmostEqual(elo_expected(1400.0, 1200.0), 0.2402530734, places=9)

    def test_single_turn_expectation_pos2_win(self):
        e = single_turn_expectation(FIXTURE["match_log"][3])
        self.assertEqual(e["observed_pos2"], 1)
        self.assertAlmostEqual(e["expected_pos2"], 0.5, places=4)

    def test_single_turn_expectation_pos1_win_strong(self):
        e = single_turn_expectation(FIXTURE["match_log"][4])
        self.assertEqual(e["observed_pos2"], 0)  # c (pos1) won
        self.assertAlmostEqual(e["expected_pos2"], 0.2402530734, places=9)


class TestBinomial(unittest.TestCase):
    def test_values(self):
        self.assertEqual(binomial_two_sided_all_one_way(0), 1.0)
        self.assertEqual(binomial_two_sided_all_one_way(1), 1.0)   # 2*0.5
        self.assertEqual(binomial_two_sided_all_one_way(2), 0.5)
        self.assertAlmostEqual(binomial_two_sided_all_one_way(4), 0.125, places=6)


class TestTrivialSkip(unittest.TestCase):
    def test_trivial_recognised(self):
        self.assertTrue(is_trivial(TRIVIAL))
        self.assertTrue(is_trivial({"round": 1}))  # no match_log
        self.assertFalse(is_trivial(FIXTURE))


class TestAnalyzeState(unittest.TestCase):
    def test_full_census(self):
        a = analyze_state(FIXTURE)
        self.assertEqual(a["debates_total"], 3)
        self.assertEqual(a["debates_split"], 2)
        self.assertEqual(a["debates_agree"], 1)
        self.assertEqual(a["split_pos2"], 1)   # m1
        self.assertEqual(a["split_pos1"], 1)   # m3
        self.assertEqual(a["split_verdicts_pos2"], 2)
        self.assertEqual(a["split_verdicts_pos1"], 2)
        self.assertEqual(a["single_turn_n"], 2)
        self.assertEqual(a["single_turn_observed_pos2"], 1)  # m4 only
        # expected = 0.5 (m4) + 0.2402530734 (m5) = 0.7402530734
        self.assertAlmostEqual(
            a["single_turn_expected_pos2"], 0.7402530734, places=9
        )


if __name__ == "__main__":
    unittest.main()
