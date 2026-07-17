"""
test_calibration_battery.py — STEP 26. Call-free: NO model calls, NO network,
NO docker. Covers harness/calibration_battery.py — case-file integrity, the
confusion/hook-witness pure functions, the REAL maturity-hook witness (imported
from supervisor, exercised on fabricated verdicts), and the wrapper-behavior
track run against the substrates' own validators (pure Python validation only —
these reject before any solver/container).

Run directly: venv/bin/python3 tests/test_calibration_battery.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import supervisor
from harness import calibration_battery as cb
from stages.stage3_fidelity_gate import VALID_LABELS

FEA = "calculix_cantilever_fea"
CODE = "code_sklearn_eval"
FENICSX = "fenicsx_cantilever_elastic"


class TestCaseFileIntegrity(unittest.TestCase):
    def test_fea_composition(self):
        # Step 26 / R-CAL-2: slate is 15 — gate 10 (in 5 / out 5), wrapper 5.
        # C15 (out) exercises F4: geometry in-envelope, QoI max_von_mises unvalidated.
        data = cb.load_cases(FEA)
        self.assertEqual(len(data["gate_cases"]), 10)
        self.assertEqual(len(data["wrapper_cases"]), 5)
        classes = [g["expected_class"] for g in data["gate_cases"]]
        self.assertEqual(classes.count("in"), 5)
        self.assertEqual(classes.count("out"), 5)
        self.assertTrue(all(w["expected_class"] == "setup_error"
                            for w in data["wrapper_cases"]))

    def test_c15_f4_case_is_out_and_never_trust(self):
        # The F4 reported-only QoI case: geometry in-envelope, but max_von_mises is
        # NOT validated, so a raw trust is the wrong verdict.
        c15 = {g["id"]: g for g in cb.load_cases(FEA)["gate_cases"]}["C15"]
        self.assertEqual(c15["expected_class"], "out")
        self.assertNotIn("trust", c15["acceptable_labels"])
        self.assertEqual(set(c15["acceptable_labels"]), {"refine", "defer"})
        self.assertIn("max_von_mises", c15["experiment"])

    def test_code_composition(self):
        data = cb.load_cases(CODE)
        self.assertEqual(len(data["gate_cases"]), 11)
        self.assertEqual(len(data["wrapper_cases"]), 3)
        classes = [g["expected_class"] for g in data["gate_cases"]]
        self.assertEqual(classes.count("in"), 4)
        self.assertEqual(classes.count("conflation"), 3)
        self.assertEqual(classes.count("metric-mismatch"), 2)
        self.assertEqual(classes.count("leakage-suspect"), 2)
        self.assertTrue(all(w["expected_class"] == "setup_error"
                            for w in data["wrapper_cases"]))

    def test_acceptable_labels_are_vocabulary(self):
        for sid in (FEA, CODE, FENICSX):
            for g in cb.load_cases(sid)["gate_cases"]:
                self.assertTrue(g["acceptable_labels"])
                for lbl in g["acceptable_labels"]:
                    self.assertIn(lbl, VALID_LABELS)

    def test_no_bare_trust_for_conflation_or_leakage(self):
        # A single-label gate cannot emit a split; the safe proxy for a
        # conflation/leakage case is NEVER a bare trust.
        for g in cb.load_cases(CODE)["gate_cases"]:
            if g["expected_class"] in ("conflation", "leakage-suspect"):
                self.assertNotIn("trust", g["acceptable_labels"], g["id"])

    def test_rule1_no_answer_key_leak_in_built_input(self):
        # The stage_input a gate case would send carries none of the answer-key
        # keys — the same tripwire run_gate_case asserts live.
        for sid in (FEA, CODE, FENICSX):
            data = cb.load_cases(sid)
            for g in data["gate_cases"]:
                stage_input = {
                    "case_id": g["id"],
                    "substrate": data["substrate_text"],
                    "envelope": data["envelope_text"],
                    "experiment": g["experiment"],
                }
                serialized = json.dumps(stage_input)
                for k in cb._ANSWER_KEY_KEYS:
                    self.assertNotIn(f'"{k}"', serialized, f"{sid}/{g['id']}/{k}")

    def test_answer_key_blocklist_covers_every_hidden_gate_field(self):
        # COMPLETENESS / DRIFT GUARD (Step 26): the hardcoded _ANSWER_KEY_KEYS must
        # cover every gate-case field that is NOT model-visible. Derived per case as
        # (all keys) - {"id", "experiment"}. Fails the moment a case gains a hidden
        # field the blocklist does not know — so the blocklist cannot silently drift
        # out of coverage as cases are added.
        for sid in (FEA, CODE, FENICSX):
            for g in cb.load_cases(sid)["gate_cases"]:
                hidden = set(g) - set(cb._MODEL_VISIBLE_GATE_FIELDS)
                missing = hidden - set(cb._ANSWER_KEY_KEYS)
                self.assertEqual(
                    missing, set(),
                    f"{sid}/{g['id']}: answer-key field(s) not in blocklist: {missing}")


class TestAnswerKeyTripwire(unittest.TestCase):
    """The RULE-1 answer-key tripwire, proven by FAILING THE ESCAPE — not by
    re-reading the safe construction. Each test fails if the guard is removed."""

    def test_tripwire_fires_on_leaked_key(self):
        # A stage_input that leaks an answer-key key (exactly what a future
        # `stage_input = {**gate_case, ...}` regression would produce) MUST abort.
        # If the assert is deleted, no AssertionError is raised and this fails.
        leaking = {
            "case_id": "C-LEAK",
            "substrate": "s", "envelope": "e", "experiment": "x",
            "acceptable_labels": ["trust"],  # <-- the answer key, leaked in
        }
        with self.assertRaises(AssertionError) as ctx:
            cb._assert_no_answer_key_leak(leaking, "C-LEAK")
        self.assertIn("ANSWER KEY LEAK", str(ctx.exception))
        self.assertIn("C-LEAK", str(ctx.exception))
        self.assertIn("acceptable_labels", str(ctx.exception))

    def test_tripwire_fires_on_each_answer_key_field(self):
        # Every field in the blocklist is individually caught, not just one.
        for k in cb._ANSWER_KEY_KEYS:
            with self.assertRaises(AssertionError, msg=k):
                cb._assert_no_answer_key_leak({k: "anything"}, "C-LEAK")

    def test_tripwire_passes_on_clean_input(self):
        # The known-safe construction must NOT raise (guard is not over-eager).
        clean = {"case_id": "C01", "substrate": "s", "envelope": "e", "experiment": "x"}
        cb._assert_no_answer_key_leak(clean, "C01")  # no raise == pass

    def test_run_gate_case_actually_invokes_the_tripwire(self):
        # WIRING: run_gate_case must call the tripwire BEFORE any model call. A spy
        # that raises proves it is on the path; the RuntimeError propagating (not a
        # model/transport error) proves the guard runs first. Fails if the call is
        # removed from run_gate_case.
        marker = RuntimeError("TRIPWIRE-ON-PATH")

        def boom(stage_input, case_id):
            raise marker

        def must_not_be_called(*a, **k):  # call_stage_model — a real Opus spend
            raise AssertionError("model was reached before the tripwire fired")

        with mock.patch.object(cb, "_assert_no_answer_key_leak", boom), \
                mock.patch.object(cb, "call_stage_model", must_not_be_called):
            with self.assertRaises(RuntimeError) as ctx:
                cb.run_gate_case(
                    {"substrate_text": "s", "envelope_text": "e"},
                    {"id": "C01", "experiment": "x"},
                    "auto",
                )
            self.assertIn("TRIPWIRE-ON-PATH", str(ctx.exception))


class TestStagedBatteryWiring(unittest.TestCase):
    """The `_ANSWER_KEY_KEYS` amendment (label_provenance, label_rationale),
    PROVEN BY FAILING THE ESCAPE.

    MOVED from tests/test_run_fenicsx.py at the Wave-2 merge, as that build
    flagged. There the battery was frozen, so these tests SIMULATED the patched
    state by substituting the blocklist. Now the REAL blocklist is patched, so
    the roles invert: the live `cb._ANSWER_KEY_KEYS` IS the patched state
    (tested directly, no substitution), and the PRE-patch state is reconstructed
    by removing the two additions — kept only to prove the escape SUCCEEDED
    before the amendment. A guard test that passes under the patch but was never
    shown to fail without it proves nothing.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import battery_wiring  # noqa: E402
        import contract  # noqa: E402

        self.cb = cb
        self.contract = contract
        additions = tuple(battery_wiring.ANSWER_KEY_KEYS_ADDITIONS)
        # The REAL shipped blocklist — the thing under test, no substitution.
        self.patched = tuple(cb._ANSWER_KEY_KEYS)
        # The pre-amendment state, reconstructed by subtraction. If the
        # amendment is ever reverted, patched == unpatched and the trips-patched
        # assertions below fail loudly.
        self.unpatched = tuple(k for k in self.patched if k not in additions)

    def _leaking_input(self, mutated_rationale: str) -> dict:
        """A model input carrying a MUTATED label_rationale — i.e. answer-key text
        that has drifted into what the model would see."""
        return {
            "case_id": "X06",
            "substrate": "irrelevant substrate text",
            "envelope": "irrelevant envelope text",
            "experiment": "Cantilever ... element_degree=1. Extract tip_displacement.",
            "label_rationale": mutated_rationale,
        }

    def test_escape_succeeds_unpatched_then_guard_trips_patched(self):
        """THE FAILING ESCAPE (the 0199161 pattern). Take a real X06 rationale,
        mutate it, drift it into the model input, and show the guard's two states
        differ: PRE-patch it sails through; the REAL guard trips."""
        x06 = {c["id"]: c for c in self.contract.GATE_CASES}["X06"]
        mutated = x06["label_rationale"].replace("dangerous", "MUTATED-dangerous")
        self.assertNotEqual(mutated, x06["label_rationale"])  # the mutation is real
        leaking = self._leaking_input(mutated)

        # (a) UNPATCHED: the escape SUCCEEDS — the gap was real, not hypothetical.
        with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.unpatched):
            self.cb._assert_no_answer_key_leak(leaking, "X06")   # does NOT raise

        # (b) PATCHED: the REAL guard (no substitution) TRIPS on the same input.
        with self.assertRaises(AssertionError) as ctx:
            self.cb._assert_no_answer_key_leak(leaking, "X06")
        self.assertIn("label_rationale", str(ctx.exception))
        self.assertIn("X06", str(ctx.exception))

    def test_patched_guard_trips_on_each_new_field_individually(self):
        """Both added names are caught on their own, not just as a pair."""
        for field in ("label_provenance", "label_rationale"):
            with self.subTest(field=field):
                leaking = {"case_id": "X01", "experiment": "beam", field: "drifted"}
                with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.unpatched):
                    self.cb._assert_no_answer_key_leak(leaking, "X01")   # escape works
                with self.assertRaises(AssertionError):
                    self.cb._assert_no_answer_key_leak(leaking, "X01")  # real guard

    def test_patched_guard_still_passes_a_clean_input(self):
        """The real guard must not fire on the real construction path, or it
        would be a tripwire that trips on everything — which is also not a proof."""
        clean = {"case_id": "X06", "substrate": "s", "envelope": "e",
                 "experiment": "Cantilever ... element_degree=1."}
        self.cb._assert_no_answer_key_leak(clean, "X06")   # does NOT raise

    def test_merge_blocker_is_real_and_the_amendment_resolves_it(self):
        """The drift guard's own derivation, run against THIS slate:
        PRE-patch it fails on every gate case (the merge blocker was real);
        against the REAL blocklist it passes (the amendment is sufficient and no
        further name is needed)."""
        visible = set(self.cb._MODEL_VISIBLE_GATE_FIELDS)
        uncovered_unpatched, uncovered_patched = [], []
        for case in self.contract.GATE_CASES:
            hidden = set(case) - visible
            if hidden - set(self.unpatched):
                uncovered_unpatched.append(case["id"])
            if hidden - set(self.patched):
                uncovered_patched.append(case["id"])
        self.assertEqual(len(uncovered_unpatched), 10)   # merge blocker: all 10
        self.assertEqual(uncovered_patched, [])          # amendment resolves it


class TestOldPathUnchangedByThePatch(unittest.TestCase):
    """THE OLD-PATH PROPERTY: the FEA and code case files must assemble a
    BYTE-IDENTICAL model prompt before and after the patch.

    MOVED from tests/test_run_fenicsx.py at the Wave-2 merge, as flagged there.
    The amendment only adds names to a blocklist that SCANS; it must not touch
    construction, and — the real risk — the two new names must not newly trip on
    the existing slates' text. Both are proven by running the REAL
    `run_gate_case` construction path with the model call stubbed out. The
    patched list is now the live `cb._ANSWER_KEY_KEYS`; the pre-patch list is
    reconstructed by removing the two additions.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import battery_wiring  # noqa: E402

        self.cb = cb
        additions = tuple(battery_wiring.ANSWER_KEY_KEYS_ADDITIONS)
        self.patched = tuple(cb._ANSWER_KEY_KEYS)
        self.unpatched = tuple(k for k in self.patched if k not in additions)

    def _prompts_under(self, blocklist) -> list[str]:
        """Every FEA + code gate case's assembled model input, serialized, built
        through the REAL run_gate_case with only the model call replaced."""
        captured: list[str] = []

        def _fake_call(stage, prompt, stage_input, schema, model=None,
                       extra_validator=None):
            captured.append(json.dumps(stage_input, sort_keys=True))
            return ({"verdict": {"label": "defer", "rationale": "stub",
                                 "right_instrument": "stub"}}, {"attempts": 1})

        with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", blocklist), \
                mock.patch.object(self.cb, "call_stage_model", _fake_call):
            for sid in (FEA, CODE):
                data = self.cb.load_cases(sid)
                for gc in data["gate_cases"]:
                    self.cb.run_gate_case(data, gc, "auto")
        return captured

    def test_fea_and_code_prompts_are_byte_identical_before_and_after(self):
        before = self._prompts_under(self.unpatched)
        after = self._prompts_under(self.patched)
        self.assertTrue(before, "no prompts captured — the harness did not run")
        self.assertEqual(len(before), 21)          # FEA 10 + code 11 gate cases
        self.assertEqual(before, after)            # byte-identical, case for case

    def test_the_two_new_names_raise_no_false_positive_on_the_old_slates(self):
        """If FEA's or code's prompt text happened to contain the literal
        '"label_rationale"', the patched guard would abort a battery that works
        today. Prove it does not — this is the only way the patch could break the
        old path, and _prompts_under would have raised if it did."""
        for sid in (FEA, CODE):
            data = self.cb.load_cases(sid)
            for name in ("label_provenance", "label_rationale"):
                with self.subTest(substrate=sid, name=name):
                    self.assertNotIn(f'"{name}"', json.dumps(data["substrate_text"]))
                    self.assertNotIn(f'"{name}"', json.dumps(data["envelope_text"]))
                    for gc in data["gate_cases"]:
                        self.assertNotIn(f'"{name}"', json.dumps(gc["experiment"]))


class TestConfusion(unittest.TestCase):
    def test_confusion_counts(self):
        records = [
            {"expected_class": "in", "raw_verdict": "trust"},
            {"expected_class": "in", "raw_verdict": "refine"},
            {"expected_class": "out", "raw_verdict": "defer"},
            {"expected_class": "out", "raw_verdict": "defer"},
        ]
        m = cb.build_confusion(records)
        self.assertEqual(m["in"], {"trust": 1, "refine": 1, "defer": 0})
        self.assertEqual(m["out"], {"trust": 0, "refine": 0, "defer": 2})


class TestRealHookWitness(unittest.TestCase):
    """Exercises the REAL supervisor.apply_substrate_maturity_hook via witness_hook."""

    def test_hook_is_the_real_imported_function(self):
        # The battery must exercise the real hook, never a copy.
        self.assertIs(cb.apply_substrate_maturity_hook,
                      supervisor.apply_substrate_maturity_hook)

    def test_auto_downgrades_trust(self):
        w = cb.witness_hook({"label": "trust", "rationale": "r", "right_instrument": "i"}, "auto")
        self.assertTrue(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "defer")
        self.assertTrue(w["signoff_substrates"])

    def test_auto_downgrades_refine(self):
        w = cb.witness_hook({"label": "refine", "rationale": "r", "right_instrument": "i"}, "auto")
        self.assertTrue(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "defer")

    def test_defer_is_noop(self):
        w = cb.witness_hook({"label": "defer", "rationale": "r", "right_instrument": "i"}, "auto")
        self.assertFalse(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "defer")

    def test_human_mode_leaves_verdict_but_records_signoff(self):
        w = cb.witness_hook({"label": "trust", "rationale": "r", "right_instrument": "i"}, "human")
        self.assertTrue(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "trust")  # untouched in human mode
        self.assertTrue(w["signoff_substrates"])

    def test_witness_does_not_mutate_caller_verdict(self):
        raw = {"label": "trust", "rationale": "r", "right_instrument": "i"}
        cb.witness_hook(raw, "auto")
        self.assertEqual(raw["label"], "trust")  # deep-copied inside


class TestHookSummary(unittest.TestCase):
    def _rec(self, cid, raw, routed, fired):
        return {"case_id": cid, "raw_verdict": raw, "routed_outcome": routed,
                "hook_fired": fired}

    def test_all_defer_zero_silent_trusts(self):
        recs = [self._rec("C1", "defer", "defer", False),
                self._rec("C2", "refine", "defer", True)]
        s = cb.hook_summary(recs, "auto")
        self.assertTrue(s["zero_silent_trusts"])
        self.assertTrue(s["hook_fired_matches_raw_trust_refine"])
        self.assertEqual(s["n_hook_fired"], 1)
        self.assertEqual(s["n_raw_trust_or_refine"], 1)

    def test_human_routed_trust_is_not_silent(self):
        recs = [self._rec("C1", "trust", "trust", True)]
        s = cb.hook_summary(recs, "human")
        self.assertEqual(s["routed_trust_case_ids"], ["C1"])
        self.assertTrue(s["zero_silent_trusts"])  # fired -> flagged -> not silent

    def test_a_silent_trust_is_caught(self):
        # Fabricated broken state: routed trust with no hook firing.
        recs = [self._rec("C1", "trust", "trust", False)]
        s = cb.hook_summary(recs, "auto")
        self.assertFalse(s["zero_silent_trusts"])
        self.assertFalse(s["hook_fired_matches_raw_trust_refine"])


class TestWrapperBehaviorTrack(unittest.TestCase):
    """Runs the real wrapper validators (pure Python; NO docker, NO model)."""

    def test_fea_wrapper_cases_reject_as_registered(self):
        data = cb.load_cases(FEA)
        for wc in data["wrapper_cases"]:
            r = cb.run_wrapper_case(FEA, wc)
            self.assertFalse(r["wrapper_valid"], wc["id"])
            self.assertTrue(r["reason_matched"], f"{wc['id']}: {r['wrapper_reason']}")
            self.assertTrue(r["passed"], wc["id"])

    def test_code_wrapper_cases_reject_as_registered(self):
        data = cb.load_cases(CODE)
        for wc in data["wrapper_cases"]:
            r = cb.run_wrapper_case(CODE, wc)
            self.assertFalse(r["wrapper_valid"], wc["id"])
            self.assertTrue(r["reason_matched"], f"{wc['id']}: {r['wrapper_reason']}")
            self.assertTrue(r["passed"], wc["id"])


class TestEntropyBits(unittest.TestCase):
    """The small-N spread measure. At N=3 only three distributions exist."""

    def test_unanimous_is_zero(self):
        self.assertEqual(cb._entropy_bits({"trust": 3}), 0.0)

    def test_two_one_split(self):
        # 2/1 over two labels: -(2/3)log2(2/3) - (1/3)log2(1/3) = 0.9183
        self.assertAlmostEqual(cb._entropy_bits({"trust": 2, "defer": 1}), 0.9183, places=3)

    def test_maximal_three_way(self):
        # 1/1/1 = log2(3) = 1.585, the ceiling for the 3-label vocabulary.
        self.assertAlmostEqual(cb._entropy_bits({"trust": 1, "refine": 1, "defer": 1}),
                               1.585, places=3)

    def test_empty_is_zero(self):
        self.assertEqual(cb._entropy_bits({}), 0.0)


class TestAggregateCaseRepeats(unittest.TestCase):
    """The pure per-case distribution aggregator (R-REP-1). Holds the
    'do not collapse' line: raw_verdicts and every draw survive."""

    def _draw(self, cid, raw, accept):
        return {
            "case_id": cid, "track": "gate", "expected_class": "in",
            "acceptable_labels": accept, "raw_verdict": raw,
            "routed_outcome": "defer", "hook_fired": raw in ("trust", "refine"),
            "signoff_substrates": [], "passed": raw in accept, "rationale": f"r-{raw}",
            "right_instrument": "i", "wall_time_seconds": 1.0, "reask_attempts": 1,
        }

    def test_split_distribution_preserved(self):
        accept = ["trust", "refine"]
        draws = [self._draw("C1", "trust", accept),
                 self._draw("C1", "defer", accept),
                 self._draw("C1", "refine", accept)]
        agg = cb.aggregate_case_repeats(draws)
        self.assertEqual(agg["raw_verdicts"], ["trust", "defer", "refine"])
        self.assertEqual(agg["distribution"], {"trust": 1, "defer": 1, "refine": 1})
        self.assertFalse(agg["unanimous"])
        self.assertEqual(agg["n_in_band"], 2)          # trust + refine in band
        self.assertEqual(agg["in_band_fraction"], round(2 / 3, 4))
        self.assertEqual(agg["draws"], draws)          # every draw survives
        self.assertEqual(agg["n_repeats"], 3)

    def test_unanimous_case(self):
        accept = ["defer"]
        draws = [self._draw("C6", "defer", accept) for _ in range(3)]
        agg = cb.aggregate_case_repeats(draws)
        self.assertTrue(agg["unanimous"])
        self.assertEqual(agg["distribution"], {"defer": 3})
        self.assertEqual(agg["entropy_bits"], 0.0)
        self.assertEqual(agg["in_band_fraction"], 1.0)

    def test_modal_tiebreak_is_canonical_order(self):
        # 1 trust / 1 refine tie -> canonical VALID_LABELS order picks 'trust'
        # (index 0), deterministically. NOT a claim trust is 'the' verdict.
        accept = ["trust", "refine"]
        draws = [self._draw("C1", "refine", accept), self._draw("C1", "trust", accept)]
        agg = cb.aggregate_case_repeats(draws)
        self.assertEqual(agg["modal_verdict"], "trust")


def _fake_gate_record(case_id, expected_class, acceptable_labels, raw):
    return {
        "case_id": case_id, "track": "gate", "expected_class": expected_class,
        "acceptable_labels": list(acceptable_labels), "raw_verdict": raw,
        "routed_outcome": "defer", "hook_fired": raw in ("trust", "refine"),
        "signoff_substrates": [], "passed": raw in acceptable_labels,
        "rationale": f"r-{raw}", "right_instrument": "i",
        "wall_time_seconds": 0.01, "reask_attempts": 1,
    }


class TestRepeatsBattery(unittest.TestCase):
    """run_battery under --repeats, with run_gate_case FAKED (NO model calls).
    Proves backward-compat at repeats=1, distribution shape at repeats>1,
    independent draws, and wrapper-case EXCLUSION from repetition."""

    def _run(self, repeats, cycle=("trust", "defer", "refine")):
        import itertools
        import tempfile
        gate_calls = []
        wrapper_calls = []

        def fake_gate(data, gc, mode):
            # A distinct raw verdict each call so repeats produce a real split;
            # each call records itself, proving draws are separate invocations.
            raw = cycle[len(gate_calls) % len(cycle)]
            gate_calls.append((gc["id"], raw))
            return _fake_gate_record(gc["id"], gc["expected_class"],
                                     gc["acceptable_labels"], raw)

        real_wrapper = cb.run_wrapper_case

        def spy_wrapper(sid, wc):
            wrapper_calls.append(wc["id"])
            return real_wrapper(sid, wc)

        report_path = Path(tempfile.mkdtemp()) / "rep.json"
        with mock.patch.object(cb, "run_gate_case", fake_gate), \
                mock.patch.object(cb, "run_wrapper_case", spy_wrapper):
            rc = cb.run_battery(CODE, "auto", report_path=report_path, repeats=repeats)
        report = json.loads(report_path.read_text())
        return rc, report, gate_calls, wrapper_calls

    def test_repeats1_report_shape_is_backward_compatible(self):
        # repeats=1 reproduces the pre-R-REP-1 report shape EXACTLY: no top-level
        # n_repeats, gate block has the original 5 keys, cases ARE draw records.
        _, report, gate_calls, _ = self._run(1)
        self.assertNotIn("n_repeats", report)
        self.assertEqual(set(report["gate"]),
                         {"n_cases", "n_passed", "confusion", "hook_witness", "cases"})
        n_gate = len(cb.load_cases(CODE)["gate_cases"])
        self.assertEqual(len(gate_calls), n_gate)          # one draw per case
        for c in report["gate"]["cases"]:
            self.assertIn("raw_verdict", c)                # a single draw record
            self.assertNotIn("draws", c)
            self.assertNotIn("distribution", c)

    def test_repeats3_is_independent_draws_per_gate_case(self):
        _, report, gate_calls, _ = self._run(3)
        cases = cb.load_cases(CODE)
        n_gate = len(cases["gate_cases"])
        # Exactly 3 INDEPENDENT run_gate_case invocations per gate case.
        self.assertEqual(len(gate_calls), 3 * n_gate)
        self.assertEqual(report["n_repeats"], 3)
        self.assertEqual(report["gate"]["n_draws"], 3 * n_gate)
        for c in report["gate"]["cases"]:
            self.assertEqual(len(c["draws"]), 3)
            self.assertEqual(sum(c["distribution"].values()), 3)
            self.assertEqual(c["raw_verdicts"], [d["raw_verdict"] for d in c["draws"]])

    def test_confusion_sums_over_all_draws_at_repeats3(self):
        _, report, _, _ = self._run(3)
        n_gate = len(cb.load_cases(CODE)["gate_cases"])
        total = sum(sum(row.values()) for row in report["gate"]["confusion"].values())
        self.assertEqual(total, 3 * n_gate)               # every draw counted

    def test_wrapper_cases_run_once_regardless_of_repeats(self):
        # EXCLUSION PROOF: wrapper-behavior cases are deterministic zero-model
        # validation; repeating measures nothing, so they run ONCE at any N.
        cases = cb.load_cases(CODE)
        n_wrap = len(cases["wrapper_cases"])
        for repeats in (1, 5):
            _, report, _, wrapper_calls = self._run(repeats)
            self.assertEqual(len(wrapper_calls), n_wrap, f"repeats={repeats}")
            self.assertEqual(report["wrapper_behavior"]["n_cases"], n_wrap)

    def test_repeats_below_one_rejected(self):
        with self.assertRaises(ValueError):
            cb.run_battery(CODE, "auto", repeats=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
