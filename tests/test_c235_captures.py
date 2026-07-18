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

  C2 — chooser retry (attempt-2) user-turn, including the envelope-error
       text. The Phase-1 capture used a canned attempt-1 reply carrying a
       "substrate_id" field, which the PRE-23.5 envelope forbade — the
       preserved fixture chooser_retry_user_turn.txt holds the exact
       before-state sentence ('reply with exactly "ack_run_id",
       "chosen_id", and "reasoning"').
       CONTAINMENT CLASS: documented the BEFORE-state only; SUPERSEDED in
       Phase 2 under R-23.5-1 (truth-edit itemized in the Phase-2 commit):
       that reply is now the VALID envelope shape, so it composes no retry
       — the flip is asserted directly, the superseded fixture stays
       append-only as history, and the post-23.5 retry surface (an
       enrolled-but-UNROUTABLE substrate_id, one validator error) is
       birth-fixtured as chooser_retry_user_turn_v235.txt.

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


class C2ChooserRetrySuperseded(unittest.TestCase):
    """C2's Phase-1 role, post-supersession (R-23.5-1, truth-edited in
    Phase 2; each proof kept with a post-flip subject): the preserved
    fixture is read-only history of the before-state, and the before-state
    reply is asserted to be the NEW valid envelope shape — the flip
    documented from both sides."""

    def test_superseded_fixture_preserved_with_before_state_error(self):
        # Append-only history: the Phase-1 fixture still carries the exact
        # pre-23.5 envelope-error sentence. Read-only — never re-derived.
        validation_error = json.loads(_fixture("chooser_retry_user_turn.txt"))[
            "validation_error"
        ]
        self.assertIn(
            "reply field 'substrate_id' is not allowed — reply with exactly "
            '"ack_run_id", "chosen_id", and "reasoning", nothing else.',
            validation_error,
        )
        self.assertEqual(validation_error.count(" (raw reply: "), 1)

    def test_original_input_matches_c1_pinned_user_turn(self):
        # Cross-family coherence, the d3 pattern: the preserved retry
        # surface embeds the SAME assembled stage_input C1 pins — and C1 is
        # a whole-build containment tripwire, so this holds post-change too.
        parsed = json.loads(_fixture("chooser_retry_user_turn.txt"))
        self.assertEqual(
            json.dumps(parsed["original_input"]),
            _fixture("chooser_attempt1_user_turn.txt"),
        )

    def test_before_state_reply_is_now_the_valid_envelope(self):
        # THE FLIP, asserted directly: the reply the pre-23.5 validator
        # rejected (extra substrate_id field) is exactly the post-23.5
        # valid shape — routable substrate_id and all four fields.
        reply = json.loads(_fixture("chooser_reply_substrate_id_field.json"))
        validator = g1c.make_choice_validator({"h1", "h2"})
        self.assertEqual(validator(reply), [])


class C2bChooserRetryBirth(unittest.TestCase):
    """Birth pin of the post-23.5 chooser retry surface (R-23.5-1): an
    enrolled-but-UNROUTABLE substrate_id draws the new envelope-error text
    from the LIVE registry read — exactly one validator error."""

    def test_retry_user_turn_byte_identical_to_birth_fixture(self):
        system_prompt, user_turn = compose_chooser_retry(
            _fixture("chooser_reply_unroutable_substrate.json")
        )
        self.assertEqual(user_turn, _fixture("chooser_retry_user_turn_v235.txt"))
        # the attempt-2 system prompt IS the composed chooser prompt — its
        # base text is rwin1's chooser.txt pin; identity of composition here.
        self.assertEqual(system_prompt, g1c.compose_chooser_prompt())

    def test_composition_is_deterministic(self):
        reply = _fixture("chooser_reply_unroutable_substrate.json")
        self.assertEqual(
            compose_chooser_retry(reply), compose_chooser_retry(reply)
        )

    def test_original_input_matches_c1_pinned_user_turn(self):
        parsed = json.loads(_fixture("chooser_retry_user_turn_v235.txt"))
        self.assertEqual(
            json.dumps(parsed["original_input"]),
            _fixture("chooser_attempt1_user_turn.txt"),
        )

    def test_carries_exactly_the_new_envelope_error(self):
        validation_error = json.loads(
            _fixture("chooser_retry_user_turn_v235.txt")
        )["validation_error"]
        self.assertIn(
            "substrate_id must be exactly one of "
            "['cavity_2d_cfd', 'sympy_symbolic_exact', "
            "'ngspice_linear_passive']; got 'web_search'.",
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


NGSPICE_RETRY_CLASSES = ("bad_kind", "bad_target", "bad_reduction", "alien_keys")

NGSPICE_RETRY_PERTURBATIONS = {
    "bad_kind": {"kind": "voltage_node"},
    "bad_target": {"target": "out node!"},
    "bad_reduction": {"reduction": "average"},
    "alien_keys": {"operation": "volAverage"},
}


def _ngspice_reply_with(perturb: dict) -> str:
    """The known-valid full ngspice spec (frozen at
    tests/fixtures/c235/ngspice_full_spec.json) with exactly ONE qoi
    perturbation, wrapped in the stage-2 reply envelope — so each captured
    validation_error carries exactly one validator error string (the d3
    one-perturbation discipline)."""
    spec = json.loads(_fixture("ngspice_full_spec.json"))
    spec["qoi"].update(perturb)
    return json.dumps(
        {"ack_run_id": "c235-canned-ngspice", "spec": spec}, indent=2
    )


def compose_stage2_retry(baton_fixture: str, reply_text: str) -> tuple[str, str]:
    """Drive the REAL stage-2 re-ask composition on a c235 canned baton (the
    d3 pattern): transport patched so attempt 1 returns `reply_text` and
    attempt 2 captures the exact (system_prompt, user_turn) pair."""
    baton = Baton.from_json(_fixture(baton_fixture))
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
    tmp = tempfile.mkdtemp(prefix="c235_s2retry_")
    try:
        os.chdir(tmp)
        with patch.dict(os.environ, {"BLANK_MEMORY": "1"}):
            with patch.object(
                model_call, "_transport_with_retry", side_effect=_transport
            ):
                try:
                    s2.run(baton)
                except _Captured:
                    pass
                else:
                    raise AssertionError(
                        "attempt 2 was never reached — the canned reply did "
                        "not trigger a re-ask"
                    )
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    return captured["system_prompt"], captured["user_turn"]


class C5NgspiceStage2Birth(unittest.TestCase):
    """Phase-3b birth pin: stage 2's composition on an ngspice-routed
    post-gate-1 payload — the NEW model-visible surface the 3a un-pin
    creates. The injected contract IS the graduated registry constant;
    substrate_id still enters no composed prompt (R-23.5-4)."""

    def test_user_turn_byte_identical_to_birth_fixture(self):
        _, user_turn = assemble_stage2_variant(
            "canned_stage2_input_ngspice.json", hermetic_journal=False
        )
        self.assertEqual(user_turn, _fixture("stage2_user_turn_ngspice.txt"))

    def test_contract_is_the_ngspice_constant_and_no_substrate_id_leak(self):
        from substrates import NGSPICE_LINEAR_PASSIVE_CONTRACT

        system_prompt, user_turn = assemble_stage2_variant(
            "canned_stage2_input_ngspice.json", hermetic_journal=False
        )
        parsed = json.loads(user_turn)
        self.assertEqual(
            parsed["substrate_contract"], NGSPICE_LINEAR_PASSIVE_CONTRACT
        )
        self.assertNotIn("substrate_id", parsed)
        self.assertIs(system_prompt, s2.SYSTEM_PROMPT)

    def test_assembly_is_deterministic(self):
        self.assertEqual(
            assemble_stage2_variant("canned_stage2_input_ngspice.json", False),
            assemble_stage2_variant("canned_stage2_input_ngspice.json", False),
        )

    def test_canned_baton_is_canonical_post_gate1_shape(self):
        from schemas import validate_payload_post_gate1

        baton = json.loads(_fixture("canned_stage2_input_ngspice.json"))
        self.assertEqual(validate_payload_post_gate1(baton["payload"]), [])


class C6NgspiceRetryBirth(unittest.TestCase):
    """Phase-3b birth pins: the ngspice-class stage-2 retry rejection
    shapes — validate_spec running the NGSPICE vocabulary inside the real
    re-ask loop (d3's cavity four are untouched; this is the new class).
    One perturbation per canned reply = exactly one validator error."""

    def _check_class(self, cls: str) -> None:
        system_prompt, user_turn = compose_stage2_retry(
            "canned_stage2_input_ngspice.json",
            _fixture(f"ngspice_reply_{cls}.json"),
        )
        self.assertEqual(user_turn, _fixture(f"ngspice_retry_{cls}.txt"))
        self.assertIs(system_prompt, s2.SYSTEM_PROMPT)

    def test_bad_kind_retry_byte_identical(self):
        self._check_class("bad_kind")

    def test_bad_target_retry_byte_identical(self):
        self._check_class("bad_target")

    def test_bad_reduction_retry_byte_identical(self):
        self._check_class("bad_reduction")

    def test_alien_keys_retry_byte_identical(self):
        self._check_class("alien_keys")

    def test_each_class_carries_exactly_one_validator_error(self):
        markers = {
            "bad_kind": "qoi kind must be one of",
            "bad_target": "qoi target must be the exact name",
            "bad_reduction": "qoi reduction must be one of",
            "alien_keys": "belong to a different substrate class's QoI grammar",
        }
        for cls, marker in markers.items():
            validation_error = json.loads(
                _fixture(f"ngspice_retry_{cls}.txt")
            )["validation_error"]
            self.assertIn(marker, validation_error)
            self.assertEqual(validation_error.count(" (raw reply: "), 1)

    def test_original_input_matches_c5_pinned_user_turn(self):
        for cls in NGSPICE_RETRY_CLASSES:
            parsed = json.loads(_fixture(f"ngspice_retry_{cls}.txt"))
            self.assertEqual(
                json.dumps(parsed["original_input"]),
                _fixture("stage2_user_turn_ngspice.txt"),
            )


def capture() -> None:
    """Write the four captured-surface fixtures from the CURRENT tree's
    composition (the canned INPUT fixtures are hand-authored and never
    regenerated here)."""
    FIX.mkdir(parents=True, exist_ok=True)

    _, c1 = assemble_chooser_attempt1()
    (FIX / "chooser_attempt1_user_turn.txt").write_text(c1)
    print(f"captured C1 chooser attempt-1 user turn: {len(c1)} bytes")

    # C2 (chooser_retry_user_turn.txt) is SUPERSEDED history (R-23.5-1,
    # Phase 2): frozen append-only, never regenerated. Its successor is the
    # post-23.5 birth capture below.
    _, c2b = compose_chooser_retry(
        _fixture("chooser_reply_unroutable_substrate.json")
    )
    (FIX / "chooser_retry_user_turn_v235.txt").write_text(c2b)
    print(f"captured C2b chooser retry user turn (v235): {len(c2b)} bytes")

    _, c3 = assemble_stage2_variant("canned_stage2_input_lessons.json", True)
    (FIX / "stage2_user_turn_lessons.txt").write_text(c3)
    print(f"captured C3 stage-2 lessons user turn: {len(c3)} bytes")

    _, c4 = assemble_stage2_variant("canned_stage2_input_prior_thought.json", False)
    (FIX / "stage2_user_turn_prior_thought.txt").write_text(c4)
    print(f"captured C4 stage-2 prior-thought user turn: {len(c4)} bytes")

    # Phase-3b birth captures (Step 23.5): the ngspice stage-2 surface.
    _, c5 = assemble_stage2_variant("canned_stage2_input_ngspice.json", False)
    (FIX / "stage2_user_turn_ngspice.txt").write_text(c5)
    print(f"captured C5 stage-2 ngspice user turn: {len(c5)} bytes")

    for cls, perturb in NGSPICE_RETRY_PERTURBATIONS.items():
        reply = _ngspice_reply_with(perturb)
        (FIX / f"ngspice_reply_{cls}.json").write_text(reply)
        _, user_turn = compose_stage2_retry(
            "canned_stage2_input_ngspice.json", reply
        )
        (FIX / f"ngspice_retry_{cls}.txt").write_text(user_turn)
        print(f"captured C6 ngspice retry {cls}: {len(user_turn)} bytes")


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture()
    else:
        unittest.main()
