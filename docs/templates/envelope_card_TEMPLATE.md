# Envelope Card — (SUBSTRATE, PHYSICS-REGIME)  ·  TEMPLATE

> **STATUS: DRAFT — not yet reviewed.**
> Provenance: `drafted-by-agent` (see §2 — advance the state as review proceeds).

> **How to use this template.** Fill every `<...>` and every `[CITATION NEEDED]`.
> Nothing enters §3A without an on-disk citation. An unresolved `[CITATION
> NEEDED]` or `TODO-HUMAN` in a load-bearing section (§3, §5, §6) blocks
> sign-off (see `docs/reviewer_rubric.md`). Card unit = the (substrate,
> physics-regime) pair — one card per regime.

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, physics-regime) pair |
| Substrate | `<substrate id>` |
| Physics regime | `<the exact regime this card validates — not the solver's full reach>` |
| Solver | `<solver + version, container>` |
| Wrapper | `<tools/…>` (deterministic, no AI) |
| Wrapper commit (last touch) | `<sha>` |
| Contract text (last touch) | `<substrates.py contract, sha>` |
| Card drafted against repo HEAD | `<sha>` |

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | `<agent / human>` |
| Drafted date | `<YYYY-MM-DD>` |
| Sources | `<run evidence / contract in code / V&V literature — mark literature as such>` |
| Signature | `<unsigned | provisionally-signed / owner / date>` |
| Reviewer sign-off | `<pending | signed / reviewer / date>` |
| **Provenance state** | `<drafted-by-agent | provisionally-signed / awaiting-external-review | expert-reviewed / signed>` |

*Provenance state is the load-bearing field: it sets how much grounding
authority the card carries (see §7 / reviewer rubric).*

---

## 3. Validated envelope

Two sections, deliberately separate. **Nothing enters Table 3A without an
on-disk citation.**

### 3A. Ranges actually exercised (disk-cited)
| Parameter | Range exercised | Evidence (run id / artifact) |
|---|---|---|
| `<param>` | `<range>` | `<run id>` |

### 3B. Believed-but-not-exercised region (ruled, not run)
`<the region trusted on physics grounds but never exercised; each entry ruled,
not asserted>`

---

## 4. Known failure modes
For each: name it, the class it produces (defer / refine / out_of_envelope /
setup_error), and its evidence.
- **4A. Un-buildable geometry / boundary conditions** → builder halt (defer). `<...>`
- **4B. Un-extractable QoI** → defer. `<...>`
- **4C. Under-resolution near threshold** → converged-but-wrong (refine). `<...>`
- **4D. Out-of-envelope use** → `<...>`
- **4E. Mis-simulated physics the diagnostics can't catch** → `<...>`
- **4F. Labeling convention** → `<...>`
- **4G. QoI contaminated by a numerical artifact** (add per measured instance) → `<...>`

---

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| `<non-convergence, blow-up, stability-number ≫ 1>` | `<converged-but-wrong, mesh/discretization independence, regime-assumption certainty>` |

*Overclaiming diagnostic reach is the most dangerous error a card can make.*

---

## 6. Extraction contract (verbatim)

**Canonical parameter vocabulary** (`substrates.py`) — the builder honors
exactly these; anything else halts loudly, by name:

| Name | Units | Meaning |
|---|---|---|
| `<param>` | `<units>` | `<meaning>` |

**QoI extraction path** — verbatim capability:
- `<one QoI per run? which operations? which fields? single-shot / latest-time?>`
- On success: `<qoi {…} shape>`. On ANY failure: `<qoi_error, no number>`.
- `<what field classes YES / what NO>`.

**QoI screening rule (REQUIRED slot):** state the screen every candidate QoI
must pass at design vet beyond mere contract fit — e.g. *every extremum QoI is
screened for numerical-artifact / boundary-singularity contamination.* Cite the
measured instance that motivates it (see §4G). `<fill from a real run or mark
[CITATION NEEDED]>`

---

## 7. Cost model (measured rates)
| Regime | Measured rate | Evidence |
|---|---|---|
| `<operating point>` | `<solver time / wall-clock>` | `<run id>` |
| Hard kill limit | `<timeout>` | `<wrapper const>` |

*Per-unit rate published as a RANGE, not a constant, unless proven constant.*

---

## 8. Resolved questions / open watches
`<each START-of-onboarding open question with its ruling, or an explicit watch>`
