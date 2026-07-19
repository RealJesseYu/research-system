"""contract.py — the model-visible fidelity contract for the
(homology_search, homology_search) substrate (the BLAST+HMMER bundle).

STAGING — RESOLVED at the D.4 promotion #2 flip (owner ruling, 2026-07-19, on
the N=7 re-run after the G03/G05 card fix: every in-envelope case modal trust,
out 35/35 defer). The runtime CONTRACT constant has GRADUATED to substrates.py
(its canonical home; re-exported below) and is wired into
tools/substrate_registry.py `_CONTRACTS` alongside routable=True at maturity
MATURE — the ngspice R2-flip precedent. ONE source; the line below is an import,
never a second copy. Before promotion this file WAS the contract's home while
homology_search enrolled `calibrating`/`routable=False` and
`contract_for("homology_search")` raised (Option A, owner-ruled 2026-07-18); it
was HELD from the first D.4 merge (the G03/G05 card fix + re-run) and promotes
now on the trust-dominant re-run.
"""

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from substrates import HOMOLOGY_SEARCH_CONTRACT  # noqa: E402
