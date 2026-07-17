"""
test_boundary_enforcement.py — standalone tests of the supervisor's
enforce_boundary_schema helper (Step 15). Zero model calls.

record_run_outcome is patched out so no test ever appends to the real
journal (memory/journal.jsonl is append-only evidence — tests must not
write to it); the Logger writes to a temp file. The live loud-halt
behavior, including the real journal append, is separately proven on disk
at runs/schema-halt-proof-20260706T052125Z (chunk-2 evidence).

Run directly: venv/bin/python3 tests/test_boundary_enforcement.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import schemas
from baton import Baton
from supervisor import Logger, enforce_boundary_schema

# Truth-edited Step 23.5 (R-23.5-4): the post-gate-1 payload carries the
# decided instrument.
VALID_POST_GATE1_PAYLOAD = {
    "domain": "baseline characterization of laminar lid-driven cavity flows",
    "chosen_hypothesis": {
        "id": "hand-baseline",
        "statement": "baseline cavity mean-speed characterization",
        "rationale": "canned copy of the RUN B payload's hypothesis",
    },
    "substrate_id": "cavity_2d_cfd",
}


def _make_baton(payload: dict) -> Baton:
    return Baton(
        run_id="test-boundary",
        created_at="2026-07-06T00:00:00+00:00",
        mode="auto",
        payload=payload,
    )


class TestEnforceBoundarySchema(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmp.name) / "log.txt"
        self.logger = Logger(self.log_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_payload_passes_through(self):
        baton = _make_baton(dict(VALID_POST_GATE1_PAYLOAD))
        with patch("supervisor.record_run_outcome") as recorded:
            enforce_boundary_schema(
                self.logger, baton, "gate 1", schemas.validate_payload_post_gate1
            )
            recorded.assert_not_called()
        log = self.log_path.read_text()
        self.assertIn("SCHEMA OK after gate 1", log)
        self.assertNotIn("SCHEMA VIOLATION", log)

    def test_corrupted_payload_halts_loudly(self):
        payload = dict(VALID_POST_GATE1_PAYLOAD)
        payload["stowaway"] = "not part of any locked shape"
        baton = _make_baton(payload)
        with patch("supervisor.record_run_outcome") as recorded:
            with self.assertRaises(SystemExit) as ctx:
                enforce_boundary_schema(
                    self.logger, baton, "gate 1", schemas.validate_payload_post_gate1
                )
            self.assertEqual(ctx.exception.code, 1)
            recorded.assert_called_once()
            self.assertIn(
                "schema violation after gate 1", recorded.call_args.args[1]
            )
        log = self.log_path.read_text()
        self.assertIn("SCHEMA VIOLATION after gate 1", log)
        self.assertIn("'stowaway'", log)
        self.assertNotIn("SCHEMA OK", log)


if __name__ == "__main__":
    unittest.main()
