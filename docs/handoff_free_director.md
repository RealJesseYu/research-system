# Handoff — Free Director / Manager-of-Managers (+ cross-run file hand-off)

**Session:** 2026-07-24/25. **Branch:** `iterate-experiment-loop`.
**Commits:** `b96f436` (build) + `157745c` (workspace-confinement fix), on top of `45306a5`.
**Status:** built, tested (1503 tests collect green), **live-validated on real Opus**, committed.
**Read alongside:** `docs/free_director_plan.md` (the plan + rulings R-FD-1..5, the authoritative record) and `CLAUDE.md` (PRIME DIRECTIVE + invariants).

---

## 0. TL;DR — what a new session needs to know first

The **director became a true manager**. Before this session `pi_agent/decider.py` was a reactive
four-verb chooser (`run_single`/`run_campaign`/`run_fan`/`stop`). Now there is a **free director**:
a FULL agent in a loop with an **open action space**, one of whose actions is spawning *another*
free director — recursion, i.e. the "manager of managers." It decomposes a goal into subsystems,
optimizes each on a **provably-bounded budget slice**, and **joint-verifies** the assembly. It was
built **alongside** the enum director (ruling R-FD-1); the enum path is untouched and still the
default. Additionally, **cross-run file hand-off** lets a child sub-study hand a *file* (sequence,
alignment, dataset, structure) to a parent integration — the file travels as its **reproducible
producer recipe, never as bytes**, so the verification core needed **zero changes**.

**Nothing here is a moonshot to continue** — the architecture is done and proven. Remaining work
is deferred/parked items and one merge step (see §7). **Do not rebuild what exists** (assert-
without-looking is this project's cardinal sin).

---

## 1. Architecture — how a run flows

```
python -m pi_agent --director free --goal "..." --max-moves N   (or --cost-cap $)
  └─ free_investigate()  [pi_agent/free_director.py]  — the director loop, in the FOREGROUND
       repeat until budget spent / decision cap / director stops:
         decide_action()  [pi_agent/free_decider.py]  — one Opus call, OPEN action space
         act on it:
           run_experiment          → dispatch a real run (subprocess) → free experimenter + wall
           spawn_sub_investigation  → allocate a budget slice → a CHILD free_investigate (recursion)
           call_integration         → dispatch a run that ASSEMBLES the verified parts + files
           call_{ideation,validation,data_analysis} → optional tools (pi_agent/capabilities.py)
           read_memory / write_memory → cross-study memory (write uses a distinct kind, R-FD-5)
           stop
       write studies/<id>/report.json
```

**Key invariants preserved at every depth:**
- **The measurement boundary is a law, not a stage.** A number of record comes from a tool +
  verification, never the director's narration. Only VERIFIED findings bubble up from a child;
  only reproduced file PRODUCERS cross a run boundary.
- **Budget provably bounds the whole tree.** `pi_agent/budget.py` — `allocate(k)` *transfers*
  moves to a child (never copies), so the sum across the tree = the root total, partitioned; plus
  a `MAX_DEPTH=5` backstop. Termination is provable.
- **Optional tools are optional.** ideation / validation / data-analysis are actions the director
  *may* choose; nothing forces them.

---

## 2. Modules (all NEW unless noted)

| File | Role |
|---|---|
| `pi_agent/budget.py` | Divisible move budget (conserved, provably terminates). `Budget`, `from_cost_cap`. |
| `pi_agent/free_decider.py` | The director's brain: open action space + validator + `decide_action`. Opus, FULL. |
| `pi_agent/free_director.py` | `free_investigate()` — the loop, budget integration, capability routing, integration branch, report. |
| `pi_agent/capabilities.py` | Optional-tool executors: ideation, validation, data-analysis, spawn (recursion), read/write memory. |
| `stages/reusable_artifacts.py` | Cross-run file hand-off gate: `validate_reusable_artifact` (reproduction), `structural_errors`, `as_producer_step`. |
| `pi_agent/__main__.py` (mod) | CLI: `--director {enum,free}`, `--max-moves` **or** `--cost-cap`. |
| `pi_agent/loop.py` (mod) | Enum loop; gained per-run cost aggregation + `ceiling` provenance. |
| `pi_agent/dispatch.py` (mod) | `RunResult` gained `cost` + `reusable_artifacts`; reads them from disk. |
| `pi_agent/study.py` (mod) | `parent_study_id` (tree link); arc carries cost + reusable_artifacts; `study_scratch_dir`. |
| `pi_agent/decider.py` (mod) | Enum decider; workspace-confined (the fix). |
| `supervisor.py` (mod) | Writes per-run cost into the run_record. |
| `stages/free_experimenter.py` (mod) | May declare `reusable_artifacts` (file + producer), gated post-call. |
| `stages/generation_strategies.py` (mod) | Raw ideation pool 10 → **25** (15/1/5/4). |

Tests: `test_budget.py`, `test_free_director.py`, `test_free_director_e2e.py`, `test_capabilities.py`,
`test_reusable_artifacts.py` (new) + additions to `test_pi_cli/dispatch/loop`, `test_free_experimenter`.

---

## 3. Rulings (recorded; do not re-litigate — see `docs/free_director_plan.md` §2)

- **R-FD-1** — free director built ALONGSIDE the enum one; purge the enum only after full live validation.
- **R-FD-2** — moves are the enforced ceiling; `--cost-cap` derives moves via `RESEARCH_EST_COST_PER_MOVE_USD` (default 5.0, a placeholder — calibrate from real spend).
- **R-FD-3** — children return VERIFIED artifacts, never narration.
- **R-FD-4** — decomposition is emergent-first (no explicit dependency DAG until a real run needs it).
- **R-FD-5** — `write_memory` writes a distinct `director_note` journal kind, NEVER `learned_summary` (that channel is md5-pinned by the kill-rate battery; a distinct kind can't poison it). `read_memory` reads both.

**Design keystone (cross-run hand-off):** a file crosses a run boundary as its **reproducible
producer recipe**, inlined into the parent's composition — never as stored bytes. Because a
composition re-runs every step, verifying the parent re-runs the child's producer. The verification
engine is **unchanged**.

---

## 4. What is live-validated vs offline-only

**Live-validated on real Opus (evidence on disk, re-derived not narrated):**
- Flat path — a single-experiment goal, clean stop (`study-20260724T041913Z`).
- Recursion + integration — a 3-subsystem sorting study → integrate → verified numeric recommendation (`study-20260725T010625Z`).
- **Cross-run file hand-off** — a bio study: 2 children each produced a reproducible file, both bubbled, integration regenerated each from its producer and computed a verified joint CAI (`study-20260725T015607Z`). Confirmed from `free_investigation.json` / `report.json`, not the summary text.

**Offline-only (proven by tests, not yet live):**
- The `--cost-cap` → moves conversion with a *calibrated* number.
- `call_ideation` / `call_validation` / `call_data_analysis` executors firing live (structurally wired + unit-tested; a live goal hasn't exercised them yet).
- The **workspace-confinement fix** (§6) — offline-tested (the director's tool cwd is confined); "no strays after a live run" is proven only on the next live outing.

---

## 5. How to run it

```bash
# flat / simple goal
caffeinate -i venv/bin/python3 -m pi_agent --goal "..." --director free --max-moves 3

# decomposition (phrase the goal "as separate sub-studies … then integrate")
caffeinate -i venv/bin/python3 -m pi_agent --goal "..." --director free --max-moves 6

# spend cap instead of a move count (calibrate the estimate first)
RESEARCH_EST_COST_PER_MOVE_USD=0.7 caffeinate -i venv/bin/python3 -m pi_agent \
  --goal "..." --director free --cost-cap 20
```

Evidence to read after a run: `studies/<id>/report.json` (arc, termination, `total_spend`,
`budget_final`), `studies/<id>/decisions/decide*.json` (the director's reasoning trail),
`runs/<id>/verification.json` and `runs/<id>/free_investigation.json` (wall-verified numbers +
reusable artifacts).

**RUN-VENUE RULE (absolute):** live/long runs launch from a plain Terminal under `caffeinate`,
never a builder-session background task. Live outings are the owner's, not a builder job.

---

## 6. Known issues / watch items

- **Workspace confinement (fixed, awaiting live confirmation).** Director-layer FULL agents used to
  write scratch files to the repo root — this produced stray `*.py` and once an empty `harness.py`
  that shadowed the `harness/` package and broke ~92 tests. Fixed by `study_scratch_dir` +
  `agent_workspace` (commit `157745c`). **After the next live run, `git status` at repo root should
  show no new stray files** — if it does, the fix missed a call site.
- **25-hypothesis pool re-baselines the ideation apparatus.** Reflection reviews every candidate, so
  per-run generation+review cost is ~2.5× the old pool=10; the locked kill-rate baselines were at 10.
- **Free-text findings don't verify.** A recommendation returned as a bare string ("mergesort") fails
  the wall (only numeric artifacts reproduce); the director learned to re-express it as a numeric
  argmin. Expected behavior, worth knowing.

---

## 7. Task board for the next session

**Actionable now:**
- **FAST merge gate + merge to `main`** — the FAST gate makes live calls, so it is owner-triggered.
  Run it green before merging `iterate-experiment-loop`.
- **Confirm the workspace fix live** — any live run + `git status` (see §6).

**Deferred (expand-on-evidence — do NOT build blind):**
- **Case-build R-ART-6** — the last in-run file-emit gap; needs a live emitting CFD-class substrate.
- **Dependency-DAG scheduling** — only if a real run shows emergent ordering thrashing (R-FD-4).

**Parked by owner:**
- **Meta-loop** — mission → self-generated goals → studies → memory → next goal (the "level 6"
  fully-autonomous layer; recursion one level above the director). `read/write_memory` is the
  prerequisite and is built. Owner said hold off.

**Last by design:**
- **Connectors** — drop an `mcp_servers.json` in; a connector result is already just another
  re-runnable artifact the free agents handle. No code change expected.

**Calibration (minor):** set `RESEARCH_EST_COST_PER_MOVE_USD` from real spend (data point: the
sorting run's experiments ran ~650k tokens each).

---

## 8. Discipline (do NOT break)

- **Never `git add -A`.** The tree carries the owner's uncommitted WIP (`CLAUDE.md`, `memory/*.jsonl`,
  `tests/test_campaign_controller.py`, `tests/test_scholar_search.py`, and various root files). Stage
  only files you changed, by explicit path.
- **Verification purity** — no model in the verification path; a kept number/file re-runs from its recipe.
- **STOP-and-rule** — changing a contract, a locked schema, or a "ruled" input is a decision to record;
  preserve superseded fixtures append-only.
- **Run-venue rule** — see §5.
- **Substrates are TOOLS, never a cage** (PRIME DIRECTIVE, `CLAUDE.md`).
