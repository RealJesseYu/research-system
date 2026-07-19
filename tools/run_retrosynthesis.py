"""
run_retrosynthesis — the retrosynthetic route-search wrapper (AiZynthFinder /
ASKCOS class). BIO Wave D.2. Plain, deterministic. NO AI in execution.

**DEFERRED (owner-ruled 2026-07-18):** these are heavy models AND — crucially —
they query a REACTION ROUTE DATABASE / expansion backend (a DATA dependency
BEYOND model weights). Neither the models nor the backend are available here.
Enrolled INERT; card §3A PENDING-PROVISIONING. The pure-Python INPUT gate is
proven now; a valid input returns the honest DEFERRED state — never a fabricated
route.

UN-DEFER REQUIREMENT (specific — "GPU + weights" UNDERCOUNTS this tool): a host
with the heavy models AND the **reaction ROUTE DATABASE / expansion backend the
tool queries** (AiZynthFinder's policy+stock, or ASKCOS's reaction DB — name the
backend + version at provisioning), + a **KNOWN-ANSWER VALIDATION RUN** (a
molecule with a known feasible route) before any §3A number is trusted.

REGIME (retrosynthetic_route_search, FILTER-class): a found route is
TEMPLATE-feasible, not experimentally validated — never yields/conditions/
selectivity.

Typed input: run_retrosynthesis({"target_smiles": "CCO", "backend": "aizynth",
                                  "quantity": "synthesizability"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
"""
from __future__ import annotations
import json, re, time

_REQUIRED_FIELDS = ("target_smiles", "backend", "quantity")
BACKEND_ALLOWLIST = ("aizynth", "askcos")
QOI_FIELDS = ("synthesizability",)
_SMILES_RE = re.compile(r"^[A-Za-z0-9@+\-\[\]()=#$%./\\]+$")
MAX_SMILES = 4_000


class RetrosynthesisInputError(ValueError):
    """The typed input is not a runnable route-search request."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise RetrosynthesisInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise RetrosynthesisInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise RetrosynthesisInputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    smi = spec["target_smiles"]
    if not isinstance(smi, str) or not smi.strip():
        raise RetrosynthesisInputError("'target_smiles' must be a non-empty SMILES string")
    if len(smi) > MAX_SMILES:
        raise RetrosynthesisInputError(f"'target_smiles' is {len(smi)} chars, over {MAX_SMILES}")
    if not _SMILES_RE.match(smi.strip()):
        raise RetrosynthesisInputError("'target_smiles' contains characters not valid in SMILES")
    if spec["backend"] not in BACKEND_ALLOWLIST:
        raise RetrosynthesisInputError(
            f"backend {spec['backend']!r} is not on the allowlist "
            f"(allowed: {', '.join(BACKEND_ALLOWLIST)})")
    if spec["quantity"] not in QOI_FIELDS:
        raise RetrosynthesisInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"target_smiles": smi.strip(), "backend": spec["backend"],
            "quantity": spec["quantity"]}


def models_and_backend_available() -> str | None:
    """None when the heavy models AND the reaction route database/backend are
    present, else the DEFERRED reason. On this host: neither is available."""
    return ("the retrosynthesis models AND their reaction ROUTE DATABASE / "
            "expansion backend are not available here — DEFERRED. Provision the "
            "heavy models AND the backend the tool queries (AiZynth policy+stock "
            "or ASKCOS reaction DB), and pass a KNOWN-ANSWER run — 'GPU + weights' "
            "alone undercounts this tool's DATA dependency.")


def run_retrosynthesis(spec: dict) -> dict:
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except RetrosynthesisInputError as e:
        return fail(f"input rejected: {e}")
    reason = models_and_backend_available()
    if reason:
        return fail(f"substrate not ready: {reason}")
    raise NotImplementedError(  # pragma: no cover - unreachable until provisioned
        "the route-search path is wired at provisioning with the models + "
        "backend; unreachable while models_and_backend_available() defers")


if __name__ == "__main__":
    print(json.dumps(run_retrosynthesis({"target_smiles": "CCO", "backend": "aizynth", "quantity": "synthesizability"}), indent=2))
