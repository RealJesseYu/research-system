# Memo D.3 — QoI vocabulary is per-substrate in SHAPE, not just contents

**Date:** 2026-07-17. **Companion code:** `tools/qoi_vocab.py` (the lookup),
`stages/stage2_spec.py` (the consumer), `tests/test_qoi_vocab.py` /
`tests/test_d3_retry_surfaces.py` (the proofs). Human-facing note; no frozen
document is edited by D.3.

## The two-shape fact

A substrate's structured QoI vocabulary differs from another's not merely in
its word lists but in its GRAMMAR. One table keyed the same way for every
substrate would wave wrong-grammar requests through. Two shapes exist today,
and the vocab record is therefore TAGGED (one frozen dataclass per shape;
validators dispatch on the shape, never on a substrate name):

1. **field-reduction shape** (cavity class): a QoI request is a *reduction
   over a field* — `operation` × `component` × a field-name grammar ×
   spatial `mask` types. Structured source: `tools/run_cfd.py`
   (`QOI_OPERATIONS`, `QOI_COMPONENTS`, `_QOI_FIELD_RE`, `MASK_TYPES`).

2. **named-quantity shape** (ngspice/FEA class): a QoI request *names a
   quantity* — enumerated `kind` × a target-name grammar × enumerated
   `reduction` (+ `at` for `value_at`). Structured source:
   `tools/run_ngspice.py` (`_QOI_KINDS`, `_NAME_RE`, `_REDUCTIONS`).

Only `max`/`min` collide between the two lists, and they collide by accident
of English (spatial-field reduction vs solved-sweep reduction). The staged
onboarding memo `onboarding/ngspice_linear_passive/schema_fragment.py`
reached the same conclusion independently and is corroborating prose.

## Packet correction (recorded)

The D.3 packet pointed at the ngspice onboarding `contract.py` as the
vocabulary source. That file is PROSE (D.2's finding, reconfirmed): the
structured QoI vocabulary for ngspice lives in the wrapper,
`tools/run_ngspice.py:152-164`, exactly mirroring how cavity's lives in
`tools/run_cfd.py:61-70,305`. Wrappers own vocabularies; contracts describe
them.

## Where things are wired

- Production `_VOCABS` wires **cavity alone** (mirroring the registry's
  `_CONTRACTS` and selection's `_SIGNATURES`): members ARE `run_cfd`'s
  objects by import, assertIs-proven — no third copy. `vocab_for` fails loud
  (KeyError unknown id, LookupError unwired) and never falls back to cavity.
- The **ngspice record exists in tests only** (`tests/test_qoi_vocab.py`,
  built from `run_ngspice`'s own constants) until the promotion ruling, per
  the wire-alongside-routability discipline.
- The validator's error strings are **model-visible** (D.3 Step 0 proved the
  re-ask path live and byte-pinned it: `tests/fixtures/d3/`), so error text
  is behavior; the cavity strings are preserved byte-identically, including
  the component string's hardcoded `"mag" or 0|1|2` prose (an acknowledged
  awkward seam, flagged in code).

## Substrate-card suggestion (no frozen edit made)

If the substrate card format should carry this fact, the right home is a
one-line `qoi_shape: field_reduction | named_quantity` field on each card,
added under a card-format ruling — not edited into any card frozen for this
wave. Stated here rather than done.
