# --repeats on the calibration battery + the sampling-parameter trace (step16.6)

Session 2026-07-16. HEAD parent 8ca77a5, era-of-record 862531b. ZERO
model-visible changes: this is a harness-level loop only; touched files are
`harness/`, `tests/`, `docs/`. `stages/`, `supervisor.py`, `substrates.py`,
`schemas.py`, `model_call.py`, `cost_meter.py` are byte-identical to era
862531b before and after.

## Why this session exists

The C13 steerability probe (`harness/probe_c13_steerability_20260716T043257Z.json`,
run 2026-07-16T0432Z) drew cell **P-0 — byte-identical to slate C13 — three
times and returned `['trust', 'defer', 'refine']`. One of each. Maximum
entropy on identical input.** P8 (C13 reproduces trust on ≥2/3) is FALSIFIED.

Consequence: **the fidelity gate is stochastic, and every fidelity measurement
in this project is n=1 on a stochastic instrument** — the 18-verdict ledger,
the 21 calibration verdicts, the Brier point predictions, the Step-21
contradiction trigger. None has ever been repeated. R-REP-1 authorizes
`--repeats` so a verdict can be drawn N times and reported as a distribution.

## Step 1 — sampling-parameter trace (REPORTED; nothing changed)

Path traced from `calibration_battery.run_gate_case` →
`model_call.call_stage_model` → `_transport_with_retry` → `_invoke_transport`
→ `asyncio.run(_ask_once(...))` → `claude_agent_sdk.query`.

**(a) Is temperature / top_p / top_k / seed set anywhere on this path?**
NO. `_ask_once` builds `ClaudeAgentOptions(model, system_prompt,
allowed_tools=[], disallowed_tools=..., setting_sources=[], max_turns=1)`.
No sampling field is set — none appears anywhere on the path.

**(b) If unset — what is the default, and is it even EXPOSED?**
It is **not exposed by this transport at all.** `dataclasses.fields(
ClaudeAgentOptions)` has NO `temperature`, `top_p`, `top_k`, or `seed`
field (full field list checked live). The transport is the **Claude Code
CLI**, not the raw Messages API — corroborated by the `cli_path` option field
and by the battery's own transport errors ("Claude Code returned an error
result: Reached maximum number of turns (1)"). Sampling defaults live inside
that CLI/server and are not surfaced to the Python caller. There is an
`extra_args` escape hatch for arbitrary CLI flags, but no sampling flag is
passed and none is part of the documented option surface.

Deeper finding, sharper than P16 anticipated: **temperature is not merely
un-pinned — it is unreachable from here.** Setting it would require a
transport change, a new session, and its own ruling. The stochasticity cannot
be configured away from this layer.

**(c) Could a repeat be a cache replay rather than an independent draw?**
NO. The reports show `cache_read_input_tokens` (~180–227k) and
`cache_creation_input_tokens` — this is Anthropic **prompt caching**, an
INPUT-side optimization that reuses processed input tokens; it does not replay
outputs. The direct proof is the probe itself: **P-0 returned three DIFFERENT
labels on byte-identical input.** If outputs were served from cache all three
would be identical. `--repeats` therefore draws independently. Confirmed: no
sampling parameter was set or changed.

## Step 2 — `--repeats N` (gate cases only)

- Applies to **gate cases only.** Wrapper-behavior cases are deterministic
  zero-model-call validation; repeating them measures nothing. They run ONCE
  at any N. Proven by `test_wrapper_cases_run_once_regardless_of_repeats`
  (wrapper validator invoked exactly `n_wrapper` times at repeats ∈ {1, 5}).
- Each repeat is an **independent call**: `run_gate_case` (UNCHANGED — the
  probe imports it) is invoked once per draw, each building a fresh
  `stage_input` through `call_stage_model`'s isolated session
  (`setting_sources=[]`, `max_turns=1`, no `session_id`/`resume`/
  `continue_conversation`). No shared context between repeats. Proven by
  `test_repeats3_is_independent_draws_per_gate_case` (exactly 3×n_gate
  invocations).
- Per gate case recorded: `raw_verdicts` (ordered list), `distribution`,
  `unanimous`, `modal_verdict` (ties broken by canonical VALID_LABELS order —
  reader-stable, NOT a claim the mode is "the" verdict), `n_in_band` /
  `in_band_fraction`, `entropy_bits`, and every full `draws` record.
- **Not collapsed to a point.** Spread measure = **Shannon entropy in bits**
  (base 2: 0.0 = unanimous, 1.0 = even 2-way, log2(3)=1.585 = maximal 3-way).
  Honest small-N caveat baked into the docstring: at N=3 only three
  distributions exist (0.0 / 0.918 / 1.585), so entropy here is an ORDINAL
  flag reported *beside* the raw distribution, never in place of it.
- **Backward compatible.** `--repeats` defaults to 1 and reproduces the
  pre-R-REP-1 report shape byte-for-byte: top-level `n_repeats` and all
  per-case distribution machinery appear ONLY at repeats>1. Proven by
  `test_repeats1_report_shape_is_backward_compatible` and a live structural
  diff against last night's on-disk code report (gate keys, case-record keys,
  hook-witness keys, cost outer keys all identical; the only delta is empty
  token buckets, an artifact of the zero-call fake).
- **One report per launch.** All N×cases draws land in ONE per-launch
  timestamped file — no per-repeat file naming, so no collision across
  repeats (Step-18 no-shared-mutable-state).
- Confusion + hook witness at repeats>1 are computed over ALL draws (every
  draw is an observation; rows sum to n_draws, annotated in the report and the
  printout).

## Step 3 — the calibration ledger under repeats (R-CAL-3 holds)

**Decision: the atomic ledger entry is ONE DRAW, not one case-with-a-
distribution.** Derivation: the ledger is append-only observation evidence; a
draw IS the observation, a distribution is DERIVED by a reader from the draws.
Storing a distribution as the atomic entry would (1) duplicate derivable data,
(2) fight the existing draw-oriented schema (the `repeat` field the probe
already writes 0..N-1), and (3) make the 21 legacy single-draw entries
incommensurable with new entries. The owner's lean (one row per draw) is
**correct and already the probe's established convention** — confirmed, not
corrected.

- The 21 legacy battery entries (`repeat=null`, two batch_ids
  `20260716T013008Z` FEA / `20260716T013014Z` code) are legitimate single
  draws and are **kept, not deleted.**
- **How a future reader tells repeats=1 from repeats=3:** group on
  `(source, batch_id, case_id)` and count rows — 1 row = single draw
  (repeat null for legacy seeds, or 0 for a new repeats=1 seed); 3 rows
  (repeat 0,1,2) = a 3-repeat batch. `n_repeats` also appears at the report
  top level for repeats>1.
- `seed_from_battery_report` now handles both report shapes: old shape → one
  entry per case, `repeat=null` (byte-identical to legacy seeding); new shape
  → one entry per draw, `repeat=0..N-1`. Idempotency key extended to
  `(batch_id, case_id, repeat)`.
- **Fidelity/override ledgers stay 0/0.** The battery is LEDGER-SILENT (never
  calls a ledger writer during a run); it brackets the production
  fidelity/override counts and records the delta, and the exit code goes RED
  if either is non-zero. Unchanged this session.

## Step 4 — corrected cost from disk (owner said "63 calls, ~6 minutes")

From last night's reports:

| battery | repeats=1 wall | calls | s / gate case |
|---|---|---|---|
| FEA  | 179.9 s | 10 | **17.99** |
| code | 60.5 s  | 11 | **5.50**  |

At **repeats=3** (gate draws ×3; wrapper cases unchanged, 0 calls):

| battery | draws | est. wall | est. min |
|---|---|---|---|
| FEA  | 30 | 30 × 17.99 ≈ **540 s** | ≈ 9.0 min |
| code | 33 | 33 × 5.50  ≈ **182 s** | ≈ 3.0 min |
| **both** | **63** | **≈ 722 s** | **≈ 12 min** |

**Calls (63) were right; time was wrong.** The owner used code's 5.5 s/call
rate for both (63 × 5.5 ≈ 347 s ≈ 6 min). FEA is ~3.3× slower per call
(longer envelope text), so the real estimate is **≈12 min, not 6.** Serial,
per the run-venue rule.

## Launch (printed, NOT run — plain Terminal, `caffeinate -i`, lid open, serial)

```
caffeinate -i venv/bin/python3 harness/run_harness.py --mode calibration --substrate calculix_cantilever_fea --repeats 3
caffeinate -i venv/bin/python3 harness/run_harness.py --mode calibration --substrate code_sklearn_eval --repeats 3
```
