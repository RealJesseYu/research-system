"""
test_d4_entry_construction.py — D.4 step 0 fixture (standing rule, data-surface
variant). Call-free: no model calls, no solver, no docker.

REGISTERED PREDICTION CONFIRMED FROM DISK: before this file, cavity's stage-4
ENTRY CONSTRUCTION — stages/stage4_simulation.py:103-115 building the locked
{converged, wall_clock_s, qoi_value|qoi_error} run entries, plus the
results.json bytes run() writes — was pinned NOWHERE on canned wrapper output:
tests/test_stage4_case_builder.py exercises only the pure translate_qoi,
tests/test_loop_controller.py and tests/test_retry_total_defer.py drive STUB
stage-4 callables, and tests/fixtures/d0/canned_stage4_results.json is
CONSUMED as stage-5 input (test_d0_stage5_input.py), never produced by
stage 4. This test closes that hole ON THE UNTOUCHED TREE, before D.4's
dispatch surgery, so the surgery can be proven byte-neutral on the cavity
data surface.

Inputs are reused, never copied: the canned baton
(tests/fixtures/d4/canned_stage4_input.json) is d0's canned stage-5 input
MINUS execution_results — the post-stage-3 trust baton whose two mini-runs
produced exactly the d0 canned wrapper summaries — and the wrapper stub
returns those summaries verbatim from
tests/fixtures/d0/canned_stage4_results.json (runs[].summary).

SEAMS ARE ERA-STABLE BY CONSTRUCTION. Pre-D.4, stage4_simulation binds
build_case and run_cfd into its own namespace at import time; post-D.4,
dispatch resolves the builder and the wrapper at CALL time (from the builder
module and the registry row). The patch helpers below pick whichever seam the
current tree exposes — the construction under test is identical either way,
which is exactly what the fixture pins.

Run directly: venv/bin/python3 tests/test_d4_entry_construction.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton
from schemas import validate_payload_post_stage4
from stages import stage4_simulation as s4

FIXTURES = Path(__file__).resolve().parent / "fixtures"
D4 = FIXTURES / "d4"
D0 = FIXTURES / "d0"

# The canned wrapper summaries, reused from d0 (never a second copy): the two
# full run_cfd summaries the d0 results file records for the canned baton's
# two mini-runs, in mini-run order.
_D0_RESULTS = json.loads((D0 / "canned_stage4_results.json").read_text())
CANNED_SUMMARIES = [entry["summary"] for entry in _D0_RESULTS["runs"]]


def _patch_build_case(stub):
    """Patch the case builder at whichever seam the current tree exposes:
    pre-D.4 the name is bound into stage4_simulation's namespace; post-D.4
    dispatch late-binds it from the builder module at call time."""
    if hasattr(s4, "build_case"):
        return mock.patch.object(s4, "build_case", stub)
    from stages import stage4_case_builder

    return mock.patch.object(stage4_case_builder, "build_case", stub)


def _patch_wrapper(stub):
    """Patch the cavity wrapper at whichever seam the current tree exposes:
    pre-D.4 stage4_simulation binds run_cfd at import time; post-D.4 dispatch
    resolves it at call time from the registry row's wrapper field."""
    if hasattr(s4, "run_cfd"):
        return mock.patch.object(s4, "run_cfd", stub)
    from tools import run_cfd as run_cfd_module

    return mock.patch.object(run_cfd_module, "run_cfd", stub)


def drive() -> dict:
    """Drive the REAL stage4_simulation.run() on the canned trust baton with
    the builder stubbed to a no-op and the wrapper stubbed to the canned d0
    summaries. Returns everything the fixture pins: the results.json bytes,
    the payload execution_results, the history note, and the exact
    builder/wrapper call arguments."""
    baton = Baton.from_json((D4 / "canned_stage4_input.json").read_text())

    build_calls: list[dict] = []
    wrapper_calls: list[dict] = []
    summaries = iter(CANNED_SUMMARIES)

    def build_stub(params, case_name, roles=None, **kwargs):
        build_calls.append(
            {"params": params, "case_name": case_name, "roles": roles, **kwargs}
        )

    def wrapper_stub(case, qoi_request=None):
        wrapper_calls.append({"case": case, "qoi_request": qoi_request})
        return next(summaries)

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="d4_stage4_")
    try:
        os.chdir(tmp)  # run() writes runs/<id>/ relative to cwd
        with _patch_build_case(build_stub), _patch_wrapper(wrapper_stub):
            out = s4.run(baton)
        results_bytes = (
            Path("runs") / baton.run_id / "stage4" / "results.json"
        ).read_bytes()
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "results_bytes": results_bytes,
        "execution_results": out.payload["execution_results"],
        "payload": out.payload,
        "history_note": out.history[-1]["note"],
        "build_calls": build_calls,
        "wrapper_calls": wrapper_calls,
    }


class EntryConstructionByteIdentity(unittest.TestCase):
    def test_results_json_bytes_identical_to_fixture(self):
        got = drive()
        self.assertEqual(
            got["results_bytes"], (D4 / "expected_results.json").read_bytes()
        )

    def test_execution_results_identical_to_fixture(self):
        got = drive()
        self.assertEqual(
            json.dumps(got["execution_results"], indent=2) + "\n",
            (D4 / "expected_execution_results.json").read_text(),
        )

    def test_run_entries_are_the_locked_conclusions_shape(self):
        # the locked {converged, wall_clock_s, qoi_value|qoi_error} entries,
        # via the boundary schema itself — never a re-implementation here
        got = drive()
        self.assertEqual(validate_payload_post_stage4(got["payload"]), [])
        for entry in got["execution_results"]["runs"]:
            self.assertEqual(
                sorted(entry), ["converged", "qoi_value", "wall_clock_s"]
            )

    def test_history_note_is_the_code_authored_conclusion(self):
        got = drive()
        self.assertEqual(
            got["history_note"],
            "executed 2 mini-run(s): 2 converged, 2 QoI extracted",
        )

    def test_wrapper_called_with_unchanged_arguments(self):
        # the exact cavity wrapper call D.4's dispatch must resolve to,
        # pinned BEFORE the surgery: (case_name, qoi_request=<translated>)
        got = drive()
        expected_request = {
            "field": "U",
            "operation": "volAverage",
            "component": "mag",
        }
        self.assertEqual(
            got["wrapper_calls"],
            [
                {"case": "d0-canned-cavity_run1", "qoi_request": expected_request},
                {"case": "d0-canned-cavity_run2", "qoi_request": expected_request},
            ],
        )
        self.assertEqual(
            [c["case_name"] for c in got["build_calls"]],
            ["d0-canned-cavity_run1", "d0-canned-cavity_run2"],
        )

    def test_construction_is_deterministic_on_fixed_input(self):
        first, second = drive(), drive()
        self.assertEqual(first["results_bytes"], second["results_bytes"])
        self.assertEqual(first["execution_results"], second["execution_results"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
