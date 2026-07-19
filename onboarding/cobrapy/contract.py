"""contract.py — the model-visible fidelity contract for the
(cobrapy, fba_steady_state) substrate.

STAGING — RESOLVED at the D.4 promotion flip (owner ruling, 2026-07-19, on the
N=7 re-run: in-envelope 34 trust / 1 refine (G02 lone), out 35/35 defer — the
G02 split WASHED OUT). The runtime CONTRACT constant has GRADUATED to
substrates.py (its canonical home; re-exported below so any staging import stays
valid) and is wired into tools/substrate_registry.py `_CONTRACTS` alongside
routable=True at maturity MATURE — the ngspice R2-flip precedent. ONE source;
the line below is an import, never a second copy. Before promotion this file WAS
the contract's home while cobrapy enrolled `calibrating`/`routable=False` and
`contract_for("cobrapy")` raised (Option A, owner-ruled 2026-07-18).
"""

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from substrates import COBRAPY_FBA_CONTRACT  # noqa: E402
