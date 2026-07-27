---
name: chai1
description: Structure prediction with Chai-1 — handles complexes and ligands, unlike ESMFold. Slower, and its embedding download is unreliable.
status: WORKS (with one flag)
requirements: remote GPU (A10G)
---

# Chai-1 — structure prediction, including complexes

Reach for this over `esmfold` when the question involves **more than one chain,
or a ligand** — Chai-1 handles complexes and small molecules, which ESMFold
cannot. For a single protein chain, ESMFold is faster, cheaper and (on the one
case measured here) more accurate.

## Invocation

```python
run_remote_job({
    "code": CODE,
    "gpu": "A10G",
    "python_version": "3.12",
    "pip": ["chai_lab"],
    "output_files": ["chai.cif"],
    "timeout_s": 3000,
})
```

```python
from pathlib import Path
from chai_lab.chai1 import run_inference
Path("in.fasta").write_text(">protein|name=chainA\nMQIFVKT...\n")
run_inference(fasta_file=Path("in.fasta"), output_dir=Path("out"),
              num_trunk_recycles=3, num_diffn_timesteps=200,
              seed=42, device="cuda:0",
              use_esm_embeddings=False)     # <- see the gotcha below
```

The FASTA header is `>ENTITY_TYPE|name=CHAIN_ID` — `protein`, `ligand`, `rna`,
`dna`. One record per chain; that is how you fold a complex.

## What comes back

**Five** ranked structures as mmCIF at `out/pred.model_idx_{0..4}.cif`, plus
score files. `pred.model_idx_0.cif` is the top-ranked one. Note these are CIF,
not PDB — parse the `_atom_site` loop, or convert.

## Observed

Ubiquitin: 5 structures in **154 s**, CA-RMSD to the crystal structure
**1.665 Å** — a good fold, though twice ESMFold's error on the same protein.
Some of that gap is probably the ESM-embeddings flag below.

## RECORDING THE RESULT

Identical to `esmfold`: **the fold is an INPUT** (R-REMOTE-1), reported with
`"verified": false`. Bring a CIF back, extract the coordinates you need, embed
them inline in a self-contained local artifact, and compute the finding there
where it verifies. See the esmfold runbook for the Kabsch/RMSD pattern.

## Gotchas already hit

- **`use_esm_embeddings=True` triggers a 5.7 GB download that failed here**
  mid-transfer (`ChunkedEncodingError: IncompleteRead`, 1.6 GB of 5.7 GB). With
  `False` the run completes and needs no external download at all. The accuracy
  cost is real but unmeasured here — if a fold matters, try `True` first and
  fall back, and SAY which you used.
- Output is **mmCIF, not PDB**, and there are five of them. Do not silently
  average or silently take the first without saying so.
- Weights download every run (ephemeral containers). Fold several targets in one
  job if you have several.
