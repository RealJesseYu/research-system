# `dolfinx-prod` — the FEniCSx substrate container

The recipe for the container `tools/run_fenicsx.py` executes into. Naming
mirrors the siblings: `of12-prod` (CFD) / `ccx-prod` (FEA) / **`dolfinx-prod`**.

## G0 — FEniCSx, not legacy FEniCS

FEniCS is **two projects with one name**:

- **FEniCSx / DOLFINx** — the current project (`import dolfinx`). This is what
  we build on.
- **Legacy FEniCS** (`from dolfin import *`) — last released **2019**. It is
  **not installed in this image and will not run here.** Most cantilever
  tutorials on the open web are legacy code; they do not apply. If a snippet
  says `from dolfin import`, it is the wrong project.

## Image

| Fact | Value |
|---|---|
| Image | `dolfinx/dolfinx:stable` (Docker Hub; also `ghcr.io/fenics/dolfinx`) |
| Digest | `sha256:2ae4bfbc0d9077268880faf04c72750528bee986c94ab223a2c159969bd56fa8` |
| Image created | 2026-06-11 |
| Architecture | `arm64/linux` — multi-arch image, runs **natively** under colima on Apple silicon (no emulation) |
| `dolfinx.__version__` **as printed by this container** | **`0.11.0.post0`** |
| Python / petsc4py | 3.12.3 / 3.25.1 |
| Scalar type (default) | `float64` — **real mode**, which is what linear elasticity requires |

Verified from the machine, not from documentation:

```
docker --context colima exec dolfinx-prod python3 -c \
  "import dolfinx, numpy as np; print(dolfinx.__version__, np.dtype(dolfinx.default_scalar_type).name)"
# -> 0.11.0.post0 float64
```

## Create the container

```
docker --context colima pull dolfinx/dolfinx:stable

docker --context colima run -d --name dolfinx-prod \
  -v /Users/jesseyu/research-system/cases_fenicsx:/work/cases \
  dolfinx/dolfinx:stable sleep infinity
```

**One mount, deliberately:** `/work/cases` — read-write; per-run case dirs, each
holding `input.json` **and the exact `solve_cantilever.py` that consumed it**.
Evidence-class, gitignored, exactly like `cases/`, `cases_fea/`, `cases_code/`.

`run_fenicsx.py` copies the solve script into each case dir from its own
`Path(__file__).parent/fenicsx_env/`, mirroring how `run_fea.py` writes its whole
deck into the case dir: the case dir is **self-contained evidence**.

> **Why not mount `tools/fenicsx_env` read-only instead?** That was the first
> design and it was wrong. This repo is checked out as **several parallel git
> worktrees** (`research-system`, `-17D`, `-22`, `-ngspice`, …), and sibling
> sessions switch branches in the shared checkout. A mount of one tree's `tools/`
> could hand the container a *different branch's* solve script than the wrapper
> doing the calling — a silent, invisible mismatch. Copying from `__file__` is
> unambiguous: the script that runs is always the one beside the wrapper that ran.

## Real vs complex mode — the pin

The image ships both PETSc builds, switched by:

```
source /usr/local/bin/dolfinx-real-mode      # float64  <- what we require
source /usr/local/bin/dolfinx-complex-mode   # complex128
```

Real mode is the container default, **but defaults are not guarantees**, so
`solve_cantilever.py` **asserts** the scalar type is a real float at startup and
refuses to solve otherwise. The assertion is code, not hope.

**Proven by failing the escape** (2026-07-16), never by reading the config:

```
docker --context colima exec dolfinx-prod bash -c \
  'source /usr/local/bin/dolfinx-complex-mode && python3 /work/env/solve_cantilever.py /tmp/cx_input.json'
# -> FENICSX_RESULT {"ok": false, "error": "real-mode pin FAILED: dolfinx.default_scalar_type is
#    'complex128' (complex build). Linear elasticity requires the real build — source
#    /usr/local/bin/dolfinx-real-mode before solving."}
```

The same input in the default (real) mode solves and returns numbers. The check
therefore distinguishes the two states — it can fail, so its passing means
something.

## Preflight — daemon AND container

`colima` being up does **not** imply `dolfinx-prod` is up. `run_fenicsx.preflight()`
checks both and names which one failed; the wrapper returns
`valid=False, qoi=None` with that named reason rather than a generic error.

## JIT — why the first solve is slow

FEniCSx **compiles kernels on first use** and caches them (`~/.cache/fenics`
inside the container). Measured on this container, degree 2, 8×1×1:

| | in-script `solve_seconds` | wall-clock |
|---|---|---|
| **cold** (cache cleared) | 1.823 s | 2.61 s |
| **warm** | 0.024 s | 0.45 s |

~76× on solve time. The cost model publishes a cold/warm **range**, never a
single rate. The cache survives container restarts (it lives in the writable
layer); a freshly created container is cold again. Each new *kernel variant*
(e.g. the first degree-1 solve after degree-2 solves) pays its own JIT cost.
