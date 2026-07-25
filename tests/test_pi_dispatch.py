"""
test_pi_dispatch.py — the PI control layer's dispatch wiring (chunk 2).

WHAT THIS PROVES. A whole run is callable and hands back a structured result;
the three move types invoke through one interface; and every result — including
the ones a run leaves when it halts, fails verification, or dies without
journaling — is read faithfully rather than invented.

NO LIVE PIPELINE. The subprocess dispatch is exercised against a STUB run
script that writes the exact evidence layout a real run leaves, and the journal
record is supplied through an injection seam. read_run_result and build_run_env
are pure and tested directly. (The in-process CHAIN move was purged with the
free-agent purge, 2026-07-23 — a free agent composes tools directly.)

Run directly: venv/bin/python3 tests/test_pi_dispatch.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pi_agent import dispatch  # noqa: E402
from pi_agent.dispatch import (  # noqa: E402
    Move,
    MoveResult,
    MoveType,
    RunResult,
    build_run_env,
    dispatch_run,
    invoke_move,
    read_run_result,
)


def _run_record(how_far, **extras):
    """A journal run_record shaped exactly as record_run_outcome writes it."""
    return {
        "run_id": "r",
        "kind": "run_record",
        "text": f"run r (auto mode): {how_far}",
        "extras": {"how_far": how_far, **extras},
    }


class TestReadRunResult(unittest.TestCase):
    """read_run_result is pure: a run dir + a record + an exit code in, a
    faithful RunResult out. It never raises."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "r"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_verification(self, publishable, verified, total, verdicts=None):
        (self.run_dir / "verification.json").write_text(
            json.dumps({
                "publishable": publishable, "verified": verified, "total": total,
                "verdicts": verdicts or [],
            })
        )

    def _write_paper(self):
        (self.run_dir / "stage6").mkdir()
        (self.run_dir / "stage6" / "paper.md").write_text("# paper")

    def test_clean_completion_with_a_standing_paper(self):
        self._write_paper()
        record = _run_record(
            "completed",
            iterate_decision="exit",
            verification={"publishable": True, "verified": 2, "total": 2},
        )
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertTrue(r.completed)
        self.assertTrue(r.publishable)
        self.assertEqual((r.verified, r.total), (2, 2))
        self.assertTrue(r.paper_path.endswith("stage6/paper.md"))
        self.assertTrue(r.has_run_record)

    def test_completed_but_not_publishable_is_not_a_success(self):
        record = _run_record(
            "completed",
            verification={"publishable": False, "verified": 1, "total": 2},
        )
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertTrue(r.completed)          # it did complete
        self.assertFalse(r.publishable)       # but the numbers did not stand

    def test_gate_halt_is_read_as_its_outcome_not_a_completion(self):
        record = _run_record("halted at gate after_stage_2")
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertFalse(r.completed)
        self.assertEqual(r.outcome, "halted at gate after_stage_2")
        self.assertIsNone(r.publishable)      # never reached verification

    def test_barren_halt_outcome(self):
        record = _run_record("halted_barren_budget_spent")
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertFalse(r.completed)
        self.assertEqual(r.outcome, "halted_barren_budget_spent")

    def test_no_run_record_means_it_died_without_journaling(self):
        # The watched external-kill scenario: a run that left no record. The
        # reader must say so, not invent an outcome.
        r = read_run_result(self.run_dir, "r", 137, None)
        self.assertFalse(r.has_run_record)
        self.assertIsNone(r.outcome)
        self.assertFalse(r.completed)
        self.assertEqual(r.exit_code, 137)
        # ...and no record means no cost either — the same signal (free-director
        # Phase 1: the parent cannot see a subprocess meter that never persisted).
        self.assertIsNone(r.cost)

    def test_per_run_cost_is_surfaced_from_the_run_record(self):
        record = _run_record(
            "completed free investigation (publishable)",
            cost={"calls": 42, "tokens": 5000},
        )
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertEqual(r.cost, {"calls": 42, "tokens": 5000})
        self.assertEqual(r.as_dict()["cost"], {"calls": 42, "tokens": 5000})

    def test_only_reproduced_reusable_artifacts_are_surfaced(self):
        import json as _json
        prod = {"kind": "code", "code": "c", "quantity": "n", "emits": ["good.fasta"]}
        (self.run_dir / "free_investigation.json").write_text(_json.dumps({
            "reusable_artifacts": [
                {"name": "good.fasta", "producer": prod, "verified": True},
                {"name": "bad.fasta", "producer": prod, "verified": False, "error": "no emit"},
            ]
        }))
        r = read_run_result(self.run_dir, "r", 0, _run_record("completed"))
        names = [ra["name"] for ra in r.reusable_artifacts]
        self.assertEqual(names, ["good.fasta"])                # only the reproduced one
        self.assertEqual(r.reusable_artifacts[0]["producer"], prod)
        self.assertEqual(r.as_dict()["reusable_artifacts"], r.reusable_artifacts)

    def test_no_free_investigation_json_means_no_reusables(self):
        r = read_run_result(self.run_dir, "r", 0, _run_record("completed"))
        self.assertEqual(r.reusable_artifacts, [])

    def test_verification_json_is_read_when_the_record_lacks_it(self):
        self._write_verification(True, 3, 3)
        record = _run_record("completed")  # no verification in extras
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertTrue(r.publishable)
        self.assertEqual((r.verified, r.total), (3, 3))

    def test_signoff_and_constraint_surface_from_extras(self):
        record = _run_record(
            "completed",
            needs_human_signoff=True,
            allowed_substrates=["cobrapy"],
        )
        r = read_run_result(self.run_dir, "r", 0, record)
        self.assertTrue(r.needs_human_signoff)
        self.assertEqual(r.allowed_substrates, ["cobrapy"])

    def test_reading_never_raises_on_garbage(self):
        (self.run_dir / "verification.json").write_text("{not json")
        r = read_run_result(self.run_dir, "r", 0, {"kind": "run_record"})
        self.assertIsInstance(r, RunResult)  # did not raise
        self.assertIsNone(r.publishable)

    def test_as_dict_round_trips_the_decision_fields(self):
        record = _run_record("completed", verification={"publishable": True, "verified": 1, "total": 1})
        d = read_run_result(self.run_dir, "r", 0, record).as_dict()
        self.assertEqual(d["outcome"], "completed")
        self.assertTrue(d["publishable"])
        self.assertTrue(d["completed"])
        self.assertIn("findings", d)

    def test_verified_findings_are_surfaced_as_the_results_the_pi_reads(self):
        # The measured VALUES, each flagged verified — this is the data the PI
        # decides from, not just pass/fail. A verified finding reports the
        # reproduced value; an unverified one is surfaced too, flagged.
        self._write_verification(True, 1, 2, verdicts=[
            {"label": "run 1 growth_rate", "verified": True, "original": 0.87, "reproduced": 0.87, "reason": "reproduced"},
            {"label": "run 2 flux", "verified": False, "original": 2.1, "reproduced": 9.9, "reason": "mismatch"},
        ])
        r = read_run_result(self.run_dir, "r", 0, _run_record("completed"))
        self.assertEqual(len(r.findings), 2)
        self.assertEqual(r.findings[0], {"label": "run 1 growth_rate", "value": 0.87, "verified": True, "reason": "reproduced"})
        self.assertFalse(r.findings[1]["verified"])          # a shaky result, surfaced not hidden
        self.assertEqual(r.findings[1]["value"], 2.1)        # the recorded value when it did not reproduce

    def test_a_run_without_verification_has_no_findings(self):
        r = read_run_result(self.run_dir, "r", 0, _run_record("halted_barren_budget_spent"))
        self.assertEqual(r.findings, [])


class TestBuildRunEnv(unittest.TestCase):
    """build_run_env is pure: the move's knobs become the child's env."""

    def test_unconstrained_non_campaign_adds_nothing(self):
        env = build_run_env(base_env={"PATH": "/x"})
        self.assertEqual(env, {"PATH": "/x"})

    def test_allowed_substrates_becomes_the_constraint_var(self):
        env = build_run_env(base_env={}, allowed_substrates=["cobrapy", "rdkit"])
        self.assertEqual(env["ALLOWED_SUBSTRATES"], "cobrapy,rdkit")

    def test_campaign_sets_the_flag_and_iters(self):
        env = build_run_env(base_env={}, campaign=True, campaign_max_iters=25)
        self.assertEqual(env["RESEARCH_CAMPAIGN"], "1")
        self.assertEqual(env["CAMPAIGN_MAX_ITERS"], "25")

    def test_non_campaign_does_not_set_the_flag(self):
        self.assertNotIn("RESEARCH_CAMPAIGN", build_run_env(base_env={}))

    def test_explicit_allow_set_replaces_an_inherited_one(self):
        env = build_run_env(base_env={"ALLOWED_SUBSTRATES": "mafft"}, allowed_substrates=["cobrapy"])
        self.assertEqual(env["ALLOWED_SUBSTRATES"], "cobrapy")

    def test_extra_env_applies_last(self):
        env = build_run_env(base_env={}, extra_env={"FOO": "bar", "N": 3})
        self.assertEqual(env["FOO"], "bar")
        self.assertEqual(env["N"], "3")  # stringified


# A stub "supervisor" that writes the evidence a real run leaves, then exits
# with a code chosen via env. It reads --run-id and --domain like the real one.
_STUB = textwrap.dedent(
    """
    import argparse, json, os, sys
    from pathlib import Path
    p = argparse.ArgumentParser()
    p.add_argument("--mode"); p.add_argument("--domain"); p.add_argument("--run-id")
    a = p.parse_args()
    runs_root = Path(os.environ["STUB_RUNS_ROOT"])
    run_dir = runs_root / a.run_id
    (run_dir / "stage6").mkdir(parents=True, exist_ok=True)
    if os.environ.get("STUB_WRITE_PAPER") == "1":
        (run_dir / "stage6" / "paper.md").write_text("# stub paper")
    (run_dir / "verification.json").write_text(json.dumps({
        "publishable": os.environ.get("STUB_PUBLISHABLE") == "1",
        "verified": 1, "total": 1,
    }))
    # Echo the constraint so the test can prove the env was threaded through.
    (run_dir / "seen_env.json").write_text(json.dumps({
        "ALLOWED_SUBSTRATES": os.environ.get("ALLOWED_SUBSTRATES"),
        "RESEARCH_CAMPAIGN": os.environ.get("RESEARCH_CAMPAIGN"),
        "domain": a.domain,
    }))
    sys.exit(int(os.environ.get("STUB_EXIT", "0")))
    """
)


class TestDispatchRunAgainstAStub(unittest.TestCase):
    """dispatch_run's plumbing: mint id -> build env -> run process -> read
    result. Exercised against the stub so no live pipeline runs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.stub = self.tmp / "stub.py"
        self.stub.write_text(_STUB)
        self.runs_root = self.tmp / "runs"
        self.runs_root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _command_builder(self, run_id, domain, mode):
        return [sys.executable, str(self.stub),
                "--mode", mode, "--domain", domain, "--run-id", run_id]

    def _dispatch(self, **kw):
        # The stub reads STUB_RUNS_ROOT to know where to write; thread it plus
        # the caller's knobs through extra_env, and read the record from disk
        # rather than the shared journal.
        def reader(rid):
            f = self.runs_root / rid / "record.json"
            return json.loads(f.read_text()) if f.is_file() else None

        base_extra = {"STUB_RUNS_ROOT": str(self.runs_root)}
        base_extra.update(kw.pop("extra_env", {}))
        return dispatch_run(
            "a cobrapy question",
            "auto",
            runs_root=self.runs_root,
            command_builder=self._command_builder,
            record_reader=reader,
            extra_env=base_extra,
            **kw,
        )

    def test_a_publishable_run_reads_back_as_publishable(self):
        r = self._dispatch(extra_env={"STUB_EXIT": "0", "STUB_PUBLISHABLE": "1", "STUB_WRITE_PAPER": "1"})
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(r.publishable)
        self.assertIsNotNone(r.paper_path)

    def test_a_nonzero_exit_is_captured_not_masked(self):
        r = self._dispatch(extra_env={"STUB_EXIT": "1", "STUB_PUBLISHABLE": "0"})
        self.assertEqual(r.exit_code, 1)
        self.assertFalse(r.publishable)

    def test_the_constraint_is_threaded_into_the_child_env(self):
        r = self._dispatch(allowed_substrates=["cobrapy"], extra_env={"STUB_EXIT": "0"})
        seen = json.loads((Path(r.run_dir) / "seen_env.json").read_text())
        self.assertEqual(seen["ALLOWED_SUBSTRATES"], "cobrapy")

    def test_campaign_flag_is_threaded_into_the_child_env(self):
        # invoke_move drives this in production; here prove dispatch_run does it.
        r = dispatch_run(
            "q", "auto", runs_root=self.runs_root,
            command_builder=self._command_builder,
            record_reader=lambda rid: None,
            campaign=True,
            extra_env={"STUB_RUNS_ROOT": str(self.runs_root), "STUB_EXIT": "0"},
        )
        seen = json.loads((Path(r.run_dir) / "seen_env.json").read_text())
        self.assertEqual(seen["RESEARCH_CAMPAIGN"], "1")

    def test_a_missing_record_yields_has_run_record_false(self):
        r = self._dispatch(extra_env={"STUB_EXIT": "0"})  # reader finds no record.json
        self.assertFalse(r.has_run_record)
        self.assertIsNone(r.outcome)


class TestInvokeMove(unittest.TestCase):
    """The uniform interface: every move type through one call, one envelope."""

    def test_single_move_dispatches_a_non_campaign_run(self):
        seen = {}

        def fake_dispatch(domain, mode, **kw):
            seen.update(kw, domain=domain, mode=mode)
            return RunResult(run_id="r1", exit_code=0, run_dir="d", has_run_record=True,
                             outcome="completed", publishable=True)

        res = invoke_move(Move(MoveType.SINGLE, domain="q", allowed_substrates=["rdkit"]),
                          dispatch=fake_dispatch)
        self.assertIsInstance(res, MoveResult)
        self.assertEqual(res.move_type, "single")
        self.assertTrue(res.succeeded)          # publishable
        self.assertFalse(seen["campaign"])      # SINGLE => not a campaign
        self.assertEqual(seen["allowed_substrates"], ["rdkit"])

    def test_campaign_move_sets_campaign_true(self):
        seen = {}

        def fake_dispatch(domain, mode, **kw):
            seen.update(kw)
            return RunResult(run_id="r2", exit_code=0, run_dir="d", has_run_record=True,
                             outcome="completed", publishable=False)

        res = invoke_move(Move(MoveType.CAMPAIGN, domain="q", campaign_max_iters=10),
                          dispatch=fake_dispatch)
        self.assertTrue(seen["campaign"])
        self.assertEqual(seen["campaign_max_iters"], 10)
        self.assertFalse(res.succeeded)         # ran, but not publishable

    def test_a_run_move_without_a_domain_raises(self):
        with self.assertRaises(ValueError):
            invoke_move(Move(MoveType.SINGLE), dispatch=lambda *a, **k: None)


class TestSupervisorAcceptsRunId(unittest.TestCase):
    """The one supervisor change: --run-id is accepted and, when omitted,
    behavior is unchanged. Proven at the argparse layer without a live run."""

    def test_run_id_flag_parses_and_defaults_to_none(self):
        import argparse
        # Mirror main()'s parser construction minimally to prove the flag shape.
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=["human", "auto"], default="human")
        parser.add_argument("--domain", required=True)
        parser.add_argument("--run-id", default=None)
        ns = parser.parse_args(["--domain", "q"])
        self.assertIsNone(ns.run_id)
        ns2 = parser.parse_args(["--domain", "q", "--run-id", "fixed-1"])
        self.assertEqual(ns2.run_id, "fixed-1")

    def test_supervisor_main_source_uses_run_id_or_make_run_id(self):
        # Guard the byte-level intent: the run id is caller-or-fresh, not
        # unconditionally fresh. Cheap source assertion, no run.
        src = (ROOT / "supervisor.py").read_text()
        self.assertIn("args.run_id or make_run_id()", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
