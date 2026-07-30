"""
harness/study_lint.py — the deliverable-shape lint: pure, deterministic,
ZERO model calls, importable.

WHY THIS EXISTS. The write-up prompt has always ASKED for structure, and the
structure was absent anyway: study-20260730T034915Z came out 9,296 words in 15
sections with no table of contents, no abstract, and an opening section titled
"What this document is, and what it actually establishes" that told a reader
nothing about what to DO next. Asking is not enforcement. This module is the
enforcement — it runs inside the writer's own bounded re-ask loop, so a paper
that lacks the opening block is sent back before it is ever saved.

WHAT IT CHECKS. Four things a reader needs on the FIRST SCREEN, in order
(docs/comparison_protocol.md §4 criteria 1, 2, 5, 6):

  ## Bottom line
  **What was accomplished** — the result, plain language, first
  **What it is worth**      — the impact, quantified, in units a reader cares about
  **What you can do with it now** — a CONCRETE entry point (a file, a command)
  **What is not established** — one line, so the boundary is known up front

plus navigation (a table of contents on anything over ~6 sections), the section
skeleton for the declared document kind, and the mandatory
"What a human must still validate" section that predates all of this.

WHAT IT DOES NOT CHECK, DELIBERATELY. It never reads a finding, a number, or a
provenance tag. Shape is all a text lint can honestly judge; whether the headline
is TRUE is the verification wall's job, and whether it over-claims is
study_paper's `unsupported_reproduction_claims`. A shape lint that started
grading content would quietly become a second, weaker verifier.

Failures are machine-readable — one {"code", "target", "message"} per failure,
empty list = clean — the same shape harness/paper_lint.py returns, so the two
lints report identically. Never raises: everything wrong becomes a failure entry.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------
# The opening block: name, labels, order, size.
# --------------------------------------------------------------------------

# The name says what it is. Kept short because it is also the anchor every other
# check, the writer prompt, and the deliverable pointer key on.
OPENING_HEADING = "Bottom line"

# Tolerant of section numbering ("## 0. Bottom line") and of a trailing
# subtitle ("## Bottom line — what this establishes"), because a writer
# legitimately wants both. The NAME is what is fixed.
_OPENING_RE = re.compile(
    r"^(#{1,3})\s+(?:\d+[.)]\s*)?" + re.escape(OPENING_HEADING) + r"\b.*$",
    re.MULTILINE | re.IGNORECASE,
)

# The four items, in the order a reader needs them. The label text is the
# contract: bold, exact words, one per item.
OPENING_LABELS = (
    "What was accomplished",
    "What it is worth",
    "What you can do with it now",
    "What is not established",
)

_LABEL_RES = {
    label: re.compile(r"\*\*\s*" + re.escape(label) + r"\b", re.IGNORECASE)
    for label in OPENING_LABELS
}

# "Keep it to one screen." Generous — a terminal screen is ~50 lines and a
# quantified impact item legitimately runs to a few sentences — but bounded, so
# the block cannot silently become the paper again.
MAX_OPENING_LINES = 60

# Item 3 has to be ACTIONABLE, which means naming something a reader can type or
# open. A backtick span (`python evidence/verify.py`, `deliverable/README.md`) is
# the deterministic signature of that; prose promising reproducibility is not.
_ENTRY_POINT_RE = re.compile(r"`[^`\n]{3,}`")

# --------------------------------------------------------------------------
# Navigation.
# --------------------------------------------------------------------------

# "More than about six sections" was the brief. The threshold sits at EIGHT
# because the mandatory skeleton is already eight sections — Bottom line, the six
# skeleton sections, and What a human must still validate — so a threshold of six
# would demand a table of contents of the shortest possible conforming paper, and
# a navigation aid for a document you can see all of at once is noise. Eight means
# navigation is owed by exactly the documents that grew past the standard shape,
# which is the case the brief was about (a 15-section paper with no TOC).
TOC_THRESHOLD = 8
_TOC_HEADING_RE = re.compile(
    r"^#{1,3}\s+(?:\d+[.)]\s*)?(?:contents|table of contents)\b.*$",
    re.MULTILINE | re.IGNORECASE,
)
MIN_TOC_ENTRIES = 3

# Sections APPENDED to a finished paper by machinery that runs after the writer:
# the referee's findings, the build critique, study_paper's own unsupported-claim
# correction, and the salvage notice. They are not the writer's sections and a
# table of contents written at drafting time could not have listed them, so they
# never count toward the navigation threshold — otherwise a paper that linted
# clean when written fails the same lint an hour later, purely because it was
# reviewed. Matched loosely on the leading words, since each carries a subtitle.
_APPENDED_SECTION_RE = re.compile(
    r"^(?:referee findings|build critique|correction\b|structural check\b)",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# The mandatory validate section (predates this module; free_paper and
# study_paper have both written it since Step 22's run-level ancestor).
# --------------------------------------------------------------------------

VALIDATE_HEADING = "What a human must still validate"
_VALIDATE_RE = re.compile(
    r"^#{1,6}\s+" + re.escape(VALIDATE_HEADING) + r"\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# --------------------------------------------------------------------------
# Section skeletons. Both document kinds now produce a SHORT primary document —
# the either/or that produced a design document with no abstract anywhere is
# gone. What differs is the skeleton, not whether there is one.
# --------------------------------------------------------------------------

DOCUMENT_KINDS = ("research", "design")

# (canonical name, accepted heading patterns). Synonyms are accepted because a
# heading is prose and "Background" is a legitimate Introduction; the SECTION is
# what is required, not one blessed spelling.
RESEARCH_SECTIONS = (
    ("Abstract", (r"abstract", r"summary")),
    ("Introduction", (r"introduction", r"background", r"the problem")),
    ("Methods", (r"methods?", r"method and data", r"approach", r"how .*measured",
                 r"what was done")),
    ("Results", (r"results?", r"findings", r"what .*found")),
    ("Conclusions", (r"conclusions?", r"what this means", r"implications?")),
    ("Limitations", (r"limitations?", r"caveats?",
                     r"where this must not be trusted")),
)

DESIGN_SECTIONS = (
    ("Abstract", (r"abstract", r"summary", r"what this is")),
    ("What was built", (r"what was built", r"the design", r"specification",
                        r"the .* specified", r"design")),
    ("How it performs", (r"how it performs", r"performance", r"results?",
                         r"evidence", r"findings")),
    ("How to build it", (r"how to build", r"build it", r"how to run",
                         r"reproduce", r"getting started", r"how to use")),
    ("Limitations", (r"limitations?", r"caveats?",
                     r"where this must not be trusted")),
)

_SKELETONS = {"research": RESEARCH_SECTIONS, "design": DESIGN_SECTIONS}


def _failure(code: str, target: str, message: str) -> dict:
    return {"code": code, "target": target, "message": message}


def section_headings(text: str) -> list:
    """Every level-2 heading, in document order. Level 2 is what "section" means
    here: level 1 is the title and level 3+ are subsections a reader navigates
    from within a section, not from a table of contents."""
    return [m.group(1).strip()
            for m in re.finditer(r"^##\s+(.+?)\s*$", text or "", re.MULTILINE)]


def opening_block(text: str) -> Optional[str]:
    """The text of the opening block: from its heading to the next heading at the
    same or a shallower level. None when there is no opening block. Pure."""
    text = text or ""
    m = _OPENING_RE.search(text)
    if not m:
        return None
    level = len(m.group(1))
    rest = text[m.end():]
    nxt = re.search(r"^#{1," + str(level) + r"}\s+\S", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _label_segment(block: str, label: str) -> str:
    """The text belonging to one opening-block item: from its label to the next
    label (or the end of the block). Pure; empty string when absent."""
    m = _LABEL_RES[label].search(block or "")
    if not m:
        return ""
    rest = block[m.end():]
    ends = [_LABEL_RES[other].search(rest) for other in OPENING_LABELS
            if other != label]
    cuts = [e.start() for e in ends if e]
    return rest[: min(cuts)] if cuts else rest


def _check_opening(text: str, failures: list) -> None:
    block = opening_block(text)
    if block is None:
        failures.append(_failure(
            "opening_missing", OPENING_HEADING,
            f"the document has no '{OPENING_HEADING}' section. Every deliverable "
            f"opens with one, carrying, in this order: "
            + "; ".join(f"**{lab}**" for lab in OPENING_LABELS) + "."))
        return

    # It must be the FIRST section. An opening block a reader has to scroll to is
    # not an opening block — the failure this whole module exists for was content
    # that EXISTED and was misplaced.
    headings = section_headings(text)
    if headings:
        first = headings[0]
        if not re.match(r"^(?:\d+[.)]\s*)?" + re.escape(OPENING_HEADING),
                        first, re.IGNORECASE):
            failures.append(_failure(
                "opening_not_first", OPENING_HEADING,
                f"'{OPENING_HEADING}' must be the FIRST section of the document; "
                f"the first section is '{first}'. A reader must not have to "
                "scroll to learn what was accomplished — NOTHING precedes it, "
                "including a table of contents, which belongs immediately "
                "after."))

    positions = {}
    for label in OPENING_LABELS:
        m = _LABEL_RES[label].search(block)
        if m is None:
            failures.append(_failure(
                "opening_label_missing", label,
                f"the '{OPENING_HEADING}' section is missing the bold label "
                f"**{label}**. All four are mandatory, whatever the goal type."))
        else:
            positions[label] = m.start()

    present = [lab for lab in OPENING_LABELS if lab in positions]
    if len(present) > 1:
        ordered = sorted(present, key=lambda lab: positions[lab])
        if ordered != present:
            failures.append(_failure(
                "opening_labels_out_of_order", OPENING_HEADING,
                "the opening block's items must appear in the order "
                + " -> ".join(OPENING_LABELS)
                + f"; they appear as {' -> '.join(ordered)}."))

    # Item 3 must name something a reader can actually type or open.
    if "What you can do with it now" in positions:
        segment = _label_segment(block, "What you can do with it now")
        if not _ENTRY_POINT_RE.search(segment):
            failures.append(_failure(
                "entry_point_missing", "What you can do with it now",
                "**What you can do with it now** names no concrete entry point. "
                "Give the file to open or the command to type, in backticks — "
                "e.g. `deliverable/README.md` or "
                "`python3 evidence/verify_findings.py`. Prose promising that the "
                "work is reproducible is not an entry point."))

    lines = [ln for ln in block.splitlines() if ln.strip()]
    if len(lines) > MAX_OPENING_LINES:
        failures.append(_failure(
            "opening_too_long", OPENING_HEADING,
            f"the '{OPENING_HEADING}' section is {len(lines)} non-blank lines; it "
            f"must fit one screen ({MAX_OPENING_LINES} at most). Detail belongs "
            "in the body and in the supplement."))


def _check_navigation(text: str, failures: list, *, target: str) -> None:
    headings = section_headings(text)
    body = [h for h in headings
            if not _TOC_HEADING_RE.match("## " + h)
            and not _APPENDED_SECTION_RE.match(h.strip())]
    if len(body) <= TOC_THRESHOLD:
        return
    m = _TOC_HEADING_RE.search(text or "")
    if not m:
        failures.append(_failure(
            "toc_missing", target,
            f"the document has {len(body)} sections and no table of contents. "
            f"Anything over {TOC_THRESHOLD} sections carries a '## Contents' "
            "section listing them, near the top."))
        return
    rest = (text or "")[m.end():]
    nxt = re.search(r"^#{1,2}\s+\S", rest, re.MULTILINE)
    toc_body = rest[: nxt.start()] if nxt else rest
    entries = [ln for ln in toc_body.splitlines()
               if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+\S", ln)]
    if len(entries) < MIN_TOC_ENTRIES:
        failures.append(_failure(
            "toc_empty", target,
            f"the table of contents lists {len(entries)} entr(y/ies); it must "
            f"list the document's sections (at least {MIN_TOC_ENTRIES})."))


def _check_skeleton(text: str, kind: str, failures: list) -> None:
    if kind not in _SKELETONS:
        failures.append(_failure(
            "document_kind_invalid", "document_kind",
            f"document_kind must be exactly one of {' | '.join(DOCUMENT_KINDS)}; "
            f"got {kind!r}."))
        return
    headings = section_headings(text)
    lowered = [h.lower() for h in headings]
    for canonical, patterns in _SKELETONS[kind]:
        hit = any(
            re.match(r"^(?:\d+[.)]\s*)?(?:" + "|".join(patterns) + r")\b", h)
            for h in lowered
        )
        if not hit:
            failures.append(_failure(
                "section_missing", canonical,
                f"a {kind} document needs a '{canonical}' section; none of its "
                f"headings match. Sections found: {_summarize(headings)}."))


def _summarize(headings: list) -> str:
    """The document's headings, short enough to repeat in every message. A
    15-section paper misses several sections at once, and printing the full list
    each time buries the one word a reader needs."""
    if not headings:
        return "(none)"
    short = [(h[:40] + "...") if len(h) > 43 else h for h in headings[:12]]
    if len(headings) > 12:
        short.append(f"...and {len(headings) - 12} more")
    return ", ".join(short)


def _check_validate_section(text: str, failures: list) -> None:
    if not _VALIDATE_RE.search(text or ""):
        failures.append(_failure(
            "validate_section_missing", VALIDATE_HEADING,
            f"the document is missing the mandatory heading "
            f"'{VALIDATE_HEADING}' — one bullet per claim or assumption a human "
            "must check before trusting this."))


def infer_document_kind(text: str) -> str:
    """Which skeleton this document is closest to, for linting a paper whose
    writer's declared kind was not recorded (an older study, or a hand-audited
    one). Whichever skeleton it satisfies BETTER is the one it is held to — a
    tie goes to "research", the more demanding of the two. Pure, never raises."""
    scores = {}
    for kind in DOCUMENT_KINDS:
        misses: list = []
        _check_skeleton(text or "", kind, misses)
        scores[kind] = len(misses)
    return "design" if scores["design"] < scores["research"] else "research"


def lint_study_paper(text: str, document_kind: str = "research") -> list:
    """Lint the PRIMARY document (paper.md): opening block, navigation, section
    skeleton for its declared kind, and the mandatory validate section.

    Returns the machine-readable failure list; empty = clean. Pure, never raises.
    """
    failures: list = []
    if not (text or "").strip():
        return [_failure("paper_empty", "paper", "the paper is empty.")]
    _check_opening(text, failures)
    _check_navigation(text, failures, target="paper")
    _check_skeleton(text, str(document_kind or ""), failures)
    _check_validate_section(text, failures)
    return failures


def lint_study_supplement(text: str) -> list:
    """Lint the SUPPLEMENT (report.md): the long one. It carries the arc
    narrative, the full specification, per-phase detail and the artifact
    inventory, and it may be as long as it needs to be — so the only shape it
    owes a reader is navigation, plus enough substance to be worth opening."""
    failures: list = []
    if not (text or "").strip():
        return [_failure("supplement_empty", "supplement",
                         "the supplement is empty.")]
    _check_navigation(text, failures, target="supplement")
    if len(section_headings(text)) < 2:
        failures.append(_failure(
            "supplement_thin", "supplement",
            "the supplement has fewer than two sections. It carries the arc "
            "narrative, the full specification, the per-phase detail and the "
            "artifact inventory — everything the short paper leaves out."))
    return failures


def lint_study_dir(study_dir: Any, document_kind: str = "research") -> list:
    """Lint a finished study's deliverable documents on disk: <dir>/paper.md and
    <dir>/report.md. Never raises — an unreadable file becomes a failure."""
    d = Path(study_dir)
    failures: list = []
    for name, linter, target in (("paper.md", lambda t: lint_study_paper(t, document_kind), "paper"),
                                 ("report.md", lint_study_supplement, "supplement")):
        path = d / name
        if not path.is_file():
            failures.append(_failure(
                f"{target}_missing", target,
                f"no {target} at {path}. A study writes BOTH: paper.md is the "
                "short readable document, report.md the supplement carrying the "
                "arc, the full specification and the artifact inventory."))
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            failures.append(_failure(
                f"{target}_unreadable", target,
                f"{path} could not be read: {str(e).splitlines()[0]}"))
            continue
        failures.extend(linter(text))
    return failures


def lint_errors_as_text(failures: list) -> list:
    """The failure list rendered as the plain-language error strings
    call_stage_model re-asks with. Keeps the writer's correction loop reading
    like every other validator in the system."""
    return [f"{f['message']}" for f in failures]


# --------------------------------------------------------------------------
# Surfacing the deliverable's own entry point (item 3), deterministically.
# --------------------------------------------------------------------------

def insert_entry_point_pointer(text: str, pointer_line: str) -> str:
    """Append `pointer_line` to the opening block's **What you can do with it
    now** item, so the packaged deliverable's Reproduce section is surfaced where
    a reader looks first rather than living in a file the paper never mentions.

    Written in Python, not by a model, because it is a statement about what the
    packaging step actually wrote. Returns the text UNCHANGED when there is no
    opening block, no item 3, or the pointer is already there — a pointer to
    something that might not exist is worse than none. Pure, never raises."""
    try:
        block = opening_block(text or "")
        if block is None:
            return text
        segment = _label_segment(block, "What you can do with it now")
        if not segment.strip() or pointer_line.strip() in text:
            return text
        # Anchor on the segment's own text so the insert lands at the END of item
        # 3 and nowhere else, whatever the surrounding formatting.
        idx = text.find(segment)
        if idx < 0:
            return text
        cut = idx + len(segment.rstrip())
        return text[:cut] + " " + pointer_line.strip() + text[cut:]
    except Exception:  # noqa: BLE001 — a pointer is a courtesy, never a failure
        return text
