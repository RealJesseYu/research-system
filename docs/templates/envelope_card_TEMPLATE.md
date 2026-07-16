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

**R-CARD-1 (STRUCTURAL — every ruling states whether the gate can check it).**
Adopted 2026-07-16 (see `docs/r_card_1_audit.md`). Each §3B ruling MUST carry,
inline, all three columns below — a ruling with an empty **Class** or **Criterion**
does not sign. The point: a ruling the gate cannot evaluate is not enforcement,
it is a hope, and it must be *marked a known gap*, not left to read as a rule.

| Ruling | Ruled value | **Class** | **Criterion (what the gate evaluates, and where it reads it)** |
|---|---|---|---|
| `<Fn/Cn>` | `<the bound>` | `<CHECKABLE:numeric \| CHECKABLE:membership \| CHECKABLE:semantic \| JUDGMENT>` | `<the exact threshold/list/named condition + the source it reads: spec field / success-criterion text / wrapper structural fact — OR, if JUDGMENT, "KNOWN GAP: <what is missing and why it cannot yet be made checkable>">` |

- **CHECKABLE:numeric** — a stated threshold on a spec-derivable number (e.g. `L/h ≥ 10`).
- **CHECKABLE:membership** — a set/allowlist/QoI-name test (e.g. `QoI == max_von_mises`).
- **CHECKABLE:semantic** — a named claim-category read from the criterion text
  (e.g. "criterion asserts deployment utility?") — checkable because the thing to
  check lives in the text under judgment.
- **JUDGMENT** — no stated criterion, or an assessment of something the gate
  cannot observe (e.g. dataset honesty). **Mark it a KNOWN GAP.** A JUDGMENT
  ruling may still transmit (worked example: FEA-4D nu-locking landed with no ν
  threshold) — but it is steerable by the text under judgment (worked example:
  code-C1 leakage, the C13 steerability probe), so it may never be signed as if
  it were enforcement.

---

## 4. Known failure modes
For each: name it, the class it produces (defer / refine / out_of_envelope /
setup_error), **its detection class per R-CARD-1** (CHECKABLE:{numeric,membership,
semantic} or JUDGMENT/KNOWN-GAP — how the gate would actually catch it), and its
evidence.
- **4A. Un-buildable geometry / boundary conditions** → builder halt (defer). `<class; ...>`
- **4B. Un-extractable QoI** → defer. `<class; ...>`
- **4C. Under-resolution near threshold** → converged-but-wrong (refine). `<class; ...>`
- **4D. Out-of-envelope use** → `<class; ...>`
- **4E. Mis-simulated physics the diagnostics can't catch** → `<class; ...>`
- **4F. Labeling convention** → `<class; ...>`
- **4G. QoI contaminated by a numerical artifact** (add per measured instance) → `<class; ...>`

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
