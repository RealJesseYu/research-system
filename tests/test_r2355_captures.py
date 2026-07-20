"""
test_r2355_captures.py — R-23.5-5 Phase-1 captures (era 3ce383c, pre-change).

ZERO live model calls: the two census surfaces the R-23.5-5 build touches
that no existing fixture pinned, captured at CURRENT bytes before any
production edit:

  1. THE CAVITY REGIME-REJECTION RETRY SURFACE (d3 mechanics). The d3
     family pins the four QoI rejection classes (operation / component /
     mask / field) but no regime class, and R-23.5-5 requires cavity's
     regime validation behavior and rejection text to stay byte-equal
     while _validate_regime moves behind the per-substrate vocabulary.
     reply_bad_regime.json (ordering violation, reynolds_min 300 > max
     200) -> retry_bad_regime.txt, the exact attempt-2 user turn.
     CONTAINMENT CLASS: cavity content — INVIOLABLE for the whole build.

  2. THE FOUR _validate_regime ERROR STRINGS, exact-equality pinned (a
     substring assert is a check that cannot fail against a reworded
     string). CONTAINMENT CLASS: cavity content — INVIOLABLE.

  3. THE STAGE-5 NGSPICE COMPOSED INPUT (d0 mechanics) — the 0d census's
     registered suspect, confirmed UNPINNED: no ngspice stage-5 fixture
     existed. Captured on a canned circuit baton carrying the CURRENT
     c235 placeholder spec (tests/fixtures/c235/ngspice_full_spec.json),
     proving the spec — placeholder regime included — enters stage 5's
     user turn verbatim. CONTAINMENT CLASS: carries the placeholder
     circuit regime — SUPERSEDED at Phase 3c under R-23.5-5 (original
     preserved append-only), unlike the cavity captures above.

Run directly: venv/bin/python3 tests/test_r2355_captures.py
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
from schemas import validate_payload_post_stage4
from stages import stage2_experiment_design as s2
from stages import stage5_thought_layer as s5
from stages.stage2_spec import validate_spec
from tools.qoi_vocab import vocab_for

FIX = Path(__file__).resolve().parent / "fixtures" / "r2355"
D1_FIX = Path(__file__).resolve().parent / "fixtures" / "d1"
C235_FIX = Path(__file__).resolve().parent / "fixtures" / "c235"

CHOSEN_ID = "hand-baseline"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


class _Captured(Exception):
    """Raised by the capture stub so run() stops right after assembly."""


def compose_retry_surface(reply_text: str) -> tuple[str, str]:
    """Drive the REAL re-ask composition (d3 mechanics): stage 2's run() on
    the d1 canned baton, transport patched so attempt 1 returns `reply_text`
    and attempt 2 captures the exact (system_prompt, user_turn) pair."""
    baton = Baton.from_json((D1_FIX / "canned_stage2_input.json").read_text())
    captured: dict = {}
    calls = {"n": 0}

    def _transport(stage_name, stage_input, system_prompt, user_turn, model, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return reply_text
        captured["system_prompt"] = system_prompt
        captured["user_turn"] = user_turn
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="r2355_retry_")
    try:
        os.chdir(tmp)  # run() writes runs/<id>/ relative to cwd
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


def assemble_stage5_input() -> tuple[str, str]:
    """Drive the REAL stage-5 assembly (d0 mechanics) on the canned ngspice
    baton; return the exact model-visible (system_prompt, user_turn) pair."""
    baton = Baton.from_json(_fixture("canned_stage5_input_ngspice.json"))
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="r2355_stage5_")
    try:
        stage4_dir = Path(tmp) / "runs" / baton.run_id / "stage4"
        stage4_dir.mkdir(parents=True)
        shutil.copyfile(
            FIX / "canned_stage4_results_ngspice.json",
            stage4_dir / "results.json",
        )
        os.chdir(tmp)  # _load_stage4_summaries reads runs/<id>/ relative to cwd
        with patch.object(s5, "call_stage_model", side_effect=_capture):
            try:
                s5.run(baton)
            except _Captured:
                pass
            else:
                raise AssertionError(
                    "call_stage_model was never reached — assembly did not run"
                )
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    return captured["system_prompt"], json.dumps(captured["stage_input"])


def _valid_cavity_spec() -> dict:
    """The d1-family valid cavity spec, recovered from reply_bad_regime.json
    with its deliberate regime break healed."""
    spec = json.loads(_fixture("reply_bad_regime.json"))["spec"]
    spec["regime"]["reynolds_min"] = 100
    return spec


class CavityRegimeRetryByteIdentity(unittest.TestCase):
    """Capture 1: the regime-rejection retry user turn, byte-pinned."""

    def test_bad_regime_retry_byte_identical(self):
        system_prompt, user_turn = compose_retry_surface(
            _fixture("reply_bad_regime.json")
        )
        self.assertEqual(user_turn, _fixture("retry_bad_regime.txt"))
        self.assertIs(system_prompt, s2.SYSTEM_PROMPT)

    def test_retry_carries_the_exact_ordering_error(self):
        self.assertIn(
            "regime must satisfy 0 < reynolds_min <= reynolds_max; "
            "got reynolds_min=300 and reynolds_max=200.",
            _fixture("retry_bad_regime.txt"),
        )


class CavityRegimeRejectionStrings(unittest.TestCase):
    """Capture 2: the four _validate_regime error strings, exact equality.
    vocab is passed explicitly (the cavity record) so these pins are
    insensitive to the R-23.5-5a default removal."""

    def _regime_errors(self, regime) -> list[str]:
        spec = _valid_cavity_spec()
        spec["regime"] = regime
        vocab = vocab_for("cavity_2d_cfd")
        errors = validate_spec(spec, CHOSEN_ID, vocab)
        return [e for e in errors if e.startswith("regime")]

    def test_valid_regime_produces_no_regime_error(self):
        self.assertEqual(self._regime_errors(_valid_cavity_spec()["regime"]), [])

    def test_not_an_object(self):
        self.assertEqual(
            self._regime_errors("laminar"),
            ["regime must be an object with reynolds_min, reynolds_max, and notes."],
        )

    def test_missing_notes(self):
        self.assertEqual(
            self._regime_errors({"reynolds_min": 100, "reynolds_max": 200}),
            ["regime is missing 'notes'."],
        )

    def test_non_number_bounds(self):
        self.assertEqual(
            self._regime_errors(
                {"reynolds_min": "low", "reynolds_max": 200, "notes": "n"}
            ),
            [
                "regime reynolds_min and reynolds_max must be numbers; "
                "got reynolds_min='low', reynolds_max=200."
            ],
        )

    def test_ordering_violation(self):
        self.assertEqual(
            self._regime_errors(
                {"reynolds_min": 300, "reynolds_max": 200, "notes": "n"}
            ),
            [
                "regime must satisfy 0 < reynolds_min <= reynolds_max; "
                "got reynolds_min=300 and reynolds_max=200."
            ],
        )


class Stage5NgspiceInputByteIdentity(unittest.TestCase):
    """Capture 3: the stage-5 ngspice composed input (the census suspect)."""

    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_stage5_input()
        self.assertEqual(user_turn, _fixture("thought_user_turn_ngspice.txt"))

    def test_assembly_is_deterministic_on_fixed_input(self):
        self.assertEqual(assemble_stage5_input(), assemble_stage5_input())

    def test_canned_input_is_canonical_post_stage4_shape(self):
        baton = Baton.from_json(_fixture("canned_stage5_input_ngspice.json"))
        self.assertEqual(validate_payload_post_stage4(baton.payload), [])

    def test_circuit_spec_enters_the_user_turn_verbatim(self):
        # SUPERSEDED at Phase 3c under R-23.5-5 (original assertion pinned
        # the placeholder; originals preserved as *_pre2355*): the honest
        # circuit spec IS the spec stage 5 sees — named-analysis regime in,
        # placeholder marker gone.
        _, user_turn = assemble_stage5_input()
        parsed = json.loads(user_turn)
        self.assertEqual(
            parsed["experiment_spec"],
            json.loads((C235_FIX / "ngspice_full_spec.json").read_text()),
        )
        self.assertIn("analysis_type", user_turn)
        self.assertNotIn("Not a fluid regime", user_turn)

    def test_superseded_originals_preserved_append_only(self):
        for name in (
            "canned_stage5_input_ngspice_pre2355.json",
            "thought_user_turn_ngspice_pre2355.txt",
        ):
            self.assertTrue((FIX / name).is_file(), name)
        # the preserved original still carries the placeholder it was
        # captured with — history, frozen
        self.assertIn(
            "Not a fluid regime", _fixture("thought_user_turn_ngspice_pre2355.txt")
        )


if __name__ == "__main__":
    unittest.main()
