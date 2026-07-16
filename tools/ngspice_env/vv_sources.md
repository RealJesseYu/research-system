# ngspice V&V / benchmark sources — located for the LATER card session

This session is wrapper + container + self-checks + docs index only. This is a
**list and an inventory**, captured so the later substrate-card session does not
have to re-find them. No card text is written here.

## The headline finding

**For this regime the validation reference is closed-form circuit theory, not a
published benchmark suite — ngspice has no NAFEMS analog.** The FEA substrate
could point at a standardized third-party suite with published target values
(NAFEMS LE benchmarks). Nothing equivalent exists for ngspice: the circuit-
simulation community validates against SPICE3f5 behaviour, silicon measurements,
and analytic results, not against a numbered public benchmark set.

This is not an assertion — it is measured against the shipped source (below).

## Inventory: the upstream `tests/` suite

Source: `ngspice_42+ds.orig.tar.gz`, obtained via `apt-get source ngspice`
inside `ngspice-prod` — i.e. **the exact source that built the container's
binary** (`42+ds-3build1`), not a nearby upstream tarball. The SourceForge
release tarball for 42 was not retrievable at its conventional URL (404); the
Ubuntu source package is a closer provenance match anyway.

  - `tests/` — 29 subdirectories, **113 `.cir` decks, 107 `.out` reference
    outputs**. This IS a real regression suite with expected results.
  - `examples/` — 31 subdirectories, 237 `.cir` decks. Demonstrations, mostly
    without reference outputs.

### How much of it is usable for THIS regime: 3 of 113

Every `.cir` in `tests/` was screened by element letter (element lines only;
dot-commands, comments and continuations ignored). Decks using **only**
R L C V I E F G H:

  | deck | usable as a v1 reference? |
  |---|---|
  | `polezero/filt_rc.cir` | **No** — drives `.pz` (pole-zero), which is not one of the wrapper's four analyses |
  | `resistance/res_partition.cir` | **No** — uses an AC-specific resistance (`r2 2 0 5K ac=15k`), a feature the v1 contract does not describe |
  | `regression/pipe/alter-1.cir` | **No** — no `.out` reference output ships with it |

The other **110 decks are out of regime**, dominated by device models the
regime screen rejects by construction. Offending first letters by frequency:

    Q:53 (BJT)  M:29 (MOSFET)  O:29 (lossy tline)  D:27 (diode)  S:25 (switch)
    X:18 (subckt)  Z:14  T:13 (tline)  A:13 (XSPICE)  B:11 (behavioral)
    P:9  N:2  Y:2  J:1 (JFET)

**Net: zero of the 113 upstream decks are usable as-is as a v1 regression
reference.** The suite validates the semiconductor device models — precisely the
physics this regime excludes. This is the concrete basis for the headline above.

## The actual validation references for v1

1. **Closed-form circuit theory** — the wrapper's own built-in analytic
   functions, computed from the same numbers the netlist carries:
     - `analytic_divider_vout(vin, r1, r2)` = vin·R2/(R1+R2)
     - `analytic_rc_corner_hz(r, c)` = 1/(2πRC)
     - `analytic_rc_step_v(t, vin, r, c)` = vin·(1−e^(−t/RC))
     - `analytic_rlc_step_peak(vin, r, l, c)` = vin·(1+e^(−ζπ/√(1−ζ²))), ζ<1
   Measured agreement is recorded in
   `onboarding/ngspice_linear_passive/selfcheck_evidence.json`.

2. **ngspice manual v42, worked examples** — the indexed manual carries the
   authors' own reference circuits (e.g. §21 "Example Circuits"). Version-matched
   to the container binary with zero skew.

3. **SPICE3f5 lineage** — ngspice descends from Berkeley SPICE3f5; the classic
   SPICE benchmark circuits are the de-facto community reference. Useful for the
   nonlinear regimes this card does NOT cover.

4. **`tests/regression/`** (41 decks) — upstream's own regression set. Not usable
   for v1 today (see above), but it is the right place to look when the regime
   grows beyond linear passive.

5. **Two-port network theory / filter design tables** — standard textbook
   references (e.g. Zverev, *Handbook of Filter Synthesis*) with tabulated
   closed-form responses for RLC ladder filters. This is the natural growth path
   for a validation set as the family widens beyond single-pole RC and series RLC.

## Open card question raised by this inventory

`resistance/res_partition.cir` uses `r2 2 0 5K ac=15k` — a per-analysis
resistance value. It is linear and passive, so it arguably belongs in the
regime, but the v1 contract does not describe it and the screen does not
currently reject it (the value parser reads the positional value and ignores the
trailing `ac=` token). Flagged for the card session alongside the K/coupled-
inductor question.
