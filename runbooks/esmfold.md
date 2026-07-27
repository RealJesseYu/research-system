---
name: esmfold
description: Predict a protein's 3D structure from sequence alone, on a rented GPU. Fastest working folder here; no MSA, no external services.
status: WORKS
requirements: remote GPU (A10G)
---

# ESMFold — single-sequence structure prediction

The **first choice** for folding a protein here: it needs no MSA, contacts no
external service, and folded a 76-residue protein in 109 s for about four cents.
Accuracy is very good for small well-behaved proteins and degrades for large
multi-domain ones or anything whose fold depends on coevolutionary signal — for
those, an MSA-based predictor would do better, and none currently runs (see the
`boltz2` runbook).

## Invocation

Through the remote lane, `tools/run_remote_job.py`:

```python
run_remote_job({
    "code": CODE,                       # below
    "gpu": "A10G",                      # 24 GB; a T4's 16 GB is tight past ~200 residues
    "python_version": "3.12",           # transformers/torch are not on 3.14 yet
    "pip": ["torch", "transformers", "accelerate"],
    "output_files": ["esmfold.pdb"],
    "timeout_s": 3000,                  # weights are ~2.6 GB and download per run
})
```

```python
import json, torch
from transformers import AutoTokenizer, EsmForProteinFolding
seq = "MQIFVKT..."
tok = AutoTokenizer.from_pretrained("facebook/esmfold_v1")
model = EsmForProteinFolding.from_pretrained(
    "facebook/esmfold_v1", low_cpu_mem_usage=True).cuda().eval()
enc = tok([seq], return_tensors="pt", add_special_tokens=False)
with torch.no_grad():
    out = model(**{k: v.cuda() for k, v in enc.items()})
open("/work/esmfold.pdb", "w").write(model.output_to_pdb(out)[0])
plddt = float(out["plddt"][0, :, 1].mean())      # 0–1 here, not 0–100
open("/work/result.json", "w").write(
    json.dumps({"metrics": {"mean_plddt": plddt}}))
```

## What comes back

A standard PDB file, plus `mean_plddt` on a **0–1 scale** (0.905 for ubiquitin —
multiply by 100 for the usual pLDDT convention). Above ~0.85 is a confident
fold; below ~0.5 usually means the region is disordered or the model has nothing
to say, and should be reported as such rather than measured.

## Observed

Ubiquitin (1UBQ, 76 residues): mean pLDDT **0.905**, **109 s**, **$0.042** on an
A10G including the weight download. Backbone accuracy against the crystal
structure: **CA-RMSD 0.834 Å**.

## RECORDING THE RESULT

**The fold is an INPUT, never a claim** (R-REMOTE-1). It ran on rented hardware
and the wall cannot re-run it, so `mean_plddt` and anything else the model
reports must be reported with `"verified": false`, saying where it came from.

**The findings come from the structure, locally.** Bring the PDB back, embed the
coordinates you need INLINE in a self-contained artifact, and compute there —
radius of gyration, contact order, CA-RMSD to an experimental structure, buried
surface area, whatever the question wants. Those re-run in milliseconds with no
GPU and no network, and they verify. That is how a fold becomes evidence:

```python
# artifact: {"file": "fold_check.py", "quantity": "ca_rmsd_angstrom",
#            "profile": "atomistic"}
import numpy as np
PRED = np.array([...])          # CA coords from the returned PDB, inline
EXP  = np.array([...])
P = PRED - PRED.mean(0); Q = EXP - EXP.mean(0)
V, S, Wt = np.linalg.svd(P.T @ Q)
R = V @ np.diag([1, 1, np.sign(np.linalg.det(V @ Wt))]) @ Wt
metrics = {"ca_rmsd_angstrom": float(np.sqrt((((P @ R) - Q) ** 2).sum() / len(P)))}
```

## Gotchas already hit

- **pLDDT is 0–1**, not 0–100. Reporting 0.905 as "90.5% confidence" is fine;
  reporting it as "0.9 pLDDT" against a literature threshold of 70 is not.
- Weights download **every run** — containers are ephemeral. That is most of the
  109 s and most of the cost. Fold several sequences in ONE job rather than one
  job per sequence.
- `low_cpu_mem_usage=True` matters; without it the load can exceed container RAM.
