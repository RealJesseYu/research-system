---
name: boltz2
description: DOES NOT RUN HERE. Recorded so nobody spends another hour and dollar finding out. Use esmfold or chai1 instead.
status: BROKEN — do not use
requirements: remote GPU
---

# Boltz-2 — does not currently run

**Do not reach for this.** It is recorded here precisely because it looks
attractive (current, handles ligands and affinity) and fails only after several
minutes of downloads on a paid GPU. Someone already spent that; you do not have
to.

Use **`esmfold`** for a single chain, or **`chai1`** for complexes and ligands.

## How far it gets, and where it stops

Everything works up to the model's own kernels: the package installs, weights
and CCD data download, the MSA path runs, the model loads, and the first layers
execute. Then:

```
File ".../boltz/model/layers/triangular_attention/primitives.py", line 202
    return triangle_attention(q, k, v, tri_bias, mask=mask, scale=scale)
TypeError: triangle_attention() got an unexpected keyword argument 'kv_lengths'
```

A **version skew between `boltz` and `cuequivariance-ops`** — Boltz calls
NVIDIA's kernel with an argument the installed kernel version does not accept.
Upstream packaging, not a defect in this system's lane.

## What was already tried (all of it failed; do not repeat)

| Attempt | Result |
|---|---|
| `pip install boltz`, default invocation | `ModuleNotFoundError: cuequivariance_torch` — needs the CUDA extra |
| `boltz[cuda]` + `cuequivariance-torch` + `cuequivariance-ops-torch-cu12` | reaches the `kv_lengths` TypeError above |
| `--use_msa_server` | `api.colabfold.com` timed out; boltz then exits **0 having written nothing**, so check for output files rather than trusting the exit code |
| `>A\|protein\|empty` (single-sequence, no MSA) | removes the MSA dependency cleanly — worth keeping if boltz is ever revived |

## To revive it

Find a `boltz` / `cuequivariance-ops-torch-cu12` version pair whose
`triangle_attention` signatures agree, pin both, and re-run the ubiquitin case;
a working fold should land near 1 Å CA-RMSD against 1UBQ. Until then this
runbook stays `BROKEN`.
