"""
test_strip_fence.py — standalone test of model_call's fence detector.
Zero model calls: strip_fence is a pure function with no I/O, so this
exercises it directly. The load-bearing property (Step-11 fence-fix ruling)
is that detection is independent of whether the stripped text parses as
JSON — a fenced-but-garbage reply must still report was_fenced=True.

Also covers the 17-CLOSE single-fence prose tolerance
(extract_single_fenced_block plus its call_stage_model wiring, driven by a
fake transport): the frozen fixture is the EXACT attempt-1 failure reply
from the Step-22 smoke crash (RE-ASK line, stage6_paper_hypothesis_reflect,
runs/smoke6-20260711T083510Z in the build-22 worktree) — prose around
exactly one ```json fence, which burned the whole re-ask budget live.

Run directly: venv/bin/python3 tests/test_strip_fence.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
from model_call import (
    call_stage_model,
    extract_json_object,
    extract_single_fenced_block,
    strip_fence,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "smoke6_prose_wrapped_reply.txt"
)


class TestStripFence(unittest.TestCase):
    def test_detection_is_independent_of_parseability(self):
        # Plain JSON: untouched, not fenced.
        self.assertEqual(strip_fence('{"a": 1}'), ('{"a": 1}', False))
        # Fenced JSON with language tag: stripped and flagged.
        self.assertEqual(
            strip_fence('```json\n{"a": 1}\n```'), ('{"a": 1}', True)
        )
        # Fenced JSON without language tag: stripped and flagged.
        self.assertEqual(strip_fence('```\n{"a": 1}\n```'), ('{"a": 1}', True))
        # THE undercount case: fenced text that is NOT valid JSON must still
        # be flagged — the flag reports the fence, not the parse.
        text, was_fenced = strip_fence("```\nnot json at all\n```")
        self.assertTrue(was_fenced)
        self.assertEqual(text, "not json at all")
        # Surrounding whitespace tolerated, as before.
        self.assertEqual(strip_fence('  ```json\n{"a": 1}\n```  '), ('{"a": 1}', True))
        # Unfenced non-JSON passes through unflagged (whitespace-trimmed only).
        self.assertEqual(strip_fence("  hello  "), ("hello", False))


class TestSingleFenceProseTolerance(unittest.TestCase):
    def test_smoke_crash_fixture_fails_the_existing_path(self):
        # The frozen reply reproduces the live failure: it does not START
        # with a fence (strip_fence sees no fence), and the raw text is not
        # JSON — exactly the shape that re-asked three times and crashed.
        reply = FIXTURE_PATH.read_text()
        text, was_fenced = strip_fence(reply)
        self.assertFalse(was_fenced)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)

    def test_smoke_crash_fixture_is_rescued_by_extraction(self):
        reply = FIXTURE_PATH.read_text()
        block = extract_single_fenced_block(reply)
        self.assertIsNotNone(block)
        data = json.loads(block)
        self.assertEqual(data["ack_run_id"], "smoke6-20260711T083510Z")
        self.assertIn("section_markdown", data)

    def test_no_fence_and_multiple_fences_return_none(self):
        # No fence: existing behavior kept.
        self.assertIsNone(extract_single_fenced_block("just prose, no json"))
        # Multiple fences: ambiguous, existing behavior kept.
        self.assertIsNone(
            extract_single_fenced_block(
                'a ```json\n{"a": 1}\n``` b ```json\n{"b": 2}\n``` c'
            )
        )
        # Unclosed fence (odd backtick runs): not exactly one block.
        self.assertIsNone(extract_single_fenced_block('```json\n{"a": 1}'))

    def test_language_tag_dropped_and_plain_fence_kept(self):
        self.assertEqual(
            extract_single_fenced_block('prose ```json\n{"a": 1}\n``` more prose'),
            '{"a": 1}',
        )
        self.assertEqual(
            extract_single_fenced_block('prose ```\n{"a": 1}\n```'), '{"a": 1}'
        )

    def test_call_stage_model_rescues_the_fixture_on_attempt_1(self):
        # The wiring proof: a fake transport returns the exact crash reply;
        # call_stage_model must now succeed on attempt 1 with no re-ask.
        reply = FIXTURE_PATH.read_text()
        with patch.object(model_call, "_invoke_transport", return_value=reply):
            data, timing = call_stage_model(
                "tolerance_test_stage",
                "system prompt",
                {"input": "x"},  # no run_id: nothing durably logged
                {"required": ["ack_run_id", "section_markdown"]},
            )
        self.assertEqual(timing["attempts"], 1)
        self.assertEqual(data["ack_run_id"], "smoke6-20260711T083510Z")

    def test_unrescuable_reply_keeps_existing_failure_path(self):
        # A prose-only reply (no fence) must still burn all attempts and
        # raise, exactly as before the tolerance.
        with patch.object(
            model_call, "_invoke_transport", return_value="no json here at all"
        ):
            with self.assertRaises(RuntimeError):
                call_stage_model(
                    "tolerance_test_stage",
                    "system prompt",
                    {"input": "x"},
                    {"required": ["ack_run_id"]},
                )


class TestProseWrappedObjectTolerance(unittest.TestCase):
    """A FULL/tooled agent narrates then emits raw JSON with no fence — first
    seen live in the free_experimenter Collatz run (2026-07-23). extract_json_object
    recovers the embedded object; call_stage_model must then parse on attempt 1."""

    def test_recovers_object_after_prose(self):
        reply = 'Both methods agree.\n\n**Results:** max 350.\n\n{"a": 1, "b": 2}'
        self.assertEqual(extract_json_object(reply), '{"a": 1, "b": 2}')

    def test_braces_inside_strings_do_not_fool_it(self):
        reply = 'prose {not json} more\n\n{"reproduce": "run f.py (prints {x})", "ok": true}'
        obj = json.loads(extract_json_object(reply))
        self.assertEqual(obj["reproduce"], "run f.py (prints {x})")
        self.assertTrue(obj["ok"])

    def test_last_object_wins(self):
        reply = '{"draft": 1} then I revised\n\n{"final": 2}'
        self.assertEqual(extract_json_object(reply), '{"final": 2}')

    def test_no_object_returns_none(self):
        self.assertIsNone(extract_json_object("just prose, no json at all"))

    def test_call_stage_model_rescues_a_prose_wrapped_reply(self):
        # the real free_experimenter shape: narration, then the JSON result
        reply = ('Both an independent method and the re-run agree.\n\n'
                 '{"summary": "computed collatz", "findings": '
                 '[{"label": "max", "value": 350, "verified": true, '
                 '"reproduce": "python3 verify.py"}], "publishable": true}')
        with patch.object(model_call, "_invoke_transport", return_value=reply):
            data, timing = call_stage_model(
                "tolerance_test_stage",
                "system prompt",
                {"input": "x"},
                {"required": ["summary", "publishable"]},
            )
        self.assertEqual(timing["attempts"], 1)
        self.assertTrue(data["publishable"])
        self.assertEqual(data["findings"][0]["value"], 350)


class TestTheAnswerIsPickedBySchemaNotByPosition(unittest.TestCase):
    """`extract_json_object` took the LAST candidate — a choice made for a real
    case (narration BEFORE the answer containing JSON) that fails the mirror
    case: an agent finishing with a schema restatement handed back the
    restatement, so its real answer was discarded and the stage re-asked with a
    bogus "missing required field". Under a FULL profile each such re-ask is
    another 200-turn agentic run.

    Neither first nor last is right, so selection uses the SCHEMA the caller
    already has. A restatement satisfies required-KEY presence — which is why
    validate_schema cannot discriminate it (required fields and enums only) —
    so the tell is the VALUES: type names and <placeholders> where data belongs.
    """

    SCHEMA = {"required": ["summary", "findings"]}

    def _pick(self, reply):
        return model_call._select_json_candidate(reply, self.SCHEMA)

    def test_a_trailing_schema_restatement_does_not_win(self):
        reply = ('Both methods agree.\n{"summary":"s","findings":[]}\n'
                 'For reference the schema is {"summary": "string", '
                 '"findings": "list"}.')
        self.assertEqual(json.loads(self._pick(reply))["summary"], "s")
        # and the old behaviour is what this is protecting against
        self.assertEqual(
            json.loads(extract_json_object(reply))["summary"], "string")

    def test_leading_narration_json_still_loses_to_the_answer(self):
        """The case 'last wins' was written for — it must keep working."""
        reply = 'I tried {"attempt": 1} first.\n{"summary":"s","findings":[1]}'
        self.assertEqual(json.loads(self._pick(reply))["findings"], [1])

    def test_an_example_before_and_a_restatement_after(self):
        reply = ('e.g. {"summary":"x"}\n{"summary":"real","findings":[2]}\n'
                 'schema: {"summary":"str"}')
        self.assertEqual(json.loads(self._pick(reply))["summary"], "real")

    def test_angle_bracket_placeholders_are_recognised_as_an_echo(self):
        reply = ('{"summary":"done","findings":[3]}\n'
                 'format: {"summary":"<text>","findings":"<list>"}')
        self.assertEqual(json.loads(self._pick(reply))["summary"], "done")

    def test_a_real_answer_whose_value_is_the_word_string_is_not_an_echo(self):
        """The echo test requires EVERY value to look like a description, so a
        genuine answer mentioning a type name survives."""
        reply = '{"summary":"the type is string","findings":["string"]}'
        self.assertEqual(json.loads(self._pick(reply))["findings"], ["string"])

    def test_a_reply_with_no_json_still_returns_none(self):
        self.assertIsNone(self._pick("just prose, no object at all"))

    def test_a_malformed_reply_keeps_its_old_fallback(self):
        """No candidate carries the required keys: return the last that parses,
        so the error the caller raises is the one it always raised."""
        self.assertEqual(json.loads(self._pick('{"a":1}')), {"a": 1})


class TestATransportFailureIsNotAModelError(unittest.TestCase):
    """Only `usage` was read off the ResultMessage, so is_error was invisible: a
    429/5xx returned whatever text had accumulated (often nothing), that reached
    json.loads, and the VALIDATION loop retried it three times as though the
    model had answered badly — each retry a full agentic run under a tool
    profile. The final error then read "model reply failed schema validation
    after 3 attempts", a sentence about the model for a failure of the transport.
    """

    class _RM:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Caps:
        max_turns = 200

    def test_is_error_raises(self):
        with self.assertRaises(model_call.TransportFailure):
            model_call._raise_if_transport_failed(
                self._RM(is_error=True, stop_reason="error", num_turns=3),
                self._Caps())

    def test_the_message_names_what_actually_failed(self):
        try:
            model_call._raise_if_transport_failed(
                self._RM(is_error=True, stop_reason="error", num_turns=3),
                self._Caps())
        except model_call.TransportFailure as e:
            self.assertIn("transport", str(e))
            self.assertIn("not a malformed model reply", str(e))

    def test_a_healthy_result_does_not_raise(self):
        model_call._raise_if_transport_failed(
            self._RM(is_error=False, num_turns=5), self._Caps())

    def test_a_turn_ceiling_alone_does_not_raise(self):
        """An agent can legitimately use every turn and still emit a valid final
        answer. Raising on that would fail runs that currently work."""
        model_call._raise_if_transport_failed(
            self._RM(is_error=False, num_turns=200), self._Caps())

    def test_missing_sdk_attributes_do_not_become_an_attributeerror(self):
        """stop_reason/num_turns vary across SDK versions; a missing attribute
        must not turn a real failure into a different exception."""
        with self.assertRaises(model_call.TransportFailure):
            model_call._raise_if_transport_failed(self._RM(is_error=True), None)
        model_call._raise_if_transport_failed(self._RM(), None)   # no is_error
        model_call._raise_if_transport_failed(None, None)         # older SDK

    def test_it_is_not_a_schema_error(self):
        """It must land in _transport_with_retry — which knows a TOOLED call is
        not idempotent — and never in the validation re-ask loop."""
        self.assertFalse(
            issubclass(model_call.TransportFailure, model_call.SchemaValidationError))


if __name__ == "__main__":
    unittest.main()


class TestLoggingCannotKillARun(unittest.TestCase):
    """_log_fence_note / _log_reask / _log_transport_retry each did
    `open(Path("runs")/run_id/"log.txt", "a")` with no mkdir and no guard, and all
    three are called from INSIDE the attempt loop. A run_id whose directory does
    not exist raised FileNotFoundError and took the run down.

    _log_fence_note made that acute: it fires on the FIRST FENCED REPLY, and
    CLAUDE.md's own fence watch records Sonnet and Haiku fencing at ~100%. So the
    failure mode was "the run dies on its first model reply, from the logging" —
    on a run that may already have cost tens of millions of tokens. All three
    docstrings described this as best-effort; now it is.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def _all_three(self, stage_input):
        model_call._log_fence_note("s", stage_input)
        model_call._log_reask("s", stage_input, 1, "bad json")
        model_call._log_transport_retry("s", stage_input, 1, RuntimeError("x"))

    def test_a_missing_run_directory_is_created_not_fatal(self):
        self._all_three({"run_id": "no-such-run"})
        log = Path("runs/no-such-run/log.txt")
        self.assertTrue(log.is_file())
        self.assertEqual(len(log.read_text().splitlines()), 3)

    def test_an_unwritable_path_is_survived(self):
        """runs/<id> existing as a FILE: the durable write cannot succeed, and
        losing the line is strictly better than losing the run."""
        Path("runs").mkdir()
        Path("runs/blocked").write_text("a file, not a directory")
        self._all_three({"run_id": "blocked"})       # must not raise

    def test_no_run_id_writes_nothing_and_does_not_raise(self):
        self._all_three({})
        self.assertFalse(Path("runs").exists())

    def test_a_non_dict_stage_input_is_survived(self):
        model_call._log_fence_note("s", None)
        model_call._log_fence_note("s", "not a dict")
