"""test_free_experimenter.py — the un-caged experimenter (PRIME DIRECTIVE).

Proves the free-agent harness:
  * run_free_investigation hosts a FULL agent on a goal and returns its result
    (no substrate menu, no composition-recipe cage);
  * it writes a director-readable verification.json, so a free investigation
    feeds the PI arc exactly as any run (round-trip through read_run_result);
  * the validator keeps the report honest (a kept/verified finding must say how
    to reproduce it) without ever second-guessing WHAT was investigated;
  * capability_guard permits the free experimenter the FULL (tooled) profile — it
    roams, it is not a sealed measurement-judge.

Call-free: the FULL agent is injected as a fake `call`.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capability_guard  # noqa: E402
from model_call import FULL  # noqa: E402
from pi_agent.dispatch import read_run_result  # noqa: E402
from stages.free_experimenter import (  # noqa: E402
    FREE_STAGE_NAME,
    _validate_free_result,
    run_free_investigation,
)
from stages.verification import ArtifactError, rerun_artifact  # noqa: E402

_FAKE_RESULT = {
    "summary": "descriptor space is ~4-dimensional",
    "findings": [
        {"label": "n_pc_90", "value": 4, "verified": True,
         "reproduce": "python pca.py",
         "artifact": {"file": "pca.py", "quantity": "n_pc_90"}},
        {"label": "hypothesis_X", "value": "inconclusive", "verified": False,
         "reproduce": ""},
    ],
    "publishable": True,
}


def _fake_call(*args, **kwargs):
    return copy.deepcopy(_FAKE_RESULT), {"model": "fake"}


def _fake_verify_by_artifact(claims, run_id=None):
    """A stand-in wall: a claim reproduces IFF it carries an artifact (mirroring
    the real wall's no_artifact verdict), and writes the director-shaped
    verification.json exactly as verify_run does."""
    verdicts = []
    for i, c in enumerate(claims):
        ok = c.get("artifact") is not None
        verdicts.append({
            "claim_index": i, "label": c.get("label"), "verified": ok,
            "reproduced": c.get("value") if ok else None,
            "original": c.get("value"),
            "reason": "reproduced" if ok else "no_artifact",
        })
    n_ok = sum(1 for v in verdicts if v["verified"])
    summary = {"total": len(verdicts), "verified": n_ok,
               "failed": len(verdicts) - n_ok,
               "publishable": n_ok == len(verdicts), "verdicts": verdicts}
    if run_id:
        (Path("runs") / str(run_id) / "verification.json").write_text(
            json.dumps(summary))
    return summary


class TestFreeInvestigation(unittest.TestCase):
    def test_returns_the_agents_result_with_no_substrate_cage(self):
        result = run_free_investigation("map descriptor space", call=_fake_call)
        self.assertEqual(len(result["findings"]), 2)
        self.assertTrue(result["publishable"])
        self.assertEqual(result["goal"], "map descriptor space")

    def test_writes_a_director_readable_verification(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "runs" / "freerun"
            run_dir.mkdir(parents=True)
            # run_free_investigation writes under Path("runs")/run_id; point cwd there
            import os
            cwd = os.getcwd()
            os.chdir(d)
            try:
                # the WALL (injected here) writes verification.json and its
                # verdicts are what the director reads.
                run_free_investigation("q", run_id="freerun", call=_fake_call,
                                       verify=_fake_verify_by_artifact)
                record = {"extras": {"how_far": "completed free investigation"}}
                rr = read_run_result(Path("runs") / "freerun", "freerun", 0, record)
            finally:
                os.chdir(cwd)
        # the director reads the verified CLAIM's reproduced value straight through
        self.assertTrue(rr.publishable)
        self.assertEqual(rr.verified, 1)
        self.assertEqual(rr.total, 1)          # the one kept claim (the caveat is not one)
        labels = {f["label"]: f for f in rr.findings}
        self.assertEqual(labels["n_pc_90"]["value"], 4)
        self.assertTrue(labels["n_pc_90"]["verified"])


class TestPerRunWorkspace(unittest.TestCase):
    """The free agent runs in an isolated per-run workspace (runs/<id>/workspace/)
    so its artifacts land there, not in the repo root. free_experimenter creates
    the dir and activates model_call.agent_workspace() around the call."""

    def test_workspace_created_and_active_during_the_call(self):
        import os

        import model_call
        seen = {}

        def recording_call(stage, sp, inp, schema, **kw):
            # the workspace cwd is active for the DURATION of the call
            seen["cwd"] = model_call._AGENT_CWD.get()
            return _FAKE_RESULT, {"model": "fake"}

        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                (Path("runs") / "wsrun").mkdir(parents=True)
                run_free_investigation("q", run_id="wsrun", call=recording_call,
                                       verify=_fake_verify_by_artifact)
                ws = Path("runs") / "wsrun" / "workspace"
                self.assertTrue(ws.is_dir())                    # dir created
                self.assertEqual(seen["cwd"], str(ws.resolve()))  # cwd active in-call
            finally:
                os.chdir(cwd)
        # the context is reset once the call returns
        self.assertIsNone(model_call._AGENT_CWD.get())

    def test_no_run_id_keeps_the_default_cwd(self):
        import model_call
        seen = {}

        def recording_call(stage, sp, inp, schema, **kw):
            seen["cwd"] = model_call._AGENT_CWD.get()
            return _FAKE_RESULT, {"model": "fake"}

        run_free_investigation("q", call=recording_call)  # no run_id
        self.assertIsNone(seen["cwd"])  # default cwd — byte-identical old path

    def test_prompt_tells_the_agent_about_its_workspace(self):
        captured = {}

        def capture_call(stage, sysprompt, inp, schema, **kw):
            captured["sp"] = sysprompt
            return _FAKE_RESULT, {"model": "fake"}

        run_free_investigation("q", call=capture_call)
        self.assertIn("YOUR WORKSPACE", captured["sp"])
        self.assertIn("relative paths", captured["sp"])
        self.assertIn("from tools.run_rdkit import run_rdkit", captured["sp"])


class TestWorkspaceOptionKwargs(unittest.TestCase):
    """model_call: the cwd + PYTHONPATH the SDK gets for a tooled workspace call.
    PYTHONPATH leads with the repo root so `from tools.run_X import ...` resolves
    from the workspace; the SDK merges it onto the inherited env."""

    def test_empty_without_an_active_workspace(self):
        import model_call
        self.assertEqual(model_call._workspace_option_kwargs(uses_tools=True), {})

    def test_empty_for_a_sealed_call_even_inside_a_workspace(self):
        import model_call
        with model_call.agent_workspace("/tmp/ws"):
            self.assertEqual(
                model_call._workspace_option_kwargs(uses_tools=False), {})

    def test_cwd_and_pythonpath_for_a_tooled_workspace_call(self):
        import model_call
        with model_call.agent_workspace("/tmp/ws"):
            kw = model_call._workspace_option_kwargs(uses_tools=True)
        self.assertEqual(kw["cwd"], "/tmp/ws")
        self.assertTrue(
            kw["env"]["PYTHONPATH"].startswith(str(model_call._PROJECT_ROOT)))

    def test_context_manager_sets_and_resets(self):
        import model_call
        self.assertIsNone(model_call._AGENT_CWD.get())
        with model_call.agent_workspace("/tmp/ws"):
            self.assertEqual(model_call._AGENT_CWD.get(), "/tmp/ws")
        self.assertIsNone(model_call._AGENT_CWD.get())


class TestControllerReVerify(unittest.TestCase):
    """The verification wall is AUTHORITATIVE: its re-run, not the agent's
    self-report, sets `verified`, and it can only REMOVE `publishable`."""

    def _run(self, result, verify):
        import os
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                (Path("runs") / "rv").mkdir(parents=True)
                return run_free_investigation(
                    "q", run_id="rv",
                    call=lambda *a, **k: (copy.deepcopy(result), {"model": "f"}),
                    verify=verify)
            finally:
                os.chdir(cwd)

    def test_wall_rejection_overrides_a_false_self_report(self):
        # the agent CLAIMED verified; the wall says the number did not reproduce
        result_in = {"summary": "s", "publishable": True, "findings": [
            {"label": "m", "value": 4, "verified": True, "reproduce": "x",
             "artifact": {"file": "m.py", "quantity": "m"}}]}

        def rejecting_verify(claims, run_id=None):
            verdicts = [{"claim_index": 0, "label": "m", "verified": False,
                         "reason": "mismatch", "original": 4, "reproduced": 7}]
            summary = {"total": 1, "verified": 0, "failed": 1,
                       "publishable": False, "verdicts": verdicts}
            (Path("runs") / str(run_id) / "verification.json").write_text(
                json.dumps(summary))
            return summary

        out = self._run(result_in, rejecting_verify)
        self.assertFalse(out["findings"][0]["verified"])  # downgraded by the wall
        self.assertFalse(out["publishable"])              # trust removed

    def test_wall_confirmation_keeps_publishable_and_ignores_caveats(self):
        out = self._run(_FAKE_RESULT, _fake_verify_by_artifact)
        self.assertTrue(out["publishable"])                # claim reproduced
        self.assertTrue(out["findings"][0]["verified"])    # confirmed claim
        self.assertFalse(out["findings"][1]["verified"])   # honest caveat, untouched

    def test_no_run_dir_keeps_self_report_no_wall(self):
        # no run_id -> no workspace, no wall -> the agent's report is unchanged
        out = run_free_investigation(
            "q", call=lambda *a, **k: (copy.deepcopy(_FAKE_RESULT), {"model": "f"}))
        self.assertTrue(out["findings"][0]["verified"])
        self.assertTrue(out["publishable"])


class TestArtifactRequiredForVerified(unittest.TestCase):
    def test_verified_finding_without_an_artifact_is_flagged(self):
        errs = _validate_free_result({"findings": [
            {"label": "m", "value": 1, "verified": True, "reproduce": "x"}],
            "publishable": True})
        self.assertTrue(any("artifact" in e for e in errs))

    def test_substrate_artifact_satisfies_the_requirement(self):
        errs = _validate_free_result({"findings": [
            {"label": "m", "value": 1, "verified": True, "reproduce": "x",
             "artifact": {"substrate_id": "rdkit", "typed_input": {},
                          "quantity": "tpsa"}}], "publishable": True})
        self.assertEqual(errs, [])

    def test_unverified_finding_needs_no_artifact(self):
        errs = _validate_free_result({"findings": [
            {"label": "note", "value": "qualitative", "verified": False}],
            "publishable": False})
        self.assertEqual(errs, [])


class TestWorkspaceFileArtifact(unittest.TestCase):
    """The wall's new 'workspace_file' kind re-runs the saved file through the
    same deterministic code sandbox as an inline code artifact."""

    def test_reads_the_file_and_reruns_it_as_code(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "m.py"
            code = "metrics = {}\nmetrics['m'] = 4\n"
            f.write_text(code)
            with patch("tools.run_python_experiment.run_python_experiment",
                       return_value={"valid": True, "qoi": 4.0}) as rpe:
                out = rerun_artifact(
                    {"kind": "workspace_file", "path": str(f), "quantity": "m"})
            # it ran the FILE's contents through the code sandbox
            self.assertEqual(rpe.call_args.args[0]["code"], code)
            self.assertEqual(rpe.call_args.args[0]["quantity"], "m")
            self.assertEqual(out, {"value": 4.0, "error": None})

    def test_missing_file_is_an_honest_rerun_error_not_a_crash(self):
        out = rerun_artifact(
            {"kind": "workspace_file", "path": "/no/such/file.py", "quantity": "m"})
        self.assertIsNone(out["value"])
        self.assertIn("not found", out["error"])

    def test_missing_path_or_quantity_raises(self):
        with self.assertRaises(ArtifactError):
            rerun_artifact({"kind": "workspace_file", "quantity": "m"})


class TestHonestyValidator(unittest.TestCase):
    def test_verified_finding_must_say_how_to_reproduce(self):
        errs = _validate_free_result({
            "findings": [{"label": "r", "value": 1, "verified": True,
                          "reproduce": ""}],
            "publishable": True})
        self.assertTrue(any("reproduce" in e for e in errs))

    def test_a_clean_report_validates(self):
        self.assertEqual(_validate_free_result(_FAKE_RESULT), [])

    def test_empty_findings_are_allowed(self):
        # the experimenter may honestly find nothing keepable
        self.assertEqual(
            _validate_free_result({"findings": [], "publishable": False}), [])


class TestCapabilityProfile(unittest.TestCase):
    def test_the_free_experimenter_may_hold_the_full_tooled_profile(self):
        # roams (FULL), not a sealed measurement-judge — must not raise
        capability_guard.assert_profile_allowed(FREE_STAGE_NAME, FULL.name)


class TestToolCatalogExposedOptionally(unittest.TestCase):
    """Substrates are OPTIONAL tools the free agent may reach for (PRIME
    DIRECTIVE) — the prompt lists them with an approximate caveat and an explicit
    'not a boundary' framing, never as a gate."""

    def test_prompt_lists_tools_as_optional_with_caveats(self):
        captured = {}

        def capture_call(stage, sysprompt, inp, schema, **kw):
            captured["sp"] = sysprompt
            return _FAKE_RESULT, {"model": "fake"}

        run_free_investigation("q", call=capture_call)
        sp = captured["sp"]
        self.assertIn("SPECIALIZED TOOLS", sp)
        self.assertIn("NOT a boundary", sp)         # optional, not a gate
        self.assertIn("rdkit", sp)                  # a deterministic tool
        self.assertIn("cavity_2d_cfd", sp)          # an approximate tool
        self.assertIn("confidently WRONG", sp)      # the approximate caveat


if __name__ == "__main__":
    unittest.main()
