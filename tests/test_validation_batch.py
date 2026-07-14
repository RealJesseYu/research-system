"""
test_validation_batch.py — VALIDATION-18 single-pass survival batch driver.

All offline: fixture killrate reports + fixture source run dirs on a tmp
tree, and fake stage runners / lint (zero model calls, zero solver, zero
network). Proves selection (both the baton-snapshot path and the
exception-slot tournament_state fallback), exception-flag propagation,
source.json shape, that a non-exit decision stops the chain before stage 6,
that an exit decision invokes stage 6 + lint, the report/summary shape, and
that one chain crashing does not stop the batch.

Run directly: venv/bin/python3 tests/test_validation_batch.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import validation_batch as vb

_NOOP_VALIDATORS = {
    "post_stage2": lambda p: [],
    "post_stage3": lambda p: [],
    "post_stage4": lambda p: [],
    "post_stage5": lambda p: [],
}


def _hyp(hid: str) -> dict:
    return {"id": hid, "statement": f"statement of {hid}", "rationale": f"rationale of {hid}"}


def _write_baton_slot(runs_root: Path, run_id: str, domain: str, ranked_ids: list[str]) -> None:
    d = runs_root / run_id
    d.mkdir(parents=True)
    payload = {
        "domain": domain,
        "hypotheses": [_hyp(i) for i in ranked_ids],
        "hypotheses_ranked": True,
    }
    (d / "baton_after_stage_1.json").write_text(json.dumps({"payload": payload}))


def _write_fallback_slot(runs_root: Path, run_id: str, ranked_ids: list[str]) -> None:
    """A run dir WITHOUT baton_after_stage_1.json (exception attempt): only
    stage1/tournament_state.json + survivors.json survive."""
    s1 = runs_root / run_id / "stage1"
    s1.mkdir(parents=True)
    (s1 / "tournament_state.json").write_text(
        json.dumps({"final_ranking": [{"id": i, "elo": 1200.0 - n} for n, i in enumerate(ranked_ids)]})
    )
    # survivors.json is a DIFFERENT (unranked) order and includes extra keys.
    (s1 / "survivors.json").write_text(
        json.dumps([dict(_hyp(i), novelty="x", critique="y", quality=3) for i in reversed(ranked_ids)])
    )


def _report(arm_domains: dict, slots: list[dict]) -> dict:
    return {"domains": arm_domains, "slots": slots}


def _slot(name: str, domain_key: str, run_id: str, resolved: bool,
          exception=None, rounds_completed=1) -> dict:
    return {
        "slot": name,
        "domain_key": domain_key,
        "resolved": resolved,
        "attempts": [{"run_id": run_id, "exception": exception, "rounds_completed": rounds_completed}],
    }


class SelectionTests(unittest.TestCase):
    def _build(self, tmp: Path):
        runs = tmp / "runs"
        runs.mkdir()
        _write_baton_slot(runs, "run-same1", "same domain", ["h5", "h6", "h1"])
        _write_fallback_slot(runs, "run-alt1-exc", ["h10", "h4", "ev1"])
        report_path = tmp / "killrate_18_T1b.json"
        report = _report(
            {"same": "same domain", "alt": "alt domain"},
            [
                _slot("same1", "same", "run-same1", True, rounds_completed=2),
                _slot("alt1", "alt", "run-alt1-exc", True, exception="Exception: boom"),
                _slot("same2", "same", "run-missing", False),  # unresolved → skipped
            ],
        )
        report_path.write_text(json.dumps(report))
        return runs, [("T1", report_path)]

    def test_primary_and_fallback_selection(self):
        with tempfile.TemporaryDirectory() as td:
            runs, reports = self._build(Path(td))
            sels = vb.gather_selections(reports, runs)
            self.assertEqual(len(sels), 2)  # unresolved slot skipped
            same1, alt1 = sels
            # primary path: rank-1 is hypotheses[0]
            self.assertEqual(same1["hyp_id"], "h5")
            self.assertEqual(same1["domain"], "same domain")
            self.assertEqual(same1["selection_source"], "baton_after_stage_1.json")
            self.assertFalse(same1["exception_flag"])
            self.assertEqual(same1["rounds_completed"], 2)
            # fallback path: rank-1 from tournament_state.json, resolved via survivors
            self.assertEqual(alt1["hyp_id"], "h10")
            self.assertEqual(alt1["chosen_hypothesis"]["statement"], "statement of h10")
            self.assertEqual(alt1["domain"], "alt domain")  # from report, snapshot absent
            self.assertIn("tournament_state", alt1["selection_source"])
            self.assertTrue(alt1["exception_flag"])


def _fake_stage(key: str, value):
    def _run(baton):
        p = dict(baton.payload)
        p[key] = value
        baton.payload = p
        return baton
    return _run


def _stages_with_decision(decision: str, stage6_calls: list):
    def stage6(baton):
        stage6_calls.append(baton.run_id)
        return baton
    return {
        "stage2": _fake_stage("experiment_spec", {"hypothesis_id": "h5"}),
        "stage3": _fake_stage("fidelity_verdict", {"label": "defer", "rationale": "r", "right_instrument": "i"}),
        "stage4": _fake_stage("execution_results", {"status": "skipped_defer"}),
        "stage5": lambda b: _set_thought(b, decision),
        "stage6": stage6,
    }


def _set_thought(baton, decision: str):
    p = dict(baton.payload)
    p["thought"] = {"surprise_triage": "none", "iterate_decision": decision}
    p["iterate_decision"] = decision
    baton.payload = p
    return baton


def _selection(arm="T1", slot="same1", hid="h5", exc=None) -> dict:
    return {
        "arm": arm, "slot": slot, "source_run_id": "run-x", "rank": 1, "hyp_id": hid,
        "chosen_hypothesis": _hyp(hid), "domain": "some domain", "exception": exc,
        "exception_flag": exc is not None, "rounds_completed": 1,
        "selection_source": "baton_after_stage_1.json",
    }


class ChainTests(unittest.TestCase):
    def test_source_json_shape(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / "runs"
            calls = []
            sel = _selection(exc="Exception: boom")
            vb.run_one(sel, stages=_stages_with_decision("exit", calls),
                       validators=_NOOP_VALIDATORS, lint_fn=lambda rid: [], runs_root=runs)
            src = json.loads((runs / vb.run_id_for(sel) / "source.json").read_text())
            self.assertEqual(
                set(src),
                {"report", "arm", "slot", "source_run_id", "rank", "hyp_id",
                 "exception_flag", "source_exception", "rounds_completed", "selection_source"},
            )
            self.assertEqual(src["report"], "killrate_18_T1b.json")
            self.assertTrue(src["exception_flag"])
            self.assertEqual(src["source_exception"], "Exception: boom")

    def test_non_exit_stops_chain(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / "runs"
            calls = []
            res = vb.run_one(_selection(), stages=_stages_with_decision("back_to_design", calls),
                             validators=_NOOP_VALIDATORS, lint_fn=lambda rid: [], runs_root=runs)
            self.assertEqual(calls, [])                    # stage 6 never called
            self.assertFalse(res["survived"])
            self.assertEqual(res["stage5_decision"], "back_to_design")
            self.assertIsNone(res["lint"])
            self.assertFalse(res["paper_written"])
            self.assertEqual(res["status"], "completed")

    def test_exit_invokes_stage6_and_lint(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / "runs"
            calls = []
            lint_seen = []
            res = vb.run_one(_selection(), stages=_stages_with_decision("exit", calls),
                             validators=_NOOP_VALIDATORS,
                             lint_fn=lambda rid: lint_seen.append(rid) or [], runs_root=runs)
            self.assertEqual(calls, [vb.run_id_for(_selection())])   # stage 6 called
            self.assertEqual(lint_seen, [vb.run_id_for(_selection())])
            self.assertTrue(res["survived"])
            self.assertTrue(res["paper_written"])
            self.assertEqual(res["lint"], "PASS")

    def test_exit_lint_fail_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / "runs"
            res = vb.run_one(_selection(), stages=_stages_with_decision("exit", []),
                             validators=_NOOP_VALIDATORS,
                             lint_fn=lambda rid: [{"code": "x", "target": "sidecar", "message": "m"}],
                             runs_root=runs)
            self.assertEqual(res["lint"], "FAIL")
            self.assertEqual(len(res["lint_failures"]), 1)

    def test_one_chain_crash_continues(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / "runs"
            boom = dict(_stages_with_decision("exit", []))
            def _explode(baton):
                raise RuntimeError("stage2 boom")
            boom["stage2"] = _explode
            crashed = vb.run_one(_selection(slot="same1"), stages=boom,
                                 validators=_NOOP_VALIDATORS, lint_fn=lambda rid: [], runs_root=runs)
            ok = vb.run_one(_selection(slot="same2", hid="h6"),
                            stages=_stages_with_decision("exit", []),
                            validators=_NOOP_VALIDATORS, lint_fn=lambda rid: [], runs_root=runs)
            self.assertEqual(crashed["status"], "crashed")
            self.assertIn("stage2 boom", crashed["error"])
            self.assertEqual(ok["status"], "completed")
            # crash evidence written, batch could proceed
            self.assertTrue((runs / crashed["run_id"] / "crash.txt").is_file())
            self.assertTrue((runs / crashed["run_id"] / "result.json").is_file())


class ReportShapeTests(unittest.TestCase):
    def test_summary_survival_and_breakdown(self):
        results = [
            {"arm": "T1", "status": "completed", "survived": True, "stage5_decision": "exit"},
            {"arm": "T1", "status": "completed", "survived": False, "stage5_decision": "back_to_design"},
            {"arm": "T1", "status": "crashed", "survived": False, "stage5_decision": None},
            {"arm": "T2", "status": "completed", "survived": True, "stage5_decision": "exit"},
        ]
        per_arm = vb.summarize(results)
        self.assertEqual(per_arm["T1"]["n"], 3)
        self.assertEqual(per_arm["T1"]["survived"], 1)
        self.assertEqual(per_arm["T1"]["crashed"], 1)
        self.assertAlmostEqual(per_arm["T1"]["survival_fraction"], 1 / 3)
        self.assertEqual(per_arm["T1"]["decision_breakdown"],
                         {"exit": 1, "back_to_design": 1, "crashed": 1})
        self.assertEqual(per_arm["T2"]["survival_fraction"], 1.0)


if __name__ == "__main__":
    unittest.main()
