# Memo — the atomistic lane, and the route decision behind it

**Written:** 2026-07-27. **Status:** built, live-proven, suite green.
**Rulings:** R-LANE-1, R-LANE-2. No locked schema changed; the sandbox jail is
untouched.

---

## 1. The gap this closes

The system could look up what is known about a molecule or a material and could
not **compute** anything about one. Twenty-one enrolled substrates and not a
single atomistic simulator: four narrow-regime physical solvers (CFD, two FEA,
SPICE), a CAS, cheminformatics descriptors, a metabolic LP, two sequence
algorithms, a general code sandbox — and nothing that could evaluate an
electronic structure, run a trajectory, or relax a crystal.

That is the difference between a research assistant and a researcher.

## 2. The route decision (R-LANE-1)

Adding a tool has three possible routes, and picking the wrong one is how this
project accumulated a shelf of deferred substrates:

**Route A — full substrate.** Registry row, contract, envelope card,
calibration battery, adapter, QoI vocabulary, run-entry constructor, maturity
rung. **Reserved for instruments that can converge to a confidently WRONG
number** — approximate physical simulators, where re-running faithfully
reproduces the wrong answer and only a fidelity judgment catches it. This is
what all that machinery was built for and the only thing worth paying it for.

**Route B — a sandbox shelf.** A deterministic tool that installs here. It goes
in an image; agent-authored code drives it; results verify by the ordinary
re-run because they are ordinary code artifacts. No registry ceremony at all.

**Route C — remote compute.** GPU, licence, or wrong architecture. Not built
yet; it is the next brick.

**R-LANE-1: the atomistic tools take Route B, and Route A does not grow.** The
four Route-A simulators the project owns are enough of that class; what they
need is regime expansion, not company. Everything new goes B or C. This is the
manifest's own ruling (*"a code/connector/deterministic tool needs only 'record
it so it re-runs'"*) applied rather than restated.

## 3. What was built

`tools/atomistic_env/` — a pinned image, `atomistic-img`, and two profile rows.
That is the entire change surface. The `PROFILES` table's own comment
anticipated it: *"a bigger image is built as a pinned SIBLING (the scipy-img
precedent) when a run actually needs it, and only this table's image field
changes."*

The shelf, one tool per layer of theory plus the hub that makes them compose:

| Package | Layer |
|---|---|
| **ASE** 3.29.0 | the orchestration hub — structures, optimizers, MD drivers, file formats |
| **PySCF** 2.14.0 | electronic structure (HF, DFT, MP2, CC) |
| **OpenMM** 8.5.2 | classical molecular dynamics |
| **pymatgen** 2026.5.4 | crystal and materials structure |
| **RDKit** 2026.3.4 | molecular structure and cheminformatics |

**R-LANE-2: a profile is (shelf × geometry).** Both geometries are offered
against the new shelf — `atomistic` mirrors `default`'s resources,
`atomistic-heavy` mirrors `heavy`'s. Only the image differs, and a test asserts
that factorization so one lane's resource decisions cannot drift from the
other's.

**The jail did not move.** `--network=none`, `--read-only`, `--pids-limit` and
the tmpfs are invariant flags living outside the profile table, so no entry can
express a weakening. A new shelf is a new set of libraries, never new powers.
`tests/test_heavy_profile.py`'s invariants loop over *every* profile, so these
two were covered the moment they existed — the design working as intended.

Two smaller decisions worth recording. Threads are pinned to 1 in the image
(`OMP_NUM_THREADS` and friends): a library that silently spawns a thread per
core makes wall clock — and sometimes floating-point reduction order — a
function of the host, which verification would then report as
irreproducibility. And the build *imports the whole shelf and exercises
OpenMM's platform registration*, so a broken wheel fails the build rather than
the first experiment that reaches for it.

## 4. Live proof (2026-07-27)

Every one of these ran inside the sandbox, through `run_python_experiment` with
`profile: "atomistic"`:

| Check | Result |
|---|---|
| PySCF — H₂ RHF/STO-3G at 0.74 Å | **−1.1167593 Ha**, the textbook value, in 1.2 s |
| OpenMM — harmonic bond displaced 0.05 nm from equilibrium | **1.2500000 kJ/mol** vs an analytic 1.25 |
| ASE — Cu fcc, EMT relaxation to fmax 0.01 | converged, energy per atom returned |
| pymatgen — CsCl-type cubic lattice, symmetry analysis | **space group 221** (Pm-3m), correct for that structure |
| Image build self-check | `ase 3.29.0, pyscf 2.14.0, rdkit 2026.03.4, openmm platforms ['Reference', 'CPU']` |

**And through the wall**, which is the property that matters: a
`workspace_file` artifact carrying `"profile": "atomistic"` re-ran under
`verify_claim` and reproduced −1.1167593073964253 at `rel_error 0.0`; the same
claim asserted at −1.5 came back `mismatch`. An atomistic result is a kept
number by exactly the same mechanism as any other code artifact — no new
verification path, no exception.

## 5. The physical-approximation caveat (the B\* category)

Some Route-B tools are **deterministic but physically approximate**: a force
field, a basis set, a DFT functional, an ML interatomic potential. They re-run
perfectly and can still be confidently wrong about the system they were pointed
at. Reproduction does not touch that, and nothing here pretends otherwise.

This is the one place the fidelity gate earns its keep outside CFD, and the
experimenter's prompt now says so directly: *"a force field, a basis set or a
functional reproduces perfectly and can still be the wrong physics for your
system, so say which you chose and why it suits the question."* Prose is the
current answer; a fidelity check firing on this class is the structural one,
and it is not built.

## 6. Finding: the ProteinMPNN defer is wrong

Recorded here because it came out of the same session and changes the plan.

`tools/run_proteinmpnn.py` and its registry row defer the tool because
*"ProteinMPNN is a neural model needing a GPU + downloaded weights; no GPU on
this aarch64 host."* Anthropic's own Claude Science runbooks declare
`requirements: [gpu]` on every biomodel skill **except** ProteinMPNN,
LigandMPNN and SolubleMPNN — the MPNN family carries no GPU requirement.

Tested directly: ProteinMPNN, official repo, CPU-only container, ubiquitin
(1UBQ, 76 residues) → **two designs in 1.4 s**, sequence recovery **0.5263** and
**0.5658**, which is the ordinary band for ubiquitin.

**What that settles and what it does not.** It refutes the stated reason for the
defer: no GPU is needed. It does **not** satisfy the row's own un-defer
requirement, which asks for pinned official weights with a recorded checksum
plus a known-answer validation run. So the row is deliberately **left alone**
here — flipping a trust-bearing registry row on a 1.4-second smoke test is
precisely the discipline this project has. The finding is recorded so the
un-defer can be done properly, and it should be: protein design is available on
this hardware today, which the plan of record said it was not.

## 7. What is next

- Build the wrapper for the MPNN family properly and un-defer it (§6).
- A second shelf for engineering — CadQuery, CoolProp, MuJoCo, scikit-rf —
  covering mechanical and electrical design the same way.
- **Route C, remote compute.** The largest single unlock: it clears the whole
  GPU-blocked shelf at once instead of one tool at a time.
- Regime expansion on the four Route-A simulators, last, and only when a real
  study demands turbulent flow or a nonlinear structure.
