"""
test_meta_induce.py — call-free tests for the meta-induction v1 pass.

Every model call is MOCKED; no live model call, no pipeline run. Covers:
  - digest composition from fixtures, exercising the learned-summary ->
    lesson-provenance JOIN (tagged, untagged, measured);
  - induction schema accept/reject + the bounded re-ask path (mocked transport),
    including the honest degrade-to-empty at the 2-attempt cap;
  - zero-support rule dropping;
  - the append-only sidecar writer;
  - the human-doc renderer.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

import meta_induce as mi  # noqa: E402


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


class DigestComposition(unittest.TestCase):
    """Digest is built deterministically from on-disk artifacts, and the
    learned-summary/provenance join is exercised end to end."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        # Two learned summaries: one will be tagged, one left untagged.
        self.journal = self.tmp / "journal.jsonl"
        _write_jsonl(self.journal, [
            {"kind": "run_record", "run_id": "rX", "text": "not a summary"},
            {"kind": "learned_summary", "run_id": "rA", "hypothesis_id": "h1",
             "text": "Lesson A rests on a measured slope.", "timestamp": "T1"},
            {"kind": "learned_summary", "run_id": "rB", "hypothesis_id": "h2",
             "text": "Lesson B is a said re-scope.", "timestamp": "T2"},
        ])
        # Provenance tags ONLY rA/h1 (measured); rB is deliberately untagged.
        self.prov = self.tmp / "lesson_provenance.jsonl"
        _write_jsonl(self.prov, [
            {"key": "rA|h1|T1", "provenance": "measured",
             "source_run": "rA", "basis": "executed numeric qoi"},
        ])
        self.fidelity = self.tmp / "fidelity_ledger.jsonl"
        _write_jsonl(self.fidelity, [
            {"run_id": "rA", "verdict": "trust", "substrate": "cavity_2d",
             "outcome": None, "rationale": "in-envelope"},
            {"run_id": "rB", "verdict": "defer", "substrate": "cavity_2d",
             "outcome": None, "rationale": "unextractable QoI"},
        ])
        self.override = self.tmp / "override_ledger.jsonl"
        _write_jsonl(self.override, [
            {"run_id": "rA", "gate": 1, "system_decision": "select rank 1",
             "human_decision": "select rank 2", "did_override": True},
        ])
        self.gate_bets = self.tmp / "gate_bets_report.json"
        self.gate_bets.write_text(json.dumps(
            {"n_total": 2, "n_resolved": 0, "n_excluded": 2,
             "n_unpredictable": 0, "cumulative_brier": None}))
        self.anomaly = self.tmp / "anomaly_scan_report.md"
        self.anomaly.write_text(
            "# Anomaly scan\n- run dirs walked: 5\n## (a) Outliers\n- none\n"
            "## Numeric families collected\n- foo: 3\n")
        # One minimal spec so the pi sweep runs (pi_report degrades gracefully).
        specdir = self.tmp / "runs" / "r1" / "stage2"
        specdir.mkdir(parents=True)
        (specdir / "spec.json").write_text(json.dumps(
            {"hypothesis_id": "h1", "mini_experiment": {"runs": []}}))
        self.specs_glob = str(self.tmp / "runs" / "**" / "spec.json")

    def _digest(self) -> str:
        return mi.compose_digest(
            journal_path=self.journal, provenance_path=self.prov,
            fidelity_path=self.fidelity, override_path=self.override,
            gate_bets_path=self.gate_bets, anomaly_report_path=self.anomaly,
            specs_glob=self.specs_glob,
        )

    def test_join_tags_measured_and_untagged(self) -> None:
        d = self._digest()
        # The tagged summary shows its provenance basis; the untagged one is
        # visibly marked untagged, not silently dropped.
        self.assertIn("[rA | h1 | measured] Lesson A", d)
        self.assertIn("[rB | h2 | untagged] Lesson B", d)
        # The non-summary journal record never becomes a learned-summary line.
        self.assertNotIn("not a summary", d)

    def test_all_sections_present(self) -> None:
        d = self._digest()
        for title in (
            "LEARNED SUMMARIES", "FIDELITY-LEDGER VERDICTS",
            "OVERRIDE-LEDGER DECISIONS", "GATE-BETS HEADLINE",
            "ANOMALY-SCANNER FINDINGS", "PI-GATE SWEEP SUMMARY",
        ):
            self.assertIn(title, d)
        self.assertIn("rB | defer | cavity_2d", d)          # fidelity line
        self.assertIn("override=True", d)                    # override line
        self.assertIn("specs swept: 1", d)                   # pi sweep ran
        # The numeric-families tail of the anomaly report is excluded.
        self.assertNotIn("Numeric families collected", d)

    def test_size_reported_and_under_cap(self) -> None:
        d = self._digest()
        sz = mi.digest_size(d)
        self.assertEqual(sz["chars"], len(d))
        self.assertEqual(sz["est_tokens"], (len(d) + 3) // 4)
        self.assertLessEqual(sz["est_tokens"], sz["token_cap"])


class SchemaValidation(unittest.TestCase):
    def test_valid_rule_passes(self) -> None:
        data = {"rules": [{
            "rule": "Defers cluster on unextractable field QoIs.",
            "supporting_artifacts": ["rA", "rB"],
            "provenance_basis": "said",
            "suggested_scope": "fidelity gate",
        }]}
        self.assertEqual(mi.validate_induction(data), [])

    def test_missing_and_bad_fields_flagged(self) -> None:
        data = {"rules": [
            {"rule": "", "supporting_artifacts": "notalist",
             "provenance_basis": "guessed", "suggested_scope": ""},
        ]}
        errs = mi.validate_induction(data)
        self.assertTrue(any("'rule' must be" in e for e in errs))
        self.assertTrue(any("supporting_artifacts" in e for e in errs))
        self.assertTrue(any("provenance_basis" in e for e in errs))
        self.assertTrue(any("suggested_scope" in e for e in errs))

    def test_rules_not_a_list(self) -> None:
        self.assertEqual(mi.validate_induction({"rules": {}}),
                         ["'rules' must be a list"])


class InductionCall(unittest.TestCase):
    """The bounded 2-attempt loop with a mocked transport (never live)."""

    def _fake_transport(self, replies: list[str]):
        seen = []
        queue = list(replies)

        def transport(system_prompt: str, user_turn: str, model: str) -> str:
            seen.append(json.loads(user_turn))
            return queue.pop(0)
        return transport, seen

    def test_success_on_first_attempt(self) -> None:
        good = json.dumps({"rules": [{
            "rule": "R", "supporting_artifacts": ["rA", "rB"],
            "provenance_basis": "measured", "suggested_scope": "s"}]})
        transport, seen = self._fake_transport([good])
        out = mi.induce_rules("DIGEST", transport=transport)
        self.assertTrue(out["ok"])
        self.assertEqual(out["attempts"], 1)
        self.assertEqual(len(out["rules"]), 1)
        self.assertEqual(len(seen), 1)  # exactly one live call

    def test_reask_then_success(self) -> None:
        bad = "this is not json"
        good = json.dumps({"rules": [{
            "rule": "R", "supporting_artifacts": ["rA", "rB"],
            "provenance_basis": "said", "suggested_scope": "s"}]})
        transport, seen = self._fake_transport([bad, good])
        out = mi.induce_rules("DIGEST", transport=transport)
        self.assertTrue(out["ok"])
        self.assertEqual(out["attempts"], 2)
        self.assertEqual(len(seen), 2)
        # The re-ask carried the validation error back to the model.
        self.assertNotIn("validation_error", seen[0])
        self.assertIn("validation_error", seen[1])

    def test_degrade_to_empty_at_cap(self) -> None:
        transport, seen = self._fake_transport(["nope", "still nope", "third"])
        out = mi.induce_rules("DIGEST", transport=transport)
        self.assertFalse(out["ok"])
        self.assertEqual(out["rules"], [])
        self.assertEqual(out["attempts"], 2)
        self.assertEqual(len(seen), 2)  # HARD budget: never a 3rd call
        self.assertIsNotNone(out["error"])

    def test_single_fenced_block_tolerated(self) -> None:
        reply = ("Here is the result:\n```json\n"
                 + json.dumps({"rules": [{
                     "rule": "R", "supporting_artifacts": ["rA", "rB"],
                     "provenance_basis": "mixed", "suggested_scope": "s"}]})
                 + "\n```\n")
        transport, seen = self._fake_transport([reply])
        out = mi.induce_rules("DIGEST", transport=transport)
        self.assertTrue(out["ok"])
        self.assertEqual(out["attempts"], 1)


class ZeroSupportDrop(unittest.TestCase):
    def test_zero_support_dropped(self) -> None:
        rules = [
            {"rule": "kept", "supporting_artifacts": ["rA", "rB"],
             "provenance_basis": "said", "suggested_scope": "s"},
            {"rule": "dropped", "supporting_artifacts": [],
             "provenance_basis": "said", "suggested_scope": "s"},
        ]
        kept, dropped = mi.drop_zero_support(rules)
        self.assertEqual([r["rule"] for r in kept], ["kept"])
        self.assertEqual([r["rule"] for r in dropped], ["dropped"])


class Writers(unittest.TestCase):
    def test_append_only(self) -> None:
        out = Path(tempfile.mkdtemp()) / "induced_rules.jsonl"
        first = [{"rule": "A", "supporting_artifacts": ["r1", "r2"],
                  "provenance_basis": "said", "suggested_scope": "s"}]
        second = [{"rule": "B", "supporting_artifacts": ["r3", "r4"],
                   "provenance_basis": "measured", "suggested_scope": "s"}]
        mi.append_rules(first, out_path=out)
        mi.append_rules(second, out_path=out)
        lines = [json.loads(x) for x in out.read_text().splitlines()]
        self.assertEqual([r["rule"] for r in lines], ["A", "B"])  # appended, not overwritten

    def test_render_doc_contains_rule_and_basis(self) -> None:
        out = Path(tempfile.mkdtemp()) / "induced_rules_v1.md"
        rules = [{"rule": "Defers cluster on field QoIs.",
                  "supporting_artifacts": ["rA", "rB"],
                  "provenance_basis": "said", "suggested_scope": "fidelity gate"}]
        mi.render_doc(rules, size={"chars": 100, "est_tokens": 25, "token_cap": 10000},
                      live={"ok": True, "attempts": 1, "error": None},
                      dropped=[], out_path=out)
        text = out.read_text()
        self.assertIn("Defers cluster on field QoIs.", text)
        self.assertIn("`said`", text)
        self.assertIn("rA, rB", text)

    def test_render_doc_degraded(self) -> None:
        out = Path(tempfile.mkdtemp()) / "induced_rules_v1.md"
        mi.render_doc([], size={"chars": 1, "est_tokens": 1, "token_cap": 10000},
                      live={"ok": False, "attempts": 2, "error": "boom"},
                      dropped=[], out_path=out)
        text = out.read_text()
        self.assertIn("degraded-empty", text)
        self.assertIn("No rules were accepted", text)


if __name__ == "__main__":
    unittest.main()
