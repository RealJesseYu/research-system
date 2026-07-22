"""test_compose_agent.py — the live composing experimenter, proven offline.

Call-free: NO model calls, NO network, NO docker containers. The compose agent's
JUDGMENT is replaced by a faked transport returning canned recipes; everything it
feeds into — the recipe validator the verifier itself uses, the capability guard,
the door's re-ask loop, the real investigation controller running and verifying
code-only compositions in the sandbox — runs unmocked.

The live outing (a real recipe authored by Opus across mature substrates) is a
Terminal job under caffeinate, per the run-venue rule; it is deliberately not a
unit test.

Run directly: venv/bin/python3 tests/test_compose_agent.py
"""

from __future__ import annotations

import json
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import capability_guard  # noqa: E402
import model_call  # noqa: E402
import tools.compose_agent as ca  # noqa: E402
from stages.experiment_investigation import run_investigation  # noqa: E402


def _code_composition(a=2.0, factor=3.0):
    """A code-only composition: one seeded/deterministic step, a combine that
    multiplies. Reproduces exactly, so the controller's verify pass is a genuine
    re-execution in the --network=none sandbox."""
    return {
        "kind": "composition",
        "steps": [{"step_id": "a", "kind": "code",
                   "code": f"metrics['a'] = {a}", "quantity": "a"}],
        "combine": {"kind": "code",
                    "code": f"metrics['out'] = inputs['a'] * {factor}",
                    "quantity": "out", "inputs": ["a"]},
    }


class TestProposalValidation(unittest.TestCase):
    """The agent's answer is checked in code, not hoped for in the prompt. The
    recipe check is the SAME `_validate_recipe` the verifier runs plus per-step
    payload checks, so a recipe that would crash the controller is re-asked."""

    def _errs(self, proposal):
        return ca._validate_proposal(proposal)

    def test_a_good_probe_passes(self):
        self.assertEqual(self._errs({
            "reasoning": "cheap code probe first",
            "recipe": _code_composition(),
            "predicted_value": 6.0,
        }), [])

    def test_a_good_stop_passes(self):
        self.assertEqual(self._errs({
            "reasoning": "these tools cannot compose this",
            "recipe": None, "stop": True,
            "stop_reason": "no instrument here measures the quantity",
        }), [])

    def test_stop_without_a_reason_is_refused(self):
        self.assertTrue(any("stop_reason" in e for e in
                            self._errs({"reasoning": "r", "stop": True})))

    def test_a_non_stopping_reply_needs_a_recipe(self):
        errs = self._errs({"reasoning": "r", "predicted_value": 1.0})
        self.assertTrue(any("must carry a 'recipe'" in e for e in errs))

    def test_a_predicted_value_must_be_a_number_or_null(self):
        errs = self._errs({"reasoning": "r", "recipe": _code_composition(),
                           "predicted_value": "six"})
        self.assertTrue(any("predicted_value" in e and "number or null" in e
                            for e in errs))

    def test_a_measured_value_is_never_reported(self):
        """A bool sneaks past a naive isinstance(int) check — pinned here because
        the boundary is the whole point."""
        errs = self._errs({"reasoning": "r", "recipe": _code_composition(),
                           "predicted_value": True})
        self.assertTrue(any("predicted_value" in e for e in errs))

    def test_a_malformed_recipe_is_caught_by_the_verifier_s_own_validator(self):
        bad = {"kind": "composition", "steps": [],
               "combine": {"kind": "code", "code": "x", "quantity": "q",
                           "inputs": []}}
        errs = self._errs({"reasoning": "r", "recipe": bad})
        self.assertTrue(any("not runnable" in e and "non-empty 'steps'" in e
                            for e in errs))

    def test_a_substrate_step_to_an_unroutable_instrument_is_refused(self):
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "s", "kind": "substrate",
                             "substrate_id": "no_such_tool",
                             "call_style": "typed_dict",
                             "typed_input": {"x": 1}, "quantity": "q"}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['s']",
                              "quantity": "o", "inputs": ["s"]}}
        errs = self._errs({"reasoning": "r", "recipe": recipe})
        self.assertTrue(any("not a routable instrument" in e for e in errs))

    def test_a_substrate_step_without_typed_input_is_refused(self):
        # rdkit is a real routable instrument, so this isolates the missing input
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "s", "kind": "substrate",
                             "substrate_id": "rdkit", "call_style": "typed_dict",
                             "quantity": "MolWt"}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['s']",
                              "quantity": "o", "inputs": ["s"]}}
        errs = self._errs({"reasoning": "r", "recipe": recipe})
        self.assertTrue(any("no 'typed_input'" in e for e in errs))

    def test_an_approximate_instrument_step_is_refused(self):
        """R-ROUTE-3: the experimenter loop is the EXACT-tool path. Composing an
        approximate simulator (cavity) would skip the fidelity check it needs —
        reproduction faithfully reproduces a confidently wrong number — so it is
        re-asked, not accepted."""
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "s", "kind": "substrate",
                             "substrate_id": "cavity_2d_cfd",
                             "call_style": "typed_dict",
                             "typed_input": {"x": 1}, "quantity": "q"}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['s']",
                              "quantity": "o", "inputs": ["s"]}}
        errs = self._errs({"reasoning": "r", "recipe": recipe})
        self.assertTrue(any("APPROXIMATE instrument" in e for e in errs))

    def test_an_exact_instrument_step_passes_the_class_check(self):
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "s", "kind": "substrate",
                             "substrate_id": "rdkit", "call_style": "typed_dict",
                             "typed_input": {"smiles": "CCO", "quantity": "MolWt"},
                             "quantity": "MolWt"}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['s']",
                              "quantity": "o", "inputs": ["s"]}}
        self.assertEqual(self._errs({"reasoning": "r", "recipe": recipe}), [])

    def test_a_code_to_code_file_recipe_passes(self):
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "p", "kind": "code",
                             "code": "open('d.txt','w').write('x')\nmetrics['a']=1.0",
                             "quantity": "a", "emits": ["d.txt"]},
                            {"step_id": "c", "kind": "code",
                             "code": "metrics['b']=float(len(open('d.txt').read()))",
                             "quantity": "b",
                             "consumes": [{"step_id": "p", "name": "d.txt"}]}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['c']",
                              "quantity": "o", "inputs": ["c"]}}
        self.assertEqual(self._errs({"reasoning": "file chain", "recipe": recipe}), [])

    def test_a_substrate_to_substrate_file_chain_passes(self):
        """mafft (emits) -> homology_search (consumes via resolver). Both are
        exact-class, so the chain fits the exact-only boundary."""
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "align", "kind": "substrate",
                             "substrate_id": "mafft", "call_style": "typed_dict",
                             "typed_input": {"sequences": ["MKTA", "MKTA"],
                                             "quantity": "alignment_identity"},
                             "quantity": "alignment_identity",
                             "emits": ["aln.fasta"]},
                            {"step_id": "search", "kind": "substrate",
                             "substrate_id": "homology_search",
                             "call_style": "typed_dict",
                             "typed_input": {"database": "demo_prot", "tool": "blast",
                                             "quantity": "e_value"},
                             "quantity": "e_value",
                             "consumes": [{"step_id": "align", "name": "aln.fasta",
                                           "resolve": {"into": "query",
                                                       "method": "fasta_first_ungapped"}}]}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['search']",
                              "quantity": "o", "inputs": ["search"]}}
        self.assertEqual(self._errs({"reasoning": "align then search",
                                     "recipe": recipe}), [])

    def test_a_code_step_without_code_or_quantity_is_refused(self):
        recipe = {"kind": "composition",
                  "steps": [{"step_id": "s", "kind": "code"}],
                  "combine": {"kind": "code", "code": "metrics['o']=inputs['s']",
                              "quantity": "o", "inputs": ["s"]}}
        errs = self._errs({"reasoning": "r", "recipe": recipe})
        self.assertTrue(any("needs both 'code' and 'quantity'" in e for e in errs))


class TestCapabilityAndProfile(unittest.TestCase):
    def test_the_stage_may_hold_tools_because_it_measures_nothing(self):
        capability_guard.assert_profile_allowed(ca.COMPOSE_STAGE_NAME, "bench")

    def test_a_measurement_producing_stage_still_may_not(self):
        with self.assertRaises(capability_guard.CapabilityPairingError):
            capability_guard.assert_profile_allowed("stage4_simulation", "bench")

    def test_it_reuses_the_bench_profile_and_did_not_mutate_full(self):
        self.assertEqual(ca.BENCH.allowed_tools, model_call.FULL.allowed_tools)
        self.assertLess(ca.BENCH.max_turns, model_call.FULL.max_turns)
        self.assertEqual(model_call.FULL.max_turns, 200)


class TestThePromptTeachesFileHandoff(unittest.TestCase):
    def test_the_system_prompt_describes_emits_consumes_and_resolve(self):
        for token in ("emits", "consumes", "resolve", "FILE HAND-OFF"):
            self.assertIn(token, ca.SYSTEM_PROMPT)


class TestTheGoalReachesTheExperimenter(unittest.TestCase):
    """R-DIR-1: a research question threads through run_investigation to the
    model, so a director can tell the experimenter WHAT to investigate."""

    def test_the_prompt_references_the_research_question(self):
        self.assertIn("research_question", ca.SYSTEM_PROMPT)

    def test_the_goal_in_state_reaches_the_model_input(self):
        sent = []

        def transport(system_prompt, user_turn, model, *args, **kwargs):
            sent.append(user_turn)
            return json.dumps({"reasoning": "r", "recipe": _code_composition(),
                               "predicted_value": None})

        with unittest.mock.patch.object(model_call, "_invoke_transport", transport):
            ca.propose_composition_probe(
                {"measurements": [], "budget_remaining": 3, "iteration": 0,
                 "goal": "does ethanol weigh more than water"})
        self.assertIn("research_question", sent[0])
        self.assertIn("does ethanol weigh more than water", sent[0])

    def test_run_investigation_threads_the_goal_into_state(self):
        seen = {}

        def strat(state):
            seen["goal"] = state.get("goal")
            return {"stop": True, "stop_reason": "just checking the state"}

        run_investigation(strat, max_iters=1, goal="my question")
        self.assertEqual(seen["goal"], "my question")


class TestNeverRaises(unittest.TestCase):
    def test_a_transport_failure_stops_honestly_rather_than_guessing(self):
        def explode(*a, **k):
            raise RuntimeError("transport died at turn 30")

        with unittest.mock.patch.object(ca, "call_stage_model", explode):
            out = ca.propose_composition_probe(
                {"measurements": [], "budget_remaining": 3, "iteration": 0})
        self.assertTrue(out["stop"])
        self.assertIn("transport died", out["stop_reason"])
        self.assertIsNone(out["recipe"])
        self.assertIsNone(out["predicted_value"])


class TestTheRealCallPath(unittest.TestCase):
    """The compose agent's ACTUAL call assembly, only the transport faked.

    The capability guard runs, the toolbox contracts are assembled into the
    input, the validator is enforced inside the door's re-ask loop. This is the
    plumbing a live outing would otherwise discover the expensive way.
    """

    def _call(self, replies, state=None):
        sent = []
        queue = list(replies)

        def transport(system_prompt, user_turn, model, *args, **kwargs):
            sent.append(user_turn)
            return queue.pop(0)

        with unittest.mock.patch.object(model_call, "_invoke_transport", transport):
            out = ca.propose_composition_probe(
                state or {"measurements": [], "budget_remaining": 3, "iteration": 0})
        return out, sent

    def test_the_guard_admits_the_stage_and_a_valid_probe_comes_back(self):
        reply = json.dumps({"reasoning": "cheap code probe first",
                            "recipe": _code_composition(), "predicted_value": 6.0})
        out, sent = self._call([reply])
        self.assertFalse(out["stop"])
        self.assertEqual(out["recipe"]["kind"], "composition")
        self.assertEqual(out["predicted_value"], 6.0)

    def test_the_agent_is_shown_the_routable_contracts_and_its_prior_probes(self):
        reply = json.dumps({"reasoning": "r", "recipe": _code_composition(),
                            "predicted_value": None})
        prior = [{"iteration": 0, "recipe": _code_composition(), "verified": True,
                  "reason": "reproduced", "produce_error": None}]
        _out, sent = self._call(
            [reply], state={"measurements": prior, "budget_remaining": 2,
                            "iteration": 1})
        # every routable substrate's contract is on the table
        for sid in ("rdkit", "cobrapy"):
            self.assertIn(sid, sent[0])
        # it is told which instruments it may actually compose (exact only)
        self.assertIn("exact_instruments_you_may_compose", sent[0])
        # and which artifact reducers it may name for a substrate file consume
        self.assertIn("artifact_resolver_methods", sent[0])
        self.assertIn("fasta_first_ungapped", sent[0])
        # and it can see what it already tried
        self.assertIn("reproduced", sent[0])

    def test_a_malformed_recipe_is_re_asked_not_accepted(self):
        bad = json.dumps({"reasoning": "r",
                          "recipe": {"kind": "composition", "steps": [],
                                     "combine": {"kind": "code", "code": "x",
                                                 "quantity": "q", "inputs": []}}})
        good = json.dumps({"reasoning": "fixed", "recipe": _code_composition(),
                           "predicted_value": None})
        out, sent = self._call([bad, good])
        self.assertEqual(len(sent), 2, "the bad recipe should have been re-asked")
        self.assertIn("non-empty 'steps'", sent[1])
        self.assertEqual(out["recipe"]["kind"], "composition")


class TestDrivesTheRealLoop(unittest.TestCase):
    """The whole point: the faked judgment drives the REAL investigation
    controller, which runs and independently verifies each code composition in
    the sandbox. Nothing about the measurement is faked."""

    def _transport_for(self, replies):
        queue = list(replies)

        def transport(system_prompt, user_turn, model, *args, **kwargs):
            return queue.pop(0)

        return transport

    def test_a_probe_then_stop_produces_a_verified_publishable_run(self):
        replies = [
            json.dumps({"reasoning": "cheap probe first",
                        "recipe": _code_composition(a=2.0, factor=3.0),
                        "predicted_value": 6.0}),
            json.dumps({"reasoning": "the probe reproduced; enough",
                        "recipe": None, "stop": True,
                        "stop_reason": "the composed number reproduced"}),
        ]
        with unittest.mock.patch.object(
                model_call, "_invoke_transport", self._transport_for(replies)):
            summary = run_investigation(ca.propose_composition_probe, max_iters=4)

        self.assertEqual(summary["iterations"], 1)
        self.assertTrue(summary["publishable"])
        self.assertEqual(summary["verified"], 1)
        m = summary["measurements"][0]
        self.assertTrue(m["verified"])
        self.assertEqual(m["reason"], "reproduced")
        # the number of record came from run_composition, by code — 2.0 * 3.0
        self.assertEqual(m["value"], 6.0)
        # the prediction is kept only as a prediction, compared not recorded
        self.assertEqual(m["predicted"], 6.0)
        self.assertEqual(m["prediction_abs_error"], 0.0)

    def test_the_experimenter_can_drive_a_file_chain_through_the_loop(self):
        """The capability we ship: a proposed code->code FILE recipe runs and
        verifies end-to-end through run_investigation (files re-derived)."""
        file_recipe = {
            "kind": "composition",
            "steps": [{"step_id": "p", "kind": "code",
                       "code": "open('v.txt','w').write('1,2,3,4')\nmetrics['n']=4.0",
                       "quantity": "n", "emits": ["v.txt"]},
                      {"step_id": "c", "kind": "code",
                       "code": ("metrics['s']=float(len(open('v.txt').read().split(',')))"),
                       "quantity": "s",
                       "consumes": [{"step_id": "p", "name": "v.txt"}]}],
            "combine": {"kind": "code", "code": "metrics['out']=inputs['c']",
                        "quantity": "out", "inputs": ["c"]}}
        replies = [
            json.dumps({"reasoning": "author a file chain", "recipe": file_recipe,
                        "predicted_value": 4.0}),
            json.dumps({"reasoning": "done", "recipe": None, "stop": True,
                        "stop_reason": "the file chain reproduced"}),
        ]
        with unittest.mock.patch.object(
                model_call, "_invoke_transport", self._transport_for(replies)):
            summary = run_investigation(ca.propose_composition_probe, max_iters=4)
        self.assertTrue(summary["publishable"])
        m = summary["measurements"][0]
        self.assertTrue(m["verified"])
        self.assertEqual(m["reason"], "reproduced")
        self.assertEqual(m["value"], 4.0)         # the consumer read the emitted file

    def test_a_stated_value_is_ignored_only_the_recipe_s_number_stands(self):
        """The hard boundary end-to-end: the agent predicts nonsense loudly and
        the record keeps the number the recipe actually produced."""
        replies = [
            json.dumps({"reasoning": "predicting nonsense on purpose",
                        "recipe": _code_composition(a=2.0, factor=3.0),
                        "predicted_value": 999.0}),
            json.dumps({"reasoning": "done", "recipe": None, "stop": True,
                        "stop_reason": "one probe is enough"}),
        ]
        with unittest.mock.patch.object(
                model_call, "_invoke_transport", self._transport_for(replies)):
            summary = run_investigation(ca.propose_composition_probe, max_iters=4)

        m = summary["measurements"][0]
        self.assertEqual(m["value"], 6.0)            # the recipe's real number
        self.assertEqual(m["predicted"], 999.0)      # kept only as a prediction
        self.assertGreater(m["prediction_abs_error"], 900)


if __name__ == "__main__":
    unittest.main()
