"""
test_chain_runner.py — CHAIN BUILD v1 (Steps 31/32) acceptance.

What is proven here, none of it argued:

  T1 ERA HOLDS — the whole single-node production surface is byte-identical
     to HEAD (git, not assertion), and an ordinary single-node spec still
     validates through the unchanged `validate_spec`. Proven FIRST.
  T2 CHAIN CLOSES — a REAL two-node chain (rdkit then mafft, both routable,
     both MATURE, both executing live in this environment) closes with real
     run entries carrying real numbers on both nodes.
  T3 WEAKEST LINK — the crown jewel, proven BY FIRING: the chain verdict is
     the MINIMUM over defer < refine < trust, asserted against a computed
     minimum across every label combination, never a fixed value.
  T4 FAIL-LOUD — an unroutable node and a CaseSynthesisError each halt the
     chain honestly (halted_synthesis), with no crash and no cavity anywhere.
  T5 R-B-1 STILL FIRES — an ambiguous SINGLE spec still hits the loud stop
     naming its candidates. The exemption did not weaken it.
  T6 R-B-1 EXEMPTS CHAINS — the SAME spec, named as chain nodes, routes both
     nodes without the stop firing. T5 and T6 differ by exactly one thing:
     whether the node names its substrate.

Live wrapper calls: rdkit and mafft only (pure local libraries, sub-second,
no docker, no network). ZERO model calls — verdicts are supplied by the test
through `verdict_fn`, which is exactly how the module refuses to invent one.

Run directly: venv/bin/python3 tests/test_chain_runner.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages import chain_runner
from stages.chain_runner import (
    VERDICT_STRENGTH,
    chain_verdict,
    route_node,
    run_chain,
    validate_chain,
)
from stages.stage2_spec import validate_spec
from stages.stage4_case_builder import CaseSynthesisError
from tools.qoi_vocab import vocab_for
from tools.substrate_selection import select_substrate

# The single-node production surface. The chain path is a NEW module; if any
# of these moved, the era claim is false.
FROZEN_SURFACE = (
    "schemas.py",
    "substrates.py",
    "stages/stage2_spec.py",
    "stages/stage3_fidelity_gate.py",
    "stages/stage4_simulation.py",
    "stages/stage4_case_builder.py",
    "tools/substrate_selection.py",
    "tools/substrate_dispatch.py",
    "tools/substrate_registry.py",
    "tools/qoi_vocab.py",
)


def _spec(regime: dict, quantity: str) -> dict:
    """A FULL stage-2-valid spec. Declares no parameters on purpose: the bio
    wrappers' content is a categorical instrument-instance selector, which
    validate_spec forbids as a parameter, so it rides the regime block and is
    threaded by regime_content_inputs. A zero-parameter spec is also
    genuinely AMBIGUOUS to structural selection — which is what makes the
    T5/T6 pair a clean one-variable comparison."""
    return {
        "hypothesis_id": "h1",
        "title": "t",
        "objective": "o",
        "parameters": [],
        "regime": regime,
        "qoi": {"name": "q", "units": "u", "definition": "d",
                "how_extracted": "h", "quantity": quantity},
        "success_criterion": {"statement": "s", "threshold": 10.0,
                              "direction": "above"},
        "mini_experiment": {"expected_observation": "e", "runs": [{}]},
        "full_experiment": {"design": "d", "estimated_run_count": 4},
    }


def _rdkit_spec() -> dict:
    return _spec({"notes": "small molecule, in envelope", "smiles": "CCO"}, "MolWt")


def _mafft_spec() -> dict:
    return _spec(
        {"notes": "two short nt sequences", "sequences": ["AAAACCCC", "AAAACCCG"]},
        "alignment_identity",
    )


def _ambiguous_spec() -> dict:
    """A spec that declares NOTHING structural: no parameters to narrow on at
    L0, no regime dict at L1a, no qoi dict at L1b. Every mature substrate
    serves it, so selection genuinely cannot tell which one is meant — this
    is the exact shape R-B-1 exists to refuse.

    (The full node specs above are NOT ambiguous: their `quantity` is admitted
    by exactly one substrate's QoI vocabulary, so L1b narrows them to one.
    That is why the T5/T6 pair is built on this bare spec instead — the
    comparison has to be about naming, not about narrowing.)
    """
    return {"parameters": []}


def _chain() -> dict:
    return {"nodes": [
        {"substrate_id": "rdkit", "spec": _rdkit_spec()},
        {"substrate_id": "mafft", "spec": _mafft_spec()},
    ]}


def _verdict(label: str) -> dict:
    return {"label": label, "rationale": f"{label} for test",
            "right_instrument": "yes"}


def _verdicts(*labels):
    """A verdict_fn returning the given label per node index — the ONLY way a
    verdict enters this module (there is no default and no stub)."""
    return lambda index, node, substrate_id: _verdict(labels[index])


@contextmanager
def _tmp_cwd():
    """Run chain writes into a throwaway tree, so runs/ (append-only evidence)
    is never polluted by tests."""
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(previous)


# --------------------------------------------------------------------------
# T1 — ERA HOLDS (proven first)
# --------------------------------------------------------------------------

class TestT1EraHolds(unittest.TestCase):

    def test_production_surface_byte_identical_to_head(self):
        """The chain build touched NO file on the single-node path."""
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", *FROZEN_SURFACE],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(
            changed, [],
            f"the single-node production surface moved: {changed} — the era "
            f"claim is false",
        )

    def test_schemas_py_specifically_untouched(self):
        """A5: independent nodes force NO baton change. schemas.py is the
        closed-key-set file; if the chain needed baton cargo it would show
        here."""
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "schemas.py"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(changed, "", "schemas.py changed — the baton moved")

    def test_single_node_spec_still_validates_through_the_unchanged_path(self):
        for sid, spec in (("rdkit", _rdkit_spec()), ("mafft", _mafft_spec())):
            with self.subTest(sid=sid):
                self.assertEqual(validate_spec(spec, "h1", vocab_for(sid)), [])


# --------------------------------------------------------------------------
# T5 / T6 — R-B-1
# --------------------------------------------------------------------------

class TestT5AmbiguityStopStillFires(unittest.TestCase):

    def test_ambiguous_single_spec_still_hits_the_loud_stop(self):
        """T5: an ambiguous SINGLE spec still stops loudly under R-B-1 and
        still names its candidates. The chain exemption weakened nothing."""
        with self.assertRaises(LookupError) as ctx:
            select_substrate(_ambiguous_spec())
        message = str(ctx.exception)
        self.assertIn("ambiguous (R-B-1", message)
        self.assertIn("4 candidates", message)
        for sid in ("rdkit", "cobrapy", "homology_search", "mafft"):
            self.assertIn(sid, message)

    def test_unnamed_chain_node_is_not_exempt(self):
        """The exemption is earned by NAMING, not by sitting in a chain. A
        node with no substrate_id falls through to selection and stops."""
        with self.assertRaises(LookupError) as ctx:
            route_node({"spec": _ambiguous_spec()})
        self.assertIn("R-B-1", str(ctx.exception))


class TestT6ChainNodesAreExempt(unittest.TestCase):

    def test_the_exact_spec_that_fires_rb1_routes_once_its_node_names_it(self):
        """T6, the one-variable proof: byte-for-byte the spec that raises in
        T5. The ONLY change is that the node names its substrate — deliberate
        multiplicity, not ambiguity (R1)."""
        spec = _ambiguous_spec()
        with self.assertRaises(LookupError):        # unnamed: still refused
            select_substrate(spec)
        for sid in ("rdkit", "mafft"):              # named: routes, no stop
            with self.subTest(sid=sid):
                self.assertEqual(route_node({"substrate_id": sid, "spec": spec}), sid)

    def test_named_nodes_route_without_the_stop_firing(self):
        """T6: byte-for-byte the spec that fires R-B-1 in T5 — the ONLY
        difference is that the node names its substrate."""
        routed = [route_node(node) for node in _chain()["nodes"]]
        self.assertEqual(routed, ["rdkit", "mafft"])

    def test_full_chain_validates_with_no_ambiguity_error(self):
        self.assertEqual(validate_chain(_chain()), [])

    def test_named_node_is_still_stopped_when_unroutable(self):
        """The exemption covers ambiguity ONLY. Naming a parked substrate
        still stops loudly."""
        with self.assertRaises(LookupError) as ctx:
            route_node({"substrate_id": "alphafold_db", "spec": _rdkit_spec()})
        message = str(ctx.exception)
        self.assertIn("not routable", message)
        self.assertNotIn("cavity_2d_cfd", message.split("routable set is")[0])

    def test_named_node_is_still_stopped_when_it_cannot_serve_its_spec(self):
        """Naming an instrument does not make it able to run the spec."""
        spec = _rdkit_spec()
        spec["parameters"] = [
            {"name": "lid_velocity", "role": "fixed", "value": 1.0, "units": "m/s"}
        ]
        with self.assertRaises(LookupError) as ctx:
            route_node({"substrate_id": "rdkit", "spec": spec})
        self.assertIn("cannot serve", str(ctx.exception))
        self.assertIn("lid_velocity", str(ctx.exception))


# --------------------------------------------------------------------------
# T3 — WEAKEST LINK
# --------------------------------------------------------------------------

class TestT3WeakestLink(unittest.TestCase):

    def test_chain_verdict_is_the_minimum_over_every_combination(self):
        """Asserted against a COMPUTED minimum — never a fixed value."""
        labels = ("defer", "refine", "trust")
        for a in labels:
            for b in labels:
                with self.subTest(a=a, b=b):
                    got = chain_verdict([_verdict(a), _verdict(b)])
                    expected = min((a, b), key=lambda x: VERDICT_STRENGTH[x])
                    self.assertEqual(got["label"], expected)
                    self.assertEqual(got["node_labels"], [a, b])

    def test_the_reduction_is_not_merely_the_last_node(self):
        """Guards the reduction against a positional look-alike."""
        got = chain_verdict([_verdict("defer"), _verdict("trust")])
        self.assertEqual(got["label"], "defer")
        self.assertEqual(got["weakest_node"], 0)

    def test_unknown_label_raises_rather_than_reducing(self):
        with self.assertRaises(ValueError) as ctx:
            chain_verdict([_verdict("trust"), {"label": "probably_fine"}])
        self.assertIn("probably_fine", str(ctx.exception))


class TestT3WeakestLinkByFiring(unittest.TestCase):
    """The crown jewel through the REAL chain — routing, live execution and
    the reduction, not the pure function alone."""

    def test_trust_then_defer_gives_defer(self):
        with _tmp_cwd():
            record = run_chain("wl-a", _chain(), verdict_fn=_verdicts("trust", "defer"))
        self.assertEqual(record["chain_verdict"]["label"], "defer")
        self.assertEqual(record["chain_verdict"]["node_labels"], ["trust", "defer"])
        # and it is the MINIMUM, recomputed here from what actually happened
        self.assertEqual(
            record["chain_verdict"]["label"],
            min(record["chain_verdict"]["node_labels"],
                key=lambda x: VERDICT_STRENGTH[x]),
        )

    def test_refine_then_trust_gives_refine(self):
        with _tmp_cwd():
            record = run_chain("wl-b", _chain(), verdict_fn=_verdicts("refine", "trust"))
        self.assertEqual(record["chain_verdict"]["label"], "refine")
        self.assertEqual(
            record["chain_verdict"]["label"],
            min(record["chain_verdict"]["node_labels"],
                key=lambda x: VERDICT_STRENGTH[x]),
        )


# --------------------------------------------------------------------------
# T2 — CHAIN CLOSES
# --------------------------------------------------------------------------

class TestT2ChainCloses(unittest.TestCase):

    def test_two_node_chain_closes_with_real_run_entries_on_both_nodes(self):
        with _tmp_cwd():
            record = run_chain("close-a", _chain(),
                               verdict_fn=_verdicts("trust", "trust"))

        self.assertEqual(record["status"], "executed")
        self.assertEqual(record["chain_verdict"]["label"], "trust")
        self.assertEqual(len(record["nodes"]), 2)
        self.assertEqual([n["substrate_id"] for n in record["nodes"]],
                         ["rdkit", "mafft"])

        for node in record["nodes"]:
            with self.subTest(node=node["substrate_id"]):
                self.assertEqual(node["status"], "executed")
                self.assertEqual(len(node["runs"]), 1)
                entry = node["runs"][0]
                self.assertTrue(entry["converged"])
                # a REAL number, extracted by the wrapper — not a placeholder
                self.assertIsInstance(entry["qoi_value"], float)
                self.assertNotIn("qoi_error", entry)

        # the two nodes ran different instruments and got different numbers
        values = [n["runs"][0]["qoi_value"] for n in record["nodes"]]
        self.assertAlmostEqual(values[0], 46.069, places=3)   # rdkit MolWt of CCO
        self.assertAlmostEqual(values[1], 87.5, places=3)     # mafft % identity

    def test_records_are_written_under_runs_chain_outside_the_baton(self):
        with _tmp_cwd() as tmp:
            run_chain("close-b", _chain(), verdict_fn=_verdicts("trust", "trust"))
            chain_dir = tmp / "runs" / "close-b" / "chain"
            self.assertTrue((chain_dir / "node_0.json").is_file())
            self.assertTrue((chain_dir / "node_1.json").is_file())
            self.assertTrue((chain_dir / "chain.json").is_file())
            on_disk = json.loads((chain_dir / "chain.json").read_text())
            self.assertEqual(on_disk["chain_verdict"]["label"], "trust")
            node_0 = json.loads((chain_dir / "node_0.json").read_text())
            self.assertEqual(node_0["substrate_id"], "rdkit")

    def test_run_one_point_is_called_exactly_once_per_node(self):
        """A chain runs the per-node primitive twice, sequentially."""
        calls = []
        real = chain_runner.run_one_point

        def counting(*args, **kwargs):
            calls.append(kwargs["substrate_id"])
            return real(*args, **kwargs)

        chain_runner.run_one_point = counting
        try:
            with _tmp_cwd():
                run_chain("close-c", _chain(), verdict_fn=_verdicts("trust", "trust"))
        finally:
            chain_runner.run_one_point = real
        self.assertEqual(calls, ["rdkit", "mafft"])

    def test_a_defer_node_executes_nothing(self):
        with _tmp_cwd():
            record = run_chain("close-d", _chain(),
                               verdict_fn=_verdicts("trust", "defer"))
        self.assertEqual(record["nodes"][1]["status"], "skipped_defer")
        self.assertEqual(record["nodes"][1]["runs"], [])


# --------------------------------------------------------------------------
# T4 — FAIL-LOUD
# --------------------------------------------------------------------------

class TestT4FailLoud(unittest.TestCase):

    def test_unroutable_node_halts_honestly_without_crashing(self):
        chain = _chain()
        chain["nodes"][1]["substrate_id"] = "alphafold_db"   # enrolled, parked
        with _tmp_cwd() as tmp:
            record = run_chain("fail-a", chain, verdict_fn=_verdicts("trust", "trust"))
            self.assertTrue((tmp / "runs" / "fail-a" / "chain" / "node_1.json").is_file())

        self.assertEqual(record["status"], "halted_synthesis")
        self.assertIn("not routable", record["reason"])
        # node A really did run before the halt; node B recorded, nothing after
        self.assertEqual(record["nodes"][0]["status"], "executed")
        self.assertEqual(record["nodes"][1]["status"], "halted_synthesis")
        self.assertEqual(record["nodes_attempted"], 2)
        # an honest halt carries NO chain verdict — there is nothing to reduce
        self.assertNotIn("chain_verdict", record)

    def test_a_node_no_substrate_can_serve_halts_honestly(self):
        chain = _chain()
        chain["nodes"][0]["spec"]["parameters"] = [
            {"name": "warp_coil_inductance", "role": "fixed", "value": 1.0,
             "units": "H"}
        ]
        with _tmp_cwd():
            record = run_chain("fail-b", chain, verdict_fn=_verdicts("trust", "trust"))
        self.assertEqual(record["status"], "halted_synthesis")
        self.assertIn("cannot serve", record["reason"])
        # halted at node 0 — nothing after it ran
        self.assertEqual(record["nodes_attempted"], 1)

    def test_case_synthesis_error_halts_honestly_not_as_a_crash(self):
        real = chain_runner.adapter_for

        def exploding(substrate_id):
            if substrate_id == "mafft":
                def boom(*args, **kwargs):
                    raise CaseSynthesisError("mafft case cannot be synthesized")
                return boom
            return real(substrate_id)

        chain_runner.adapter_for = exploding
        try:
            with _tmp_cwd():
                record = run_chain("fail-c", _chain(),
                                   verdict_fn=_verdicts("trust", "trust"))
        finally:
            chain_runner.adapter_for = real

        self.assertEqual(record["status"], "halted_synthesis")
        self.assertIn("cannot be synthesized", record["reason"])
        self.assertEqual(record["nodes"][0]["status"], "executed")
        self.assertEqual(record["nodes"][1]["status"], "halted_synthesis")

    def test_no_cavity_fallback_appears_on_any_halt_path(self):
        chain = _chain()
        chain["nodes"][1]["substrate_id"] = "alphafold_db"
        with _tmp_cwd():
            record = run_chain("fail-d", chain, verdict_fn=_verdicts("trust", "trust"))
        # the halted node still reports the substrate the chain NAMED — it was
        # not silently swapped for one that would have run
        self.assertEqual(record["nodes"][1]["substrate_id"], "alphafold_db")
        self.assertEqual(record["nodes"][1]["runs"], [])
        # nothing ROUTED to or EXECUTED on cavity. (The halt reason's prose
        # does name cavity_2d_cfd — it lists the routable set as a diagnostic
        # — so this asserts on the structural fields, not on the message.)
        for node in record["nodes"]:
            self.assertNotEqual(node.get("substrate_id"), "cavity_2d_cfd")
            for entry in node.get("evidence", []):
                self.assertNotIn("cavity", json.dumps(entry))

    def test_a_malformed_chain_raises_rather_than_halting(self):
        """A broken INPUT is not an experiment outcome."""
        with self.assertRaises(ValueError) as ctx:
            run_chain("fail-e", {"nodes": [{"substrate_id": "rdkit",
                                            "spec": _rdkit_spec()}]},
                      verdict_fn=_verdicts("trust"))
        self.assertIn("exactly 2 ordered nodes", str(ctx.exception))

    def test_verdict_fn_has_no_default(self):
        """The module will not manufacture a verdict."""
        with self.assertRaises(TypeError):
            run_chain("fail-f", _chain())


if __name__ == "__main__":
    unittest.main(verbosity=2)
