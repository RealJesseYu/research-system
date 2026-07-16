# `ngspice-prod` — the linear-passive circuit substrate

Container recipe and build notes for `tools/run_ngspice.py`. Mirrors the
`of12-prod` (OpenFOAM) and `ccx-prod` (CalculiX) pattern: a long-lived container
with a bind-mounted cases directory, driven by `docker exec` from a deterministic
Python wrapper with no AI inside it.

## Build and run

```sh
# from the repo root, on the colima context
docker --context colima build -t ngspice-img:latest tools/ngspice_env

docker --context colima run -d --name ngspice-prod \
  -v /Users/jesseyu/research-system/cases_ngspice:/work/cases \
  ngspice-img:latest sleep infinity
```

The image is `ngspice-img`; the long-lived container is `ngspice-prod`. That
split matches the `of12-img`/`of12-prod` and `ccx-img`/`ccx-prod` convention.

## Measured environment (not assumed — read from the running container)

| what | value |
|---|---|
| `ngspice --version` | `ngspice-42 : Circuit level simulation program`, Compiled with KLU Direct Linear Solver, Creation Date `Sun Mar 31 20:15:14 UTC 2024` |
| dpkg version | `42+ds-3build1` |
| `uname -m` | `aarch64` (host is macOS + colima on Apple silicon) |
| base image | `ubuntu:24.04` (noble) |

Ubuntu noble ships ngspice 42, so the default recipe needed no pinning, PPA, or
build-from-source. **Arch note:** the container is `aarch64`. Reference figures
taken on `x86_64` agree at pattern level (monotone convergence, marker text) but
not in the last digits — see the debrief and
`onboarding/ngspice_linear_passive/selfcheck_evidence.json` for numbers measured
*here*.

## Preflight

`run_ngspice.preflight()` checks **the daemon AND the container**, because
`colima` being up does not mean `ngspice-prod` is up, and the two want different
human actions. It returns `None` when ready, otherwise an honest reason string;
`run_ngspice()` calls it before every solve and returns `valid=False` with that
reason rather than surfacing an opaque `docker exec` error.

**This is a deliberate deviation from the sibling wrappers.** `run_cfd.py`,
`run_fea.py` and `run_code.py` do **not** preflight — they discover a down
daemon or a stopped container as a generic exec failure. Flagged for ruling:
either the siblings should gain the same check, or this one should drop it.

## Files here

| file | what it is |
|---|---|
| `Dockerfile` | the `ngspice-img` recipe |
| `README.md` | this file |
| `build_ngspice_docs_index.py` | fetches/extracts the v42 manual and builds the TF-IDF docs index (offline, zero embedding calls) |
| `selfcheck_runner.py` | regenerates the self-check evidence under `onboarding/ngspice_linear_passive/` |
| `vv_sources.md` | V&V reference inventory for the later card session |

Two of these (`build_ngspice_docs_index.py`, `selfcheck_runner.py`) are placed
here rather than in `retrieval/` or `onboarding/` respectively — see each file's
docstring for the reason. Both are flagged in the session debrief.

## Docs index

```sh
curl -sL https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf -o /tmp/ngspice-42-manual.pdf
# sha256 ac745b5e7a38abcdb1b000356045d3525020c097a803e99a3faa9d8349f72a7e
venv/bin/python3 tools/ngspice_env/build_ngspice_docs_index.py --extract /tmp/ngspice-42-manual.pdf
```

Manual **v42**, title page self-declares "Version 42 (ngspice release version)",
December 27th 2023 — an exact match to the container binary. **Zero version
skew** (contrast the FEA card's docs-v2.23 vs solver-v2.17). 737 PDF pages →
733 text pages → 701 indexed pages → 2018 chunks → **0 embedding calls**.

The corpus carries extracted *text*, not the PDF, so re-indexing needs no
PDF-reading dependency — the same reasoning `build_fea_docs_index.py` records
for carrying HTML.

## Self-check evidence

```sh
venv/bin/python3 tools/ngspice_env/selfcheck_runner.py
```

Writes `onboarding/ngspice_linear_passive/selfcheck_evidence.{json,md}`. Every
reference value is computed by the wrapper's own analytic functions from the
same numbers the netlist carries — nothing is hard-coded, so a wrong wrapper
makes these checks fail rather than agree with a frozen constant.

Runs in well under a minute total; ngspice solves of these circuits take
milliseconds and are FAST checks.
