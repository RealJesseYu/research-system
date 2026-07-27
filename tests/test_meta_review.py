"""
test_meta_review.py — Step 17-E tests: meta-review + feedback plumbing +
research overview + review 6 active + the stage-1 iteration controller +
the battery's --rounds threading. Deterministic, ZERO model calls:
model_call._invoke_transport is patched with a dispatching fake
(test_evolution.py's pattern), stage-level phases are patched at the
stage1_ideation namespace for controller tests, and every runs/ write lives
in a TemporaryDirectory the test chdirs into.

Covers the ruled minimum: meta-review validator accept/reject +
empty-feedback degradation (garbage replies, ack mismatch — never a crash);
feedback block composition (round-1 explicit empty block, the per-family
framings, the overview subsection present from round 2 and absent on round
1); review 6 active schema + None-inert path + the advisory property (the
deterministic kill filter is unaffected by its presence); the controller —
canonical files equal the last successful round, rounds.json appended per
round, trivial-marker tournament_state.json on k=1 replacing stale k>=2
state, zero-survivor round-2 termination vs the round-1 honest crash,
id-to-statement resolution (raw ids never cross a round boundary), exactly
one add_history per run(); and the battery — rounds threaded to run(),
default 1, and the new slot-record fields.

Run directly: venv/bin/python3 tests/test_meta_review.py
"""

from __future__ import annotations

import copy
import inspect
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "harness"))

import model_call  # noqa: E402
from baton import Baton  # noqa: E402
from harness import killrate_battery  # noqa: E402
from stages import meta_review, reflection_reviews, stage1_ideation, tournament  # noqa: E402
from stages.meta_review import (  # noqa: E402
    GENERATION_FRAMING,
    MAX_DIRECTIONS,
    MAX_FEEDBACK_ITEMS,
    REFLECTION_FRAMING,
    build_meta_review,
    compose_feedback_block,
    empty_feedback,
    meta_review_validator,
)


def valid_critique_reply(run_id: str) -> dict:
    return {
        "ack_run_id": run_id,
        "recurring_review_patterns": ["reviews keep flagging unsupported constants"],
        "recurring_debate_patterns": ["judges reward testability over novelty"],
        "feedback_to_generation": ["propose directly measurable claims"],
        "feedback_to_reflection": ["always check scale separation"],
        "feedback_to_ranking": ["watch for verbosity bias"],
        "research_overview": {
            "directions": [
                {
                    "summary": "vortex-strength scaling",
                    "justification": "two survivors converge on it",
                    "top_statements": ["alpha claim about vortex scaling"],
                    "suggested_experiments": ["sweep lid velocity"],
                }
            ]
        },
    }


# A prior-round tournament state already resolved to statements (what the
# controller hands review 6 — no ids anywhere).
RESOLVED_STATE = {
    "final_ranking": [
        {"statement": "alpha claim about vortex scaling", "elo": 1216.0},
        {"statement": "beta claim about corner eddies", "elo": 1184.0},
    ],
    "matches": [
        {
            "statements": [
                "alpha claim about vortex scaling",
                "beta claim about corner eddies",
            ],
            "tier": "single_turn",
            "winner_statements": ["alpha claim about vortex scaling"],
            "reasons": ["more directly testable"],
        }
    ],
    "dedup_flags": [],
}

FAKE_REFS = ([{"ref": "R1", "source": "fake", "title": "T", "snippet": "S"}], {"stub": True})


def fake_gather_review_refs(run_id, hypothesis):
    return copy.deepcopy(FAKE_REFS)


def make_fake_transport(config: dict | None = None):
    """Dispatching fake for model_call._invoke_transport (the
    test_evolution.py pattern): routes on the system prompt's identifying
    phrases, answers schema-valid JSON or configured misbehavior, unwraps
    re-ask turns. Counts calls per marker in config['calls'] when given."""
    config = config or {}
    calls: dict[str, int] = config.setdefault("calls", {})

    def fake(system_prompt: str, user_turn: str, model: str) -> str:
        inp = json.loads(user_turn)
        if isinstance(inp, dict) and "original_input" in inp:
            inp = inp["original_input"]
        run_id = inp.get("run_id")

        if "meta-review stage" in system_prompt:
            calls["meta_review"] = calls.get("meta_review", 0) + 1
            if config.get("meta_garbage"):
                return "this is not JSON at all"
            reply = valid_critique_reply(run_id)
            if config.get("meta_wrong_ack"):
                reply["ack_run_id"] = "some-other-run"
            return json.dumps(reply)
        if "recurrent-tournament-review unit" in system_prompt:
            calls["review6"] = calls.get("review6", 0) + 1
            if config.get("review6_forbidden"):
                raise AssertionError("review 6 must make NO model call on the inert path")
            observations = ["single-turn wins favored testability"]
            if config.get("review6_bad_first") and calls["review6"] == 1:
                observations = [f"obs {i}" for i in range(6)]  # over the cap of 5
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "hypothesis_id": inp["hypothesis_id"],
                    "observations": observations,
                    "carried_concerns": ["must beat the prior winner on testability"],
                }
            )
        if "initial-review unit" in system_prompt:
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "reviews": [
                        {"id": c["id"], "verdict": "pass", "reason": "test reason"}
                        for c in inp["candidates"]
                    ],
                }
            )
        if "full-review unit" in system_prompt:
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "hypothesis_id": inp["hypothesis_id"],
                    "novelty": "novel",
                    "novelty_rationale": "test rationale",
                    "novelty_grounded_in": [],
                    "critique": "test critique",
                    "quality": 3,
                }
            )
        if "scrutiny unit" in system_prompt:
            hid = inp["hypothesis_id"]
            flaw = config.get("fundamental", {}).get(hid, False)
            return json.dumps({
                "ack_run_id": run_id, "hypothesis_id": hid,
                "deep_verification": {
                    "assumptions": [{"assumption": "a1", "sub_assumptions": [],
                                     "evaluation": "correct"}],
                    "invalidating_elements": [],
                    "addressable_notes": ["carried concern"],
                    "fundamental_flaw": flaw, "summary": "test summary"},
                "observation": {"relevant_observations": [], "accounts_for": "yes",
                                "assessment": "test assessment"},
                "simulation": {"mental_simulation": ["step one"],
                               "failure_scenarios": [], "assessment": "test assessment"},
            })
        if "deep-verification unit" in system_prompt:
            hid = inp["hypothesis_id"]
            flaw = config.get("fundamental", {}).get(hid, False)
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "hypothesis_id": hid,
                    "assumptions": [
                        {"assumption": "a1", "sub_assumptions": [], "evaluation": "correct"},
                        {"assumption": "a2", "sub_assumptions": [], "evaluation": "correct"},
                    ],
                    "invalidating_elements": [],
                    "addressable_notes": ["carried concern"],
                    "fundamental_flaw": flaw,
                    "summary": "test summary",
                }
            )
        if "observation-review unit" in system_prompt:
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "hypothesis_id": inp["hypothesis_id"],
                    "relevant_observations": [],
                    "accounts_for": "yes",
                    "assessment": "test assessment",
                }
            )
        if "simulation-review unit" in system_prompt:
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "hypothesis_id": inp["hypothesis_id"],
                    "mental_simulation": ["step one", "step two", "step three"],
                    "failure_scenarios": [],
                    "assessment": "test assessment",
                }
            )
        if "advocate turn" in system_prompt:
            return json.dumps(
                {"ack_run_id": run_id, "argument": "A test argument. Second sentence."}
            )
        if "judge turn concluding" in system_prompt or "comparative-judge stage" in system_prompt:
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "winner_id": inp["hypothesis_a"]["id"],
                    "reason": "test verdict",
                }
            )
        raise AssertionError(f"unmatched system prompt: {system_prompt[:80]!r}")

    return fake


class TmpRunDirTest(unittest.TestCase):
    """chdir into a TemporaryDirectory so every runs/ write is isolated."""

    run_id = "meta-test"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = Path.cwd()
        os.chdir(self._tmp.name)
        self.run_dir = Path("runs") / self.run_id / "stage1"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _log_text(self) -> str:
        return (Path("runs") / self.run_id / "log.txt").read_text()


# --- compose_feedback_block ---------------------------------------------------


class TestComposeFeedbackBlock(unittest.TestCase):
    def test_round_1_is_explicit_empty_block(self):
        for family in ("generation", "reflection", "ranking"):
            block = compose_feedback_block(family, [], 1)
            self.assertIn(f"META-REVIEW FEEDBACK ({family}, entering round 1)", block)
            self.assertIn("none — this is the first round", block)
            # no framing, no items, no overview on the round-1 empty block
            self.assertNotIn(GENERATION_FRAMING, block)
            self.assertNotIn(REFLECTION_FRAMING, block)
            self.assertNotIn("RESEARCH-OVERVIEW DIRECTIONS", block)
        # round 1 ignores items and overview even if handed some
        block = compose_feedback_block(
            "generation", ["tip"], 1, overview={"directions": [{"summary": "s"}]}
        )
        self.assertNotIn("tip", block)
        self.assertNotIn("RESEARCH-OVERVIEW DIRECTIONS", block)

    def test_generation_framing_and_overview_subsection_round_2(self):
        overview = {
            "directions": [
                {"summary": "vortex-strength scaling", "justification": "two survivors"}
            ]
        }
        block = compose_feedback_block(
            "generation", ["propose measurable claims"], 2, overview=overview
        )
        self.assertIn(GENERATION_FRAMING, block)
        self.assertIn("over-fitting", GENERATION_FRAMING)
        self.assertIn("- propose measurable claims", block)
        self.assertIn("RESEARCH-OVERVIEW DIRECTIONS", block)
        self.assertIn("vortex-strength scaling", block)
        self.assertIn("two survivors", block)

    def test_generation_without_overview_has_no_subsection(self):
        block = compose_feedback_block("generation", ["tip"], 2)
        self.assertNotIn("RESEARCH-OVERVIEW DIRECTIONS", block)

    def test_reflection_framing(self):
        block = compose_feedback_block("reflection", ["check scale separation"], 2)
        self.assertIn(REFLECTION_FRAMING, block)
        self.assertIn("definitively address", block)
        self.assertIn("- check scale separation", block)
        self.assertNotIn("RESEARCH-OVERVIEW DIRECTIONS", block)

    def test_ranking_is_plain_labeled(self):
        block = compose_feedback_block("ranking", ["watch verbosity bias"], 2)
        self.assertIn("META-REVIEW FEEDBACK (ranking, entering round 2)", block)
        self.assertNotIn(GENERATION_FRAMING, block)
        self.assertNotIn(REFLECTION_FRAMING, block)
        self.assertIn("- watch verbosity bias", block)

    def test_empty_items_round_2_says_so(self):
        block = compose_feedback_block("ranking", [], 2)
        self.assertIn("no feedback items", block)

    def test_deterministic_and_unknown_family_raises(self):
        self.assertEqual(
            compose_feedback_block("reflection", ["x"], 3),
            compose_feedback_block("reflection", ["x"], 3),
        )
        with self.assertRaises(ValueError):
            compose_feedback_block("thought_layer", [], 2)


# --- meta_review_validator ------------------------------------------------------


class TestMetaReviewValidator(unittest.TestCase):
    def test_valid_reply_accepted(self):
        self.assertEqual(meta_review_validator(valid_critique_reply("rid")), [])

    def test_empty_lists_accepted(self):
        reply = empty_feedback()
        reply["ack_run_id"] = "rid"
        self.assertEqual(meta_review_validator(reply), [])

    def test_non_list_field_rejected(self):
        reply = valid_critique_reply("rid")
        reply["feedback_to_generation"] = "just a string"
        errors = meta_review_validator(reply)
        self.assertTrue(any("feedback_to_generation" in e for e in errors))

    def test_over_cap_list_rejected(self):
        reply = valid_critique_reply("rid")
        reply["feedback_to_reflection"] = [f"item {i}" for i in range(MAX_FEEDBACK_ITEMS + 1)]
        errors = meta_review_validator(reply)
        self.assertTrue(any("feedback_to_reflection" in e for e in errors))

    def test_overview_shape_rejected(self):
        reply = valid_critique_reply("rid")
        reply["research_overview"] = {"directions": "nope"}
        errors = meta_review_validator(reply)
        self.assertTrue(any("research_overview" in e for e in errors))

    def test_too_many_directions_rejected(self):
        reply = valid_critique_reply("rid")
        direction = reply["research_overview"]["directions"][0]
        reply["research_overview"]["directions"] = [dict(direction)] * (MAX_DIRECTIONS + 1)
        errors = meta_review_validator(reply)
        self.assertTrue(any("directions" in e for e in errors))

    def test_direction_field_errors(self):
        reply = valid_critique_reply("rid")
        reply["research_overview"]["directions"][0]["justification"] = ""
        reply["research_overview"]["directions"][0]["top_statements"] = [1, 2]
        errors = meta_review_validator(reply)
        self.assertTrue(any("justification" in e for e in errors))
        self.assertTrue(any("top_statements" in e for e in errors))


# --- build_meta_review -----------------------------------------------------------


class TestBuildMetaReview(TmpRunDirTest):
    ROUND_RECORD = {"round": 1, "domain": "d", "reflection_outcomes": [],
                    "evolution_outcomes": [], "tournament": {"note": "trivial"}}

    def _build(self, config=None):
        with patch.object(model_call, "_invoke_transport", make_fake_transport(config)), \
                patch("model_call.time.sleep"):
            return build_meta_review(self.run_id, 1, self.ROUND_RECORD)

    def test_success_returns_critique(self):
        critique = self._build()
        self.assertNotIn("ack_run_id", critique)
        self.assertNotIn("degraded", critique)
        self.assertEqual(
            critique["feedback_to_generation"], ["propose directly measurable claims"]
        )
        self.assertEqual(
            critique["research_overview"]["directions"][0]["summary"],
            "vortex-strength scaling",
        )
        log = self._log_text()
        self.assertIn("STAGE_MODEL_CALL stage=stage1_meta_review", log)
        self.assertIn("STAGE1_METAREVIEW round 1:", log)

    def test_validation_exhaustion_degrades_to_empty_feedback(self):
        critique = self._build(config={"meta_garbage": True})
        expected = empty_feedback()
        self.assertEqual(
            {k: v for k, v in critique.items() if k != "degraded"}, expected
        )
        self.assertIn("meta-review failed", critique["degraded"])
        self.assertIn("STAGE1_METAREVIEW round 1 FAILED", self._log_text())

    def test_ack_mismatch_degrades_to_empty_feedback(self):
        critique = self._build(config={"meta_wrong_ack": True})
        self.assertIn("degraded", critique)
        self.assertEqual(critique["research_overview"], {"directions": []})


# --- Review 6 ---------------------------------------------------------------------


HYP = {"id": "h1", "statement": "gamma claim about mesh effects", "rationale": "r"}


class TestReview6(TmpRunDirTest):
    def test_none_state_is_inert_no_model_call(self):
        with patch.object(
            model_call, "_invoke_transport",
            make_fake_transport({"review6_forbidden": True}),
        ):
            result = reflection_reviews.recurrent_tournament_review(self.run_id, HYP, None)
        self.assertEqual(result["status"], "inert")
        self.assertIn("no prior-round tournament results", result["reason"])

    def test_active_schema_and_validator(self):
        # first reply violates the 5-item cap, the re-ask loop recovers
        config = {"review6_bad_first": True}
        with patch.object(model_call, "_invoke_transport", make_fake_transport(config)), \
                patch("model_call.time.sleep"):
            result = reflection_reviews.recurrent_tournament_review(
                self.run_id, HYP, copy.deepcopy(RESOLVED_STATE)
            )
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["observations"], ["single-turn wins favored testability"])
        self.assertEqual(
            result["carried_concerns"], ["must beat the prior winner on testability"]
        )
        self.assertEqual(config["calls"]["review6"], 2)
        log = self._log_text()
        self.assertIn("RE-ASK stage=stage1_reflection_tournament_h1", log)
        self.assertIn("STAGE1_REVIEW6 h1:", log)

    def test_advisory_kill_filter_unaffected(self):
        """Same pool, same review verdicts, with and without review 6 active:
        the reflections (and thus every deterministic kill) are identical."""
        pool = [
            {"id": "h1", "statement": "gamma claim about mesh effects", "rationale": "r"},
            {"id": "h2", "statement": "delta claim about wall friction", "rationale": "r"},
        ]
        config = {"fundamental": {"h2": True}}

        def reflect(run_id, state):
            (Path("runs") / run_id / "stage1").mkdir(parents=True, exist_ok=True)
            with patch.object(model_call, "_invoke_transport", make_fake_transport(dict(config))), \
                    patch.object(reflection_reviews, "gather_review_refs", fake_gather_review_refs), \
                    patch("model_call.time.sleep"):
                return reflection_reviews.reflect_on_pool(
                    run_id, "test domain", copy.deepcopy(pool), None,
                    Path("runs") / run_id / "stage1",
                    tournament_state=state,
                )

        reflections_inert, summary_inert = reflect("meta-test", None)
        reflections_active, summary_active = reflect(
            "meta-test-active", copy.deepcopy(RESOLVED_STATE)
        )
        self.assertEqual(reflections_inert, reflections_active)
        self.assertEqual(summary_inert, summary_active)
        # h2's fundamental flaw killed it in BOTH runs — review 6 changed nothing
        self.assertEqual([r["hypothesis_id"] for r in reflections_active], ["h1"])

        inert_ev = json.loads((self.run_dir / "reflection_reviews.json").read_text())
        active_ev = json.loads(
            (Path("runs") / "meta-test-active" / "stage1" / "reflection_reviews.json").read_text()
        )
        self.assertIn("inert", inert_ev["tournament_review_status"])
        self.assertEqual(active_ev["tournament_review_status"], "active")
        for review in active_ev["reviews"]:
            self.assertEqual(review["tournament"]["status"], "active")
        self.assertIn(
            "STAGE1_REVIEW6 inert", (Path("runs") / "meta-test" / "log.txt").read_text()
        )


# --- resolve_tournament_to_statements ----------------------------------------------


class TestResolveTournament(unittest.TestCase):
    def test_ids_fully_resolved(self):
        survivors = [
            {"id": "h1", "statement": "alpha claim about vortex scaling", "rationale": "r"},
            {"id": "h2", "statement": "beta claim about corner eddies", "rationale": "r"},
        ]
        ratings = {"h1": 1216.0, "h2": 1184.0}
        record = tournament.build_match_record(
            ["h1", "h2"], "single_turn", [["h1", "h2"]], ["h1"],
            ["more directly testable"], {"h1": 1200.0, "h2": 1200.0}, dict(ratings),
        )
        ranked = tournament.final_ranking(ratings, survivors, [(0, 1, 0.9)])
        state = tournament.build_state(
            "seed", ratings, [record], ["h1", "h2"],
            [[1.0, 0.9], [0.9, 1.0]], [(0, 1, 0.9)], ranked,
        )
        statements = {s["id"]: s["statement"] for s in survivors}
        resolved = stage1_ideation.resolve_tournament_to_statements(state, statements)
        dumped = json.dumps(resolved)
        self.assertNotIn('"h1"', dumped)
        self.assertNotIn('"h2"', dumped)
        self.assertEqual(
            resolved["final_ranking"][0],
            {"statement": "alpha claim about vortex scaling", "elo": 1216.0},
        )
        self.assertEqual(
            resolved["matches"][0]["winner_statements"],
            ["alpha claim about vortex scaling"],
        )
        self.assertEqual(resolved["matches"][0]["reasons"], ["more directly testable"])
        self.assertEqual(
            resolved["dedup_flags"][0]["statements"],
            ["alpha claim about vortex scaling", "beta claim about corner eddies"],
        )


# --- Iteration controller -----------------------------------------------------------


def pool_of(statements: list[str]) -> list[dict]:
    return [
        {"id": f"h{n}", "statement": s, "rationale": f"rationale {n}"}
        for n, s in enumerate(statements, start=1)
    ]


def reflections_for(pool: list[dict]) -> list[dict]:
    return [
        {
            "hypothesis_id": h["id"],
            "novelty": "novel",
            "critique": "fine",
            "quality": 3,
            "addressable_notes": [],
        }
        for h in pool
    ]


class ControllerTest(TmpRunDirTest):
    run_id = "ctl-test"

    def _baton(self):
        return Baton(
            run_id=self.run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            mode="auto",
            payload={"domain": "test domain"},
            history=[],
        )

    def _run(self, round_pools, critique_fn=None, reflect_raises=None,
             rounds=None, transport_config=None):
        """Drive stage1_ideation.run with phase fakes. round_pools[i] is the
        pool Generation 'produces' in round i+1; reflect_raises maps a round
        number to an exception the reflection fake raises there. Captures
        per-round kwargs for assertions."""
        captured = {"gen": [], "refl": [], "meta": []}
        call_no = {"gen": 0, "refl": 0}

        def fake_generate(run_id, domain, memory_block, run_dir, meta_review_feedback=None):
            call_no["gen"] += 1
            captured["gen"].append(meta_review_feedback)
            return copy.deepcopy(round_pools[call_no["gen"] - 1])

        def fake_reflect(run_id, domain, hypotheses, memory_block, run_dir,
                         tournament_state=None, feedback_block=None):
            call_no["refl"] += 1
            captured["refl"].append(
                {"tournament_state": tournament_state, "feedback_block": feedback_block}
            )
            if reflect_raises and call_no["refl"] in reflect_raises:
                raise reflect_raises[call_no["refl"]]
            summary = {
                "pool": len(hypotheses),
                "initial_pass": len(hypotheses),
                "fundamental_flaw_discards": 0,
                "reflected": len(hypotheses),
            }
            return reflections_for(hypotheses), summary

        def fake_evolve(run_id, domain, survivors_full, memory_block, run_dir):
            return []

        def standard_critique(run_id, round_index, round_record):
            reply = valid_critique_reply(run_id)
            reply.pop("ack_run_id")
            return reply

        default_critique = critique_fn or standard_critique

        def fake_meta(run_id, round_index, round_record):
            captured["meta"].append({"round_index": round_index, "round_record": round_record})
            return default_critique(run_id, round_index, round_record)

        baton = self._baton()
        with patch.object(stage1_ideation, "generate_candidate_pool", fake_generate), \
                patch.object(stage1_ideation, "reflect_on_pool", fake_reflect), \
                patch.object(stage1_ideation, "evolve_and_review", fake_evolve), \
                patch.object(stage1_ideation, "journal_recent_by_kind", lambda *a, **k: []), \
                patch.object(stage1_ideation, "build_meta_review", fake_meta), \
                patch.object(model_call, "_invoke_transport",
                             make_fake_transport(transport_config)), \
                patch("model_call.time.sleep"):
            baton = stage1_ideation.run(baton, rounds=rounds)
        return baton, captured

    def test_two_rounds_canonical_files_rounds_json_and_feedback(self):
        baton, captured = self._run(
            [pool_of(["round one claim"]), pool_of(["round two claim"])], rounds=2
        )

        # canonical stage1 files == the LAST successful round's
        canonical = json.loads((self.run_dir / "survivors.json").read_text())
        self.assertEqual(canonical[0]["statement"], "round two claim")
        round1 = json.loads((self.run_dir / "round1" / "survivors.json").read_text())
        self.assertEqual(round1[0]["statement"], "round one claim")

        # rounds.json: two appended entries, audit fields present
        entries = json.loads((self.run_dir / "rounds.json").read_text())
        self.assertEqual([e["round"] for e in entries], [1, 2])
        self.assertEqual(entries[0]["pool_statements"], ["round one claim"])
        self.assertEqual(entries[0]["k"], 1)
        self.assertIsNone(entries[0]["termination_reason"])
        self.assertEqual(entries[1]["termination_reason"], "round_budget_exhausted")
        # the full critique is recorded per round — the final round's too
        # (recorded but unconsumed)
        for entry in entries:
            self.assertEqual(
                entry["meta_review"]["feedback_to_generation"],
                ["propose directly measurable claims"],
            )
        self.assertEqual(len(captured["meta"]), 2)  # meta-review after EVERY round

        # research_overview.json = last round's synthesis, never in the baton
        overview = json.loads((self.run_dir / "research_overview.json").read_text())
        self.assertEqual(overview["round"], 2)
        self.assertEqual(overview["directions"][0]["summary"], "vortex-strength scaling")
        self.assertNotIn("research_overview", baton.payload)

        # trivial marker stands canonically (k=1 both rounds)
        state = json.loads((self.run_dir / "tournament_state.json").read_text())
        self.assertIs(state["trivial"], True)

        # feedback blocks: round 1 explicit empty; round 2 framed + overview
        self.assertIn("none — this is the first round", captured["gen"][0])
        self.assertIn(GENERATION_FRAMING, captured["gen"][1])
        self.assertIn("- propose directly measurable claims", captured["gen"][1])
        self.assertIn("RESEARCH-OVERVIEW DIRECTIONS", captured["gen"][1])
        self.assertNotIn("RESEARCH-OVERVIEW DIRECTIONS", captured["gen"][0])
        self.assertIn("none — this is the first round", captured["refl"][0]["feedback_block"])
        self.assertIn(REFLECTION_FRAMING, captured["refl"][1]["feedback_block"])
        self.assertIn("- always check scale separation", captured["refl"][1]["feedback_block"])

        # review-6 threading: round 1 None; round 2 None too (round 1 was trivial)
        self.assertIsNone(captured["refl"][0]["tournament_state"])
        self.assertIsNone(captured["refl"][1]["tournament_state"])

        # payload from the last round; exactly ONE history entry
        self.assertEqual(baton.payload["hypotheses"][0]["statement"], "round two claim")
        self.assertEqual(len(baton.history), 1)
        self.assertIn("2 round(s), termination round_budget_exhausted", baton.history[0]["note"])

    def test_round2_receives_resolved_state_and_trivial_marker_replaces_stale(self):
        # round 1: k=2 -> a real tournament (fake judges); round 2: k=1
        baton, captured = self._run(
            rounds=2,
            round_pools=[
                pool_of(["alpha claim about vortex scaling", "beta claim about corner eddies"]),
                pool_of(["round two claim"]),
            ]
        )
        state_r2 = captured["refl"][1]["tournament_state"]
        self.assertIsNotNone(state_r2)
        dumped = json.dumps(state_r2)
        self.assertNotIn('"h1"', dumped)  # ids never cross a round boundary
        self.assertNotIn('"h2"', dumped)
        self.assertEqual(
            {e["statement"] for e in state_r2["final_ranking"]},
            {"alpha claim about vortex scaling", "beta claim about corner eddies"},
        )
        self.assertTrue(state_r2["matches"])
        self.assertTrue(all(m["reasons"] for m in state_r2["matches"]))

        # round 1 wrote a real multi-candidate state...
        state1 = json.loads((self.run_dir / "round1" / "tournament_state.json").read_text())
        self.assertIn("ratings", state1)
        # ...and round 2's trivial marker REPLACED it canonically
        canonical_state = json.loads((self.run_dir / "tournament_state.json").read_text())
        self.assertIs(canonical_state.get("trivial"), True)

        # meta-review round 1 received the resolved tournament (no ids)
        meta_r1 = captured["meta"][0]["round_record"]
        self.assertNotIn('"h1"', json.dumps(meta_r1["tournament"]))

    def test_zero_survivor_round2_terminates_standing_on_round1(self):
        boom = RuntimeError(
            "stage1 reflection: all 10 candidates were discarded (...). "
            "Zero reviewed hypotheses remain — this run halts here rather than "
            "continuing on a hypothesis nobody vetted."
        )
        baton, captured = self._run(
            [pool_of(["round one claim"]), pool_of(["round two claim"])],
            reflect_raises={2: boom}, rounds=2,
        )
        # stands on round 1
        self.assertEqual(baton.payload["hypotheses"][0]["statement"], "round one claim")
        canonical = json.loads((self.run_dir / "survivors.json").read_text())
        self.assertEqual(canonical[0]["statement"], "round one claim")
        entries = json.loads((self.run_dir / "rounds.json").read_text())
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1]["termination_reason"], "zero_survivors_terminated")
        self.assertEqual(entries[1]["k"], 0)
        self.assertIsNone(entries[1]["meta_review"])
        self.assertEqual(len(captured["meta"]), 1)  # no meta-review for the dead round
        self.assertEqual(len(baton.history), 1)
        self.assertIn("1 round(s), termination zero_survivors_terminated", baton.history[0]["note"])
        overview = json.loads((self.run_dir / "research_overview.json").read_text())
        self.assertEqual(overview["round"], 1)  # last successful round's synthesis

    def test_zero_survivor_round1_crashes_honestly(self):
        boom = RuntimeError(
            "stage1_ideation: all 10 hypotheses were judged 'known' against the "
            "literature. Zero survivors — there is no validated hypothesis ..."
        )
        with self.assertRaises(RuntimeError):
            self._run([pool_of(["round one claim"])], reflect_raises={1: boom})

    def test_non_zero_survivor_error_crashes_in_any_round(self):
        boom = RuntimeError("arXiv HTTP 429 through the bounded retry")
        with self.assertRaises(RuntimeError):
            self._run(
                [pool_of(["round one claim"]), pool_of(["round two claim"])],
                reflect_raises={2: boom}, rounds=2,
            )

    def test_survivor_count_cap_terminates_early(self):
        four = pool_of(
            [
                "alpha claim about vortex scaling",
                "beta claim about corner eddies",
                "gamma claim about mesh effects",
                "delta claim about wall friction",
            ]
        )
        baton, captured = self._run(
            [four, pool_of(["never reached"]), pool_of(["never reached either"])],
            rounds=3,
        )
        self.assertEqual(len(captured["gen"]), 1)  # rounds 2 and 3 never launched
        entries = json.loads((self.run_dir / "rounds.json").read_text())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["k"], 4)
        self.assertEqual(entries[0]["termination_reason"], "survivor_count_cap")
        self.assertEqual(len(captured["meta"]), 1)  # boundary meta-review still ran
        self.assertEqual(len(baton.history), 1)

    def test_rounds_default_constant(self):
        # CHANGED 2026-07-27: the default is 1. A second round re-runs the WHOLE
        # reflection chain over the whole pool, doubling the most expensive thing
        # in the system — live, it was heading for eight hours of ideation before
        # a single experiment ran. Two rounds must be CHOSEN.
        self.assertEqual(stage1_ideation.ROUNDS, 1)
        self.assertIsNone(
            inspect.signature(stage1_ideation.run).parameters["rounds"].default
        )


# --- Battery: --rounds threading and the new slot fields -----------------------------


class TestBatteryRounds(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_launch_one_threads_rounds_and_records_new_fields(self):
        captured = {}

        def fake_run(baton, rounds=None):
            captured["rounds"] = rounds
            stage1 = self.root / "runs" / baton.run_id / "stage1"
            stage1.mkdir(parents=True, exist_ok=True)
            (stage1 / "retrieved_memory.json").write_text("[]")
            (stage1 / "reflection_reviews.json").write_text(
                json.dumps({"initial_survivor_count": 4,
                            "discarded_by_deep_verification": [{"id": "h9"}]})
            )
            (stage1 / "survivors.json").write_text(
                json.dumps([{"id": "h1"}, {"id": "h2"}])
            )
            (stage1 / "evolution_variants.json").write_text(
                json.dumps([
                    {"id": "ev1", "accepted": True, "reject_reason": None},
                    {"id": "ev2", "accepted": False, "reject_reason": "judged_known"},
                ])
            )
            (stage1 / "rounds.json").write_text(
                json.dumps([
                    {"round": 1, "termination_reason": None},
                    {"round": 2, "termination_reason": "round_budget_exhausted"},
                ])
            )
            baton.payload["hypotheses"] = [{"id": "h1", "statement": "s", "rationale": "r"}]
            baton.payload["hypotheses_ranked"] = True
            return baton

        with patch.object(killrate_battery, "_PROJECT_ROOT", self.root), \
                patch.object(stage1_ideation, "run", fake_run):
            record = killrate_battery._launch_one("same1", "test domain", 2)

        self.assertEqual(captured["rounds"], 2)
        self.assertEqual(record["status"], "scored")
        self.assertEqual(record["k"], 2)  # k derivation untouched
        self.assertEqual(record["variants_emitted"], 2)
        self.assertEqual(record["variants_accepted"], 1)
        self.assertEqual(record["rounds_completed"], 2)
        self.assertEqual(record["termination_reason"], "round_budget_exhausted")
        self.assertIsNone(record["exception"])

    def test_launch_one_zero_survivor_termination_counts_completed_rounds(self):
        def fake_run(baton, rounds=None):
            stage1 = self.root / "runs" / baton.run_id / "stage1"
            stage1.mkdir(parents=True, exist_ok=True)
            (stage1 / "retrieved_memory.json").write_text("[]")
            (stage1 / "reflection_reviews.json").write_text(
                json.dumps({"initial_survivor_count": 4,
                            "discarded_by_deep_verification": []})
            )
            (stage1 / "survivors.json").write_text(json.dumps([{"id": "h1"}]))
            (stage1 / "rounds.json").write_text(
                json.dumps([
                    {"round": 1, "termination_reason": None},
                    {"round": 2, "termination_reason": "zero_survivors_terminated"},
                ])
            )
            return baton

        with patch.object(killrate_battery, "_PROJECT_ROOT", self.root), \
                patch.object(stage1_ideation, "run", fake_run):
            record = killrate_battery._launch_one("alt1", "test domain", 2)
        self.assertEqual(record["rounds_completed"], 1)
        self.assertEqual(record["termination_reason"], "zero_survivors_terminated")

    def test_battery_defaults_to_single_pass(self):
        self.assertEqual(
            inspect.signature(killrate_battery.run_battery).parameters["rounds"].default, 1
        )
        self.assertEqual(
            inspect.signature(killrate_battery.print_dry_run).parameters["rounds"].default, 1
        )
        self.assertEqual(
            inspect.signature(killrate_battery._launch_one).parameters["rounds"].kind,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )

    def test_rounds_info_absent_file(self):
        self.assertEqual(killrate_battery._rounds_info(self.root), (None, None))


if __name__ == "__main__":
    unittest.main()
