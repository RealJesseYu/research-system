"""
run_cas_offinder — the Cas-OFFinder (CRISPR off-target enumeration) wrapper.

Plain, deterministic code. NO AI inside, ever. BIO Wave D.2. **RE-TIERED T1 ->
DEFERRED (owner-ruled 2026-07-18):** Cas-OFFinder does all its work in an OpenCL
kernel, and the only CPU OpenCL runtime on this colima/aarch64 host (pocl) does
NOT compute correctly — it exits 0 and returns 0 matches from a kernel that did
not run. For CRISPR, a fabricated "0 off-targets" is the DANGEROUS wrong answer
(reads as "safe"). So this substrate enrolls INERT (`calibrating`/
`routable=False`), its real measured envelope (card §3A) is
PENDING-PROVISIONING, and the real battery may only run in an environment where
the kernel is first validated (see THE KNOWN-ANSWER GUARD).

Pinned install: cas-offinder 2.4.1 + pocl 7.1 (bioconda/conda-forge, aarch64),
in container `cas-offinder-prod` (from `cas-offinder-img`, the reusable
bioconda base). Availability is fine; kernel correctness on this host is the
block.

*** THE KNOWN-ANSWER GUARD (the did-it-work signal) ***
Cas-OFFinder's exit code and match count are BOTH untrustworthy when the kernel
is broken (exit 0, count 0). So before trusting ANY count, the wrapper runs a
baked KNOWN-ANSWER PROBE: a tiny genome containing exactly one known-present
guide+PAM site. If the probe does NOT find that site (>=1 match), the kernel is
not computing correctly and the wrapper REFUSES — qoi=None, a setup_error. A
real off-target count is returned ONLY when the probe passes first. In this
host the probe finds 0 -> the wrapper always refuses (proven by triggering);
in a validated-kernel environment the probe passes and counts are returned.
This is the RE-VALIDATION GATE that must hold to un-defer the substrate.

Typed input:
    run_cas_offinder({
      "genome": "probe",            # a baked allowlist genome (real genomes
                                    # baked at provisioning)
      "guide": "ACGT...20nt",       # the 20-nt protospacer
      "mismatches": 3,              # max mismatches in the protospacer
      "quantity": "off_target_count",
    })

Return (and ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from tools.docker_exec import CLIENT_GRACE_S

DOCKER_CONTEXT = "colima"
CONTAINER = "cas-offinder-prod"
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_cas_offinder"
SHARED_CONTAINER = "/work/cases"
PROBE_GENOME_DIR = "/opt/probe/gdir"   # baked: one known-present site
PROBE_GUIDE_FILE = "/opt/probe/guide.txt"

TIMEOUT_SECONDS = 600
MAX_RETRIES = 1
MAX_DIAG_CHARS = 800

GUIDE_LEN = 20                          # SpCas9 protospacer length (PAM appended)
MAX_MISMATCHES = 10
_DNA_RE = re.compile(r"^[ACGT]+$")


class CasOffinderInputError(ValueError):
    """The typed input is not a runnable off-target query."""


_REQUIRED_FIELDS = ("genome", "guide", "mismatches", "quantity")
GENOME_ALLOWLIST = ("probe",)          # baked genomes; real genomes at provisioning
GENOME_DIRS = {"probe": PROBE_GENOME_DIR}
QOI_FIELDS = ("off_target_count",)


def _validate_input(spec: dict) -> dict:
    """Return a clean copy, or raise CasOffinderInputError. Pure, pre-run."""
    if not isinstance(spec, dict):
        raise CasOffinderInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise CasOffinderInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise CasOffinderInputError(
            f"unsupported field(s): {', '.join(sorted(extra))}")

    if spec["genome"] not in GENOME_ALLOWLIST:
        raise CasOffinderInputError(
            f"genome {spec['genome']!r} is not a baked allowlist genome "
            f"(allowed: {', '.join(GENOME_ALLOWLIST)})")
    guide = spec["guide"]
    if not isinstance(guide, str) or not _DNA_RE.match(guide):
        raise CasOffinderInputError("'guide' must be a DNA string over A/C/G/T")
    if len(guide) != GUIDE_LEN:
        raise CasOffinderInputError(
            f"'guide' must be exactly {GUIDE_LEN} nt (the protospacer length "
            f"this pattern searches); got {len(guide)}")
    mm = spec["mismatches"]
    if not isinstance(mm, int) or isinstance(mm, bool) or not (0 <= mm <= MAX_MISMATCHES):
        raise CasOffinderInputError(
            f"'mismatches' must be an int in [0, {MAX_MISMATCHES}], got {mm!r}")
    if spec["quantity"] not in QOI_FIELDS:
        raise CasOffinderInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"genome": spec["genome"], "guide": guide, "mismatches": mm,
            "quantity": spec["quantity"]}


# The in-container orchestrator (bash — cas-offinder is a CLI). It runs the
# KNOWN-ANSWER PROBE first; only if the probe finds the known site does it run
# the caller's real query. cas-offinder needs /opt/conda/bin on PATH so pocl can
# find its linker.
_RUNNER = r'''#!/bin/bash
export PATH=/opt/conda/bin:$PATH
JOB="$1"
cd "$JOB"
PAT="$(printf 'N%.0s' $(seq 1 20))NGG"
PG="$(cat /opt/probe/guide.txt)"
# --- known-answer probe: a known-present site MUST be found ---
printf '%s\n%s\n%sNNN 0\n' "PROBE_GENOME_DIR" "$PAT" "$PG" > probe.txt
rm -f probe_out.txt
cas-offinder probe.txt C probe_out.txt >/dev/null 2>&1
PC=$(grep -c . probe_out.txt 2>/dev/null); PC=${PC:-0}
if [ "$PC" -lt 1 ]; then echo "GUARD_FAIL probe_matches=$PC"; exit 0; fi
# --- real query (input.txt written by the wrapper) ---
rm -f real_out.txt
cas-offinder input.txt C real_out.txt >/dev/null 2>&1
if [ ! -f real_out.txt ]; then echo "REAL_ERROR no_output"; exit 0; fi
RC=$(grep -c . real_out.txt 2>/dev/null); RC=${RC:-0}
echo "COUNT=$RC"
'''.replace("PROBE_GENOME_DIR", PROBE_GENOME_DIR)


def preflight() -> str | None:
    try:
        proc = subprocess.run(["docker", "--context", DOCKER_CONTEXT, "info"],
                              capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return "docker CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return "docker daemon did not respond within 60s (is colima up?)"
    if proc.returncode != 0:
        first = (proc.stderr.strip().splitlines() or ["docker info failed"])[0]
        return f"docker daemon unreachable on context {DOCKER_CONTEXT!r}: {first}"
    try:
        proc = subprocess.run(
            ["docker", "--context", DOCKER_CONTEXT, "inspect", "-f",
             "{{.State.Running}}", CONTAINER],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return f"docker inspect {CONTAINER} timed out"
    if proc.returncode != 0:
        return f"container {CONTAINER!r} does not exist (create it from cas-offinder-img)"
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


def _run_runner(job: str) -> tuple[int, str, str]:
    job_dir = f"{SHARED_CONTAINER}/{job}"
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER,
           "timeout", str(TIMEOUT_SECONDS),
           "bash", f"{job_dir}/run.sh", job_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + CLIENT_GRACE_S)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def run_cas_offinder(spec: dict) -> dict:
    """Enumerate CRISPR off-targets — but ONLY behind the known-answer guard.
    Returns the small dict at the top of this module. qoi is NEVER a count from
    an unvalidated kernel: if the baked known-answer probe does not find its
    known-present site, the wrapper refuses (valid=False, qoi=None)."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except CasOffinderInputError as e:
        return fail(f"input rejected: {e}")

    reason = preflight()
    if reason:
        return fail(f"substrate not ready: {reason}")

    job = f"casoff_{int(wall_start * 1000)}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    pattern = "N" * GUIDE_LEN + "NGG"
    genome_dir = GENOME_DIRS[clean["genome"]]
    (case_dir / "input.txt").write_text(
        f"{genome_dir}\n{pattern}\n{clean['guide']}NNN {clean['mismatches']}\n")
    (case_dir / "run.sh").write_text(_RUNNER)

    returncode, out, err = -1, "", ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            returncode, out, err = _run_runner(job)
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"cas-offinder exceeded {TIMEOUT_SECONDS}s timeout and was killed")
        if not out and err and attempt < MAX_RETRIES:
            continue
        break

    if out.startswith("GUARD_FAIL"):
        return fail(
            "known-answer guard FAILED: the baked known-present probe site was "
            "not found, so the OpenCL kernel is not computing correctly in this "
            "environment — refusing to return any off-target count (a broken "
            "kernel exits 0 with 0 matches, indistinguishable from a real 0). "
            f"[{out}] This substrate is DEFERRED until a validated-kernel host.")
    if out.startswith("REAL_ERROR") or not out.startswith("COUNT="):
        return fail(f"cas-offinder produced no usable output: {out or err or 'no output'}")

    try:
        count = int(out.split("=", 1)[1].strip())
    except (ValueError, IndexError):
        return fail(f"could not parse off-target count from: {out!r}")

    diagnostics = (f"cas-offinder off-target enumeration on genome "
                   f"{clean['genome']!r}, guide {clean['guide']}, "
                   f"<= {clean['mismatches']} mismatches; known-answer guard "
                   f"PASSED; off_target_count={count}")
    return {"valid": True, "qoi": float(count),
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


# CLI: venv/bin/python3 tools/run_cas_offinder.py  (refuses here — kernel unvalidated)
if __name__ == "__main__":
    default = {"genome": "probe", "guide": "ACGGTCATGCAAGTCCTGAT",
               "mismatches": 3, "quantity": "off_target_count"}
    print(json.dumps(run_cas_offinder(default), indent=2))
