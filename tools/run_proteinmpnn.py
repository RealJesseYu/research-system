"""
run_proteinmpnn — the ProteinMPNN (inverse-folding sequence design) wrapper.
BIO Wave D.2. Plain, deterministic. NO AI in execution.

**DEFERRED (owner-ruled 2026-07-18):** ProteinMPNN is a neural model needing a
GPU + downloaded weights; no GPU on this aarch64 host. Enrolled INERT; card §3A
PENDING-PROVISIONING. The pure-Python INPUT gate is proven now; a valid input
returns the honest DEFERRED state — never a fabricated design score.

UN-DEFER REQUIREMENT (specific — a GPU model with mismatched weights = confident
garbage): a **GPU host** + the **PINNED official ProteinMPNN weights** (record
release + checksum at provisioning) + a **KNOWN-ANSWER VALIDATION RUN** (a
backbone with a known native sequence must reproduce an expected recovery) before
any §3A number is trusted.

REGIME (backbone_conditioned_sequence_design, FILTER-class): sequence-recovery is
a RELATIVE design screen within the training distribution — high recovery does
NOT mean the sequence folds or functions.

Typed input: run_proteinmpnn({"backbone": "demo_backbone", "quantity": "seq_recovery"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
"""
from __future__ import annotations
import json, time

_REQUIRED_FIELDS = ("backbone", "quantity")
BACKBONE_ALLOWLIST = ("demo_backbone",)   # real backbones baked at provisioning
QOI_FIELDS = ("seq_recovery",)


class ProteinMPNNInputError(ValueError):
    """The typed input is not a runnable design request."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ProteinMPNNInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise ProteinMPNNInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise ProteinMPNNInputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    if spec["backbone"] not in BACKBONE_ALLOWLIST:
        raise ProteinMPNNInputError(
            f"backbone {spec['backbone']!r} is not a baked allowlist backbone "
            f"(allowed: {', '.join(BACKBONE_ALLOWLIST)})")
    if spec["quantity"] not in QOI_FIELDS:
        raise ProteinMPNNInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"backbone": spec["backbone"], "quantity": spec["quantity"]}


def gpu_and_weights_available() -> str | None:
    """None when a GPU + validated pinned weights are present, else the DEFERRED
    reason. On this host: no GPU."""
    return ("no GPU + validated ProteinMPNN weights on this host — DEFERRED. "
            "Provision a GPU host, install the PINNED official weights, and pass "
            "a KNOWN-ANSWER validation run before trusting any number.")


def run_proteinmpnn(spec: dict) -> dict:
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except ProteinMPNNInputError as e:
        return fail(f"input rejected: {e}")
    reason = gpu_and_weights_available()
    if reason:
        return fail(f"substrate not ready: {reason}")
    raise NotImplementedError(  # pragma: no cover - unreachable until provisioned
        "the design path is wired at provisioning with validated GPU + pinned "
        "weights; unreachable while gpu_and_weights_available() defers")


if __name__ == "__main__":
    print(json.dumps(run_proteinmpnn({"backbone": "demo_backbone", "quantity": "seq_recovery"}), indent=2))
