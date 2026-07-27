"""Runbooks — the operating knowledge an agent should not have to re-buy.

Offline. What is asserted is that the index composes, that a runbook records
STATUS honestly (including tools that do not work), and that every runbook tells
the agent how to record a result — the section Claude Science's skills have no
need for and ours cannot do without.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import runbooks  # noqa: E402

RUNBOOK_DIR = ROOT / "runbooks"


class TestParsing(unittest.TestCase):

    def test_frontmatter_is_read(self):
        meta = runbooks._parse_frontmatter(
            '---\nname: x\ndescription: "a thing"\nstatus: WORKS\n---\nbody\n')
        self.assertEqual(meta["name"], "x")
        self.assertEqual(meta["description"], "a thing")

    def test_a_file_without_frontmatter_degrades_to_no_metadata(self):
        self.assertEqual(runbooks._parse_frontmatter("just a body"), {})

    def test_a_missing_directory_is_empty_not_a_crash(self):
        self.assertEqual(runbooks.all_runbooks("/no/such/dir"), [])
        self.assertEqual(runbooks.runbook_catalog("/no/such/dir"), "")

    def test_name_falls_back_to_the_filename(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "orphan.md").write_text("no frontmatter here")
            self.assertEqual(runbooks.all_runbooks(d)[0]["name"], "orphan")


class TestTheRealRunbooks(unittest.TestCase):

    def setUp(self):
        self.books = runbooks.all_runbooks(RUNBOOK_DIR)

    def test_they_exist_and_all_declare_name_description_status(self):
        self.assertGreaterEqual(len(self.books), 5)
        for b in self.books:
            self.assertTrue(b["name"], b["path"])
            self.assertTrue(b["description"], b["name"])
            self.assertTrue(b["status"], b["name"])

    def test_every_WORKING_runbook_says_how_to_record_a_result(self):
        # The section that distinguishes ours from a how-to-run-it skill: a
        # runbook that omitted it would teach the agent to produce numbers it
        # cannot keep. A BROKEN tool is exempt — it has no result to record, and
        # padding it with a section would be ceremony rather than information.
        for b in self.books:
            if "BROKEN" in b["status"].upper():
                continue
            text = Path(b["path"]).read_text()
            self.assertIn("RECORDING THE RESULT", text.upper(), b["name"])

    def test_a_broken_runbook_says_what_to_use_instead(self):
        # Its whole job is redirecting the agent before it spends anything.
        for b in self.books:
            if "BROKEN" not in b["status"].upper():
                continue
            text = Path(b["path"]).read_text().lower()
            self.assertTrue(any(alt in text for alt in ("esmfold", "chai1")),
                            f"{b['name']} says it is broken but names no alternative")

    def test_a_known_broken_tool_is_recorded_as_broken(self):
        # Absence would invite the agent to spend an hour and a dollar finding
        # out for itself.
        boltz = [b for b in self.books if b["name"] == "boltz2"]
        self.assertTrue(boltz)
        self.assertIn("BROKEN", boltz[0]["status"].upper())

    def test_the_catalog_indexes_every_runbook_with_its_status(self):
        cat = runbooks.runbook_catalog(RUNBOOK_DIR)
        for b in self.books:
            self.assertIn(b["name"], cat)
            self.assertIn(b["status"], cat)

    def test_load_runbook_returns_a_body_or_none(self):
        self.assertIn("ESMFold", runbooks.load_runbook("esmfold", RUNBOOK_DIR) or "")
        self.assertIsNone(runbooks.load_runbook("nope", RUNBOOK_DIR))


class TestTheAgentIsToldTheyExist(unittest.TestCase):

    def test_the_index_rides_the_experimenter_prompt(self):
        from stages import free_experimenter as fe
        captured = {}

        def fake_call(stage, system_prompt, stage_input, schema, **kw):
            captured["prompt"] = system_prompt
            return {"summary": "s", "findings": [], "publishable": False}, {}

        fe.run_free_investigation("q", call=fake_call)
        self.assertIn("RUNBOOKS", captured["prompt"])
        self.assertIn("esmfold", captured["prompt"])

    def test_no_runbooks_means_an_unchanged_prompt(self):
        from stages import free_experimenter as fe
        prompts = []

        def fake_call(stage, system_prompt, stage_input, schema, **kw):
            prompts.append(system_prompt)
            return {"summary": "s", "findings": [], "publishable": False}, {}

        with mock.patch.object(runbooks, "runbook_catalog", return_value=""):
            fe.run_free_investigation("q", call=fake_call)
        self.assertNotIn("RUNBOOKS", prompts[0])


if __name__ == "__main__":
    unittest.main()
