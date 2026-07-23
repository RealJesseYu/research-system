# Handoff — freeing the agent (the purge), for a fresh session

**Written:** 2026-07-23. **Branch:** `iterate-experiment-loop`. **HEAD:** `0d666a4`.
**Suite:** 1806 passed, 1 skipped (offline). **Read this first, then start.**

---

## 0. THE PRIME DIRECTIVE (the north star — everything serves this)

**The system must be a FREE agent, and must NEVER be weaker or less autonomous
than a plain Claude chat.** A bare Fable chat, given ~5 words unattended, built a
functioning robot arm (CAD + code). If this 1000×-compute system can't match
that, that is the CARDINAL FAILURE — fix it before anything else.

- **Substrates are TOOLS. Garnish.** Used when useful, NEVER a limiter. A
  registry/contract/routing layer that *gates* the agent is a CAGE — purge it.
- **Verify claims, not tools.** Reproducibility applies to a KEPT number (record
  it so it re-runs), never to restrict which tools the agent may reach for.
- **The value is "a chat, AND MORE":** at least as capable as a bare chat, PLUS
  memory across runs + a director steering many runs + reproducible records.
  Expectation: 10,000× compute → 10,000 designs → find the best → full study +
  paper.
- **If anything subtracts freedom, DELETE it.**

This is encoded at the **top of `CLAUDE.md`** (a "PRIME DIRECTIVE" block that says
it overrides the substrate framing below) and in memory
(`substrates-are-tools-not-a-cage.md`). The owner said this MANY times across
chats and it kept not sticking — it sticks now because it's in always-loaded
context. **Do not drift back into substrate-centered thinking.**

Owner working style: **give a clear, specific debrief after EACH edit**, plus the
full mini-debrief + vision checklist at each brick close (memory
`debrief-after-each-feature.md`).

---

## 1. Where the system is NOW (the shape today)

A production run today:

> `supervisor.py --domain "<goal>"` (or a director move) → **the FREE experimenter**
> — a full agent (`FULL` profile: Bash, Read/Write, WebSearch/WebFetch, connectors
> via ToolSearch) with the **substrate-tools catalog** on the table — investigates
> the domain DIRECTLY: writes and runs code, reaches for any tool, iterates,
> verifies, saves reproducible artifacts. It writes a director-readable
> `verification.json`. **No gate-1, no stages 2-5, no registry gate.**

Wrapped in the KEPT "and more": memory, the PI **director** (`pi_agent/`, run via
`python -m pi_agent --goal "..."`), study/arc, and the paper path. The
propose/measure discipline survives as: the agent saves what re-runs a kept
number (verification where it earns its keep, never a tool gate).

**The whole static pipeline (gate-1 → stages 2-5 → fidelity gate → registry-gate)
is now DEAD CODE for production** — reachable only via `LEGACY_PIPELINE=1` (a
transitional kill-switch) or the stub-test seam. **Deleting it is the next step
(§3).**

---

## 2. What shipped this session (commit trail, oldest→newest)

The session had two phases: (A) finish Step ④ (free the entrance) + fixes, then
(B) the owner's directive to purge the substrate cage.

**Phase A — Step ④ + fixes:**
- `75ef7fc` M1: exact route default-on + Phase-A cut audit (`docs/audit_cut_list.md`)
  + M2 manifest.
- `68496cf`/`6069dfb` M2 Tier 1/2: deleted mature-exact-tool ceremony (cards,
  onboarding dirs, calibration).
- `4a23ffe` re-stamped the killrate memory-md5 pin (was owner journal drift).
- `61ca3c4` ④.1 ideation defaults to `quick` (apparatus opt-in).
- `46c0fd9` ④.2a `python -m pi_agent` CLI (the director was already built —
  `pi_agent/` — do NOT rebuild it; memory `step4-director-already-built.md`).
- `efea7ef` FIX: the director was BLIND to exact-route findings — now writes a
  director-readable `verification.json`. Live-validated: the arc COMPOUNDS
  (study-20260723T005833Z: redundancy r≈0.997 → 4 PCs → minimal subset).
- `c5b0c7c` Defects A+B: compose-agent transport retry; error-aborted runs aren't
  publishable. (Both modules later deleted in 4b — fixes are moot now but the
  design lessons live in `docs/defects_from_director_run.md`.)
- `cb45213` ④.3 de-funnel: all-exact runs skip ideation+gate-1
  (`docs/design_step4_3_defunnel.md`); bound the constraint to the experimenter
  (compose_agent used `routable_ids` → `permitted_ids`).

**Phase B — the purge (owner directive: substrates are tools, free the agent):**
- Prime directive encoded (CLAUDE.md top + memory) — the "it never sticks" fix.
- `9699baf` brick 1: `stages/free_experimenter.py` — the FREE experimenter (a
  FULL agent, no substrate limit; `run_free_investigation`).
- `7c33d0b` brick 2: routed `run_exact_route` to it (behind a flag).
- `376755d` parse tolerance: `extract_json_object` — a full agent narrates then
  emits JSON; the parser now recovers it. (Surfaced by the first live free run.)
- `368dbf7` **4a**: `run_exact_route` is ALWAYS free — deleted the caged
  composition branch + the flag.
- `895755f` **4b**: deleted the caged modules (`compose_agent.py`,
  `experiment_investigation.py`, `experiment_route.py`, `experiment_report.py`) +
  6 tests — **−1,769 lines**.
- `3fe6dcc` substrates as tools: `substrate_tools_catalog()` appended to the free
  agent's prompt (optional, with an "approximate — can be confidently wrong"
  caveat; never a gate).
- `0d666a4` **free is the default entry**: a production run goes straight to the
  free agent; the whole pipeline is dead code (`LEGACY_PIPELINE=1` kill-switch).

**Live validations (owner's Terminal, all passed):**
- Collatz free run — agent wrote/ran code, correct answer (max 350 @ 77031,
  OEIS A006577), verified, publishable.
- rdkit free run (`20260723T041424Z`) — agent read the catalog, wrote
  `from tools.run_rdkit import run_rdkit`, computed correct TPSA/MolLogP, 10/10
  verified. **Proof a free agent reaches for a substrate as a tool, ungated.**

---

## 3. THE NEXT STEP — delete the dead pipeline (the final big cut)

Free is the default; the static pipeline is dead code. Delete it. **This is the
biggest deletion and the ONLY one that touches a LOCKED schema (`schemas.py`) —
STOP-and-rule; stage it in careful sub-steps with the suite green at each.**

Candidate deletions (VERIFY each is orphaned by tracing callers first — the last
session got burned once by under-tracing; always trace, never assert):
- `stages/gate1_chooser.py` and its use in `run_relay` (the post-gate-1 payload +
  schema enforcement).
- `stages/stage2_experiment_design.py`, `stage2_spec.py`,
  `stage3_fidelity_gate.py`, `stage4_case_builder.py`, `stage4_simulation.py`,
  `stage5_thought_layer.py` — the static stages, and the `STAGES` list.
- The **registry-as-gate**: `permitted_ids`/`routable`/contracts/`vocab_for` where
  they GATE (keep `wrapper_callable` + `substrate_tools_catalog` — the free agent
  uses those; keep the wrappers as tools).
- The loop/gate machinery in `supervisor.py` (`run_gate`, `run_gate5`,
  `apply_loopback_surgery`, `MAX_LOOPBACKS`, the maturity hook) — all
  static-pipeline-only now.
- Coupled: `schemas.py` (locked — a deletion that removes `vocab_for` or the
  `substrate_id` payload key is STOP-and-rule; may be avoidable by leaving the
  schema and just not exercising it, as the free path already does).

**KEEP (do NOT delete):**
- `stages/free_experimenter.py` (the agent), `stages/verification.py` (the wall —
  `run_composition`/`verify_claim`; its own tests stay green).
- The substrate **wrappers** (`tools/run_rdkit.py`, `run_cfd.py`, …) and
  `tools/substrate_dispatch.py` `wrapper_callable` + `substrate_tools_catalog` —
  substrates-as-tools depends on these.
- `pi_agent/` (director), `memory/`, `stage6_paper.py` (paper), `stage1_ideation`
  (optional depth tool for the director).

**Order suggestion:** (i) confirm nothing production reaches the pipeline (it
doesn't — free is default); (ii) delete the stub-test seam's dependence or accept
deleting those stub tests; (iii) delete stages 2-5 + gate-1 + their tests; (iv)
strip the registry-gate; (v) resolve the `schemas.py` coupling under a recorded
ruling. Keep `LEGACY_PIPELINE` until (iii) lands, then remove it.

---

## 4. Forward work AFTER the purge (the two caveats + connectors)
- **Per-run workspace:** the free agent wrote artifacts to the REPO ROOT
  (`collatz/`, `run_tpsa_check.py`). Give it a per-run workspace
  (`runs/<id>/workspace/`) so artifacts are isolated and reproducible-in-place.
- **Controller re-verify:** `verified=True` is currently the agent's OWN re-run.
  Wire a deterministic no-model re-run of the agent's saved artifacts (the wall,
  applied to a kept number — never a tool gate).
- **Connectors (the robot arm):** wire an MCP connector (e.g. CAD) into the
  `FULL` profile so the free agent reaches for it. The SDK supports `mcp_servers`;
  a connector result becomes a KEPT result once it's a re-runnable artifact.
  This is the path to the robot-arm-class work the directive is really about.

---

## 5. Rules & guardrails (do not violate)
- **Run-venue (absolute):** full/long runs launch from a plain Terminal under
  `caffeinate`, never a builder-session background task. (Live runs are the
  owner's to launch.)
- **STOP-and-rule:** locked schemas, contracts, "ruled" inputs, trust-bearing
  deletions → record the decision first.
- **Never `git add -A`** — the tree carries owner dirty files (`CLAUDE.md`,
  `memory/journal.jsonl`, `docs/architecture_collapse_manifest.md`,
  `tests/test_campaign_controller.py`, `tests/test_scholar_search.py`,
  `docs/status_archive_bio.md`). Stage explicit paths. **`CLAUDE.md` is dirty with
  the owner's edits + the prime-directive block — do NOT commit it (the block
  loads from the working tree + memory anyway); let the owner commit it.**
- **Trace callers before deleting** (no assert-without-looking; run the full suite
  after each cut).
- **Debrief after each edit** (owner instruction).

## 6. How to resume
1. Read this file + the `CLAUDE.md` PRIME DIRECTIVE block + memory
   (`substrates-are-tools-not-a-cage`, `step4-director-already-built`).
2. `git log --oneline f62be7a..HEAD` for the trail; `venv/bin/python3 -m pytest
   tests/ -q` should show ~1806 passed.
3. Start §3 (delete the dead pipeline), sub-step by sub-step, suite green each
   time, tracing callers first.
4. Live runs (owner's Terminal): `python -m pi_agent --goal "..."` (director) or
   `supervisor.py --mode auto --domain "..."` (single free run) — both go free by
   default now.
