"""
test_d4_dispatch.py — D.4. Call-free by default: no model calls, no docker,
no subprocess (the one real-solve smoke is env-gated and skipped otherwise).

Proves stage 4's per-substrate execution dispatch (tools/substrate_dispatch),
which retires the hardcoded run_cfd call from stage4_simulation.run():

  (1) wrapper_callable resolves cavity FROM the registry row's wrapper field
      to the IDENTICAL tools/run_cfd.run_cfd object (assertIs — never a
      second wrapper table), and ngspice's row to run_ngspice; an unknown id
      raises KeyError.
  (2) adapter_for on the REAL registry: cavity -> the cavity adapter;
      ngspice -> LookupError (unwired), proven by failing the escape; an
      unknown id raises KeyError. No cavity fallback anywhere.
  (3) a cavity spec driven through the REAL run() on a CONSTRUCTED
      two-routable registry invokes run_cfd (spy) with UNCHANGED arguments
      and stays byte-identical to the step-0 fixture.
  (4) an ngspice spec on the constructed registry selects ngspice; the
      registered-for-tests adapter invokes run_ngspice (spy) with the
      correctly translated typed dict, asserted against run_ngspice's OWN
      validators — no subprocess.
  (5) run() on an ngspice spec WITHOUT an adapter registration raises
      LookupError AT DISPATCH: no wrapper call, no results.json —
      escape-failing.
  (6) input/QoI translation fails loud on anything untranslatable, naming
      every offender — never a silent drop or default.

Constructed registries follow tests/test_substrate_selection.py's precedent
(mock-patched routable set; ngspice stays routable=False in the real
registry). Every vocabulary/contract/adapter wiring here is IMPORTED from
its single source — run_ngspice's own constants, the onboarding contract via
importlib — never copied. Do NOT construct ngspice run entries here: the
{valid, qoi, diagnostics, runtime_s} -> run-entry boundary is D.5's
material; these tests stop at the wrapper-call boundary.

Run directly: venv/bin/python3 tests/test_d4_dispatch.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baton import Baton
from stages import stage4_simulation as s4
from tools import qoi_vocab
from tools import run_cfd as run_cfd_module
from tools import run_ngspice
from tools import substrate_dispatch as dispatch
from tools import substrate_registry as registry
from tools import substrate_selection as selection
from test_d4_entry_construction import D4, drive

# ngspice's contract, imported from its single source (never copied) — the
# same importlib path test_substrate_selection.py uses.
_NGSPICE_CONTRACT_PATH = (
    ROOT / "onboarding" / "ngspice_linear_passive" / "contract.py"
)
_spec = importlib.util.spec_from_file_location(
    "_ngspice_contract_for_d4_tests", _NGSPICE_CONTRACT_PATH
)
_ngspice_contract_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ngspice_contract_mod)
NGSPICE_CONTRACT = _ngspice_contract_mod.NGSPICE_LINEAR_PASSIVE_CONTRACT

# ngspice's wiring, each piece from the wrapper that owns it (never copied).
NGSPICE_SIGNATURE = frozenset(run_ngspice._REQUIRED_FIELDS)
NGSPICE_VOCAB = qoi_vocab.NamedQuantityVocab(
    kinds=run_ngspice._QOI_KINDS,
    target_re=run_ngspice._NAME_RE,
    reductions=run_ngspice._REDUCTIONS,
)

DIVIDER_BODY = "V1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k"


def _ngspice_registry(with_adapter: bool):
    """The constructed two-routable registry: ngspice promoted routable IN
    THE TESTS ONLY, wired from its single sources; the adapter registration
    is the piece under test, so it is optional."""
    patches = [
        mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", "ngspice_linear_passive"),
        ),
        mock.patch.dict(
            registry._CONTRACTS, {"ngspice_linear_passive": NGSPICE_CONTRACT}
        ),
        mock.patch.dict(
            selection._SIGNATURES, {"ngspice_linear_passive": NGSPICE_SIGNATURE}
        ),
        mock.patch.dict(
            qoi_vocab._VOCABS, {"ngspice_linear_passive": NGSPICE_VOCAB}
        ),
    ]
    if with_adapter:
        patches.append(
            mock.patch.dict(
                dispatch._ADAPTERS,
                {"ngspice_linear_passive": dispatch._ngspice_adapter},
            )
        )
    return patches


class _Stack:
    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        return False


def _ngspice_spec_qoi() -> dict:
    return {
        "name": "divider output voltage",
        "units": "V",
        "definition": "operating-point voltage at node out",
        "how_extracted": "op solve, v(out)",
        "kind": "node_voltage",
        "target": "out",
        "reduction": "op_value",
    }


def _ngspice_trust_baton() -> Baton:
    b = Baton(run_id="run-d4-ngspice", created_at="2026-07-17T00:00:00Z", mode="auto")
    b.payload = {
        "domain": "circuits",
        "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
        "experiment_spec": {
            "parameters": [{"name": "netlist_body"}, {"name": "analysis"}],
            "qoi": _ngspice_spec_qoi(),
            "mini_experiment": {
                "runs": [
                    {"netlist_body": DIVIDER_BODY, "analysis": {"type": "op"}}
                ]
            },
        },
        "fidelity_verdict": {
            "label": "trust",
            "rationale": "constructed d4 dispatch baton",
            "right_instrument": "constructed",
        },
    }
    return b


class TestWrapperCallable(unittest.TestCase):
    def test_cavity_resolves_to_the_identical_run_cfd_object(self):
        # (1) resolved FROM the registry row's wrapper field, at call time —
        # the very object tools/run_cfd exports, never a copy or a re-import
        self.assertIs(
            dispatch.wrapper_callable("cavity_2d_cfd"), run_cfd_module.run_cfd
        )

    def test_ngspice_row_resolves_to_run_ngspice(self):
        # reading the row implies no promotion: ngspice stays routable=False
        self.assertIs(
            dispatch.wrapper_callable("ngspice_linear_passive"),
            run_ngspice.run_ngspice,
        )
        self.assertFalse(registry.get("ngspice_linear_passive").routable)

    def test_unknown_id_raises_keyerror(self):
        with self.assertRaises(KeyError):
            dispatch.wrapper_callable("no_such_substrate")


class TestAdapterForRealRegistry(unittest.TestCase):
    def test_cavity_resolves_to_the_cavity_adapter(self):
        self.assertIs(
            dispatch.adapter_for("cavity_2d_cfd"), dispatch._cavity_adapter
        )

    def test_ngspice_unwired_raises_lookuperror_escape_failed(self):
        # failing the escape: the inner assertion only runs if a fallback
        # adapter is wrongly returned instead of the raise
        with self.assertRaises(LookupError) as ctx:
            got = dispatch.adapter_for("ngspice_linear_passive")
            self.assertIsNot(got, dispatch._cavity_adapter)
        self.assertIn("no execution adapter wired", str(ctx.exception))
        self.assertIn("must NOT fall back", str(ctx.exception))

    def test_unknown_id_raises_keyerror(self):
        with self.assertRaises(KeyError):
            dispatch.adapter_for("no_such_substrate")


class TestCavityDispatchThroughRun(unittest.TestCase):
    def test_two_routable_registry_cavity_spec_unchanged_call_and_bytes(self):
        # (3) the REAL run() on the constructed two-routable registry: the
        # cavity spec still selects cavity, run_cfd (spy inside drive()) is
        # invoked with the arguments the step-0 fixture pinned, and the data
        # surface stays byte-identical.
        with _Stack(_ngspice_registry(with_adapter=True)):
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
            got["results_bytes"], (D4 / "expected_results.json").read_bytes()
        )


class TestNgspiceAdapterAtTheWrapperBoundary(unittest.TestCase):
    def test_selection_and_dispatch_resolve_the_registered_adapter(self):
        with _Stack(_ngspice_registry(with_adapter=True)):
            spec = _ngspice_trust_baton().payload["experiment_spec"]
            sid = selection.select_substrate(spec)
            self.assertEqual(sid, "ngspice_linear_passive")
            self.assertIs(dispatch.adapter_for(sid), dispatch._ngspice_adapter)

    def test_adapter_invokes_wrapper_with_the_correctly_translated_dict(self):
        # (4) the translated typed input, asserted against run_ngspice's OWN
        # validators — never a re-implementation, no subprocess
        request = dispatch.ngspice_qoi_request(_ngspice_spec_qoi())
        self.assertEqual(
            request,
            {"kind": "node_voltage", "target": "out", "reduction": "op_value"},
        )
        sentinel = {"valid": True, "qoi": 6.6667, "diagnostics": "spy",
                    "runtime_s": 0.0}
        calls: list[dict] = []

        def spy(typed):
            calls.append(typed)
            return sentinel

        with mock.patch.object(run_ngspice, "run_ngspice", spy):
            summary = dispatch._ngspice_adapter(
                "ngspice_linear_passive",
                {"netlist_body": DIVIDER_BODY, "analysis": {"type": "op"}},
                "case_name_unused",
                {},
                request,
            )
        self.assertEqual(len(calls), 1)
        typed = calls[0]
        self.assertEqual(list(typed), list(run_ngspice._REQUIRED_FIELDS))
        self.assertEqual(typed["netlist_body"], DIVIDER_BODY)
        self.assertEqual(typed["analysis"], {"type": "op"})
        self.assertIs(typed["qoi"], request)
        # the wrapper's own validator accepts the translation verbatim
        cleaned = run_ngspice._validate_input(typed)
        self.assertEqual(cleaned["qoi"]["kind"], "node_voltage")
        self.assertEqual(cleaned["qoi"]["at"], None)
        # the summary is returned VERBATIM: no entry construction, no
        # valid->converged mapping — that boundary is D.5's material
        self.assertIs(summary, sentinel)

    def test_value_at_request_carries_at_through(self):
        qoi = dict(_ngspice_spec_qoi(), reduction="value_at", at=1000.0)
        self.assertEqual(
            dispatch.ngspice_qoi_request(qoi),
            {"kind": "node_voltage", "target": "out",
             "reduction": "value_at", "at": 1000.0},
        )


class TestRunEscapeFailsOnUnwiredDispatch(unittest.TestCase):
    def test_run_raises_at_dispatch_no_wrapper_call_no_results(self):
        # (5) selection picks ngspice, but NO adapter is registered: run()
        # must raise at dispatch, before any translation or wrapper call,
        # and write no results.json — never fall back to the cavity path.
        baton = _ngspice_trust_baton()
        wrapper_calls: list = []
        old_cwd = os.getcwd()
        tmp = tempfile.mkdtemp(prefix="d4_escape_")
        try:
            os.chdir(tmp)
            with _Stack(_ngspice_registry(with_adapter=False)):
                with mock.patch.object(
                    run_ngspice, "run_ngspice",
                    lambda typed: wrapper_calls.append(typed),
                ), mock.patch.object(
                    run_cfd_module, "run_cfd",
                    lambda case, qoi_request=None: wrapper_calls.append(case),
                ):
                    with self.assertRaises(LookupError) as ctx:
                        s4.run(baton)
            self.assertIn("no execution adapter wired", str(ctx.exception))
            self.assertEqual(wrapper_calls, [])
            self.assertFalse(
                (Path("runs") / baton.run_id / "stage4" / "results.json").exists()
            )
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmp, ignore_errors=True)


class TestFailLoudTranslation(unittest.TestCase):
    def test_qoi_missing_machine_keys_raises_naming_them(self):
        prose_only = {"name": "corner", "units": "Hz",
                      "definition": "…", "how_extracted": "…"}
        with self.assertRaises(ValueError) as ctx:
            dispatch.ngspice_qoi_request(prose_only)
        for key in run_ngspice._REQUIRED_QOI_FIELDS:
            self.assertIn(key, str(ctx.exception))

    def test_qoi_non_dict_raises(self):
        with self.assertRaises(ValueError):
            dispatch.ngspice_qoi_request(None)

    def test_params_unknown_key_raises_naming_it_wrapper_untouched(self):
        calls: list = []
        with mock.patch.object(
            run_ngspice, "run_ngspice", lambda typed: calls.append(typed)
        ):
            with self.assertRaises(ValueError) as ctx:
                dispatch._ngspice_adapter(
                    "ngspice_linear_passive",
                    {"netlist_body": DIVIDER_BODY, "analysis": {"type": "op"},
                     "lid_velocity": 2.0},
                    "case", {},
                    dispatch.ngspice_qoi_request(_ngspice_spec_qoi()),
                )
        self.assertIn("lid_velocity", str(ctx.exception))
        self.assertIn("netlist_body", str(ctx.exception))
        self.assertEqual(calls, [])

    def test_params_missing_key_raises_naming_it_wrapper_untouched(self):
        calls: list = []
        with mock.patch.object(
            run_ngspice, "run_ngspice", lambda typed: calls.append(typed)
        ):
            with self.assertRaises(ValueError) as ctx:
                dispatch._ngspice_adapter(
                    "ngspice_linear_passive",
                    {"netlist_body": DIVIDER_BODY},
                    "case", {},
                    dispatch.ngspice_qoi_request(_ngspice_spec_qoi()),
                )
        self.assertIn("analysis", str(ctx.exception))
        self.assertEqual(calls, [])

    def test_untranslated_qoi_request_raises_never_a_default(self):
        calls: list = []
        with mock.patch.object(
            run_ngspice, "run_ngspice", lambda typed: calls.append(typed)
        ):
            with self.assertRaises(ValueError) as ctx:
                dispatch._ngspice_adapter(
                    "ngspice_linear_passive",
                    {"netlist_body": DIVIDER_BODY, "analysis": {"type": "op"}},
                    "case", {}, None,
                )
        self.assertIn("refusing to invent a default", str(ctx.exception))
        self.assertEqual(calls, [])


class TestTranslateQoiVocabSeam(unittest.TestCase):
    def test_bare_call_equals_explicit_cavity_vocab_call(self):
        # the pre-D.4 single-argument shape resolves the record structurally
        # and matches the explicit cavity record — same objects, same result
        spec_qoi = {"name": "x", "field": "U", "operation": "volAverage",
                    "component": "mag"}
        self.assertEqual(
            s4.translate_qoi(spec_qoi),
            s4.translate_qoi(spec_qoi, qoi_vocab.vocab_for("cavity_2d_cfd")),
        )

    def test_cavity_vocab_members_are_run_cfds_objects(self):
        # P1 pattern: the re-checks read the wrapper's OWN objects
        vocab = qoi_vocab.vocab_for("cavity_2d_cfd")
        self.assertIs(vocab.operations, run_cfd_module.QOI_OPERATIONS)
        self.assertIs(vocab.components, run_cfd_module.QOI_COMPONENTS)


@unittest.skipUnless(
    os.environ.get("D4_NGSPICE_SMOKE") == "1",
    "real ngspice solve — set D4_NGSPICE_SMOKE=1 (needs colima + ngspice-prod)",
)
class TestRealNgspiceSmoke(unittest.TestCase):
    def test_adapter_end_to_end_divider_solve(self):
        summary = dispatch._ngspice_adapter(
            "ngspice_linear_passive",
            {"netlist_body": DIVIDER_BODY, "analysis": {"type": "op"}},
            "case_name_unused",
            {},
            dispatch.ngspice_qoi_request(_ngspice_spec_qoi()),
        )
        self.assertTrue(summary["valid"], summary["diagnostics"])
        analytic = run_ngspice.analytic_divider_vout(10.0, 1e3, 2e3)
        self.assertAlmostEqual(summary["qoi"], analytic, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
