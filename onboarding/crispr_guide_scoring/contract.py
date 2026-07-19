"""contract.py — STAGED. Model-visible fidelity contract for the
(crispr_guide_scoring, guide_activity_scoring) substrate. NOTHING imports this.

Option A: enrolls calibrating/routable=False, INERT — contract_for raises.
Additionally DEFERRED (no verified py3 scorer); un-defer needs a verified
scorer ARTIFACT (transcription forbidden — see the card). At promotion the text
moves to substrates.py as CRISPR_GUIDE_SCORING_CONTRACT.
"""

CRISPR_GUIDE_SCORING_CONTRACT = """SUBSTRATE CONTRACT — crispr_guide_scoring, guide_activity_scoring

1. WHAT THIS IS.
A CRISPR guide-efficiency scorer (Doench/CFD models, CRISPOR/CHOPCHOP class): it
scores a guide RNA's on-target efficiency for a target site under a given
nuclease. FILTER-class: the score is a RELATIVE efficiency screen from a
published model — not measured cutting.

2. TYPED INPUT.
    guide   : the 20-nt protospacer (A/C/G/T).
    pam     : the PAM, matching the enzyme's motif.
    enzyme  : a baked allowlist nuclease (SpCas9 = NGG).
    quantity: the QoI (the activity score).

3. REGIME (guide_activity_scoring).
In-regime: a valid guide + matching PAM + allowlist nuclease, scored by a
VERIFIED model. Out of regime: off-target specificity, non-allowlist nucleases,
measured-cutting claims.

4. WHAT IT RETURNS.
One scalar QoI — the relative on-target efficiency — returned ONLY from a
verified scorer. It never returns a score from an unverified/transcribed model.

5. THE VERIFIED-SCORER GATE, THE KNOWN GAP, AND A PROHIBITION.
The score is trustworthy ONLY when computed by a VERIFIED scorer; a
hand-transcribed model is FORBIDDEN (it produces plausible-but-unverifiable
scores — the silent-wrong failure). THE KNOWN GAP (uncheckable): the score is a
model's relative efficiency, not measured cutting; whether the guide/context is
within the model's training distribution is unknowable. Trust the score as a
relative screen, never as measured editing.
"""
