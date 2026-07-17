"""
test_c235_gate.py — Step 23.5 Phase-2 proofs: the gate decides the
instrument. ZERO live model calls; ZERO docker.

Covers, per the owner-ruled 2026-07-17 brief:
  2a — the chooser envelope is exactly {ack_run_id, chosen_id, substrate_id,
       reasoning}; substrate_id membership is validated against
       routable_ids() read LIVE from the registry (proven live by swapping
       the registry read and watching the acceptance set follow it — never
       a hardcoded list); the fallback record carries substrate_id null.
  2b — auto mode: a null instrument STOPS the run loudly at the gate with a
       named reason (R-23.5-2), distinguishable in the log from a human
       halt; PROVEN BY FAILING with a constructed fallback record. A
       non-null instrument travels with the selection.
  2c — human mode: the chooser's instrument read joins the advisory; after
       the valid rank pick the R-23.5-3 instrument prompt (live routable
       list; halt allowed; same invalid-answer cap pattern);
       parse_gate1_instrument is pure and unit-tested; the override-ledger
       rank entry keeps its exact current shape and the instrument answer
       is logged additively beside it.
  2d — apply_gate1_selection writes the R-23.5-4 payload
       {domain, chosen_hypothesis, substrate_id}; substrate_id is a
       REQUIRED keyword (a caller that omits it raises — escape-failing,
       never a default).

Schema-layer escapes (widened POST_GATE1_KEYS rejects extra keys and
missing/empty substrate_id) live beside their family in
tests/test_schemas.py::TestPostGate1.

Run directly: venv/bin/python3 tests/test_c235_gate.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import supervisor
from baton import Baton
from stages import gate1_chooser
from tools.substrate_registry import routable_ids

RUN_ID = "c235-gate-test"

HYPOTHESES = [
    {"id": "h1", "statement": "statement one", "rationale": "rationale one"},
    {"id": "h2", "statement": "statement two", "rationale": "rationale two"},
]

CHOOSER_RECORD_NGSPICE = {
    "chosen_id": "h2",
    "substrate_id": "ngspice_linear_passive",
    "reasoning": "constructed: h2 on the circuit instrument",
    "fallback": False,
}

# The R-23.5-2 constructed fallback record: the never-raise path's shape.
FALLBACK_RECORD_NULL = {
    "chosen_id": "h1",
    "substrate_id": None,
    "reasoning": "fallback to rank 1: constructed transport failure",
    "fallback": True,
}


def make_baton():
    return Baton(
        run_id=RUN_ID,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode="auto",
        payload={
            "domain": "test domain",
            "hypotheses": [dict(h) for h in HYPOTHESES],
            "hypotheses_ranked": True,
        },
    )


class TmpRunDirCase(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        self.run_dir = Path("runs") / RUN_ID
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()


class TestChooserEnvelope(unittest.TestCase):
    """2a: envelope + validator, constructed replies, no model."""

    def _validator(self):
        return gate1_chooser.make_choice_validator({"h1", "h2"})

    def test_valid_four_field_reply_passes(self):
        for sid in routable_ids():
            reply = {
                "ack_run_id": RUN_ID,
                "chosen_id": "h1",
                "substrate_id": sid,
                "reasoning": "fine",
            }
            self.assertEqual(self._validator()(reply), [])

    def test_schema_requires_substrate_id(self):
        self.assertIn("substrate_id", gate1_chooser.SCHEMA["required"])
        self.assertIn("substrate_id", gate1_chooser.ENVELOPE_FIELDS)

    def test_unroutable_substrate_rejected_with_live_list(self):
        reply = {
            "ack_run_id": RUN_ID,
            "chosen_id": "h1",
            "substrate_id": "web_search",  # enrolled, NOT routable
            "reasoning": "fine",
        }
        errors = self._validator()(reply)
        self.assertEqual(len(errors), 1)
        self.assertIn(
            f"substrate_id must be exactly one of {list(routable_ids())}",
            errors[0],
        )

    def test_unknown_substrate_rejected(self):
        reply = {
            "ack_run_id": RUN_ID,
            "chosen_id": "h1",
            "substrate_id": "no_such_instrument",
            "reasoning": "fine",
        }
        self.assertEqual(len(self._validator()(reply)), 1)

    def test_extra_field_rejected_with_new_envelope_text(self):
        reply = {
            "ack_run_id": RUN_ID,
            "chosen_id": "h1",
            "substrate_id": routable_ids()[0],
            "reasoning": "fine",
            "stowaway": True,
        }
        errors = self._validator()(reply)
        self.assertEqual(len(errors), 1)
        self.assertIn(
            'exactly "ack_run_id", "chosen_id", "substrate_id", and '
            '"reasoning", nothing else.',
            errors[0],
        )

    def test_membership_reads_the_registry_LIVE_not_a_copy(self):
        # The no-third-copy proof: swap the registry read at the chooser's
        # import site and the acceptance set must follow it — a hardcoded
        # list could not.
        reply_alien = {
            "ack_run_id": RUN_ID,
            "chosen_id": "h1",
            "substrate_id": "alien_substrate",
            "reasoning": "fine",
        }
        reply_cavity = {
            "ack_run_id": RUN_ID,
            "chosen_id": "h1",
            "substrate_id": "cavity_2d_cfd",
            "reasoning": "fine",
        }
        validator = self._validator()
        self.assertEqual(len(validator(reply_alien)), 1)
        self.assertEqual(validator(reply_cavity), [])
        with patch.object(
            gate1_chooser, "routable_ids", lambda: ("alien_substrate",)
        ):
            self.assertEqual(validator(reply_alien), [])
            self.assertEqual(len(validator(reply_cavity)), 1)


class TestAutoModeInstrument(TmpRunDirCase):
    """2b: the auto gate carries the instrument; null stops loudly."""

    def test_null_instrument_stops_the_run_at_the_gate(self):
        # PROVEN BY FAILING (R-23.5-2): a constructed fallback record with
        # substrate_id null must stop the run — never a cavity default.
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        with patch.object(
            supervisor.gate1_chooser,
            "choose_hypothesis",
            lambda run_id, hyps, run_dir: dict(FALLBACK_RECORD_NULL),
        ):
            outcome = supervisor.run_gate1(logger, baton, "auto")
        self.assertEqual(outcome, ("halt",))
        log_text = (self.run_dir / "log.txt").read_text()
        # The named reason, distinguishable in the log from a human halt
        # (no human prompt/answer lines exist on this path).
        self.assertIn("STOP null-instrument (R-23.5-2)", log_text)
        self.assertIn("chooser returned substrate_id null", log_text)
        self.assertIn("constructed transport failure", log_text)
        self.assertNotIn("human answered", log_text)

    def test_non_null_instrument_travels_with_the_selection(self):
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        with patch.object(
            supervisor.gate1_chooser,
            "choose_hypothesis",
            lambda run_id, hyps, run_dir: dict(CHOOSER_RECORD_NGSPICE),
        ):
            outcome = supervisor.run_gate1(logger, baton, "auto")
        self.assertEqual(outcome, ("select", 2, "ngspice_linear_passive"))


class TestParseGate1Instrument(unittest.TestCase):
    """2c: the pure instrument-answer parser (parse_gate1_selection pattern)."""

    ROUTABLE = ("cavity_2d_cfd", "ngspice_linear_passive")

    def parse(self, raw):
        return supervisor.parse_gate1_instrument(raw, self.ROUTABLE)

    def test_exact_id_selects(self):
        self.assertEqual(
            self.parse("ngspice_linear_passive"),
            ("instrument", "ngspice_linear_passive"),
        )

    def test_padded_id_selects(self):
        self.assertEqual(
            self.parse("  cavity_2d_cfd  "), ("instrument", "cavity_2d_cfd")
        )

    def test_index_selects_in_enrollment_order(self):
        self.assertEqual(self.parse("1"), ("instrument", "cavity_2d_cfd"))
        self.assertEqual(self.parse("2"), ("instrument", "ngspice_linear_passive"))

    def test_n_halts_both_cases(self):
        self.assertEqual(self.parse("n"), ("halt",))
        self.assertEqual(self.parse("N"), ("halt",))

    def test_out_of_range_index_invalid(self):
        self.assertEqual(self.parse("0"), ("invalid",))
        self.assertEqual(self.parse("3"), ("invalid",))

    def test_unknown_text_invalid(self):
        self.assertEqual(self.parse("openfoam"), ("invalid",))

    def test_empty_invalid(self):
        self.assertEqual(self.parse(""), ("invalid",))
        self.assertEqual(self.parse("   "), ("invalid",))


class TestHumanModeInstrument(TmpRunDirCase):
    """2c: the human instrument prompt — ledger additivity, halt, cap."""

    def run_human(self, inputs):
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        ledger_writes = []
        with patch.object(
            supervisor.gate1_chooser,
            "choose_hypothesis",
            lambda run_id, hyps, run_dir: dict(CHOOSER_RECORD_NGSPICE),
        ), patch.object(
            supervisor, "override_append", lambda **kw: ledger_writes.append(kw)
        ), patch("builtins.input", side_effect=inputs):
            outcome = supervisor.run_gate1(logger, baton, "human")
        return outcome, ledger_writes, (self.run_dir / "log.txt").read_text()

    def test_index_answer_resolves_by_enrollment_order(self):
        outcome, writes, log = self.run_human(["1", "2"])
        self.assertEqual(outcome, ("select", 1, "ngspice_linear_passive"))
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[1]["human_decision"], "instrument ngspice_linear_passive")
        # agreeing with the chooser's read is not an override
        self.assertFalse(writes[1]["did_override"])

    def test_advisory_shows_the_chooser_instrument_read(self):
        _, _, log = self.run_human(["1", "1"])
        self.assertIn("chooser instrument: ngspice_linear_passive", log)

    def test_halt_at_instrument_prompt(self):
        outcome, writes, log = self.run_human(["2", "n"])
        self.assertEqual(outcome, ("halt",))
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0]["human_decision"], "select rank 2")
        self.assertEqual(writes[1]["human_decision"], "halt (instrument prompt)")
        self.assertTrue(writes[1]["did_override"])

    def test_invalid_cap_halts_like_the_rank_prompt(self):
        bad = ["zzz"] * supervisor.MAX_GATE1_INVALID_ANSWERS
        outcome, writes, log = self.run_human(["1"] + bad)
        self.assertEqual(outcome, ("halt",))
        self.assertIn(
            f"{supervisor.MAX_GATE1_INVALID_ANSWERS} invalid instrument "
            "answers, halting",
            log,
        )
        self.assertEqual(len(writes), 2)
        self.assertIn("invalid instrument answers", writes[1]["human_decision"])

    def test_prompt_lists_the_live_routable_ids(self):
        _, _, log = self.run_human(["1", "1"])
        listing = ", ".join(
            f"{i}={sid}" for i, sid in enumerate(routable_ids(), start=1)
        )
        self.assertIn(listing, log)


class TestApplyGate1Selection(TmpRunDirCase):
    """2d: the R-23.5-4 payload write; substrate_id required, never defaulted."""

    def test_payload_is_exactly_the_ruled_three_keys(self):
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        supervisor.apply_gate1_selection(
            logger, baton, "auto", 2, self.run_dir,
            substrate_id="ngspice_linear_passive",
        )
        self.assertEqual(
            baton.payload,
            {
                "domain": "test domain",
                "chosen_hypothesis": {
                    "id": "h2",
                    "statement": "statement two",
                    "rationale": "rationale two",
                },
                "substrate_id": "ngspice_linear_passive",
            },
        )
        snapshot = json.loads(
            (self.run_dir / "baton_after_gate_1.json").read_text()
        )
        self.assertEqual(snapshot["payload"], baton.payload)

    def test_omitting_substrate_id_raises(self):
        # Escape-failing: a caller that fails to pass the gate's decision
        # raises — there is no default of any kind.
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        with self.assertRaises(TypeError):
            supervisor.apply_gate1_selection(
                logger, baton, "auto", 2, self.run_dir
            )


if __name__ == "__main__":
    unittest.main()
