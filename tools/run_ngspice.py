"""
run_ngspice — the production ngspice (linear passive circuit) solver wrapper.

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_cfd.py holds for OpenFOAM and run_fea.py holds for CalculiX. This
wrapper is REGISTERED and ROUTABLE: promoted at the R2 flip (owner ruling,
2026-07-17) — its contract is enrolled in tools/substrate_registry.py, its QoI
vocabulary and regime semantics are wired in tools/qoi_vocab.py from this
module's own constants, and stage 4 reaches it through the dispatch seam.
(TRUTH-EDIT, R-23.5-5b, 2026-07-17: the previous "UNREGISTERED at build time"
sentence was written at this wrapper's birth and went stale at the R2
promotion flip; grep-verified before editing that this docstring enters no
composed prompt.)

Shape mirrors run_fea:
  * a typed input is turned into a full ngspice deck by deterministic Python
    (no LLM anywhere in the execution step);
  * the deck runs inside the `ngspice-prod` container (bind-mounted
    cases_ngspice/, mirroring of12-prod / ccx-prod), with a hard timeout and
    ONE retry on transient failure;
  * ngspice's raw log and wrdata output are parsed down to a SMALL summary and
    the raw log NEVER leaves the wrapper.

Typed input:
    run_ngspice({
      "netlist_body": "V1 in 0 DC 10\\nR1 in out 1k\\nR2 out 0 2k",
      "analysis": {"type": "op"},
      "qoi": {"kind": "node_voltage", "target": "out",
              "reduction": "op_value", "at": None},
    })

Return (and ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}

WHO OWNS WHAT
-------------
The CALLER supplies circuit element lines ONLY. The WRAPPER owns every
dot-command, the .control block, the analysis statement, the wrdata call, and
the .end. This is why `.`-lines are rejected outright (see the screen below):
allowing them would let a caller redefine the analysis the wrapper believes it
ran, or pull in arbitrary files.

THE REGIME SCREEN (verbatim; this IS the regime boundary, enforced pre-solve)
----------------------------------------------------------------------------
Every rule below names the offending line and the reason. Rejection happens
BEFORE any solve, and a rejected input never reaches the container.

  1. SIZE.  netlist_body is capped at 200 lines / 20000 bytes.
  2. ALLOWED ELEMENT LETTERS (case-insensitive), first character of the line:
         R  resistor
         L  inductor
         C  capacitor
         V  independent voltage source
         I  independent current source
         E  linear voltage-controlled voltage source
         F  linear current-controlled current source
         G  linear voltage-controlled current source
         H  linear current-controlled voltage source
     Every other letter is rejected by letter and line, including:
         D Q M J B T O U S W A X K N P  and any unknown letter.
     K (coupled inductors) is excluded from v1 DELIBERATELY — mutual coupling
     is linear and would fit the regime, but it is untested here. It is an
     OPEN CARD QUESTION, not an oversight.
  3. DOT-LINES.  Any line whose first non-blank character is `.` is rejected.
     This bans .model, .subckt, .include, .lib, .param, .ic, .options, .tran,
     .ac, .dc, .op and everything else BY CONSTRUCTION rather than by listing.
  4. NONLINEAR / EXPRESSION FORMS.  On E/F/G/H lines the tokens POLY, TABLE,
     and `value=` are rejected (matched case-insensitively, on word
     boundaries, so a node merely named "table" is not a false positive).
     A `{` ANYWHERE in the body is rejected — braces are ngspice's expression
     interpolation syntax and admit arbitrary nonlinear behaviour.
  5. COMPONENT VALUES.  An R/L/C line must be EXACTLY
         <name> <node+> <node-> <value>
     — four tokens. The value is parsed with a deterministic SPICE number parser
     and must be > 0. A non-positive value, an unparseable value, or ANY extra
     trailing token (a model name, `ac=`, `temp=`, `tc1=`, `m=`, `ic=` ...) is
     rejected by name pre-solve. See "WHY RULE 5 IS LOAD-BEARING" below.
  6. COMMENTS.  `*` comment lines and in-line `;` comments are permitted and
     ignored by the screen; a `+` continuation line is rejected in v1 (the
     screen classifies lines independently and cannot see what it continues).

WHY RULE 5 IS LOAD-BEARING (two measured findings, not precautions)
------------------------------------------------------------------
Both were MEASURED on ngspice-42, aarch64, in ngspice-prod. Both produce a
confident, plausible, WRONG number with exit code 0 and a clean log, so nothing
downstream of the solve can catch either. The pre-solve screen is the only
defence, which is why it is in code here and not in any prompt.

  (i) ZERO VALUE.  `R1 a 0 0` does not warn, does not set a nonzero exit code,
      and emits NO log marker. ngspice silently substitutes a minimum
      resistance and reports `i(v1) = -1.00000e+03` — a fabricated 1000 A
      through a short.

 (ii) TRAILING VALUE OVERRIDE.  `R1 in out 1k ac=100k` runs cleanly and reports
      an RC corner of 10.0 Hz where the written 1k implies 1000 Hz. The deck's
      stated value is not the simulated value, and no marker fires. Found by
      screening ngspice's own shipped test suite, where
      tests/resistance/res_partition.cir uses exactly this form.

WHY THE MARKER SCAN EXISTS (also measured)
------------------------------------------
MEASURED: a floating node (no DC path to ground) makes ngspice fail its
operating-point solve, fall through gmin stepping and source stepping, then
succeed at a transient operating point and print a plausible-looking answer
with exit code 0. The exit code is NOT a sufficient failure signal. Any marker
hit forces valid=False and qoi=None — the wrapper never returns a QoI when a
marker fired.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import time
import uuid
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration — the only knobs, kept in one place (mirrors run_fea.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"            # same colima VM as the CFD/FEA substrates
CONTAINER = "ngspice-prod"           # the production container; NOT ngspice-img
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_ngspice"  # Mac side
SHARED_CONTAINER = "/work/cases"     # same folder seen inside the container

TIMEOUT_SECONDS = 600                # hard cap so a stuck solver can't hang us
MAX_RETRIES = 1                      # ONE retry on a transient (infra) failure
MAX_DIAG_CHARS = 800                 # bound on how much diagnostic text we return

MAX_NETLIST_LINES = 200              # sanity caps on the caller's netlist body
MAX_NETLIST_BYTES = 20_000

# Docs-RAG index for the ngspice manual — a SEPARATE index from solver_docs and
# fea_docs, mirroring their layout under retrieval/.
_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
NGSPICE_DOCS_INDEX = _RETRIEVAL_DIR / "ngspice_docs_index.pkl"


class NgspiceInputError(ValueError):
    """The typed input is not a runnable linear-passive circuit config."""


# ----------------------------------------------------------------------------
# Typed input.
# ----------------------------------------------------------------------------
_REQUIRED_FIELDS = ("netlist_body", "analysis", "qoi")

_ANALYSIS_FIELDS = {
    "op": (),
    "dc": ("source", "start", "stop", "step"),
    "ac": ("variation", "n", "fstart", "fstop"),
    "tran": ("tstep", "tstop", "tmax"),
}
_AC_VARIATIONS = ("dec", "lin", "oct")

_QOI_KINDS = ("node_voltage", "vsource_current")
# `corner_3db` is an ADDITION to the originally-specified reduction list. The
# spec required the wrapper to extract the AC -3 dB corner by log-frequency
# interpolation, but listed no reduction that could express it. Rather than let
# the self-checks reach around the wrapper into the raw wrdata file (which would
# break "summarize at the wrapper"), the corner is a first-class ac-only
# reduction and goes through the same validation and marker scan as every other.
_REDUCTIONS = ("op_value", "final", "max", "min", "value_at", "corner_3db")

_REQUIRED_QOI_FIELDS = ("kind", "target", "reduction")

# A node/source name ngspice will accept, locked before it reaches a shell.
_NAME_RE = re.compile(r"^[A-Za-z0-9_#\.\-\+]+$")


# ----------------------------------------------------------------------------
# The SPICE number parser.
#
# Verified against ngspice-42 itself (a 1 A source across the resistor under
# test, reading back v(a) == R):
#     1k -> 1e3     1K   -> 1e3     1meg -> 1e6    1MEG -> 1e6
#     1m -> 1e-3    1M   -> 1e-3    1mil -> 2.54e-5
#     1u -> 1e-6    1n   -> 1e-9    1p   -> 1e-12  1f   -> 1e-15
#     1g -> 1e9     1t   -> 1e12
#     1kohm -> 1e3  (trailing alpha noise ignored)
#     1e3   -> 1e3  (exponent form)
#     1x    -> 1.0  (UNKNOWN suffix is silently ignored, not an error)
# Two traps this encodes: `m` is milli and `meg` is 1e6 (so `1M` is a
# MILLIohm, not a megohm), and `1F` is femto, not farads.
# ----------------------------------------------------------------------------
_NUM_RE = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# Order matters: the multi-character suffixes must be tried before `m`.
_SUFFIXES = (
    ("meg", 1e6),
    ("mil", 25.4e-6),
    ("f", 1e-15),
    ("p", 1e-12),
    ("n", 1e-9),
    ("u", 1e-6),
    ("m", 1e-3),
    ("k", 1e3),
    ("g", 1e9),
    ("t", 1e12),
)


def parse_spice_number(token: str) -> float | None:
    """Parse a SPICE component value like '1k', '2.5meg', '1e3', '4.7u'.

    Returns the float value, or None if `token` has no leading number at all.
    Mirrors ngspice-42's measured behaviour, including silently ignoring an
    unknown or trailing alphabetic suffix (`1kohm` -> 1e3, `1x` -> 1.0).
    """
    if token is None:
        return None
    tok = token.strip()
    m = _NUM_RE.match(tok)
    if not m:
        return None
    value = float(m.group(0))
    rest = tok[m.end():].lower()
    for suffix, mult in _SUFFIXES:
        if rest.startswith(suffix):
            return value * mult
    return value


# ----------------------------------------------------------------------------
# The regime screen. Pure, deterministic, pre-solve. See the module docstring
# for the authoritative rule list.
# ----------------------------------------------------------------------------
ALLOWED_ELEMENT_LETTERS = frozenset("RLCVIEFGH")
_CONTROLLED_SOURCE_LETTERS = frozenset("EFGH")
_PASSIVE_LETTERS = frozenset("RLC")

_BANNED_EXPR_RE = re.compile(r"\b(poly|table)\b|\bvalue\s*=", re.IGNORECASE)


def _strip_comment(line: str) -> str:
    """Drop an in-line `;` comment; ngspice treats the rest of the line as prose."""
    return line.split(";", 1)[0]


def screen_netlist(netlist_body: str) -> list[str]:
    """Return a list of rejection reasons (EMPTY list == the body passes v1).

    Every reason names the offending line number and the reason. Pure: never
    runs anything, never touches the container.
    """
    reasons: list[str] = []

    if not isinstance(netlist_body, str):
        return [f"netlist_body must be a string, got {type(netlist_body).__name__}"]
    if not netlist_body.strip():
        return ["netlist_body is empty — no circuit to solve"]

    n_bytes = len(netlist_body.encode("utf-8"))
    if n_bytes > MAX_NETLIST_BYTES:
        reasons.append(f"netlist_body is {n_bytes} bytes, over the {MAX_NETLIST_BYTES}-byte cap")
    raw_lines = netlist_body.splitlines()
    if len(raw_lines) > MAX_NETLIST_LINES:
        reasons.append(f"netlist_body is {len(raw_lines)} lines, over the {MAX_NETLIST_LINES}-line cap")

    if "{" in netlist_body:
        for i, line in enumerate(raw_lines, start=1):
            if "{" in line:
                reasons.append(
                    f"line {i}: '{line.strip()}' — '{{' (expression interpolation) is not "
                    f"allowed in the linear-passive regime"
                )

    for i, raw in enumerate(raw_lines, start=1):
        line = _strip_comment(raw).strip()
        if not line or line.startswith("*"):
            continue                                   # comment / blank: ignored
        if line.startswith("."):
            reasons.append(
                f"line {i}: '{line}' — dot-commands are owned by the wrapper, not the "
                f"caller; the netlist body carries circuit elements only"
            )
            continue
        if line.startswith("+"):
            reasons.append(
                f"line {i}: '{line}' — continuation lines are not supported in v1; "
                f"write the element on a single line"
            )
            continue

        letter = line[0].upper()
        if letter not in ALLOWED_ELEMENT_LETTERS:
            reasons.append(
                f"line {i}: '{line}' — element letter '{line[0]}' is outside the "
                f"linear-passive regime (allowed: "
                f"{' '.join(sorted(ALLOWED_ELEMENT_LETTERS))})"
            )
            continue

        if letter in _CONTROLLED_SOURCE_LETTERS:
            hit = _BANNED_EXPR_RE.search(line)
            if hit:
                reasons.append(
                    f"line {i}: '{line}' — '{hit.group(0)}' form on a controlled source is "
                    f"nonlinear/expression-valued; only the plain linear-gain form passes v1"
                )
                continue

        if letter in _PASSIVE_LETTERS:
            reasons.extend(_screen_passive_value(i, line, letter))

    return reasons


def _screen_passive_value(lineno: int, line: str, letter: str) -> list[str]:
    """R/L/C must be EXACTLY '<name> <node+> <node-> <value>', with a value that
    parses and is strictly positive.

    The exact-arity rule is not pedantry. ngspice's general form for a passive is
        RXXXX n+ n- <value> <mname> <m=..> <scale=..> <temp=..> <tc1=..> <ic=..>
    and several of those trailing forms SILENTLY change the value that is
    actually simulated. MEASURED on prod: `R1 in out 1k ac=100k` reports an RC
    corner of 10.0 Hz — the deck's stated 1k is simply not what the AC analysis
    used, and every marker stays quiet. A netlist whose headline value is not the
    simulated value cannot honour the contract's promise that a QoI characterizes
    the netlist as provided, so v1 rejects the whole shape rather than trying to
    enumerate which trailing tokens are benign.
    """
    tokens = line.split()
    if len(tokens) < 4:
        return [f"line {lineno}: '{line}' — {letter} element needs "
                f"'<name> <node+> <node-> <value>'"]
    if len(tokens) > 4:
        return [f"line {lineno}: '{line}' — {letter} element takes exactly "
                f"'<name> <node+> <node-> <value>' in v1; the extra token(s) "
                f"{' '.join(tokens[4:])!r} select a model or a per-analysis/temperature "
                f"value override, which can silently change the simulated value away "
                f"from the one written here"]
    value = parse_spice_number(tokens[3])
    if value is None:
        return [f"line {lineno}: '{line}' — cannot parse the {letter} value "
                f"{tokens[3]!r} as a SPICE number"]
    if value <= 0:
        return [f"line {lineno}: '{line}' — {letter} value {tokens[3]!r} parses to "
                f"{value:g}, which is not positive; ngspice would silently substitute a "
                f"minimum value and return a fabricated result"]
    return []


# ----------------------------------------------------------------------------
# Input validation — reject by name, pre-solve (the _REQUIRED_FIELDS pattern).
# ----------------------------------------------------------------------------

def _validate_input(spec: dict) -> dict:
    """Return a clean copy of `spec`, or raise NgspiceInputError naming the field."""
    if not isinstance(spec, dict):
        raise NgspiceInputError(f"spec must be a dict, got {type(spec).__name__}")

    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise NgspiceInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise NgspiceInputError(
            f"unsupported field(s) for ngspice linear-passive v1: {', '.join(sorted(extra))}")

    analysis = _validate_analysis(spec["analysis"])
    qoi = _validate_qoi(spec["qoi"], analysis["type"])

    reasons = screen_netlist(spec["netlist_body"])
    if reasons:
        raise NgspiceInputError("netlist rejected by the regime screen: " + " | ".join(reasons))

    return {"netlist_body": spec["netlist_body"], "analysis": analysis, "qoi": qoi}


def _validate_analysis(analysis) -> dict:
    if not isinstance(analysis, dict):
        raise NgspiceInputError(f"'analysis' must be a dict, got {type(analysis).__name__}")
    if "type" not in analysis:
        raise NgspiceInputError("'analysis' is missing required field: type")
    atype = analysis["type"]
    if atype not in _ANALYSIS_FIELDS:
        raise NgspiceInputError(
            f"analysis type {atype!r} is not supported (supported: "
            f"{', '.join(sorted(_ANALYSIS_FIELDS))})")

    required = _ANALYSIS_FIELDS[atype]
    missing = [k for k in required if k not in analysis]
    if missing:
        raise NgspiceInputError(
            f"analysis {atype!r} is missing required field(s): {', '.join(missing)}")
    allowed = set(required) | {"type"}
    extra = [k for k in analysis if k not in allowed]
    if extra:
        raise NgspiceInputError(
            f"analysis {atype!r} has unsupported field(s): {', '.join(sorted(extra))}")

    out: dict = {"type": atype}
    for k in required:
        v = analysis[k]
        if k in ("source", "variation"):
            out[k] = v
            continue
        if k == "n":
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                raise NgspiceInputError(f"analysis field 'n' must be an integer, got {v!r}")
            if out[k] < 1:
                raise NgspiceInputError(f"analysis field 'n' must be >= 1, got {out[k]}")
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            raise NgspiceInputError(f"analysis field {k!r} must be a number, got {v!r}")

    if atype == "dc":
        if not isinstance(out["source"], str) or not _NAME_RE.match(out["source"]):
            raise NgspiceInputError(f"analysis field 'source' is not a valid name: {out['source']!r}")
        if out["step"] == 0:
            raise NgspiceInputError("analysis field 'step' must be non-zero")
    if atype == "ac":
        if out["variation"] not in _AC_VARIATIONS:
            raise NgspiceInputError(
                f"analysis field 'variation' must be one of {', '.join(_AC_VARIATIONS)}, "
                f"got {out['variation']!r}")
        for k in ("fstart", "fstop"):
            if out[k] <= 0:
                raise NgspiceInputError(f"analysis field {k!r} must be positive, got {out[k]}")
        if out["fstop"] <= out["fstart"]:
            raise NgspiceInputError("analysis field 'fstop' must exceed 'fstart'")
    if atype == "tran":
        for k in ("tstep", "tstop", "tmax"):
            if out[k] <= 0:
                raise NgspiceInputError(f"analysis field {k!r} must be positive, got {out[k]}")
        if out["tstop"] <= 0:
            raise NgspiceInputError("analysis field 'tstop' must be positive")

    return out


def _validate_qoi(qoi, atype: str) -> dict:
    if not isinstance(qoi, dict):
        raise NgspiceInputError(f"'qoi' must be a dict, got {type(qoi).__name__}")
    missing = [k for k in _REQUIRED_QOI_FIELDS if k not in qoi]
    if missing:
        raise NgspiceInputError(f"'qoi' is missing required field(s): {', '.join(missing)}")
    extra = [k for k in qoi if k not in set(_REQUIRED_QOI_FIELDS) | {"at"}]
    if extra:
        raise NgspiceInputError(f"'qoi' has unsupported field(s): {', '.join(sorted(extra))}")

    if qoi["kind"] not in _QOI_KINDS:
        raise NgspiceInputError(
            f"qoi kind {qoi['kind']!r} is not supported (supported: {', '.join(_QOI_KINDS)})")
    if not isinstance(qoi["target"], str) or not _NAME_RE.match(qoi["target"]):
        raise NgspiceInputError(f"qoi target is not a valid name: {qoi['target']!r}")
    if qoi["reduction"] not in _REDUCTIONS:
        raise NgspiceInputError(
            f"qoi reduction {qoi['reduction']!r} is not supported (supported: "
            f"{', '.join(_REDUCTIONS)})")

    at = qoi.get("at")
    if qoi["reduction"] == "value_at":
        if at is None:
            raise NgspiceInputError("qoi reduction 'value_at' requires field 'at'")
        try:
            at = float(at)
        except (TypeError, ValueError):
            raise NgspiceInputError(f"qoi field 'at' must be a number, got {at!r}")
    elif at is not None:
        raise NgspiceInputError(
            f"qoi field 'at' is only meaningful for reduction 'value_at', got at={at!r} "
            f"with reduction {qoi['reduction']!r}")

    # Reduction/analysis compatibility — an op solve has exactly one row.
    if atype == "op" and qoi["reduction"] != "op_value":
        raise NgspiceInputError(
            f"analysis 'op' produces a single point; reduction must be 'op_value', "
            f"got {qoi['reduction']!r}")
    if atype != "op" and qoi["reduction"] == "op_value":
        raise NgspiceInputError(
            f"reduction 'op_value' is only valid for analysis 'op', got analysis {atype!r}")
    if qoi["reduction"] == "corner_3db" and atype != "ac":
        raise NgspiceInputError(
            f"reduction 'corner_3db' is only valid for analysis 'ac', got analysis {atype!r}")

    return {"kind": qoi["kind"], "target": qoi["target"],
            "reduction": qoi["reduction"], "at": at}


# ----------------------------------------------------------------------------
# Deck composition. ONE convention for all four analyses: the analysis
# statement lives INSIDE the .control block (verified: `tran` in .control
# honours tmax exactly as the `.tran` dot-form does).
# ----------------------------------------------------------------------------

def qoi_vector(qoi: dict) -> str:
    """The ngspice vector name for a typed QoI: v(node) or i(source)."""
    if qoi["kind"] == "node_voltage":
        return f"v({qoi['target']})"
    return f"i({qoi['target']})"


def analysis_command(analysis: dict) -> str:
    """The one-line ngspice analysis statement for a validated analysis dict."""
    a = analysis
    if a["type"] == "op":
        return "op"
    if a["type"] == "dc":
        return f"dc {a['source']} {a['start']:.10g} {a['stop']:.10g} {a['step']:.10g}"
    if a["type"] == "ac":
        return f"ac {a['variation']} {a['n']:d} {a['fstart']:.10g} {a['fstop']:.10g}"
    # tran: tstart is pinned to 0 and tmax is the refinement lever — without it
    # ngspice's adaptive stepping ignores tstep for accuracy purposes.
    return f"tran {a['tstep']:.10g} {a['tstop']:.10g} 0 {a['tmax']:.10g}"


def compose_deck(spec: dict, out_path: str) -> str:
    """Turn a validated typed input into a full ngspice deck (a string).

    Pure and deterministic: identical input -> byte-identical deck. The caller
    contributes element lines only; every dot-command here is the wrapper's.
    """
    spec = _validate_input(spec)
    body = spec["netlist_body"].strip("\n")
    return "\n".join([
        f"* run_ngspice linear-passive v1 ({spec['analysis']['type']})",
        body,
        ".control",
        analysis_command(spec["analysis"]),
        f"wrdata {out_path} {qoi_vector(spec['qoi'])}",
        "quit",
        ".endc",
        ".end",
        "",
    ])


# ----------------------------------------------------------------------------
# Failure-marker scan — the heart of this wrapper.
#
# MEASURED on ngspice-42 (aarch64, ngspice-prod). The exit code is NOT a
# sufficient failure signal: the floating-node probe exits 0 and prints a
# plausible number. Every marker below was observed in a real prod log except
# where noted.
# ----------------------------------------------------------------------------
_FAILURE_MARKERS = (
    # Observed: floating-node probe (exit 0!) — the operating point never solved.
    ("singular matrix", "singular matrix — a node has no DC path to ground"),
    ("gmin stepping failed", "gmin stepping failed to find an operating point"),
    ("source stepping failed", "source stepping failed to find an operating point"),
    # Observed: undefined-model and garbage-line probes (exit 1).
    ("error on line", "ngspice rejected a netlist line"),
    ("simulation interrupted", "ngspice interrupted the simulation due to an error"),
    ("unknown device type", "unknown device type in the netlist"),
    ("can't find model", "netlist references an undefined model"),
    # Observed: requesting a vector that does not exist (exit 0, no wrdata file).
    ("no such vector", "the requested QoI vector does not exist in the solved circuit"),
    # Not observed in any prod probe; retained because ngspice's checkvalid path
    # emits it when a vector exists but carries no data. Kept deliberately: an
    # unfired marker costs nothing, a missing one fabricates a number.
    ("is not available or has zero length", "the requested QoI vector is empty"),
    # Defensive: ngspice's own hard-error vocabulary.
    ("fatal error", "ngspice reported a fatal error"),
)


def scan_failure_markers(log_text: str) -> str | None:
    """Return an honest reason string if ANY failure marker is present, else None.

    Case-insensitive substring scan. `gmin stepping failed` deliberately matches
    both of ngspice's variants ("Dynamic gmin stepping failed" and "True gmin
    stepping failed").
    """
    low = log_text.lower()
    for marker, reason in _FAILURE_MARKERS:
        if marker in low:
            return reason
    return None


# ----------------------------------------------------------------------------
# wrdata extraction — pure functions over the ASCII wrdata table.
#
# MEASURED shapes (ngspice-42, prod):
#   .op   -> one row: [scale, value]. The scale column is NOT a constant and
#            NOT meaningful: it is v(<first node in ngspice's internal
#            ordering>), an implementation artifact. Verified by varying the
#            source (Vin=7 -> scale 7.0) and by adding a second source
#            (V1 in=4, V2 b=9 -> scale 4.0, i.e. v(in), not the alphabetically
#            first node). The requested value is ALWAYS the LAST column, which
#            stays correct even when the target IS the scale node
#            (v(in) -> [4.0, 4.0]).
#   .ac   -> rows of [freq, re, im]  (complex as real/imag; magnitude in Python)
#   .tran -> rows of [t, value]
#   .dc   -> rows of [sweep, value]
# ----------------------------------------------------------------------------

def parse_wrdata(text: str) -> list[list[float]]:
    """Parse a wrdata ASCII table into rows of floats. Raises ValueError if the
    table is empty or unparseable — never returns a fabricated row."""
    rows: list[list[float]] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append([float(tok) for tok in ln.split()])
        except ValueError:
            raise ValueError(f"unparseable wrdata row: {ln[:80]!r}")
    if not rows:
        raise ValueError("wrdata file is empty — the solver wrote no data")
    widths = {len(r) for r in rows}
    if len(widths) != 1:
        raise ValueError(f"wrdata rows have inconsistent widths: {sorted(widths)}")
    return rows


def _xy(rows: list[list[float]], atype: str) -> tuple[list[float], list[float]]:
    """Reduce measured wrdata rows to (x, y) pairs for a given analysis type.

    For .ac the value is the COMPLEX magnitude sqrt(re^2 + im^2), computed here
    in Python — never in ngspice `meas` scripting.
    """
    if atype == "ac":
        if len(rows[0]) != 3:
            raise ValueError(f"ac wrdata should have 3 columns [freq, re, im], "
                             f"got {len(rows[0])}")
        return ([r[0] for r in rows],
                [math.hypot(r[1], r[2]) for r in rows])
    if len(rows[0]) < 2:
        raise ValueError(f"wrdata should have at least 2 columns, got {len(rows[0])}")
    # The requested value is the LAST column; the leading column(s) are the
    # scale (see the measured note above).
    return ([r[0] for r in rows], [r[-1] for r in rows])


def _interpolate(xs: list[float], ys: list[float], at: float, log_x: bool = False) -> float:
    """Linear interpolation of y at x=`at`. Raises if `at` is outside the data."""
    if at < min(xs) or at > max(xs):
        raise ValueError(f"requested point {at:g} is outside the solved range "
                         f"[{min(xs):g}, {max(xs):g}]")
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x0 <= at <= x1:
            if x1 == x0:
                return ys[i]
            if log_x:
                t = (math.log10(at) - math.log10(x0)) / (math.log10(x1) - math.log10(x0))
            else:
                t = (at - x0) / (x1 - x0)
            return ys[i] + t * (ys[i + 1] - ys[i])
    raise ValueError(f"could not bracket {at:g} in the solved range")


def reduce_qoi(rows: list[list[float]], qoi: dict, atype: str) -> float:
    """Apply the typed reduction to measured wrdata rows. Pure; raises on any
    condition that would otherwise require inventing a number."""
    xs, ys = _xy(rows, atype)
    red = qoi["reduction"]
    if red == "op_value":
        if len(ys) != 1:
            raise ValueError(f"op analysis should produce exactly 1 row, got {len(ys)}")
        return ys[0]
    if red == "final":
        return ys[-1]
    if red == "max":
        return max(ys)
    if red == "min":
        return min(ys)
    if red == "value_at":
        return _interpolate(xs, ys, qoi["at"], log_x=(atype == "ac"))
    if red == "corner_3db":
        return ac_corner_hz(rows)
    raise ValueError(f"unsupported reduction: {red!r}")


def ac_corner_hz(rows: list[list[float]]) -> float:
    """The -3 dB corner of an AC sweep, by LOG-frequency interpolation at
    |H| = |H_dc| / sqrt(2).

    KNOWN SYSTEMATIC BIAS — measured, quantified, and NOT removable here.
    |H_dc| is PROXIED by the magnitude at the lowest solved frequency, because
    the wrapper does not know the caller's circuit and cannot evaluate a true
    DC gain. For a one-pole response that proxy biases the corner HIGH by a
    relative (fstart / fcorner)**2:

        1/sqrt(1+u^2) = 1/(sqrt(2)*sqrt(1+s^2))  =>  u = sqrt(1+2s^2) ~ 1+s^2
        with u = f/fcorner and s = fstart/fcorner.

    Measured on ngspice-42/prod (R=1k, C=159.155n, fcorner_analytic=999.9996):
        fstart=10 Hz  -> 1000.0991  (+9.94e-05, predicted 1.00e-04)
        fstart=1 Hz   -> 1000.0006  (+9.96e-07, predicted 1.00e-06)
        fstart=0.1 Hz ->  999.99965 (+7.51e-09, predicted 1.00e-08)

    This bias DOMINATES frequency-grid density: refining 10 -> 100 points per
    decade moved the same corner by only 3.8e-06 relative, ~26x less than the
    fstart bias it sat inside. A corner QoI is therefore only as good as its
    fstart is low; start the sweep >= 3 decades below the expected corner for
    ~1e-6, and do not read the grid-density delta as the error bar.
    """
    freqs, mags = _xy(rows, "ac")
    target = mags[0] / math.sqrt(2.0)
    for i in range(len(freqs) - 1):
        if (mags[i] - target) * (mags[i + 1] - target) <= 0 and mags[i] != mags[i + 1]:
            # Interpolate in log(f) against magnitude.
            lf0, lf1 = math.log10(freqs[i]), math.log10(freqs[i + 1])
            t = (target - mags[i]) / (mags[i + 1] - mags[i])
            return 10 ** (lf0 + t * (lf1 - lf0))
    raise ValueError("the AC sweep never crosses |H_dc|/sqrt(2) — widen the range")


def corner_fstart_bias(fstart: float, corner_hz: float) -> float:
    """The estimated RELATIVE bias a corner_3db reading carries because |H_dc|
    was proxied at fstart: (fstart / corner)**2, for a one-pole response.

    Pure, and derived rather than remembered — see ac_corner_hz's docstring for
    the algebra and the three measured points that confirm it to 3 digits.
    Returns a POSITIVE relative magnitude; the bias direction is HIGH.

    Raises ValueError on a non-positive corner: a bias relative to a zero or
    negative corner is not a number, and inventing one here would be exactly the
    fabrication this wrapper exists to prevent.
    """
    if corner_hz <= 0:
        raise ValueError(f"corner must be positive to estimate its bias, got {corner_hz!r}")
    if fstart <= 0:
        raise ValueError(f"fstart must be positive to estimate a bias, got {fstart!r}")
    return (fstart / corner_hz) ** 2


def corner_fstart_bias_note(fstart: float, corner_hz: float) -> str:
    """The per-run honesty note appended to a corner_3db run's diagnostics.

    WHY THIS IS ON EVERY RUN, not in the docs. The measured finding (see
    ac_corner_hz) is that this bias DOMINATES frequency-grid density by ~26x on
    the self-checked RC — so the obvious error bar (refine the grid, watch the
    corner move) understates the real error by that factor and reads as
    reassurance. A caller who never opens the card would otherwise have no way
    to know. Stating it per run turns a documented trap into a reported number.

    Never raises: diagnostics must never be the thing that fails a good run, so
    an inestimable bias degrades to an honest string rather than an exception.
    """
    try:
        bias = corner_fstart_bias(fstart, corner_hz)
    except ValueError as e:
        return f"fstart bias not estimable ({e})"
    decades = math.log10(corner_hz / fstart) if fstart > 0 and corner_hz > 0 else 0.0
    return (f"estimated fstart bias {bias:.2e} relative, HIGH "
            f"((fstart/corner)^2 with fstart={fstart:.10g} Hz, "
            f"{decades:.1f} decades below the corner) — this dominates grid "
            f"density (~26x on the self-checked RC), so do NOT read a "
            f"grid-refinement delta as the error bar; lower fstart to shrink it")


# ----------------------------------------------------------------------------
# Analytic reference functions — closed-form circuit theory.
#
# These are computed from the SAME numeric values the caller puts in the
# netlist. Nothing here is a hard-coded expected result: a hard-coded number
# cannot fail when the wrapper is wrong, and a check that cannot fail is not a
# proof.
# ----------------------------------------------------------------------------

def analytic_divider_vout(vin: float, r1: float, r2: float) -> float:
    """Resistive divider, output across r2: vout = vin * r2 / (r1 + r2)."""
    if r1 <= 0 or r2 <= 0:
        raise ValueError(f"divider resistances must be positive, got r1={r1}, r2={r2}")
    return vin * r2 / (r1 + r2)


def analytic_rc_corner_hz(r: float, c: float) -> float:
    """RC low-pass -3 dB corner: f = 1 / (2*pi*R*C)."""
    if r <= 0 or c <= 0:
        raise ValueError(f"R and C must be positive, got r={r}, c={c}")
    return 1.0 / (2.0 * math.pi * r * c)


def analytic_rc_step_v(t: float, vin: float, r: float, c: float) -> float:
    """RC step response across C: v(t) = vin * (1 - exp(-t / (R*C)))."""
    if r <= 0 or c <= 0:
        raise ValueError(f"R and C must be positive, got r={r}, c={c}")
    if t < 0:
        raise ValueError(f"t must be non-negative, got {t}")
    return vin * (1.0 - math.exp(-t / (r * c)))


def rlc_zeta(r: float, l: float, c: float) -> float:
    """Series-RLC damping ratio: zeta = (R/2) * sqrt(C/L)."""
    if r <= 0 or l <= 0 or c <= 0:
        raise ValueError(f"R, L and C must be positive, got r={r}, l={l}, c={c}")
    return (r / 2.0) * math.sqrt(c / l)


def analytic_rlc_step_peak(vin: float, r: float, l: float, c: float) -> float:
    """Series-RLC step response peak measured across C (underdamped ONLY).

    peak = vin * (1 + exp(-zeta*pi / sqrt(1 - zeta^2))), the standard
    second-order overshoot. Raises on zeta >= 1: an overdamped circuit has no
    overshoot peak to predict, and returning the settled value instead would be
    a fabricated answer to a question that has none.
    """
    zeta = rlc_zeta(r, l, c)
    if zeta >= 1.0:
        raise ValueError(f"analytic_rlc_step_peak is underdamped-only; zeta={zeta:.4f} >= 1")
    overshoot = math.exp(-zeta * math.pi / math.sqrt(1.0 - zeta * zeta))
    return vin * (1.0 + overshoot)


# ----------------------------------------------------------------------------
# Preflight — daemon AND container.
#
# NOTE: run_cfd.py, run_fea.py and run_code.py do NOT preflight; they discover a
# down daemon or a stopped container as an opaque exec failure. This wrapper
# adds the check because `colima up` != `ngspice-prod up`, and the two failures
# want different human actions. Reported as a deliberate deviation.
# ----------------------------------------------------------------------------

def preflight() -> str | None:
    """Return None when the substrate is ready, else an honest reason string."""
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
            ["docker", "--context", DOCKER_CONTEXT, "inspect", "-f", "{{.State.Running}}",
             CONTAINER],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return f"docker inspect {CONTAINER} timed out"
    if proc.returncode != 0:
        return f"container {CONTAINER!r} does not exist (create it per tools/ngspice_env/README.md)"
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


def ngspice_version() -> str:
    """The container's own `ngspice --version`, verbatim. Measured, never assumed."""
    proc = subprocess.run(
        ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "ngspice", "--version"],
        capture_output=True, text=True, timeout=60)
    return proc.stdout.strip()


# ----------------------------------------------------------------------------
# Execution — sandboxed docker exec, hard timeout, one retry on transient fail.
# ----------------------------------------------------------------------------

def _run_ngspice_cmd(job: str) -> tuple[int, str]:
    """Run ngspice on the job's deck inside the container. Returns
    (returncode, infra_stderr). Raises subprocess.TimeoutExpired on the hard
    timeout so the caller can classify it as transient and retry once."""
    job_dir = f"{SHARED_CONTAINER}/{job}"
    remote = f"cd {job_dir} && ngspice -b -o {job_dir}/ngspice.log {job_dir}/deck.cir"
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    return proc.returncode, proc.stderr.strip()


def _is_transient(returncode: int, infra_stderr: str, log_exists: bool) -> bool:
    """A failure is transient (worth one retry) when it looks like infrastructure
    rather than a bad deck: no log produced and a docker/exec-level stderr."""
    if log_exists:
        return False
    low = infra_stderr.lower()
    if infra_stderr and ("docker" in low or "cannot" in low or "error response" in low
                         or "is not running" in low):
        return True
    return returncode != 0 and not log_exists


def run_ngspice(spec: dict) -> dict:
    """Compose, run, and summarize one linear-passive circuit case.

    Returns the small dict documented at the top of this module — and nothing
    else leaves the wrapper. A QoI is NEVER returned when a failure marker
    fired, when the wrdata file is missing/empty, or when the requested vector
    is absent.
    """
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    # --- validate + screen (pure, pre-solve) ------------------------------
    try:
        clean = _validate_input(spec)
    except NgspiceInputError as e:
        return fail(f"input rejected: {e}")

    # --- preflight: daemon AND container ----------------------------------
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
    job = f"lp_{clean['analysis']['type']}_{int(wall_start * 1000)}_{uuid.uuid4().hex[:8]}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    out_container = f"{SHARED_CONTAINER}/{job}/out.dat"
    deck = compose_deck(spec, out_container)
    (case_dir / "deck.cir").write_text(deck)

    out_path = case_dir / "out.dat"
    log_path = case_dir / "ngspice.log"

    # --- run, with one retry on a transient failure -----------------------
    for attempt in range(MAX_RETRIES + 1):
        # Clear stale artifacts so a retry can't read an old result.
        for p in (out_path, log_path):
            if p.exists():
                p.unlink()
        try:
            returncode, infra_stderr = _run_ngspice_cmd(job)
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"ngspice exceeded {TIMEOUT_SECONDS}s timeout and was killed")

        log_exists = log_path.is_file()
        if not log_exists and _is_transient(returncode, infra_stderr, log_exists) \
                and attempt < MAX_RETRIES:
            continue
        break

    if not log_path.is_file():
        return fail(f"ngspice produced no log (exit {returncode}): "
                    f"{infra_stderr.splitlines()[0] if infra_stderr else 'no stderr'}")

    log_text = log_path.read_text(errors="replace")

    # --- marker scan FIRST: exit 0 proves nothing -------------------------
    marker_reason = scan_failure_markers(log_text)
    if marker_reason:
        return fail(f"solver reported a failure (exit {returncode}): {marker_reason}"
                    f" [{_marker_context(log_text)}]")
    if returncode != 0:
        return fail(f"ngspice exited {returncode}: {_marker_context(log_text)}")

    # --- extraction: no file, no number -----------------------------------
    if not out_path.is_file():
        return fail("ngspice ran without an error marker but wrote no wrdata output — "
                    "the requested QoI vector could not be written")
    raw = out_path.read_text(errors="replace")
    if not raw.strip():
        return fail("ngspice wrote an EMPTY wrdata file — no QoI data to read")
    try:
        rows = parse_wrdata(raw)
        value = reduce_qoi(rows, clean["qoi"], clean["analysis"]["type"])
    except ValueError as e:
        return fail(f"solver ran but output was unusable: {e}")

    if not math.isfinite(value):
        return fail(f"extracted QoI is not finite ({value!r}) — refusing to return it")

    diagnostics = (f"ngspice {clean['analysis']['type']} on "
                   f"{len([l for l in clean['netlist_body'].splitlines() if l.strip()])} "
                   f"element line(s); {len(rows)} data row(s); "
                   f"{clean['qoi']['reduction']} of {qoi_vector(clean['qoi'])}")
    # A corner_3db reading carries a systematic fstart bias that dominates grid
    # density; report each run's own estimate rather than leaving it in the card.
    if clean["qoi"]["reduction"] == "corner_3db":
        diagnostics += "; " + corner_fstart_bias_note(clean["analysis"]["fstart"], value)
    return {"valid": True, "qoi": value,
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


def _marker_context(log_text: str) -> str:
    """A bounded, honest excerpt of the offending log lines — never the whole log."""
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    interesting = [ln for ln in lines
                   if any(m in ln.lower() for m, _ in _FAILURE_MARKERS)
                   or ln.lower().startswith("error")
                   or ln.lower().startswith("warning")]
    picked = interesting[:4] or lines[-2:]
    return " | ".join(picked)[:300]


# ----------------------------------------------------------------------------
# Docs RAG — search the ngspice manual index (separate from solver_docs/fea_docs).
# ----------------------------------------------------------------------------

def search_ngspice_docs(query: str, top_k: int = 3) -> list[dict]:
    """Search the ngspice-manual TF-IDF index. Mirrors search_fea_docs but points
    at the separate ngspice_docs index. Offline, deterministic, no API."""
    import sys
    if str(_RETRIEVAL_DIR) not in sys.path:
        sys.path.insert(0, str(_RETRIEVAL_DIR))
    from tfidf_core import search  # noqa: E402  (retrieval/ helper, path-injected)

    if not NGSPICE_DOCS_INDEX.exists():
        raise FileNotFoundError(
            "ngspice_docs index not built yet — run "
            "venv/bin/python3 tools/ngspice_env/build_ngspice_docs_index.py"
        )
    return search(NGSPICE_DOCS_INDEX, query, top_k=top_k)


# CLI:  venv/bin/python3 tools/run_ngspice.py     (runs the divider self-check)
if __name__ == "__main__":
    default = {
        "netlist_body": "V1 in 0 DC 10\nR1 in out 1k\nR2 out 0 2k",
        "analysis": {"type": "op"},
        "qoi": {"kind": "node_voltage", "target": "out",
                "reduction": "op_value", "at": None},
    }
    result = run_ngspice(default)
    result["analytic_divider_vout"] = analytic_divider_vout(10.0, 1e3, 2e3)
    print(json.dumps(result, indent=2))
