"""
test_fidelity_ledger_substrate.py — the fidelity ledger records the ROUTED
substrate id, for every contract header format.

THE BUG THIS PINS (found 2026-07-20, run 20260719T231117Z). Stage 3 wrote the
ledger's `substrate` field by PARSING the substrate name off the contract's
first line, matching the literal prefix "SUBSTRATE CONTRACT:" — with a colon.
The five pre-bio contracts use that colon and parsed fine. All four MATURE bio
contracts (rdkit, cobrapy, mafft, homology_search) head their text with an EM
DASH — "SUBSTRATE CONTRACT — cobrapy, fba_steady_state" — so the parse missed
and the ledger banked `substrate: null` on a real, correctly-routed trust
verdict. The routed id was in scope at the call site the whole time.

Two entangled defects, both fixed by passing the routed id:

  (1) NULL ON EVERY BIO VERDICT — a trust with no named instrument. Weakest-link
      chain trust (Steps 31/32) is per-link attribution; a ledger that cannot
      name the link cannot support it.
  (2) THE PARSED NAME WAS NEVER THE ID — cavity's header says "cavity_2d" but
      its registry id is "cavity_2d_cfd", so even the entries that DID parse
      were not joinable against the registry.

Both are proven here BY FIRING, not argued: the em-dash substrate must record
its id, and the colon substrate must record its id too (not its header name).

ZERO live model calls (the transport is patched to a constructed verdict).

Run directly: venv/bin/python3 tests/test_fidelity_ledger_substrate.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import model_call  # noqa: E402
from baton import Baton  # noqa: E402
from stages import stage3_fidelity_gate as s3  # noqa: E402
from tools.substrate_registry import contract_for  # noqa: E402
from tools.substrate_selection import select_substrate  # noqa: E402


def _cavity_spec() -> dict:
    """The hand-authored baseline spec — routes to cavity_2d_cfd (colon header)."""
    return json.loads((ROOT / "specs" / "handcrafted_baseline_qoi.json").read_text())


def _cobrapy_spec() -> dict:
    """Declares min_growth, cobrapy's one declarable numeric knob — routes
    uniquely to cobrapy (em-dash header). Same shape as the D.4 routing proof."""
    return {
        "parameters": [{"name": "min_growth"}],
        "regime": {"notes": "in-regime by construction"},
        "qoi": {
            "name": "growth",
            "units": "1/h",
            "definition": "d",
            "how_extracted": "h",
            "quantity": "growth_rate",
        },
    }


class LedgerSubstrateCase(unittest.TestCase):
    """Drive the REAL stage-3 run() on a constructed verdict and capture what
    it hands the ledger writer."""

    def setUp(self):
        self._old_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def ledger_entry_for(self, spec: dict, substrate_id: str) -> dict:
        run_id = f"ledger-substrate-{substrate_id}"
        (Path("runs") / run_id).mkdir(parents=True, exist_ok=True)
        baton = Baton(
            run_id=run_id,
            created_at="2026-07-20T00:00:00+00:00",
            mode="auto",
            payload={
                "domain": "constructed",
                "chosen_hypothesis": {
                    "id": "h1",
                    "statement": "constructed",
                    "rationale": "constructed",
                },
                "substrate_id": substrate_id,
                "experiment_spec": spec,
            },
        )
        reply = json.dumps(
            {
                "ack_run_id": run_id,
                "verdict": {
                    "label": "trust",
                    "rationale": "constructed verdict for the ledger pin",
                    "right_instrument": "yes",
                },
            }
        )
        ledger: list[dict] = []
        with patch.object(
            model_call, "_invoke_transport", lambda sp, ut, m: reply
        ), patch.object(s3, "fidelity_append", lambda **kw: ledger.append(kw)):
            s3.run(baton)

        self.assertEqual(len(ledger), 1, "exactly one ledger entry per verdict")
        return ledger[0]


class TestRoutedSubstrateIsRecorded(LedgerSubstrateCase):

    def test_em_dash_contract_records_its_routed_id_not_null(self):
        """THE BUG, FIRED: cobrapy's em-dash header defeated the parser and
        banked substrate=null on a real trust verdict."""
        spec = _cobrapy_spec()
        self.assertEqual(select_substrate(spec), "cobrapy")  # precondition

        entry = self.ledger_entry_for(spec, "cobrapy")

        self.assertIsNotNone(
            entry["substrate"],
            "a trust verdict was banked with NO named substrate — the ledger "
            "cannot attribute this verdict to the instrument that earned it",
        )
        self.assertEqual(entry["substrate"], "cobrapy")

    def test_colon_contract_records_its_routed_id_not_its_header_name(self):
        """No regression on the old format — and the stricter half: cavity
        records its registry id, not the "cavity_2d" its header happens to say."""
        spec = _cavity_spec()
        self.assertEqual(select_substrate(spec), "cavity_2d_cfd")  # precondition

        entry = self.ledger_entry_for(spec, "cavity_2d_cfd")

        self.assertEqual(entry["substrate"], "cavity_2d_cfd")

    def test_recorded_substrate_is_always_a_registry_id(self):
        """The property both cases share, stated once: whatever lands in the
        ledger must be a real registry id — contract_for() resolves it."""
        for spec, sid in ((_cobrapy_spec(), "cobrapy"),
                          (_cavity_spec(), "cavity_2d_cfd")):
            with self.subTest(substrate=sid):
                recorded = self.ledger_entry_for(spec, sid)["substrate"]
                contract_for(recorded)  # LookupError/KeyError if not an id


class TestHeaderFormatsDiverge(unittest.TestCase):
    """WHY the parse-based approach could not have worked — the contract
    headers are not one format, and were never the id."""

    def test_bio_headers_use_an_em_dash_and_cavity_header_is_not_its_id(self):
        self.assertTrue(
            contract_for("cobrapy").strip().splitlines()[0].startswith(
                "SUBSTRATE CONTRACT —"
            )
        )
        self.assertTrue(
            contract_for("cavity_2d_cfd").strip().splitlines()[0].startswith(
                "SUBSTRATE CONTRACT:"
            )
        )
        # The colon format parsed — but to "cavity_2d", never the id.
        self.assertNotIn(
            "cavity_2d_cfd",
            contract_for("cavity_2d_cfd").strip().splitlines()[0],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
