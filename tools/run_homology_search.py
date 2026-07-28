"""
run_homology_search — the production sequence-homology-search wrapper (the
BLAST+HMMER bundle, BIO Wave D.2, T2). ONE substrate `homology_search`; the
`tool` field selects the backend {blast, hmmer} (the ruled B bundle). This
increment wires the BLAST backend; the HMMER backend is added in the next
increment (same substrate, same card).

Plain, deterministic code. NO AI inside, ever. At build time UNREGISTERED and
INERT: enrolls `calibrating`/`routable=False`; nothing routes to it until a D.4
promotion ruling. cas-offinder-img is the reusable bioconda base; BLAST is pure
CLI (no OpenCL), so its measured envelope is real here.

Shape mirrors the prior wrappers: typed input -> docker exec into
`homology-search-prod` (bind-mounted cases_homology/, databases BAKED into the
image at /opt/blastdb/), hard timeout, one retry, capped diagnostics, output
summarized at the wrapper, NO LLM.

REGIME (card unit = (homology_search, homology_search)). A local
sequence-similarity search against a validly-built database, with Karlin-Altschul
e-value statistics. FILTER-class: the e-value is the SIGNIFICANCE of similarity, a
relative screen — not homology or function.

*** THE DID-IT-WORK SIGNAL (owner-ruled 2026-07-18) ***
BLAST's dangerous failure is "real-looking output that isn't what was asked for":
a missing/malformed database makes blastp print a DB error to STDERR and **exit
0 with no hits** — indistinguishable from a legitimate "no significant hits" if
you only check the exit code. So the signal is NOT exit 0; it is: the search ran
against a validly-built DB with NO error on stderr. On any BLAST error marker the
wrapper returns valid=False (setup_error) — distinct from a clean run that found
0 hits (valid=True, qoi=None: a real "no homolog at this cutoff"). This is the
sequence-search analog of cobrapy's status gate.

Typed input:
    run_homology_search({
      "database": "demo_prot",      # a baked allowlist database
      "query": "MKTAYIAK...",       # a protein sequence
      "tool": "blast",              # backend {blast, hmmer}; hmmer pending
      "quantity": "e_value",
    })

Return (ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}
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
CONTAINER = "homology-search-prod"
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_homology"
SHARED_CONTAINER = "/work/cases"

TIMEOUT_SECONDS = 600
MAX_RETRIES = 1
MAX_DIAG_CHARS = 800
MAX_QUERY_LEN = 40_000


class HomologySearchInputError(ValueError):
    """The typed input is not a runnable homology search."""


_REQUIRED_FIELDS = ("database", "query", "tool", "quantity")

# database -> in-container DB path (BAKED into homology-search-img).
# `_broken_selftest` is a documented FAULT-INJECTION entry (points at a
# non-existent DB) used to PROVE the DB-integrity jail by triggering it — the
# sequence-search analog of cas_offinder's known-answer probe.
DATABASE_PATHS = {
    "demo_prot": "/opt/blastdb/demo_prot",
    "_broken_selftest": "/opt/blastdb/_no_such_db",
}
DATABASE_ALLOWLIST = tuple(DATABASE_PATHS)

# HMMER (hmmsearch) searches a PROFILE against a target sequence FASTA. HMMER has
# TWO integrity surfaces BLAST lacks: the PROFILE and the TARGET, each separately
# breakable, each producing plausible-looking output when broken. So the hmmer
# `query` names a baked PROFILE (not a sequence), and `database` names a baked
# target FASTA. `_broken_profile` is the PROFILE-integrity fault injection (a
# malformed/empty HMM); `_broken_selftest` reuses the missing-target injection.
PROFILE_PATHS = {
    "demo_hmm": "/opt/hmm/demo_hmm.hmm",
    "_broken_profile": "/opt/hmm/_broken_profile.hmm",
}
PROFILE_ALLOWLIST = tuple(PROFILE_PATHS)
# hmmer target FASTA per database name (the same baked demo_prot sequences).
TARGET_FASTA_PATHS = {
    "demo_prot": "/opt/blastdb/demo_prot.fa",
    "_broken_selftest": "/opt/blastdb/_no_such_target.fa",
}

TOOLS = ("blast", "hmmer")           # the ruled BLAST+HMMER bundle
QOI_FIELDS = ("e_value",)

_PROT_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZ*]+$", re.IGNORECASE)

# BLAST error markers on stderr — exit code is NOT trusted (a missing DB exits 0).
_BLAST_ERROR_MARKERS = (
    "blast database error",
    "database memory map file error",
    "no such file",
    "cannot",
    "error:",
    "could not",
    "not found",
)
# HMMER error markers — exit code is likewise NOT trusted (a malformed HMM exits
# 0). Covers BOTH integrity surfaces: profile ("file format problem", "parse
# failed") and target ("failed to open", "no such file").
_HMMER_ERROR_MARKERS = (
    "file format problem",   # profile surface: a malformed/empty HMM
    "parse failed",          # profile surface
    "failed to open",        # target surface: unreadable target FASTA
    "no such file",          # target surface
    "fatal exception",       # HMMER's hard-error prefix
)


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise HomologySearchInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise HomologySearchInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise HomologySearchInputError(f"unsupported field(s): {', '.join(sorted(extra))}")

    tool = spec["tool"]
    if tool not in TOOLS:
        raise HomologySearchInputError(
            f"tool {tool!r} is not supported (allowed: {', '.join(TOOLS)})")
    if spec["database"] not in DATABASE_ALLOWLIST:
        raise HomologySearchInputError(
            f"database {spec['database']!r} is not a baked allowlist database "
            f"(allowed: {', '.join(DATABASE_ALLOWLIST)})")
    query = spec["query"]
    if not isinstance(query, str) or not query.strip():
        raise HomologySearchInputError("'query' must be a non-empty string")
    query = query.strip()
    # `query` is interpreted per backend: a protein SEQUENCE for blast, a baked
    # PROFILE name for hmmer (the bundle's tool field selects the vocabulary).
    if tool == "blast":
        if len(query) > MAX_QUERY_LEN:
            raise HomologySearchInputError(
                f"'query' is {len(query)} chars, over the {MAX_QUERY_LEN} cap")
        if not _PROT_RE.match(query):
            raise HomologySearchInputError(
                "'query' must be a protein sequence (amino-acid letters only) for "
                "tool='blast'")
    else:  # hmmer
        if query not in PROFILE_ALLOWLIST:
            raise HomologySearchInputError(
                f"for tool='hmmer', 'query' must be a baked profile name "
                f"(allowed: {', '.join(PROFILE_ALLOWLIST)}); got {query!r}")
    if spec["quantity"] not in QOI_FIELDS:
        raise HomologySearchInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"database": spec["database"], "query": query,
            "tool": tool, "quantity": spec["quantity"]}


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
        return f"container {CONTAINER!r} does not exist (create it from homology-search-img)"
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


def _run_blast(job: str, db_path: str) -> tuple[int, str, str]:
    """Run blastp for the job's query against db_path. Returns (rc, stdout,
    stderr). PATH carries /opt/conda/bin so the conda blast is found."""
    job_dir = f"{SHARED_CONTAINER}/{job}"
    remote = (f"export PATH=/opt/conda/bin:$PATH; "
              f"blastp -query {job_dir}/query.fa -db {db_path} -outfmt '6 evalue'")
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER,
           "timeout", str(TIMEOUT_SECONDS), "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + CLIENT_GRACE_S)
    return proc.returncode, proc.stdout, proc.stderr


def _run_hmmer(job: str, profile_path: str, target_path: str) -> tuple[int, str, str]:
    """Run hmmsearch of a PROFILE against a target FASTA. Returns (rc, stdout,
    stderr) where stdout is one full-sequence E-value per line (parsed from
    --tblout column 5, in-container) and stderr carries hmmsearch's report/log so
    the wrapper's marker scan can see BOTH integrity surfaces (profile: 'file
    format problem'; target: 'failed to open')."""
    job_dir = f"{SHARED_CONTAINER}/{job}"
    remote = (
        f"export PATH=/opt/conda/bin:$PATH; "
        f"hmmsearch --tblout {job_dir}/tbl.txt {profile_path} {target_path} "
        f"> {job_dir}/hmmer.log 2>&1; "
        f"grep -v '^#' {job_dir}/tbl.txt 2>/dev/null | awk 'NF>=5{{print $5}}'; "
        f"cat {job_dir}/hmmer.log >&2")
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER,
           "timeout", str(TIMEOUT_SECONDS), "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + CLIENT_GRACE_S)
    return proc.returncode, proc.stdout, proc.stderr


def run_homology_search(spec: dict) -> dict:
    """Run one homology search behind the DID-IT-WORK signal. The e-value QoI is
    returned only when the search provably ran against a valid DB with no error;
    a clean run with 0 hits returns valid=True/qoi=None (a real 'no homolog'),
    distinct from a DB/query error which returns valid=False."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except HomologySearchInputError as e:
        return fail(f"input rejected: {e}")

    reason = preflight()
    if reason:
        return fail(f"substrate not ready: {reason}")

    tool = clean["tool"]
    # UNIQUE PER CALL, not per millisecond. The job name was
    # f"...{int(wall_start*1000)}", so two calls landing in the same
    # millisecond shared a job directory — and each of these wrappers
    # CLEARS and rewrites that directory, so they would clobber each
    # other's inputs and read each other's result file. Sequential use was
    # assumed but never enforced, and the free agent can launch wrappers
    # concurrently from Bash. run_code and run_scipy already suffix a uuid.
    job = f"hsearch_{int(wall_start * 1000)}_{uuid.uuid4().hex[:8]}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)

    # Dispatch on the bundle's tool field. The BLAST path is unchanged; the HMMER
    # path gates on the SAME kind of stderr signal but its own marker set,
    # covering HMMER's two integrity surfaces (profile AND target).
    if tool == "blast":
        (case_dir / "query.fa").write_text(f">q\n{clean['query']}\n")
        runner = lambda: _run_blast(job, DATABASE_PATHS[clean["database"]])
        markers = _BLAST_ERROR_MARKERS
    else:  # hmmer
        runner = lambda: _run_hmmer(
            job, PROFILE_PATHS[clean["query"]],
            TARGET_FASTA_PATHS[clean["database"]])
        markers = _HMMER_ERROR_MARKERS

    rc, out, err = -1, "", ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            rc, out, err = runner()
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"{tool} exceeded {TIMEOUT_SECONDS}s timeout and was killed")
        if not out and not err and rc != 0 and attempt < MAX_RETRIES:
            continue
        break

    # THE DID-IT-WORK SIGNAL: an error marker means the search could NOT run
    # (bad/missing DB or, for hmmer, a malformed PROFILE) — NOT a legitimate
    # 0-hits. Exit code is not trusted (both tools can error at exit 0).
    low_err = err.lower()
    hit = next((m for m in markers if m in low_err), None)
    if hit:
        first = next((ln for ln in err.strip().splitlines()
                      if hit in ln.lower()), f"{tool} error")
        surface = ("profile/target integrity" if tool == "hmmer" else "DB integrity")
        return fail(f"homology search ({tool}) could not run — {surface} failure, "
                    f"NOT a 'no-hits' result: {first.strip()[:200]}")

    # search ran cleanly. Parse e-values; 0 lines == a real 'no significant hit'.
    evalues: list[float] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evalues.append(float(line.split()[0]))
        except (ValueError, IndexError):
            return fail(f"{tool} produced an unparseable e-value row: {line[:80]!r}")

    if not evalues:
        return {"valid": True, "qoi": None,
                "diagnostics": (f"{tool} search ran cleanly on {clean['database']!r}; "
                                f"0 significant hits (no e-value — a real 'no "
                                f"homolog at this cutoff')")[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    best = min(evalues)
    if not math.isfinite(best):
        return fail(f"best e-value is not finite ({best!r}) — refusing to return it")
    diagnostics = (f"{tool} search on {clean['database']!r}: {len(evalues)} hit(s); "
                   f"best (min) e_value={best:g}")
    return {"valid": True, "qoi": float(best),
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


# CLI: venv/bin/python3 tools/run_homology_search.py  (known-hit self-check)
if __name__ == "__main__":
    default = {
        "database": "demo_prot",
        "query": ("MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEK"
                  "AVQVKVKALPDAQFEVVHSLAKWKR"),
        "tool": "blast", "quantity": "e_value",
    }
    print(json.dumps(run_homology_search(default), indent=2))
