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

from dataclasses import dataclass

from substrates import (
    CALCULIX_CANTILEVER_FEA_CONTRACT,
    CAVITY_2D_CONTRACT,
    FENICSX_CANTILEVER_ELASTIC_CONTRACT,
    NGSPICE_LINEAR_PASSIVE_CONTRACT,
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
        wrapper="tools/run_rdkit.py",
        card_path="docs/envelope_card_rdkit.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "descriptor_computation wrapper (tools/run_rdkit.py) proven real in "
            "rdkit-prod, all four jails triggered; card signed from real runs "
            "(docs/envelope_card_rdkit.md, rdkit 2026.03.4). ENROLLED but INERT "
            "— the runtime maps (contract/signature/vocab/dispatch) are STAGED "
            "in onboarding/rdkit/, UNWIRED; contract_for('rdkit') must keep "
            "raising LookupError until a D.4 promotion ruling. Battery pending "
            "an owner-OK'd slot. First BIO substrate; nothing routes here."
        ),
    ),
    SubstrateRecord(
        substrate_id="cobrapy",
        wrapper="tools/run_cobrapy.py",
        card_path="docs/envelope_card_cobrapy.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "fba_steady_state wrapper (tools/run_cobrapy.py) proven real in "
            "cobrapy-prod on e_coli_core + iML1515; the STRUCTURAL status-gate "
            "jail (infeasible -> qoi None, never the stale objective) proven by "
            "triggering it on BOTH models; card from real runs "
            "(docs/envelope_card_cobrapy.md). ENROLLED but INERT — runtime maps "
            "STAGED in onboarding/cobrapy/, UNWIRED; contract_for('cobrapy') "
            "must keep raising LookupError until a D.4 promotion ruling. "
            "Battery pending. Nothing routes here."
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
        wrapper="tools/run_homology_search.py",
        card_path="docs/envelope_card_homology_search.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): the "
            "BLAST+HMMER bundle (substrate_id homology_search; tool field). "
            "BLAST backend (tools/run_homology_search.py) proven real in "
            "homology-search-prod — known hit e_value 4.36e-58; the "
            "did-it-work / DB-integrity gate proven by triggering (a broken DB "
            "-> search-could-not-run, distinct from a clean 0-hits result, since "
            "blastp exits 0 on a missing DB). Card from real runs "
            "(docs/envelope_card_homology_search.md, BLAST 2.16.0+). HMMER "
            "backend wired in the next increment (same substrate, no new row). "
            "ENROLLED but INERT — runtime maps STAGED in onboarding/"
            "homology_search/, UNWIRED; contract_for('homology_search') must "
            "keep raising until a D.4 promotion ruling. Nothing routes here. "
            "HMMER backend WIRED (2026-07-18): hmmsearch on baked profiles, its "
            "profile-integrity jail (malformed HMM -> could-not-run, distinct "
            "from 0-hits) proven; known hit e_value 8.2e-61; pinned HMMER 3.4. "
            "BLAST path proven unperturbed."
        ),
    ),
    SubstrateRecord(
        substrate_id="mafft",
        wrapper="tools/run_mafft.py",
        card_path="docs/envelope_card_mafft.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): MSA "
            "alignment (tools/run_mafft.py) proven real in mafft-prod "
            "(alignment_identity 94.4444, deterministic). Alignment is a "
            "near-TOTAL function (garbage in -> well-formed alignment of garbage "
            "out), so the did-it-work signal is the STRICT INPUT GATE (>=2 "
            "alignable same-alphabet sequences, refused PRE-RUN); input jails "
            "(single-seq, junk residues, mixed alphabet, empty) proven by "
            "triggering. NARROWEST trust claim in the wave: an alignment used "
            "DESCRIPTIVELY, not 'the correct' one (C1-hole M4 carries all "
            "biological-correctness claims). Card from real runs. Pinned MAFFT "
            "v7.526. ENROLLED but INERT — runtime maps STAGED in onboarding/"
            "mafft/, UNWIRED; contract_for('mafft') must keep raising until a "
            "D.4 promotion ruling. Nothing routes here."
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
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "DEFERRED — a network lookup against the AlphaFold DB endpoint, not "
            "reachable/verified here. Wrapper input gate proven pure-Python "
            "(protein_sequence, quantity mean_pLDDT); valid input -> honest "
            "DEFERRED, never a fabricated pLDDT. Card SKELETON, 3A PENDING. "
            "UN-DEFER (specific) = working network + the specific AFDB endpoint "
            "reachable. LOOKUP-class: A3 never-trust-alone is PERMANENT (a "
            "standing trust claim, corroboration required forever, not just a "
            "provisioning gate). Signature {protein_sequence,quantity} SHARES "
            "with boltz2 BY DESIGN (Step-41 L1a pair, distinct regimes). Runtime "
            "maps STAGED, UNWIRED; contract_for raises."
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
            "BIO Wave D.2 enrollment (Option A, owner-ruled 2026-07-18): "
            "DEFERRED — a 4-API network wrapper (PDB/PubChem/UniProt/ChEMBL); no "
            "endpoint reachable here. The most expensive single wrapper in the "
            "wave (4 API integrations). Wrapper input gate proven pure-Python "
            "incl. PER-NAMESPACE id form (database allowlist, record_id form, "
            "quantity round_trip_id); valid input -> honest DEFERRED, never a "
            "fabricated record. Card SKELETON, 3A PENDING. UN-DEFER (specific) = "
            "ALL FOUR endpoints reachable (ONE down = PARTIAL defer, not full). "
            "LOOKUP-class: D3 never-trust-alone is PERMANENT (corroboration "
            "required forever) + the DB's curation currency is unverifiable. "
            "Runtime maps STAGED, UNWIRED; contract_for raises."
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

    Deterministic pure function of the registry: loops routable_ids() in
    enrollment order and emits, per substrate, a minimal fixed header naming
    the substrate_id and then contract_for(id) VERBATIM — never a paraphrase,
    never a pasted copy. No timestamps, fixed separators, byte-stable.
    FAIL LOUD inherits from contract_for: a routable substrate without a
    wired contract cannot compose — the LookupError escapes."""
    return "\n\n".join(
        "ROUTABLE SUBSTRATE: " + sid + "\n" + contract_for(sid)
        for sid in routable_ids()
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


def routable_ids() -> tuple[str, ...]:
    """The substrate ids the pipeline may route execution to, in enrollment
    order. This is the registry's answer to 'what can a run execute on' — it
    is consulted structurally, NOT parsed from a payload's substrate names
    (that would violate the substrate-agnostic invariant). Since the
    Packet B Phase 2 flip (build chat under the owner's standing
    delegation, 2026-07-17): ('cavity_2d_cfd', 'calculix_cantilever_fea',
    'fenicsx_cantilever_elastic', 'sympy_symbolic_exact',
    'ngspice_linear_passive') — five ids, enrollment order preserved."""
    return tuple(r.substrate_id for r in _REGISTRY if r.routable)
