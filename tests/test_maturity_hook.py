"""
test_maturity_hook.py — STEP 28. Call-free: no model calls, no network. Covers
the supervisor's substrate-maturity routing hook, the run-record stamping, and
the gate-5 signoff display.

Run directly: venv/bin/python3 tests/test_maturity_hook.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import supervisor
from baton import Baton
from tools import substrate_registry as registry


class CaptureLogger:
    """Minimal stand-in for supervisor.Logger — the hook only calls .log()."""

    def __init__(self):
        self.lines: list[str] = []

    def log(self, line: str) -> None:
        self.lines.append(line)


def _baton(mode: str, label: str) -> Baton:
    b = Baton(run_id="run-x", created_at="2026-07-15T00:00:00Z", mode=mode)
    b.payload = {
        "domain": "fluids",
        "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
        "experiment_spec": {"title": "t"},
        "fidelity_verdict": {
            "label": label,
            "rationale": "the model's reasoning",
            "right_instrument": "the right instrument text",
        },
    }
    return b


class TestHumanModeNonMature(unittest.TestCase):
    def test_trust_verdict_untouched_but_signoff_required(self):
        b = _baton("human", "trust")
        before = dict(b.payload["fidelity_verdict"])
        logger = CaptureLogger()
        supervisor.apply_substrate_maturity_hook(logger, b, "human")
        # verdict is UNTOUCHED in human mode (byte-identical routing to stage 4)
        self.assertEqual(b.payload["fidelity_verdict"], before)
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "trust")
        # but the signoff is recorded + logged
        signoff = b._maturity_signoff
        self.assertTrue(signoff["required"])
        self.assertEqual(signoff["substrates"], ["cavity_2d_cfd@provisional"])
        self.assertTrue(any("NEEDS_HUMAN_SIGNOFF" in ln for ln in logger.lines))
        # no downgrade line in human mode
        self.assertFalse(any("MATURITY_DOWNGRADE" in ln for ln in logger.lines))

    def test_cfd_today_human_mode_byte_identical_payload(self):
        """Back-compat proof: in human mode the hook changes NOTHING the stage
        relay routes on — the whole payload is identical before and after."""
        b = _baton("human", "trust")
        import copy

        before = copy.deepcopy(b.payload)
        supervisor.apply_substrate_maturity_hook(CaptureLogger(), b, "human")
        self.assertEqual(b.payload, before)


class TestAutoModeDowngrade(unittest.TestCase):
    def test_trust_downgraded_to_defer_and_logged(self):
        b = _baton("auto", "trust")
        logger = CaptureLogger()
        supervisor.apply_substrate_maturity_hook(logger, b, "auto")
        # never silently trusted: the verdict is downgraded to defer-class
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "defer")
        self.assertTrue(any("MATURITY_DOWNGRADE" in ln for ln in logger.lines))
        self.assertTrue(any("never silently trusted" in ln for ln in logger.lines))
        self.assertTrue(b._maturity_signoff["required"])

    def test_refine_also_downgraded(self):
        b = _baton("auto", "refine")
        supervisor.apply_substrate_maturity_hook(CaptureLogger(), b, "auto")
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "defer")


class TestNoOpPaths(unittest.TestCase):
    def test_defer_verdict_is_not_a_trust_decision(self):
        b = _baton("auto", "defer")
        logger = CaptureLogger()
        supervisor.apply_substrate_maturity_hook(logger, b, "auto")
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "defer")
        self.assertFalse(hasattr(b, "_maturity_signoff"))
        self.assertEqual(logger.lines, [])

    def test_mature_substrate_passes_untouched(self):
        """If every routable substrate were mature, the hook is a full no-op —
        verdict untouched, no signoff, no log lines."""
        b = _baton("auto", "trust")
        logger = CaptureLogger()
        with mock.patch.object(registry, "is_mature", return_value=True):
            supervisor.apply_substrate_maturity_hook(logger, b, "auto")
        self.assertEqual(b.payload["fidelity_verdict"]["label"], "trust")
        self.assertFalse(hasattr(b, "_maturity_signoff"))
        self.assertEqual(logger.lines, [])

    def test_no_verdict_is_noop(self):
        b = Baton(run_id="r", created_at="c", mode="auto")
        b.payload = {"domain": "fluids"}
        supervisor.apply_substrate_maturity_hook(CaptureLogger(), b, "auto")
        self.assertFalse(hasattr(b, "_maturity_signoff"))


class TestRunRecordStamping(unittest.TestCase):
    def test_signoff_stamped_into_run_record(self):
        b = _baton("human", "trust")
        supervisor.apply_substrate_maturity_hook(CaptureLogger(), b, "human")
        captured = []
        with mock.patch.object(supervisor, "journal_append", lambda e: captured.append(e) or e):
            supervisor.record_run_outcome(b, "completed")
        rec = captured[0]
        self.assertTrue(rec["extras"]["needs_human_signoff"])
        self.assertEqual(
            rec["extras"]["needs_human_signoff_substrates"], ["cavity_2d_cfd@provisional"]
        )
        self.assertIn("needs_human_signoff=[cavity_2d_cfd@provisional]", rec["text"])

    def test_no_signoff_run_record_is_byte_identical(self):
        """Back-compat: a baton the hook never touched yields a record with no
        needs_human_signoff key at all."""
        b = _baton("human", "defer")  # defer never sets the attribute
        captured = []
        with mock.patch.object(supervisor, "journal_append", lambda e: captured.append(e) or e):
            supervisor.record_run_outcome(b, "completed")
        rec = captured[0]
        self.assertNotIn("needs_human_signoff", rec["extras"])
        self.assertNotIn("needs_human_signoff", rec["text"])


class TestGateDisplay(unittest.TestCase):
    def test_display_shows_signoff(self):
        b = _baton("human", "trust")
        supervisor.apply_substrate_maturity_hook(CaptureLogger(), b, "human")
        out = supervisor.build_maturity_signoff_display(b)
        self.assertIn("NEEDS HUMAN SIGN-OFF", out)
        self.assertIn("cavity_2d_cfd@provisional", out)

    def test_display_empty_when_no_signoff(self):
        b = _baton("human", "defer")
        self.assertEqual(supervisor.build_maturity_signoff_display(b), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
