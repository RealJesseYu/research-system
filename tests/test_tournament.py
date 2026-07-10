"""
test_tournament.py — standalone tests of stage-1's Elo-tournament machinery
(stages/tournament.py, Step 17-C). Zero model calls: every function under
test is pure, so this exercises them directly against canned data — Elo math
(wins, draws, sequences, zero-sum), the both-orderings debate score rule,
TF-IDF proximity + dedup flags on synthetic near-dupes, match-order
determinism, final-ranking tiebreaks and deduped_by flagging, the
tournament_state schema shape, the k=1 bypass condition, and an end-to-end
canned-verdict flow from judge outputs through ratings to the final ranking.

Run directly: python3 tests/test_tournament.py
"""

from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.tournament import (
    DEDUP_THRESHOLD,
    ELO_INIT,
    K_FACTOR,
    build_match_record,
    build_state,
    debate_score,
    dedup_flags,
    elo_update,
    final_ranking,
    matrix_pair_map,
    order_matches,
    proximity_matrix,
)

# Three synthetic survivors: the first two are near-duplicates (one trailing
# word apart), the third is a distinct claim sharing only incidental terms.
NEAR_DUPE_1 = {
    "id": "h1",
    "statement": "Increasing lid velocity raises the volume averaged kinetic energy of the recirculating cavity flow",
    "rationale": "Faster lid motion injects more momentum into the primary vortex and the average speed rises",
}
NEAR_DUPE_2 = {
    "id": "h2",
    "statement": "Increasing lid velocity raises the volume averaged kinetic energy of the recirculating cavity flow markedly",
    "rationale": "Faster lid motion injects more momentum into the primary vortex and the average speed rises",
}
DISTINCT = {
    "id": "h3",
    "statement": "Refining the mesh shifts the location of the pressure minimum at the primary vortex core",
    "rationale": "Coarse grids under resolve the steep pressure gradient near the vortex center",
}


class TestEloUpdate(unittest.TestCase):
    def test_equal_ratings_win(self):
        r_a, r_b = elo_update(1200.0, 1200.0, 1.0)
        self.assertEqual(r_a, 1216.0)
        self.assertEqual(r_b, 1184.0)

    def test_equal_ratings_draw_is_no_op(self):
        r_a, r_b = elo_update(1200.0, 1200.0, 0.5)
        self.assertEqual(r_a, 1200.0)
        self.assertEqual(r_b, 1200.0)

    def test_underdog_win_gains_more_than_16(self):
        r_a, r_b = elo_update(1000.0, 1400.0, 1.0)
        # expected_a = 1/(1+10^1) = 1/11; gain = 32 * 10/11 = 29.0909...
        self.assertAlmostEqual(r_a, 1029.0909, places=3)
        self.assertAlmostEqual(r_b, 1370.9091, places=3)

    def test_draw_between_unequal_moves_ratings_together(self):
        r_a, r_b = elo_update(1300.0, 1100.0, 0.5)
        self.assertLess(r_a, 1300.0)
        self.assertGreater(r_b, 1100.0)

    def test_zero_sum(self):
        for pair, score in (((1200.0, 1200.0), 1.0), ((1315.5, 1084.5), 0.5), ((1000.0, 1400.0), 0.0)):
            r_a, r_b = elo_update(pair[0], pair[1], score)
            self.assertAlmostEqual(r_a + r_b, pair[0] + pair[1], places=9)

    def test_sequence_of_two_wins(self):
        r_a, r_b = elo_update(1200.0, 1200.0, 1.0)
        r_a, r_b = elo_update(r_a, r_b, 1.0)
        # Second win against the now-lower-rated opponent gains less than 16.
        self.assertAlmostEqual(r_a, 1230.53, places=1)
        self.assertAlmostEqual(r_b, 1169.47, places=1)
        self.assertLess(r_a - 1216.0, 16.0)

    def test_custom_k(self):
        r_a, r_b = elo_update(1200.0, 1200.0, 1.0, k=16)
        self.assertEqual(r_a, 1208.0)
        self.assertEqual(r_b, 1192.0)


class TestDebateScore(unittest.TestCase):
    def test_both_orderings_agree_on_a(self):
        self.assertEqual(debate_score("h1", "h2", "h1", "h1"), 1.0)

    def test_both_orderings_agree_on_b(self):
        self.assertEqual(debate_score("h1", "h2", "h2", "h2"), 0.0)

    def test_disagreement_is_a_draw(self):
        self.assertEqual(debate_score("h1", "h2", "h1", "h2"), 0.5)
        self.assertEqual(debate_score("h1", "h2", "h2", "h1"), 0.5)


class TestProximityAndDedup(unittest.TestCase):
    def test_near_dupes_flagged_distinct_not(self):
        survivors = [NEAR_DUPE_1, NEAR_DUPE_2, DISTINCT]
        matrix = proximity_matrix(survivors)
        # Symmetric, unit diagonal.
        self.assertAlmostEqual(matrix[0][0], 1.0, places=6)
        self.assertAlmostEqual(matrix[0][1], matrix[1][0], places=9)
        # Near-dupes are highly similar; the distinct claim is not.
        self.assertGreaterEqual(matrix[0][1], DEDUP_THRESHOLD)
        self.assertLess(matrix[0][2], DEDUP_THRESHOLD)
        self.assertLess(matrix[1][2], DEDUP_THRESHOLD)
        flags = dedup_flags(matrix)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0][:2], (0, 1))
        self.assertGreaterEqual(flags[0][2], DEDUP_THRESHOLD)

    def test_proximity_matrix_deterministic(self):
        survivors = [NEAR_DUPE_1, NEAR_DUPE_2, DISTINCT]
        self.assertEqual(proximity_matrix(survivors), proximity_matrix(survivors))

    def test_dedup_threshold_boundary(self):
        matrix = [[1.0, 0.85, 0.8499], [0.85, 1.0, 0.2], [0.8499, 0.2, 1.0]]
        flags = dedup_flags(matrix, threshold=0.85)
        self.assertEqual(flags, [(0, 1, 0.85)])


class TestOrderMatches(unittest.TestCase):
    MATRIX = [
        [1.0, 0.2, 0.9],
        [0.2, 1.0, 0.2],
        [0.9, 0.2, 1.0],
    ]

    def test_most_similar_first_with_index_tiebreak(self):
        pairs = list(itertools.combinations(range(3), 2))
        # (0,2) at 0.9 first; (0,1) and (1,2) tie at 0.2, broken by (i, j).
        self.assertEqual(order_matches(pairs, self.MATRIX), [(0, 2), (0, 1), (1, 2)])

    def test_input_order_irrelevant(self):
        shuffled = [(1, 2), (0, 2), (0, 1)]
        self.assertEqual(order_matches(shuffled, self.MATRIX), [(0, 2), (0, 1), (1, 2)])

    def test_repeat_calls_identical(self):
        pairs = list(itertools.combinations(range(3), 2))
        self.assertEqual(order_matches(pairs, self.MATRIX), order_matches(pairs, self.MATRIX))


class TestFinalRanking(unittest.TestCase):
    SURVIVORS = [
        {"id": "h1", "statement": "s1", "rationale": "r1"},
        {"id": "h2", "statement": "s2", "rationale": "r2"},
        {"id": "h3", "statement": "s3", "rationale": "r3"},
        {"id": "h4", "statement": "s4", "rationale": "r4"},
    ]

    def test_elo_desc_with_survivor_order_tiebreak(self):
        ratings = {"h1": 1210.0, "h2": 1210.0, "h3": 1250.0, "h4": 1150.0}
        ranked = final_ranking(ratings, self.SURVIVORS)
        self.assertEqual([s["id"] for s in ranked], ["h3", "h1", "h2", "h4"])

    def test_all_equal_elo_keeps_survivor_order(self):
        ratings = {s["id"]: ELO_INIT for s in self.SURVIVORS}
        ranked = final_ranking(ratings, self.SURVIVORS)
        self.assertEqual([s["id"] for s in ranked], ["h1", "h2", "h3", "h4"])

    def test_deduped_by_flags_lower_ranked_sibling_never_removes(self):
        ratings = {"h1": 1210.0, "h2": 1210.0, "h3": 1250.0, "h4": 1150.0}
        ranked = final_ranking(ratings, self.SURVIVORS, [(0, 1, 0.9)])
        self.assertEqual(len(ranked), 4)  # flag, never remove
        by_id = {s["id"]: s for s in ranked}
        self.assertEqual(by_id["h2"]["deduped_by"], "h1")  # h2 ranked below h1
        for kept in ("h1", "h3", "h4"):
            self.assertNotIn("deduped_by", by_id[kept])
        # Inputs are not mutated.
        for s in self.SURVIVORS:
            self.assertNotIn("deduped_by", s)

    def test_deduped_by_points_at_highest_ranked_sibling_regardless_of_flag_order(self):
        ratings = {"h1": 1300.0, "h2": 1250.0, "h3": 1100.0, "h4": 1000.0}
        for flags in ([(0, 3, 0.9), (1, 3, 0.88)], [(1, 3, 0.88), (0, 3, 0.9)]):
            ranked = final_ranking(ratings, self.SURVIVORS, flags)
            by_id = {s["id"]: s for s in ranked}
            self.assertEqual(by_id["h4"]["deduped_by"], "h1")


class TestStateSchema(unittest.TestCase):
    def test_state_dict_keys_complete(self):
        survivors = [
            {"id": "h1", "statement": "s1", "rationale": "r1"},
            {"id": "h2", "statement": "s2", "rationale": "r2"},
        ]
        matrix = [[1.0, 0.9], [0.9, 1.0]]
        flags = dedup_flags(matrix)
        ratings = {"h1": ELO_INIT, "h2": ELO_INIT}
        elo_before = dict(ratings)
        # Canned debate verdicts: both orderings pick h1 -> score 1.0 for h1.
        score = debate_score("h1", "h2", "h1", "h1")
        ratings["h1"], ratings["h2"] = elo_update(ratings["h1"], ratings["h2"], score)
        record = build_match_record(
            ["h1", "h2"],
            "debate",
            [["h1", "h2"], ["h2", "h1"]],
            ["h1", "h1"],
            ["reason one", "reason two"],
            elo_before,
            dict(ratings),
        )
        self.assertEqual(
            set(record),
            {"pair", "tier", "orderings", "verdicts", "reasons", "elo_before", "elo_after"},
        )
        ranked = final_ranking(ratings, survivors, flags)
        state = build_state("fake-run-id", ratings, [record], ["h1", "h2"], matrix, flags, ranked)
        self.assertEqual(
            set(state),
            {"elo_init", "k_factor", "rng_seed", "ratings", "match_log", "proximity", "final_ranking"},
        )
        self.assertEqual(state["elo_init"], ELO_INIT)
        self.assertEqual(state["k_factor"], K_FACTOR)
        self.assertEqual(state["rng_seed"], "fake-run-id")
        self.assertEqual(set(state["proximity"]), {"matrix", "dedup_flags"})
        self.assertEqual(state["proximity"]["matrix"], {"h1_vs_h2": 0.9})
        self.assertEqual(state["proximity"]["dedup_flags"], [{"pair": ["h1", "h2"], "similarity": 0.9}])
        self.assertEqual(state["match_log"], [record])
        # h1 won at 1.0, so it ranks first; h2, the flagged near-dupe ranked
        # below its sibling, carries deduped_by.
        self.assertEqual(state["final_ranking"][0], {"id": "h1", "elo": ratings["h1"]})
        self.assertEqual(
            state["final_ranking"][1],
            {"id": "h2", "elo": ratings["h2"], "deduped_by": "h1"},
        )

    def test_matrix_pair_map_upper_triangle_only(self):
        matrix = [[1.0, 0.3, 0.4], [0.3, 1.0, 0.5], [0.4, 0.5, 1.0]]
        self.assertEqual(
            matrix_pair_map(["h1", "h2", "h3"], matrix),
            {"h1_vs_h2": 0.3, "h1_vs_h3": 0.4, "h2_vs_h3": 0.5},
        )


class TestK1Bypass(unittest.TestCase):
    def test_single_survivor_produces_no_matches(self):
        # The stage's trivial-branch condition: k == 1. With one survivor
        # there are no pairs, so no tournament invocation path exists.
        survivors = [NEAR_DUPE_1]
        k = len(survivors)
        self.assertEqual(k, 1)
        pairs = list(itertools.combinations(range(k), 2))
        self.assertEqual(pairs, [])
        self.assertEqual(order_matches(pairs, [[1.0]]), [])

    def test_stage1_retains_trivial_branch(self):
        source = (Path(__file__).resolve().parent.parent / "stages" / "stage1_ideation.py").read_text()
        self.assertIn("if k == 1:", source)
        self.assertIn('"ranking trivial (k=1)"', source)


class TestEndToEndFakeVerdicts(unittest.TestCase):
    def test_canned_judge_outputs_to_final_ranking(self):
        survivors = [
            {"id": "h1", "statement": "s1", "rationale": "r1"},
            {"id": "h2", "statement": "s2", "rationale": "r2"},
            {"id": "h3", "statement": "s3", "rationale": "r3"},
        ]
        # Proximity chosen so the match order is (0,1), (0,2), (1,2).
        matrix = [[1.0, 0.5, 0.3], [0.5, 1.0, 0.1], [0.3, 0.1, 1.0]]
        matches = order_matches(list(itertools.combinations(range(3), 2)), matrix)
        self.assertEqual(matches, [(0, 1), (0, 2), (1, 2)])

        ratings = {s["id"]: ELO_INIT for s in survivors}
        # Canned verdicts, applied in match order:
        #   h1 vs h2 -> h2 wins; h1 vs h3 -> h3 wins;
        #   h2 vs h3 -> debate orderings disagree -> draw.
        canned = {
            (0, 1): 0.0,  # score for the pair's first member (h1)
            (0, 2): 0.0,
            (1, 2): debate_score("h2", "h3", "h2", "h3"),
        }
        for i, j in matches:
            id_i, id_j = survivors[i]["id"], survivors[j]["id"]
            ratings[id_i], ratings[id_j] = elo_update(
                ratings[id_i], ratings[id_j], canned[(i, j)]
            )

        ranked = final_ranking(ratings, survivors)
        self.assertEqual([s["id"] for s in ranked], ["h2", "h3", "h1"])
        self.assertGreater(ratings["h2"], ratings["h3"])
        self.assertGreater(ratings["h3"], ratings["h1"])
        # Exact expected ratings, derived by hand from the Elo formula.
        self.assertAlmostEqual(ratings["h1"], 1168.74, places=1)
        self.assertAlmostEqual(ratings["h2"], 1215.97, places=1)
        self.assertAlmostEqual(ratings["h3"], 1215.30, places=1)


if __name__ == "__main__":
    unittest.main()
