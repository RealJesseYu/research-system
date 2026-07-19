# Envelope Card — (mafft, msa_alignment)

> **STATUS: DRAFT — signed-from-real-runs, external review pending.** §3A numbers
> MEASURED in `mafft-prod` (MAFFT v7.526). HUMAN-FACING ONLY (R-20.5-1). ENROLLED
> `calibrating`/`routable=False` — inert (`contract_for("mafft")` raises).

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, regime) pair |
| Substrate | `mafft` (**ENROLLED**, `calibrating`/`routable=False`) |
| Regime | **msa_alignment**: a multiple sequence alignment — arranging >= 2 same-alphabet sequences into columns of putative homology. |
| Tool | **MAFFT v7.526** (bioconda; `mafft --auto --anysymbol`), in `mafft-prod` (from `mafft-img`, the reusable bioconda base). No network. **PINNED.** |
| Wrapper | `tools/run_mafft.py` (deterministic Python, no AI) |
| Class | **filter/answer** — the alignment IS the tool's computed output, but with the NARROWEST trust claim in the wave (see §3B) |
| Contract text (staged) | `onboarding/mafft/contract.py` — moves to `substrates.py` at D.4 |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | real `mafft-prod` runs: a 3-sequence protein alignment, the strict-input-gate refusals, and a determinism repeat. |
| Signature | `unsigned` |
| Provenance state | `drafted-by-agent` |

## 3. Validated envelope

### 3A. Cases actually exercised (disk-cited, MEASURED)
| Case | Input | Result | alignment_identity (QoI) |
|---|---|---|---|
| real MSA | 3 similar 24-aa sequences | aligned, length 24 | **94.4444** (avg pairwise %id) |
| divergent MSA | 3 seqs needing a gap | aligned, length 22 | 100.0 over non-gap columns |
| **INPUT-GATE JAIL** | 1 sequence | **refused BEFORE running** | None, valid=False |
| **INPUT-GATE JAIL** | junk residues `12345!@#` | **refused BEFORE running** | None, valid=False |
| **INPUT-GATE JAIL** | mixed protein+nucleotide | **refused BEFORE running** | None, valid=False |

The real MSA reproduces **alignment_identity 94.4444**; determinism verified
(identical repeat → identical value; MAFFT's default is deterministic). **The
input-gate jails refuse un-alignable input BEFORE MAFFT runs — never after
inspecting a well-formed-but-meaningless alignment.**

### 3B. Ruled envelope bounds (R-CARD-2 — Class / Criterion / Consequence both sides)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **M1 — THE STRICT INPUT GATE (did-it-work)** | Input must be alignable BEFORE running | `CHECKABLE:membership` (pre-run, in code) | >= 2 sequences, each non-empty and valid, ALL over one alphabet (all protein OR all nucleotide) | alignable → **eligible**; not alignable → **setup_error** (refused up front — a well-formed alignment of un-alignable input is never trusted). *Necessary because alignment is near-total: "MAFFT produced an alignment" is NOT sufficient.* |
| **M2** | Alignment well-formed | `CHECKABLE:numeric` (post-run) | the output has one row per input, equal lengths | well-formed → the metric is computed; malformed → **setup_error** |
| **M3** | Quantity on the allowlist | `CHECKABLE:membership` | `quantity ∈ {alignment_identity}` | on list → eligible; else → **setup_error** |
| **M4 (C1-hole) — THE WHOLE SCIENTIFIC QUESTION** | Well-formed ≠ correct | **JUDGMENT / KNOWN GAP** | **none the gate can read** — a computed alignment is a HEURISTIC homology hypothesis, guide-tree-dependent; a different tool/setting gives a different alignment | trust side = "an alignment MAFFT COMPUTED, well-formed, used **DESCRIPTIVELY**"; any claim that it is **the correct / biologically-true** alignment → **defer**. For an MSA tool the gap between well-formed and correct is the entire scientific question — the trust side must not overclaim. |

## 4. Known failure modes
- **4A. A well-formed alignment of un-alignable input → prevented at the INPUT (structural, M1).** MAFFT is near-total: garbage in → a plausible alignment of garbage out, with NO error. The only defense is the strict pre-run input gate; proven by triggering (single-sequence, junk residues, mixed alphabet all refused before running).
- **4B. A well-formed alignment read as THE correct alignment → defer (M4, the C1-hole).** Invisible to every diagnostic — the alignment is perfectly well-formed; its biological correctness is a heuristic hypothesis, not a fact.
- **4C. Malformed output (unequal rows) → setup_error (M2).**
- **4D. Container down / timeout → transient.** One retry, then honest failure.

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Whether the input is alignable (M1) — the load-bearing pre-run gate | Whether the alignment is the biologically CORRECT one (M4) |
| Whether the output is well-formed, and the avg pairwise %id (M2) | Whether a different guide tree / tool would align it differently |
| Input validity: >=2 seqs, one alphabet (M1) | Any homology claim beyond "these columns were aligned by this heuristic" |

*The wrapper checks that the input was alignable and MAFFT produced a well-formed
alignment — NOT that the alignment is correct.*

## 6. Extraction contract + QoI status
Typed input `{sequences, quantity}`; `sequences` is a list of >= 2 same-alphabet
sequences. QoI = `alignment_identity` — the average pairwise percent identity
over the computed alignment (non-gap columns), in [0, 100], DESCRIPTIVE only.
`QOI_FIELDS` is the single source, imported at promotion. Honest limitation: the
alphabet is inferred heuristically (a short pure-ACGTU peptide is called
nucleotide) — ambiguous only for degenerate short inputs.

## 7. Cost model (measured)
| Operating point | Measured wall-clock |
|---|---|
| `mafft --auto` on 3 short sequences | **~0.9 s/run** |
| Hard kill limit | 600 s → reported failure |
*Cost is container-exec overhead on small inputs; real MSA cost scales with
sequence count and length.*

## 8. Negative space + open watches
Out of scope: alignment CORRECTNESS / phylogenetic inference (M4 — the whole
gap); alignment scoring beyond avg pairwise identity (SP-score, TC-score are
later additions); very large alignments (the exercised envelope is small);
non-standard alphabets. **Open watches:** (1) External reviewer — pending. (2)
Registration deferred — `contract_for("mafft")` must keep raising until a D.4
ruling. (3) The heuristic alphabet inference (§6) for degenerate short inputs. (4)
Calibration battery assembled-later, on the owner's manifest.
