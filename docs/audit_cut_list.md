# Phase A — Cut-list audit (READ-ONLY, zero deletions)

**Written:** 2026-07-21. **Branch:** `iterate-experiment-loop`.
**Method:** every claim below was reached by tracing actual callers (grep +
read), not asserted. Produced by six parallel caller-tracing passes over
`supervisor.py`, `substrates.py`, `tools/substrate_registry.py`, the `stages/`,
`harness/`, `onboarding/`, and `tests/`. Multiple passes independently
confirmed the load-bearing facts (EXACT_ROUTE default-off; the exact route
bypasses stages 2–5; cavity stays on the static path; calibration is
offline-only; envelope cards are never read at runtime).

**This is an audit, not a cut.** It feeds Phase B (§101 of
`docs/plan_collapse_and_simplify.md`): owner signs off per Bucket-1 item before
any deletion.

---

## 0. The governing insight (read this first — it reframes the whole cut)

Two facts change how "cut the exact-tool ceremony" must be executed:

1. **The ceremony and the approximate pipeline are the SAME code.**
   `cavity_2d_cfd` — the frozen anchor — is `instrument_class=APPROXIMATE`,
   `maturity=PROVISIONAL` (`tools/substrate_registry.py:128-147`). Approximate
   instruments have **no experimenter path** (the compose agent *refuses*
   approximate steps, `tools/compose_agent.py:242-256`), so cavity/calculix/
   fenicsx **structurally require static stages 2–5 + the fidelity gate**. You
   cannot delete stages 2–5, the fidelity gate, or the maturity hook — cavity
   rides them. They **demote to approximate-only**, they do not get cut.

2. **The exact-tool bypass is already built but OFF by default.** With
   `EXACT_ROUTE=1` *and* an exact `substrate_id` at gate 1, `run_exact_route`
   replaces stages 2–5 with the experimenter loop and the run ends there —
   fidelity gate, both agreement checks, stage-2 spec ceremony, and the
   maturity hook (which fires inside stage 3) are all skipped
   (`supervisor.py:1665-1666`, `stages/experiment_route.py:38-51`). But
   `exact_route_active()` is `os.environ.get("EXACT_ROUTE") == "1"`, **off by
   default** (`supervisor.py:1392`; comment `:133`). So *today's live default
   still runs the full ceremony for the five exact tools.*

**Therefore the real cut has two moves, in order:**
- **(M1) Flip the exact route on for exact instruments** (make `EXACT_ROUTE`
  the default, or delete the flag and route on `instrument_class`). This
  *retires* the runtime ceremony for exact tools without touching the shared
  static pipeline that cavity needs. Once M1 lands, the exact-tool ceremony is
  dead code, not live behavior.
- **(M2) Delete the genuinely-orphaned apparatus** (calibration battery,
  envelope-card files, onboarding kit, dead helpers). These are already
  unreachable from any supervised run *today* — see Bucket 1.

Do NOT try to delete stages 2–5 themselves. That is a Bucket-2/3 mistake.

---

## 1. Corrected ground truth — the roster (supersedes stale prose)

Classification lives in **`tools/substrate_registry.py` `_REGISTRY`** (lines
127–565), NOT `substrates.py` (which holds only the model-visible contract
*text*). `instrument_class` defaults to `APPROXIMATE`
(`substrate_registry.py:113`, fail-safe); only 5 rows override to `EXACT`.

**20 enrolled · 10 routable · 5 mature · 5 exact.** The 5 exact and 5 mature are
the same set: **`rdkit, cobrapy, homology_search, mafft, python_experiment`**
(markers at `substrate_registry.py:247, 269, 314, 345, 532`).

Approximate physical simulators (the KEEP set): **`cavity_2d_cfd`
(PROVISIONAL, frozen_anchor), `calculix_cantilever_fea` (CALIBRATING),
`fenicsx_cantilever_elastic` (CALIBRATING)** — all class-default APPROXIMATE.

**Name-vs-class traps — do NOT classify by name when cutting:**
- `sympy_symbolic_exact` — name and contract say "exact", but the record has
  **no `EXACT` marker** → APPROXIMATE by default (`substrate_registry.py:207`).
  Deliberate: its failure mode is "an exactly correct answer to the wrong
  question" (`substrates.py:474-478`), exactly what the fidelity gate guards.
- `ngspice_linear_passive` — contract says "a linear network has an exact
  answer" but the record is APPROXIMATE (`substrate_registry.py:229`).
- `scipy` is **not a substrate id** (the plan's parenthetical is loose);
  `sympy_symbolic_exact` uses the `run_scipy.py` wrapper.
- Stale docstring: `routable_ids()` (`substrate_registry.py:769-780`) still
  says "nine ids / last four mature" — live count is 10 routable / 5 mature
  after python_experiment's 2026-07-21 promotion. Prose only; the function
  derives from `_REGISTRY`, so no logic bug.

---

## 2. BUCKET 1 — DEAD in the run path → safe to cut (owner signs off per item)

These are unreachable from any `supervisor.py --mode auto/human` run **today**,
for exact *and* approximate tools alike. The one nuance: some of them are the
*promotion track* for approximate tools (a human re-runs them to justify
bumping a `maturity=` constant). So "safe to cut" = safe to remove from the
**run path**; if kept at all, keep only as an offline promotion aid, and only
for the approximate frontier.

| # | Item | Module / lines | Who calls it | Evidence it's dead in the run path |
|---|---|---|---|---|
| B1-a | **Calibration battery + ledger** | `harness/calibration_battery.py` (649L), `harness/calibration_ledger.py` (174L) | Only `harness/run_harness.py:396,409` (`--mode calibration`, manual) and `harness/c13_steerability_probe.py:59,317` (manual probe) + tests | `supervisor.py`, `stages/`, `pi_agent/` have **zero** calibration references (grep empty). Battery self-describes as "LEDGER-SILENT / NOT part of FAST's hard gate" (`calibration_battery.py:26,45`). |
| B1-b | **Calibration case + report JSON** | 26 `harness/calibration_*.json` (12 `calibration_cases_*` inputs + 14 timestamped reports) | Read only by the battery/probe above | `substrate_registry.py` mentions them only in `notes=` prose strings (`:159,193,278,…`); the registry does **zero** file I/O (`grep 'json.load|open(|read_text'` over it = empty). |
| B1-c | **Envelope cards** | 18 `docs/envelope_card_*.md` | **Nothing at runtime.** `card_path` is stored per registry row (`substrate_registry.py:93`) but never opened | Proof: `python_experiment`'s `card_path` points at `docs/envelope_card_python_experiment.md` which **does not exist on disk**, yet python_experiment routes+executes fine. If cards were read at runtime that route would crash. The live "envelope" is the contract *text* via `contract_for()`. |
| B1-d | **Onboarding kit** | `onboarding/<15 substrates>/` (`contract.py`, `registry_row_fragment.py`, `d4_wiring_fragments.py`, `generate_calibration_cases.py`, `selfcheck_evidence.json`, …) | **No runtime importer** — `grep 'from onboarding\|import onboarding'` over `stages/`, `tools/`, `supervisor.py`, `harness/` = empty | Authoring-only staging kit. Dependency runs the *opposite* way: `onboarding/<s>/contract.py` re-exports the constant *from* `substrates.py` (e.g. `onboarding/rdkit/contract.py:25`). Only prod mention is a provenance comment (`substrates.py:783`). |
| B1-e | **Dead `fidelity_gate_applies` helper** | `tools/substrate_registry.py:760-766` | **No production caller** — only `tests/test_instrument_class.py:61,65` | The live route decision is `routed_instrument_is_exact` + `exact_route_active` (`supervisor.py:1395,1389`), which call `is_approximate()` directly, never `fidelity_gate_applies`. |
| B1-f | **Fidelity gate + agreement checks AS THEY APPLY TO EXACT TOOLS** | `stages/stage3_fidelity_gate.py:142` (Opus call), agreement raises `stage3_fidelity_gate.py:152` + `stage4_simulation.py:311` | Fire for exact tools only because `EXACT_ROUTE` is off (see §0-M1) | Under `EXACT_ROUTE=1` + exact instrument these are already fully bypassed (`supervisor.py:1665-1666`; run ends in `run_exact_route`). They gate a non-question for a deterministic tool. **Cut = M1 (flip the route), not deleting the code** (cavity needs it). |
| B1-g | **Static stage-2 spec ceremony FOR EXACT TOOLS** | `validate_spec` + `vocab_for` machine-key QoI vocab + `signature_for`/`_serve_ability_errors` (`stage2_experiment_design.py:297-303,381`; `stage2_spec.py`) | Consumed only by stage 2 and `chain_runner.py:147-148` | The experimenter path uses **none** of it — the compose agent authors `typed_input`+`quantity` directly and `verification.py` runs+verifies; the only QoI artifact there is a lightweight `qoi_request={"quantity":…}` passthrough (`verification.py:209,433`). Retired for exact tools by M1. |

**Cross-cutting caveat for B1-a/b/c/d:** these are the substrate *promotion*
apparatus. They are dead in the RUN path for every tool, but for the approximate
frontier (calculix/fenicsx are `CALIBRATING`) they are the offline evidence a
human uses to promote to `MATURE`. If the owner intends to promote more
approximate simulators later, keep the *battery + cards for approximate tools*
as an offline aid; the exact tools' calibration cases/cards/onboarding dirs
(`rdkit, cobrapy, mafft, homology_search`) are inert on both axes and are the
cleanest first deletions.

---

## 3. BUCKET 2 — LOAD-BEARING for approximate tools → KEEP

These earn their keep for tools that can be **confidently wrong** (converge to a
wrong number that reproduction faithfully reproduces). Do not touch.

| Item | Module / lines | Why it stays |
|---|---|---|
| **Fidelity gate (the judgment itself)** | `stages/stage3_fidelity_gate.py:43-53,142` | The only thing between "converged" and "confidently-wrong" for cavity/calculix/fenicsx. The rationale is stated in code: `compose_agent.py:242-256`. |
| **Static stages 2–5 for approximate** | `supervisor.py:35-49` STAGES; `stage2_experiment_design.py`, `stage4_case_builder.py`, `stage4_simulation.py`, `stage5_thought_layer.py` | Approximate tools have no experimenter path; they *require* the typed spec → case-build (`call_style=CALL_CASE_BUILD`) → run flow. |
| **Contract text (sections 2/4/3/5)** | `substrates.py` constants; `contract_for()` `substrate_registry.py:626` | Sections 3/5 (regime certainty, trust/refine, "gap uncheckable by the gate") are *written for the fidelity gate* and are load-bearing for approximate. (Sections 2/4 — typed input, returned metrics — are also read by the compose agent on the exact path, so the contract text is not purely approximate.) |
| **Maturity hook (as it bites approximate)** | `supervisor.py:415-495`, fired `:1594-1595` | For non-mature routable substrates (all three approximate simulators) it forces human sign-off / auto-downgrades trust→defer. This is real unattended-safety for tools that can be confidently wrong. No-op for the (mature) exact tools. |
| **`verification.py` — the wall** | `stages/verification.py` (731L) | Non-negotiable (plan §5). Not ceremony. |
| **`capability_guard.py`** | `capability_guard.py` (227L) | Live on the tooled-agent branch; guards isolation/evidence (transcript read-back, calibration answer-key leaks, memory/runs mutation). Orthogonal to maturity/envelopes — this is part of the wall philosophy, KEEP. |

---

## 4. BUCKET 3 — ENTANGLED → needs a ruling before cutting

| Item | Where | Why it needs a ruling |
|---|---|---|
| **`gate1_chooser` + `substrate_id`** | `stages/gate1_chooser.py:194`; applied `supervisor.py:1646-1648` | Produces `substrate_id`, consumed by BOTH the exact-route dispatch (`supervisor.py:1403`) AND the approximate agreement checks. Cannot be cut — it is the instrument decision for *every* run, exact included. It's CORE, not ceremony. |
| **Cavity frozen-anchor byte-identity** | `is_frozen_anchor` `substrate_registry.py:733`; `CAVITY_2D_CONTRACT` `substrates.py:16`; pinned surfaces in stage 2/3/5 | Cutting the exact route does **not** touch cavity (it never routes there). BUT the pinned model bytes are *produced by* `contract_for` / `_selected_contract` / `routable_contracts_block` / stage-2 contract threading. **Any** refactor of that fetch/assembly path reddens the byte-identity tests. Respect it: do not touch contract-fetch internals while cutting. |
| **Maturity hook removal** | `supervisor.py:415-495` | It's a no-op for exact tools, so removing it *seems* exact-only — but cavity (non-mature) is a **live consumer**: today the hook downgrades a cavity trust verdict to defer (auto) / flags NEEDS_HUMAN_SIGNOFF (human). Cutting it changes cavity's runtime behavior. Ruling needed; likely KEEP (it's Bucket 2 for approximate). |
| **`call_style` / `CALL_CASE_BUILD` on the exact path** | `verification.py:175,420-423` | Structurally *refused* in the composition executor ("cannot emit or consume a file artifact yet") so it's inert on the exact path — but it's the approximate case-build style. Trim the exact-path reference only; keep the approximate machinery. |
| **File-artifact typed vocabulary (R-ART-7/8)** | `emits`/`consumes`/`resolve` in `verification.py:272-322,388-478`; `_ARTIFACT_RESOLVERS:367` (one method); taught `compose_agent.py:98-113` | Load-bearing *in principle* for multi-tool pipelines and test-covered, but **not exercised live** — zero `runs/*/investigation.json` contain `emits`/`consumes` (grep empty); exactly one resolver (`fasta_first_ungapped`). This is the "thin-glue lens re-examination" the plan defers to Phase C3, not a Phase-B cut. Flag, don't cut. |

---

## 5. STOP-and-rule tripwires (locked artifacts — record a ruling first)

- **`schemas.py` is locked (Step 15).** A cut hits it — forcing a recorded
  ruling — only if it (a) removes/renames **`vocab_for`** (called directly by
  `schemas._check_experiment_spec:182`), or (b) removes the **`substrate_id`
  payload key** (validated in all five boundary validators,
  `schemas.py:451,466,483,501,521`; schema-atomicity rule `:56-59`). Cuts
  confined to the maturity hook, calibration, cards, onboarding, or
  contract-fetch *internals* do **not** edit `schemas.py`.
- **Cavity byte-identity** (§4) — any perturbation of the contract-fetch /
  prompt-assembly path is a STOP-and-rule + fixture-preservation event.
- Standard project rules apply: preserve superseded fixtures append-only
  (`*_pre<x>`), never `git add -A`, no model in the verification path.

---

## 6. Tests that will move (tie each cut to its guard)

- **Calibration cut (B1-a/b):** `tests/test_calibration_battery.py`,
  `test_calibration_cases_ngspice.py`,
  `test_c13_probe_and_calibration_ledger.py`, `test_gate_bets.py`,
  `test_fidelity_ledger_substrate.py`.
- **Envelope-card / onboarding cut (B1-c/d):** no runtime tests (they're not in
  the run path); onboarding self-checks live under `onboarding/*/selfcheck_*`.
- **Maturity machinery (Bucket 3 — expect to KEEP):** `test_maturity_hook.py`,
  `test_flip_promotion.py`, `test_b1/b2_flip_promotion.py`,
  `test_d4_bio_promotion.py`, `test_substrate_registry.py:270-273`.
- **Contract / cavity byte-identity (must stay GREEN):**
  `test_contract_registry.py:82-94`, `test_d1_contract_surfaces.py:98-160`,
  `test_d1a_stage5_contract.py:90-102`, `test_c235_chain.py:345`,
  `test_instrument_class.py:99`.
- **Exact route / selection (must stay GREEN through M1):**
  `test_exact_route_supervisor.py`, `test_instrument_class.py`,
  `test_substrate_selection.py`, `test_step41_routing.py`.
- **Locked-schema coupling (STOP-and-rule if red):** `test_stage2_spec.py`,
  `test_qoi_vocab.py`, `test_multiqoi_contract_schema.py`, `test_null_twin.py`,
  `test_r2355_captures.py`, `test_r2355_regime.py`.

---

## 7. Recommended cut order (feeds Phase B §101–§111)

Biggest, cleanest, lowest-risk first:

1. **M1 — flip the exact route on for exact instruments** (make `EXACT_ROUTE`
   default for exact `substrate_id`, or route on `instrument_class` and drop
   the env flag). This is the single lever that retires the runtime fidelity /
   agreement / stage-2 / maturity ceremony for the five exact tools **without
   deleting any shared static-pipeline code**. Verify: exact runs enter
   `run_exact_route`; cavity/calculix/fenicsx runs stay byte-identical; whole
   suite green. This IS the plan's §6-step-4 intent, done safely.
2. **Delete the exact-tools' orphaned apparatus** (B1-e dead helper; then the
   `rdkit/cobrapy/mafft/homology_search` calibration cases + reports + envelope
   cards + onboarding dirs — inert on both run and promotion axes for mature
   exact tools).
3. **Decide the approximate-frontier promotion apparatus** (B1-a/b/c/d for
   calculix/fenicsx) — keep as offline aid or cut, owner's call; not in the run
   path either way.
4. **Do NOT** touch stages 2–5, the fidelity gate, the maturity hook, or
   contract-fetch internals — cavity rides them (Bucket 2/3).

**Nothing in this audit has been deleted.** Phase B begins only after per-item
owner sign-off, starting with M1.
