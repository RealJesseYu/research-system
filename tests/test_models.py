"""test_models.py — the model-tier resolver (the 'model 1 / model 2' knobs)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import models  # noqa: E402


class TestModelFor(unittest.TestCase):
    def test_defaults_preserve_the_historical_mix(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("RESEARCH_MODEL_HEAVY", "RESEARCH_MODEL_LIGHT",
                      "RESEARCH_MODEL_TRIAGE"):
                os.environ.pop(k, None)
            self.assertEqual(models.model_for("heavy"), models.OPUS)
            self.assertEqual(models.model_for("light"), models.SONNET)
            self.assertEqual(models.model_for("triage"), models.HAIKU)

    def test_alias_override(self):
        with patch.dict(os.environ, {"RESEARCH_MODEL_HEAVY": "sonnet"}, clear=False):
            self.assertEqual(models.model_for("heavy"), models.SONNET)

    def test_all_opus_via_two_knobs(self):
        with patch.dict(os.environ, {"RESEARCH_MODEL_HEAVY": "opus",
                                     "RESEARCH_MODEL_LIGHT": "opus"}, clear=False):
            self.assertEqual(models.model_for("heavy"), models.OPUS)
            self.assertEqual(models.model_for("light"), models.OPUS)

    def test_full_model_id_passes_through(self):
        with patch.dict(os.environ, {"RESEARCH_MODEL_LIGHT": "claude-custom-9"},
                        clear=False):
            self.assertEqual(models.model_for("light"), "claude-custom-9")

    def test_case_insensitive_alias(self):
        with patch.dict(os.environ, {"RESEARCH_MODEL_TRIAGE": "OPUS"}, clear=False):
            self.assertEqual(models.model_for("triage"), models.OPUS)

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            models.model_for("gigantic")


class TestSetTier(unittest.TestCase):
    def test_set_and_clear(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESEARCH_MODEL_HEAVY", None)
            models.set_tier("heavy", "opus")
            self.assertEqual(models.model_for("heavy"), models.OPUS)
            models.set_tier("heavy", "")   # clear -> back to default
            self.assertEqual(models.model_for("heavy"), models.OPUS)  # default is opus
            models.set_tier("light", "opus")
            self.assertEqual(models.model_for("light"), models.OPUS)
            models.set_tier("light", "")
            self.assertEqual(models.model_for("light"), models.SONNET)

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            models.set_tier("nope", "opus")


if __name__ == "__main__":
    unittest.main()
