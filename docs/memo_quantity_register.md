# The quantity register — T0.1 built, and what it does and does not catch

**Built 2026-07-30.** Roadmap item `docs/roadmap_capability.md` T0.1. Code:
`stages/quantity_register.py` (the whole design rationale lives in its module
docstring; this memo is the short version plus the empirical result).

## What it is

A deterministic, no-model store of the quantities a study has established —
`{name, value, units, producer, move, run_id, label, verified}` — in
`studies/<id>/quantities.jsonl`, beside `arc.jsonl`. On every write, three
mechanical checks:

1. **value** — same name, already registered, values disagree beyond tolerance.
2. **units** — same name, already registered, units disagree.
3. **comparison** — a finding declares `"compares": [a, b]` and those two names
   are registered in units that are not the same.

A conflict is **surfaced, never enforced**: it rides the move's own arc entry
(the `blocked_on` pattern from commit 8df1379), gets a standing block in the
director's next turn, and prints in liveview and the CLI summary. Nothing ends
an arc but the director.

## It is not verification, and the distinction is the point

The wall (`stages/verification.py`) asks **"does this number recompute"**. This
asks **"does this contradict something already established"**. Both headline
failures of `study-20260730T034915Z` were the second question, which is why the
wall caught neither — every one of those numbers reproduces perfectly on its own.

`verification.py` and `reusable_artifacts.py` are untouched; a test greps them
and pins zero occurrences of *constraint / conflict / consist / contradict*.
Nothing here writes `verification.json` and no conflict changes a
verified/unverified verdict.

## Where it plugs in

    free_experimenter findings (units, quantity, compares are new/optional)
      -> runs/<id>/free_investigation.json          (already written)
      -> dispatch._read_quantity_findings           (NEW)
      -> RunResult.quantities -> as_dict -> MoveResult.raw
      -> study.record_move -> quantities.jsonl + arc entry quantity_conflicts
      -> director's next turn / liveview / CLI summary

**A defect found on the way, worth recording.** The obvious source — the arc's
`results`, i.e. `RunResult.findings` — comes from `verification.json` and is the
wrong source twice over: it projects each verdict to
`{label, value, verified, reason}`, dropping the artifact whose `quantity` key
is the name a value registers under; and it contains only findings the agent
*claimed verified*, because an unverified finding never becomes a claim. Wired
that way the register would have registered **nothing**. Measured on
`study-20260730T034915Z`: all 136 arc findings carry `artifact: null`. Reading
the agent's own report instead (as `_read_reusable_artifacts` already did) takes
it from **0 to 136 registrations** on that same study. Pinned by two tests.

## Units: declared strings, canonicalised, compared for equality

**A dimensional-analysis engine would not have caught the real failure.**
`sigma_years` is the spread of log10(years) and `sigma_esals` the spread of
log10(ESALs); a logarithm's argument is dimensionless before the log is taken,
so both are formally dimensionless and any dimensional system passes them as
commensurable. Worse, an ESAL is a count with no SI dimension at all. What
differed was the *response variable*, and only a string carries that.

Canonicalisation applies only meaning-preserving transforms: superscript runs
(before NFKC — NFKC folds `m²` to `m2`, silently turning an exponent into a
digit), the math lookalikes `· × − ⁄`, `**` → `^`, case-fold, whitespace strip,
and one four-entry table for the spellings of dimensionless. It does **not**
know `m/s` and `meters per second` are the same unit, deliberately:

> **The error asymmetry is the whole argument.** A missing alias produces a
> false conflict — one extra line in the director's turn. A wrong alias produces
> a missed conflict — the failure that cost this project its headline. So the
> table stays small enough to be obviously correct and every judgement call is
> resolved toward firing.

Undeclared units are a **third state**, not a synonym for dimensionless: they
never fire a units conflict, and an undeclared registration in between does not
erase an earlier assertion.

## Tolerance: 0.05 relative, derived and not overridable

    |a - b| / max(|a|, |b|)  >  0.05  ->  conflict

Derived, not guessed. The wall holds a re-run to `DEFAULT_REL_TOL = 1e-6` and the
loosest band any claim may declare for itself is `MAX_DECLARED_REL_TOL = 0.02`.
So anything the wall could ever call "the same number" is at most 2% apart;
a wider gap is not floating-point noise but **a different computation wearing the
same name**. Whether that is legitimate or a contradiction is a judgement, and
judgement belongs to the director. 0.05 sits just above the wall's loosest
declarable band, so the register can never fire on a gap the wall would have
accepted as a reproduction.

**No per-registration override.** A knob letting a move widen its own conflict
band is precisely "a checker that can be talked out of a conflict".

### What it catches

- `b_sn` 3.6537 (m12) vs 7.4314 (m14) — rel 0.508, fires **at move 14**, which
  is where the study actually had the information; on disk it surfaced in §5.2
  of the write-up. 0.3215 (m15) then fires against 7.4314.
- `b_sn` 0.3215 (pooled) vs 0.4711 (within SPS project) — rel 0.318. **Intended.**
  Those are two estimators sharing one name and the correct response is to name
  them apart (`b_sn_pooled` / `b_sn_sps`) or acknowledge the collision.
- σ in log10(years) against σ in log10(ESALs) — on units if they share a name, on
  the declared comparison if they do not.

### What it does not catch

- **The same quantity under two different names.** No threshold fixes this. It is
  the register's fundamental blind spot and it is why check 3 exists.
- **A wrong number registered once.** Nothing contradicts it.
- **Values that agree numerically but mean different things and were never
  compared.** Units help only where declared.
- **A finding that names no quantity.** A name is never inferred from a label —
  fuzzy matching would manufacture both false collisions and false silence.
- **A move that emitted no findings** (roadmap T0.2).

## The honest empirical result: replayed on the study it was built from, it fires zero times

Run against `study-20260730T034915Z` exactly as that study ran:

| | |
|---|---|
| findings in the runs' reports | 273 |
| findings that named a quantity (registered) | 136 (0 before the source fix) |
| registrations declaring units | **0** |
| conflicts | **0** |

Not because the values were absent. All six structural-elasticity estimates are
in the reports — 3.654 and 7.431 (m12), 0.3215 and 0.4711 (m15), 1.61 and 4.98
(m16) — and every one of them carries `verified: false` and therefore no
artifact, and therefore **no name to collide on**. The `units` field did not
exist at all.

So the register is proven on the real values in the real order **by
construction** (`tests/test_quantity_register.py`, 60 tests, the first two are
those exact cases) and is **unproven on a real run**. The two things it needs are
both now in place and neither is a code change to the checker:

- an explicit `"quantity"` on a finding with no artifact, so an unverified value
  can still be registered;
- `"units"` on every numeric finding, and `"compares"` on a comparison.

Both are in `free_experimenter.py`'s SYSTEM_PROMPT and its JSON contract, with
the measured failure named in the prompt so the instruction carries its reason.
**The next real study is the measurement.** If it registers few names or no
units, the lever is the prompt — not a smarter checker, and never a model inside
one.
