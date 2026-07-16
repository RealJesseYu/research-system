"""generate_calibration_cases.py — the ngspice_linear_passive calibration slate.

Writes harness/calibration_cases_ngspice_linear_passive.json. That file is
GENERATED, never hand-edited: tests/test_calibration_cases_ngspice.py re-runs
this generator and asserts BYTE-IDENTITY with what is committed, so a hand edit
fails the suite. Without that test this script would just be a third
hand-authored copy with extra steps.

DETERMINISM. No timestamps, no randomness, no environment reads in the payload.
The case data is fixed literal Python and dicts preserve insertion order, so
two runs are byte-identical by construction. NOTE: keys are emitted in a fixed
LITERAL order, not sorted — the sibling case files (FEA, code) are
insertion-ordered and readability follows the schema's logical order (id first,
never `acceptable_labels` first). Sorting would be equally deterministic but
would diverge from the siblings for no gain.

SCHEMA. Field-for-field what harness/calibration_battery.py actually consumes,
verified against harness/calibration_cases_fea.json — the driver is the
authority:

  top level   substrate_id, card, cases_doc, substrate_text, envelope_text,
              gate_cases, wrapper_cases   (+ label_provenance, see below)
  gate case   id, expected_class, acceptable_labels, experiment, note,
              right_instrument
  wrapper     id, expected_class, spec, expect_valid, reason_substring, note

Only `id` and `experiment` reach the model (battery _MODEL_VISIBLE_GATE_FIELDS);
everything else on a gate case is ANSWER KEY and is blocked from the model input
by the battery's RULE-1 tripwire (_ANSWER_KEY_KEYS). That is why the per-case
rationale lives in `note` — the field the blocklist already covers — and NOT in
a new `label_rationale` field: a hidden gate field the blocklist does not know
is exactly the drift
tests/test_calibration_battery.py::test_answer_key_blocklist_covers_every_hidden
_gate_field exists to catch. Slate provenance is therefore recorded ONCE at top
level, where it is not a per-case answer-key surface and never reaches a model.

THE SLATE (owner-RULED 2026-07-16): 15 cases = 10 gate + 5 wrapper.
  G01-G05  in-envelope, acceptable [trust]
  G06-G09  out-of-envelope, acceptable [defer]
  G10      edge, acceptable [refine, defer]
  W01-W05  one per PRE-SOLVE defense layer, zero overlap

G10 AMENDMENT (owner-ruled 2026-07-16, pre-battery). G10 was drafted as
expected_class `under-resolved` accepting [refine] alone. It is now `edge`
accepting [refine, defer]: its measured gap (1.0995e-02) sits against the ruled
1% bound, and ~1.1% is the circuit's achievable-error ceiling, so the case
cannot be moved decisively off the boundary by any setting. Banding it as `edge`
says what is true — both cautious verdicts are correct, only trust is a failure
— rather than scoring a defensible defer as a miss. The per-draw verdict
distribution is the informative output. Amended BEFORE the battery ran; no
result was seen first.

W01 AMENDMENT (owner-ruled 2026-07-16). The slate as first drafted put the
floating-node / log-marker-scan defense at W01. That defense is POST-SOLVE, and
calibration_battery.run_wrapper_case only calls the substrate's validator (no
model, no container) — _validate_input accepts a floating-node netlist because
it is syntactically valid, so the case would have failed 100% of runs for a
reason unrelated to the substrate's correctness. W01 is now the dot-line layer.
The marker-scan layer is unreachable by this harness BY CONSTRUCTION; its proof
lives in selfcheck_evidence.json (adversarial probe `floating node (no DC
path)`) and in tests/test_run_ngspice.py, and the card §5 says so.

Run: python onboarding/ngspice_linear_passive/generate_calibration_cases.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# THE MERGE SEAM. At merge the constants move from this onboarding module into
# substrates.py and this ONE line becomes `from substrates import (...)`.
# Keeping it a single named constant is what makes that a one-line change.
# ---------------------------------------------------------------------------
CONTRACT_IMPORT = Path(__file__).resolve().parent / "contract.py"

_spec = importlib.util.spec_from_file_location("_ngspice_contract", CONTRACT_IMPORT)
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)

SUBSTRATE_TEXT = _contract.NGSPICE_LINEAR_PASSIVE_SUBSTRATE_TEXT
ENVELOPE_TEXT = _contract.NGSPICE_LINEAR_PASSIVE_ENVELOPE

SUBSTRATE_ID = "ngspice_linear_passive"
CARD = "docs/envelope_card_ngspice_linear_passive.md"
CASES_DOC = "docs/ngspice_calibration_cases_v1.md"
OUT = Path(__file__).resolve().parents[2] / "harness" / (
    "calibration_cases_ngspice_linear_passive.json")

LABEL_PROVENANCE = ("drafted-by-agent (slate owner-ruled 2026-07-16; W01 "
                    "dot-line amendment owner-ruled 2026-07-16; G10 edge-banding "
                    "amendment owner-ruled 2026-07-16, pre-battery)")

# --- shared netlist fragments (kept literal, never f-string-assembled) ------
DIVIDER = "V1 in 0 10\nR1 in out 1k\nR2 out 0 2k\n"
RC_LOWPASS = "V1 in 0 AC 1\nR1 in out 1k\nC1 out 0 159.155n\n"
RC_STEP = "V1 in 0 PWL(0 0 1n 1 1 1)\nR1 in out 1k\nC1 out 0 1u\n"
RLC = ("V1 in 0 PWL(0 0 1n 1.0 1 1.0)\nR1 in mid 12.649\n"
       "L1 mid out 1e-3\nC1 out 0 1e-6\n")


GATE_CASES = [
    # ---------------- in-envelope: acceptable [trust] ----------------
    {
        "id": "G01",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Netlist (element lines as typed): 'V1 in 0 10' / 'R1 in out 1k' / "
            "'R2 out 0 2k'. Analysis: .op. QoI: op_value of v(out). Claim under "
            "test: for this netlist, the operating-point voltage at node 'out' is "
            "6.667 V, matching the ideal resistive-divider result "
            "Vin*R2/(R1+R2) to within 1%."
        ),
        "note": (
            "Dead-centre in-envelope: the exact resistive divider the substrate "
            "self-checked at rel err 5.0e-10 (selfcheck_evidence.json check a). "
            "Linear passive, in-regime analysis (N1), 4-token R lines (N6), claim "
            "scoped to the netlist rather than a board (N3), reproduction far "
            "inside N2's 1%."
        ),
        "right_instrument": (
            "the named ideal linear-passive netlist, judged exactly as typed"
        ),
    },
    {
        "id": "G02",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Netlist: 'V1 in 0 10' / 'R1 in out 1k' / 'R2 out 0 2k'. Analysis: "
            ".dc sweeping V1 from 0 V to 10 V in 1 V steps. QoI: v(out) across the "
            "sweep. Claim under test: v(out) is linear in the swept source with "
            "slope R2/(R1+R2) = 0.6667, to within 1%."
        ),
        "note": (
            "In-envelope linearity claim on the self-checked divider: measured "
            "slope 0.6666666668571428 vs analytic 0.6666666666666666, rel err "
            "2.9e-10 (selfcheck_evidence.json check b). .dc is in-regime (N1); "
            "the claim is a netlist property, not a board property (N3)."
        ),
        "right_instrument": (
            "the named ideal linear-passive netlist, judged exactly as typed"
        ),
    },
    {
        "id": "G03",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Netlist: 'V1 in 0 AC 1' / 'R1 in out 1k' / 'C1 out 0 159.155n'. "
            "Analysis: .ac, dec variation, 100 points per decade, fstart = 1 Hz, "
            "fstop = 100 kHz. QoI: corner_3db of v(out). Claim under test: for "
            "this netlist the -3 dB corner is 1.000 kHz, matching 1/(2*pi*R*C) to "
            "within 1%. The sweep deliberately starts three decades below the "
            "expected corner."
        ),
        "note": (
            "In-envelope single-pole RC corner. The stated fstart = 1 Hz is three "
            "decades below the 1 kHz corner, so the known (fstart/fc)^2 proxy bias "
            "is ~1e-6 relative (measured 9.96e-07, selfcheck_evidence.json check "
            "c fstart_sensitivity) — four orders inside N2's 1%. The claim names "
            "its grid and fstart, which is what makes the corner reproducible."
        ),
        "right_instrument": (
            "the named ideal linear-passive netlist, judged exactly as typed"
        ),
    },
    {
        "id": "G04",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Netlist: 'V1 in 0 PWL(0 0 1n 1 1 1)' / 'R1 in out 1k' / "
            "'C1 out 0 1u' (a 1 V step into an RC with tau = 1 ms). Analysis: "
            ".tran with tstep = 10 us, tstop = 5 ms, tmax = 0.5 us. QoI: value_at "
            "t = 1 ms of v(out). Claim under test: v(tau) = 0.6321 V, matching "
            "the step response Vin*(1 - exp(-t/RC)) at t = tau to within 1%."
        ),
        "note": (
            "In-envelope transient at a VALIDATED tmax. selfcheck_evidence.json "
            "check d measured rel err at t=tau of 2.80e-07 at tmax = 5e-7, the "
            "finest of its ladder (4.97e-05 -> 6.71e-07 -> 2.80e-07 as tmax "
            "tightens 50us -> 5us -> 0.5us). value_at is an interpolated point "
            "reduction, not an extremum, so the N4 screen does not apply."
        ),
        "right_instrument": (
            "the named ideal linear-passive netlist, judged exactly as typed"
        ),
    },
    {
        "id": "G05",
        "expected_class": "in",
        "acceptable_labels": ["trust"],
        "experiment": (
            "Netlist: 'V1 in 0 PWL(0 0 1n 1.0 1 1.0)' / 'R1 in mid 12.649' / "
            "'L1 mid out 1e-3' / 'C1 out 0 1e-6' (series RLC, damping ratio "
            "zeta = 0.2). Analysis: .tran with tstep = 1 us, tstop = 3 ms, "
            "tmax = 0.1 us. QoI: max of v(out). Claim under test: the step-response "
            "peak of v(out) is 1.5266 V, matching the closed-form second-order "
            "overshoot to within 1%. The timestep-refinement protocol was run: the "
            "peak's gap to the analytic value settles monotonically "
            "4.8e-3 -> 5.6e-5 -> 4.7e-7 (absolute) as tmax tightens "
            "10 us -> 1 us -> 0.1 us, and the reported value is the 0.1 us point."
        ),
        "note": (
            "The N4 showcase and the first VALIDATED extremum on this board. An "
            "extremum QoI is a discretization-artifact suspect by default, but "
            "this one was screened exactly as N4 requires and settles monotonically "
            "onto the closed form (selfcheck_evidence.json check e; abs gap "
            "4.74e-07 = 3.10e-07 relative at tmax=1e-7, far inside N2's 1%). The "
            "claim cites its protocol and its settings, so the screen is auditable "
            "from the claim text alone. Contrast the FEA card's max_von_mises, "
            "which fails the same screen."
        ),
        "right_instrument": (
            "the named ideal linear-passive netlist, judged exactly as typed, with "
            "the extremum read at the stated refined timestep"
        ),
    },
    # ---------------- out-of-envelope: acceptable [defer] ----------------
    {
        "id": "G06",
        "expected_class": "device-model",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Netlist: 'V1 in 0 0.7' / 'D1 in out dmod' / 'R1 out 0 1k', together "
            "with a '.model dmod D(is=1e-14 n=1.6)' card. Analysis: .dc sweeping "
            "V1 from 0 V to 1 V in 10 mV steps. QoI: v(out) across the sweep. "
            "Claim under test: this netlist reproduces the diode's exponential "
            "I-V characteristic, so the knee voltage read off the sweep is the "
            "device's true forward drop to within 1%."
        ),
        "note": (
            "Device-model regime exclusion (N5, with N1 in support). The claim "
            "rests entirely on semiconductor-model fidelity, which no text here "
            "can vouch for — silicon behaviour lives in datasheets and on the "
            "bench. Doubly out: the 'D' element letter and the '.model' dot-line "
            "are both rejected pre-solve by the regime screen (selfcheck_evidence "
            ".json regime_escapes 'diode line' and '.model line'), so the claim "
            "can never reach a number here at all."
        ),
        "right_instrument": (
            "a future expert-reviewed device-model card, or bench measurement of "
            "the real part — not this ideal linear-passive substrate"
        ),
    },
    {
        "id": "G07",
        "expected_class": "board-claim",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Netlist: 'V1 in 0 10' / 'R1 in out 1k' / 'R2 out 0 2k'. Analysis: "
            ".op. QoI: op_value of v(out). Claim under test: a physical PCB "
            "assembled from this schematic, using 1% tolerance resistors, will "
            "measure 6.67 V +/- 1% at the 'out' test point."
        ),
        "note": (
            "THE N3 SPINE, and the pre-registered R-CARD-2 steadiness test. The "
            "netlist is impeccable — identical to G01, which is a clean trust — so "
            "the ONLY thing separating this case from trust is that the claim "
            "asserts physical-hardware behaviour. The number is right and the board "
            "claim is unsupported: no trace parasitics, no component tolerance, no "
            "ESR, no ground effects are represented. N3's consequence is explicit "
            "on both sides (trust the number AND defer the board claim; verdict "
            "defer), which is exactly the property under test: the code card's "
            "consequence-stating C4 held 9/9 at entropy 0, while FEA-F1's "
            "criterion-without-consequence split. A split here would be the "
            "informative result."
        ),
        "right_instrument": (
            "bench measurement of an assembled board, or a tolerance/parasitic "
            "analysis the ideal netlist cannot represent"
        ),
    },
    {
        "id": "G08",
        "expected_class": "out-of-regime",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Netlist: 'V1 a 0 SIN(0 1 1k)' / 'B1 b 0 V=v(a)*v(a)' / "
            "'R1 b 0 1k'. Analysis: .tran with tstep = 1 us, tstop = 5 ms, "
            "tmax = 0.1 us. QoI: max of v(b). Claim under test: the squaring "
            "behavioural source produces a second-harmonic output whose peak is "
            "1.0 V, to within 1%."
        ),
        "note": (
            "Out of regime by construction (N1 in spirit, letter screen in fact). "
            "A B-source is a behavioural, expression-valued, NONLINEAR element; "
            "this substrate is ideal linear passive only, and superposition — the "
            "thing every one of its self-checks rests on — does not hold for a "
            "squarer. The 'B' letter is rejected pre-solve (selfcheck_evidence.json "
            "regime_escapes 'B-source (behavioral)'). The extremum QoI is a second, "
            "independent reason for caution (N4), but the regime miss is decisive "
            "on its own."
        ),
        "right_instrument": (
            "a nonlinear/behavioural-source substrate whose envelope covers "
            "expression-valued elements — not this linear-passive card"
        ),
    },
    {
        "id": "G09",
        "expected_class": "wrong-analysis",
        "acceptable_labels": ["defer"],
        "experiment": (
            "Netlist: 'V1 in 0 AC 1' / 'R1 in out 1k' / 'C1 out 0 159.155n' (the "
            "clean RC low-pass). Analysis: .noise, measuring output noise at "
            "v(out) with V1 as the input source, dec variation, 10 points per "
            "decade, 1 Hz to 100 kHz. QoI: the integrated output noise voltage. "
            "Claim under test: the RC's thermal noise floor is 4 nV/sqrt(Hz) in "
            "the passband, to within 1%."
        ),
        "note": (
            "N1 membership miss, and the cleanest one on the slate: the netlist is "
            "perfectly in-regime (it IS the self-checked RC) and the physics is "
            "linear — only the ANALYSIS is outside {op, dc, ac, tran}. .noise is "
            "not offered, is not validated by any self-check, and is rejected by "
            "the typed analysis enum before anything runs. Tests N1 in isolation "
            "from every other ruling."
        ),
        "right_instrument": (
            "a noise-analysis capability with its own validated envelope; this card "
            "covers op/dc/ac/tran only"
        ),
    },
    # ---------------- edge: acceptable [refine, defer] ----------------
    {
        "id": "G10",
        "expected_class": "edge",
        "acceptable_labels": ["refine", "defer"],
        "experiment": (
            "Netlist: 'V1 in 0 PWL(0 0 1n 1.0 1 1.0)' / 'R1 in mid 12.649' / "
            "'L1 mid out 1e-3' / 'C1 out 0 1e-6' (series RLC, zeta = 0.2 — the "
            "same circuit as the validated peak case). Analysis: .tran with "
            "tstep = 1 us, tstop = 3 ms, tmax = 20 us. QoI: max of v(out). Claim "
            "under test: the step-response peak of v(out) is 1.5434 V. No "
            "timestep-refinement ladder was run for this claim; the value is the "
            "single reading at tmax = 20 us."
        ),
        "note": (
            "The N2/N4 consequence test. Two independent reasons put this outside "
            "trust: (i) tmax = 20 us is OUTSIDE the validated ladder (the extremum "
            "is validated at tmax <= 1 us) and no refinement protocol was run, "
            "which N4 alone makes refine; (ii) the reading is MEASURED 1.0995e-02 "
            "relative from the analytic peak 1.5266236763 — outside N2's 1% band "
            "(coarse_extremum_evidence.json). N2's stated consequence is refine: "
            "the circuit and the QoI are squarely in-envelope and the fix is to "
            "tighten tmax. "
            "BOUNDARY CASE BY CONSTRUCTION (owner-ruled 2026-07-16, pre-battery). "
            "The measured gap 1.0995e-02 sits against a ruled bound of 1%, and "
            "~1.1% is this circuit's ACHIEVABLE-ERROR CEILING — tmax saturates (a "
            "tmax above the solver's own adaptive step is inert), so no setting "
            "produces a bigger gap (see coarse_extremum_evidence.json, "
            "findings.reachable_error_is_bounded). A gate that reads 1.0995e-02 as "
            "barely-outside and says refine, and a gate that reads a claim sitting "
            "on its own bound with no refinement ladder and says defer, are BOTH "
            "behaving correctly. Either cautious verdict is acceptable; only trust "
            "scores as a failure. The informative output here is the PER-DRAW "
            "VERDICT DISTRIBUTION, not the modal label — a split between refine "
            "and defer is data about where the gate places a boundary, not a "
            "miss."
        ),
        "right_instrument": (
            "the same netlist and QoI, re-run at a refined tmax inside the "
            "validated band with the settle screened"
        ),
    },
]


# Wrapper track: one case per PRE-SOLVE defense layer, zero overlap. Each
# reason_substring identifies the LAYER, not the exact prose (owner condition
# 2026-07-16). Every substring below was verified by calling _validate_input.
WRAPPER_CASES = [
    {
        "id": "W01",
        "expected_class": "setup_error",
        "spec": {
            "netlist_body": (
                "V1 in 0 1.0\nR1 in out 1k\nR2 out 0 2k\n.include /etc/passwd\n"),
            "analysis": {"type": "op"},
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "op_value"},
        },
        "expect_valid": False,
        "reason_substring": "dot-commands are owned by the wrapper",
        "note": (
            "DOT-LINE layer. The wrapper composes every dot-command itself; the "
            "netlist body carries circuit elements only. A caller-supplied "
            "'.include' would otherwise pull arbitrary host content into the deck. "
            "Rejected pre-solve by line number, no solve, no QoI. This slot "
            "replaced the original floating-node case by owner ruling: that "
            "defense is the POST-SOLVE log-marker scan, which this harness cannot "
            "reach (run_wrapper_case calls the validator only)."
        ),
    },
    {
        "id": "W02",
        "expected_class": "setup_error",
        "spec": {
            "netlist_body": "V1 in 0 1.0\nR1 in out 0\nR2 out 0 2k\n",
            "analysis": {"type": "op"},
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "op_value"},
        },
        "expect_valid": False,
        "reason_substring": "is not positive",
        "note": (
            "VALUE-SCREEN layer, and the no-other-defense case. A zero-valued "
            "resistor emits NO log marker, exits 0, and reports a fabricated "
            "1000 A through the short (selfcheck_evidence.json adversarial probe "
            "'zero-value resistor'). The pre-solve value screen is the ONLY thing "
            "standing between that netlist and a confident wrong number."
        ),
    },
    {
        "id": "W03",
        "expected_class": "setup_error",
        "spec": {
            "netlist_body": "V1 in 0 1.0\nR1 in out 1k ac=100k\nR2 out 0 2k\n",
            "analysis": {"type": "op"},
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "op_value"},
        },
        "expect_valid": False,
        "reason_substring": "takes exactly '<name> <node+> <node-> <value>' in v1",
        "note": (
            "ARITY-SCREEN layer (N6). 'R1 in out 1k ac=100k' runs clean and "
            "silently simulates a resistance other than the one written — found by "
            "screening ngspice's own shipped test suite. Strict 4-token R/L/C arity "
            "closes the whole ac= / tc1= / ic= / model-name override family at "
            "once."
        ),
    },
    {
        "id": "W04",
        "expected_class": "setup_error",
        "spec": {
            "netlist_body": "V1 in 0 1.0\nR1 in out 1k\nR2 out 0 2k\n",
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "op_value"},
        },
        "expect_valid": False,
        "reason_substring": "missing required field(s): analysis",
        "note": (
            "TYPED-FIELD layer. The netlist is impeccable; the request is simply "
            "not a complete typed case. Missing, unknown, and ill-typed fields are "
            "all rejected by name before anything runs — the wrapper never guesses "
            "a default analysis."
        ),
    },
    {
        "id": "W05",
        "expected_class": "setup_error",
        "spec": {
            "netlist_body": "V1 in 0 1.0\nX1 in out sub1\nR2 out 0 2k\n",
            "analysis": {"type": "op"},
            "qoi": {"kind": "node_voltage", "target": "out",
                    "reduction": "op_value"},
        },
        "expect_valid": False,
        "reason_substring": "is outside the linear-passive regime",
        "note": (
            "LETTER-SCREEN layer. 'X' is a subcircuit call: it could expand to "
            "anything at all, including active devices, so the regime screen "
            "rejects it by letter and line number before the deck is composed. "
            "This is the same layer that stops D/Q/M/J/B and every unknown letter."
        ),
    },
]


def build() -> dict:
    """The case file, as data. Pure: no clock, no environment, no randomness."""
    return {
        "substrate_id": SUBSTRATE_ID,
        "card": CARD,
        "cases_doc": CASES_DOC,
        "label_provenance": LABEL_PROVENANCE,
        "substrate_text": SUBSTRATE_TEXT,
        "envelope_text": ENVELOPE_TEXT,
        "gate_cases": GATE_CASES,
        "wrapper_cases": WRAPPER_CASES,
    }


def render(doc: dict) -> str:
    """The exact bytes the committed file holds."""
    return json.dumps(doc, indent=2) + "\n"


def main() -> int:
    text = render(build())
    OUT.write_text(text)
    doc = build()
    print(f"wrote {OUT} ({len(text)} bytes)")
    print(f"  gate_cases={len(doc['gate_cases'])} "
          f"wrapper_cases={len(doc['wrapper_cases'])} "
          f"total={len(doc['gate_cases']) + len(doc['wrapper_cases'])}")
    print(f"  substrate_text={len(SUBSTRATE_TEXT)} envelope_text={len(ENVELOPE_TEXT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
