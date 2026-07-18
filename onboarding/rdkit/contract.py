"""contract.py — STAGED. The model-visible fidelity contract for the
(rdkit, descriptor_computation) substrate. NOTHING imports this today.

Option A enrollment (owner-ruled 2026-07-18): at D.2 this substrate enrolls
`calibrating` / `routable=False` and is INERT — its contract is NOT in
tools/substrate_registry.py `_CONTRACTS`, and `contract_for("rdkit")` MUST keep
raising LookupError until a D.4 promotion ruling. This file is where the
contract text lives until then; at promotion it moves to substrates.py as the
constant `RDKIT_DESCRIPTOR_CONTRACT` and is wired into `_CONTRACTS`, exactly as
NGSPICE_LINEAR_PASSIVE_CONTRACT did at the R2 flip (never a pasted copy — one
runtime source of truth).

The value below is the five-section runtime contract a fidelity gate would
judge a descriptor spec against. It is prose-for-a-model; it enters no composed
prompt today (grep-verifiable: nothing imports this module).
"""

RDKIT_DESCRIPTOR_CONTRACT = """SUBSTRATE CONTRACT — rdkit, descriptor_computation

1. WHAT THIS IS.
A deterministic cheminformatics calculator (RDKit) that computes 2D molecular
descriptors from a single small molecule supplied as a SMILES string. It is an
ANSWER-class instrument: the descriptor it returns IS its exact computed output
for the parsed molecule, not a prediction or an estimate. It runs no model, no
simulation, and no experiment.

2. TYPED INPUT.
    smiles   : the molecule, a SMILES string RDKit can parse AND sanitize.
    quantity : which descriptor to return, one of the fixed allowlist below.
The molecule as written is the parameterization; there is no separate parameter
dictionary. A SMILES that does not parse-and-sanitize under RDKit's own valence
model yields no number.

3. REGIME (the (substrate, regime) card unit — descriptor_computation).
In-regime: a valid, sanitizable, single small organic molecule, and a
descriptor on the fixed allowlist (2D graph/constitution descriptors only:
MolWt, ExactMolWt, HeavyAtomCount, NumHDonors, NumHAcceptors,
NumRotatableBonds, TPSA, MolLogP, NumAromaticRings, RingCount, FractionCSP3,
NOCount). Out of regime, by construction: any ML-PREDICTED property (solubility,
ADMET, activity), any 3D/conformer-dependent quantity, reactions, or a
descriptor outside the allowlist. These are rejected or unrepresentable, not
approximated.

4. WHAT IT RETURNS.
One scalar QoI — the requested allowlist descriptor for the molecule — plus a
bounded diagnostic string. It never returns a raw structure, a descriptor for an
unparseable molecule, or a non-finite value.

5. QoI EXTRACTION AND THE ONE KNOWN GAP.
The QoI is the named descriptor, computed deterministically (identical SMILES ->
identical value). THE KNOWN GAP (uncheckable by the gate): a computed descriptor
is a PROXY for a molecular property, never a measured one. In particular MolLogP
is Crippen's COMPUTED logP, not an experimental logP; TPSA is a topological
estimate of polar surface area, not a measured one. Trust the number as RDKit's
exact computation of that descriptor; do NOT read it as an experimental
measurement of the underlying physical property.
"""
