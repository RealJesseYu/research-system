"""quantity_register.py — a deterministic store of the quantities a study has
established, and a mechanical check that a new one does not contradict them.

WHY THIS EXISTS (docs/roadmap_capability.md T0.1, §1 is the evidence). Both
headline failures of study-20260730T034915Z were contradictions between numbers
that each reproduced perfectly on their own:

  - Three fits of the same coefficient on overlapping LTPP data gave
    `b_sn` = 3.6537 (m12), 7.4314 (m14) and 0.3215 (m15) — a 23x spread, one
    implying a 260-year pavement life against an observed 12.4. The paper calls
    it "a first-order unresolved problem... the single strongest reason this
    replacement is not ready to use", and it surfaced in §5.2 of the write-up
    rather than when the second fit landed at move 14.
  - A headline "4x better" was sigma 0.36 against 1.46 measured in DIFFERENT
    response variables — log10(years) against log10(ESALs). Changing which one
    you predict moves sigma from 1.10 to 0.38 before any model exists
    (docs/finding_armc_core_recovery.md).

NEITHER IS A VERIFICATION FAILURE, and this is NOT verification. The wall
(stages/verification.py) asks "does this number recompute". This asks a
different question — "does this contradict something already established" —
which is why the wall caught neither. The two must not be confused: nothing
here touches verification.py, nothing here is written to verification.json, and
a conflict NEVER changes a verified/unverified verdict. A number can be
perfectly reproduced and flatly contradict its neighbour; that is the whole
point.

NO MODEL IN IT, same discipline as the wall and for the same reason: a checker
that can be talked out of a conflict is not a checker. Pure deterministic
Python, unit-testable offline, zero model calls.

ADDITIVE. A move MAY register quantities; nothing forces it and nothing gates on
it. A study whose findings name no quantities writes a byte-identical arc. A
conflict is SURFACED — to the director's next turn, to liveview — and never ends
an arc. Nothing ends an arc but the director.

--------------------------------------------------------------------------
WHAT A REGISTRATION IS
--------------------------------------------------------------------------
{name, value, units, producer, move, run_id, label, verified, at}

It RIDES THE EXISTING FINDING SHAPE rather than being a second thing an agent
must remember (see stages/free_experimenter.py's SYSTEM_PROMPT and JSON
contract):

  name     <- finding["quantity"] if given, else finding["artifact"]["quantity"]
              — which every verified finding already carries, because it is the
              key the wall regenerates the value under. So the common case
              registers with ZERO extra work from the agent.
  value    <- finding["value"]              (already there)
  producer <- finding["artifact"]           (already there: the file or
                                             substrate call that regenerates it)
  units    <- finding["units"]              (THE ONE NEW OPTIONAL FIELD)

A finding that names no quantity is simply not registered. That is the additive
default, not a failure.

--------------------------------------------------------------------------
THE THREE CHECKS
--------------------------------------------------------------------------
1. VALUE     same name, already registered, values disagree beyond tolerance.
2. UNITS     same name, already registered, units disagree.
3. COMPARISON a finding declares "compares": [name_a, name_b] and those two
             names are registered with units that are not the same.

--------------------------------------------------------------------------
UNITS: HOW THEY ARE DECLARED AND COMPARED, AND WHY THIS WAY
--------------------------------------------------------------------------
Units are a DECLARED STRING, conservatively canonicalised, compared for
EQUALITY. There is no dimensional algebra. That is a deliberate choice against
the obvious alternative, and the real failure is what decides it:

  A dimensional-analysis engine (pint and friends) would NOT have caught the
  sigma case. sigma_years is the spread of log10(years) and sigma_esals the
  spread of log10(ESALs). A logarithm's argument is made dimensionless before
  the log is taken, so BOTH are formally dimensionless and a dimensional engine
  passes them as commensurable. Worse, "ESAL" — an equivalent single axle load —
  is a count with no SI dimension at all, so no unit system has a symbol for the
  thing that actually differed.

  What actually differed was the RESPONSE VARIABLE, and a string that says so —
  "log10(years)" against "log10(ESALs)" — is exactly the discriminator. So the
  string is the representation, not a lossy encoding of one.

Canonicalisation applies only transformations that CANNOT change meaning:
Unicode NFKC, the math lookalikes (· × − and superscript digits), `**` -> `^`,
case-folding, whitespace removal, and one tiny explicit table for the
spellings of dimensionless ("1", "-", "dimensionless", "unitless"). It does NOT
know that "m/s" and "meters per second" are the same unit, and deliberately so:

  THE ERROR ASYMMETRY IS THE WHOLE ARGUMENT. A missing alias produces a FALSE
  conflict — one extra line in the director's next turn, cheap and visible. A
  wrong alias produces a MISSED conflict — which is the failure that cost this
  project its headline result. So the table stays small enough to be obviously
  correct, and every judgement call is resolved toward firing.

UNDECLARED (`units` absent or empty) is a THIRD STATE, not a synonym for
dimensionless. It never fires a units conflict — you cannot contradict what was
never asserted — and it is recorded as null so a reader can see the gap.

--------------------------------------------------------------------------
TOLERANCE: THE RULE, AND WHAT IT DOES AND DOES NOT CATCH
--------------------------------------------------------------------------
Two registrations of one name conflict when

    |a - b| / max(|a|, |b|)  >  0.05

and that 0.05 is DERIVED, not guessed:

  - The wall holds a re-run to DEFAULT_REL_TOL = 1e-6, and the loosest band any
    claim may declare for itself is MAX_DECLARED_REL_TOL = 0.02
    (stages/verification.py). So anything the wall could ever call "the same
    number" is at most 2% apart.
  - Therefore a gap wider than that is not floating-point noise. It is a
    DIFFERENT COMPUTATION wearing the same name.
  - Whether that difference is legitimate (a better fit, a narrower sample) or a
    contradiction is a JUDGEMENT, and judgement belongs to the director, not to a
    deterministic checker. The checker's only job is to route it there.

  0.05 sits just above the wall's loosest declarable band, so the register can
  never fire on something the wall would have accepted as a reproduction.

THERE IS NO PER-REGISTRATION OVERRIDE, deliberately. A knob letting a move widen
its own conflict band is precisely "a checker that can be talked out of a
conflict". One rule, one number, stated here.

WHAT IT CATCHES: b_sn 3.6537 vs 7.4314 (rel 0.508) fires at move 14, and 0.3215
against either fires at move 15 — instead of in §5.2 of the write-up. It also
fires on b_sn 0.3215 (pooled) vs 0.4711 (identified within SPS project), rel
0.318, and THAT IS INTENDED: those are two different estimators sharing one
name, and the register's correct response is to force them apart into
b_sn_pooled / b_sn_sps or to have the collision acknowledged.

WHAT IT DOES NOT CATCH:
  - The same quantity registered under two DIFFERENT names. No threshold fixes
    this; it is the register's fundamental blind spot, and it is exactly why
    check 3 (a declared comparison) exists and why units are half the value.
  - A wrong number registered once. Nothing contradicts it. Not this tool's job.
  - Two values that agree numerically but mean different things and were never
    compared. Units help only where they were declared.
  - Anything in a move that emitted no findings at all. On the study above,
    m12/m14/m15/m16 each emitted zero — which is roadmap item T0.2, and is why
    T0.1 and T0.2 are paired in Tier 0.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# See the TOLERANCE block above: derived from the wall's MAX_DECLARED_REL_TOL of
# 0.02, so the register can never fire on a gap the wall would have accepted as
# a reproduction. Not declarable per registration, deliberately.
CONFLICT_REL_TOL = 0.05

# The spellings of "no units at all". Kept to the four that cannot mean anything
# else; "none", "ratio" and "fraction" are deliberately NOT here, because each
# could be hiding a unit and a wrong alias is the expensive direction of error.
_DIMENSIONLESS = {"1", "-", "dimensionless", "unitless"}

# Meaning-preserving character rewrites only. No unit algebra lives here.
_CHAR_MAP = {
    "·": "*",   # ·  middle dot
    "×": "*",   # ×  multiplication sign
    "⋅": "*",   # ⋅  dot operator
    "−": "-",   # −  minus sign
    "⁄": "/",   # ⁄  fraction slash
}

# Superscripts must be handled BEFORE Unicode NFKC, and as RUNS rather than
# character by character. NFKC folds "m²" to "m2" — silently turning an exponent
# into a digit of the unit's name, which is exactly the kind of
# meaning-changing normalisation this module forbids itself. And a per-character
# map turns "s⁻¹" into "s^-^1" rather than "s^-1". So a maximal run of
# superscript characters becomes one "^" followed by their plain forms.
_SUPERSCRIPT = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-", "⁺": "+",
}


def _expand_superscripts(text: str) -> str:
    out, run = [], []
    for ch in text:
        plain = _SUPERSCRIPT.get(ch)
        if plain is not None:
            run.append(plain)
            continue
        if run:
            out.append("^" + "".join(run))
            run = []
        out.append(ch)
    if run:
        out.append("^" + "".join(run))
    return "".join(out)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_units(units: Any) -> Optional[str]:
    """Canonical form of a declared unit string, or None for UNDECLARED.

    Conservative by construction — see the UNITS block in the module docstring.
    Never raises: a unit declared as a number, a dict or anything else is
    stringified rather than rejected, because a malformed declaration must not
    be able to sink the move that carried it."""
    if units is None:
        return None
    if not isinstance(units, str):
        units = str(units)
    # Superscripts first — NFKC would flatten them into ordinary digits.
    text = _expand_superscripts(units)
    text = "".join(_CHAR_MAP.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("**", "^")
    text = "".join(text.split()).lower()
    if not text:
        return None
    if text in _DIMENSIONLESS:
        return "1"
    return text


def _as_number(value: Any) -> Optional[float]:
    """The value as a float, or None when it is not a number. A bool is NOT a
    number here — True would compare equal to 1.0 and that is a coincidence, not
    an agreement."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f == f and abs(f) != float("inf") else None
    return None


def _values_disagree(a: Any, b: Any) -> Optional[float]:
    """None when the two values agree; otherwise the relative difference that
    made them disagree (float('inf') for two non-numeric values that differ, so
    a caller can always report a number).

    Non-numeric values (a finding's value may be "a short string") compare by
    exact stripped string equality — no normalisation, same discipline the wall
    applies to string claims."""
    fa, fb = _as_number(a), _as_number(b)
    if fa is None or fb is None:
        same = str(a).strip() == str(b).strip()
        return None if same else float("inf")
    denom = max(abs(fa), abs(fb))
    if denom == 0.0:
        return None  # both exactly zero
    rel = abs(fa - fb) / denom
    return None if rel <= CONFLICT_REL_TOL else rel


def _where(reg: dict) -> str:
    """A short human-readable 'move 14 (m_b_sn.py)' for a conflict detail."""
    move = reg.get("move")
    at = f"move {move}" if move is not None else (reg.get("run_id") or "an earlier move")
    prod = reg.get("producer") or {}
    src = prod.get("file") or prod.get("substrate_id") if isinstance(prod, dict) else None
    return f"{at} ({src})" if src else str(at)


def registration_from_finding(
    finding: Any, *, move: Any = None, run_id: Optional[str] = None
) -> Optional[dict]:
    """One registration derived from one finding, or None when the finding names
    no quantity. Pure, never raises.

    The name is the finding's explicit "quantity" if it gave one, else the
    "quantity" key its artifact already carries — the key the wall regenerates
    the value under. That fallback is what makes registration free: a verified
    finding registers itself with no extra work from the agent."""
    if not isinstance(finding, dict):
        return None
    artifact = finding.get("artifact")
    artifact = artifact if isinstance(artifact, dict) else None
    name = finding.get("quantity")
    if not (isinstance(name, str) and name.strip()) and artifact:
        name = artifact.get("quantity")
    if not (isinstance(name, str) and name.strip()):
        return None
    return {
        "name": name.strip(),
        "value": finding.get("value"),
        "units": finding.get("units") if finding.get("units") not in ("",) else None,
        "units_canonical": canonical_units(finding.get("units")),
        # The thing that regenerates it — the artifact the wall already re-runs.
        # Recorded, never re-executed here: this module runs no code.
        "producer": artifact,
        "move": move,
        "run_id": run_id,
        "label": finding.get("label"),
        # Carried so a reader can weigh a conflict, NEVER consulted by the
        # checks: a conflict between two unverified values is still a conflict,
        # and verification's verdict is not this file's business (constraint 3).
        "verified": bool(finding.get("verified")),
        "at": _utc_now(),
    }


def check_against(registration: dict, prior: list) -> list:
    """Conflicts between one new registration and everything registered before
    it. Pure. Checks 1 (value) and 2 (units) from the module docstring.

    Compared against the MOST RECENT prior registration of the same name — one
    conflict per new registration per kind, so a name registered five times
    reports four conflicts rather than ten. The chain is complete either way and
    the director's turn stays readable."""
    name = registration.get("name")
    earlier = [r for r in prior if isinstance(r, dict) and r.get("name") == name]
    if not earlier:
        return []
    conflicts = []
    last = earlier[-1]
    rel = _values_disagree(last.get("value"), registration.get("value"))
    if rel is not None:
        spread = (f"relative difference {rel:.3g}" if rel != float("inf")
                  else "the values are not the same")
        conflicts.append({
            "kind": "value",
            "name": name,
            "detail": (
                f"{name!r} was registered as {last.get('value')!r} at "
                f"{_where(last)} and is now registered as "
                f"{registration.get('value')!r} at {_where(registration)} — "
                f"{spread}, outside the {CONFLICT_REL_TOL:g} band. Both may "
                "reproduce perfectly; at most one can be the quantity this "
                "name means."
            ),
            "rel_difference": None if rel == float("inf") else rel,
            "prior": last,
            "this": registration,
        })
    # Units are checked against the most recent prior registration that actually
    # DECLARED them: an undeclared registration in between must not erase the
    # assertion an earlier one made.
    declared = [r for r in earlier if r.get("units_canonical")]
    if declared and registration.get("units_canonical"):
        ref = declared[-1]
        if ref["units_canonical"] != registration["units_canonical"]:
            conflicts.append({
                "kind": "units",
                "name": name,
                "detail": (
                    f"{name!r} was registered in units {ref.get('units')!r} at "
                    f"{_where(ref)} and is now registered in units "
                    f"{registration.get('units')!r} at {_where(registration)}. "
                    "Two things under one name are not one thing."
                ),
                "prior": ref,
                "this": registration,
            })
    return conflicts


def check_comparison(finding: Any, register: list, *, move: Any = None) -> list:
    """Check 3: a finding that declares "compares": [name_a, name_b] where the
    two names are registered in units that are not the same.

    This is the check for the failure a same-name test cannot reach — the
    headline "4x better" that set sigma in log10(years) against sigma in
    log10(ESALs). Silent when either name is unregistered or either side left
    its units undeclared: an undeclared unit asserts nothing, and this module
    does not invent assertions."""
    if not isinstance(finding, dict):
        return []
    names = finding.get("compares")
    if not isinstance(names, (list, tuple)) or len(names) < 2:
        return []
    latest: dict = {}
    for r in register:
        if isinstance(r, dict) and r.get("units_canonical"):
            latest[r.get("name")] = r
    conflicts = []
    pairs = [(names[i], names[j])
             for i in range(len(names)) for j in range(i + 1, len(names))]
    for a, b in pairs:
        ra, rb = latest.get(a), latest.get(b)
        if not ra or not rb:
            continue
        if ra["units_canonical"] == rb["units_canonical"]:
            continue
        conflicts.append({
            "kind": "incommensurable_comparison",
            "name": f"{a} vs {b}",
            "detail": (
                f"this move compares {a!r} (units {ra.get('units')!r}, "
                f"{_where(ra)}) with {b!r} (units {rb.get('units')!r}, "
                f"{_where(rb)}) — they are not in the same units, so the "
                f"comparison {str(finding.get('label') or '')!r} is not "
                "like-for-like whatever the numbers say."
            ),
            "prior": ra,
            "this": rb,
            "compared_by": {"label": finding.get("label"),
                            "value": finding.get("value"), "move": move},
        })
    return conflicts


def read_register(path: Any) -> list:
    """Every registration on disk, oldest first. Never raises: a missing file is
    an empty register, and an unreadable LINE is skipped and counted out loud
    rather than taking down the reader — the same discipline the journal's read
    side uses, and for the same reason (one torn line must not break the channel
    every later move reads through)."""
    p = Path(path)
    if not p.is_file():
        return []
    out, bad = [], 0
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (ValueError, TypeError):
                bad += 1
                continue
            if isinstance(entry, dict):
                out.append(entry)
            else:
                bad += 1
    if bad:
        print(f"NOTE: {bad} unreadable line(s) skipped in {p}")
    return out


def register_findings(
    path: Any, findings: Any, *, move: Any = None, run_id: Optional[str] = None
) -> tuple:
    """Register a move's findings and return (registrations, conflicts).

    The one entry point a caller needs. Appends each derived registration to
    `path` (append-only, one JSON object per line, beside arc.jsonl) and returns
    the conflicts detected while doing so.

    ORDER MATTERS AND IS THE POINT: each registration is checked against
    everything registered before it — including earlier findings of this same
    move — so a conflict is attributed to the move that CREATED it, which is the
    move the director is about to read about. Comparison declarations are checked
    last, against the whole register, so a ratio finding may sit in the same move
    as the two quantities it compares.

    Never raises for a bad finding; a finding that names no quantity is skipped."""
    prior = read_register(path)
    new: list = []
    conflicts: list = []
    for finding in (findings if isinstance(findings, (list, tuple)) else []):
        reg = registration_from_finding(finding, move=move, run_id=run_id)
        if reg is None:
            continue
        conflicts.extend(check_against(reg, prior + new))
        new.append(reg)
    whole = prior + new
    for finding in (findings if isinstance(findings, (list, tuple)) else []):
        conflicts.extend(check_comparison(finding, whole, move=move))
    if new:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            for reg in new:
                f.write(json.dumps(reg) + "\n")
    return new, conflicts


def replay_conflicts(path: Any) -> list:
    """Every conflict the register on disk implies, recomputed from scratch.

    DERIVED, NEVER STORED — so the conflicts a reader sees can never drift from
    the registrations that produced them. Cheap: a study's register is tens of
    entries, and this is the only way to be sure the two agree.

    Comparison conflicts (check 3) are NOT replayable from the register alone —
    the declaration lives on the finding, not on a registration — so they are
    recorded in the arc entry of the move that declared them and are not
    recomputed here. Said out loud rather than silently omitted."""
    register = read_register(path)
    conflicts: list = []
    seen: list = []
    for reg in register:
        conflicts.extend(check_against(reg, seen))
        seen.append(reg)
    return conflicts


def conflict_summary(conflicts: list) -> list:
    """The compact form for a turn view or a terminal: kind, name, detail, and
    where each side came from. Pure; never raises on a malformed conflict."""
    out = []
    for c in conflicts or []:
        if not isinstance(c, dict):
            continue
        out.append({
            "kind": c.get("kind"),
            "quantity": c.get("name"),
            "detail": c.get("detail"),
            "first_registered_at_move": (c.get("prior") or {}).get("move"),
            "conflicting_move": (c.get("this") or {}).get("move"),
        })
    return out
