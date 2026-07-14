"""
test_evolution.py — Step 17-D Evolution tests. Deterministic, ZERO model
calls: model_call._invoke_transport is patched with a dispatching fake
(test_transport_retry.py's pattern), retrieval functions are patched at the
namespaces Evolution imported them into, and every run dir lives in a
TemporaryDirectory the test chdirs into.

Covers the ruled minimum: rotation determinism from run_id; combination
fallback at 1 parent; emitted-variant schema + id/provenance shape;
zero-accept tolerance (no raise, parents-only pool); pool assembly
(survivors_full unmutated, survivors.json byte-identical before/after); the
trivial branch keyed off tournament_pool; the survival-counter HARD
INVARIANT (4 survivors + 2 variants -> k == 4 AND variants_emitted == 2);
and the handfeed side-door fallback, hit and miss.

Run directly: venv/bin/python3 tests/test_evolution.py
"""

from __future__ import annotations

import copy
import json
import os
import random
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
import handfeed_stage2  # noqa: E402
import survival_counter  # noqa: E402
from baton import Baton  # noqa: E402
from stages import evolution_strategies, stage1_ideation  # noqa: E402
from stages.evolution_strategies import (  # noqa: E402
    EVOLUTION_MAX_VARIANTS,
    EVOLUTION_MODEL,
    ROTATION_STRATEGIES,
    choose_rotation,
    evolve_and_review,
    plan_variants,
)

PARENTS = [
    {
        "id": "h1",
        "statement": "Vortex core precession frequency scales with lid velocity in a cavity.",
        "rationale": "Benchmark tabulations suggest kinematic coupling.",
        "novelty": "novel",
        "critique": "sound",
        "quality": 4,
        "addressable_notes": [],
    },
    {
        "id": "h2",
        "statement": "Secondary eddy strength saturates beyond a threshold aspect ratio.",
        "rationale": "Geometry bounds the recirculation budget.",
        "novelty": "novel",
        "critique": "sound",
        "quality": 3,
        "addressable_notes": [],
    },
]

FAKE_REFS = ([{"ref": "R1", "source": "fake", "title": "T", "snippet": "S"}], {"stub": True})


def fake_gather_review_refs(run_id, hypothesis):
    return copy.deepcopy(FAKE_REFS)


def run_id_with_rotation(strategy: str, prefix: str = "rot") -> str:
    """Deterministically find a run_id whose variant-2 rotation lands on
    `strategy` — pure RNG arithmetic, no model, no I/O."""
    for i in range(10000):
        rid = f"{prefix}{i}"
        if choose_rotation(rid) == strategy:
            return rid
    raise AssertionError(f"no run_id found rotating to {strategy}")


def make_fake_transport(config: dict | None = None):
    """A dispatching fake for model_call._invoke_transport: routes on the
    system prompt's identifying phrases and answers with schema-valid JSON
    (or configured misbehavior). Handles re-ask turns by unwrapping
    original_input."""
    config = config or {}

    def fake(system_prompt: str, user_turn: str, model: str) -> str:
        inp = json.loads(user_turn)
        if isinstance(inp, dict) and "original_input" in inp:
            inp = inp["original_input"]
        run_id = inp.get("run_id")

        if "initial-review unit" in system_prompt:
            verdicts = config.get("initial_verdicts", {})
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "reviews": [
                        {
                            "id": c["id"],
                            "verdict": verdicts.get(c["id"], "pass"),
                            "reason": "test reason",
                        }
                        for c in inp["candidates"]
                    ],
                }
            )
        if "full-review unit" in system_prompt:
            hid = inp["hypothesis_id"]
            novelty = config.get("novelty", {}).get(hid, "novel")
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "hypothesis_id": hid,
                    "novelty": novelty,
                    "novelty_rationale": "test rationale",
                    "novelty_grounded_in": ["R1"] if novelty == "known" else [],
                    "critique": "test critique",
                    "quality": 3,
                }
            )
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
                {"ack_run_id": run_id, "argument": "A test argument in two sentences. Second."}
            )
        if "judge turn concluding" in system_prompt or "comparative-judge stage" in system_prompt:
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "winner_id": inp["hypothesis_a"]["id"],
                    "reason": "test verdict",
                }
            )
        for marker, word in (
            ("simplification evolution strategy", "simplified boundary layer separation onset"),
            ("grounding-enhancement evolution strategy", "grounded shear stress plateau measurement"),
            ("combination evolution strategy", "combined precession saturation interplay claim"),
            ("out-of-the-box evolution strategy", "inverted regime rotating frame analogy"),
        ):
            if marker in system_prompt:
                if config.get("emission_garbage"):
                    return "this is not JSON at all"
                return json.dumps(
                    {
                        "ack_run_id": run_id,
                        "statement": f"Variant statement about {word}.",
                        "rationale": f"Variant rationale about {word}.",
                    }
                )
        raise AssertionError(f"unmatched system prompt: {system_prompt[:80]!r}")

    return fake


class TmpRunDirTest(unittest.TestCase):
    """chdir into a TemporaryDirectory so every runs/ write is isolated —
    same pattern as test_transport_retry.py."""

    run_id = "evo-test"

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

    def _variants_file(self) -> list:
        return json.loads((self.run_dir / "evolution_variants.json").read_text())


class TestRuntimePolicy(unittest.TestCase):
    def test_rotation_deterministic_from_run_id(self):
        for rid in ("20260711T000000Z", "abc", "x1"):
            expected = random.Random(f"{rid}:evolution").choice(list(ROTATION_STRATEGIES))
            self.assertEqual(choose_rotation(rid), expected)
            # stable across repeated calls — an independent RNG instance each time
            self.assertEqual(choose_rotation(rid), choose_rotation(rid))

    def test_rotation_covers_all_three_strategies(self):
        seen = {choose_rotation(f"cover{i}") for i in range(200)}
        self.assertEqual(seen, set(ROTATION_STRATEGIES))

    def test_variant1_always_simplification_of_top_parent(self):
        for rid in ("a", "b", "c", "d"):
            plan = plan_variants(rid, PARENTS)
            self.assertEqual(len(plan), EVOLUTION_MAX_VARIANTS)
            self.assertEqual(plan[0]["slot"], 1)
            self.assertEqual(plan[0]["strategy"], "simplification")
            self.assertEqual(plan[0]["parent_ids"], ["h1"])

    def test_combination_fallback_at_one_parent(self):
        rid = run_id_with_rotation("combination")
        # with 2 parents: combination over the top two
        plan2 = plan_variants(rid, PARENTS)
        self.assertEqual(plan2[1]["strategy"], "combination")
        self.assertEqual(plan2[1]["parent_ids"], ["h1", "h2"])
        self.assertNotIn("fallback_from", plan2[1])
        # with 1 parent: fall back to out_of_box, fallback recorded
        plan1 = plan_variants(rid, PARENTS[:1])
        self.assertEqual(plan1[1]["strategy"], "out_of_box")
        self.assertEqual(plan1[1]["parent_ids"], ["h1"])
        self.assertEqual(plan1[1]["fallback_from"], "combination")


class TestEvolveAndReview(TmpRunDirTest):
    def _evolve(self, config=None, parents=PARENTS, run_id=None,
                gather=fake_gather_review_refs, openalex=None):
        run_id = run_id or self.run_id
        if run_id != self.run_id:
            (Path("runs") / run_id / "stage1").mkdir(parents=True, exist_ok=True)
        run_dir = Path("runs") / run_id / "stage1"
        # search_openalex is ALWAYS patched: rotation may land on
        # grounding_enhancement for any run_id, and no test may touch HTTP.
        openalex = openalex or (lambda query, top_k=3: [])
        with patch.object(model_call, "_invoke_transport", make_fake_transport(config)), \
                patch.object(evolution_strategies, "gather_review_refs", gather), \
                patch.object(evolution_strategies, "search_openalex", openalex), \
                patch("model_call.time.sleep"):
            accepted = evolve_and_review(run_id, "test domain", parents, None, run_dir)
        return accepted, json.loads((run_dir / "evolution_variants.json").read_text())

    def test_emitted_schema_ids_and_provenance(self):
        accepted, records = self._evolve()
        self.assertEqual(len(records), 2)
        parent_ids = {p["id"] for p in PARENTS}
        seen_ids = [r["id"] for r in records]
        self.assertEqual(seen_ids, ["ev1", "ev2"])
        self.assertEqual(len(set(seen_ids)), 2)
        for r in records:
            self.assertTrue(r["id"].startswith("ev"))
            self.assertNotIn(r["id"], parent_ids)
            for field in ("id", "statement", "rationale", "novelty", "critique",
                          "quality", "addressable_notes", "provenance", "accepted",
                          "reject_reason"):
                self.assertIn(field, r)
            prov = r["provenance"]
            self.assertEqual(set(prov), {"parent_ids", "strategy", "model"})
            self.assertEqual(prov["model"], EVOLUTION_MODEL)
            self.assertEqual(EVOLUTION_MODEL, "claude-sonnet-4-6")
            self.assertTrue(set(prov["parent_ids"]) <= parent_ids)
            self.assertTrue(r["accepted"])
            self.assertIsNone(r["reject_reason"])
        self.assertEqual(records[0]["provenance"]["strategy"], "simplification")
        self.assertEqual(records[0]["provenance"]["parent_ids"], ["h1"])
        # accepted pool entries carry exactly the 7 survivor fields
        self.assertEqual(len(accepted), 2)
        for a in accepted:
            self.assertEqual(
                set(a),
                {"id", "statement", "rationale", "novelty", "critique", "quality",
                 "addressable_notes"},
            )
            self.assertEqual(a["novelty"], "novel")
            self.assertEqual(a["addressable_notes"], ["carried concern"])

    def test_emission_failure_degrades_to_recorded_rejection(self):
        accepted, records = self._evolve(config={"emission_garbage": True})
        self.assertEqual(accepted, [])
        for r in records:
            self.assertFalse(r["accepted"])
            self.assertEqual(r["reject_reason"], "emission_failed")
            self.assertIsNone(r["statement"])
            self.assertIsNone(r["novelty"])
        self.assertIn("zero variants accepted", self._log_text())

    def test_zero_accept_on_fundamental_flaw_never_raises(self):
        accepted, records = self._evolve(
            config={"fundamental": {"ev1": True, "ev2": True}}
        )
        self.assertEqual(accepted, [])
        for r in records:
            self.assertFalse(r["accepted"])
            self.assertTrue(r["reject_reason"].startswith("fundamental_flaw:"))
            # review reached these fields: recorded, not null
            self.assertEqual(r["novelty"], "novel")
            self.assertEqual(r["quality"], 3)
        self.assertIn("zero variants accepted", self._log_text())

    def test_judged_known_rejected_by_novelty_rule(self):
        accepted, records = self._evolve(config={"novelty": {"ev1": "known"}})
        by_id = {r["id"]: r for r in records}
        self.assertFalse(by_id["ev1"]["accepted"])
        self.assertEqual(by_id["ev1"]["reject_reason"], "judged_known")
        self.assertTrue(by_id["ev2"]["accepted"])
        self.assertEqual([a["id"] for a in accepted], ["ev2"])

    def test_initial_review_discard_recorded(self):
        accepted, records = self._evolve(
            config={"initial_verdicts": {"ev1": "discard", "ev2": "discard"}}
        )
        self.assertEqual(accepted, [])
        for r in records:
            self.assertTrue(r["reject_reason"].startswith("initial_review_discard:"))
            self.assertIsNone(r["novelty"])  # review never reached full_review

    def test_review_failure_degrades_to_recorded_rejection(self):
        def broken_gather(run_id, hypothesis):
            raise RuntimeError("openalex HTTP 500 — hard-required source down")

        accepted, records = self._evolve(gather=broken_gather)
        self.assertEqual(accepted, [])
        for r in records:
            self.assertFalse(r["accepted"])
            self.assertTrue(r["reject_reason"].startswith("review_failed:"))
            self.assertIsNotNone(r["statement"])  # emission succeeded

    def test_grounding_retrieval_best_effort_failure(self):
        rid = run_id_with_rotation("grounding_enhancement")

        def failing_openalex(query, top_k=3):
            raise RuntimeError("HTTP 429 from OpenAlex")

        accepted, records = self._evolve(run_id=rid, openalex=failing_openalex)
        self.assertEqual(records[1]["provenance"]["strategy"], "grounding_enhancement")
        self.assertTrue(records[1]["accepted"])  # retrieval failure never aborts
        log = (Path("runs") / rid / "log.txt").read_text()
        self.assertIn("grounding retrieval openalex failed", log)

    def test_survivors_json_and_parents_untouched(self):
        survivors_path = self.run_dir / "survivors.json"
        survivors_path.write_text(json.dumps(PARENTS, indent=2))
        before_bytes = survivors_path.read_bytes()
        parents_copy = copy.deepcopy(PARENTS)
        accepted, _records = self._evolve(parents=parents_copy)
        self.assertEqual(survivors_path.read_bytes(), before_bytes)
        self.assertEqual(parents_copy, PARENTS)
        self.assertEqual(len(accepted), 2)


class TestStage1PoolAssembly(TmpRunDirTest):
    run_id = "evo-stage1-test"

    POOL = [
        {
            "id": "h1",
            "statement": "Vortex core precession frequency scales with lid velocity in a cavity.",
            "rationale": "Benchmark tabulations suggest kinematic coupling.",
            "strategy": "literature_exploration",
        }
    ]
    REFLECTIONS = [
        {
            "hypothesis_id": "h1",
            "novelty": "novel",
            "critique": "solid",
            "quality": 4,
            "addressable_notes": ["carried note"],
        }
    ]
    SUMMARY = {"pool": 1, "initial_pass": 1, "fundamental_flaw_discards": 0, "reflected": 1}

    def _run_stage1(self, config=None):
        baton = Baton(
            run_id=self.run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            mode="auto",
            payload={"domain": "test domain"},
            history=[],
        )
        snapshot: dict = {}
        real_evolve = stage1_ideation.evolve_and_review

        def spying_evolve(run_id, domain, survivors_full, memory_block, run_dir):
            snapshot["survivors_bytes"] = (run_dir / "survivors.json").read_bytes()
            snapshot["survivors_ref"] = survivors_full
            snapshot["survivors_copy"] = copy.deepcopy(survivors_full)
            return real_evolve(run_id, domain, survivors_full, memory_block, run_dir)

        with patch.object(model_call, "_invoke_transport", make_fake_transport(config)), \
                patch.object(evolution_strategies, "gather_review_refs", fake_gather_review_refs), \
                patch.object(evolution_strategies, "search_openalex",
                             lambda query, top_k=3: []), \
                patch.object(stage1_ideation, "generate_candidate_pool",
                             lambda *a, **k: copy.deepcopy(self.POOL)), \
                patch.object(stage1_ideation, "reflect_on_pool",
                             lambda *a, **k: (copy.deepcopy(self.REFLECTIONS), dict(self.SUMMARY))), \
                patch.object(stage1_ideation, "journal_recent_by_kind", lambda *a, **k: []), \
                patch.object(stage1_ideation, "evolve_and_review", spying_evolve), \
                patch("model_call.time.sleep"):
            baton = stage1_ideation.run(baton)
        return baton, snapshot

    def test_accepted_variants_join_in_memory_pool_only(self):
        baton, snapshot = self._run_stage1()
        # survivors.json byte-identical before/after; survivors_full unmutated
        survivors_path = self.run_dir / "survivors.json"
        self.assertEqual(survivors_path.read_bytes(), snapshot["survivors_bytes"])
        self.assertEqual(snapshot["survivors_ref"], snapshot["survivors_copy"])
        self.assertEqual([s["id"] for s in json.loads(survivors_path.read_text())], ["h1"])
        # the delivered ranked payload is the 3-member pool, gate-1 shape
        ids = [h["id"] for h in baton.payload["hypotheses"]]
        self.assertEqual(sorted(ids), ["ev1", "ev2", "h1"])
        for h in baton.payload["hypotheses"]:
            self.assertEqual(set(h), {"id", "statement", "rationale"})
        self.assertTrue(baton.payload["hypotheses_ranked"])
        # tournament ran over the pool: its state file ranks all 3
        state = json.loads((self.run_dir / "tournament_state.json").read_text())
        self.assertEqual(
            sorted(e["id"] for e in state["final_ranking"]), ["ev1", "ev2", "h1"]
        )
        # evidence file written before the tournament, complete
        records = self._variants_file()
        self.assertEqual([r["accepted"] for r in records], [True, True])

    def test_trivial_branch_keyed_off_tournament_pool(self):
        # both variants rejected at the initial review -> pool == parents ==
        # [h1] -> k=1 trivial branch, and the run completes over parents alone
        baton, _snapshot = self._run_stage1(
            config={"initial_verdicts": {"ev1": "discard", "ev2": "discard"}}
        )
        self.assertEqual(
            [h["id"] for h in baton.payload["hypotheses"]], ["h1"]
        )
        log = self._log_text()
        self.assertIn("ranking trivial (k=1)", log)
        self.assertIn("zero variants accepted", log)
        # Step 17-E: k=1 rounds write a trivial-marker state file (so stale
        # multi-candidate state can never lie beside an empty ranking) —
        # this replaced the pre-17-E "no state file" behavior.
        state = json.loads((self.run_dir / "tournament_state.json").read_text())
        self.assertIs(state["trivial"], True)
        records = self._variants_file()
        self.assertEqual(len(records), 2)
        self.assertFalse(any(r["accepted"] for r in records))


class TestSurvivalCounter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.stage1 = Path(self._tmp.name) / "stage1"
        self.stage1.mkdir(parents=True)
        (self.stage1 / "reflection_reviews.json").write_text(
            json.dumps(
                {"initial_survivor_count": 6, "discarded_by_deep_verification": [{"id": "h9"}]}
            )
        )
        (self.stage1 / "survivors.json").write_text(
            json.dumps([{"id": f"h{i}"} for i in range(1, 5)])
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_hard_invariant_k_excludes_variants(self):
        (self.stage1 / "evolution_variants.json").write_text(
            json.dumps(
                [
                    {"id": "ev1", "accepted": True, "reject_reason": None},
                    {"id": "ev2", "accepted": False, "reject_reason": "judged_known"},
                ]
            )
        )
        result = survival_counter.count_run(self._tmp.name)
        self.assertEqual(result["status"], survival_counter.STATUS_SCORED)
        self.assertEqual(result["k"], 4)  # THE HARD INVARIANT: variants never enter k
        self.assertEqual(result["variants_emitted"], 2)
        self.assertEqual(result["variants_accepted"], 1)

    def test_absent_variants_file_is_zero_zero(self):
        result = survival_counter.count_run(self._tmp.name)
        self.assertEqual(result["status"], survival_counter.STATUS_SCORED)
        self.assertEqual(result["k"], 4)
        self.assertEqual(result["variants_emitted"], 0)
        self.assertEqual(result["variants_accepted"], 0)

    def test_run_totals_without_round_dirs_equal_canonical(self):
        # 17-CLOSE: single-pass run (no round dirs) — both semantics coincide.
        (self.stage1 / "evolution_variants.json").write_text(
            json.dumps(
                [
                    {"id": "ev1", "accepted": True, "reject_reason": None},
                    {"id": "ev2", "accepted": False, "reject_reason": "judged_known"},
                ]
            )
        )
        result = survival_counter.count_run(self._tmp.name)
        self.assertEqual(result["variants_emitted_total"], 2)
        self.assertEqual(result["variants_accepted_total"], 1)

    def test_run_totals_sum_across_round_dirs(self):
        # 17-CLOSE: with 17-E round dirs, the canonical file is the LAST
        # round's (last-round fields keep that meaning) while the *_total
        # fields sum every round — including a round that halted before
        # Evolution and so has no variants file (contributes 0).
        round1 = self.stage1 / "round1"
        round2 = self.stage1 / "round2"
        round3 = self.stage1 / "round3"
        for d in (round1, round2, round3):
            d.mkdir()
        (round1 / "evolution_variants.json").write_text(
            json.dumps(
                [
                    {"id": "ev1", "accepted": True, "reject_reason": None},
                    {"id": "ev2", "accepted": False, "reject_reason": "judged_known"},
                ]
            )
        )
        # round2 has NO evolution_variants.json (halted pre-Evolution).
        (round3 / "evolution_variants.json").write_text(
            json.dumps(
                [
                    {"id": "ev1", "accepted": True, "reject_reason": None},
                    {"id": "ev2", "accepted": True, "reject_reason": None},
                ]
            )
        )
        # Canonical file = the last successful round's copy (round3).
        (self.stage1 / "evolution_variants.json").write_text(
            (round3 / "evolution_variants.json").read_text()
        )
        result = survival_counter.count_run(self._tmp.name)
        self.assertEqual(result["variants_emitted"], 2)   # last round, unchanged
        self.assertEqual(result["variants_accepted"], 2)  # last round, unchanged
        self.assertEqual(result["variants_emitted_total"], 4)
        self.assertEqual(result["variants_accepted_total"], 3)


class TestRoundOneZeroSurvivorClassification(unittest.TestCase):
    """18-hygiene: a round-1 zero-survivor crash under the 17-E iteration
    controller leaves its reflection evidence ONLY in stage1/round1/ (no
    successful round -> no canonical stage1 files). The battery abort
    classifier read only stage1/ and logged this legitimate zero-survivor
    scientific outcome as an infra death (n=1 live,
    killrate-20260714T001356Z-same1), charging a wasteful relaunch. These
    tests reproduce the exact on-disk signature a zero-survivor raise leaves
    and assert it now scores k=0, distinct from a true infra abort."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        self.round1 = self.run_dir / "stage1" / "round1"
        self.round1.mkdir(parents=True)
        # Every zero-survivor round writes reflection_reviews.json first.
        (self.round1 / "reflection_reviews.json").write_text(
            json.dumps(
                {
                    "initial_survivor_count": 5,
                    "discarded_by_deep_verification": [{"id": f"h{i}"} for i in range(1, 5)],
                }
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_round1_all_known_at_filter_scores_zero(self):
        # filter_survivors raised AFTER reflections.json was written but
        # before survivors.json — the all_known_at_filter zero-survivor shape.
        (self.round1 / "reflections.json").write_text(json.dumps([{"id": "h5"}]))
        result = survival_counter.count_run(self.run_dir)
        self.assertEqual(result["status"], survival_counter.STATUS_SCORED)
        self.assertEqual(result["k"], 0)
        self.assertEqual(result["k_reason"], survival_counter.ALL_KNOWN_AT_FILTER)
        self.assertIsNone(result["abort_reason"])
        self.assertEqual(result["counted_from_round_dir"], "round1")
        self.assertAlmostEqual(result["deep_verify_kill_rate"], 0.8)

    def test_round1_deep_verify_discarded_all_scores_zero(self):
        # reflect_on_pool wrote reflection_reviews.json and raised immediately
        # (no reflections.json) — the deep_verify_discarded_all shape.
        result = survival_counter.count_run(self.run_dir)
        self.assertEqual(result["status"], survival_counter.STATUS_SCORED)
        self.assertEqual(result["k"], 0)
        self.assertEqual(result["k_reason"], survival_counter.DEEP_VERIFY_DISCARDED_ALL)
        self.assertIsNone(result["abort_reason"])
        self.assertEqual(result["counted_from_round_dir"], "round1")

    def test_true_infra_abort_still_aborts(self):
        # A round dir with NO reflection_reviews.json anywhere is genuine
        # infra death (retrieval/transport failure or external kill) — it must
        # still classify ABORTED so the relaunch machinery still fires.
        (self.round1 / "reflection_reviews.json").unlink()
        (self.round1 / "generation.json").write_text(json.dumps({"pool": []}))
        result = survival_counter.count_run(self.run_dir)
        self.assertEqual(result["status"], survival_counter.STATUS_ABORTED)
        self.assertIsNone(result["k"])
        self.assertIsNotNone(result["abort_reason"])
        self.assertNotIn("counted_from_round_dir", result)


class TestHandfeedFallback(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.source_dir = Path(self._tmp.name)
        stage1 = self.source_dir / "stage1"
        stage1.mkdir(parents=True)
        (stage1 / "survivors.json").write_text(
            json.dumps([{"id": "h1", "statement": "s1", "rationale": "r1"}])
        )
        (stage1 / "evolution_variants.json").write_text(
            json.dumps(
                [
                    {
                        "id": "ev1",
                        "statement": "variant statement",
                        "rationale": "variant rationale",
                        "accepted": True,
                        "reject_reason": None,
                    },
                    {
                        "id": "ev2",
                        "statement": "rejected statement",
                        "rationale": "rejected rationale",
                        "accepted": False,
                        "reject_reason": "judged_known",
                    },
                ]
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_survivor_hit_unchanged(self):
        chosen = handfeed_stage2.resolve_hypothesis(self.source_dir, "h1")
        self.assertEqual(chosen, {"id": "h1", "statement": "s1", "rationale": "r1"})

    def test_fallback_hit_on_accepted_variant(self):
        chosen = handfeed_stage2.resolve_hypothesis(self.source_dir, "ev1")
        self.assertEqual(
            chosen,
            {"id": "ev1", "statement": "variant statement", "rationale": "variant rationale"},
        )

    def test_rejected_variant_is_a_miss(self):
        with self.assertRaises(SystemExit) as ctx:
            handfeed_stage2.resolve_hypothesis(self.source_dir, "ev2")
        self.assertIn("ev2", str(ctx.exception))
        self.assertIn("accepted", str(ctx.exception))

    def test_miss_without_variants_file(self):
        (self.source_dir / "stage1" / "evolution_variants.json").unlink()
        with self.assertRaises(SystemExit) as ctx:
            handfeed_stage2.resolve_hypothesis(self.source_dir, "nope")
        self.assertIn("nope", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
