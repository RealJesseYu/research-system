"""
test_gate1_chooser.py — the Stage-1.5 gate-1 chooser (Step 23). ZERO live
model calls: model_call._invoke_transport is patched with fakes throughout
(the test_meta_review pattern). Each test runs in a temporary cwd so the
Path("runs")-derived evidence, transcripts, and log writes never touch the
project's runs/, and supervisor.override_append is patched in the
human-mode test so the frozen override ledger is never written.

Covered: the chooser selecting a non-rank-1 hypothesis on reasoning (and
the evidence sections actually reaching the assembled model input on the
CHOOSER_MODEL pin); repeated invalid chosen_id burning the RE-ASK budget
then falling back to rank 1 with fallback=true recorded; transport
exhaustion falling back the same way without raising; human mode's
advisory display leaving the payload and the human decision provably
untouched; and auto mode's baton carrying the chosen hypothesis through
apply_gate1_selection exactly as gate-1 selection always has.

Run directly: venv/bin/python3 tests/test_gate1_chooser.py
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

import model_call
import supervisor
from baton import Baton
from stages import gate1_chooser
from stages.gate1_chooser import CHOOSER_MODEL, choose_hypothesis

RUN_ID = "chooser-test"

HYPOTHESES = [
    {"id": "h1", "statement": "statement one", "rationale": "rationale one"},
    {"id": "h2", "statement": "statement two", "rationale": "rationale two"},
    {"id": "h3", "statement": "statement three", "rationale": "rationale three"},
]

GOOD_REPLY_H2 = json.dumps(
    {
        "ack_run_id": RUN_ID,
        "chosen_id": "h2",
        "reasoning": "Near-tie in Elo and h2 carries lighter addressable concerns.",
    }
)


def make_transport(reply=None, exception=None, calls=None):
    """Fake for model_call._invoke_transport: records each call, then either
    raises `exception` or returns `reply` (verbatim every attempt)."""

    def fake(system_prompt, user_turn, model):
        if calls is not None:
            calls.append(
                {"system_prompt": system_prompt, "user_turn": user_turn, "model": model}
            )
        if exception is not None:
            raise exception
        return reply

    return fake


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


class Gate1ChooserTest(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        self.run_dir = Path("runs") / RUN_ID
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def seed_stage1_evidence(self):
        stage1 = self.run_dir / "stage1"
        stage1.mkdir(parents=True)
        (stage1 / "survivors.json").write_text(
            json.dumps(
                [
                    {"id": "h1", "addressable_notes": ["needs finer mesh"]},
                    {"id": "h2", "addressable_notes": []},
                    # h3 deliberately absent — an accepted Evolution variant
                    # never appears in survivors.json.
                ]
            )
        )
        (stage1 / "tournament_state.json").write_text(
            json.dumps(
                {
                    "final_ranking": [
                        {"id": "h1", "elo": 1201.2},
                        {"id": "h2", "elo": 1200.4},
                        {"id": "h3", "elo": 1130.0},
                    ]
                }
            )
        )
        (stage1 / "research_overview.json").write_text(
            json.dumps({"directions": [{"summary": "pursue near-wall scaling"}]})
        )

    # --- chooser selects non-rank-1 when reasoning says so ---

    def test_chooser_selects_non_rank1_with_evidence_in_input(self):
        self.seed_stage1_evidence()
        calls = []
        with patch.object(
            model_call, "_invoke_transport", make_transport(GOOD_REPLY_H2, calls=calls)
        ):
            record = choose_hypothesis(RUN_ID, HYPOTHESES, self.run_dir)

        self.assertEqual(record["chosen_id"], "h2")
        self.assertFalse(record["fallback"])
        self.assertIn("lighter addressable concerns", record["reasoning"])

        # The record is durable evidence in the run dir.
        on_disk = json.loads((self.run_dir / "gate1_chooser.json").read_text())
        self.assertEqual(on_disk, record)

        # One call, on the ruled pin, and every evidence section reached the
        # assembled input — including the variant-shaped empty notes for h3.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], CHOOSER_MODEL)
        sent = json.loads(calls[0]["user_turn"])
        self.assertEqual(
            [h["id"] for h in sent["ranked_hypotheses"]], ["h1", "h2", "h3"]
        )
        self.assertEqual(sent["ranked_hypotheses"][0]["rank"], 1)
        self.assertEqual(sent["elo_table"][1], {"id": "h2", "elo": 1200.4})
        self.assertEqual(sent["addressable_notes"]["h1"], ["needs finer mesh"])
        self.assertEqual(sent["addressable_notes"]["h3"], [])
        self.assertEqual(
            sent["research_overview_directions"], ["pursue near-wall scaling"]
        )

    def test_auto_mode_resolves_to_chooser_pick(self):
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        with patch.object(
            model_call, "_invoke_transport", make_transport(GOOD_REPLY_H2)
        ):
            outcome = supervisor.run_gate1(logger, baton, "auto")
        self.assertEqual(outcome, ("select", 2))
        log_text = (self.run_dir / "log.txt").read_text()
        self.assertIn("chooser chose h2 (rank 2 of 3, fallback=False)", log_text)

    # --- invalid chosen_id: re-ask, then fall back to rank 1 ---

    def test_invalid_chosen_id_reasks_then_falls_back(self):
        bad_reply = json.dumps(
            {"ack_run_id": RUN_ID, "chosen_id": "zz", "reasoning": "confidently wrong"}
        )
        calls = []
        with patch.object(
            model_call, "_invoke_transport", make_transport(bad_reply, calls=calls)
        ):
            record = choose_hypothesis(RUN_ID, HYPOTHESES, self.run_dir)

        # The full bounded RE-ASK budget was spent before falling back.
        self.assertEqual(len(calls), model_call.MAX_ATTEMPTS)
        self.assertIn("validation_error", calls[1]["user_turn"])
        self.assertEqual(record["chosen_id"], "h1")
        self.assertTrue(record["fallback"])
        self.assertIn("fallback to rank 1", record["reasoning"])
        on_disk = json.loads((self.run_dir / "gate1_chooser.json").read_text())
        self.assertTrue(on_disk["fallback"])
        self.assertEqual(on_disk["chosen_id"], "h1")

    # --- transport exhaustion: fall back, never crash ---

    def test_transport_exhaustion_falls_back(self):
        with patch.object(model_call, "TRANSPORT_RETRY_BACKOFFS", ()), patch.object(
            model_call,
            "_invoke_transport",
            make_transport(exception=ConnectionError("transport down")),
        ):
            record = choose_hypothesis(RUN_ID, HYPOTHESES, self.run_dir)
        self.assertEqual(record["chosen_id"], "h1")
        self.assertTrue(record["fallback"])
        self.assertIn("transport down", record["reasoning"])

    def test_ack_mismatch_falls_back(self):
        wrong_ack = json.dumps(
            {"ack_run_id": "some-other-run", "chosen_id": "h2", "reasoning": "fine"}
        )
        with patch.object(model_call, "_invoke_transport", make_transport(wrong_ack)):
            record = choose_hypothesis(RUN_ID, HYPOTHESES, self.run_dir)
        self.assertEqual(record["chosen_id"], "h1")
        self.assertTrue(record["fallback"])
        self.assertIn("ack_run_id mismatch", record["reasoning"])

    # --- human mode: advisory is display-only ---

    def test_human_mode_payload_unchanged_and_pick_decides(self):
        baton = make_baton()
        payload_before = json.dumps(baton.payload, sort_keys=True)
        logger = supervisor.Logger(self.run_dir / "log.txt")
        ledger_writes = []
        with patch.object(
            model_call, "_invoke_transport", make_transport(GOOD_REPLY_H2)
        ), patch.object(
            supervisor, "override_append", lambda **kw: ledger_writes.append(kw)
        ), patch(
            "builtins.input", return_value="3"
        ):
            outcome = supervisor.run_gate1(logger, baton, "human")

        # The human's integer pick decides, not the chooser's h2.
        self.assertEqual(outcome, ("select", 3))
        # The payload is provably untouched by the advisory display.
        self.assertEqual(json.dumps(baton.payload, sort_keys=True), payload_before)
        # The advisory block is durable in the log, chooser pick visible.
        log_text = (self.run_dir / "log.txt").read_text()
        self.assertIn("CHOOSER ADVISORY (display-only; your pick decides)", log_text)
        self.assertIn("chooser chose: h2", log_text)
        # Frozen ledger semantics: system_decision baseline stays rank 1.
        self.assertEqual(len(ledger_writes), 1)
        self.assertEqual(ledger_writes[0]["system_decision"], "select rank 1")
        self.assertEqual(ledger_writes[0]["human_decision"], "select rank 3")

    def test_advisory_builder_never_raises(self):
        self.assertIn("chooser chose: h2", supervisor.build_gate1_chooser_advisory(
            {"chosen_id": "h2", "reasoning": "because", "fallback": False}
        ))
        self.assertIn("FALLBACK to rank 1", supervisor.build_gate1_chooser_advisory(
            {"chosen_id": "h1", "reasoning": "fallback to rank 1: x", "fallback": True}
        ))
        self.assertIn("?", supervisor.build_gate1_chooser_advisory({}))
        self.assertIn("unavailable", supervisor.build_gate1_chooser_advisory(None))

    # --- auto mode: baton carries the chosen hypothesis exactly as always ---

    def test_auto_mode_baton_carries_chosen_hypothesis(self):
        baton = make_baton()
        logger = supervisor.Logger(self.run_dir / "log.txt")
        with patch.object(
            model_call, "_invoke_transport", make_transport(GOOD_REPLY_H2)
        ):
            outcome = supervisor.run_gate1(logger, baton, "auto")
        supervisor.apply_gate1_selection(
            logger, baton, "auto", outcome[1], self.run_dir
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
            },
        )
        snapshot = json.loads((self.run_dir / "baton_after_gate_1.json").read_text())
        self.assertEqual(snapshot["payload"], baton.payload)


if __name__ == "__main__":
    unittest.main()
