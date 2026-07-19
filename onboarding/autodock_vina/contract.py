"""contract.py — STAGED. Model-visible fidelity contract for the
(autodock_vina, rigid_pocket_dock) substrate. NOTHING imports this today.

Option A: enrolls calibrating/routable=False, INERT — contract_for('autodock_vina')
MUST keep raising. Additionally DEFERRED (no aarch64 build); un-defer needs an
x86 host per the card. At promotion the text moves to substrates.py as
AUTODOCK_VINA_CONTRACT.
"""

AUTODOCK_VINA_CONTRACT = """SUBSTRATE CONTRACT — autodock_vina, rigid_pocket_dock

1. WHAT THIS IS.
A molecular docking tool (AutoDock Vina): it docks a flexible ligand into a
RIGID receptor pocket within a defined search box and scores the pose with an
empirical function. FILTER-class: the docking score is a RELATIVE screen within
a GIVEN receptor+box setup — not absolute binding affinity, and not a claim that
the pose is correct.

2. TYPED INPUT.
    receptor : a baked allowlist receptor (PDBQT).
    ligand   : a baked allowlist ligand (PDBQT).
    box      : center_x/y/z + size_x/y/z (the search box).
    quantity : the QoI (the docking score).

3. REGIME (rigid_pocket_dock).
In-regime: a baked receptor+ligand, a well-formed box, a docking search with a
fixed seed. Out of regime: flexible-receptor docking, absolute-affinity claims,
non-allowlist structures.

4. WHAT IT RETURNS.
One scalar QoI — the best-mode docking score — returned ONLY when the search
converges to a valid pose (with a fixed seed for determinism). A failed or
degenerate search returns no number.

5. THE CONVERGENCE GATE AND THE KNOWN GAP (HARD).
The search converging says only that Vina ran — NOT that the setup was right.
Receptor preparation and box placement are UNVALIDATED UPSTREAM inputs the tool
cannot see: a confident, converged score on a wrongly-prepared receptor or a
mis-placed box is indistinguishable from a correct one. So the docking score is
trustworthy ONLY as a RELATIVE screen within a receptor+box a human has
validated; never as absolute affinity, and never as evidence the pose is correct.
"""
