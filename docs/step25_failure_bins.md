# Step 25 — Failure-bin read

*Doc-only analysis session, 2026-07-14. Every binned item cites a run id or
on-disk artifact. Zero pipeline runs, zero live model calls were made to
produce this read — it is a pass over `memory/`, `runs/`, `harness/` reports,
and `docs/` already on disk.*

Repo state at analysis: HEAD `c52c173`, working tree clean.

---

## The five layers (the plan's bins)

- **(a) physics outside CFD entirely** — the hypothesis is about physics a
  CFD solver categorically cannot represent; no wrapper work fixes it.
- **(b) inside CFD but outside the validated envelope** — CFD *can* model it,
  but the run sits at/over the resolution or regime edge the card validates, so
  the number is a model estimate with an unvalidated residual gap.
- **(c) setup / extraction complexity** — the physics is inside the solver, but
  the **wrapper tooling** cannot build the case or extract the quantity. Fixed by
  builder/extraction engineering, *not* a new solver.
- **(d) design-stage failure** — the spec did not capture the hypothesis: a
  proxy substituted for the native quantity, a redundant/duplicate experiment,
  or numerically-unsound sweep parameters.
- **(e) fidelity-gate error** — the gate returned a demonstrably wrong verdict.

---

## Bin table — primary population (fidelity ledger + distinct journal halts)

The richest, cleanest failure signal is `memory/fidelity_ledger.jsonl`: **18
verdicts from 13 distinct runs**, all dated 2026‑07‑07 onward. Verdict mix
**13 defer / 5 refine / 0 trust**. Each row below cites its run id and the
one-line reason; a `†` marks an item that also touches a second bin (reason
stated).

### Bin (c) — setup/extraction complexity  ·  **DOMINANT · 13 items**

| # | Run id (verdict) | Blocker |
|---|---|---|
| 1 | `handfeed3-20260707T183101Z` (defer) | peak vorticity — a derived velocity-gradient field the wrapper cannot compute (∂v/∂x−∂u/∂y) |
| 2 | `20260712T194452Z` (defer) | vorticity-based sub-domain circulation ratio — derived field + sub-domain integration unsupported |
| 3 | `20260712T212952Z` (defer) | `profile_amplitude` / cosine lid BC — spatially-varying lid the builder's scalar `lid_velocity` cannot express → builder halt |
| 4 | `20260712T212952Z` (defer) | double-Gaussian `codedFixedValue` lid — non-canonical params (`profile_sigma`, `profile_peak_velocity`) the builder cannot synthesize |
| 5 | `20260713T020121Z` (defer) | central-obstacle geometry (builder halt) + enstrophy (two-step derived) |
| 6 | `validate18-T1-same1-ev1` (defer) | polar-frame radial velocity gradient — coordinate transform + spatial differentiation outside the single-shot reduction path |
| 7 | `validate18-T1-alt1-ev2` (defer) | corner-restricted secondary-eddy chord measurements — only global reductions exist |
| 8 | `validate18-T1-alt2-ev2` (defer) | closed-streamfunction contour (topological) unextractable **+** non-square geometry outside builder vocabulary → dual build+extract |
| 9 | `validate18-T2-alt1-h10` (defer) | streamfunction saddle-point topology / recirculation-region count — no supported operation resolves it |
| 10 | `validate18-T3-same1-ev1` (defer) | primary-vortex streamfunction-bounded KE fraction — spatial sub-domain decomposition unsupported |
| 11 | `validate18-T3-alt1-ev1` (defer) | offline streamfunction reconstruction + saddle-point contour masking |
| 12 | `20260714T152314Z` (defer, pass 2) | corner-masked *bulk* minimum pressure — spatial masking of field files; contract offers only whole-domain reductions **[= demand-ledger entry #1]** |
| 13 | `20260706T090043Z` (journal `learned_summary`) | `postProcess max` on `U` returns velocity magnitude, not a component; need a vorticity function-object or verified U_y extraction |

### Bin (b) — inside CFD, outside/at the edge of the validated envelope  ·  7 items

| # | Run id (verdict) | Concern |
|---|---|---|
| 1 | `20260712T194452Z` (refine) | in-envelope `min(Ux)`, but mesh-independence **not** claimed; corner vortices under-resolved at Re=1000 †(d): admitted proxy for secondary-vortex emergence |
| 2 | `20260713T020121Z` (refine) | 64×64 marginally under-resolved vs Ghia et al. 129×129; the trust-critical −0.35 threshold sits exactly where mesh error bites |
| 3 | `validate18-T1-same2-ev2` (refine) | in-envelope `min(Ux)` at **untested resolution**, a proxy for vortex strength †(d) |
| 4 | `validate18-T2-same1-h5` (refine) | numerically-predicted field approximates but does not measure; QoI `volAverage|U|` is **further a proxy** for primary-vortex circulation †(d, proxy) |
| 5 | `20260714T152314Z` (refine, pass 1) | `min(p)` on a marginal 64×64 mesh dominated by the mesh-dependent lid-corner pressure singularity (envelope card §4G) |
| 6 | `20260714T152314Z` (defer, pass 3) | global `min(p)` is a non-mesh-convergent corner-singularity artifact — cleanly extractable but faithfully represents *no* physical minimum †(c): masking would be needed to escape it |
| 7 | `20260713T020121Z` (journal `ev2`) | `|min(Ux)|` superlinear in Re — "run a finer mesh at Re=1000 to firm up the absolute threshold" |

### Bin (d) — design-stage failure  ·  primary items

| # | Evidence | Failure |
|---|---|---|
| 1 | anomaly scanner §(b): identical QoI `volAverage(mag(U))` = 0.416835 **and** 0.193007 across `handfeed4-20260704T083221Z` **and** `handfeed4-20260706T045314Z` | the **same experiment executed twice** — duplicate design (induced Rule 7) |
| 2 | π-sweep (spec-level): **20 specs** flagged with a duplicate-Re point (raw: 48 pairwise) | redundant sweep points at the same Re — the same experiment declared twice within one spec |

*(The proxy notes †(d) on bin-(b) rows 1/3/4 are design-shortfalls too — a
substrate-servable proxy substituted for the hypothesis-native quantity — but
each is binned primary (b) because the recorded verdict's decisive concern was
resolution/model-gap, not the proxy.)*

### Bin (a) — physics outside CFD entirely  ·  **0 items**

No item in any source is a hypothesis CFD categorically cannot touch. Every
blocker is instrument-fit *within* fluid dynamics (can't-build, can't-extract,
under-resolved) — not a domain mismatch. This zero is itself a finding: the
system has never yet been *asked* something a CFD solver is the wrong tool for.

### Bin (e) — fidelity-gate error  ·  **0 observed (but undetectable today)**

No case shows the gate returning a demonstrably wrong verdict. This zero is
**weak**: `harness/gate_bets_report.json` records `n_resolved=0`,
`cumulative_brier=null` — all 18 gate bets are unresolved, so there is no
ground-truth-labeled outcome against which a gate error *could* be caught. We
cannot yet distinguish "the gate is never wrong" from "we have no way to see
when it is." (See the induced-rules review note on R6.)

### Totals

| Bin | Count (primary population) |
|---|---|
| (a) physics outside CFD | 0 |
| (b) outside validated envelope | 7 (5 refine + 1 defer + 1 journal) |
| **(c) setup/extraction complexity** | **13 (12 defer + 1 journal) — DOMINANT** |
| (d) design-stage failure | 2 primary (+3 proxy secondaries in (b)) |
| (e) fidelity-gate error | 0 observed / undetectable |

**Dominant bin: (c) setup/extraction complexity.** Twelve of the eighteen
fidelity-ledger verdicts, plus a distinct journal halt, are the wrapper being
unable to build a case or extract a derived/masked field — engineering the
existing solver's tooling, never a new solver.

### Aggregate advisory flags (never killed a run)

Two offline scanners contribute population-level flags. They are **advisory**
(the π-gate `pi_enforce_verdict` is wired nowhere; the anomaly scanner "is a
scanner, not a judge"), so they are kept separate from the verdict rows above:

- **π-gate sweep** (`tools/pi_gate.py` recompute over 41 specs): 33 flag / 8 pass;
  20 specs duplicate-Re → bin (d); 15 specs high-Courant → bin (c)/(d) numerics.
- **Anomaly scanner** (`tools/anomaly_scan_report.md`): `max_Courant` outliers
  ~0.60 (`handfeed4-20260704T083221Z_run1`, `handfeed4-20260706T045314Z_run1`) →
  numerics; residual outliers ~1e-5 on the higher-Re sweep runs
  (`20260706T063330Z` runs 2–3, `handfeed4-20260706T075137Z_run3`) — shapes to
  watch, not failures (those runs converged).

### Outside the five physics layers — operational / pre-design halts

Kept out of the bins deliberately (they are not experiment-fidelity failures):

- `20260712T194452Z` — colima/Docker daemon down → honest run halt (infra).
- `20260706T054646Z` — Stage-5 SDK "max turns" exception → harness crash
  (Step-16 fix territory).
- `20260712T212952Z` — killed externally mid-pass-3 (launch-venue error; the
  run-venue rule is now absolute).
- `20260706T052837Z` and 17‑D `same2` — Stage-1 **zero-survivor** halts (all
  hypotheses judged known at filter): ideation-novelty failures, upstream of any
  experiment design.

---

## Composition — the honesty note (the read is Stage-1/2/3-heavy)

The failure population must not be oversold as "executed experiments went
wrong." Counted from disk:

| Milestone | Run dirs |
|---|---|
| Total run directories | 183 |
| Reached experiment design (Stage-2 spec) | 57 |
| Reached the fidelity gate (Stage-3 verdict) | 60 |
| Reached Stage 4 (results.json) | 33 |
| — of which `skipped_defer` | 20 |
| — of which `halted_synthesis` | 7 |
| — **of which actually executed the solver** | **6** |

So **only 6 run directories ever ran the CFD solver** (`20260706T063330Z`,
`20260713T020121Z`, `handfeed4-20260704T083221Z`, `handfeed4-20260706T045314Z`,
`handfeed4-20260706T075137Z`, `validate18-T2-same1-h5`). The 18 fidelity-ledger
verdicts come from 13 runs, and **12 of the 18 are extraction/build defers
decided at the fidelity gate *before any solver ran*.** The anomaly scanner's
numeric families rest on ≤7 data points each.

**What this means for the read:** it characterizes *what the instrument refuses
at design/fidelity time* far more than *what executed experiments revealed*. Bin
(c)'s dominance is a statement about the fidelity gate's most common output on
this one narrow substrate — a real and useful signal, but a design-time signal,
not an execution-time one. Treat the (b)/(d) evidence, which needs runs that
actually executed, as thinner still.

---

## π-count reconciliation (Lane-2 CLI sweep vs Lane-3 digest recompute)

Two π-gate tallies were reported and looked contradictory:

- **Lane-2 CLI sweep:** flag = 31; Courant-warns = 31; duplicate-Re = 48 pairwise.
- **Lane-3 digest recompute** (`_pi_sweep_lines`, `tools/meta_induce.py`):
  flag = 33, pass = 8; 20 duplicate-Re; 15 Courant.

**This is not a bug.** Re-running both counters over the *current* on-disk
population (`runs/**/spec.json`, 41 specs, 0 parse errors) reproduces **both**
sets exactly:

```
specs globbed: 41   parse_errors=0
verdicts: flag=33 pass=8
SPEC-LEVEL   (Lane-3 unit): duplicate-Re specs = 20   Courant specs = 15
RAW OCCURRENCE (Lane-2 unit): duplicate-Re pairwise = 48   Courant point-warns = 31
```

Two independent differences were stacked on top of each other:

1. **Counting unit (the Courant/duplicate gap).** `_pi_sweep_lines` counts each
   *reason pattern once per spec* — it normalizes away the numbers and adds a
   `seen_here` de-dup set, so a spec whose 4-point sweep warns on every point
   contributes **1** Courant count, and a spec with several duplicate pairs
   contributes **1** duplicate count. The Lane-2 CLI reported **raw
   occurrences**: every point-level Courant warning (31) and every pairwise
   duplicate detection (48). Same 41 specs, same reasons — 15 vs 31 and 20 vs 48
   are `per-spec` vs `raw`, and both are correct under their own definition.

2. **Population drift (the flag gap, 31 → 33).** The Lane-2 CLI ran at the
   LANE2 commit over a *smaller* spec set; the Lane-3 recompute ran later, after
   the 7/14 additions (`20260714T152314Z`'s passes among them), so two more
   specs were present to be flagged. The raw occurrence totals (31 / 48) did not
   move, so the two added flagged specs flagged on grounds other than new
   high-Courant / duplicate-Re points.

**Canonical numbers going forward.** Report the **spec-level** counts as the
headline — they answer "how many *designs* have this problem," the
decision-relevant unit, and they are what the committed `_pi_sweep_lines` digest
emits: **41 specs, 33 flag / 8 pass, 20 with a duplicate-Re, 15 with a
high-Courant point.** Keep the **raw occurrence** counts (48 duplicate pairs, 31
point-warnings) as the *within-spec severity* detail, always labeled "raw." Do
not mix the two units in one sentence again.

---

## Advisory — what the read says the SECOND SOLVER (Step 27, FEA) is *for*

*(Advisory only; the ruling is the strategist's.)* On this evidence the second
solver's primary justification is **proving generalization, not buying new
reach.** Bin (a) is empty and bin (e) is undetectable; the dominant, well-evidenced
failure mode is bin (c) — twelve extraction/build defers on a *single* narrow
substrate (`cavity_2d`). That population cannot tell us whether "can't
build / can't extract" is a `cavity_2d`-wrapper limitation or a systemic one,
nor whether the envelope-card + fidelity-gate + onboarding machinery is actually
substrate-agnostic as the architecture claims. A second (substrate, regime) pair
is the experiment that answers both: it exercises the onboarding recipe end to
end on something new, and it finally gives the router a real choice so an
instrument-fit defer can be *re-routed* instead of dead-ended. FEA does also add
genuine new physics reach (solid-mechanics hypotheses CFD cannot touch — the
first real bin-(a) territory), but that is the secondary dividend; the urgent,
disk-backed reason to add it is to test that the recipe generalizes. Lead with
generalization; bank new-reach second.
