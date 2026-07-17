"""
test_d5_entry_construction.py — D.5 (R1 option 4): the additive run-entry
schema widening and the ngspice entry constructor. Zero model calls, zero
solver calls: the validator is a pure payload -> [errors] function and
ngspice_run_entry is pure summary -> entry.

Two surfaces, tested ADDITIVELY (no existing test changed):

  1. The widened _check_execution_run_entry via validate_payload_post_stage4:
     an optional `state` (non-empty string) is admitted; the required set
     {converged, wall_clock_s, qoi_value|qoi_error} is unchanged; every
     OTHER unknown key is still rejected — the set stays closed except the
     one ruled optional. The scipy tri-state proof is SCHEMA-SIDE ONLY
     (state in {solved_verified, unevaluated, error} all admitted — the
     values come from tools/run_scipy.py's own tri-state, repo_facts §10.6);
     no scipy adapter exists, deliberately — that is its own promotion.

  2. tools.substrate_dispatch.ngspice_run_entry on run_ngspice-SHAPED canned
     literals (the wrapper's documented return contract,
     tools/run_ngspice.py:28 — D.4's canned summaries are cavity/run_cfd
     shapes, so ngspice literals are authored here, shaped on the return
     sites at run_ngspice.py:884 and :966): converged := (valid is True),
     wall_clock_s := runtime_s, valid=False -> qoi_error from diagnostics
     and never a fabricated qoi_value; structurally missing or ill-typed
     wrapper fields raise (the escape must fail loud, never default). NO
     `state` is wired for ngspice: the wrapper summary carries no
     own-vocabulary state field.

The passing base payload is the same tracked REAL evidence test_schemas.py
uses: specs/step15_executed_payload.json (RUN B handfeed4-20260706T045314Z).

Run directly: venv/bin/python3 tests/test_d5_entry_construction.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import validate_payload_post_stage4
from tools.substrate_dispatch import ngspice_run_entry

_PAYLOAD_FILE = (
    Path(__file__).resolve().parent.parent / "specs" / "step15_executed_payload.json"
)

# run_scipy's own tri-state (tools/run_scipy.py:117-119, repo_facts §10.6) —
# retyped HERE ONLY as test data proving the schema admits a tri-state; the
# schema itself never enumerates per-substrate values (contract-§3 material).
_SCIPY_TRISTATE = ("solved_verified", "unevaluated", "error")


def _executed_payload(runs: list[dict]) -> dict:
    """RUN B's pre-stage-4 payload plus an executed execution_results block
    carrying exactly the given run entries."""
    payload = json.loads(_PAYLOAD_FILE.read_text())
    payload.pop("provenance")
    payload["execution_results"] = {"status": "executed", "runs": runs}
    return payload


def _entry(**overrides) -> dict:
    """A minimal valid run entry; overrides layered on top."""
    entry = {"converged": True, "wall_clock_s": 0.26, "qoi_value": 0.909}
    entry.update(overrides)
    return entry


class TestWidenedRunEntrySchema(unittest.TestCase):
    """The D.5 widening: optional `state`, required set unchanged, set still
    closed against everything else."""

    def test_state_valid_string_accepted(self):
        payload = _executed_payload([_entry(state="solved_verified")])
        self.assertEqual(validate_payload_post_stage4(payload), [])

    def test_scipy_tristate_all_admitted(self):
        for value in _SCIPY_TRISTATE:
            with self.subTest(state=value):
                # error-state entries carry qoi_error, the honest pairing
                entry = (
                    _entry(converged=False, state=value)
                    if value == "error"
                    else _entry(state=value)
                )
                if value == "error":
                    del entry["qoi_value"]
                    entry["qoi_error"] = "solver reported an error state"
                payload = _executed_payload([entry])
                self.assertEqual(validate_payload_post_stage4(payload), [])

    def test_state_wrong_type_rejected(self):
        payload = _executed_payload([_entry(state=3)])
        errors = validate_payload_post_stage4(payload)
        self.assertTrue(any("state" in e for e in errors), errors)

    def test_state_empty_string_rejected(self):
        payload = _executed_payload([_entry(state="   ")])
        errors = validate_payload_post_stage4(payload)
        self.assertTrue(any("state" in e for e in errors), errors)

    def test_other_unknown_key_still_rejected(self):
        payload = _executed_payload([_entry(residual=1e-3)])
        errors = validate_payload_post_stage4(payload)
        self.assertTrue(any("'residual'" in e and "not allowed" in e for e in errors), errors)

    def test_state_alone_never_substitutes_for_required_keys(self):
        # state is additive only: an entry missing its qoi key still fails.
        entry = _entry(state="solved_verified")
        del entry["qoi_value"]
        payload = _executed_payload([entry])
        errors = validate_payload_post_stage4(payload)
        self.assertTrue(any("exactly one of" in e for e in errors), errors)


class TestNgspiceRunEntry(unittest.TestCase):
    """ngspice summary -> stage-4 run entry, per the staged contract §3
    mapping. Canned literals are run_ngspice-shaped (documented contract,
    tools/run_ngspice.py:28)."""

    # Shaped on run_ngspice.py:966 (the valid=True return site).
    VALID_SUMMARY = {
        "valid": True,
        "qoi": 0.9090909091,
        "diagnostics": "ngspice op on 3-element divider; qoi node_voltage "
        "out reduced op_value",
        "runtime_s": 0.26,
    }

    # Shaped on run_ngspice.py:884 (the valid=False return site).
    INVALID_SUMMARY = {
        "valid": False,
        "qoi": None,
        "diagnostics": "operating point failed: floating node detected by "
        "log failure marker; no number reported",
        "runtime_s": 0.31,
    }

    def test_valid_summary_constructs_converged_entry(self):
        entry = ngspice_run_entry(dict(self.VALID_SUMMARY))
        self.assertEqual(
            entry,
            {"converged": True, "wall_clock_s": 0.26, "qoi_value": 0.9090909091},
        )
        # exact key set — and NO state: run_ngspice has no own state vocabulary
        self.assertEqual(sorted(entry), ["converged", "qoi_value", "wall_clock_s"])

    def test_invalid_summary_constructs_qoi_error_entry(self):
        entry = ngspice_run_entry(dict(self.INVALID_SUMMARY))
        self.assertEqual(entry["converged"], False)
        self.assertEqual(entry["wall_clock_s"], 0.31)
        self.assertEqual(entry["qoi_error"], self.INVALID_SUMMARY["diagnostics"])
        self.assertNotIn("qoi_value", entry)
        self.assertEqual(sorted(entry), ["converged", "qoi_error", "wall_clock_s"])

    def test_constructed_entries_pass_the_widened_schema(self):
        runs = [
            ngspice_run_entry(dict(self.VALID_SUMMARY)),
            ngspice_run_entry(dict(self.INVALID_SUMMARY)),
        ]
        self.assertEqual(validate_payload_post_stage4(_executed_payload(runs)), [])

    def test_missing_field_raises_naming_it(self):
        for key in ("valid", "qoi", "diagnostics", "runtime_s"):
            with self.subTest(missing=key):
                summary = dict(self.VALID_SUMMARY)
                del summary[key]
                with self.assertRaises(ValueError) as ctx:
                    ngspice_run_entry(summary)
                self.assertIn(key, str(ctx.exception))

    def test_non_dict_summary_raises(self):
        with self.assertRaises(ValueError):
            ngspice_run_entry(None)

    def test_non_bool_valid_raises(self):
        with self.assertRaises(ValueError):
            ngspice_run_entry(dict(self.VALID_SUMMARY, valid="yes"))

    def test_non_number_runtime_raises(self):
        with self.assertRaises(ValueError):
            ngspice_run_entry(dict(self.VALID_SUMMARY, runtime_s=None))

    def test_valid_true_without_number_raises(self):
        # valid=true with qoi=None breaks the wrapper's own contract:
        # refuse to fabricate a qoi_value.
        with self.assertRaises(ValueError):
            ngspice_run_entry(dict(self.VALID_SUMMARY, qoi=None))

    def test_valid_false_without_diagnostics_raises(self):
        # a failed run must carry its named reason: refuse to invent one.
        with self.assertRaises(ValueError):
            ngspice_run_entry(dict(self.INVALID_SUMMARY, diagnostics="  "))


if __name__ == "__main__":
    unittest.main(verbosity=2)
