"""contract.py — the model-visible fidelity contract for the
(rdkit, descriptor_computation) substrate.

STAGING — RESOLVED at the D.4 promotion flip (owner ruling, 2026-07-19, on the
N=3 clean 30/30 calibration evidence). The runtime CONTRACT constant has
GRADUATED to substrates.py (its canonical home; re-exported below so any
staging import and every historical reference stay valid) and is wired into
tools/substrate_registry.py `_CONTRACTS` alongside routable=True at maturity
MATURE — exactly as NGSPICE_LINEAR_PASSIVE_CONTRACT did at the R2 flip. ONE
source; the line below is an import, never a second copy. Before promotion this
file WAS the contract's home while rdkit enrolled `calibrating`/`routable=False`
and `contract_for("rdkit")` raised (Option A, owner-ruled 2026-07-18).

The five-section runtime contract a fidelity gate judges a descriptor spec
against. It is prose-for-a-model.
"""

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from substrates import RDKIT_DESCRIPTOR_CONTRACT  # noqa: E402
