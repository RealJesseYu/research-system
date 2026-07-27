# Memo — the remote lane: rented hardware, and why its results are inputs

**Written:** 2026-07-27. **Status:** built and offline-tested; **live proof owed**
(needs the owner's Modal account — see §5). **Rulings:** R-REMOTE-1, R-REMOTE-2.
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

## 5. Status: live proof owed

The unauthenticated path **is** proven live: with no token present, a real
dispatch attempt returns

> `setup_error: the remote backend could not be reached (AuthError: Token
> missing…) — this job could not run … no result was fabricated`

which is the honest could-not-run behaviour, naming the fix. Everything else is
offline-tested through the `dispatch` seam (15 tests).

**What is not yet proven is a job actually running**, because that needs an
account this machine does not have. The owner must, once:

1. register at modal.com;
2. run `modal token new` (browser auth — an interactive login, so it has to be
   the owner, not the agent);

after which a first live job (a CPU no-op, then a small GPU job) becomes the
witness this memo owes. Cost is per-second with free monthly credits; nothing
here spends anything until that token exists.

## 6. What this unlocks, once witnessed

`boltz2`, ESMFold, OpenFold3, Chai-1, AutoDock Vina, Evo2, Borzoi, scGPT, and
plane-wave DFT (GPAW / Quantum ESPRESSO) — the whole GPU-blocked shelf, through
one door rather than nine wrappers.

Note what does **not** change: those substrates' registry rows stay deferred and
unrouted. The capability arrives as a *shelf-style* route (agent-driven, R-LANE-1)
whose results are inputs, not as nine promotions. Un-deferring a row would mean
claiming its results are verifiable, and under R-REMOTE-1 they are not.

## 7. Open watches

- **Cost has no ceiling in code.** The timeout bounds one job; nothing bounds
  spend across a run. If the agent starts reaching for GPUs freely, a budget cap
  belongs here.
- **The template ships the caller's code to third-party hardware.** That is
  inherent to renting compute and worth stating plainly rather than burying:
  anything in a remote job's code or input files leaves this machine.
