# repo_facts.md — what the code actually does, with citations
**Produced by the RECON CHAT, 2026-07-17. Doc-only session: zero pipeline runs, zero live model calls (precedent: `docs/step25_failure_bins.md:1-4`).**
**Read at sha: `be1b1ff`; REFRESHED AND RE-STAMPED at the Packet B Phase 2 close (build session, 2026-07-18) against the flip commit `a07f939`** — §§1-3, the §6 router/NUMBER chapters, §8, and §§10.5-10.6 are rewritten from that session's measured state (every new claim read fresh at `a07f939`); chapters NOT re-verified this pass are listed at the end of §11. (Original recon provenance: owner-supplied `be1b1ff`, 2026-07-17; the `07816ba` and `d6c52fa` diffs were supplied as text files and are cited as `diff:` below.)
**RE-STAMPED AGAIN at the BIO Wave D.1 close (build session, 2026-07-18) against `6befb63` — THE ERA-OF-RECORD ADVANCES `a07f939` -> `6befb63` (owner-ruled).** D.1 invalidated exactly three areas, refreshed here: the stage-5 contract handoff (§7 — stage 5 now sees the routed substrate's contract for every non-anchor substrate, D.1a `664b5c2`), Step-41 hierarchical selection (§6 SUPERSEDED block — L0/L1a/L1b/L2, D.1b `a60e2f4`), and the `SubstrateRecord` field list (§2 — new declared `frozen_anchor` property, D.1a). **Routable set UNCHANGED through D.1: still five, still zero mature** (nothing promoted; promotion is D.4). Cavity's model-visible bytes did NOT move — only these citations. Design memo for Step 41: `docs/memo_step41_routing.md`.
**BIO Wave D.2 COMPLETE + D.3 MID-FLIGHT (2026-07-19, HEAD `6add06a`): NOT re-stamped here (ruled).** D.2 enrolled 12 bio substrate rows INERT (Option A) — registry now 19 enrolled, but **routable UNCHANGED at 5 / 0 mature** (nothing promoted; D.2 enrolls, D.4 promotes). D.3 calibration batteries (the 4 runnable tools: rdkit, cobrapy, homology_search, mafft) do NOT change enrollment or routability. The §8-standing re-stamp happens ONCE, after D.4, when routable actually changes. §2's "seven rows / five routable" enrollment prose is now stale-by-count (19 enrolled) but the ROUTABLE facts (5 / 0 mature) it gates on are current — full §2 refresh folds into the post-D.4 re-stamp.

**RE-STAMPED AT THE BIO Wave D.4 PROMOTION (build session, 2026-07-19) against the flip commit `5bc037c` — THE ERA-OF-RECORD ADVANCES `6befb63` -> `5bc037c` (owner-ruled).** THIS IS the once-after-D.4 re-stamp the D.2/D.3 notes deferred: **routable 5 -> 8, mature 0 -> 3**. rdkit + cobrapy + mafft flipped `routable=True` AND `maturity=MATURE` together (the FIRST mature substrates) on the calibration evidence — rdkit/mafft clean at N=3, cobrapy on the N=7 wash-out (in-envelope 34 trust / 1 refine, out 35/35 defer). `homology_search` is HELD (a G03/G05 card fix + re-run, no promotion). §2 refreshed below (routable eight-id tuple, three mature, enrollment 19). §8 refreshed (era + the two growing fixtures re-captured additive-only: `feasibility_nudge.txt` now eight contract blocks, `chooser_retry_user_turn_v235.txt` now the eight-id list; pre-D.4 originals preserved append-only as `*_pred4`). Cavity's model-visible bytes did NOT move (`tests/test_d0_stage5_input.py` unchanged — the frozen anchor held). Full suite 89/89 files green; FAST GREEN. Areas NOT re-verified this pass keep their prior status (§11).
**Rule of this doc: no claim without a `file:line`. Anything uncitable is listed under Open Questions instead.**

---

## 1. Where contracts live (D.1 Q1)

- The **contract text** (the model-visible five-section description of an instrument) is authored as a module constant in `substrates.py` — FIVE contracts since the Packet B flips: `CAVITY_2D_CONTRACT` (:16), `NGSPICE_LINEAR_PASSIVE_CONTRACT` (:169), `SYMPY_SYMBOLIC_EXACT_CONTRACT` (:356, authored at the Phase 1 graduation), `CALCULIX_CANTILEVER_FEA_CONTRACT` (:538, authored from zero at the Phase 2 graduation), and `FENICSX_CANTILEVER_ELASTIC_CONTRACT` (:760, COMPOSED from the onboarding module's own path-loaded section constants so the battery-facing text keeps one source).
- The **runtime lookup** lives in the registry, not in `substrates.py`: `tools/substrate_registry.py:160-162` defines `_CONTRACTS: dict[str, str]`, currently one entry, `"cavity_2d_cfd": CAVITY_2D_CONTRACT` — the value **is** the imported constant, never a pasted copy (`tools/substrate_registry.py:39,153-155`; proven by `tests/test_contract_registry.py:32-37`, which asserts `assertIs`, i.e. same object).
- `contract_for(substrate_id)` (`tools/substrate_registry.py:165-194`): first calls `get(substrate_id)` — **raises `KeyError`** on an id not in `_REGISTRY` (`:184`, `:223-226`); then looks up `_CONTRACTS` — **raises `LookupError`** on an enrolled substrate with no wired contract (`:187-194`), with an error message that explicitly forbids falling back to cavity. Both raise conditions are proven by failing the escape in `tests/test_contract_registry.py:82-113` (FEA, code, web_search each raise; `test_never_falls_back_to_cavity_for_a_contractless_substrate` at `:99`).
- Why contracts should **not** be "moved into `substrates.py`" as a routing mechanism: `substrates.py` is text-only (its own header: "Nothing imports this file yet" at `substrates.py:12` is **stale** — see §9); the selection seam was deliberately placed in the registry by R-S3-1 (`tools/substrate_registry.py:149-159`, commit `07816ba`, diff:`stages/stage3_fidelity_gate.py`).

## 2. The registry (D.1 Q2)

- `_REGISTRY` is a frozen tuple of `SubstrateRecord` dataclasses: `tools/substrate_registry.py:72-144`. `SubstrateRecord` fields: `substrate_id, wrapper, card_path, maturity, routable, cost_tier, notes`, plus the declared **`frozen_anchor: bool = False`** (D.1a, owner-ruled 2026-07-18) — a reproducibility-anchor role, `True` for cavity alone, read by `registry.is_frozen_anchor()` to opt the anchor OUT of surfaces that would grow its byte-frozen model input (§7), by DATA not a name branch (`frozen=True`, mutation-refusal proven at `tests/test_substrate_registry.py`).
- Nineteen rows, in enrollment order. The pre-BIO seven: `cavity_2d_cfd` (provisional, ROUTABLE), `calculix_cantilever_fea` (calibrating, ROUTABLE since the Packet B Phase 2 flip `a07f939`), `code_sklearn_eval` (calibrating, unroutable), `fenicsx_cantilever_elastic` (calibrating, ROUTABLE since `a07f939`), `sympy_symbolic_exact` (calibrating, ROUTABLE since the Phase 1 flip `167fdaa`), `ngspice_linear_passive` (calibrating, ROUTABLE since the R2 flip), then the twelve BIO rows (D.2 Option A), then `web_search` (retrieval-provisional, unroutable) stays LAST. Of the twelve BIO rows: `rdkit` / `cobrapy` / `mafft` are **MATURE + ROUTABLE since the D.4 promotion `5bc037c`**; `homology_search` is HELD (calibrating/unroutable, a D.4 G03/G05 card fix); the other eight (`cas_offinder`, `autodock_vina`, `crispr_guide_scoring`, `boltz2`, `proteinmpnn`, `retrosynthesis`, `alphafold_db`, `bio_db_lookup`) stay DEFERRED (calibrating/unroutable, each with its own recorded un-defer requirement).
- `all_substrates()` returns `_REGISTRY` in enrollment order. `routable_ids()` returns the ids with `routable=True` — since the BIO Wave D.4 promotion (`5bc037c`) exactly the EIGHT-id tuple `('cavity_2d_cfd', 'calculix_cantilever_fea', 'fenicsx_cantilever_elastic', 'sympy_symbolic_exact', 'ngspice_linear_passive', 'rdkit', 'cobrapy', 'mafft')` — the Packet-B five plus the three D.4 promotions in enrollment order.
- **Enrollment is now NINETEEN rows** (seven pre-BIO + twelve bio, D.2 Option A). **Routable = 8; mature = 3** (rdkit/cobrapy/mafft, the FIRST mature substrates — D.4). The other eleven bio rows stay `calibrating`/`routable=False` (eight DEFERRED, plus `homology_search` HELD by the D.4 card fix, plus code/web_search's own classes among the pre-BIO seven).
- **Enrollment order IS asserted by a test:** `tests/test_substrate_registry.py` asserts the exact nineteen-id enrollment list, the eight-id routable tuple, and that exactly rdkit/cobrapy/mafft are mature.
- Rows change **only by editing this file under a recorded ruling** — never at runtime, never from a prompt (`tools/substrate_registry.py:24-28`; comment-presence proven by `tests/test_substrate_registry.py:76`).

## 3. ⭐ The two "enrollments" (D.1 Q3 — Block E row 2)

Two distinct memberships, two distinct gates:

| Membership | Where | What it gates | Raise if absent |
|---|---|---|---|
| Row in `_REGISTRY` | `tools/substrate_registry.py:72-144` | Existence: `get()`/`maturity_of()`/hook visibility. A row does **not** make a substrate runnable — `routable` and `maturity` are separate fields on the row | `KeyError` from `get()` (`:223-226`) |
| Key in `_CONTRACTS` | `tools/substrate_registry.py:160-162` | The fidelity gate having a contract to judge against | `LookupError` from `contract_for()` (`:187-194`) |

Seven substrates are in `_REGISTRY`; FIVE are in `_CONTRACTS` (`:220-231` since `a07f939`) — the remaining unwired set is exactly {`code_sklearn_eval`, `web_search`}, whose absence stays the fail-loud escape (subject migrated to code_sklearn_eval at the Phase 2 flip; `tests/test_contract_registry.py` proves it plus the live-derived contractless sweep). `_REGISTRY` membership alone still does not authorize routing; since Packet B, wiring travels as a five-artifact set per flip — contract, signature (`tools/substrate_selection.py:100`), vocab record (`tools/qoi_vocab.py:263`), adapter + translation + entry constructor (`tools/substrate_dispatch.py:354/437/701`) — each imported from the substrate's own single sources under the flip's ruling.

## 4. The maturity hook (D.1 Q4)

`supervisor.apply_substrate_maturity_hook` (`supervisor.py:203-266`):
- **Reads:** `baton.payload["fidelity_verdict"]` (`:237`) and the registry's routable set structurally — `registry.routable_ids()` filtered by `registry.is_mature()` (`:243`). Never parses substrate names from the payload (`:209-211`).
- **Does:** nothing for non-dicts or `defer` verdicts (`:238-241`); nothing if all routable substrates are mature (`:244-245`). Otherwise stashes `baton._maturity_signoff` (non-payload attribute, `:248-253`), logs `NEEDS_HUMAN_SIGNOFF` (`:254-257`); in `auto` mode **downgrades the verdict label to `defer` in place** and logs `MATURITY_DOWNGRADE` (`:258-264`). In `human` mode the verdict is untouched (`:220-223`). Fires the moment the stage-3 verdict is validated, before stage 4 (`supervisor.py:1002-1008`). Signoff surfaces in every terminal run_record (`supervisor.py:151-156`) and gate display (`:509-516`). Proven: `tests/test_maturity_hook.py:50-155`.
- **Cannot catch:** anything that bypasses the supervisor loop — `harness/fidelity_case_runner.py` calls the frozen stage-3 prompt directly and by design never goes through `stage3_fidelity_gate.run()` or the supervisor (`harness/fidelity_case_runner.py:9-11`); and it gates on the **routable set**, not on what actually executes — stage 4 runs `run_cfd` unconditionally (`stages/stage4_simulation.py:166`), so if stage 4 were ever handed a spec for a different substrate the hook would neither know nor care (routing is not read from the spec anywhere: `supervisor.py:209-211`).

## 5. The sequence: wrapper on disk → pipeline runs it (D.1 Q5)

Gates in order, each marked **code** or **convention**:

1. **Envelope card authored** — convention only: cards are human-facing, "no code reads it, no model sees it" (R-20.5-1, e.g. `docs/envelope_card_calculix_cantilever.md:7`). Nothing in code checks a card exists beyond the `card_path` string in the row (`tools/substrate_registry.py:63`).
2. **Registry row added, at `calibrating`/`routable=False`** — code + ruling: editing `_REGISTRY` under a recorded ruling (`tools/substrate_registry.py:24-32`); order-locked by `tests/test_substrate_registry.py:24-37`.
3. **Calibration battery run, owner-OK'd** — convention/governance: every non-cavity row's `notes` field says battery pending owner OK (`tools/substrate_registry.py:92,101,110,119-124,133`). No code enforces battery-before-promotion.
4. **Contract wired into `_CONTRACTS`** — code: without it `contract_for` raises (`tools/substrate_registry.py:187-194`). Wiring is itself "under a recorded ruling" (`:191-194` error text).
5. **`routable=True` flip (promotion)** — code + ruling: only then does the id appear in `routable_ids()` (`:241-247`).
6. **Routable set must remain exactly one, or selection must be built** — code: `sole_routable_id()` **raises `RuntimeError`** if the routable set is not exactly one (`tools/substrate_registry.py:197-215`; proven `tests/test_contract_registry.py:39-49`). Stage 3 calls it at `stages/stage3_fidelity_gate.py:121`. So promoting a second substrate without building Step-35 selection breaks the pipeline **loudly at stage 3** — this is the named seam, not an accident.
7. **Maturity: unless `mature`, every trust/refine verdict is human-gated (human mode) or auto-downgraded to defer (auto mode)** — code: §4. No substrate is mature today (`tools/substrate_registry.py:17`, test `:64-65`).
8. **Stage 2 spec validation, Stage 4 build+execute** — code, but **CFD-pinned** (see §6): even after 1–7, a non-cavity spec cannot be validated against its own vocabulary (`stages/stage2_spec.py:22`) and cannot be built or executed (`stages/stage4_case_builder.py:49-69`, `stages/stage4_simulation.py:43,166`).

**Q6 — what `routable=False` actually prevents, with call sites:** exclusion from `routable_ids()` (`tools/substrate_registry.py:247`), whose only production consumers are (a) `stage3_fidelity_gate._selected_contract` via `sole_routable_id()` — `stages/stage3_fidelity_gate.py:121` — so an unroutable substrate is never the contract the gate judges against; and (b) the maturity hook's non-mature scan — `supervisor.py:243`. It does **not** prevent execution by construction elsewhere: stage 4 never consults the registry (no registry import in `stages/stage4_simulation.py`; its execution call is the hardcoded `run_cfd` at `:166`) — unroutable substrates are unreachable today because nothing *selects* them, not because stage 4 checks.

---

## 6. ⭐ D.2 — THE PIN AUDIT

### Q7: the four names imported at `stages/stage2_spec.py:22`

Vocabulary source of truth is the wrapper: `tools/run_cfd.py:61` (`QOI_OPERATIONS`), `:67` (`QOI_COMPONENTS`), `:70` (`_QOI_FIELD_RE`), `:305` (`MASK_TYPES`).

| Name | Consumed at | What breaks for a non-CFD spec |
|---|---|---|
| `MASK_TYPES` | `stages/stage2_spec.py:155-157` (multi-QoI mask type check) | any mask vocabulary other than `corner_exclusion/boundary_exclusion/box` (`tools/run_cfd.py:305`) is rejected as an error string |
| `_QOI_FIELD_RE` | `stages/stage2_spec.py:197` (QoI field-name check) | field names are forced to the CFD wrapper's identifier grammar (`tools/run_cfd.py:70`) |
| `QOI_OPERATIONS` | `stages/stage2_spec.py:203-205` | any operation outside the CFD reduction set is rejected — an FEA "max_von_mises"-style operation cannot validate |
| `QOI_COMPONENTS` | `stages/stage2_spec.py:208` | components outside `("mag",0,1,2)` (`tools/run_cfd.py:67`) rejected |

So Block E row 3 is confirmed: Stage 2 is CFD-pinned **at the import line** — there is no per-substrate schema fragment that could be "applied"; the vocabulary is structurally single-substrate.

### Q8: every pin in the upper layers (`stages/`, `supervisor.py`, `schemas.py`, `harness/`, plus `tools/experiment_picker.py`)

**Hard imports from `tools.run_cfd`:**

| # | Site | Kind | Depth |
|---|---|---|---|
| P1 | `stages/stage2_spec.py:22` | hard import (4 vocab names) | shallow — validator lookups only (Q7 table) |
| P2 | `stages/stage4_case_builder.py:49-56` (`CONTAINER, DOCKER_CONTEXT, OF_BASHRC, SHARED_CONTAINER, SHARED_HOST, TIMEOUT_SECONDS`) | hard import + **whole-file pin**: template dir `cavity_baseline` (`:58`), `BUILDABLE_PARAMS` = the six cavity names (`:62-69`), Reynolds decomposition rule (`:77-82`), blockMesh synthesis and failure parsing (`:266-298, 351-385`) | **deepest** — the module *is* an OpenFOAM case builder end to end |
| P3 | `stages/stage4_simulation.py:43` (`QOI_COMPONENTS, QOI_OPERATIONS, run_cfd`) | hard import; **execution call** `run_cfd(...)` at `:166`; vocab re-checks at `:66-70` | deep — the execute step is hardwired to one wrapper |
| P4 | `harness/validation_batch.py:62` (`CONTAINER, DOCKER_CONTEXT`) | hard import | shallow, harness-only |

**Direct contract-constant imports (`from substrates import CAVITY_2D_CONTRACT`) — the same shape stage 3 had before R-S3-1:**

| # | Site | Used at |
|---|---|---|
| P5 | `stages/gate1_chooser.py:40` | prompt block `:65` |
| P6 | `stages/reflection_reviews.py:84` | prompt block `:206` |
| P7 | `stages/generation_strategies.py:54` | feasibility nudge `:120` |
| P8 | `stages/stage2_experiment_design.py:29` | model-visible `stage_input["substrate_contract"]` `:182` |

**String-literal / default pins:**

| # | Site | Kind |
|---|---|---|
| P9 | `tools/experiment_picker.py:68-107` | cavity per-step solver rate hardcoded from the contract (`:68-73`); substrate detection by parameter-name signature `{"lid_velocity","cavity_length"}` (`:102-103`) — a cost model that only knows cavity |
| P10 | `stages/stage4_case_builder.py:58` `TEMPLATE = SHARED_HOST / "cavity_baseline"` | default template path (subsumed by P2 but is the single loudest literal) |

**Comment/docstring-only (not code pins, listed for completeness):** `supervisor.py:212`, `stages/stage3_fidelity_gate.py:116-117`, `harness/calibration_battery.py:22`, `harness/fidelity_case_runner.py:10` (the last two are **stale** — see §9). `schemas.py` carries **no** run_cfd import and no cavity literal (grep over `schemas.py` returned none); its QoI-summary shape (`schemas.py:161-192`: `converged, wall_clock_s, qoi_value|qoi_error`) is substrate-neutral in vocabulary but assumes a converged/wall-clock-shaped summary.

**Was Stage 2 the only pin? No — it is the shallowest of four hard-import pins plus four contract-constant pins plus a pinned cost model.** Stage 3 was the same shape and was already un-pinned by `07816ba`.

### Q9: whose vocabulary does the case builder halt on?

Its **own**, not the wrapper's and not the registry's: `BUILDABLE_PARAMS` is defined locally at `stages/stage4_case_builder.py:62-69` (six cavity parameter names, each mapped to an OpenFOAM file), with the halt-loudly-by-name behavior the recipe describes. This is a **second, independent** copy of the cavity vocabulary — pinned by local definition, not by import — and it must agree by hand with the contract's §5 list (`substrates.py:§5`, "CANONICAL PARAMETER VOCABULARY", same six names). Nothing asserts the two lists match (no cross-reference found between `stage4_case_builder.BUILDABLE_PARAMS` and `substrates.py` text).

### Q10: `right_instrument`

**Free text.** The stage-3 validator requires only a non-empty string (`stages/stage3_fidelity_gate.py:90-93`; same in `schemas.py:145`). The prompt instructs the model to repeat the named instrument or write "none — route to human/real experiment" (`stages/stage3_fidelity_gate.py:52`), but no code checks the value against the registry — so yes, **it can name a substrate that isn't cavity, or anything else**, and nothing downstream branches on it: the supervisor merely displays it (`supervisor.py:388`) and the maturity hook leaves it "as the model wrote" (`supervisor.py:227`).

### Q11: ⭐ the measured unit — R-S3-1 part A (`07816ba`)

From diff:`07816ba` (`diff_R-S3-1-partA.txt`): 6 files, but two are calibration-battery JSON artifacts (+952, +1016) and one is a doc template (+19/−7). The **code surgery** was:

| File | Δ |
|---|---|
| `stages/stage3_fidelity_gate.py` | +17 / −3 (constant → `_selected_contract()` via registry) |
| `tools/substrate_registry.py` | +71 / −0 (`_CONTRACTS`, `contract_for`, `sole_routable_id`) |
| `tests/test_contract_registry.py` | +117 / −0, **10 tests** (`grep -c "def test"` = 10) |

**Unit = "un-pin one consumer": ~205 code lines across 3 files, 10 new tests, one commit.** The diff cannot yield wall-clock duration (no session log in the tarball); the commit message shows it landed alongside R-CARD-2 work in one session (diff header, commit subject). Duration per unit is therefore an assumption, stated as a band in Q12.

### Q12: ⭐ THE NUMBER

Cost per pin, in R-S3-1-part-A units (1 unit ≈ 205 code lines + ~10 tests, one focused surgery):

| Pin | Surgery | Units | Why |
|---|---|---|---|
| P1 (stage2 vocab) | vocab moves behind a per-substrate lookup (registry-adjacent, same `contract_for` pattern); validator takes injected vocab; fail-loud on missing vocab | 1.0–1.5 | same shape as the unit, but 4 names consumed at 6 sites vs 1 constant at 1 site, and a vocab table must be *defined* for at least one second substrate |
| P5–P8 (4 prompt-block contract imports) | replace `from substrates import` with registry read; byte-identity tests per R-WIN-1 fixture discipline (`tests/test_rwin1_prompts.py:5-11`) | 1.0–1.5 total | mechanical ×4, but each has a frozen-prompt byte-identity proof to re-anchor |
| P3 (stage4 execution dispatch) | `run_cfd(...)` call → dispatch keyed on substrate_id from the registry (wrapper field already exists per row, `tools/substrate_registry.py:62`); vocab re-checks follow P1 | 1.0 | direct analogue of the unit |
| P2 (case builder) | **the outlier.** The builder is a ~400-line OpenFOAM-specific module. Un-pinning = per-substrate builder dispatch **plus authoring a second builder.** For a substrate whose wrapper takes typed params directly (run_code / run_scipy style — wrappers exist: `tools/run_code.py`, `tools/run_scipy.py`), the second "builder" is thin: 1–2 units. For a mesh-building solver, comparable to the original: 3–4 units | 1–4 | **this is the uncertainty driver** |
| P9 (cost model) | either generalize or explicitly scope to cavity with a fail-soft for unknown signatures (it already returns a signature miss path, `tools/experiment_picker.py:91-103`) | 0.25–0.5 | optional for correctness; required for honesty of cost estimates |
| P4 (validation_batch) | harness-only; follow-on | 0.25 | |

**Stage-2-un-pin + full pin retirement: ≈ 4.5–9 units.**

### Q13–Q15: the router, as-is and minimum

> **SUPERSEDED (Packet B close, 2026-07-18).** The machinery these chapters priced is BUILT: signature-based selection (`tools/substrate_selection.py`, D.2) replaced `sole_routable_id` (retired from production, kept for tests/history at `tools/substrate_registry.py:297`); per-substrate vocabularies, adapters, translations, and entry constructors are live for all five routable substrates; the pin census's P5-P8 contract-constant imports were retired at `7f78115` (D.1). The text below is kept as the recon-era record only; do not cite it as current.
>
> **UPDATED (BIO Wave D.1b, `a60e2f4`, 2026-07-18) — Step 41 hierarchical routing is now LIVE in `select_substrate` (`tools/substrate_selection.py`).** Selection is no longer flat serve-ability + R-B-1; it is a four-level pipeline, all structural, reading only the vocab records each substrate declares (`tools/qoi_vocab.py`) — no new source of truth, no invented tie-break:
> - **L0 serve-ability** — declared parameter names ⊆ signature (unchanged);
> - **L1a regime-shape** — keep candidates whose regime grammar admits the spec's regime block (reuses `stage2_spec._validate_regime` via `vocab_for`);
> - **L1b QoI-vocab** — keep candidates whose QoI vocabulary admits the requested QoI (reuses `stage2_spec._validate_qoi`) — routes a shared-signature family on the quantity it asks for;
> - **L2 instance** — maturity then R-B-1's LOUD STOP, **Option 1 (loud stop, stated reason) — the owner-CONFIRMED standing policy, NO preference table** (Option 3 stays a queued per-family owner-declared add-on, built only if a family later needs a default winner).
>
> R-B-1 is PRESERVED byte-identical as the L2 default (reached only on genuine ties, not on every family); L1a/L1b are transparent when the spec declares no regime/qoi. Every level that empties the candidate set stops loudly with a level-named reason — never a cavity fallback. Proven by firing in `tests/test_step41_routing.py` (the live calculix/fenicsx pair is acceptance test #3; L1a/L1b each narrow both directions). Design of record: `docs/memo_step41_routing.md`. The text below is doubly historical.

**Q13 — verified, with one correction of emphasis.** The recipe's claim (`docs/substrate_onboarding_recipe.md:98-106`) that the fidelity gate's `right_instrument` is "the only routing decision the system currently makes" is **true for model-authored decisions** but understates the code: the *actual* routing decision today is structural, not model-made — `sole_routable_id()` at `stages/stage3_fidelity_gate.py:121` picks the substrate, and `right_instrument` is advisory free text nothing branches on (Q10). There is no standalone router: confirmed — no module selects among substrates; `sole_routable_id` raises on any plurality (`tools/substrate_registry.py:207-214`).

**Q14 — router cards.** Cavity's router-card material lives in `docs/substrate_registry.md` (staged, frozen for the wave: `docs/substrate_registry.md:143-144`) drafted from `docs/templates/router_card_TEMPLATE.md`. **No code reads any card**: the only place a card path appears in code is as the inert `card_path` string field (`tools/substrate_registry.py:63,76,88,97,106,115,129,138`); grep for card reads in `stages/ supervisor.py harness/` returns none. Human-facing, same class as envelope cards (R-20.5-1, `docs/envelope_card_calculix_cantilever.md:7`). Noted mismatch already flagged on disk: registry `cost_tier` vocabulary (`low/minimal`) ≠ router-card template vocabulary (`cheap/moderate/expensive`) (`docs/substrate_registry.md:180`).

**Q15 — minimum router for Step 28's done-when.** Required reads: the spec (to type the task), `routable_ids()`/maturity (`tools/substrate_registry.py:241-247,229-238`), `contract_for` per candidate (`:165-194`). Required builds: (i) a selection function replacing the two `sole_routable_id` call sites — a task-typing rule as simple as parameter-signature matching, which `experiment_picker._detect` already prototypes (`tools/experiment_picker.py:91-103`): **1 unit**; (ii) contract enrollment for the second substrate — one `_CONTRACTS` line + ruling; contract text already drafted for ngspice/fenicsx/sympy in `onboarding/*/contract.py` (e.g. `onboarding/ngspice_linear_passive/contract.py:10-15`): **0.25 unit**; (iii) the human-pause half of the done-when **already exists** — the maturity hook fires on any trust/refine touching a non-mature routable (§4), and every candidate second substrate is `calibrating` — **0 units**; (iv) P1 + P3 from Q12 so the routed spec can validate and execute: **2–2.5 units**; (v) P2's second builder: **1–4 units** depending on substrate choice.

**Minimum router total: ≈ 4.5–8 units.** (Overlaps Q12 — the union, not the sum, is the build.)

### THE NUMBER, translated

Union of Q12 + Q15 (they share P1/P2/P3): **≈ 5–9 units.** At the observed cadence — the unit landed as one focused surgery inside a single session, and the 2× bigger `d6c52fa` (+740 code/test lines across 6 files, diff:`d6c52fa`) also landed in one session — a defensible band is **0.5–1 day per unit**, giving:

> **Stage-2 un-pin + minimum router: ≈ 3–5 days if the second substrate is a no-mesh wrapper (run_code / run_scipy / run_ngspice class); ≈ 5–9 days if it requires a second full case builder (FEA/FEniCSx class). Confidence: medium on the unit count (it comes from a line-by-line pin census), low on the days-per-unit conversion (no duration data exists on disk — only diff sizes and one-session commit cadence). The single biggest uncertainty is P2, the second case builder; the Wave Guide's "~2–3 days" is reachable only in the no-mesh case and only at the fast end of the cadence band.**

---

## 7. Model-visible vs human-facing (D.4 Q16)

**The model sees, per stage (each via `stage_input` / composed prompt):**
- Stage 1 generation: `CAVITY_2D_CONTRACT` in the feasibility nudge (`stages/generation_strategies.py:117-120`).
- Reflection: contract block (`stages/reflection_reviews.py:203-206`).
- Gate-1 chooser: contract block (`stages/gate1_chooser.py:62-65`).
- Stage 2 design: `"substrate_contract": CAVITY_2D_CONTRACT` (`stages/stage2_experiment_design.py:182`).
- Stage 3: registry-selected contract in `stage_input` (`stages/stage3_fidelity_gate.py:131-136`).
- Stage 4: **no model at all** — "Deterministic control flow, ZERO model calls" (`stages/stage4_simulation.py:4`).
- **Stage 5 (NEW, BIO Wave D.1a `664b5c2`):** the thought layer now receives the routed substrate's own fidelity contract as an OPTIONAL seventh prompt-inputs key `substrate_contract` — threaded by `run()` via `registry.contract_for(payload["substrate_id"])` for every substrate EXCEPT the declared frozen anchor (`registry.is_frozen_anchor` — cavity, excluded so its stage-5 turn stays byte-frozen). `PROMPT_INPUT_KEYS` stays the six-key core (the leak tripwire allows the one optional key, still fires on a missing core key or any eighth key); `SYSTEM_PROMPT` is UNCHANGED. So cavity's stage-5 model input is byte-identical (`tests/test_d0_stage5_input.py`, green and unchanged), while ngspice/sympy/fenicsx grew by exactly the added contract (blessed non-anchor re-capture, proven additive-only). Grounds stage 6's already-built "What Humans Must Validate" sidecar (Step 22) via stage 5's justification.
All model-visible contract blocks are asserted to be the imported constant, never a paste (`tests/test_rwin1_prompts.py:103-144`, `tests/test_multiqoi_contract_schema.py:80`).

**Human-facing only (no code reads, no model sees):** every envelope card (R-20.5-1 banner, e.g. `docs/envelope_card_calculix_cantilever.md:7`, `..._fenicsx...:6`, `..._ngspice...:6`, `..._sympy...:7`, `..._code_sklearn...:8`); the router card / cost-tier table (`docs/substrate_registry.md:143-144`); `card_path` in the registry is an inert string (`tools/substrate_registry.py:63`).

## 8. The era (D.4 Q17)

**`5bc037c` is the era-of-record commit** since the BIO Wave D.4 promotion (owner-ruled 2026-07-19; the chain since recon: `862531b` -> `e9084af` (R5) -> the Step-23.5 build's final commit -> `167fdaa` (Phase 1) -> `a07f939` (Phase 2) -> `6befb63` (BIO Wave D.1) -> **`5bc037c` (BIO Wave D.4 promotion)**). Each move was deliberate, ruled, and contained to pre-disclosed / blessed pins. **The D.4 move (`5bc037c`):** cavity's model-visible surfaces did NOT change — the era anchor held byte-identical (`tests/test_d0_stage5_input.py`, unchanged; the frozen-anchor property, §2). What moved were the two BLESSED GROWING FIXTURES, each grown ADDITIVE-ONLY by exactly the three newly-routable substrates and proven so before re-capture: `tests/fixtures/d1/feasibility_nudge.txt` (the all-routable contract block, five blocks -> **eight**: gains the rdkit/cobrapy/mafft contracts verbatim in enrollment order, drops nothing) and `tests/fixtures/c235/chooser_retry_user_turn_v235.txt` (the routable-id retry list, five ids -> **eight**: gains exactly `rdkit`/`cobrapy`/`mafft`). Pre-D.4 originals preserved append-only as `*_pred4` (joining the earlier `*_preb1`/`*_preb2` series). This is the same owner-ruled growing-fixture behavior as the D.1 non-anchor stage-5 inputs — the fixtures re-capture whatever is actually routable at the merge, NOT an era break. **Verified by byte-identity tests, not procedure:** `tests/test_d4_bio_promotion.py::TestFixturesAdditiveOnly`, `test_d1_contract_surfaces`, `test_c235_captures`, the D.0 stage-5 anchor pin, and the R-WIN-1 fixture suite. Moving the era = changing model-visible text under a ruling and re-capturing the affected pins (anchor pins never move; non-anchor / all-routable pins may grow additively under a ruling); no other mechanism on disk.

---

## 9. Stale statements found on disk (surprises)

- `substrates.py:12` "Nothing imports this file yet" — false since at least Step 28: eight importers (§6 P5–P8, `tools/substrate_registry.py:39`, `tools/experiment_picker.py` by reference).
- `harness/fidelity_case_runner.py:10` and `harness/calibration_battery.py:22` claim `stage3.run()` "hardcodes CAVITY_2D_CONTRACT" — stale since `07816ba`; run() is registry-driven (`stages/stage3_fidelity_gate.py:114-122`). The *design consequence* (battery bypasses run()) still stands, but the stated reason is outdated.
- `envelope_card_cavity2d.md` carries **no** R-20.5-1 human-facing banner, unlike all five newer cards (banner grep hits only the non-cavity cards). Convention says it's human-facing; the cavity card itself doesn't say so.
- Registry `cost_tier` vs router-card tier vocabulary mismatch, already flagged at `docs/substrate_registry.md:180`.

## 10. Block E acceptance table

| # | Must state | Where in this doc | Tick |
|---|---|---|---|
| 1 | where contracts live, why not `substrates.py` | §1 (`tools/substrate_registry.py:160-194`) | ✅ |
| 2 | `_REGISTRY` ≠ `_CONTRACTS`, what each gates | §3 (`:72-144` vs `:160-162`) | ✅ |
| 3 | Stage 2 CFD-pinned at the import line; no snippet to paste | §6 Q7 (`stages/stage2_spec.py:22`) | ✅ |
| 4 | card is human-facing; model never sees it | §7 (R-20.5-1 banners; inert `card_path`) | ✅ — with the caveat that the **cavity** card itself lacks the banner (§9); the claim holds by code inspection (no card read sites) |
| 5 | the registry is `tools/substrate_registry.py`; row order | §2 (`:72-144`; order test `tests/test_substrate_registry.py:24-37`) | ✅ |
| 6 | `calibrating` means pre-registration-for-routing; registration follows calibration | §5 steps 2–5 (`tools/substrate_registry.py:10-11,30-32`) — precise form: `calibrating` = enrolled-but-never-routable; *routing* registration (`_CONTRACTS` + `routable=True`) follows calibration by separate ruling | ✅ |

## 10.5 ADDENDUM (same session, +30 min): P2 re-priced — no Wave-2 substrate needs a stage-4 builder

Owner hypothesis, verified: **every Wave-2 wrapper is its own builder.** Each takes a typed dict and constructs its solver input internally, deterministically, with no external case directory to synthesize:

- `run_fea(spec)` (`tools/run_fea.py:319`): "a typed input… is turned into a CalculiX input deck by a template + deterministic Python mesh generator" (`tools/run_fea.py:10-12`); deck built by `build_deck(spec)` (`:123`), mesh by `_mesh_counts` (`:109`).
- `run_fenicsx(spec)` (`tools/run_fenicsx.py:274`): "typed input… is turned into a mesh + solve by a fixed in-container script" (`:15-17`) — **the mesh is built inside the wrapper**, so the FEniCSx "mesh-building" fork in §6 Q12 was a false fork.
- `run_ngspice(spec)` (`tools/run_ngspice.py:873`): full deck composed by the wrapper (`compose_deck`, `:509`); the wrapper owns every dot-command and the analysis statement (`:30-37`).
- `run_scipy(spec, …)` (`tools/run_scipy.py:1314`): runs a fixed job template, never writes code (`:5-7`); allowlists imported from `onboarding/sympy_symbolic_exact/contract.py` as single source of truth (`:11-14`).
- `run_code(spec, …)` (`tools/run_code.py:522`): runner generated from a fixed template, only allowlisted spec values filled in (`:5-7`).

**What stage 4 still needs per non-CFD substrate is dispatch plus a thin adapter, not a builder:** (i) map the stage-2 spec's parameter list to the wrapper's typed dict per mini-run; (ii) translate the QoI request; (iii) adapt the return shape — and (iii) is the genuinely new fact this check surfaced: the Wave-2 wrappers return `{valid, qoi, diagnostics, runtime_s}` (e.g. `tools/run_fea.py:22-26`) while the locked stage-4→5 boundary expects `{converged, wall_clock_s, qoi_value|qoi_error}` (`schemas.py:161-192`). `valid` and `converged` are not synonyms; reconciling them is a schema-boundary decision that needs a ruling, not just code.

**Re-priced:** P2+P3 collapse to dispatch + first adapter ≈ 1.0–1.5 units, +0.25 per additional substrate. Union total (with P1, P5–P8, selection, enrollment unchanged from §6): **≈ 4.5–6 units.**

> **THE NUMBER, restated: ≈ 2.5–5 days, with NO substrate-choice fork — the 5–9-day FEA/FEniCSx branch is retired.** Confidence: medium-high on the unit count (the fork's premise is now disproven by wrapper docstrings and entry points, cited above); still low on days-per-unit (unchanged, no duration data). The remaining uncertainty drivers, in order: the `valid`-vs-`converged` schema-boundary ruling, and the per-substrate QoI vocabulary shape for stage 2 (P1) — FEA-class QoIs are *named quantities* (`tip_displacement`, `max_von_mises`, `tools/run_fea.py:24`), not field reductions, so the injected vocabulary is per-substrate in *shape*, not just in contents.

## 10.6 ADDENDUM (same session, +30 min): scoping the `valid`-vs-`converged` ruling

> **SETTLED (Packet B close, 2026-07-18).** Option 4 (additive widening) was ruled at D.5 (R1 option 4, commit `22e9fd7`) and is consumed live: `state` carries sympy's tri-state verbatim (`tools/substrate_dispatch.py`, `sympy_run_entry`); ngspice and both cantilevers map converged := (valid is true) with the mapping STATED in each contract's §3 (the cantilever constructors additionally take the additive `qoi_request` third parameter to pick one of the two returned numbers — Packet B Phase 2, ruled option V-A). Cavity entries stayed byte-identical throughout, by exact-dict asserts. The options text below is the recon-era record only.

**(a) Is there an honest mapping?** No — not to the CFD contract's own definition. `converged` is contractually strict for cavity: end time reached AND every final-step residual below 1e-3; "finished cleanly alone is not converged" (`substrates.py:§3`). The Wave-2 wrappers assert something weaker and different:
- `run_fea` returns `valid: True` iff input validated + deck built + solver exit 0 with a `.dat` produced + output parseable (`tools/run_fea.py:319-385`; the four `valid: False` exits at `:329,353,364,373` vs success `:382-384`). **No residual or convergence check exists** — a linear-elastic static solve is a direct solve; `valid` means "ran and parsed", exactly the thing the cavity contract says is *not* converged.
- `run_scipy` is **tri-state**, not boolean: `state ∈ {solved_verified, unevaluated, error}` (`tools/run_scipy.py:117-119`), and `valid: True` coexists with `state: unevaluated` (`:1412`). A bool mapping destroys information the wrapper deliberately reports.
- `run_ngspice` / `run_fenicsx` return the same `{valid, qoi, diagnostics, runtime_s}` shape (`tools/run_ngspice.py:28`, `tools/run_fenicsx.py:34-38`) with no surfaced convergence notion.

So the field is not meaningless for them — but the honest per-substrate semantics is "completed-and-parsed" (FEA/ngspice/fenicsx) or a tri-state (scipy), never the cavity residual criterion.

**(b) Is `converged` model-visible at stage 5?** **Yes, twice:** `execution_results` (whose run entries carry `converged`, built at `stages/stage4_simulation.py:103-115`, schema-locked at `schemas.py:158-192`) is in stage 5's model input (`stages/stage5_thought_layer.py:44-51,220-227`), and so are the raw `stage4_summaries` (`:215-217,226`). Two era-relevant facts: (i) **no frozen prompt mentions the word** — stage 5's frozen `SYSTEM_PROMPT` says "judge whether the result is valid" and never says "converged" (`stages/stage5_thought_layer.py:63-97`); (ii) the era byte-identity machinery pins the composed prompt *families* and the contract (`tests/fixtures/rwin1/` = chooser, debate_judge, full_review, ranking_judge; `tests/test_contract_registry.py:52-70`) — **no fixture pins stage 5's input-data shape**. So renaming the field moves no frozen text, but it changes the model-visible payload for *cavity* runs, which violates the cavity-byte-identical discipline every prior surgery preserved (`07816ba` commit subject: "cavity byte-identical, era 862531b holds"). Also: stage 5 receives **no substrate contract** (its input key list, `stages/stage5_thought_layer.py:44-51`), so no contract text can explain a per-substrate meaning to the stage-5 model.

**(c) The options:**

| Option | Cost | Era / honesty consequence |
|---|---|---|
| **1. Rename** `converged` → neutral (`completed`) | ~1 unit: `schemas.py:158-192`, `stages/stage4_simulation.py:103-115,208-211`, `supervisor.py:399-407`, tests | No frozen prompt touched, but **cavity's model-visible payload changes** — breaks the cavity-byte-identical discipline; itself needs an era ruling. Pays the era cost yet keeps a bool still lossy for scipy |
| **2. Adapter maps `valid`→`converged` per substrate** | ~0.25 unit (inside the §10.5 adapter) | Cavity untouched, era holds trivially. **Dishonest as-is:** stage 5 sees `converged: true` meaning "ran and parsed", with no contract available at stage 5 to redefine it (see b). Loses scipy's tri-state |
| **3. Each card defines `converged` for its substrate** | ~0 code | **Cannot work alone:** cards are human-facing, no model sees them (R-20.5-1, §7) — the stage-5 model's ambiguity is untouched. Fine as documentation *on top of* another option |
| **4. Additive widening:** keep `converged` required, admit an optional per-substrate `state` key; per-substrate `converged` mapping ruled in each substrate's *contract* §3 (model-visible at stages 1–3) | ~0.5–0.75 unit: widen the closed key set at `schemas.py:189-192` + adapter + tests | **Cavity entries byte-identical** (absent optional key = unchanged shape — the established additive pattern: `stages/stage2_spec.py:35-55` OPTIONAL_SPEC_FIELDS; `supervisor.py:150` "key absent => record byte-identical"). Preserves scipy's tri-state; the bool's residual looseness is disclosed in the model-visible contract, which stages 1–3 do see |

**Recommendation to rule on:** option 4, with option 3's card documentation on top; option 2 alone is cheapest but leaves the stage-5 model reading a word whose definition it cannot access. Whatever is ruled, the per-substrate meaning of `converged` belongs in each substrate's **contract §3** (the one model-visible place, §7) — not only in the card.

## 10.7 ADDENDUM (same session, +15 min): days-per-unit replaced by a measured clock — partially

**What is measured vs. what still isn't.** No `.git` exists in the recon environment (tarball was cut without it), so this session cannot read the reflog itself. Available clock data: (i) owner-reported reflog gap — the ruler commit `07816ba` landed **45 minutes** after its predecessor `abe749a`; (ii) commit datetimes in the two supplied diff headers: `d6c52fa` 2026-07-15 13:37 −0400, `07816ba` 2026-07-16 02:08 −0400 (diff headers). A commit gap is an **upper bound on build time, not build time** — the gap can contain anything else the session did. A fuller measurement needs the reflog pasted; gaps for the other surgery-shaped commits are the one thing that would tighten this further.

**Build-hours per unit (measured, n=1):** the ruler unit (3 code files, ~205 lines, 10 tests, §6 Q11) took **≤ 0.75 build-hours**. Caveats: single data point; the 2×-sized `d6c52fa` has no predecessor gap available here; and the ruler was pure code surgery — the §10.6 schema-boundary work includes a design decision, which commits slower than mechanical un-pinning.

**THE NUMBER, restated as two figures:**

> **Build-hours (measured): 4.5–6 units × ≤ 0.75 h/unit ≈ 3.5–4.5 h; stated with a safety factor for the non-mechanical parts (schema widening, selection design) as ≈ 4–8 build-hours — under one working day of build.**
>
> **Calendar-days (build + rulings + review): 1–2 days, conditional.** The build is not the critical path; the **rulings are**: at minimum (R1) the `valid`-vs-`converged` schema ruling (§10.6 — options pre-drafted, ready to rule), (R2) contract wiring per substrate "under a recorded ruling" (`tools/substrate_registry.py:187-194`), (R3) the `routable=True` promotion ruling (`:24-28`), (R4) acceptance of the minimal selection design (Step 35 was deliberately named-not-built, `:200-206`). Observed ruling cadence supports same-day batching: the sympy row records a card signing plus S1–S6 plus three sub-rulings all ruled on one day, 2026-07-16 (`tools/substrate_registry.py:119-124`).
>
> **The Wave Guide's "1–2 calendar days" therefore survives the check — checked, not taken — under two conditions:** the four rulings are batched into one sitting (R1's options are already on the table in §10.6), and the first routed substrate is any single Wave-2 wrapper (per §10.5, none needs a builder, so the choice no longer moves the estimate). If rulings serialize across days, the calendar figure grows ruling-by-ruling while build-hours stay fixed.

## 11. Open questions (updated)

- ~~The sha this doc was read at~~ — resolved: `be1b1ff`, owner-supplied same day.
- ~~Days-per-unit~~ — partially resolved by §10.7 (one measured reflog gap, ≤ 0.75 h/unit upper bound); a pasted reflog would add the remaining surgery gaps.
- Whether `BUILDABLE_PARAMS` (`stages/stage4_case_builder.py:62-69`) and the contract's §5 vocabulary are asserted equal anywhere — none found; treated as an unguarded duplicate (§6 Q9).
- ~~Which substrate goes second~~ — retired by §10.5: no Wave-2 substrate needs a builder, so the choice no longer moves the estimate.

**RE-VERIFIED AT THE BIO Wave D.1 CLOSE (`6befb63`, 2026-07-18):** the header re-stamp, §2's `SubstrateRecord` field list (added `frozen_anchor`), the §6 SUPERSEDED block (Step-41 L0/L1a/L1b/L2 now live), the §7 stage-5 `substrate_contract` addition, and §8 (era advanced to `6befb63`). These carry the D.1 measured state.

**NOT RE-VERIFIED at the D.1 pass (still recon-/Packet-B-era):** §4 (the maturity hook — mechanism prose believed current; rung lists carry five substrates), §5 (wrapper-to-pipeline sequence — its point-6 `sole_routable_id`/plurality prose is stale; production selection is now Step-41, §6), §6 Q7-Q12 (the pin audit's per-pin tables — P1-P4 statuses unchecked; P5-P8 retired as noted), the §7 stages 1-4 bullets (only the stage-5 bullet was refreshed at D.1), §9 (stale-statements list), §10/10.7 (day-count arithmetic — historical), and every line-number citation inside those chapters. Re-verify before citing.
