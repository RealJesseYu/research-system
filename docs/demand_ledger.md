# Demand Ledger

Capabilities the running system has **asked for** — each named by concrete
evidence (a defer/refine verdict, a halt, a blocked QoI) rather than by
speculation. A row is opened when a real run demonstrates the gap and closed
when a scheduled build delivers the capability. This is the "expand only on
evidence" discipline made auditable: nothing is built because it *might* be
needed; a row here is the evidence that it *is*.

| # | Capability demanded | Named by (evidence) | Blocked QoI / need | Scheduled carrier | Status |
|---|---|---|---|---|---|
| 1 | Field export / spatially-masked reductions | Two defer verdicts in run `20260714T152314Z` (passes 2 and 3) | Interior / masked extrema — the current contract offers only whole-domain volume reductions, so an interior or region-masked extremum cannot be extracted | Multi-QoI build, week of 7/20 | CAPABILITY DELIVERED (see note) |

## Notes

- **Entry 1.** The extraction contract (`substrates.py` §3) exposes single-shot
  whole-domain reductions (`volAverage | min | max | volIntegrate`) at the
  latest written time. Two passes of run `20260714T152314Z` deferred because
  the hypothesis needed a QoI over an *interior* or *masked* subregion — a
  field export or spatially-masked reduction the contract does not provide.
  Global `min(p)` is additionally contaminated by the lid-corner singularity
  (envelope card §4G), so a whole-domain extremum is not a safe substitute.
  The multi-QoI build (week of 7/20) is the scheduled carrier.

  **STATUS: CAPABILITY DELIVERED** (`50a4646` part A, the wrapper + this commit,
  part B, the model-visible contract and spec schema). The contract
  (`substrates.py` §3) now offers a multi-QoI vector of masked reductions
  (corner_exclusion / boundary_exclusion / box) plus a compact field export,
  and the spec schema (`stages/stage2_spec.py`) learned the `qois` list and the
  per-qoi `mask` vocabulary. This closes the 7/14 defer class **pending first
  in-pipeline use** — the capability is built and contract-visible, but no
  supervised run has yet requested a masked extremum; the row is retired on that
  first in-pipeline exercise. (Screening caveat carried into the contract and
  envelope card §4H: masked extrema must be shown mask-radius-insensitive before
  they are relied on — the measured interior min(p) at Re 100 swings −0.270 →
  −0.141 from radius 0.05 to 0.10.)
