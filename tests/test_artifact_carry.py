"""test_artifact_carry.py — the carry bus: a phase hands its WORK to the next one.

Before this, a study's verified file producers reached exactly one consumer
(call_integration). Every other dispatch — run_experiment, spawn_sub_investigation
— got only the director's prose, so each move rebuilt the world from a sentence
and nothing compounded across phases.

Proves, entirely offline (no model calls, no subprocess runs, no Docker):
  - a question is byte-identical when the study has carried nothing (a first move
    in a fresh study is untouched);
  - a run_experiment move receives the producers of files earlier moves produced;
  - a spawned child receives them BOTH ways — inlined in its goal and seeded on its
    study — so its own first move carries them too;
  - a file this study regenerated supersedes the version it inherited (the newest
    version of a design is the one that carries — what iteration needs);
  - the carry is bounded, so a long arc cannot grow a question without limit;
  - producers travel, never bytes.

Run directly: venv/bin/python3 tests/test_artifact_carry.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent import free_director as FD  # noqa: E402
from pi_agent.capabilities import _default_spawn_investigate  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402


def _producer(name: str, value: float = 1.0) -> dict:
    """A reusable file artifact as the experimenter declares it: a re-runnable
    producer that RE-EMITS the file, never the file's bytes."""
    return {
        "name": name,
        "producer": {
            "kind": "code",
            "code": f"open({name!r}, 'w').write('x')\nmetrics['q'] = {value}",
            "quantity": "q",
            "emits": [name],
        },
    }


def _record(study, *, artifacts=(), results=(), run_id="r1") -> None:
    """Append one arc entry carrying reusable artifacts and/or findings."""
    S.record_move(
        study,
        MoveResult(
            move_type="single",
            run_id=run_id,
            succeeded=True,
            outcome="completed",
            raw={"findings": list(results), "reusable_artifacts": list(artifacts),
                 "publishable": True},
        ),
        finding="a move happened",
    )


class CarryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _study(self, goal="the goal", **kw):
        return S.create_study(goal, studies_root=self.root, **kw)


# --------------------------------------------------------------------------
# The question a dispatched move actually receives.
# --------------------------------------------------------------------------

class TestCarryDomain(CarryTestCase):
    def test_empty_study_leaves_the_question_byte_identical(self):
        """Nothing carried => the director's question, verbatim. A fresh study's
        first move must be unchanged from before the carry bus existed."""
        study = self._study()
        self.assertEqual(FD._carry_domain("does X hold?", study), "does X hold?")

    def test_carries_producers_of_files_earlier_moves_produced(self):
        study = self._study()
        _record(study, artifacts=[_producer("arm.json")])
        out = FD._carry_domain("now design the gripper", study)
        self.assertTrue(out.startswith("now design the gripper"))
        self.assertIn("arm.json", out)
        # The PRODUCER travels, so the receiver can regenerate the file.
        self.assertIn("metrics['q']", out)
        self.assertIn("re-runnable producer", out)

    def test_instructs_regeneration_never_a_stored_copy(self):
        """The one contract that keeps a carried file reproducible at every hop."""
        study = self._study()
        _record(study, artifacts=[_producer("arm.json")])
        out = FD._carry_domain("build on it", study)
        self.assertIn("never assume a stored copy", out)

    def test_carry_is_bounded(self):
        study = self._study()
        _record(study, artifacts=[_producer(f"f{i}.json") for i in range(20)])
        out = FD._carry_domain("q", study)
        carried = json.loads(out[out.index("[{"):out.rindex("]") + 1])
        self.assertEqual(len(carried), FD.MAX_CARRIED_FILES)

    def test_a_regenerated_file_supersedes_the_inherited_version(self):
        """Iteration needs the NEWEST version of a design to be the one that
        carries: this study's own arm.json wins over the one it inherited."""
        study = self._study(inherited_artifacts=[_producer("arm.json", 1.0)])
        _record(study, artifacts=[_producer("arm.json", 2.0)])
        files = FD._integration_context(study)["files"]
        self.assertEqual([f["name"] for f in files], ["arm.json"])
        self.assertIn("2.0", files[0]["producer"]["code"])


# --------------------------------------------------------------------------
# run_experiment — the dispatched Move carries.
# --------------------------------------------------------------------------

class TestRunExperimentCarries(CarryTestCase):
    def test_move_domain_carries_prior_artifacts(self):
        study = self._study()
        _record(study, artifacts=[_producer("arm.json")])
        move = FD._move_from_action(
            {"action": "run_experiment", "domain": "optimize the gripper"}, study)
        self.assertTrue(move.domain.startswith("optimize the gripper"))
        self.assertIn("arm.json", move.domain)

    def test_move_domain_untouched_when_nothing_carried(self):
        study = self._study()
        move = FD._move_from_action(
            {"action": "run_experiment", "domain": "optimize the gripper"}, study)
        self.assertEqual(move.domain, "optimize the gripper")


# --------------------------------------------------------------------------
# spawn_sub_investigation — the child inherits, both ways.
# --------------------------------------------------------------------------

class TestSpawnHandsDown(CarryTestCase):
    def _spawn(self, parent, domain="optimize the gripper"):
        """Run the real spawn handler with free_investigate faked, and capture
        exactly what the child was handed."""
        seen = {}

        def fake_investigate(goal, **kw):
            seen["goal"] = goal
            seen["inherited"] = kw.get("inherited_artifacts")
            child = S.create_study(
                goal, studies_root=kw["studies_root"], study_id=kw["study_id"],
                parent_study_id=kw["parent_study_id"],
                inherited_artifacts=kw.get("inherited_artifacts"))
            seen["child"] = child
            return {"study_id": child.study_id, "arc": [], "moves_run": 0,
                    "termination": {"reason": "done"}}

        import pi_agent.free_director as fd
        original = fd.free_investigate
        fd.free_investigate = fake_investigate
        try:
            _default_spawn_investigate(
                domain, S.Budget(1) if hasattr(S, "Budget") else _FakeBudget(),
                f"{parent.study_id}-sub1", parent)
        finally:
            fd.free_investigate = original
        return seen

    def test_child_goal_inlines_the_parents_producers(self):
        parent = self._study()
        _record(parent, artifacts=[_producer("arm.json")])
        seen = self._spawn(parent)
        self.assertTrue(seen["goal"].startswith("optimize the gripper"))
        self.assertIn("arm.json", seen["goal"])

    def test_child_study_is_seeded_so_its_own_moves_carry(self):
        """The goal alone is not enough — the child's LATER moves author fresh
        questions. Seeding the study is what makes them carry too."""
        parent = self._study()
        _record(parent, artifacts=[_producer("arm.json")])
        seen = self._spawn(parent)
        self.assertEqual([a["name"] for a in seen["inherited"]], ["arm.json"])
        child = seen["child"]
        # The child's arc is EMPTY, and it still carries — from inheritance alone.
        self.assertEqual(S.study_findings(child), [])
        self.assertIn("arm.json", FD._carry_domain("its own next question", child))

    def test_inheritance_survives_a_reload(self):
        """A child study reloaded from disk keeps what it inherited."""
        parent = self._study()
        _record(parent, artifacts=[_producer("arm.json")])
        seen = self._spawn(parent)
        reloaded = S.load_study(seen["child"].study_id, studies_root=self.root)
        self.assertEqual([a["name"] for a in reloaded.inherited_artifacts],
                         ["arm.json"])

    def test_nothing_to_hand_down_leaves_the_child_goal_verbatim(self):
        parent = self._study()
        seen = self._spawn(parent)
        self.assertEqual(seen["goal"], "optimize the gripper")
        self.assertEqual(seen["inherited"], [])


class _FakeBudget:
    """Minimal stand-in — the spawn handler only passes it through to the child."""


# --------------------------------------------------------------------------
# The measurement boundary is untouched by any of this.
# --------------------------------------------------------------------------

class TestBoundaryHolds(CarryTestCase):
    def test_only_producers_travel_never_stored_bytes_or_narration(self):
        study = self._study()
        _record(
            study,
            artifacts=[_producer("arm.json")],
            results=[{"label": "reach", "value": 0.42, "verified": True},
                     {"label": "guess", "value": 9.9, "verified": False}],
        )
        out = FD._carry_domain("next", study)
        carried = json.loads(out[out.index("[{"):out.rindex("]") + 1])
        # Every carried item is a name + a producer recipe. Nothing else rides.
        for item in carried:
            self.assertEqual(set(item), {"name", "producer"})
        # An unverified finding never becomes a carried claim.
        self.assertNotIn("9.9", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
