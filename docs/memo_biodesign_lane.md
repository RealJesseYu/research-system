# Memo — the bio-design lane, and a defer whose reason was wrong

**Written:** 2026-07-27. **Status:** built, live-proven, suite green.
**Rulings:** R-BIO-1 (truth-edit without promotion). Route decision inherits
R-LANE-1 (`docs/memo_atomistic_lane.md`). No locked schema changed; the sandbox
jail is untouched.

---

## 1. The claim that was wrong

`tools/run_proteinmpnn.py` and its registry row have said since 2026-07-18:

> DEFERRED — ProteinMPNN is a GPU neural model with downloaded weights; no GPU
> here.

Two premises, and they do not share a fate.

**The GPU premise is false.** ProteinMPNN is roughly 1.7M parameters — small
enough that CPU inference is unremarkable. Anthropic's Claude Science ships a
runbook per biomodel, and every one declares `requirements: [gpu]` **except**
ProteinMPNN, LigandMPNN and SolubleMPNN. That was the tell; the measurement
settled it.

**The weights premise is true**, and it matters more than it looks: the
verification sandbox runs `--network=none`, so a tool that downloads weights at
runtime cannot run there at all. Any fix had to provision them ahead of time.

A capability sat on the shelf for nine days because half a sentence was wrong
and nobody re-tested it. Worth noticing as a pattern: a defer records a judgment
made on one day's evidence, and nothing re-examines it unless someone does so
deliberately.

## 2. The route (inherits R-LANE-1)

ProteinMPNN is **deterministic under a fixed seed** — proven below, bit-identical
across repeats — so re-running IS the reproduction check and the full
envelope-card-plus-calibration ceremony would buy nothing it does not already
have. It takes the **sandbox-shelf route**: an image, two profile rows, no
registry ceremony.

What re-running does *not* establish is whether a designed sequence folds or
functions. That is a FILTER-class interpretation limit, it was already stated on
the card, and it is untouched by anything here. Reproducibility was never the
open question for this tool.

## 3. What was built

`tools/biodesign_env/` → `biodesign-img`, plus `biodesign` / `biodesign-heavy`
profile rows (same shelf × geometry factorization as the atomistic lane).

**Provisioning, which is the part that had to be right:**

- Upstream **pinned to commit `8907e6671bfbfc92303b5f79c4b5e6ce47cdef57`**. The
  weights ship inside the repo, so one pin fixes both code and parameters.
- The build writes a **sha256 manifest of every `.pt`** to
  `/opt/proteinmpnn/WEIGHTS.sha256` and fails if the set is empty, so a run can
  state exactly which parameters produced its numbers. The row's own un-defer
  clause names the failure this guards — *"mismatched weights = confident
  garbage."* Recorded at build:

  | weights | sha256 (first 16) |
  |---|---|
  | `vanilla_model_weights/v_48_020.pt` | baked into the image manifest |
  | `ca_model_weights/v_48_020.pt` | `f28f40170e21858c…` |
  | `soluble_model_weights/v_48_020.pt` | `7af52d090172c230…` |

- **CPU torch explicitly** (`--index-url .../whl/cpu`). The default index would
  pull a CUDA build that cannot load here, and a silent fallback is how a "GPU
  required" myth starts in the first place.
- Build-time smoke asserts torch imports, the runner exists, and the default
  weights are present — so a moved upstream path fails the build, not the first
  experiment.

## 4. Live proof (2026-07-27)

Known-answer validation, exactly what the un-defer clause asks for: ubiquitin
(1UBQ, 76 residues), backbone-only, native sequence known.

| Check | Result |
|---|---|
| 4 designs, T=0.1, seed 37 | mean native-sequence recovery **0.5526**, best **0.5658** |
| In the expected band for ubiquitin? | yes — 40–60% is ordinary for ProteinMPNN |
| Repeat at the same seed | **bit-identical** (0.5526249999999999 both runs) |
| Wall clock, CPU | **~2.9 s** |
| Through the verification wall | a self-contained artifact (backbone inline) reproduced at `rel_error 0.0`; the same claim asserted at 0.95 → `mismatch` |

The fixture is `tests/fixtures/1ubq_backbone.pdb` (304 ATOM records, N/CA/C/O
only). A design result is now a kept number by the same mechanism as any other
code artifact.

## 5. R-BIO-1 — correcting a defer must not promote it

The registry row's note is **truth-edited** to record that the GPU premise was
wrong, that the weights premise is now satisfied, and where the capability
actually lives. Everything trust-bearing is **deliberately unchanged**:
`routable=False`, maturity untouched, adapter / QoI translation / run-entry
constructor / contract all still unwired, `contract_for('proteinmpnn')` still
raises.

The distinction is the point. A note says what we believe; `routable` says what
the system may do unattended. Discovering that a stated reason was false
corrects the first and earns nothing toward the second — and under R-LANE-1 this
tool would not take the routable path anyway. `tests/test_biodesign_lane.py`
asserts the row stayed unrouted and its maps unwired, so a later edit cannot
quietly convert a correction into a promotion.

## 6. What is next

- The **engineering shelf** — CadQuery, CoolProp, MuJoCo, scikit-rf — closing
  the mechanical and electrical gaps, which this session has not touched.
- **Remote compute (Route C)**, the largest single unlock: one build clears
  every GPU-blocked tool at once (Boltz-2, ESMFold, OpenFold3, Chai-1, AutoDock
  Vina, Evo2, Borzoi, scGPT, solid-state DFT) instead of one per session.
- **LigandMPNN and SolubleMPNN** are the same family and the same route; they
  are a small addition to this image whenever a run wants them.
- **Re-examine the other defers the way this one was re-examined.** The
  remaining five each name a specific blocker. At least one more may be as stale
  as this one was.
