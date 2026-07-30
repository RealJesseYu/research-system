"""test_study_lint.py — the deliverable-shape lint (harness/study_lint.py).

The failure it exists for is real and on disk: study-20260730T034915Z came out
9,296 words in 15 sections with NO table of contents, no abstract anywhere, and
an opening section titled "What this document is, and what it actually
establishes" that told a reader nothing about what to DO next. The write-up
prompt had asked for structure the whole time. Asking is not enforcement.

Call-free, no model calls, no disk beyond a tmpdir. Proves:
  - the opening block is required, must be FIRST, and must carry its four labels
    in order;
  - **What you can do with it now** must name a concrete entry point, not prose
    promising reproducibility;
  - a table of contents is required past six sections, and must actually list
    something;
  - both document kinds get a skeleton, and neither can skip the Abstract;
  - the mandatory "What a human must still validate" section survives;
  - a well-formed document of EITHER kind lints clean (the lint is satisfiable);
  - the deliverable back-pointer inserts into item 3 and is a no-op when there
    is nothing to point from.

Run directly: venv/bin/python3 tests/test_study_lint.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.study_lint import (  # noqa: E402
    MAX_OPENING_LINES, OPENING_HEADING, infer_document_kind,
    insert_entry_point_pointer, lint_study_dir, lint_study_paper,
    lint_study_supplement, opening_block, section_headings)


def _opening(entry="`python3 verify.py`", labels=None):
    labels = labels or ["What was accomplished", "What it is worth",
                        "What you can do with it now", "What is not established"]
    body = [f"## {OPENING_HEADING}\n"]
    for lab in labels:
        extra = entry if lab == "What you can do with it now" else "some text"
        body.append(f"**{lab}** — {extra}\n")
    return "\n".join(body)


RESEARCH_BODY = """
## Abstract
one paragraph.

## Introduction
prior work said X.

## Methods
we did Y.

## Results
0.42, independently reproduced.

## Conclusions
therefore Z.

## Limitations
the unverified ratio is not established.

## What a human must still validate

- the unverified ratio
"""

DESIGN_BODY = """
## Abstract
one paragraph.

## What was built
a 1.2 m arm.

## How it performs
0.42 m reach, independently reproduced.

## How to build it
run `python3 build.py`.

## Limitations
the tip deflection did not reproduce.

## What a human must still validate

- the tip deflection
"""


def _codes(failures):
    return sorted(f["code"] for f in failures)


class TestOpeningBlock(unittest.TestCase):
    def test_a_well_formed_research_paper_lints_clean(self):
        """The lint must be SATISFIABLE — a shape check nothing can pass is a
        shape check that will be deleted the first time it blocks a run."""
        self.assertEqual(
            lint_study_paper(_opening() + RESEARCH_BODY, "research"), [])

    def test_a_well_formed_design_paper_lints_clean(self):
        self.assertEqual(
            lint_study_paper(_opening() + DESIGN_BODY, "design"), [])

    def test_missing_opening_block_is_a_failure(self):
        out = lint_study_paper("# Title\n" + RESEARCH_BODY, "research")
        self.assertIn("opening_missing", _codes(out))

    def test_the_real_failure_shape_a_bureaucratic_first_section(self):
        """The exact live defect: a first section that describes the document
        instead of leading with the result."""
        text = ("# The AASHTO-93 equation measures the wrong thing\n\n"
                "## 0. What this document is, and what it actually establishes\n\n"
                "The brief was to find a consequential engineering decision...\n"
                + RESEARCH_BODY)
        self.assertIn("opening_missing", _codes(lint_study_paper(text, "research")))

    def test_opening_block_must_be_the_first_section(self):
        text = "# T\n\n## Introduction\nprelude.\n\n" + _opening() + RESEARCH_BODY
        self.assertIn("opening_not_first", _codes(lint_study_paper(text, "research")))

    def test_each_missing_label_is_named_individually(self):
        text = _opening(labels=["What was accomplished", "What it is worth"])
        out = lint_study_paper(text + RESEARCH_BODY, "research")
        targets = [f["target"] for f in out if f["code"] == "opening_label_missing"]
        self.assertEqual(sorted(targets),
                         ["What is not established", "What you can do with it now"])

    def test_labels_out_of_order_are_caught(self):
        text = _opening(labels=["What it is worth", "What was accomplished",
                                "What you can do with it now",
                                "What is not established"])
        self.assertIn("opening_labels_out_of_order",
                      _codes(lint_study_paper(text + RESEARCH_BODY, "research")))

    def test_prose_promising_reproducibility_is_not_an_entry_point(self):
        """Item (3) is the one a reader ACTS on. 'everything here is fully
        reproducible' is exactly the sentence that leaves them with nothing to
        type."""
        text = _opening(entry="everything here is fully reproducible.")
        out = lint_study_paper(text + RESEARCH_BODY, "research")
        self.assertIn("entry_point_missing", _codes(out))

    def test_a_named_file_counts_as_an_entry_point(self):
        text = _opening(entry="open `deliverable/README.md`.")
        self.assertNotIn("entry_point_missing",
                         _codes(lint_study_paper(text + RESEARCH_BODY, "research")))

    def test_opening_block_is_capped_to_one_screen(self):
        fat = _opening() + "\n" + "\n".join(f"line {i}" for i in range(MAX_OPENING_LINES + 5))
        out = lint_study_paper(fat + RESEARCH_BODY, "research")
        self.assertIn("opening_too_long", _codes(out))

    def test_opening_block_extraction_stops_at_the_next_section(self):
        block = opening_block(_opening() + RESEARCH_BODY)
        self.assertIn("What is not established", block)
        self.assertNotIn("prior work said X", block)

    def test_numbering_and_a_subtitle_are_tolerated(self):
        text = _opening().replace(f"## {OPENING_HEADING}",
                                  f"## 0. {OPENING_HEADING} — what this establishes")
        self.assertEqual(_codes(lint_study_paper(text + RESEARCH_BODY, "research")), [])


class TestNavigation(unittest.TestCase):
    def _many_sections(self, n):
        extra = "".join(f"\n## Section {i}\nbody.\n" for i in range(n))
        return _opening() + RESEARCH_BODY + extra

    def test_no_toc_needed_at_or_below_the_threshold(self):
        self.assertEqual(
            lint_study_paper(_opening() + RESEARCH_BODY, "research"), [])

    def test_toc_required_past_six_sections(self):
        out = lint_study_paper(self._many_sections(4), "research")
        self.assertIn("toc_missing", _codes(out))

    def test_a_toc_that_lists_nothing_is_caught(self):
        text = self._many_sections(4).replace(
            f"## {OPENING_HEADING}", "## Contents\n\n(todo)\n\n## " + OPENING_HEADING, 1)
        self.assertIn("toc_empty", _codes(lint_study_paper(text, "research")))

    def test_a_real_toc_satisfies_it(self):
        """Placed AFTER the opening block, which is where navigation belongs:
        nothing precedes the result, not even a table of contents."""
        toc = "\n## Contents\n\n- [Abstract](#abstract)\n- [Methods](#methods)\n- [Results](#results)\n"
        text = self._many_sections(4).replace("\n## Abstract", toc + "\n## Abstract", 1)
        self.assertEqual(_codes(lint_study_paper(text, "research")), [])

    def test_a_toc_placed_ahead_of_the_opening_block_is_caught(self):
        toc = "## Contents\n\n- [a](#a)\n- [b](#b)\n- [c](#c)\n\n"
        text = toc + self._many_sections(4)
        self.assertIn("opening_not_first", _codes(lint_study_paper(text, "research")))

    def test_review_sections_appended_after_drafting_do_not_owe_a_toc(self):
        """The referee and the build critic APPEND to a finished paper. A paper
        that linted clean when written must not fail the same lint an hour later
        purely because it was reviewed — and a TOC written at drafting time could
        not have listed sections that did not exist yet."""
        text = (_opening() + RESEARCH_BODY
                + "\n## Referee findings (artifact review)\nx.\n"
                + "\n## Build critique — could this be used today?\ny.\n"
                + "\n## Correction — claims the wall did not support\nz.\n")
        self.assertEqual(lint_study_paper(text, "research"), [])

    def test_section_headings_are_level_two_only(self):
        self.assertEqual(
            section_headings("## A\n### A.1\n## B\n# Title"), ["A", "B"])


class TestSkeleton(unittest.TestCase):
    def test_a_design_document_with_no_abstract_is_caught(self):
        """Goal 2 said 'build the replacement end to end', took the
        design-document branch, and there was no abstract anywhere."""
        text = _opening() + DESIGN_BODY.replace("## Abstract\none paragraph.\n", "")
        out = lint_study_paper(text, "design")
        self.assertIn("Abstract", [f["target"] for f in out])

    def test_missing_research_sections_are_named(self):
        text = _opening() + """
## Abstract
a.

## What a human must still validate

- x
"""
        targets = [f["target"] for f in lint_study_paper(text, "research")
                   if f["code"] == "section_missing"]
        self.assertEqual(sorted(targets),
                         ["Conclusions", "Introduction", "Limitations", "Methods",
                          "Results"])

    def test_synonym_headings_are_accepted(self):
        text = _opening() + RESEARCH_BODY.replace("## Introduction", "## Background")
        self.assertEqual(lint_study_paper(text, "research"), [])

    def test_an_invalid_kind_is_reported_not_crashed(self):
        out = lint_study_paper(_opening() + RESEARCH_BODY, "essay")
        self.assertIn("document_kind_invalid", _codes(out))

    def test_kind_is_inferred_when_it_was_never_declared(self):
        self.assertEqual(infer_document_kind(DESIGN_BODY), "design")
        self.assertEqual(infer_document_kind(RESEARCH_BODY), "research")


class TestMandatorySections(unittest.TestCase):
    def test_the_validate_section_is_still_mandatory(self):
        text = (_opening() + RESEARCH_BODY).replace(
            "## What a human must still validate", "## Notes")
        self.assertIn("validate_section_missing", _codes(lint_study_paper(text, "research")))

    def test_an_empty_paper_is_reported_not_crashed(self):
        self.assertEqual(_codes(lint_study_paper("   ", "research")), ["paper_empty"])

    def test_none_input_never_raises(self):
        self.assertEqual(_codes(lint_study_paper(None, "research")), ["paper_empty"])


class TestSupplement(unittest.TestCase):
    def test_a_thin_supplement_is_caught(self):
        self.assertIn("supplement_thin", _codes(lint_study_supplement("## Only one\nx")))

    def test_the_supplement_owes_navigation_but_not_a_skeleton(self):
        """It may be as long as it needs to be and carries whatever the arc
        produced — so it is held to navigation, not to a section list."""
        long_doc = "".join(f"## Phase {i}\ndetail.\n\n" for i in range(9))
        self.assertEqual(_codes(lint_study_supplement(long_doc)), ["toc_missing"])

    def test_empty_supplement_is_reported(self):
        self.assertEqual(_codes(lint_study_supplement("")), ["supplement_empty"])


class TestLintStudyDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_both_documents_are_required(self):
        codes = _codes(lint_study_dir(self.dir))
        self.assertEqual(codes, ["paper_missing", "supplement_missing"])

    def test_a_conforming_pair_lints_clean(self):
        (self.dir / "paper.md").write_text(_opening() + RESEARCH_BODY)
        (self.dir / "report.md").write_text("## Arc\ndetail.\n\n## Artifacts\nlist.\n")
        self.assertEqual(lint_study_dir(self.dir, "research"), [])

    def test_a_missing_supplement_does_not_hide_paper_failures(self):
        (self.dir / "paper.md").write_text("# T\n" + RESEARCH_BODY)
        codes = _codes(lint_study_dir(self.dir, "research"))
        self.assertIn("opening_missing", codes)
        self.assertIn("supplement_missing", codes)


class TestEntryPointPointer(unittest.TestCase):
    POINTER = "See `deliverable/README.md`."

    def test_pointer_lands_inside_item_three(self):
        text = _opening() + RESEARCH_BODY
        out = insert_entry_point_pointer(text, self.POINTER)
        block = opening_block(out)
        self.assertIn(self.POINTER, block)
        # ...and specifically before item 4, not appended to the document end.
        self.assertLess(block.index(self.POINTER), block.index("What is not established"))

    def test_still_lints_clean_after_the_pointer(self):
        out = insert_entry_point_pointer(_opening() + RESEARCH_BODY, self.POINTER)
        self.assertEqual(lint_study_paper(out, "research"), [])

    def test_no_opening_block_means_no_change(self):
        text = "# T\n\n## Introduction\nx.\n"
        self.assertEqual(insert_entry_point_pointer(text, self.POINTER), text)

    def test_inserting_twice_is_idempotent(self):
        once = insert_entry_point_pointer(_opening() + RESEARCH_BODY, self.POINTER)
        self.assertEqual(insert_entry_point_pointer(once, self.POINTER), once)


if __name__ == "__main__":
    unittest.main(verbosity=2)
