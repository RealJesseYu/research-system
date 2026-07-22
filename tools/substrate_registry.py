"""
substrate_registry.py — STEP 28: the substrate maturity registry.

A typed, code-authored table of every substrate the system knows about, and
how far each one has climbed the trust ladder. This is the single source of
truth the supervisor consults before it lets a fidelity "trust decision"
(a trust/refine verdict) route to real execution.

THE MATURITY LADDER (low -> high), for routable substrates:
    calibrating  -- a card exists / a battery is being assembled, but the
                    substrate has not earned unattended trust. Not routable
                    by default; AMENDED by ruling R3 (owner, 2026-07-17): a
                    calibrating substrate whose battery has run MAY be ruled
                    routable — every trust decision touching it stays
                    human-required via the supervisor's maturity hook
                    (NEEDS_HUMAN_SIGNOFF; auto-mode trust/refine downgrades
                    to defer), so it is never silently trusted.
    provisional  -- real runs are accruing and the wrapper behaves, but the
                    calibration is not complete (e.g. cavity_2d_cfd: real runs
                    accruing, mini-21 pending). Routable, but a trust decision
                    that touches it is human-required (see the supervisor hook).
    mature       -- calibration complete; trust decisions may proceed
                    unattended. NO substrate is 'mature' today.

web_search sits in its OWN class, retrieval-provisional, deliberately OUTSIDE
the routable ladder: it is a retrieval source that is structurally never
trusted alone, so it is never routable and never the target of a trust
decision.

changes only by recorded ruling — maturity and routable are trust-bearing
facts. Editing a row (promoting a rung, flipping routable) is a governance
act: it happens by editing THIS file under a recorded ruling, never at
runtime, never from a prompt, never inferred from a run. That is why the
table is plain Python data and not read from a mutable store.

Registration-for-routing of the FEA and code substrates is a SEPARATE future
ruling; enrolling them here as calibrating/unroutable does NOT authorize the
pipeline to route to them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from substrates import (
    CALCULIX_CANTILEVER_FEA_CONTRACT,
    CAVITY_2D_CONTRACT,
    COBRAPY_FBA_CONTRACT,
    FENICSX_CANTILEVER_ELASTIC_CONTRACT,
    HOMOLOGY_SEARCH_CONTRACT,
    MAFFT_CONTRACT,
    NGSPICE_LINEAR_PASSIVE_CONTRACT,
    PYTHON_EXPERIMENT_CONTRACT,
    RDKIT_DESCRIPTOR_CONTRACT,
    SYMPY_SYMBOLIC_EXACT_CONTRACT,
)

# --- maturity rungs -------------------------------------------------------
CALIBRATING = "calibrating"
PROVISIONAL = "provisional"
MATURE = "mature"
# web_search's own class — outside the routable ladder, never trusted alone.
RETRIEVAL_PROVISIONAL = "retrieval-provisional"

# The routable ladder, low -> high. RETRIEVAL_PROVISIONAL is intentionally NOT
# a member: a retrieval source is not on the execute-and-trust path at all.
MATURITY_LADDER = (CALIBRATING, PROVISIONAL, MATURE)

# The one and only maturity a trust decision may proceed on unattended.
TRUSTWORTHY = MATURE

# --- instrument class (Phase 3, R-ROUTE-1; docs/memo_phase3_routing.md) -----
# Whether a substrate is an EXACT tool (deterministic: re-running IS the check,
# with no unresolved model-to-reality gap in the quantity it reports) or an
# APPROXIMATE physical/statistical instrument that can converge to a
# confidently WRONG number — the only class for which the fidelity gate earns
# its keep (manifest §1). This is a structural fact upper layers READ; they
# never branch on a substrate_id. It is trust-bearing, so it changes only by a
# recorded ruling, exactly like maturity/routable.
EXACT = "exact"
APPROXIMATE = "approximate"
INSTRUMENT_CLASSES = (EXACT, APPROXIMATE)


@dataclass(frozen=True)
class SubstrateRecord:
    """One row of the registry. Frozen: a runtime caller can read it but can
    never mutate a trust-bearing fact in place."""

    substrate_id: str
    wrapper: str
    card_path: str
    maturity: str
    routable: bool
    cost_tier: str
    notes: str
    # A declared per-substrate ROLE (D.1a, owner-ruled 2026-07-18): a
    # reproducibility-anchor / frozen-fixture substrate is the golden
    # known-correct case whose model-visible surfaces are byte-frozen and used
    # as the era drift-guard. Generic logic that would grow a model-visible
    # surface (e.g. threading the substrate contract into the thought layer)
    # opts the anchor OUT by reading THIS property — never by a substrate-NAME
    # branch. Opt-in, default False: a new substrate is never an anchor until
    # declared one under a recorded ruling.
    frozen_anchor: bool = False
    # The instrument class (Phase 3, R-ROUTE-1). Defaults to APPROXIMATE — the
    # fail-SAFE direction: the failure mode we refuse is SKIPPING the fidelity
    # gate on something that needed it, so a substrate is treated as
    # confidently-wrong-capable until it is explicitly declared EXACT under a
    # ruling. Only a substrate whose reported quantity cannot be confidently
    # wrong (re-running fully catches any error) is marked EXACT.
    instrument_class: str = APPROXIMATE

    def __post_init__(self):
        # Fail loud at import if a record carries an unknown class — a
        # trust-bearing fact is never silently accepted (frozen dataclass, so
        # this validates without mutating).
        if self.instrument_class not in INSTRUMENT_CLASSES:
            raise ValueError(
                f"substrate {self.substrate_id!r} has instrument_class "
                f"{self.instrument_class!r}, not one of {INSTRUMENT_CLASSES}")


# The registry itself. Order is the enrollment order and is preserved by
# all_substrates(). changes only by recorded ruling (see module docstring).
_REGISTRY: tuple[SubstrateRecord, ...] = (
    SubstrateRecord(
        substrate_id="cavity_2d_cfd",
        wrapper="tools/run_cfd.py",
        card_path="docs/envelope_card_cavity2d.md",
        maturity=PROVISIONAL,
        routable=True,
        cost_tier="low",
        notes=(
            "real runs accruing, mini-21 pending; first-enrolled routable "
            "substrate (sole-routable note retired at the R2 flip, owner "
            "2026-07-17)"
        ),
        # THE FROZEN REPRODUCIBILITY ANCHOR (D.1a, owner-ruled 2026-07-18):
        # cavity is the golden known-correct case; its stage-5 model-visible
        # turn is byte-frozen (tests/fixtures/d0/thought_user_turn.txt) as the
        # era drift-guard, and it needs a grounded validation instruction least.
        # This declared property — not its name — is what excludes it from
        # contract-threading. No other substrate is an anchor.
        frozen_anchor=True,
    ),
    SubstrateRecord(
        substrate_id="calculix_cantilever_fea",
        wrapper="tools/run_fea.py",
        card_path="docs/envelope_card_calculix_cantilever.md",
        maturity=CALIBRATING,
        routable=True,
        cost_tier="low",
        notes=(
            "battery executed 2026-07-16 (30/30 gate draws in-band at 3 "
            "repeats, 9/10 cases unanimous, hook witnessed 16/16 "
            "zero-silent-trust, wrapper self-checks 5/5 — harness/"
            "calibration_calculix_cantilever_fea_20260716T053643Z.json; "
            "first single-repeat pass 10/10 — harness/"
            "calibration_calculix_cantilever_fea_20260716T013008Z.json); "
            "F1-F4 RULED + card provisionally signed (owner, 2026-07-15); "
            "routable=True RULED Packet B Phase 2 (owner 'start phase 1' "
            "pair unit + R-B-1 + the Phase-2.0 ruling line, build chat "
            "under the owner's standing delegation, 2026-07-17: "
            "StaticSmallDeflectionRegime shape, option R1), maturity "
            "CALIBRATING unchanged — every trust decision human-required "
            "via the maturity hook until a separate maturity ruling. A "
            "spec both cantilevers serve stops loudly at selection under "
            "R-B-1 — never a silent enrollment-order pick."
        ),
    ),
    SubstrateRecord(
        substrate_id="code_sklearn_eval",
        wrapper="tools/run_code.py",
        card_path="docs/envelope_card_code_sklearn_eval.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="battery not on the run manifest — owner decision pending",
    ),
    SubstrateRecord(
        substrate_id="fenicsx_cantilever_elastic",
        wrapper="tools/run_fenicsx.py",
        card_path="docs/envelope_card_fenicsx_cantilever_elastic.md",
        maturity=CALIBRATING,
        routable=True,
        cost_tier="low",
        notes=(
            "battery executed 2026-07-17 (28/30 gate draws in-band at 3 "
            "repeats, 8/10 cases unanimous, hook witnessed 18/18 "
            "zero-silent-trust, wrapper self-checks 5/5 — harness/"
            "calibration_fenicsx_cantilever_elastic_20260717T125837Z.json); "
            "G0-G5 RULED + card provisionally signed (owner, 2026-07-16); "
            "routable=True RULED Packet B Phase 2 (owner 'start phase 1' "
            "pair unit + R-B-1 + the Phase-2.0 ruling line, build chat "
            "under the owner's standing delegation, 2026-07-17: "
            "StaticSmallDeflectionRegime shape, option R1), maturity "
            "CALIBRATING unchanged — every trust decision human-required "
            "via the maturity hook until a separate maturity ruling. The "
            "element-order bound G5 must survive into every routing "
            "decision (router card §7); a spec both cantilevers serve "
            "stops loudly at selection under R-B-1 — never a silent "
            "enrollment-order pick."
        ),
    ),
    SubstrateRecord(
        substrate_id="sympy_symbolic_exact",
        wrapper="tools/run_scipy.py",
        card_path="docs/envelope_card_sympy_symbolic_exact.md",
        maturity=CALIBRATING,
        routable=True,
        cost_tier="low",
        notes=(
            "sci-Python Regime A (exact symbolic CAS); card provisionally "
            "signed (owner, 2026-07-16), S1-S6 + S2a/S4a/S4b all RULED (owner, "
            "2026-07-16); battery executed 2026-07-17 (28/30 draws in-band, "
            "8/10 cases unanimous, hook witnessed 16/16 zero-silent-trust, "
            "wrapper self-checks 5/5 — harness/"
            "calibration_sympy_symbolic_exact_20260717T115450Z.json); "
            "routable=True RULED Packet B Phase 1 (owner 'start phase 1' + "
            "Phase-1.0 ruling line, 2026-07-17: OperationSetRegime regime "
            "shape, item 1), maturity CALIBRATING unchanged — every trust "
            "decision human-required via the maturity hook until a separate "
            "maturity ruling. Regime B (scipy_numeric_quad) is QUEUED and "
            "has no row."
        ),
    ),
    SubstrateRecord(
        substrate_id="ngspice_linear_passive",
        wrapper="tools/run_ngspice.py",
        card_path="docs/envelope_card_ngspice_linear_passive.md",
        maturity=CALIBRATING,
        routable=True,
        cost_tier="low",
        notes=(
            "battery executed 2026-07-17 (30/30 draws in-band, 10/10 cases "
            "unanimous, hook witnessed 18/18 zero-silent-trust — harness/"
            "calibration_ngspice_linear_passive_20260717T123935Z.json); "
            "routable=True RULED R2, maturity CALIBRATING unchanged RULED R3 "
            "(owner, 2026-07-17) — every trust decision human-required via "
            "the maturity hook until a separate maturity ruling"
        ),
    ),
    SubstrateRecord(
        substrate_id="rdkit",
        instrument_class=EXACT,  # deterministic cheminformatics descriptors
        wrapper="tools/run_rdkit.py",
        card_path="docs/envelope_card_rdkit.md",
        maturity=MATURE,
        routable=True,
        cost_tier="low",
        notes=(
            "BIO Wave D.4 PROMOTION (owner-ruled 2026-07-19): routable=True AND "
            "maturity=MATURE flipped TOGETHER — one of the first three MATURE "
            "substrates, so an in-envelope trust verdict routed here STANDS (the "
            "maturity hook no longer names it). descriptor_computation wrapper "
            "(tools/run_rdkit.py) proven real in rdkit-prod, all four jails "
            "triggered; card signed from real runs (docs/envelope_card_rdkit.md, "
            "rdkit 2026.03.4). Calibration CLEAN at N=3 (in-envelope 30/30 trust, "
            "out 30/30 defer). Runtime maps WIRED: contract graduated to "
            "substrates.py (RDKIT_DESCRIPTOR_CONTRACT, re-exported by "
            "onboarding/rdkit/contract.py — one source), signature/vocab/dispatch "
            "wired at this flip. First BIO substrate to route."
        ),
    ),
    SubstrateRecord(
        substrate_id="cobrapy",
        instrument_class=EXACT,  # deterministic FBA linear-program optimum
        wrapper="tools/run_cobrapy.py",
        card_path="docs/envelope_card_cobrapy.md",
        maturity=MATURE,
        routable=True,
        cost_tier="low",
        notes=(
            "BIO Wave D.4 PROMOTION (owner-ruled 2026-07-19): routable=True AND "
            "maturity=MATURE flipped TOGETHER on the N=7 re-run "
            "(calibration_cobrapy_20260719T052035Z.json): in-envelope 34 trust "
            "/ 1 refine (the lone G02/iML1515 refine, 1 of 7 draws — the D.3 "
            "split WASHED OUT), out 35/35 defer. fba_steady_state wrapper "
            "(tools/run_cobrapy.py) proven real in cobrapy-prod on e_coli_core + "
            "iML1515; the STRUCTURAL status-gate jail (infeasible -> qoi None, "
            "never the stale objective) proven on BOTH models; card from real "
            "runs (docs/envelope_card_cobrapy.md). Runtime maps WIRED: contract "
            "graduated to substrates.py (COBRAPY_FBA_CONTRACT, re-exported by "
            "onboarding/cobrapy/contract.py — one source), signature "
            "{model,quantity} (min_growth optional, not in the signature), "
            "vocab/dispatch wired at this flip."
        ),
    ),
    SubstrateRecord(
        substrate_id="cas_offinder",
        wrapper="tools/run_cas_offinder.py",
        card_path="docs/envelope_card_cas_offinder.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "RE-TIERED T1 -> DEFERRED — Cas-OFFinder's OpenCL kernel does not "
            "compute correctly on colima/aarch64 (pocl exits 0 with 0 matches; "
            "a fabricated '0 off-targets' is the dangerous CRISPR wrong answer). "
            "Wrapper (tools/run_cas_offinder.py) built with a KNOWN-ANSWER GUARD "
            "that refuses unless a known-present probe site is found — proven to "
            "FIRE on this host; input jails proven. Card SKELETON, section 3A "
            "PENDING-PROVISIONING (no kernel-produced numbers). Pinned: "
            "cas-offinder 2.4.1 + pocl 7.1 (bioconda, aarch64). Runtime maps "
            "STAGED in onboarding/cas_offinder/, UNWIRED; contract_for raises. "
            "Un-defer requires the guard to pass on a validated-kernel host."
        ),
    ),
    SubstrateRecord(
        substrate_id="homology_search",
        instrument_class=EXACT,  # deterministic sequence search
        wrapper="tools/run_homology_search.py",
        card_path="docs/envelope_card_homology_search.md",
        maturity=MATURE,
        routable=True,
        cost_tier="low",
        notes=(
            "BIO Wave D.4 PROMOTION #2 (owner-ruled 2026-07-19): routable=True "
            "AND maturity=MATURE flipped TOGETHER — the FOURTH mature substrate. "
            "HELD from the first D.4 merge for a G03/G05 card fix (the two cases "
            "were written too close to the e-value-vs-homology boundary and drew "
            "a correct refine cluster; reframed strictly as similarity-"
            "significance, gate untouched), then promoted on the trust-dominant "
            "N=7 re-run (calibration_homology_search_20260719T071928Z.json: "
            "in-envelope 30 trust / 5 refine / 0 defer — every case MODAL TRUST; "
            "out 35/35 defer). The 5 residual in-envelope refines are STRUCTURAL "
            "texture (e_value=significance sits one careful step from the "
            "homology C1-hole), trust-with-caveat not defer — NOT miscalibration. "
            "The BLAST+HMMER bundle: ONE substrate, ONE row, signature {database, "
            "query, tool, quantity}; BLAST known hit e_value 4.36e-58, HMMER "
            "8.2e-61; the did-it-work / DB+profile-integrity gate proven by "
            "triggering. Pinned BLAST 2.16.0+ / HMMER 3.4. Runtime maps WIRED: "
            "contract graduated to substrates.py (HOMOLOGY_SEARCH_CONTRACT, "
            "re-exported by onboarding/homology_search/contract.py — one source), "
            "signature/vocab/dispatch wired at this flip. THREE-state wrapper "
            "(valid=False could-not-run; valid=True/qoi=None clean no-hit; "
            "valid=True/qoi=e_value a hit), handled by a dedicated run entry."
        ),
    ),
    SubstrateRecord(
        substrate_id="mafft",
        instrument_class=EXACT,  # deterministic multiple-sequence alignment
        wrapper="tools/run_mafft.py",
        card_path="docs/envelope_card_mafft.md",
        maturity=MATURE,
        routable=True,
        cost_tier="low",
        notes=(
            "BIO Wave D.4 PROMOTION (owner-ruled 2026-07-19): routable=True AND "
            "maturity=MATURE flipped TOGETHER; calibration CLEAN at N=3 "
            "(in-envelope 30/30 trust, out 30/30 defer). MSA alignment "
            "(tools/run_mafft.py) proven real in mafft-prod (alignment_identity "
            "94.4444, deterministic). Alignment is a near-TOTAL function "
            "(garbage in -> well-formed alignment of garbage out), so the "
            "did-it-work signal is the STRICT INPUT GATE (>=2 alignable "
            "same-alphabet sequences, refused PRE-RUN); input jails (single-seq, "
            "junk residues, mixed alphabet, empty) proven by triggering. "
            "NARROWEST trust claim in the wave: an alignment used DESCRIPTIVELY, "
            "not 'the correct' one (C1-hole M4 carries all biological-"
            "correctness claims). Card from real runs. Pinned MAFFT v7.526. "
            "Runtime maps WIRED: contract graduated to substrates.py "
            "(MAFFT_CONTRACT, re-exported by onboarding/mafft/contract.py — one "
            "source), signature/vocab/dispatch wired at this flip."
        ),
    ),
    SubstrateRecord(
        substrate_id="autodock_vina",
        wrapper="tools/run_autodock_vina.py",
        card_path="docs/envelope_card_autodock_vina.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "RE-TIERED T2 -> DEFERRED — AutoDock Vina has NO aarch64 build "
            "(bioconda 'No entries matching autodock-vina'; pip 'No matching "
            "distribution ... versions: none'), so it will not install on this "
            "host. Wrapper (tools/run_autodock_vina.py) written with the "
            "intended fixed-seed + convergence-gate + input-validation logic; "
            "the pure-Python INPUT jails are proven now; card SKELETON, section "
            "3A PENDING-PROVISIONING with a HARD C1-hole (docking_score is a "
            "relative screen within a human-validated receptor+box; prep + box "
            "are unvalidated upstream). UN-DEFER needs a DIFFERENT ARCHITECTURE "
            "(an x86 host where Vina installs) + real 3A + fixed-seed "
            "determinism + the convergence jail triggered — distinct from "
            "cas_offinder's validated-environment requirement. Runtime maps "
            "STAGED in onboarding/autodock_vina/, UNWIRED; contract_for raises."
        ),
    ),
    SubstrateRecord(
        substrate_id="crispr_guide_scoring",
        wrapper="tools/run_crispr_guide_scoring.py",
        card_path="docs/envelope_card_crispr_guide_scoring.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "RE-TIERED T2 -> DEFERRED — no VERIFIED py3 Doench/CFD scorer runs "
            "here (Azimuth is Python-2 + model-based; no standalone CFD "
            "package). A SOFTWARE-AVAILABILITY defer (distinct from "
            "cas_offinder's validated-environment and autodock_vina's x86 "
            "architecture). Wrapper (tools/run_crispr_guide_scoring.py): the "
            "pure-Python INPUT gate (20-nt guide, PAM matching the enzyme "
            "motif, allowlist enzyme) is proven now; a valid input returns the "
            "honest DEFERRED state, never a fabricated score. Card SKELETON, "
            "section 3A PENDING. UN-DEFER = a verified py3 Doench/CFD "
            "scorer/model FROM A TRUSTED SOURCE; hand-transcribing coefficients "
            "is FORBIDDEN (silent-wrong) — the prohibition is part of the spec. "
            "Runtime maps STAGED in onboarding/crispr_guide_scoring/, UNWIRED; "
            "contract_for raises."
        ),
    ),
    SubstrateRecord(
        substrate_id="boltz2",
        wrapper="tools/run_boltz2.py",
        card_path="docs/envelope_card_boltz2.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "DEFERRED — Boltz-2 is a GPU neural model with downloaded weights; "
            "no GPU on this aarch64 host. Wrapper input gate proven pure-Python "
            "(protein_sequence, quantity in {affinity,rmsd}); valid input -> "
            "honest DEFERRED, never a fabricated prediction. Card SKELETON, 3A "
            "PENDING. UN-DEFER (specific) = a GPU host + the PINNED official "
            "Boltz-2 weights + a KNOWN-ANSWER validation run before any number "
            "is trusted (mismatched weights = confident garbage). Signature "
            "{protein_sequence,quantity} SHARES with alphafold_db BY DESIGN (the "
            "Step-41 L1a pair, distinct regimes) — fires only at D.4. Runtime "
            "maps STAGED, UNWIRED; contract_for raises."
        ),
    ),
    SubstrateRecord(
        substrate_id="proteinmpnn",
        wrapper="tools/run_proteinmpnn.py",
        card_path="docs/envelope_card_proteinmpnn.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "DEFERRED — ProteinMPNN is a GPU neural model with downloaded "
            "weights; no GPU here. Wrapper input gate proven pure-Python "
            "(backbone allowlist, quantity seq_recovery); valid input -> honest "
            "DEFERRED, never a fabricated score. Card SKELETON, 3A PENDING. "
            "UN-DEFER (specific) = a GPU host + the PINNED official ProteinMPNN "
            "weights + a KNOWN-ANSWER validation run (mismatched weights = "
            "confident garbage). Runtime maps STAGED, UNWIRED; contract_for raises."
        ),
    ),
    SubstrateRecord(
        substrate_id="retrosynthesis",
        wrapper="tools/run_retrosynthesis.py",
        card_path="docs/envelope_card_retrosynthesis.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "DEFERRED — AiZynth/ASKCOS heavy models AND a reaction ROUTE "
            "DATABASE/backend (a DATA dependency beyond weights), neither "
            "available here. Wrapper input gate proven pure-Python "
            "(target_smiles, backend in {aizynth,askcos}, quantity "
            "synthesizability); valid input -> honest DEFERRED, never a "
            "fabricated route. Card SKELETON, 3A PENDING. UN-DEFER (specific) = "
            "the models AND the reaction route DB/backend the tool queries + a "
            "KNOWN-ANSWER run ('GPU + weights' UNDERCOUNTS the data dependency). "
            "Runtime maps STAGED, UNWIRED; contract_for raises."
        ),
    ),
    SubstrateRecord(
        substrate_id="alphafold_db",
        wrapper="tools/run_alphafold_db.py",
        card_path="docs/envelope_card_alphafold_db.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A) -> D.4-network UN-DEFER "
            "(owner-ruled 2026-07-19): the AFDB endpoint IS reachable, so the "
            "network lookup path is WIRED (tools/run_alphafold_db.py) and returns "
            "a REAL mean pLDDT from globalMetricValue — proven live (P0DP23 -> "
            "85.25, ~0.13 s); the not-found (well-formed absent accession -> 404) "
            "and endpoint-unreachable (setup_error) jails proven by triggering; "
            "never a fabricated pLDDT. Card §3A FILLED from real calls. "
            "INPUT-SHAPE RULING (owner 2026-07-19): keyed by uniprot_accession, "
            "NOT protein_sequence (AFDB is accession-keyed) — the boltz2 L1a "
            "pairing is dropped; the {uniprot_accession,quantity} signature is "
            "unique/disjoint. LOOKUP-class: A3 never-trust-alone is PERMANENT (a "
            "standing trust claim, NOT lifted by un-deferring). Calibration slate "
            "staged (harness/calibration_cases_alphafold_db.json); battery "
            "dispatch extended. STILL calibrating/routable=False — PROMOTION "
            "(routable+mature, six-surface wiring) is a SEPARATE later flip on "
            "clean gate-track calibration; contract_for raises until then."
        ),
    ),
    SubstrateRecord(
        substrate_id="bio_db_lookup",
        wrapper="tools/run_bio_db_lookup.py",
        card_path="docs/envelope_card_bio_db_lookup.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A) -> D.4-network UN-DEFER "
            "(owner-ruled 2026-07-19): ALL FOUR endpoints (PDB/PubChem/UniProt/"
            "ChEMBL) are reachable, so the per-database lookup path is WIRED "
            "(tools/run_bio_db_lookup.py) and returns a REAL round-trip "
            "resolution — proven live (probe_endpoints fully_live=true; 4HHB/"
            "2244/P0DP23/CHEMBL25 all resolve, ~0.07-0.6 s). The per-namespace "
            "not-found shapes incl. the HTTP-200 traps (PubChem 200-but-no-"
            "formula; UniProt 200-but-Inactive) are classed not-found, DISTINCT "
            "from a network failure; the PARTIAL-defer path (one endpoint down -> "
            "that database defers while others resolve) proven by triggering; "
            "never a fabricated record. Card §3A FILLED from real calls. "
            "LOOKUP-class: D3 never-trust-alone is PERMANENT (corroboration "
            "required forever) + the DB's curation currency is unverifiable — "
            "NOT lifted by un-deferring. Calibration slate staged "
            "(harness/calibration_cases_bio_db_lookup.json); battery dispatch "
            "extended. STILL calibrating/routable=False — PROMOTION is a SEPARATE "
            "later flip on clean gate-track calibration; contract_for raises "
            "until then."
        ),
    ),
    SubstrateRecord(
        substrate_id="python_experiment",
        instrument_class=EXACT,  # sealed deterministic code sandbox
        wrapper="tools/run_python_experiment.py",
        card_path="docs/envelope_card_python_experiment.md",
        maturity=MATURE,
        routable=True,
        cost_tier="low",
        notes=(
            "Code-execution promotion, owner-ruled 2026-07-21 ('unblock "
            "everything'): the general model-authored-Python instrument, so an "
            "ML / algorithms / numerical experiment routes and gets measured + "
            "verified like any other. MATURE on a different basis than a physics "
            "solver's fidelity-distribution battery: a code experiment's "
            "fidelity IS its reproducibility, and that is guarded DIRECTLY by "
            "the verification pass (stages/verification.py already re-runs "
            "kind='code' artifacts and compares) plus the stage-3 fidelity gate "
            "— a stronger, more direct guarantee than a calibrating solver's, so "
            "unattended trust is warranted. Sandbox: ephemeral --network=none "
            "container, resource-capped, structural metric gate (the script "
            "writes {metrics:{...}} to a result file; a number is never parsed "
            "from prose). The agents that AUTHOR the code already roam under the "
            "FULL capability profile; this makes their code-run RESULTS count as "
            "verified measurements of record."
        ),
    ),
    SubstrateRecord(
        substrate_id="web_search",
        wrapper="tools/web_search_stub.py",
        card_path="docs/substrate_registry.md",
        maturity=RETRIEVAL_PROVISIONAL,
        routable=False,
        cost_tier="minimal",
        notes="structurally never trusted alone",
    ),
)

_BY_ID: dict[str, SubstrateRecord] = {r.substrate_id: r for r in _REGISTRY}

# --- the model-visible fidelity contract, keyed by substrate id ------------
# R-S3-1: the ONE place "which contract does the gate judge against" is
# answered, replacing stage3's hardcoded module constant. Registry-driven and
# structural — a caller passes a substrate_id it obtained STRUCTURALLY from
# this registry (routable_ids / sole_routable_id), never parsed from a payload
# name (R-28H-1). cavity's value IS the imported substrates.CAVITY_2D_CONTRACT
# (never a pasted copy — substrates.py stays the single source of truth, same
# discipline as the R-WIN-1 prompt blocks). A substrate absent from this map
# has NO wired contract: contract_for RAISES rather than substitute cavity.
# Enrolling FEA/code here is a SEPARATE future ruling (they are unroutable and
# uncalibrated today) — their absence from this map is deliberate, not an
# oversight, and is the fail-loud escape the Part-A tests prove.
_CONTRACTS: dict[str, str] = {
    "cavity_2d_cfd": CAVITY_2D_CONTRACT,
    # R2 promotion flip (owner, 2026-07-17): the IMPORTED runtime constant,
    # graduated to substrates.py — never a pasted copy, and never the
    # battery's compact SUBSTRATE_TEXT (a different artifact; see
    # onboarding/ngspice_linear_passive/contract.py).
    "ngspice_linear_passive": NGSPICE_LINEAR_PASSIVE_CONTRACT,
    # Packet B Phase 1 flip (owner, 2026-07-17): the IMPORTED runtime
    # constant, AUTHORED AT GRADUATION in substrates.py (the sympy
    # onboarding module had no 5-section text to move — its structured
    # allowlists stay the wrapper's source of truth; see the onboarding
    # module's STAGING NOTE) — never a pasted copy, and never the
    # battery's substrate_text/envelope_text (different artifacts).
    "sympy_symbolic_exact": SYMPY_SYMBOLIC_EXACT_CONTRACT,
    # Packet B Phase 2 flip (build chat under the owner's standing
    # delegation, 2026-07-17): the IMPORTED runtime constants — calculix
    # AUTHORED AT GRADUATION in substrates.py (no onboarding module ever
    # existed for it); fenicsx COMPOSED in substrates.py from the
    # onboarding module's own section constants (path-loaded, the
    # run_scipy mechanism) so the battery-facing text has exactly one
    # source and the executed battery's case file stays byte-identical.
    "calculix_cantilever_fea": CALCULIX_CANTILEVER_FEA_CONTRACT,
    "fenicsx_cantilever_elastic": FENICSX_CANTILEVER_ELASTIC_CONTRACT,
    # BIO Wave D.4 promotion flip (owner, 2026-07-19): the first MATURE
    # substrates. Each IMPORTED runtime constant graduated from
    # onboarding/<sub>/contract.py to substrates.py (never a pasted copy —
    # the onboarding module re-exports it). rdkit + mafft on clean N=3
    # (30/30); cobrapy on the N=7 wash-out (34 trust / 1 refine in-envelope,
    # G02 lone). homology_search HELD (G03/G05 card fix, no _CONTRACTS entry).
    "rdkit": RDKIT_DESCRIPTOR_CONTRACT,
    "cobrapy": COBRAPY_FBA_CONTRACT,
    "mafft": MAFFT_CONTRACT,
    # Code-execution promotion (owner-ruled 2026-07-21): the general
    # model-authored-Python instrument, so an ML / algorithms experiment routes
    # and gets measured + verified like any other. The IMPORTED runtime
    # constant, authored in substrates.py — never a pasted copy.
    "python_experiment": PYTHON_EXPERIMENT_CONTRACT,
    # BIO Wave D.4 promotion #2 (owner, 2026-07-19): homology_search, HELD from
    # the first merge for a G03/G05 card fix, promotes on the trust-dominant
    # N=7 re-run (every in-envelope case modal trust; out 35/35 defer). The
    # BLAST+HMMER bundle — one substrate, one contract.
    "homology_search": HOMOLOGY_SEARCH_CONTRACT,
}


def contract_for(substrate_id: str) -> str:
    """The model-visible fidelity-contract text for one substrate, read
    STRUCTURALLY from the registry (R-28H-1: never parsed from a payload name).

    THE CHAIN SEAM (Steps 31/32). A chain of N nodes needs N contracts — each
    node verdicted against its OWN card, chain trust capped at the weakest link.
    This function is that seam: call it once per node with the node's own
    substrate_id. It is keyed on substrate_id ALONE so a multi-node chain drops
    in without rework; it does NOT decide which substrate a node runs on (that
    is Stage 3 / task-typing's job — Step 35 — and is deliberately not built
    here).

    FAIL LOUD (R-S3-1): a substrate with no wired contract raises LookupError.
    The gate NEVER falls back to cavity for a substrate it has no contract for —
    an unroutable FEA/code substrate has no routing contract here by design, and
    a run that reached this point for one is a broken invariant, not a case to
    paper over with the wrong contract. An unknown id raises KeyError first (via
    get) — an unenrolled substrate is never silently treated as anything.
    """
    record = get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _CONTRACTS[substrate_id]
    except KeyError:
        raise LookupError(
            f"no fidelity contract wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "the gate must NOT fall back to cavity — wire a contract in "
            "_CONTRACTS under a recorded ruling before routing to this "
            "substrate."
        )


def routable_contracts_block() -> str:
    """R5 (owner, 2026-07-17): the ALL-ROUTABLE contract block for Stage-1
    surfaces. Stage 1 sits BEFORE any hypothesis is chosen, so its honest
    grounding is every instrument the run could route to — never a selected
    one (the D.1.1 direction: all routable contracts at Stage-1 surfaces,
    task-typed selection at Stage-2/Step-35).

    Deterministic pure function of the registry: loops permitted_ids() in
    enrollment order and emits, per substrate, a minimal fixed header naming
    the substrate_id and then contract_for(id) VERBATIM — never a paraphrase,
    never a pasted copy. No timestamps, fixed separators, byte-stable.
    FAIL LOUD inherits from contract_for: a routable substrate without a
    wired contract cannot compose — the LookupError escapes.

    Reads permitted_ids() rather than routable_ids() so a run-scoped
    constraint narrows this block too. That HONORS R5 rather than departing
    from it: the ruling's point is that the block shows every instrument the
    run could route to, never a pre-selected one, and under a constraint the
    excluded instruments are precisely the ones the run cannot reach.
    Grounding ideation in a contract whose substrate routing will refuse is
    how you get a hypothesis that cannot be run. Unconstrained, this is
    byte-identical to the all-routable block."""
    return "\n\n".join(
        "ROUTABLE SUBSTRATE: " + sid + "\n" + contract_for(sid)
        for sid in permitted_ids()
    )


def sole_routable_id() -> str:
    """RETIRED FROM PRODUCTION (D.2, 2026-07-17): zero production call sites —
    stage 3 now selects via tools/substrate_selection.select_substrate
    (signature-based serve-ability, mature preferred, enrollment-order
    tie-break), and that module's fail-loud probes (contract AND signature
    wired for every routable substrate) replace this function's
    exactly-one-routable raise as the promotion seam. The body stays for
    tests/history (tests/test_contract_registry.py exercises it); no new call
    site may use it.

    Original contract, still honored: the one routable substrate id, read from
    the registry, never guessed; RAISES if the routable set is not exactly
    one."""
    routable = routable_ids()
    if len(routable) != 1:
        raise RuntimeError(
            f"substrate selection is ambiguous: routable set is {list(routable)}; "
            "the single-node pipeline requires exactly one routable substrate. "
            "Multi-substrate node selection is Step 35 (task typing) — it must "
            "not be silently guessed here."
        )
    return routable[0]


def all_substrates() -> tuple[SubstrateRecord, ...]:
    """Every enrolled substrate, in enrollment order."""
    return _REGISTRY


def get(substrate_id: str) -> SubstrateRecord:
    """The record for one substrate. Raises KeyError on an unknown id — an
    unknown substrate is never silently treated as anything."""
    return _BY_ID[substrate_id]


def maturity_of(substrate_id: str) -> str:
    """The maturity rung of one substrate."""
    return _BY_ID[substrate_id].maturity


def is_mature(substrate_id: str) -> bool:
    """True only when the substrate is fully 'mature' — the one rung a trust
    decision may proceed on unattended. provisional / calibrating /
    retrieval-provisional all return False (non-mature)."""
    return _BY_ID[substrate_id].maturity == MATURE


def is_frozen_anchor(substrate_id: str) -> bool:
    """True only for a declared reproducibility-anchor substrate (D.1a) —
    today, cavity alone. Generic logic that would grow a model-visible surface
    reads THIS to opt the anchor out, keeping its byte-frozen era guard intact,
    without ever branching on a substrate name. Raises KeyError on an unknown
    id (via _BY_ID) — an unenrolled substrate is never silently treated as
    anything, same fail-loud discipline as the rest of the registry."""
    return _BY_ID[substrate_id].frozen_anchor


def instrument_class_of(substrate_id: str) -> str:
    """The instrument class (EXACT | APPROXIMATE) of one substrate (Phase 3,
    R-ROUTE-1). Read structurally, never parsed from a substrate name. Raises
    KeyError on an unknown id (via _BY_ID) — same fail-loud discipline as the
    rest of the registry."""
    return _BY_ID[substrate_id].instrument_class


def is_approximate(substrate_id: str) -> bool:
    """True when the substrate is an APPROXIMATE instrument — one that can
    converge to a confidently wrong number (R-ROUTE-1). Written as
    'not EXACT' so anything that is not explicitly the exact class is treated
    as approximate: the fail-safe direction, matching the record's default.
    Raises KeyError on an unknown id (fail loud)."""
    return instrument_class_of(substrate_id) != EXACT


def routable_ids() -> tuple[str, ...]:
    """The substrate ids the pipeline may route execution to, in enrollment
    order. This is the registry's answer to 'what can a run execute on' — it
    is consulted structurally, NOT parsed from a payload's substrate names
    (that would violate the substrate-agnostic invariant). Since the BIO
    Wave D.4 promotion #2 (owner, 2026-07-19): ('cavity_2d_cfd',
    'calculix_cantilever_fea', 'fenicsx_cantilever_elastic',
    'sympy_symbolic_exact', 'ngspice_linear_passive', 'rdkit', 'cobrapy',
    'homology_search', 'mafft') — nine ids, enrollment order preserved (note
    homology_search enrolls BEFORE mafft); the last four are the MATURE
    substrates (rdkit/cobrapy/homology_search/mafft)."""
    return tuple(r.substrate_id for r in _REGISTRY if r.routable)


# --- RUN-SCOPED SUBSTRATE CONSTRAINT --------------------------------------
# A caller may restrict which of the routable substrates THIS RUN may reach,
# so a goal-level constraint ("only use cobrapy") is enforced AT ROUTING
# rather than merely stated in a prompt and ignored by every decision after
# it. Before this, a constraint in the goal text reached the ideation model
# and evaporated: every routing surface read the full routable set.
#
# THIS IS A RUNTIME NARROWING OF AN UNCHANGED REGISTRY. Rows are never
# mutated — maturity and routable stay governance facts that change only by
# editing this file under a recorded ruling (see the header). routable_ids()
# keeps its registry meaning, unnarrowed, because "what is routable" is a
# fact about the system and "what may this run reach" is a fact about the
# run. permitted_ids() is the second question, and it is the one every
# routing surface should ask.
#
# With the variable unset, permitted_ids() == routable_ids() and every
# consumer sees exactly what it saw before. That byte-identity is the
# property the whole change rests on.
#
# The channel is the environment, matching RESEARCH_CAMPAIGN /
# CAMPAIGN_MAX_ITERS / BLANK_MEMORY, and chosen so that a controller
# dispatching runs as subprocesses hands each run its constraints the same
# way it hands them everything else.
ALLOWED_SUBSTRATES_ENV = "ALLOWED_SUBSTRATES"


def allowed_constraint() -> frozenset[str] | None:
    """The run-scoped allow-set parsed from the environment, or None when the
    run is unconstrained.

    Unset, empty, or whitespace-only => None (unconstrained), matching the
    convention every other env flag in this project follows. A value that has
    content but names an id this registry does not enroll RAISES, and so does
    one that parses to nothing (e.g. ",,,"): a constraint that names something
    nonexistent is a caller error, and silently dropping it would produce
    exactly the failure this feature exists to prevent — a constraint that
    reads as binding and is not.

    Names are comma-separated; surrounding whitespace is tolerated.
    """
    raw = os.environ.get(ALLOWED_SUBSTRATES_ENV, "")
    if not raw.strip():
        return None
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        raise RuntimeError(
            f"{ALLOWED_SUBSTRATES_ENV}={raw!r} parses to no substrate names. "
            "Set it to a comma-separated list of enrolled substrate ids, or "
            "unset it to leave the run unconstrained — it is never treated as "
            "an empty allow-set, because a constraint that silently permits "
            "everything is the failure this setting exists to prevent."
        )
    unknown = sorted(n for n in names if n not in _BY_ID)
    if unknown:
        raise RuntimeError(
            f"{ALLOWED_SUBSTRATES_ENV} names substrate(s) this registry does "
            f"not enroll: {unknown}. Enrolled ids are "
            f"{[r.substrate_id for r in _REGISTRY]}. A constraint naming a "
            "substrate that does not exist is a caller error, not an empty "
            "restriction — fix the name, or enroll the substrate under a "
            "recorded ruling; stopping before routing."
        )
    return frozenset(names)


def permitted_ids() -> tuple[str, ...]:
    """The substrate ids THIS RUN may route to: routable_ids() narrowed by the
    run-scoped constraint, enrollment order preserved.

    This is what every routing surface should consult — selection, the
    contract blocks composed into model inputs, the gate-1 chooser's
    validator, chain-node routing, and the human instrument prompt. Asking
    routable_ids() instead is how a constraint becomes decorative.

    Unconstrained => returns routable_ids() unchanged. Constrained to a set
    that leaves NO routable substrate => RAISES, naming both sides. There is
    no fallback: a run that may reach nothing must stop loudly rather than
    quietly widen back to the full set.

    Deliberately calls routable_ids() rather than reading _REGISTRY directly,
    so the existing test seams that patch routable_ids keep working.
    """
    routable = routable_ids()
    allowed = allowed_constraint()
    if allowed is None:
        return routable
    permitted = tuple(sid for sid in routable if sid in allowed)
    if not permitted:
        parked = sorted(allowed - set(routable))
        raise RuntimeError(
            f"{ALLOWED_SUBSTRATES_ENV}={sorted(allowed)} leaves no routable "
            f"substrate for this run: the routable set is {list(routable)}, and "
            f"the constrained id(s) {parked} are enrolled but not routable. "
            "Constrain the run to at least one routable substrate, or promote "
            "one under a recorded ruling; stopping before routing. The "
            "constraint is never widened back to the full routable set."
        )
    return permitted
