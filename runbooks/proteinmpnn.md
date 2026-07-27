---
name: proteinmpnn
description: Design protein sequences for a given backbone. Runs LOCALLY on CPU in seconds — no GPU, no remote job needed.
status: WORKS (local, CPU)
requirements: local sandbox profile "biodesign"
---

# ProteinMPNN — backbone-conditioned sequence design

Give it a protein backbone, it proposes sequences likely to fold into it. It is
a ~1.7M-parameter network and runs **locally on CPU in about three seconds** —
no GPU, no rented hardware. (Its registry row still says it needs a GPU; that
was tested and is wrong. See `docs/memo_biodesign_lane.md`.)

## Invocation

The local sandbox, profile `biodesign`. Weights are baked into the image, so
there is no download and no network:

```python
run_python_experiment({
    "code": CODE,
    "quantity": "mean_seq_recovery",
    "profile": "biodesign",
    "input_files": {"bb.pdb": backbone_pdb_bytes},
})
```

```python
import subprocess, os, glob, re
home = os.environ["PROTEINMPNN_HOME"]           # /opt/proteinmpnn
subprocess.run([os.path.join(home, "protein_mpnn_run.py") and "python",
                f"{home}/protein_mpnn_run.py",
                "--pdb_path", "bb.pdb", "--pdb_path_chains", "A",
                "--out_folder", "out", "--num_seq_per_target", "8",
                "--sampling_temp", "0.1",       # low = conservative, high = diverse
                "--seed", "37",                 # SEED IT: this is how it reproduces
                "--batch_size", "1"], check=True, capture_output=True)
text = open(glob.glob("out/seqs/*.fa")[0]).read()
recs = [float(m) for m in re.findall(r"seq_recovery=([0-9.]+)", text)]
metrics = {"mean_seq_recovery": sum(recs) / len(recs)}
```

Input is a **PDB backbone** — N, CA, C, O are enough; side chains are ignored.

## What comes back

A FASTA at `out/seqs/*.fa`. The first record is the native sequence; each
subsequent one is a design with `score` (lower is better) and `seq_recovery`
(fraction matching native). Weight checksums are at
`/opt/proteinmpnn/WEIGHTS.sha256` if a run needs to state which parameters
produced it.

## Observed

Ubiquitin backbone, 4 designs at seed 37: mean recovery **0.5526**, best
**0.5658**, **~2.9 s** — and **bit-identical** across repeats at the same seed.
40–60% recovery is the ordinary band for a small natural protein.

## RECORDING THE RESULT

Unlike the remote folders, this **is directly verifiable** — it is a local
sandbox result, deterministic under a fixed seed. Record it as an ordinary
artifact:

```json
{"file": "mpnn_design.py", "quantity": "mean_seq_recovery", "profile": "biodesign"}
```

The artifact must be **self-contained**: the wall re-runs the file with no
workspace files beside it, so embed the backbone PDB INLINE as a string and
write it out at the top of the script. A 76-residue backbone is ~25 KB, well
inside the 100 KB code limit.

## The limit that matters

ProteinMPNN is a **filter, not an oracle**. High sequence recovery means "this
looks like the kind of sequence that folds into this backbone" — it does **not**
mean the design folds, is soluble, or functions. Say that whenever you report
one. To go further, fold the design back with `esmfold` and compare structures;
that round-trip is real evidence, and its RMSD half verifies locally.
