# Memo — a heavy lane through the verification sandbox

**Date:** 2026-07-26. **Status:** designed + minimal implementation landed
(profile mechanism); everything heavier is evidence-gated with named wake
conditions. **Trigger:** none yet — no run has hit the sandbox ceiling. This
memo exists so that when one does, the answer is a one-line table edit instead
of an architecture debate.

## 1. The problem, stated narrowly

The verification wall (`stages/verification.py`) re-runs every kept code
artifact in the ephemeral sandbox (`tools/run_python_experiment.py`):
`--network=none`, `--read-only`, 4 GB memory, 2 CPUs, 300 s default budget,
image `code-img:latest` (numpy/scipy/sklearn/pandas only). Right for cheap
checks — and the free experimenter is already instructed to make its artifacts
cheap: search at full scale in its own workspace, then save a **small,
deterministic winner-recheck file** as the artifact. So the sandbox only ever
re-runs one evaluation per claim, not a search.

The gap: when that *one* evaluation is genuinely heavy (a real FEA solve in
Python, a physics rollout), the re-run that would confirm a legitimate result
dies at 300 s or 4 GB, or the import it needs isn't in the image. The claim is
then reported `rerun_failed` — verification obstructing execution, the exact
failure mode the tolerance ruling of 2026-07-25 fixed for numeric drift.

A fact that shrinks the problem: heavy **substrate** runs already have their
own lanes — `run_fea.py` (ccx-img, 600 s), `run_cfd.py` (of12, 600 s) — with
their own timeouts, and the wall re-runs those through the substrate branch
untouched. The gap is only heavy **model-authored code** artifacts.

A second fact, found while investigating: the wall never passes `timeout_s` at
all. `rerun_artifact` calls `run_python_experiment({"code", "quantity"})`, so
even the wrapper's existing 1800 s ceiling was unreachable from verification —
every re-run was pinned to 300 s. Any fix must make the budget travel **with
the artifact**, or it does not exist where it matters.

## 2. Decision: a second profile, not raised defaults

Raising the defaults was considered and rejected:

* The default lane's tightness is a feature. A hung or runaway recheck script
  should die in 5 minutes, not 30 — verification runs on every kept claim, and
  a study keeps many.
* "One evaluation is heavy" is the rare case by design (the search-outside/
  verify-winner instruction). The rare case should pay its own cost, declared,
  not tax every claim.
* A declared profile is **recorded in the artifact**, so the re-run conditions
  are part of the claim's record — same reasoning as the declared `tolerance`
  field: a knob that travels with the claim and is clamped by code, never a
  global loosening.

So: a fixed, code-owned **profile table** in `run_python_experiment.py`, and an
optional `"profile"` field on the typed input and on code-bearing artifacts.

## 3. What a profile may and may not control

**Structurally outside the table** (shared invariant flags, not per-profile
values — a profile *cannot* express a weakening):

* `--rm`, `--network=none`, `--read-only`, `--pids-limit`, tmpfs `/tmp`.
  No-network and no-persistence are why verification means anything; they are
  not knobs.
* The structural metric gate, the SIGALRM in-container budget enforcement, the
  hardcoded-constant tripwire, the artifact-byte caps — all unchanged, all
  profile-independent.

**Inside the table** (resource geometry only):

| profile   | image           | default budget | max `timeout_s` | memory | cpus |
|-----------|-----------------|----------------|-----------------|--------|------|
| `default` | code-img:latest | 300 s          | 1800 s          | 4 GB   | 2    |
| `heavy`   | code-img:latest | 1800 s         | 3600 s          | 6 GB   | 4    |

Numbers and their reasons:

* **Memory 6 GB, not 16.** The colima VM is 8 GiB total (measured:
  `docker info` reports 7.7 GiB usable). 6 GB leaves headroom for the daemon
  and the host-side wrapper. A bigger cap is a *VM resize* decision (colima
  `--memory`), which is an owner call about the machine, not a wrapper default
  — the table makes it a one-line follow-up when that happens.
* **CPUs 4** = the whole VM. Fine for the heavy lane's premise: one evaluation
  at a time, on demand. (Thread-count-dependent float reduction order is a
  real determinism caveat, but it is *per-profile constant* — a heavy claim
  re-runs at cpus=4 every time. Cross-environment drift vs the agent's local
  original run is already what the declared-`tolerance` band covers.)
* **Budget 1800 s default / 3600 s max.** 30 min covers a serious single FEA
  solve or rollout on 4 cores; 1 h is the honest ceiling for "verify on every
  kept claim" on this machine. A single evaluation beyond that belongs on a
  bigger host — a separate decision, see §6.
* **Same image, deliberately.** No new image is built today (no run has needed
  one). `code-img` is a frozen, card-backed measurement surface; when a run
  actually needs a library it lacks, the wake action is to build a **new**
  pinned sibling image (`code-heavy-img`, the exact scipy-img precedent:
  pattern reused, image never mutated or derived) and flip the `heavy` row's
  image field. One line here, one Dockerfile there, defaults untouched.

## 4. How the profile travels (the determinism story)

The agent declares it **on the finding's artifact**, next to `quantity`:

```json
"artifact": {"file": "recheck_winner.py", "quantity": "tip_deflection_mm",
             "profile": "heavy"}
```

* `free_experimenter._finding_artifact` passes it through to the wall's
  artifact shape (`workspace_file` / `code`).
* `rerun_artifact` (code + workspace_file branches) and the composition step
  runner pass it to the sandbox spec. Composition code steps and
  reusable-artifact producers may carry it the same way — one read site each,
  same field name.
* The wrapper validates it against the table; an unknown profile is a
  `PythonExperimentInputError`, which verification converts to an
  `unrunnable_artifact` verdict — a malformed claim fails loudly, it never
  crashes the pass and never silently falls back to `default`.
* Because the profile is *in* the artifact, the re-run — today's and any
  future reader's — executes under the same recorded geometry. Nothing about
  what "reproduced" means changes: same bit-exact default tolerance, same
  clamped declared-tolerance band, same tripwires.

Cost containment: the profile only raises *ceilings*. A heavy re-run of a
600 s artifact takes 600 s, not 1800. The one real cost risk — an agent
declaring `heavy` on everything, making every wall pass slow — is a prompt
matter (the instruction says: only when the recheck genuinely needs it), and
if abused it shows up immediately as slow verification, not as a wrong number.

## 5. GPU: refused for now, with reasons that are facts

* This host cannot do it: colima on macOS has no GPU passthrough. There is no
  flag to add.
* Even on a host that could, GPU floating-point (atomics, cuDNN autotuning)
  breaks the wall's bit-exact default; a GPU lane needs a determinism story
  first (fixed seeds, deterministic-kernels mode, a declared tolerance as the
  norm rather than the exception). That is a design decision to make when a
  real run demands a GPU — recorded here so it isn't re-litigated from
  scratch.

## 6. Wake conditions (the evidence gates, named)

1. **A live claim fails `rerun_failed` on timeout or OOM under `default`** →
   the agent should have declared `profile: "heavy"`; if it did and heavy
   also failed, revisit the heavy row's numbers (and only then the VM size).
2. **A live claim needs an import absent from code-img** → build
   `code-heavy-img` (pinned, sibling, never derived from code-img), flip the
   heavy row's image field, record resolved versions like scipy_env does.
3. **A single legitimate evaluation needs > 1 h or > 6 GB** → that is a
   host-capacity conversation (bigger VM or a remote runner), not a wrapper
   edit; the profile table is where its outcome lands.
4. **A run genuinely needs GPU** → §5's determinism design happens first.

## 7. What was implemented now (minimal)

* `tools/run_python_experiment.py`: the `PROFILES` table; optional `profile`
  field validated against it; per-profile timeout bounds, memory, cpus, image.
  Invariant jail flags factored so no profile can touch them. Default-profile
  calls are behavior-identical to before (same flags, same bounds).
* `stages/verification.py`: `profile` passed through in the `code`,
  `workspace_file`, and composition code-step lanes; `PythonExperimentInputError`
  converted to `ArtifactError` so a bad profile is an unrunnable artifact, not
  a crash.
* `stages/free_experimenter.py`: `_finding_artifact` passes `profile` through;
  one prompt sentence telling the agent the re-run sandbox's default budget and
  that a genuinely heavy single-evaluation artifact may declare
  `"profile": "heavy"` — sparingly.
* Tests: profile validation, bounds, flag construction (including the
  invariant that every profile's flags contain `--network=none` and
  `--read-only`), verification pass-through, unknown-profile verdict, and a
  live heavy-lane smoke run (skipped when the image is absent).
