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

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capability_guard  # noqa: E402
from model_call import FULL  # noqa: E402
from pi_agent.dispatch import read_run_result  # noqa: E402
from stages.free_experimenter import (  # noqa: E402
    FREE_STAGE_NAME,
    _validate_free_result,
    run_free_investigation,
)

_FAKE_RESULT = {
    "summary": "descriptor space is ~4-dimensional",
    "findings": [
        {"label": "n_pc_90", "value": 4, "verified": True,
         "reproduce": "python pca.py"},
        {"label": "hypothesis_X", "value": "inconclusive", "verified": False,
         "reproduce": ""},
    ],
    "publishable": True,
}


def _fake_call(*args, **kwargs):
    return _FAKE_RESULT, {"model": "fake"}


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
                run_free_investigation("q", run_id="freerun", call=_fake_call)
                record = {"extras": {"how_far": "completed free investigation"}}
                rr = read_run_result(Path("runs") / "freerun", "freerun", 0, record)
            finally:
                os.chdir(cwd)
        # the director reads the verified finding's value straight through
        self.assertTrue(rr.publishable)
        self.assertEqual(rr.verified, 1)
        self.assertEqual(rr.total, 2)
        labels = {f["label"]: f for f in rr.findings}
        self.assertEqual(labels["n_pc_90"]["value"], 4)
        self.assertTrue(labels["n_pc_90"]["verified"])
        self.assertFalse(labels["hypothesis_X"]["verified"])


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
                run_free_investigation("q", run_id="wsrun", call=recording_call)
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
