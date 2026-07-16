# `scipy-img` — resolved versions (captured from the BUILT IMAGE)

> **Provenance: `pip freeze` run inside `scipy-img:latest`, 2026-07-16.**
> Every number below was read off disk from the built image, never copied from a
> prompt or a manifest. `tools/scipy_env/requirements.txt` states the *intent*
> (`sympy==1.14.*`, `scipy==1.18.*`, numpy left to the resolver); THIS file is
> the record of what actually shipped, and it is what the envelope card's §1
> Identity table cites.

## Capture commands (reproducible)

```
docker --context colima build -t scipy-img:latest tools/scipy_env
docker --context colima run --rm --network=none scipy-img:latest pip freeze
docker --context colima run --rm --network=none scipy-img:latest python -c \
  "import sys,sympy,scipy,numpy,mpmath; print(sys.version)"
```

## Resolved set

| Package | Resolved version | How it got here |
|---|---|---|
| Python | **3.12.13** | base image `python:3.12-slim` |
| `sympy` | **1.14.0** | pinned `sympy==1.14.*` — the Regime-A substrate itself |
| `scipy` | **1.18.0** | pinned `scipy==1.18.*` — cross-check arm ONLY (Regime B queued) |
| `numpy` | **2.5.1** | **resolver-selected**, not pinned; satisfies scipy 1.18's `numpy>=2.0.0` |
| `mpmath` | **1.3.0** | transitive dependency of sympy (its arbitrary-precision backend) |

Raw `pip freeze` output, verbatim:

```
mpmath==1.3.0
numpy==2.5.1
scipy==1.18.0
sympy==1.14.0
```

## Image facts

| Field | Value |
|---|---|
| Tag | `scipy-img:latest` |
| Manifest-list digest | `sha256:f1531c11bb6475d066d5a2d9e2ae49890353968ef9fd7205c91f5dbd3fcb6826` |
| Image ID (short) | `f1531c11bb64` |
| Size | **593 MB** |
| Docker context | `colima` |
| Base | `python:3.12-slim` |

## Why a NEW image, and not `code-img`

`code-img` is **frozen** — it sits behind a signed card (`docs/envelope_card_code_sklearn_eval.md`)
and a ruled 14-case slate, making it a model-visible measurement surface. Beyond
that governance fact, two independent *technical* blockers make reuse impossible,
and both were confirmed against the resolved set above rather than assumed:

1. **Python.** `scipy 1.18` supports Python 3.12–3.14. `code-img` is `python:3.11-slim`.
2. **NumPy.** `scipy 1.18` requires `numpy>=2.0.0`; the resolver selected **2.5.1**.
   `code-img` pins `numpy==1.26.4`.

The *pattern* is reused (pinned base + one deterministic build step + ephemeral
`docker run --rm` jails); the *image* is not.

## Base-choice note

`python:3.12-slim`, the lowest rung scipy 1.18 supports. Chosen for maximal
prebuilt-wheel availability and to match the repo's conservative-base habit.
No compiler is needed at build time (all four resolve to prebuilt `cp312`
manylinux wheels); jobs get **no network at runtime**.

## Cross-check arm — live sanity probe (this session)

`scipy.integrate.quad` was exercised inside the image to confirm the cross-check
arm is functional before the wrapper leaned on it:

```
scipy.integrate.quad(lambda x: x*sin(x), 0, pi)
  -> (3.141592653589793, 3.487868498008632e-14)
```

The second element is quad's own **error ESTIMATE, not a bound** — the wrapper
carries it as `quad_abserr_estimate` and the card says so in §5 and §8.
