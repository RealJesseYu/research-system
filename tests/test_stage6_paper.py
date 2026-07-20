"""
test_stage6_paper.py — standalone tests of the real Paper stage (Step 22).
Deterministic, ZERO model calls: model_call._invoke_transport (the factored
transport seam, per test_transport_retry.py) is patched with fakes, the
journal read-side is patched with canned summaries, and the reference seam
runs in offline mode against tests/fixtures/refs_canned.json.

Run directly: venv/bin/python3 tests/test_stage6_paper.py
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
from baton import Baton
from harness.paper_lint import REQUIRED_HEADING, lint_paper
from stages import desk_review, stage6_paper

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "paper"

CANNED_SUMMARIES = [
    {"kind": "learned_summary", "run_id": "prev1", "text": "newest canned lesson"},
    {"kind": "learned_summary", "run_id": "prev2", "text": "older canned lesson"},
]

FAKE_ITEMS = {
    "trust": [
        {
            "kind": "none_required",
            "reason": "The gate trusted the instrument for this QoI; nothing to validate.",
        }
    ],
    "refine": [
        {"claim": "Confirm the volAverage(mag(U)) shift at finer mesh resolution."}
    ],
    "defer": [
        {
            "substrate": "a scalar-transport-capable solver",
            "conditions": "Re 200 cavity with a passive tracer step",
            "measurement": "concentration-variance decay rate over 20 s",
        }
    ],
}


class FakeTransport:
    """Answers every stage-6 call with valid JSON, keyed off the stage_input
    the stage assembled (sidecar task vs section draft/reflect vs the
    2026-07-20 desk screen). Records
    every (stage_input, model) pair for assertions."""

    def __init__(self):
        self.calls: list[dict] = []
        self.models: list[str] = []
        self.sidecar_first_observed: list[bool] = []
        self.desk_reviews: list[dict] = []

    def __call__(self, system_prompt: str, user_turn: str, model: str) -> str:
        payload = json.loads(user_turn)
        stage_input = payload.get("original_input", payload)
        self.calls.append(stage_input)
        self.models.append(model)
        run_id = stage_input["run_id"]
        if stage_input.get("task") == "validation_sidecar":
            return json.dumps(
                {
                    "ack_run_id": run_id,
                    "validation_items": FAKE_ITEMS[stage_input["fidelity_class"]],
                }
            )
        # A desk-screen call (2026-07-20): the paper exists by now, and the
        # fake passes it so the happy path stays a happy path. The reject
        # routes have their own tests against real reviewer output.
        if "manuscript_markdown" in stage_input:
            self.desk_reviews.append(stage_input)
            return json.dumps(
                {"ack_run_id": run_id, "desk_reject": False,
                 "reasons": [], "remedy": "none"}
            )
        # A section call: SIDECAR-FIRST means the sidecar file must already
        # exist on disk while the paper does not yet (checked on every
        # first-pass section call).
        stage_dir = Path("runs") / run_id / "stage6"
        self.sidecar_first_observed.append(
            (stage_dir / "paper_validation.json").is_file()
            and not (stage_dir / "paper.md").is_file()
        )
        section = stage_input["section"]
        kind = "reflected" if "draft_section_markdown" in stage_input else "drafted"
        body = f"{kind} body for {section}."
        if section == "Title and Abstract":
            body = f"# Canned Title\n\n{body}"
        return json.dumps({"ack_run_id": run_id, "section_markdown": body})


class Stage6TestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = Path.cwd()
        os.chdir(self._tmp.name)
        self._old_refs_mode = stage6_paper.REFS_MODE
        stage6_paper.REFS_MODE = "offline"
        self._patches = [
            patch.object(
                stage6_paper,
                "journal_recent_by_kind",
                lambda kind, limit=3: CANNED_SUMMARIES,
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        stage6_paper.REFS_MODE = self._old_refs_mode
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def make_baton(self, run_id: str, verdict_fixture: str) -> Baton:
        run_dir = Path("runs") / run_id
        (run_dir / "stage3").mkdir(parents=True)
        (run_dir / "log.txt").write_text("")
        shutil.copy(FIXTURES / verdict_fixture, run_dir / "stage3" / "verdict.json")
        stage5 = json.loads((FIXTURES / "stage5_thought.json").read_text())
        return Baton(
            run_id=run_id,
            created_at="2026-07-11T00:00:00+00:00",
            mode="auto",
            payload={
                "thought": stage5["thought"],
                "iterate_decision": stage5["iterate_decision"],
            },
            history=[],
        )

    def run_stage(self, run_id: str, verdict_fixture: str) -> tuple[Baton, FakeTransport]:
        baton = self.make_baton(run_id, verdict_fixture)
        fake = FakeTransport()
        with patch.object(model_call, "_invoke_transport", fake):
            baton = stage6_paper.run(baton)
        return baton, fake


class TestHappyPath(Stage6TestCase):
    def test_trust_run_assembles_lint_clean_paper(self):
        run_id = "s6-trust"
        baton, fake = self.run_stage(run_id, "verdict_trust.json")

        # 1 sidecar call + 8 sections x (draft + reflect) + 1 desk screen
        # (2026-07-20) = 18 calls, all on the explicit ruled pin.
        self.assertEqual(len(fake.calls), 18)
        # Stage 6 legitimately spans TWO tiers since 2026-07-20: sections are
        # workhorse drafting, the desk screen is a hard judgment about whether
        # the paper may stand. Asserting one pin would force them to agree.
        self.assertEqual(
            set(fake.models),
            {stage6_paper.STAGE6_MODEL, desk_review.DESK_REVIEW_MODEL},
        )

        # SIDECAR-FIRST held on every first-pass section call.
        self.assertEqual(len(fake.sidecar_first_observed), 16)
        self.assertTrue(all(fake.sidecar_first_observed))

        stage_dir = Path("runs") / run_id / "stage6"
        sidecar = json.loads((stage_dir / "paper_validation.json").read_text())
        self.assertEqual(sidecar["fidelity_class"], "trust")
        self.assertEqual(sidecar["validation_items"], FAKE_ITEMS["trust"])

        paper = (stage_dir / "paper.md").read_text()
        self.assertTrue(paper.startswith("# Canned Title"))
        for name in stage6_paper.SECTION_NAMES[1:]:
            self.assertIn(f"## {name}", paper)
        # The reflection pass's output is what lands in the paper.
        self.assertIn("reflected body for Results.", paper)
        self.assertNotIn("drafted body for Results.", paper)

        self.assertEqual(lint_paper(run_id), [])
        self.assertEqual(len(baton.history), 1)
        self.assertEqual(baton.history[0]["stage"], "stage6_paper")
        self.assertIn("fidelity_class=trust", baton.history[0]["note"])

    def test_payload_is_untouched(self):
        run_id = "s6-payload"
        baton = self.make_baton(run_id, "verdict_trust.json")
        before = copy.deepcopy(baton.payload)
        with patch.object(model_call, "_invoke_transport", FakeTransport()):
            baton = stage6_paper.run(baton)
        self.assertEqual(baton.payload, before)

    def test_refine_and_defer_sidecars(self):
        for label, fixture in (
            ("refine", "verdict_refine.json"),
            ("defer", "verdict_defer.json"),
        ):
            run_id = f"s6-{label}"
            self.run_stage(run_id, fixture)
            sidecar = json.loads(
                (Path("runs") / run_id / "stage6" / "paper_validation.json").read_text()
            )
            self.assertEqual(sidecar["fidelity_class"], label)
            self.assertEqual(sidecar["validation_items"], FAKE_ITEMS[label])
            self.assertEqual(lint_paper(run_id), [])

    def test_sidecar_inputs_are_exactly_the_ruled_ones(self):
        run_id = "s6-inputs"
        _, fake = self.run_stage(run_id, "verdict_defer.json")
        sidecar_calls = [
            c for c in fake.calls if c.get("task") == "validation_sidecar"
        ]
        self.assertEqual(len(sidecar_calls), 1)
        self.assertEqual(
            sorted(sidecar_calls[0]),
            sorted(
                [
                    "run_id",
                    "task",
                    "fidelity_class",
                    "stage3_rationale",
                    "stage5_justification",
                ]
            ),
        )
        # References reach exactly Background and References; the sidecar
        # reaches exactly What Humans Must Validate.
        for call in fake.calls:
            if "section" not in call:
                continue
            self.assertEqual(
                "references" in call,
                call["section"] in ("Background", "References"),
                call["section"],
            )
            self.assertEqual(
                "validation_sidecar" in call,
                call["section"] == REQUIRED_HEADING,
                call["section"],
            )


class TestVerdictHandling(Stage6TestCase):
    def test_missing_verdict_is_an_honest_crash(self):
        baton = self.make_baton("s6-noverdict", "verdict_trust.json")
        (Path("runs") / "s6-noverdict" / "stage3" / "verdict.json").unlink()
        with patch.object(model_call, "_invoke_transport", FakeTransport()):
            with self.assertRaises(RuntimeError) as ctx:
                stage6_paper.run(baton)
        self.assertIn("no stage-3 verdict", str(ctx.exception))

    def test_invalid_verdict_label_is_an_honest_crash(self):
        baton = self.make_baton("s6-badlabel", "verdict_trust.json")
        (Path("runs") / "s6-badlabel" / "stage3" / "verdict.json").write_text(
            json.dumps({"label": "maybe", "rationale": "r", "right_instrument": "i"})
        )
        with patch.object(model_call, "_invoke_transport", FakeTransport()):
            with self.assertRaises(RuntimeError) as ctx:
                stage6_paper.run(baton)
        self.assertIn("verdict label", str(ctx.exception))


class TestOfflineRefsSeam(Stage6TestCase):
    def test_offline_mode_reads_the_canned_fixture(self):
        refs = stage6_paper.gather_references("any query", "no-run")
        canned = json.loads(stage6_paper.REFS_FIXTURE_PATH.read_text())
        self.assertEqual(len(refs), len(canned))
        for n, (ref, record) in enumerate(zip(refs, canned), start=1):
            self.assertEqual(ref["ref"], f"R{n}")
            self.assertEqual(ref["title"], record["title"])
            self.assertEqual(ref["source"], "canned")


class TestLintFeedbackLoop(Stage6TestCase):
    def test_sidecar_failure_regenerates_sidecar_and_derived_section(self):
        run_id = "s6-regen"
        baton = self.make_baton(run_id, "verdict_trust.json")
        fake = FakeTransport()
        lint_results = iter(
            [
                [
                    {
                        "code": "items_invalid",
                        "target": "sidecar",
                        "message": "synthetic sidecar defect",
                    }
                ],
                [],
            ]
        )
        with patch.object(model_call, "_invoke_transport", fake), patch.object(
            stage6_paper, "lint_paper", lambda rid: next(lint_results)
        ):
            baton = stage6_paper.run(baton)
        # 17 first-pass calls + regeneration: 1 sidecar + draft/reflect of
        # the sidecar-derived What Humans Must Validate section = 20.
        self.assertEqual(len(fake.calls), 21)  # +1 desk screen
        regen_calls = fake.calls[17:]
        self.assertEqual(regen_calls[0]["task"], "validation_sidecar")
        self.assertEqual(
            regen_calls[0]["lint_errors_to_fix"], ["synthetic sidecar defect"]
        )
        self.assertEqual(regen_calls[1]["section"], REQUIRED_HEADING)
        self.assertEqual(regen_calls[2]["section"], REQUIRED_HEADING)
        self.assertIn("draft_section_markdown", regen_calls[2])
        self.assertEqual(len(baton.history), 1)

    def test_section_failure_regenerates_only_that_section(self):
        run_id = "s6-regen-section"
        baton = self.make_baton(run_id, "verdict_trust.json")
        fake = FakeTransport()
        lint_results = iter(
            [
                [
                    {
                        "code": "heading_missing",
                        "target": REQUIRED_HEADING,
                        "message": "synthetic heading defect",
                    }
                ],
                [],
            ]
        )
        with patch.object(model_call, "_invoke_transport", fake), patch.object(
            stage6_paper, "lint_paper", lambda rid: next(lint_results)
        ):
            stage6_paper.run(baton)
        self.assertEqual(len(fake.calls), 20)  # 17 + one section redraft + desk screen
        self.assertEqual(fake.calls[17]["section"], REQUIRED_HEADING)
        self.assertEqual(
            fake.calls[17]["lint_errors_to_fix"], ["synthetic heading defect"]
        )

    def test_persistent_failure_raises_with_evidence_on_disk(self):
        run_id = "s6-crash"
        baton = self.make_baton(run_id, "verdict_trust.json")
        always_failing = [
            {
                "code": "items_invalid",
                "target": "sidecar",
                "message": "unfixable synthetic defect",
            }
        ]
        with patch.object(model_call, "_invoke_transport", FakeTransport()), patch.object(
            stage6_paper, "lint_paper", lambda rid: list(always_failing)
        ):
            with self.assertRaises(RuntimeError) as ctx:
                stage6_paper.run(baton)
        self.assertIn("failed lint after 2 regeneration", str(ctx.exception))
        # Honest crash: the evidence is on disk.
        stage_dir = Path("runs") / run_id / "stage6"
        self.assertTrue((stage_dir / "paper.md").is_file())
        self.assertTrue((stage_dir / "paper_validation.json").is_file())
        self.assertEqual(len(baton.history), 0)


if __name__ == "__main__":
    unittest.main()
