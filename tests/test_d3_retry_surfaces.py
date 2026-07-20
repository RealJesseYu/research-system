"""
test_d3_retry_surfaces.py — D.3 Step-0 captures (era 56c5d6b, pre-surgery).

ZERO live model calls: before stage2_spec.py's four run_cfd vocabulary
imports (QOI_OPERATIONS, QOI_COMPONENTS, MASK_TYPES, _QOI_FIELD_RE) move
behind a per-substrate lookup (D.3), the MODEL-VISIBLE re-ask surface those
vocabularies compose into gets byte-pinned. The path being pinned:

  validate_spec error strings
    -> stage2_experiment_design._make_extra_validator (stage2_experiment_design.py)
    -> call_stage_model extra_validator -> SchemaValidationError(" ".join(errors))
       (model_call.py, validation block)
    -> last_error = f"{e} (raw reply: {reply!r})"
    -> attempt-2 user_turn json.dumps({"original_input": ..., "validation_error": ...})
       (model_call.py, the attempt > 1 branch) — SENT TO THE MODEL.

The d1 family pins only the attempt-1 pair; this family pins the attempt-2
retry user_turn for one cavity spec per rejection class owned by the four
imported names:

  bad operation  -> QOI_OPERATIONS   (reply_bad_operation.json / retry_bad_operation.txt)
  bad component  -> QOI_COMPONENTS   (reply_bad_component.json / retry_bad_component.txt)
  bad mask type  -> MASK_TYPES       (reply_bad_mask.json      / retry_bad_mask.txt)
  bad field name -> _QOI_FIELD_RE    (reply_bad_field.json     / retry_bad_field.txt)

Each canned reply is the known-valid handcrafted baseline spec (frozen here,
never re-read from specs/) with exactly ONE perturbation, so the captured
validation_error carries exactly one validator error string. The baton is the
d1 canned post-gate-1 cavity baton (single source, reused not copied). The
transport is intercepted at model_call._transport_with_retry: call 1 returns
the canned failing reply, call 2 captures the composed retry user_turn and
raises — no model is ever called.

Regenerate fixtures (only ever legitimately run on the pre-surgery tree, or
to prove post-surgery byte-identity by diff):
    venv/bin/python3 tests/test_d3_retry_surfaces.py --capture
Run as tests: venv/bin/python3 tests/test_d3_retry_surfaces.py
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
from stages import stage2_experiment_design as s2

FIX = Path(__file__).resolve().parent / "fixtures" / "d3"
D1_FIX = Path(__file__).resolve().parent / "fixtures" / "d1"

REJECTION_CLASSES = ("bad_operation", "bad_component", "bad_mask", "bad_field")


class _Captured(Exception):
    """Raised by the transport stub on attempt 2, right after the composed
    retry user_turn is in hand."""


def compose_retry_surface(reply_text: str) -> tuple[str, str]:
    """Drive the REAL re-ask composition: stage 2's run() on the d1 canned
    baton, transport patched so attempt 1 returns `reply_text` and attempt 2
    captures the exact (system_prompt, user_turn) pair the model would see.
    """
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
    tmp = tempfile.mkdtemp(prefix="d3_retry_")
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


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


class RetrySurfaceByteIdentity(unittest.TestCase):
    def _check_class(self, cls: str) -> None:
        system_prompt, user_turn = compose_retry_surface(
            _fixture(f"reply_{cls}.json")
        )
        self.assertEqual(user_turn, _fixture(f"retry_{cls}.txt"))
        # the attempt-2 system prompt IS the module constant — the d1 family
        # already byte-pins its text; identity is the stronger claim here.
        self.assertIs(system_prompt, s2.SYSTEM_PROMPT)

    def test_bad_operation_retry_byte_identical(self):
        self._check_class("bad_operation")

    def test_bad_component_retry_byte_identical(self):
        self._check_class("bad_component")

    def test_bad_mask_retry_byte_identical(self):
        self._check_class("bad_mask")

    def test_bad_field_retry_byte_identical(self):
        self._check_class("bad_field")

    def test_composition_is_deterministic(self):
        reply = _fixture("reply_bad_operation.json")
        self.assertEqual(
            compose_retry_surface(reply), compose_retry_surface(reply)
        )

    def test_original_input_matches_d1_pinned_user_turn(self):
        # Cross-family coherence: the retry surface embeds the SAME assembled
        # stage_input the d1 family pinned as the attempt-1 user_turn.
        for cls in REJECTION_CLASSES:
            parsed = json.loads(_fixture(f"retry_{cls}.txt"))
            self.assertEqual(
                json.dumps(parsed["original_input"]),
                (D1_FIX / "stage2_user_turn.txt").read_text(),
            )

    def test_each_class_carries_exactly_one_validator_error(self):
        # One perturbation per canned reply -> exactly one error string in
        # the validation_error (before the " (raw reply: ...)" tail), so each
        # fixture pins its class unmixed. The error text ends with a period;
        # assert the tail follows the single error directly.
        markers = {
            "bad_operation": "qoi operation must be one of",
            "bad_component": "qoi component must be",
            "bad_mask": "qoi mask type must be one of",
            "bad_field": "qoi field must be the exact name",
        }
        for cls, marker in markers.items():
            validation_error = json.loads(_fixture(f"retry_{cls}.txt"))[
                "validation_error"
            ]
            self.assertIn(marker, validation_error)
            self.assertEqual(validation_error.count(" (raw reply: "), 1)


def capture() -> None:
    """Write the eight d3 fixtures from the CURRENT tree's composition."""
    FIX.mkdir(parents=True, exist_ok=True)
    base_envelope = json.loads(
        (Path(__file__).resolve().parent.parent / "specs" / "handcrafted_baseline_qoi.json").read_text()
    )

    def envelope_with(perturb: dict) -> str:
        spec = json.loads(json.dumps(base_envelope))  # deep copy
        spec["qoi"].update(perturb)
        return json.dumps(
            {"ack_run_id": "d1-canned-cavity", "spec": spec}, indent=2
        )

    perturbations = {
        "bad_operation": {"operation": "median"},
        "bad_component": {"component": "x"},
        "bad_mask": {"mask": {"type": "sphere", "params": {"radius_frac": 0.1}}},
        "bad_field": {"field": "2bad field!"},
    }
    for cls, perturb in perturbations.items():
        reply = envelope_with(perturb)
        (FIX / f"reply_{cls}.json").write_text(reply)
        _, user_turn = compose_retry_surface(reply)
        (FIX / f"retry_{cls}.txt").write_text(user_turn)
        print(f"captured {cls}: {len(user_turn)} bytes")


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture()
    else:
        unittest.main()
