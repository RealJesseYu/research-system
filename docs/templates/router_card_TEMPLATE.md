# Router Card — (SUBSTRATE, PHYSICS-REGIME)  ·  TEMPLATE

> **STATUS: DRAFT.** The router card gives the upper layers the abstract facts
> to *choose* this substrate for a hypothesis, on `{validated envelope, cost,
> confidence}` alone — **without naming the solver** (substrate-agnostic upper
> layers, an architecture invariant). Card unit = the (substrate,
> physics-regime) pair, matching its envelope card.

> **Status of routing in the system:** there is no standalone multi-substrate
> router yet. Today the fidelity gate's `right_instrument` field
> (`stages/stage3_fidelity_gate.py`) is the only routing decision made. Author
> this card so the *next* substrate has a real choice to route to.

---

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `<substrate id>` |
| Physics regime | `<regime>` |
| Envelope card | `<docs/envelope_card_<...>.md>` |
| Provenance state (from envelope card §2) | `<drafted-by-agent | provisionally-signed | signed>` |

## 2. Capability summary (abstract — no solver names above the wrapper)
| Property | Value |
|---|---|
| Physics served | `<what classes of hypothesis this substrate can test>` |
| QoIs servable | `<abstract QoI classes — e.g. whole-domain field reductions>` |
| QoIs NOT servable | `<the honest exclusions — derived fields, masked sub-domains, …>` |
| Validated-envelope summary | `<one-line pointer to envelope §3A/3B>` |

## 3. Cost tier
| Field | Value |
|---|---|
| Cost tier | `<cheap | moderate | expensive — the routing-relevant bucket>` |
| Measured basis | `<envelope card §7 rates + run ids>` |
| Hard kill limit | `<timeout>` |
| Per-unit rate | `<RANGE, not a constant>` |

## 4. Confidence / maturity
| Field | Value |
|---|---|
| Maturity rung | `<drafted / provisional / mature — see reviewer rubric>` |
| Human-at-trust-calls? | `<yes until signed>` |
| Override history | `<memory/override_ledger.jsonl summary>` |

## 5. Routing rules
- **Prefer this substrate when:** `<the hypothesis + QoI classes it fits>`
- **Route away (defer / to human / to another substrate) when:** `<the failure
  classes from envelope §4 — un-buildable geometry, un-extractable QoI,
  out-of-envelope regime>`
- **Tie-break vs a peer substrate:** `<cost tier, then confidence>`
