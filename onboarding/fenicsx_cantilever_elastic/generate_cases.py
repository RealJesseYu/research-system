"""generate_cases.py — generate the battery case file FROM contract.py.

The case file `harness/calibration_cases_fenicsx_cantilever_elastic.json` is
GENERATED, never hand-authored. contract.py is the ONE runtime source of truth:
the card points at it by path, and this script emits the battery's JSON from it.
A test (tests/test_run_fenicsx.py::TestCaseFileGeneration) regenerates the file
and asserts BYTE-IDENTITY against the committed copy, so the two cannot drift
without a test failure.

Run:  venv/bin/python3 onboarding/fenicsx_cantilever_elastic/generate_cases.py
      venv/bin/python3 onboarding/fenicsx_cantilever_elastic/generate_cases.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract  # noqa: E402  (staging module, path-injected)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CASE_FILE = (_PROJECT_ROOT / "harness" /
             "calibration_cases_fenicsx_cantilever_elastic.json")


def build_case_file() -> dict:
    """The case-file dict, composed from contract.py alone.

    Shape mirrors harness/calibration_cases_fea.json exactly (read from disk):
    substrate_id / card / cases_doc / substrate_text / envelope_text /
    gate_cases / wrapper_cases — the shapes harness/calibration_battery.py
    actually consumes.
    """
    return {
        "substrate_id": contract.SUBSTRATE_ID,
        "card": contract.CARD_PATH,
        "cases_doc": contract.CASES_DOC,
        # Generated from contract.py — the newlines are flattened because these
        # are prose blocks handed to a model, not code.
        "substrate_text": _flatten(contract.SUBSTRATE_TEXT),
        "envelope_text": _flatten(contract.ENVELOPE_TEXT),
        "gate_cases": [dict(c) for c in contract.GATE_CASES],
        "wrapper_cases": [dict(c) for c in contract.WRAPPER_CASES],
    }


def _flatten(text: str) -> str:
    """Collapse a hard-wrapped prose block into single-spaced lines.

    The contract is wrapped for human review in contract.py; the model sees one
    flowing block. Paragraph breaks (blank lines) survive as ' | ' separators so
    section boundaries remain legible.
    """
    paragraphs = [" ".join(p.split()) for p in text.split("\n\n") if p.strip()]
    return " | ".join(paragraphs)


def render() -> str:
    """The exact bytes of the case file."""
    return json.dumps(build_case_file(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the fenicsx battery case file.")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed file matches; write nothing")
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        if not CASE_FILE.exists():
            print(f"MISSING: {CASE_FILE}")
            return 1
        actual = CASE_FILE.read_text()
        if actual != rendered:
            print(f"DRIFT: {CASE_FILE} does not match contract.py")
            return 1
        print(f"OK: {CASE_FILE} is byte-identical to contract.py's rendering")
        return 0

    CASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CASE_FILE.write_text(rendered)
    n_gate = len(contract.GATE_CASES)
    n_wrap = len(contract.WRAPPER_CASES)
    print(f"wrote {CASE_FILE}")
    print(f"  gate cases: {n_gate}  wrapper cases: {n_wrap}  total: {n_gate + n_wrap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
