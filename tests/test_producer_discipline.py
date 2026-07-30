"""test_producer_discipline.py — one scalar, one file (2026-07-30).

THE REUSABLE LESSON study-20260730T034915Z PAID FOR, re-derived from its own
verification.json and free_investigation.json rather than from the write-up:

  m11: 17 findings, 12 marked verified, 12 DISTINCT producer files
       (m_n_segments.py, m_n_sections.py, m_sn_ratio.py, ...) -> 12/12 reproduced
  m12: 26 findings, 0 artifacts named -> 0 reproduced
  m14: 12 findings, 0 artifacts named -> 0 reproduced
  m15: 34 findings, 0 artifacts named -> 0 reproduced
  m16: 26 findings, 0 artifacts named -> 0 reproduced

98 findings against one dataset, none of them backed. The wall sinks a whole
record when any part of it fails, and a producer that was never written sinks
everything at once — which is why the brief also says to write each one AS YOU GO
(three of those four moves were cut off mid-work; see
docs/finding_m16_stopping_mechanism.md).

GUIDANCE THE AGENT MAY APPLY OR IGNORE. No schema field, no validator, no gate —
the tests below pin that too.

Run directly: venv/bin/python3 tests/test_producer_discipline.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages import free_experimenter as FE  # noqa: E402


class TestTheBriefCarriesIt(unittest.TestCase):
    def test_one_scalar_one_file_is_stated(self):
        self.assertIn("ONE SCALAR, ONE FILE", FE.SYSTEM_PROMPT)
        self.assertIn("a separate, self-contained file per number of record",
                      FE.SYSTEM_PROMPT)

    def test_it_names_the_measured_result_not_just_an_opinion(self):
        self.assertIn("reproduced 12 of 12", FE.SYSTEM_PROMPT)
        self.assertIn("reproduced 0 of 98", FE.SYSTEM_PROMPT)

    def test_it_explains_the_mechanism_that_sinks_a_record(self):
        self.assertIn("every finding that names it sinks together",
                      FE.SYSTEM_PROMPT)

    def test_it_says_write_them_as_you_go(self):
        """The half that matters most: three of the four failing moves were cut
        off before the wrap-up, so a producer deferred to the end never existed."""
        self.assertIn("WRITE EACH ONE AS YOU GO", FE.SYSTEM_PROMPT)
        self.assertIn("a finding that does not count", FE.SYSTEM_PROMPT)

    def test_it_is_guidance_with_a_stated_exception(self):
        self.assertIn("This is guidance, not a rule", FE.SYSTEM_PROMPT)
        self.assertIn("genuinely coupled outputs of a single expensive "
                      "computation is fine", FE.SYSTEM_PROMPT)


class TestNothingWasEnforced(unittest.TestCase):
    def test_a_single_shared_artifact_is_still_perfectly_valid(self):
        """The discipline must not become a schema rule: two findings naming the
        same file still validate."""
        errors = FE._validate_free_result({
            "summary": "s",
            "findings": [
                {"label": "a", "value": 1, "verified": True,
                 "reproduce": "run all.py",
                 "artifact": {"file": "all.py", "quantity": "a"}},
                {"label": "b", "value": 2, "verified": True,
                 "reproduce": "run all.py",
                 "artifact": {"file": "all.py", "quantity": "b"}},
            ],
            "publishable": True,
        })
        self.assertEqual(errors, [])

    def test_no_new_required_field(self):
        self.assertEqual(FE.SCHEMA["required"],
                         ["summary", "findings", "publishable"])


if __name__ == "__main__":
    unittest.main()
