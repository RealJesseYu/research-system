# Calibration Battery — (SUBSTRATE, PHYSICS-REGIME)  ·  TEMPLATE

> **STATUS: DRAFT.** A battery of **10–20 hand-labeled cases** spanning
> clearly-in-envelope, clearly-out-of-envelope, and edge cases, used to score
> the fidelity gate's verdicts against known-correct labels. Card unit = the
> (substrate, physics-regime) pair.

> ⚙ **Assembling and labeling the cases (this document) is offline. EXECUTING
> the battery to score the gate is a real compute run** (it dispatches model
> and/or solver runs) and requires an **explicit owner OK before it fires.**
> CFD reference: `harness/fidelity_case_runner.py`, `harness/triage_battery.py`,
> `harness/triage_cases/`.

---

## Coverage target
| Band | Target count | Purpose |
|---|---|---|
| Clearly in-envelope | `<~4–6>` | gate should `trust`/`refine` |
| Edge / near-boundary | `<~4–6>` | gate should `refine` with the right caution |
| Clearly out-of-envelope | `<~4–6>` | gate should `defer` / route away |
| **Total** | **10–20** | |

## Case schema (one row per case; the label is the ground truth)
| Field | Meaning |
|---|---|
| `case_id` | stable id |
| `spec` | the stage-2 spec (or pointer to a fixture file) |
| `expected_verdict` | `trust | refine | defer` — the hand label |
| `expected_class` | `in-envelope | edge | out-of-envelope | un-buildable | un-extractable` |
| `label_rationale` | one line: *why* this is the correct verdict (the domain-expert justification) |
| `label_provenance` | `drafted-by-agent | expert-reviewed` |

## Cases
```
# fill 10–20 rows; each MUST carry a label_rationale and a label_provenance.
- case_id: <...>
  spec: <fixture path or inline>
  expected_verdict: <trust|refine|defer>
  expected_class: <...>
  label_rationale: <...>
  label_provenance: <drafted-by-agent|expert-reviewed>
```

## Scoring (⚙ run — owner OK required)
- Run each case's spec through the fidelity gate; compare `verdict` to
  `expected_verdict`.
- Report: per-class hit rate, confusion (esp. false `trust` on an
  out-of-envelope case — the dangerous error), and any gate-error candidates for
  the failure-bin read.
- A false `trust` on a labeled out-of-envelope case is a **bin (e) fidelity-gate
  error** and must be surfaced, not averaged away.
