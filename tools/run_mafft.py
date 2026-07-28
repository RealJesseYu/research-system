"""
run_mafft — the production MAFFT (multiple-sequence-alignment) wrapper.
BIO Wave D.2, T2. Plain, deterministic code. NO AI inside, ever. At build time
UNREGISTERED and INERT: enrolls `calibrating`/`routable=False`.

Shape mirrors the prior wrappers: typed input -> docker exec into `mafft-prod`
(bind-mounted cases_mafft/), hard timeout, one retry, capped diagnostics, output
summarized at the wrapper, NO LLM. MAFFT is pure CLI (no OpenCL/GPU/network), so
its measured envelope is real here.

REGIME (card unit = (mafft, msa_alignment)). A multiple sequence ALIGNMENT: the
tool arranges the input sequences into columns of putative homology. FILTER/
answer-class — but with the NARROWEST trust claim of any substrate in the wave.

*** THE DID-IT-WORK SIGNAL IS ON THE INPUT (owner-ruled 2026-07-18) ***
Alignment is a (near-)TOTAL function: feed MAFFT garbage and it returns a
well-formed alignment OF the garbage. So "MAFFT produced a well-formed alignment"
is NECESSARY but NOT SUFFICIENT — a well-formed alignment of junk is the
plausible-wrong-answer case. The STRICT gate is therefore on the INPUT, checked
BEFORE running: >= 2 sequences, each non-empty and valid, ALL over the same
alphabet (all protein OR all nucleotide) — i.e. actually alignable. Input that
fails this is refused up front; the wrapper never trusts an alignment of
un-alignable input.

TRUST CLAIM (the narrowest in the wave). The trust side is "an alignment MAFFT
COMPUTED, well-formed, used DESCRIPTIVELY" — NOT "the CORRECT alignment." The
C1-hole (M4): a computed alignment is a heuristic homology HYPOTHESIS,
guide-tree-dependent; a different tool/setting gives a different alignment. All
biological-correctness claims live in that gap.

Typed input:
    run_mafft({
      "sequences": ["MKTAY...", "MKTAI...", "MKTAY..."],  # >= 2, same alphabet
      "quantity": "alignment_identity",
    })

Return (ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}
The QoI is `alignment_identity`: the average pairwise percent identity over the
computed alignment (a descriptive statistic of the alignment, in [0, 100]).
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import time
import uuid
from pathlib import Path

from tools.docker_exec import CLIENT_GRACE_S

DOCKER_CONTEXT = "colima"
CONTAINER = "mafft-prod"
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_mafft"
SHARED_CONTAINER = "/work/cases"

TIMEOUT_SECONDS = 600
MAX_RETRIES = 1
MAX_DIAG_CHARS = 800
MAX_SEQS = 500
MAX_SEQ_LEN = 50_000


class MafftInputError(ValueError):
    """The typed input is not an alignable sequence set."""


_REQUIRED_FIELDS = ("sequences", "quantity")
# emit_artifacts (Phase 4, R-ART-7): opt-in file emit — the aligned FASTA under
# caller-chosen bare filenames. Optional; absent => byte-identical to before.
_ALLOWED_FIELDS = _REQUIRED_FIELDS + ("emit_artifacts",)
QOI_FIELDS = ("alignment_identity",)

_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$", re.IGNORECASE)      # protein
_NT_RE = re.compile(r"^[ACGTU]+$", re.IGNORECASE)                     # nucleotide


def _alphabet(seq: str) -> str | None:
    """'nt', 'aa', or None. Nucleotide is the stricter test, so it is tried
    first (a pure-ACGTU sequence is called nucleotide)."""
    if _NT_RE.match(seq):
        return "nt"
    if _AA_RE.match(seq):
        return "aa"
    return None


def _validate_input(spec: dict) -> dict:
    """Return a clean copy, or raise MafftInputError. THE STRICT INPUT GATE —
    pure, pre-run; the wrapper refuses un-alignable input BEFORE running MAFFT."""
    if not isinstance(spec, dict):
        raise MafftInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise MafftInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _ALLOWED_FIELDS]
    if extra:
        raise MafftInputError(f"unsupported field(s): {', '.join(sorted(extra))}")

    seqs = spec["sequences"]
    if not isinstance(seqs, list):
        raise MafftInputError("'sequences' must be a list of sequence strings")
    if len(seqs) < 2:
        raise MafftInputError(
            f"alignment needs >= 2 sequences; got {len(seqs)} — a single sequence "
            "is not an alignment")
    if len(seqs) > MAX_SEQS:
        raise MafftInputError(f"'sequences' has {len(seqs)} entries, over the {MAX_SEQS} cap")

    cleaned: list[str] = []
    alphabets: set[str] = set()
    for i, s in enumerate(seqs):
        if not isinstance(s, str) or not s.strip():
            raise MafftInputError(f"sequence #{i + 1} is empty or not a string")
        s = s.strip()
        if len(s) > MAX_SEQ_LEN:
            raise MafftInputError(
                f"sequence #{i + 1} is {len(s)} chars, over the {MAX_SEQ_LEN} cap")
        a = _alphabet(s)
        if a is None:
            raise MafftInputError(
                f"sequence #{i + 1} is not a valid protein or nucleotide sequence "
                "(contains non-residue characters)")
        alphabets.add(a)
        cleaned.append(s)
    if len(alphabets) != 1:
        raise MafftInputError(
            "sequences mix alphabets (protein and nucleotide) — they are not "
            "alignable together; all sequences must be the same alphabet")

    if spec["quantity"] not in QOI_FIELDS:
        raise MafftInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")

    # Phase 4 (R-ART-7): opt-in file emit. A composition step may ask for the
    # aligned FASTA under one or more bare filenames. Validated here, before the
    # run; absent (every existing caller), nothing changes.
    emit_raw = spec.get("emit_artifacts") or []
    if not isinstance(emit_raw, list):
        raise MafftInputError("'emit_artifacts' must be a list of filenames")
    emit_names = []
    for n in emit_raw:
        if not isinstance(n, str) or n != Path(n).name or n in ("", ".", ".."):
            raise MafftInputError(
                f"emit_artifacts name {n!r} must be a bare filename (no path parts)")
        emit_names.append(n)

    return {"sequences": cleaned, "alphabet": alphabets.pop(),
            "quantity": spec["quantity"], "emit_artifacts": emit_names}


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
        return f"container {CONTAINER!r} does not exist (create it from mafft-img)"
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


def _run_mafft(job: str) -> tuple[int, str, str]:
    job_dir = f"{SHARED_CONTAINER}/{job}"
    remote = (f"export PATH=/opt/conda/bin:$PATH; "
              f"mafft --auto --anysymbol {job_dir}/in.fa 2>{job_dir}/mafft.log; "
              f"cat {job_dir}/mafft.log >&2")
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER,
           "timeout", str(TIMEOUT_SECONDS), "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + CLIENT_GRACE_S)
    return proc.returncode, proc.stdout, proc.stderr


def _parse_fasta(text: str) -> list[str]:
    """Parse aligned-FASTA text into a list of (gapped) sequence strings."""
    seqs: list[str] = []
    cur: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if cur:
                seqs.append("".join(cur))
                cur = []
        elif line.strip():
            cur.append(line.strip())
    if cur:
        seqs.append("".join(cur))
    return seqs


def alignment_identity(aligned: list[str]) -> float:
    """Average pairwise percent identity over the alignment (columns where BOTH
    sequences are non-gap). Pure; deterministic. Raises on a malformed alignment
    (fewer than 2 rows, or unequal lengths)."""
    if len(aligned) < 2:
        raise ValueError("alignment has fewer than 2 rows")
    L = len(aligned[0])
    if any(len(a) != L for a in aligned):
        raise ValueError("alignment rows have unequal lengths — malformed alignment")
    pair_ids: list[float] = []
    for i in range(len(aligned)):
        for j in range(i + 1, len(aligned)):
            a, b = aligned[i], aligned[j]
            same = compared = 0
            for x, y in zip(a, b):
                if x == "-" or y == "-":
                    continue
                compared += 1
                if x.upper() == y.upper():
                    same += 1
            if compared:
                pair_ids.append(100.0 * same / compared)
    if not pair_ids:
        raise ValueError("no aligned column pairs to compare (all-gap overlap)")
    return sum(pair_ids) / len(pair_ids)


def run_mafft(spec: dict) -> dict:
    """Align >= 2 alignable sequences and return the average pairwise percent
    identity of the alignment. The STRICT INPUT GATE refuses un-alignable input
    BEFORE running MAFFT — a well-formed alignment of junk is never trusted."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    # THE STRICT INPUT GATE — before anything runs.
    try:
        clean = _validate_input(spec)
    except MafftInputError as e:
        return fail(f"input rejected (not alignable): {e}")

    reason = preflight()
    if reason:
        return fail(f"substrate not ready: {reason}")

    # UNIQUE PER CALL, not per millisecond. The job name was
    # f"...{int(wall_start*1000)}", so two calls landing in the same
    # millisecond shared a job directory — and each of these wrappers
    # CLEARS and rewrites that directory, so they would clobber each
    # other's inputs and read each other's result file. Sequential use was
    # assumed but never enforced, and the free agent can launch wrappers
    # concurrently from Bash. run_code and run_scipy already suffix a uuid.
    job = f"mafft_{int(wall_start * 1000)}_{uuid.uuid4().hex[:8]}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    fasta = "".join(f">s{i}\n{s}\n" for i, s in enumerate(clean["sequences"]))
    (case_dir / "in.fa").write_text(fasta)

    rc, out, err = -1, "", ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            rc, out, err = _run_mafft(job)
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"mafft exceeded {TIMEOUT_SECONDS}s timeout and was killed")
        if not out and rc != 0 and attempt < MAX_RETRIES:
            continue
        break

    if not out.strip():
        return fail(f"mafft produced no alignment output "
                    f"(exit {rc}): {err.strip().splitlines()[0] if err.strip() else 'no output'}")

    aligned = _parse_fasta(out)
    if len(aligned) != len(clean["sequences"]):
        return fail(f"mafft returned {len(aligned)} aligned rows for "
                    f"{len(clean['sequences'])} inputs — malformed alignment")
    try:
        ident = alignment_identity(aligned)
    except ValueError as e:
        return fail(f"alignment produced but unusable: {e}")
    if not math.isfinite(ident):
        return fail(f"alignment_identity is not finite ({ident!r})")

    diagnostics = (f"mafft alignment of {len(aligned)} {clean['alphabet']} "
                   f"sequence(s), length {len(aligned[0])}; "
                   f"alignment_identity (avg pairwise %id) = {ident:.4f} "
                   f"[DESCRIPTIVE — a heuristic alignment, not 'the correct' one]")
    result = {"valid": True, "qoi": round(ident, 6),
              "diagnostics": diagnostics[:MAX_DIAG_CHARS],
              "runtime_s": round(time.time() - wall_start, 3)}
    # R-ART-7: opt-in emit. MAFFT has exactly one emittable artifact — the
    # aligned FASTA it just produced (`out`, already in-hand as captured stdout,
    # so nothing new is read from disk). Return it under each requested name.
    # Only present when asked: a normal call is the byte-identical 4-key summary.
    if clean["emit_artifacts"]:
        fasta_bytes = out.encode("utf-8")
        result["artifacts"] = {name: fasta_bytes for name in clean["emit_artifacts"]}
    return result


# CLI: venv/bin/python3 tools/run_mafft.py  (aligns three similar sequences)
if __name__ == "__main__":
    default = {
        "sequences": ["MKTAYIAKQRQISFVKSHFSRQLE",
                      "MKTAYIAKQRAISFVKSHFSRQLE",
                      "MKTAYIAKQRQISFVKSHYSRQLE"],
        "quantity": "alignment_identity",
    }
    print(json.dumps(run_mafft(default), indent=2))
