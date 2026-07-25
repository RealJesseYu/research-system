"""test_capabilities.py — the free director's optional tools (Phase 3).

Proves each executor OFFLINE (inner machinery faked): ideation returns a hypothesis
digest, data-analysis and validation return advisory results, each spends exactly
one move, an unaffordable call spends nothing, the not-yet-wired actions are honest,
and validation NEVER sets verified/publishable (the wall stays authoritative).

Run directly: venv/bin/python3 tests/test_capabilities.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.capabilities as C  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.study import create_study  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = create_study("goal", study_id="s", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()


class TestIdeation(_Base):
    def test_returns_hypothesis_digest_and_spends_one_move(self):
        def fake_run(domain, study, seq):
            return [{"id": "h1", "statement": "A"}, {"id": "h2", "statement": "B"}]
        b = Budget(5)
        r = C.run_ideation({"action": "call_ideation", "domain": "q"}, self.study, b, 1, run=fake_run)
        self.assertTrue(r["succeeded"])
        self.assertEqual(r["outcome"], "ideation_done")
        self.assertEqual([h["id"] for h in r["hypotheses"]], ["h1", "h2"])
        self.assertEqual(b.remaining(), 4)  # spent one

    def test_empty_ideation_is_honest(self):
        r = C.run_ideation({"action": "call_ideation", "domain": "q"}, self.study,
                           Budget(2), 1, run=lambda *a: [])
        self.assertFalse(r["succeeded"])
        self.assertEqual(r["outcome"], "ideation_empty")

    def test_no_budget_means_no_spend_and_no_call(self):
        called = {"n": 0}

        def fake_run(*a):
            called["n"] += 1
            return [{"id": "h1", "statement": "A"}]
        b = Budget(0)
        r = C.run_ideation({"action": "call_ideation", "domain": "q"}, self.study, b, 1, run=fake_run)
        self.assertEqual(r["outcome"], "call_ideation_insufficient_budget")
        self.assertEqual(called["n"], 0)   # never invoked the machinery
        self.assertEqual(b.remaining(), 0)


class TestDataAnalysis(_Base):
    def test_advisory_result_and_one_move(self):
        def fake_call(stage, prompt, inp, schema, **kw):
            # the door returns (data, timing)
            return {"analysis": "results trend up", "directions": ["test Y"]}, {}
        b = Budget(3)
        r = C.run_data_analysis({"action": "call_data_analysis", "detail": "analyze"},
                                self.study, b, 1, call=fake_call)
        self.assertEqual(r["outcome"], "data_analysis_done")
        self.assertEqual(r["directions"], ["test Y"])
        self.assertEqual(b.remaining(), 2)

    def test_validator_rejects_empty_analysis(self):
        self.assertTrue(C._analysis_validator({"analysis": "  ", "directions": []}))
        self.assertEqual(C._analysis_validator({"analysis": "ok", "directions": ["a"]}), [])


class TestValidation(_Base):
    def test_advisory_and_never_sets_verified(self):
        def fake_call(stage, prompt, inp, schema, **kw):
            return {"assessment": "finding 2 looks shaky", "concerns": ["c1"], "recheck": ["f2"]}, {}
        b = Budget(3)
        r = C.run_validation({"action": "call_validation", "detail": "scrutinize"},
                             self.study, b, 1, call=fake_call)
        self.assertEqual(r["outcome"], "validation_done")
        self.assertEqual(r["concerns"], ["c1"])
        self.assertEqual(b.remaining(), 2)
        # the boundary: a validation result carries NO verified/publishable verdict.
        self.assertNotIn("verified", r)
        self.assertNotIn("publishable", r)

    def test_prompt_forbids_setting_a_verdict(self):
        # the split is load-bearing enough to assert in the prompt text.
        self.assertIn("NEVER declare a finding verified", C.VALIDATION_PROMPT)


class TestSpawn(_Base):
    def _child_report(self, **over):
        base = {
            "study_id": "s-sub1",
            "moves_run": 1,
            "termination": {"reason": "director_judged_complete"},
            "arc": [{"move_type": "single", "results": [
                {"label": "k", "value": 2.0, "verified": True},
                {"label": "shaky", "value": 9.0, "verified": False},
            ]}],
        }
        base.update(over)
        return base

    def test_allocates_a_child_slice_and_bubbles_verified_findings(self):
        seen = {}

        def fake_investigate(domain, child_budget, child_id, parent_study):
            seen["domain"] = domain
            seen["child_remaining"] = child_budget.remaining()
            seen["child_depth"] = child_budget.depth
            seen["child_id"] = child_id
            return self._child_report()
        b = Budget(6)
        r = C.run_spawn({"action": "spawn_sub_investigation", "domain": "sub q",
                         "budget_moves": 4}, self.study, b, 1, investigate=fake_investigate)
        self.assertTrue(r["succeeded"])
        self.assertEqual(r["outcome"], "sub_investigation_done")
        # 4 moves left the parent and became the child's whole pool at depth+1.
        self.assertEqual(b.remaining(), 2)
        self.assertEqual(seen["child_remaining"], 4)
        self.assertEqual(seen["child_depth"], 1)
        self.assertEqual(seen["child_id"], "s-sub1")
        # only the VERIFIED finding counts as standing; both are surfaced.
        self.assertEqual(len(r["findings"]), 2)
        self.assertEqual([f["verified"] for f in r["findings"]], [True, False])

    def test_reproduced_reusable_files_bubble_up_from_the_child(self):
        prod = {"kind": "code", "code": "c", "quantity": "n", "emits": ["seq.fasta"]}
        report = self._child_report(arc=[{
            "move_type": "single",
            "results": [{"label": "k", "value": 2.0, "verified": True}],
            "reusable_artifacts": [{"name": "seq.fasta", "producer": prod}],
        }])
        r = C.run_spawn(
            {"action": "spawn_sub_investigation", "domain": "q", "budget_moves": 2},
            self.study, Budget(5), 1, investigate=lambda *a: report)
        self.assertEqual(len(r["reusable_artifacts"]), 1)
        self.assertEqual(r["reusable_artifacts"][0]["name"], "seq.fasta")
        self.assertEqual(r["reusable_artifacts"][0]["producer"], prod)

    def test_barren_child_is_honest(self):
        r = C.run_spawn(
            {"action": "spawn_sub_investigation", "domain": "q", "budget_moves": 2},
            self.study, Budget(5), 1,
            investigate=lambda *a: self._child_report(arc=[]),
        )
        self.assertFalse(r["succeeded"])
        self.assertEqual(r["outcome"], "sub_investigation_barren")

    def test_insufficient_budget_does_not_allocate(self):
        called = {"n": 0}

        def fake(*a):
            called["n"] += 1
            return self._child_report()
        b = Budget(2)
        r = C.run_spawn({"action": "spawn_sub_investigation", "domain": "q",
                         "budget_moves": 5}, self.study, b, 1, investigate=fake)
        self.assertEqual(r["outcome"], "spawn_insufficient_budget")
        self.assertEqual(called["n"], 0)   # no child ran
        self.assertEqual(b.remaining(), 2)  # nothing allocated

    def test_depth_cap_is_reported_distinctly(self):
        from pi_agent.budget import MAX_DEPTH
        b = Budget(10, depth=MAX_DEPTH)
        r = C.run_spawn({"action": "spawn_sub_investigation", "domain": "q",
                         "budget_moves": 1}, self.study, b, 1, investigate=lambda *a: {})
        self.assertEqual(r["outcome"], "spawn_depth_cap")
        self.assertEqual(b.remaining(), 10)  # untouched


class TestReadMemory(_Base):
    def test_reads_recent_learned_summaries_and_spends_nothing(self):
        b = Budget(3)
        r = C.run_read_memory(
            {"action": "read_memory"}, self.study, b, 1,
            read=lambda: [{"text": "prior lesson", "run_id": "r1"}],
        )
        self.assertEqual(r["outcome"], "memory_read")
        self.assertEqual(r["memory"][0]["text"], "prior lesson")
        self.assertEqual(b.remaining(), 3)  # a read costs no move

    def test_empty_memory_is_honest(self):
        r = C.run_read_memory({"action": "read_memory"}, self.study, Budget(1), 1, read=lambda: [])
        self.assertEqual(r["outcome"], "memory_empty")


class TestWriteMemory(_Base):
    def test_writes_a_director_note_and_spends_nothing(self):
        captured = {}

        def fake_write(study, note):
            captured["study"] = study.study_id
            captured["note"] = note
        b = Budget(3)
        r = C.run_write_memory(
            {"action": "write_memory", "detail": "prefer cheap probes first"},
            self.study, b, 1, write=fake_write,
        )
        self.assertEqual(r["outcome"], "memory_written")
        self.assertEqual(captured["note"], "prefer cheap probes first")
        self.assertEqual(b.remaining(), 3)  # a write costs no move

    def test_empty_note_is_honest(self):
        r = C.run_write_memory({"action": "write_memory", "detail": "  "},
                               self.study, Budget(1), 1, write=lambda *a: None)
        self.assertEqual(r["outcome"], "memory_write_empty")

    def test_default_write_targets_director_note_never_learned_summary(self):
        import memory.journal as J
        captured = {}
        orig = J.journal_append
        try:
            J.journal_append = lambda entry: captured.update(entry) or entry
            C._default_write_memory(self.study, "a lesson")
        finally:
            J.journal_append = orig
        self.assertEqual(captured["kind"], "director_note")   # R-FD-5
        self.assertNotEqual(captured["kind"], "learned_summary")

    def test_default_read_merges_both_memory_kinds(self):
        import memory.journal as J
        orig = J.journal_recent_by_kind
        try:
            J.journal_recent_by_kind = lambda kind, n: [{"text": kind, "run_id": "x"}]
            merged = C._default_read_memory()
        finally:
            J.journal_recent_by_kind = orig
        kinds = [m["text"] for m in merged]
        self.assertIn("learned_summary", kinds)
        self.assertIn("director_note", kinds)


class TestRegistry(_Base):
    def test_not_yet_wired_is_honest_if_ever_used(self):
        # nothing maps to it now (every action is wired), but the safety net stays.
        r = C._not_yet_wired({"action": "future_thing"}, self.study, Budget(4), 1)
        self.assertFalse(r["succeeded"])
        self.assertEqual(r["outcome"], "future_thing_not_yet_wired")

    def test_unknown_action_is_honest_not_a_crash(self):
        r = C.execute("call_teleport", {"action": "call_teleport"}, self.study, Budget(2), 1)
        self.assertEqual(r["outcome"], "call_teleport_unknown")

    def test_execute_routes_a_wired_tool(self):
        # route call_ideation through execute (its default live seam would call the
        # stage; here we only prove routing reaches run_ideation, which guards on
        # budget=0 before any machinery runs).
        r = C.execute("call_ideation", {"action": "call_ideation", "domain": "q"},
                      self.study, Budget(0), 1)
        self.assertEqual(r["outcome"], "call_ideation_insufficient_budget")


if __name__ == "__main__":
    unittest.main()
