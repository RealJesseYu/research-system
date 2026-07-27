# Memo — the remote lane: rented hardware, and why its results are inputs

**Written:** 2026-07-27. **Status:** built, offline-tested, and **LIVE-WITNESSED** (§5). **Rulings:** R-REMOTE-1, R-REMOTE-2.
`stages/verification.py` untouched, and deliberately so.

---

## 1. The gap

Five capabilities sat deferred for one reason: hardware this laptop does not
have. `boltz2` (GPU), `autodock_vina` (no aarch64 build at all), the GPU-only
model zoo, plane-wave DFT for solids. Building one wrapper per tool clears them
at one per session, forever. **This clears the class**: any tool that needs a
GPU, a different architecture, or simply more machine can run, because the
machine is rented by the second and thrown away.

## 2. R-REMOTE-1 — a remote result is an INPUT, never a CLAIM

Owner-ruled 2026-07-27, and it shapes the whole design.

The wall regenerates a number by **re-running its artifact**. Make a remote GPU
job an artifact and two bad things follow:

1. **Cost doubles.** Every verification pass bills the GPU again.
2. **Good results fail.** GPU inference is frequently nondeterministic —
   nondeterministic kernels, TF32, atomic reduction order — so a perfectly sound
   result comes back as a `mismatch` through no fault of the science.

The alternative was a tolerance band, which would have meant weakening what
"reproduced" means for the most expensive class of result in the system. That is
the wrong direction: the band would exist to accommodate the tool, not the
physics.

**So: run the expensive thing ONCE, bring its outputs back as files, compute the
findings FROM those files locally where they are cheap and deterministic.** Fold
the protein remotely, report its pLDDT as a sourced caveat; then measure radius
of gyration, contact order or interface area from the returned structure in the
atomistic shelf, and let *those* be the claims. This is the "INPUTS ARE NOT
CLAIMS" rule (R-CAGE-1 §3) applied where re-running is genuinely unaffordable.

## 3. R-REMOTE-2 — the policy is enforced by ABSENCE, not by a flag

A flag is the kind of thing a later edit flips with good intentions. So the
guarantee is structural, and there are four absences holding it up:

| Absence | Why it matters |
|---|---|
| No `remote` artifact kind in `verification.py` | the wall refuses it as `unrunnable_artifact` |
| The wrapper returns **no `qoi`** | every other wrapper returns one because every other wrapper feeds a claim; the missing field *is* the policy, at the type level |
| `verification.py` never imports it | no path exists, so none can be taken |
| No registry row | enrollment would give `wrapper_callable` a route, which is half of becoming verifiable |

`tests/test_remote_lane.py` asserts all four. They are the tests that matter
here — an absence is exactly the kind of guarantee that erodes unnoticed.

## 4. What was built

`tools/run_remote_job.py` — deterministic dispatch to **Modal** (owner's choice,
2026-07-27), the user's own account and bill.

```
run_remote_job({"code": ..., "gpu": "A10G", "pip": [...], "apt": [...],
                "input_files": {...}, "output_files": [...], "timeout_s": 900})
  -> {"valid", "metrics", "artifacts", "diagnostics", "runtime_s"}   # no qoi
```

The remote runner is a **fixed template**, the `tools/run_code.py` discipline:
the caller's code is data written to a file, never spliced into the scaffolding,
and the scaffolding alone decides how results come back. Metrics arrive through
the same `result.json` contract the local sandbox uses, so a script moves
between local and remote without changing how it reports.

Jails: a **GPU allowlist** (a typo is refused before it becomes a bill on
hardware nobody meant to rent), a bounded timeout (≤3600 s), bare-filename
checks on every input and output, and an artifact size cap. A job that runs and
fails is reported with its stderr tail and **its metrics are not passed off as
usable** — distinct from a backend that could not be reached, which is an honest
`setup_error`.

## 5. Live proof (2026-07-27)

The unauthenticated path **is** proven live: with no token present, a real
dispatch attempt returns

> `setup_error: the remote backend could not be reached (AuthError: Token
> missing…) — this job could not run … no result was fabricated`

which is the honest could-not-run behaviour, naming the fix. Everything else is
offline-tested through the `dispatch` seam (15 tests).

The owner authenticated (`modal token new`) and the lane was witnessed end to
end:

| Witness | Result |
|---|---|
| Remote CPU job | metrics `{answer: 42.0}` + a returned file, **3.9 s**. Host: `Linux-4.19.0-gvisor-x86_64` |
| Remote GPU job (T4) | `cuda_available=1.0`, **trace(I₁₀₀₀) = 1000.0** (known answer), `Tesla T4 | torch 2.13.0+cu130`, 165 s incl. first image build |
| Real model on GPU | ESM-2 (35M) top-1 prediction for ubiquitin, 102 s |
| **THE PATTERN, end to end** | the ESM prediction came back as a FILE (an input, caveated); a local self-contained artifact computed top-1 agreement with the native sequence = **1.0** and **reproduced at `rel_error 0.0`**; the same claim asserted at 0.5 was rejected as `mismatch` |

That last row is the whole ruling made concrete: the expensive, non-reproducible
step ran once on rented hardware and was never claimed; the finding derived from
it re-runs locally in milliseconds, on any machine, with no GPU and no bill.

**One fact worth its own line: the remote host is `x86_64`.** `autodock_vina`
was deferred because it has no aarch64 build — that blocker is now gone.

**One bug the first live run caught**, which no amount of offline testing would
have: Modal ships the entry point as a serialized closure and refuses a
Python-version mismatch between client and image. The image had been pinned to
3.12 against a 3.14 venv. The fix reads the version from `sys` rather than
pinning it, because a pin rots silently the day the venv moves and surfaces as a
confusing remote error instead of the local fact it is.

## 6. What this unlocks

`boltz2`, ESMFold, OpenFold3, Chai-1, AutoDock Vina, Evo2, Borzoi, scGPT, and
plane-wave DFT (GPAW / Quantum ESPRESSO) — the whole GPU-blocked shelf, through
one door rather than nine wrappers.

Note what does **not** change: those substrates' registry rows stay deferred and
unrouted. The capability arrives as a *shelf-style* route (agent-driven, R-LANE-1)
whose results are inputs, not as nine promotions. Un-deferring a row would mean
claiming its results are verifiable, and under R-REMOTE-1 they are not.

## 7. The spend gate (added 2026-07-27, owner-set $100)

`tools/gpu_budget.py`. This is the **first place in the project where a dollar
ceiling means anything** — `cost_meter.py` states outright that there is no
dollar cost per run because auth is a subscription, and `pi_agent/budget.py`
counts moves, converting a `--cost-cap` through an estimate while noting that
real spend enforcement "waits on per-run cost reporting (a later Phase-1 task)".
Rented GPU time is billed to a card by the second, so it gets a real gate rather
than an estimate.

How it accounts, and why it is pessimistic in exactly one direction:

- **Before dispatch**, a job is checked against its **worst case** — the full
  timeout at that GPU's rate — because the check must happen before the money is
  spent. A job that *might* fit is refused rather than gambled on.
- **After it returns**, the **actual** seconds are recorded — including for a job
  that failed, which still consumed the machine it crashed on. The gate refuses
  on what could happen; the ledger tells the truth about what did.

The ledger is a FILE (`memory/gpu_spend.jsonl`, append-only, the
`override_ledger.jsonl` idiom) and that is load-bearing: a campaign dispatches
runs as subprocesses, so an in-process total would reset every run and the cap
would bound nothing.

Rates are rounded UP from published per-second pricing, and an unrecognised GPU
name bills at the most expensive rate — an over-estimate refuses earlier and can
never overshoot, while a cap that silently under-counts is the failure worth
avoiding. They are not a billing record; the provider's invoice is.

**Delegation.** The ceiling reads from `RESEARCH_GPU_BUDGET_USD`, the same
environment channel as `ALLOWED_SUBSTRATES` and `CAMPAIGN_MAX_ITERS`. A director
hands a child run a slice by setting it on the subprocess — `pi_agent/budget.py`'s
allocate() idea, in dollars, across a process boundary. Unset, malformed, or
non-positive falls back to $100 rather than reading as unlimited, the same
refusal `ALLOWED_SUBSTRATES` already makes.

Live: a real remote job passed the gate, billed $0.0002, and left $99.9998.

## 8. Open watches
- **The template ships the caller's code to third-party hardware.** That is
  inherent to renting compute and worth stating plainly rather than burying:
  anything in a remote job's code or input files leaves this machine.
