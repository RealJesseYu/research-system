# Plan — collapse to autonomy, then cut the ceremony

**Written:** 2026-07-21. **Branch:** `iterate-experiment-loop` (HEAD `028773c`).
**Status:** the thin autonomous core is built and the experimenter is validated
live; the next major move is **subtraction** (an audit, then careful cutting),
not more features. This file is the durable plan — a new chat can start from it.

**How to resume in a fresh session:** open this file first, then
`docs/architecture_collapse_manifest.md` (§2 is the cut list, §4 the target
shape). The rest of this doc is self-contained.

---

## 0. The sharpened vision (owner, this session — read this before anything)

**Autonomy means autonomy.** The goal is an agent that operates *independently*
and goes where its own creativity takes it — NOT a system with a special feature
bolted on per function. This project was burned before by exactly that: it
"couldn't operate independently" because it was chopped into sealed, special-cased
stages (the manifest's own words: *weaker than a plain chat*). Do not drift back
into feature-accretion. The test for any change is **"does this let it operate
more independently / go somewhere surprising?"** — never "did we add a
capability?"

### The ONE thing that is not a feature and must never be cut
A chat, left unwatched, **narrates** — it reports a number nobody computed. The
line that separates a trustworthy unattended researcher from an unsupervised chat
is: **a kept number must re-run deterministically (no model, no network) and
reproduce.** That wall (`stages/verification.py`, the propose→measure boundary)
is *the point*, not ceremony. Everything else should be as open and un-special-
cased as the wall allows.

Framing to hold onto: **endless freedom in HOW it investigates; a hard wall only
at the result boundary.**

---

## 1. The fork, decided: thin glue (NOT callable-in-code)

Should science tools be *callable functions the agent's code invokes*, or *typed
orchestrated steps*?

**Ruling (builder, owner-amendable): keep glue, make it THIN.**
- **Not callable-in-sandbox.** Letting sandboxed model code reach the tool
  containers breaks network isolation — a result could silently depend on the
  internet/host state and stop being re-runnable. Reproducibility is the wall; it
  forces *some* orchestration. That is the only thing that does.
- **But the current glue is more elaborate than reproducibility needs.** The
  overengineering is the typed vocabulary accreted *around* the orchestrator
  (resolvers, emit-flags, call-styles, per-substrate maturity/contracts), not the
  orchestrator itself. The agent already has near-total freedom inside a `code`
  step.
- **Connectors/MCP** are the honest vehicle for "tools the agent just reaches
  for" — but for *exploration*; a connector number is only a *kept* result once
  it is a re-runnable artifact (manifest §3).

Net: **glue because reproducibility forces it, thin because nothing else does.**

---

## 2. Where the cut analysis already lives

- **`docs/architecture_collapse_manifest.md` §2 — the KEEP / DEMOTE / CUT table.**
  This IS the authoritative cut list. It marks CUT/DEMOTE: the six sealed stages
  as the spine, one-substrate-per-run, static single-spec authoring, **the
  contract/calibration/maturity ceremony on exact tools**, the universal fidelity
  gate, and the gate/loop-back machinery.
- **`docs/handoff_experimenting_agent.md`** — the inverse guardrail ("do NOT
  delete the campaign-loop scaffolding": `run_one_point`, the `execution_results`
  contract, `compare_prediction`, per-iteration evidence). Respect it.
- No *separate* dedicated cut-report was found beyond the manifest §2 (searched
  2026-07-21). If the owner recalls one by name, pull it in before cutting.

---

## 3. THE PLAN (clear steps)

### Phase A — Audit (READ-ONLY, zero deletions). Do first.
Trace every caller of the ceremony the manifest §2 marks CUT and produce a
**verified three-bucket list**:

- **A1. Bucket 1 — DEAD for exact tools → safe to cut.** For the 5 exact tools
  (`rdkit, cobrapy, mafft, homology_search, python_experiment` — which are also
  the entire mature frontier), the maturity ladder, calibration batteries
  (`harness/calibration_*`, 29 files), envelope cards (18), substrate-selection
  agreement checks, and per-substrate maturity gating all decide a non-question
  (a deterministic tool cannot be confidently wrong; re-running IS the check).
- **A2. Bucket 2 — LOAD-BEARING for approximate tools → keep.** The fidelity gate
  and likely calibration for the CFD/FEA simulators (`cavity_2d_cfd`,
  `calculix_cantilever_fea`, `fenicsx_cantilever_elastic`) — these genuinely CAN
  be confidently wrong.
- **A3. Bucket 3 — ENTANGLED → needs a ruling.** cavity's frozen anchor
  (byte-identity), anything the supervisor's core loop / locked schemas depend on.
- **A4. Deliverable:** a written audit (`docs/audit_cut_list.md`) with, per item:
  the module/lines, who calls it, which bucket, and the evidence. **Ground every
  claim by tracing callers — no assert-without-looking.** Sizing already measured
  this session: ideation apparatus ≈3,250 lines (default-on); substrate
  maturity/selection/contract machinery ≈3,500 lines + a ≈4,300-line
  `harness/`; the thin core (experimenter + verification) ≈1,300 lines.

### Phase B — Cut by ruling, one bucket at a time. Owner signs off per bucket.
For each Bucket-1 item:
- **B1.** Record a ruling (STOP-and-rule); preserve superseded fixtures
  append-only (`*_pre<x>`).
- **B2.** Delete; keep the whole suite green; keep `verification.py` and cavity's
  byte-identity untouched; keep the approximate-tool path working.
- **B3.** Suggested order (biggest, cleanest first): (i) make the ideation
  apparatus on-demand by default (the depth switch is built — commit `9290e44`;
  wire "who chooses depth" so `quick` is default); (ii) strip the exact-tool
  maturity/calibration/contract ceremony (this is literally **manifest §6 step
  4**); (iii) demote gate/loop-back ceremony on the exact-tool path.
- **B4.** This is planned collapse, not a detour — §6 step 4 is the next ordered
  step regardless.

### Phase C — Resume forward capability ONLY after the cut. Thin by construction.
- **C1.** The director stays a **thin free-deciding agent** — budget-bounded and
  behind the verification wall — NOT a growing typed menu of moves. If you catch
  yourself adding move #4/#5/#6 as special cases, that is the smell to stop.
- **C2.** Prefer **connectors** (tools the agent reaches for) over new typed
  composition features.
- **C3.** Re-examine the file-artifact typed vocabulary (R-ART-7/8 resolvers/
  emit-flags) under the thin-glue lens; keep only what earns its keep.

---

## 4. Already built this session — DO NOT rebuild (branch `iterate-experiment-loop`)
The thin autonomous core. These ENABLE the cut (you can only delete the old path
once the new path works); they are not on the chopping block.

- `9290e44` — ideation depth switch (`stage1_ideation.run(depth=...)`), apparatus
  kept but made on-demand.
- `00be140` — **Phase 3 routing** (R-ROUTE): `instrument_class` marker on
  substrates (exact|approximate, default approximate/fail-safe); the experimenter
  loop replaces static stages 2–5 for an EXACT instrument, behind `EXACT_ROUTE=1`
  (off by default → production byte-identical); fidelity gate fires only for
  approximate. Memo: `docs/memo_phase3_routing.md`.
- `fa15d66` — routed runs get a deterministic, verified write-up
  (`exact_route_report.md`), no model in the report path.
- `df1547f` / `c46c6a9` / `f7b98a5` — **Phase 4 file hand-off** (R-ART-5/7/8):
  code↔code, a mature substrate emits (mafft), a substrate consumes via a
  resolver (mafft→homology). Every file re-derived on verification. Memo:
  `docs/memo_phase4_artifacts.md`. **(This is the typed vocabulary to re-examine
  in Phase C3.)**
- `193dbf2` / `32df94a` — compose_agent prompt fixes (top-level recipe `kind`;
  taught the file channel).
- `028773c` — **Phase 5 director, brick R-DIR-1**: the experimenter accepts a
  research question (`goal` threaded to `compose_agent`). Memo:
  `docs/memo_phase5_director.md` (R-DIR-2/3/4 are PAUSED per §0 — do not build
  them as typed moves without re-reading this plan).

**Live validation done:** first `caffeinate` outing of the experimenter passed —
3/3 probes verified, publishable, excellent small-before-big reasoning (it read
wrapper source to author valid recipes). The brain works.

**Owner's outstanding run (their Terminal):** the capstone —
`caffeinate -i env EXACT_ROUTE=1 venv/bin/python3 supervisor.py --mode auto
--domain "computational prediction of small-molecule physicochemical properties"`
— watch the log for `EXACT ROUTE` to confirm the full arc ran through the
experimenter.

---

## 5. Guardrails — what must NOT be cut or broken
- `stages/verification.py` and the propose→measure boundary — the wall.
- cavity's frozen-anchor byte-identity (model-visible surfaces).
- The approximate-instrument path (fidelity gate + calibration for CFD/FEA).
- The campaign-loop scaffolding the new design reuses
  (`docs/handoff_experimenting_agent.md`).
- The hard `max_moves` / turn budgets — an open-ended loop of powerful agents
  must stay bounded.

## 6. Rules & traps (owner-ruled)
- **Run-venue (absolute):** full/long runs from a plain Terminal under
  `caffeinate`, never a builder-session background task.
- **STOP-and-rule:** contracts, locked schemas, "ruled" inputs, deletions of
  trust-bearing state → record the decision first.
- **Never `git add -A`** — the tree carries the owner's dirty files (memory
  ledgers, `tests/test_campaign_controller.py`, `tests/test_scholar_search.py`).
  Stage explicit paths.
- **Verification purity:** no model in the verification path.
- **Traps:** assert-without-looking; fail-open gates; test fakes have signatures
  (widening a seam silently vacuates old fakes).

## 7. Immediate next action
Run **Phase A (the audit)** — read-only — and produce `docs/audit_cut_list.md`
with the three buckets, evidence per item. Then the owner signs off on Bucket 1
before any deletion.
