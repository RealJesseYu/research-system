"""
test_c235_captures.py — Step 23.5 Phase-1 captures (captured at 2510a97,
whose parent e9084af is the era-of-record; zero production changes in the
capture commit — the git order is the capture-before-touch proof).

ZERO live model calls. Four model-visible surfaces byte-pinned BEFORE the
Step-23.5 instrument-selection build touches anything, following the
rwin1/d1/d3 fixture discipline (fixture file + byte-identity test):

  C1 — chooser attempt-1 user-turn: the exact json.dumps(stage_input)
       call_stage_model hands the transport, driven through the REAL
       gate1_chooser.choose_hypothesis on canned hypotheses + canned stage1
       evidence files (tournament_state / survivors / research_overview).
       CONTAINMENT CLASS: must stay byte-identical through the ENTIRE
       Step-23.5 build — an era containment tripwire. R-23.5-1 confines the
       chooser era move to instruction text + retry-path envelope-error
       text; the composed stage_input rendering is NOT licensed to move.

  C2 — chooser retry (attempt-2) user-turn, including the CURRENT
       envelope-error text. The canned attempt-1 reply carries a
       "substrate_id" field, which TODAY'S envelope forbids — so the
       captured validation_error holds the exact before-state sentence
       ('reply with exactly "ack_run_id", "chosen_id", and "reasoning"').
       CONTAINMENT CLASS: documents the BEFORE-state only; superseded
       during Phase 2 under R-23.5-1 — this fixture is preserved
       append-only and the post-change retry bytes get a birth fixture of
       their own.

  C3 — stage-2 composed user-turn, lessons-block-present variant: the d1
       family pinned the lessons-absent shape (BLANK_MEMORY); this pins the
       block-present shape on a hermetic canned journal (JOURNAL_PATH swap,
       the test_memory_reach pattern).
       CONTAINMENT CLASS: must stay byte-identical through the ENTIRE
       build.

  C4 — stage-2 composed user-turn, prior-thought-present variant (the
       Step-16 loop-back re-entry shape the d1 family pinned as null).
       CONTAINMENT CLASS: must stay byte-identical through the ENTIRE
       build.

Canned-baton shape (owner-ruled at the Step-23.5 d1/C3-C4 shape STOP): the
C3/C4 canned post-gate-1 payloads carry substrate_id "cavity_2d_cfd" FROM
BIRTH — the R-23.5-4 canned three-key shape for a cavity-twin input, NOT a
runtime default (R-23.5-2 untouched). Today's stage 2 ignores the key;
after Phase 3a it selects the contract fetch — contract_for("cavity_2d_cfd")
IS substrates.CAVITY_2D_CONTRACT (assertIs on disk in
test_contract_registry), so the composed bytes hold either way. R-23.5-4
also rules that substrate_id enters NO composed prompt anywhere — asserted
here as the no-prompt-entry tripwire.

call_stage_model is intercepted at the chooser's / stage 2's import site
(C1, C3, C4) or at model_call._transport_with_retry (C2, the d3 pattern);
every capture raises before any transport, so no model is called.

Regenerate fixtures (only ever legitimately run on the pre-change tree, or
to prove post-change byte-identity by diff):
    venv/bin/python3 tests/test_c235_captures.py --capture
Run as tests: venv/bin/python3 tests/test_c235_captures.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
from baton import Baton
from memory import journal
from stages import gate1_chooser as g1c
from stages import stage2_experiment_design as s2

FIX = Path(__file__).resolve().parent / "fixtures" / "c235"

CHOOSER_STAGE1_FILES = (
    "tournament_state.json",
    "survivors.json",
    "research_overview.json",
)


class _Captured(Exception):
    """Raised by a capture stub so the driven code stops right after the
    model-visible surface is in hand."""


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


def _canned_chooser() -> tuple[str, list]:
    canned = json.loads(_fixture("canned_chooser_hypotheses.json"))
    return canned["run_id"], canned["hypotheses"]


def _materialize_chooser_run(run_id: str) -> Path:
    """Copy the canned stage1 evidence files into runs/<run_id>/stage1 under
    the CURRENT (temporary) cwd; return the run dir."""
    run_dir = Path("runs") / run_id
    (run_dir / "stage1").mkdir(parents=True)
    for name in CHOOSER_STAGE1_FILES:
        shutil.copy(FIX / "canned_chooser_stage1" / name, run_dir / "stage1" / name)
    return run_dir


def assemble_chooser_attempt1() -> tuple[str, str]:
    """Drive the real chooser on the canned inputs; return the exact
    model-visible pair (system_prompt, attempt-1 user_turn). The capture stub
    raises inside choose_hypothesis, which by contract swallows it into the
    rank-1 fallback record — the captured pair is already in hand."""
    run_id, hypotheses = _canned_chooser()
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="c235_chooser1_")
    try:
        os.chdir(tmp)
        run_dir = _materialize_chooser_run(run_id)
        with patch.object(g1c, "call_stage_model", side_effect=_capture):
            g1c.choose_hypothesis(run_id, hypotheses, run_dir)
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    if "stage_input" not in captured:
        raise AssertionError(
            "call_stage_model was never reached — chooser assembly did not run"
        )
    return captured["system_prompt"], json.dumps(captured["stage_input"])


def compose_chooser_retry(reply_text: str) -> tuple[str, str]:
    """Drive the REAL chooser re-ask composition: transport patched so
    attempt 1 returns `reply_text` and attempt 2 captures the exact
    (system_prompt, user_turn) pair the model would see (the d3 pattern)."""
    run_id, hypotheses = _canned_chooser()
    captured: dict = {}
    calls = {"n": 0}

    def _transport(stage_name, stage_input, system_prompt, user_turn, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return reply_text
        captured["system_prompt"] = system_prompt
        captured["user_turn"] = user_turn
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="c235_chooser2_")
    try:
        os.chdir(tmp)
        run_dir = _materialize_chooser_run(run_id)
        with patch.object(
            model_call, "_transport_with_retry", side_effect=_transport
        ):
            g1c.choose_hypothesis(run_id, hypotheses, run_dir)
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    if "user_turn" not in captured:
        raise AssertionError(
            "attempt 2 was never reached — the canned reply did not trigger "
            "a re-ask"
        )
    return captured["system_prompt"], captured["user_turn"]


def assemble_stage2_variant(baton_fixture: str, hermetic_journal: bool) -> tuple[str, str]:
    """Drive the real stage-2 assembly on a c235 canned baton; return the
    exact model-visible pair (system_prompt, user_turn). hermetic_journal
    swaps memory.journal.JOURNAL_PATH for the canned journal (lessons
    PRESENT); otherwise BLANK_MEMORY=1 keeps the lessons block absent."""
    baton = Baton.from_json(_fixture(baton_fixture))
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="c235_stage2_")
    old_journal = journal.JOURNAL_PATH
    env = {"BLANK_MEMORY": "0"} if hermetic_journal else {"BLANK_MEMORY": "1"}
    try:
        os.chdir(tmp)
        if hermetic_journal:
            journal.JOURNAL_PATH = FIX / "canned_journal.jsonl"
        with patch.dict(os.environ, env):
            with patch.object(s2, "call_stage_model", side_effect=_capture):
                try:
                    s2.run(baton)
                except _Captured:
                    pass
                else:
                    raise AssertionError(
                        "call_stage_model was never reached — assembly did not run"
                    )
    finally:
        journal.JOURNAL_PATH = old_journal
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    return captured["system_prompt"], json.dumps(captured["stage_input"])


class C1ChooserAttempt1ByteIdentity(unittest.TestCase):
    """C1 containment tripwire: byte-identical through the ENTIRE build."""

    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_chooser_attempt1()
        self.assertEqual(user_turn, _fixture("chooser_attempt1_user_turn.txt"))

    def test_assembly_is_deterministic(self):
        self.assertEqual(
            assemble_chooser_attempt1(), assemble_chooser_attempt1()
        )

    def test_evidence_sections_entered_the_input(self):
        _, user_turn = assemble_chooser_attempt1()
        parsed = json.loads(user_turn)
        self.assertEqual(len(parsed["ranked_hypotheses"]), 2)
        self.assertEqual(
            [e["id"] for e in parsed["elo_table"]], ["h1", "h2"]
        )
        self.assertEqual(
            sorted(parsed["addressable_notes"]), ["h1", "h2"]
        )
        self.assertEqual(len(parsed["research_overview_directions"]), 1)


class C2ChooserRetryByteIdentity(unittest.TestCase):
    """C2 documents the BEFORE-state envelope-error text; superseded during
    Phase 2 under R-23.5-1 (this fixture preserved append-only, post-change
    bytes birth-fixtured separately)."""

    def test_retry_user_turn_byte_identical_to_fixture(self):
        system_prompt, user_turn = compose_chooser_retry(
            _fixture("chooser_reply_substrate_id_field.json")
        )
        self.assertEqual(user_turn, _fixture("chooser_retry_user_turn.txt"))
        # the attempt-2 system prompt IS the composed chooser prompt — its
        # base text is rwin1's chooser.txt pin; identity of composition here.
        self.assertEqual(system_prompt, g1c.compose_chooser_prompt())

    def test_composition_is_deterministic(self):
        reply = _fixture("chooser_reply_substrate_id_field.json")
        self.assertEqual(
            compose_chooser_retry(reply), compose_chooser_retry(reply)
        )

    def test_original_input_matches_c1_pinned_user_turn(self):
        # Cross-family coherence, the d3 pattern: the retry surface embeds
        # the SAME assembled stage_input C1 pinned as the attempt-1 user_turn.
        parsed = json.loads(_fixture("chooser_retry_user_turn.txt"))
        self.assertEqual(
            json.dumps(parsed["original_input"]),
            _fixture("chooser_attempt1_user_turn.txt"),
        )

    def test_carries_exactly_the_current_envelope_error(self):
        validation_error = json.loads(_fixture("chooser_retry_user_turn.txt"))[
            "validation_error"
        ]
        self.assertIn(
            "reply field 'substrate_id' is not allowed — reply with exactly "
            '"ack_run_id", "chosen_id", and "reasoning", nothing else.',
            validation_error,
        )
        self.assertEqual(validation_error.count(" (raw reply: "), 1)


class C3Stage2LessonsByteIdentity(unittest.TestCase):
    """C3 containment tripwire: byte-identical through the ENTIRE build."""

    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_stage2_variant(
            "canned_stage2_input_lessons.json", hermetic_journal=True
        )
        self.assertEqual(user_turn, _fixture("stage2_user_turn_lessons.txt"))

    def test_assembly_is_deterministic(self):
        self.assertEqual(
            assemble_stage2_variant("canned_stage2_input_lessons.json", True),
            assemble_stage2_variant("canned_stage2_input_lessons.json", True),
        )

    def test_lessons_block_present_and_filtered(self):
        _, user_turn = assemble_stage2_variant(
            "canned_stage2_input_lessons.json", hermetic_journal=True
        )
        parsed = json.loads(user_turn)
        block = parsed["substrate_capability_lessons"]
        self.assertTrue(block.startswith(s2.LESSONS_HEADER))
        self.assertEqual(block.count("C235 CANNED lesson"), 3)
        self.assertNotIn("decoy", block)  # the kind filter held

    def test_substrate_id_enters_no_composed_prompt(self):
        # R-23.5-4 no-prompt-entry tripwire: the canned payload carries
        # substrate_id, the composed model input must not.
        system_prompt, user_turn = assemble_stage2_variant(
            "canned_stage2_input_lessons.json", hermetic_journal=True
        )
        self.assertNotIn("substrate_id", json.loads(user_turn))
        self.assertNotIn("substrate_id", system_prompt)

    def test_canned_baton_carries_the_ruled_three_key_shape(self):
        payload = json.loads(_fixture("canned_stage2_input_lessons.json"))["payload"]
        self.assertEqual(
            set(payload), {"domain", "chosen_hypothesis", "substrate_id"}
        )
        self.assertEqual(payload["substrate_id"], "cavity_2d_cfd")


class C4Stage2PriorThoughtByteIdentity(unittest.TestCase):
    """C4 containment tripwire: byte-identical through the ENTIRE build."""

    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_stage2_variant(
            "canned_stage2_input_prior_thought.json", hermetic_journal=False
        )
        self.assertEqual(
            user_turn, _fixture("stage2_user_turn_prior_thought.txt")
        )

    def test_assembly_is_deterministic(self):
        self.assertEqual(
            assemble_stage2_variant("canned_stage2_input_prior_thought.json", False),
            assemble_stage2_variant("canned_stage2_input_prior_thought.json", False),
        )

    def test_prior_thought_entered_the_input_verbatim(self):
        _, user_turn = assemble_stage2_variant(
            "canned_stage2_input_prior_thought.json", hermetic_journal=False
        )
        parsed = json.loads(user_turn)
        canned = json.loads(_fixture("canned_stage2_input_prior_thought.json"))
        self.assertEqual(
            parsed["prior_thought"], canned["payload"]["prior_thought"]
        )

    def test_substrate_id_enters_no_composed_prompt(self):
        system_prompt, user_turn = assemble_stage2_variant(
            "canned_stage2_input_prior_thought.json", hermetic_journal=False
        )
        self.assertNotIn("substrate_id", json.loads(user_turn))
        self.assertNotIn("substrate_id", system_prompt)


def capture() -> None:
    """Write the four captured-surface fixtures from the CURRENT tree's
    composition (the canned INPUT fixtures are hand-authored and never
    regenerated here)."""
    FIX.mkdir(parents=True, exist_ok=True)

    _, c1 = assemble_chooser_attempt1()
    (FIX / "chooser_attempt1_user_turn.txt").write_text(c1)
    print(f"captured C1 chooser attempt-1 user turn: {len(c1)} bytes")

    _, c2 = compose_chooser_retry(_fixture("chooser_reply_substrate_id_field.json"))
    (FIX / "chooser_retry_user_turn.txt").write_text(c2)
    print(f"captured C2 chooser retry user turn: {len(c2)} bytes")

    _, c3 = assemble_stage2_variant("canned_stage2_input_lessons.json", True)
    (FIX / "stage2_user_turn_lessons.txt").write_text(c3)
    print(f"captured C3 stage-2 lessons user turn: {len(c3)} bytes")

    _, c4 = assemble_stage2_variant("canned_stage2_input_prior_thought.json", False)
    (FIX / "stage2_user_turn_prior_thought.txt").write_text(c4)
    print(f"captured C4 stage-2 prior-thought user turn: {len(c4)} bytes")


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture()
    else:
        unittest.main()
