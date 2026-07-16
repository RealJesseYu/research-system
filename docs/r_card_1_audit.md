# R-CARD-1 — Card Audit: CHECKABLE vs JUDGMENT (both signed cards)

**Date:** 2026-07-16 · **Session:** step21 (dry) · **Adopted ruling:** R-CARD-1.
**Cards audited:** `docs/envelope_card_calculix_cantilever.md` (FEA),
`docs/envelope_card_code_sklearn_eval.md` (code). **Measurement:** the two
calibration batteries run 2026-07-16T0130Z
(`harness/calibration_calculix_cantilever_fea_20260716T013008Z.json`,
`harness/calibration_code_sklearn_eval_20260716T013014Z.json`).

**Classification key (derived, not taken):**
- **CHECKABLE** — a threshold, list membership, or named spec condition the gate
  can evaluate *from what it actually sees* (the spec fields + the success-
  criterion text + the wrapper's structural facts). Sub-kinds:
  - *numeric* — a stated threshold on a spec-derivable number (e.g. `L/h ≥ 10`).
  - *membership* — a set/allowlist/QoI-name test (e.g. `QoI == max_von_mises`).
  - *semantic* — a named category evaluated from the criterion text (e.g. "does
    the success criterion assert deployment utility?"). Evaluable because the
    thing to check **lives in the text under judgment**.
- **JUDGMENT** — requires an assessment with **no stated criterion**, OR an
  assessment of something the gate **cannot observe** from what it sees.

---

## FEA card — `calculix_cantilever`

### §3B envelope-bound rulings

> **CORRECTION #1 (count).** The prompt says "FEA F1-F5." The card's §3B has
> **only F1–F4** — there is no F5. Audited as F1–F4.

| Ruling | Criterion on the card | Class | Where the gate reads it | Battery evidence |
|---|---|---|---|---|
| **F1** slenderness `L/h ≥ 10` | explicit numeric bound | **CHECKABLE (numeric)** | spec `length/height` | C06/C07 (`L/h=2`) → defer; C04 (`L/h=10`, the boundary) → trust; C01–C05 → trust. **Landed.** |
| **F2** linearity `δ_tip/L ≤ 0.10` | explicit numeric bound | **CHECKABLE (numeric)** | computable from spec (`δ = PL³/3EI`) or disclosed in text | C08 (`δ/L≈15%`) → defer. **Landed.** |
| **F3** mesh reproduces analytic δ within **2.0%** | explicit numeric bound | **CHECKABLE (numeric)** | a new mesh's result vs analytic | **UNEXERCISED** — no gate case tests mesh reproduction (it is an onboarding/wrapper property, not a spec the fidelity gate judges). |
| **F4** `max_von_mises` is **reported-only (not validated)** | QoI-name condition | **CHECKABLE (membership)** | requested QoI name | C15 (geometry in-envelope, QoI `max_von_mises`) → defer. **Landed — the cleanest checkable win: a pure QoI-name rule caught a geometry-fine case.** |

> **CORRECTION #2 (F3 omitted).** The owner's evidence list ("F1/F2/F4 … landed")
> silently drops **F3**. F3 *is* checkable; it simply was **not exercised** by the
> battery. Name it as checkable-but-unexercised rather than leaving it unlisted.

### §4 failure modes (4A–4E — five, not four)

| Mode | Detection basis | Class | Battery evidence |
|---|---|---|---|
| **4A** nonphysical input → setup_error | validator: positive fields, `ν∈(−1,0.5)`, `mesh_density≥1` | **CHECKABLE (membership/threshold)** | wrapper cases C10–C14 all rejected with the pre-registered reason. |
| **4B** out-of-slenderness → EB invalid | = F1 applied (`L/h<10`) | **CHECKABLE (numeric)** | C06/C07 → defer. |
| **4C** large-deflection → linear broken | = F2 applied (`δ/L>0.10`) | **CHECKABLE (numeric)** | C08 → defer. |
| **4D** near-incompressible `ν` → volumetric locking | card says "`ν → 0.5`" — **NO numeric cutoff stated** | **JUDGMENT — KNOWN GAP** | C09 (`ν=0.4999`) → defer. It transmitted, but via the gate's physics **judgment**, not a checkable threshold. |
| **4E** `max_von_mises` singularity → converged-but-misleading | for the named QoI: = F4 (membership); *in general*: "every extremum QoI screened for singularity" | **CHECKABLE (membership) for the named QoI; JUDGMENT for the general screen** | C15 → defer (caught by the F4 name rule). |

> **CORRECTION #3 (nu-locking is NOT checkable).** The owner's evidence sentence
> lists "nu-locking … landed" among the **CHECKABLE** rulings that transmitted.
> Derived: 4D is **JUDGMENT** — the card names the mode but states **no ν
> threshold** (0.4999 defers, 0.33 trusts, with no stated cutoff between them). It
> *did* land (C09 deferred), which proves a **judgment-class ruling can still
> transmit** — an important corrective to the framing that "the ruling that
> failed is judgment, therefore judgment rulings fail." They do not uniformly.

---

## Code card — `code_sklearn_eval`

### §3B envelope-bound rulings

> **CORRECTION #4 (count).** The prompt says "code C1-C5." The card's §3B has
> **only C1–C4** — there is no C5. Audited as C1–C4.

| Ruling | Criterion on the card | Class | Where the gate reads it | Battery evidence |
|---|---|---|---|---|
| **C1** dataset provenance: builtin trusted; **user CSV flagged "only as honest as the CSV"** | a **principle**, no stated verdict floor | **JUDGMENT** | the *trigger* (builtin vs `dataset.path`) is checkable; the *consequence* (is the CSV honest? what verdict does the flag compel?) is not — CSV honesty is **not observable** and the card names **no minimum verdict** for a user CSV | **THE ONE THAT FAILED.** C03 (user CSV, no leak) → **refine** (caution applied); **C13 (user CSV, DISCLOSED leak) → trust** (caution NOT applied). The C03-vs-C13 inconsistency is the proof it is judgment, not a mechanical rule. |
| **C2** flag `n_test < 30` as too noisy to headline | explicit numeric bound | **CHECKABLE (numeric)** | reported `n_test` | supporting factor in C07's defer rationale ("'tiny' split likely below n_test≥30"). |
| **C3** allowlist-drift: new family → amendment + determinism re-proof | allowlist membership | **CHECKABLE (membership)** | spec `model/metric/dataset` vs allowlist | wrapper case C10 (`xgboost`) rejected. |
| **C4** deployment-claim rule: criterion references real-world/production/clinical/deployment utility → trust number **AND** defer utility | a **named category** of claim | **CHECKABLE (semantic)** | the success-criterion **text** | C05 (diagnostic), C06 (deploy), C07 (production) → **all defer, 3/3.** **Landed.** |

### §4 failure modes (4A–4D)

| Mode | Detection basis | Class | Battery evidence |
|---|---|---|---|
| **4A** benchmark–deployment conflation → split | = C4 (claim in criterion text) | **CHECKABLE (semantic)** | C05–C07 → defer. |
| **4B** leakage the wrapper can't see → defer/flag | leakage is **not observable**; even when disclosed in text the gate must **judge** whether to act | **JUDGMENT** | C14 (dupes, disclosed) → **defer** (correct); **C13 (leak, disclosed) → trust** (wrong). Inconsistent — confirms judgment. **The failure lives here.** |
| **4C** metric–task mismatch → refine/flag | stated metric vs stated task/goal (both in text) | **CHECKABLE (semantic)** | C08 (imbalanced + accuracy), C09 (ranking goal + accuracy) → defer. |
| **4D** single-thread determinism guard | mechanical config (`n_jobs=1`, thread env) | **CHECKABLE (structural), unexercised by gate cases** | wrapper/determinism property; twice-run identity in §3A. |

---

## The structural finding (why C13 failed, derived)

The owner's classification of **C1 as JUDGMENT is correct**, but the sharper
statement is:

- **C4 (deployment-claim) is CHECKABLE because the thing to check — the
  overreaching claim — lives in the success-criterion text the gate reads.** It
  transmitted 3/3.
- **C1/4B (leakage) is JUDGMENT because dataset honesty lives in the CSV rows the
  gate never sees.** When the leak was DISCLOSED in C13's text, it became
  text-visible — yet the gate still trusted, steered by the narrow-triple
  framing ("trust the reported accuracy as a benchmark … even though y_copy
  inflates it"). So the failure is not "the flaw was invisible"; it is **"a
  judgment-class ruling, with the flaw visible in text, was steered by the
  wording of the criterion."** That is exactly the hypothesis the C13
  steerability probe tests — and it is why the probe matters: if the criterion
  text can flip a leakage verdict, an upstream LLM stage can instruct the gate.

**Net corrections to the prompt:** (1) FEA has F1–F4, not F1–F5; (2) code has
C1–C4, not C1–C5; (3) F3 is checkable-but-unexercised, not absent; (4) FEA-4D
(nu-locking) is JUDGMENT, not a checkable ruling that "landed" — it transmitted
*via judgment*, which shows judgment rulings can transmit. Agreement: C1 is
JUDGMENT and is where the C13 failure originates (as its §4B expression).

## Consequence for the template (R-CARD-1 made structural)

`docs/templates/envelope_card_TEMPLATE.md` §3B and §4 now REQUIRE every ruling to
carry, inline: its **class** (CHECKABLE numeric/membership/semantic, or
JUDGMENT), its **criterion** (the exact threshold/list/named condition and where
the gate reads it), and — if JUDGMENT — an explicit **KNOWN GAP** marker naming
what is missing. FEA-4D is the worked example of a ruling that must now be marked
a known gap (a ν-locking mode with no ν threshold). Wave 2's twelve substrates
inherit this structure so no ruling can be signed without stating whether the
gate can actually evaluate it.
