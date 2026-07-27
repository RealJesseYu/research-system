---
name: autodock_vina
description: Molecular docking — score how a ligand binds a receptor. Runs on the remote x86_64 lane; will not install locally on this Mac.
status: WORKS (remote only)
requirements: remote CPU (x86_64) — no GPU needed
---

# AutoDock Vina — molecular docking

Docking works, but **only remotely**: Vina has no aarch64 build, so it cannot
install on this machine. The remote lane rents x86_64 Linux, where `pip install
vina` succeeds. No GPU is needed — this is a CPU job, so it is cheap.

The registry row `autodock_vina` is deliberately still `routable=False`: the
capability lives here, agent-driven, not as a routed substrate.

## Invocation

```python
run_remote_job({
    "code": CODE,
    "gpu": None,                                   # CPU — do not rent a GPU
    "apt": ["build-essential", "swig", "libboost-all-dev"],
    "pip": ["vina"],
    "output_files": ["poses.pdbqt"],
    "timeout_s": 1800,
})
```

```python
from vina import Vina
v = Vina(sf_name="vina", seed=42, verbosity=0)     # SEED IT — see below
v.set_receptor("receptor.pdbqt")
v.set_ligand_from_file("ligand.pdbqt")
v.compute_vina_maps(center=[15.190, 53.903, 16.917], box_size=[20, 20, 20])
score = v.score()[0]                               # the input pose, unmoved
v.dock(exhaustiveness=8, n_poses=5)
best = v.energies(n_poses=1)[0][0]                 # kcal/mol, more negative = tighter
v.write_poses("/work/poses.pdbqt", n_poses=5, overwrite=True)
```

Both inputs must be **PDBQT**, not PDB — prepare them with Meeko/OpenBabel
first, or use already-prepared files.

## Observed

The 1iep system (imatinib in ABL kinase): `score()` **−12.513 kcal/mol**, best
docked pose **−13.286 kcal/mol** — realistic for that complex. About 98 s wall
including install.

## RECORDING THE RESULT

**The docking score is an INPUT, not a claim** — remote, and the search is
stochastic even with a seed. Report it `"verified": false`.

What CAN be a verified finding is anything you compute **locally** from the
returned poses: RMSD between the docked pose and a crystal pose, contact counts,
a ranking you derive yourself, buried surface area. Bring `poses.pdbqt` back,
embed the coordinates inline, compute in the `atomistic` shelf.

**And the honest caveat that outlives all of this:** a docking score is a
*relative screen inside a human-validated receptor and box*. It is not a binding
affinity. Comparing two ligands in the same box is meaningful; quoting one
number as "the binding energy" is not. State the receptor, the box centre and
size whenever you report one.

## Gotchas already hit

- `set_ligand_from_file` needs PDBQT; a PDB fails unhelpfully.
- **Example data paths move.** A tutorial URL that 404s looks exactly like the
  tool failing. The working files live under
  `raw.githubusercontent.com/ccsb-scripps/AutoDock-Vina/develop/example/basic_docking/solution/`
  — verify a download before blaming the tool.
- Always pass `seed=`. Without it, two identical runs disagree and nothing
  downstream is comparable.
