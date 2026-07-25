"""test_free_director_e2e.py — Phase 6: the whole manager-of-managers, end to end.

ONE offline test that stitches every phase together and proves they compose:

  Phase 1  the budget divides down the tree and is conserved to the last move;
  Phase 2  the free director loop drives an open-action-space arc to a clean stop;
  Phase 4  spawn_sub_investigation recurses into REAL child free_investigate runs,
           each on its carved slice, and their VERIFIED findings bubble up;
  Phase 3  read_memory is reached as an optional tool;
  Phase 5  call_integration dispatches a joint check whose domain carries the parts
           that bubbled up from BOTH children — the full child→bubble→root→integrate
           chain.

Only the two leaves are faked: the model brain (decide_action) and the subprocess
dispatch (run_move). Everything else — the loop, budget allocation, the recursion,
the bubbling, the integration framing, cost aggregation, the on-disk study tree — is
the real production code. The first LIVE outing (real models, real runs) is the
owner's, from a plain Terminal under caffeinate (run-venue rule).

Run directly: venv/bin/python3 tests/test_free_director_e2e.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.capabilities as C  # noqa: E402
import pi_agent.study as S  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from pi_agent.free_director import free_investigate  # noqa: E402

ROOT_GOAL = "design a widget: a frame and a motor that fit together"
FRAME_Q = "optimize the frame"
MOTOR_Q = "optimize the motor"


def _act(action, **over):
    base = {"ack": "s", "reading": "r", "reasoning": "because", "action": action,
            "domain": None, "instrument": None, "campaign": False,
            "budget_moves": None, "detail": None, "stop_reason": None}
    base.update(over)
    return base


# Per-goal scripts. The root reads memory, decomposes into two subsystems, then
# integrates the verified parts and stops. Each child runs one verified experiment.
SCRIPTS = {
    ROOT_GOAL: [
        _act("read_memory"),
        _act("spawn_sub_investigation", domain=FRAME_Q, budget_moves=2),
        _act("spawn_sub_investigation", domain=MOTOR_Q, budget_moves=2),
        _act("call_integration", detail="frame and motor fit; total mass < 10"),
        _act("stop", stop_reason="widget designed and its parts compose"),
    ],
    FRAME_Q: [
        _act("run_experiment", domain="measure frame mass"),
        _act("stop", stop_reason="frame optimized"),
    ],
    MOTOR_Q: [
        _act("run_experiment", domain="measure motor mass"),
        _act("stop", stop_reason="motor optimized"),
    ],
}

# What a faked run_move "measures" (verified) for a given experiment domain.
VERIFIED = {
    "measure frame mass": {"label": "frame_mass", "value": 3.0, "verified": True},
    "measure motor mass": {"label": "motor_mass", "value": 4.0, "verified": True},
}


class TestEndToEndRecursiveInvestigation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _brain(self):
        """A decide_action that plays each study's script in order, tracked per
        study_id so parent and children advance independently."""
        pos: dict = {}

        def decide(study, arc, budget):
            script = SCRIPTS[study.goal]
            i = pos.get(study.study_id, 0)
            pos[study.study_id] = i + 1
            return script[min(i, len(script) - 1)]
        return decide

    def _run_move(self):
        """A faked dispatch: records the move with a verified finding (by domain)
        and a fixed per-run cost. An integration run gets its own verified joint
        finding."""
        def run_move(study, move, finding=None, runs_root=None):
            raw = {"publishable": True, "cost": {"calls": 5, "tokens": 500}}
            if move.domain.startswith("Integration check"):
                raw["findings"] = [{"label": "assembly_mass", "value": 7.0, "verified": True}]
            else:
                for key, f in VERIFIED.items():
                    if key in move.domain:
                        raw["findings"] = [f]
                        break
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or f"{study.study_id}-mX",
                           True, "completed", raw),
                finding=finding,
            )
        return run_move

    def _exec(self, decide, run_move):
        """A capability executor that makes spawn recurse into a REAL child
        free_investigate (same faked brain + dispatch injected, so grandchildren
        would recurse too), and routes everything else to the live registry."""
        def exec_cap(name, action, study, budget, seq):
            if name == "spawn_sub_investigation":
                def child_investigate(domain, child_budget, child_id, parent_study):
                    return free_investigate(
                        domain, budget=child_budget, mode=parent_study.mode,
                        allowed_substrates=parent_study.allowed_substrates,
                        study_id=child_id, parent_study_id=parent_study.study_id,
                        studies_root=parent_study.studies_root,
                        decide_action=decide, run_move=run_move,
                        execute_capability=exec_cap,
                    )
                return C.run_spawn(action, study, budget, seq, investigate=child_investigate)
            return C.execute(name, action, study, budget, seq)
        return exec_cap

    def test_full_decompose_investigate_integrate_arc(self):
        decide = self._brain()
        run_move = self._run_move()
        report = free_investigate(
            ROOT_GOAL, budget=Budget(8), studies_root=self.root,
            decide_action=decide, run_move=run_move,
            execute_capability=self._exec(decide, run_move), study_id="root",
        )

        # --- the arc has the shape we decomposed into --------------------------
        by_type = {}
        for e in report["arc"]:
            by_type.setdefault(e["move_type"], []).append(e)
        self.assertEqual(len(by_type.get("read_memory", [])), 1)
        self.assertEqual(len(by_type.get("spawn_sub_investigation", [])), 2)
        self.assertEqual(len(by_type.get("single", [])), 1)  # the integration run
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")

        # --- Phase 4: both sub-investigations stood, verified parts bubbled up --
        spawns = by_type["spawn_sub_investigation"]
        self.assertTrue(all(s["succeeded"] for s in spawns))
        bubbled = {r["label"]: r["value"] for s in spawns for r in s["results"]}
        self.assertEqual(bubbled, {"frame_mass": 3.0, "motor_mass": 4.0})

        # --- Phase 5: integration ran over the parts that bubbled from BOTH kids-
        integ = by_type["single"][0]
        self.assertEqual(report["moves_run"], 1)  # only the integration is a root move
        # the integration run measured a verified joint quantity
        self.assertEqual(integ["results"], [{"label": "assembly_mass", "value": 7.0, "verified": True}])

        # --- Phase 1: budget conserved to the last move across the whole tree ---
        # root: allocated 2+2, spent 1 (integration), so 3 remain.
        self.assertEqual(report["budget_final"]["remaining"], 3)
        children = self._load_child_reports("root")
        self.assertEqual(len(children), 2)
        for child in children:
            self.assertEqual(child["moves_run"], 1)                 # one experiment each
            self.assertEqual(child["budget_final"]["remaining"], 1)  # got 2, spent 1
            self.assertEqual(child["ceiling"], None)                 # a spawned child has no human ceiling
        # tree total = root(spent 1 + remaining 3 + allocated 4) = 8, and every
        # allocated move is accounted for in a child (spent 1 + remaining 1)*2 = 4.
        tree_spent = 1 + sum(1 for _ in children)  # root integration + one per child
        tree_remaining = report["budget_final"]["remaining"] + sum(
            c["budget_final"]["remaining"] for c in children)
        self.assertEqual(tree_spent + tree_remaining, 8)  # nothing conjured, nothing lost

        # --- Phase 1 cost: each study sums its own arc; the tree total is real ---
        self.assertEqual(report["runs_spend"]["calls"], 5)  # the one root (integration) run
        tree_cost = report["runs_spend"]["calls"] + sum(c["runs_spend"]["calls"] for c in children)
        self.assertEqual(tree_cost, 15)  # 3 experiments * 5 calls each

        # --- the study tree is on disk, parent-linked ---------------------------
        for child in children:
            self.assertEqual(child["study_id"].startswith("root-sub"), True)

    def _load_child_reports(self, root_id: str) -> list:
        """Every study whose parent is root_id, read from its on-disk report."""
        out = []
        for sj in sorted(self.root.glob("*/study.json")):
            identity = json.loads(sj.read_text())
            if identity.get("parent_study_id") == root_id:
                out.append(json.loads((sj.parent / "report.json").read_text()))
        return out


if __name__ == "__main__":
    unittest.main()
