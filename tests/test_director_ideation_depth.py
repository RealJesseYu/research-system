"""test_director_ideation_depth.py — the DIRECTOR's ideation-depth dial (R-FD-6).

Companion to tests/test_ideation_depth.py, which covers the stage-1 side of the
switch (what quick vs full actually run). This file covers the director side:
whether the PI can CHOOSE.

call_ideation was already correctly wired as a TOOL in the open action space —
the director may call it at any turn, it returns ranked hypotheses into the arc,
and the director decides what to do with them. What it lacked was a dial: it
always invoked stage1_ideation at depth='quick' (one generation strategy), so the
full Co-Scientist apparatus (four generation strategies, six review types, an Elo
tournament, evolution, meta-review) was unreachable from the director path.

Proves, entirely offline (no model calls, no ideation runs):
  - the validator accepts depth on call_ideation and rejects it elsewhere;
  - an unknown depth is rejected with a plain error (re-asked in the bounded loop);
  - absent depth means 'quick', so a director that never names one behaves exactly
    as it did before the dial existed;
  - the chosen depth reaches the ideation runner;
  - a runner with the OLD 3-arg signature is still called correctly rather than
    crashing (injected fakes have signatures — a known trap in this codebase);
  - the depth used is recorded, so the arc distinguishes "thin ideas from a quick
    pass" from "thin ideas the full apparatus could not improve on".

Run directly: venv/bin/python3 tests/test_director_ideation_depth.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent import capabilities as C  # noqa: E402
from pi_agent import free_decider  # noqa: E402


class _Budget:
    """Spends without bound; the depth dial is orthogonal to budget."""

    def can_spend(self, n):
        return True

    def spend(self, n):
        return None


class _Study:
    study_id = "study-x"
    goal = "the goal"
    mode = "auto"


# --------------------------------------------------------------------------
# The validator — depth is call_ideation's dial and nothing else's.
# --------------------------------------------------------------------------

class TestDepthValidation(unittest.TestCase):
    def _v(self, over):
        base = {
            "ack": "study-1", "reading": "a pass ran", "reasoning": "need ideas",
            "action": "call_ideation", "domain": None, "instrument": None,
            "campaign": False, "budget_moves": None, "detail": "ideas please",
            "depth": None, "stop_reason": None,
        }
        base.update(over)
        return free_decider.make_action_validator("study-1", 1, ("rdkit",))(base)

    def test_full_depth_is_accepted_on_call_ideation(self):
        self.assertEqual(self._v({"depth": "full"}), [])

    def test_quick_depth_is_accepted(self):
        self.assertEqual(self._v({"depth": "quick"}), [])

    def test_null_depth_is_always_valid(self):
        self.assertEqual(self._v({"depth": None}), [])

    def test_unknown_depth_is_rejected_plainly(self):
        errs = self._v({"depth": "exhaustive"})
        self.assertTrue(any("depth must be one of" in e for e in errs))

    def test_depth_on_another_action_is_rejected(self):
        """Naming a depth on a non-ideation action means the director has confused
        two actions — better to re-ask than to silently ignore it."""
        errs = self._v({"action": "run_experiment", "domain": "q",
                        "detail": None, "depth": "full"})
        self.assertTrue(any("depth must be null" in e for e in errs))

    def test_depth_is_declared_in_the_envelope(self):
        """An undeclared reply field is rejected outright, so depth had to join the
        envelope or the director could never send it."""
        self.assertIn("depth", free_decider._ENVELOPE_FIELDS)


# --------------------------------------------------------------------------
# The executor — the chosen depth reaches ideation.
# --------------------------------------------------------------------------

class TestDepthReachesIdeation(unittest.TestCase):
    def _run(self, action, runner):
        return C.run_ideation(action, _Study(), _Budget(), 1, run=runner)

    def test_full_depth_is_passed_through(self):
        seen = {}

        def runner(domain, study, seq, depth="quick"):
            seen["depth"] = depth
            return [{"id": "h1", "statement": "an idea"}]

        out = self._run({"action": "call_ideation", "detail": "d", "depth": "full"},
                        runner)
        self.assertEqual(seen["depth"], "full")
        self.assertEqual(out["depth"], "full")
        self.assertTrue(out["succeeded"])

    def test_absent_depth_defaults_to_quick(self):
        """A director that never names a depth behaves exactly as before the dial."""
        seen = {}

        def runner(domain, study, seq, depth="quick"):
            seen["depth"] = depth
            return [{"id": "h1", "statement": "an idea"}]

        out = self._run({"action": "call_ideation", "detail": "d"}, runner)
        self.assertEqual(seen["depth"], "quick")
        self.assertEqual(out["depth"], "quick")

    def test_an_old_three_arg_runner_is_still_called_correctly(self):
        """Injected runners have signatures. A fake written before this dial takes
        (domain, study, seq); calling it with a 4th argument would break it
        silently, so depth is passed only to a runner that can accept it."""
        calls = []

        def old_runner(domain, study, seq):
            calls.append((domain, seq))
            return [{"id": "h1", "statement": "an idea"}]

        out = self._run({"action": "call_ideation", "detail": "d", "depth": "full"},
                        old_runner)
        self.assertEqual(len(calls), 1)
        self.assertTrue(out["succeeded"])

    def test_a_kwargs_runner_is_treated_as_accepting_depth(self):
        seen = {}

        def kwargs_runner(domain, study, seq, **kw):
            seen.update(kw)
            return [{"id": "h1", "statement": "x"}]

        self._run({"action": "call_ideation", "detail": "d", "depth": "full"},
                  kwargs_runner)
        self.assertEqual(seen.get("depth"), "full")

    def test_depth_is_recorded_even_when_ideation_comes_back_empty(self):
        """'thin ideas from a quick pass' and 'thin ideas the full apparatus could
        not improve on' are different facts; the arc must distinguish them."""
        out = self._run({"action": "call_ideation", "detail": "d", "depth": "full"},
                        lambda d, s, q, depth="quick": [])
        self.assertFalse(out["succeeded"])
        self.assertEqual(out["outcome"], "ideation_empty")
        self.assertEqual(out["depth"], "full")
        self.assertIn("depth=full", out["detail"])


class TestDefaults(unittest.TestCase):
    def test_default_depth_is_quick(self):
        """Cheap by default; escalation is a judgment the director makes."""
        self.assertEqual(free_decider.DEFAULT_IDEATION_DEPTH, "quick")
        self.assertEqual(free_decider.DEPTH_VALUES, ("quick", "full"))

    def test_the_prompt_teaches_when_to_escalate(self):
        p = free_decider.SYSTEM_PROMPT
        self.assertIn('"depth": "full"', p)
        self.assertIn("tournament", p)
        # and that it is a tool callable at ANY point, not an opening phase
        self.assertIn("not only at the start", p)


class TestIdeationRequestIsNotPreConstrained(unittest.TestCase):
    """THE ANCHOR, ONE LEVEL UP. Contracts were stripped from generation
    (3798326), but the director writes its own ideation request and had been
    narrowing it itself — live, in study-20260725T233436Z: "testable on one of
    the available instruments (CFD, FEA, symbolic math, SPICE, RDKit, FBA)". An
    unanchored generator handed a constrained question is still constrained."""

    def test_the_director_is_told_to_ask_the_open_question(self):
        p = free_decider.SYSTEM_PROMPT
        self.assertIn("ASK IT THE OPEN QUESTION", p)
        self.assertIn("do not list the instruments in it", p)

    def test_it_explains_why_pre_constraining_is_harmful(self):
        """Not just a rule — the reason, so it holds under pressure."""
        p = free_decider.SYSTEM_PROMPT
        self.assertIn("already answered", p)

    def test_the_menu_is_still_the_directors_tool_for_dispatching(self):
        """The instrument menu is not removed — it is what the director uses when
        it runs an experiment. Only the ideation REQUEST is unconstrained."""
        p = free_decider.SYSTEM_PROMPT
        self.assertIn("what YOU use when dispatching an experiment", p)

    def test_the_action_menu_line_says_it_too(self):
        entry = [a for a in free_decider._action_space_menu()
                 if a["action"] == "call_ideation"][0]
        self.assertIn("never narrowed to the instrument menu", entry["does"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
