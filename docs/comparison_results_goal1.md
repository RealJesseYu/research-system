# Goal 1 results — verified, arms A and B

**2026-07-29.** Arm C still running. Verification done per
`docs/comparison_protocol.md` §6: criteria 2 and 3 checked **mechanically**,
from each arm's raw data, not from its summary.

---

## Protocol deviation to record up front

**Arm A was not the arm the protocol specified.** §2 defines A as "bare chat,
claude.ai, no tools". The run reported "toolchain is ready" and "ran out of tool
budget" — it had code execution. So A is a *tooled chat*, not the no-tools
floor.

That is not a spoiled run, but it changes what it measures: there is now **no
floor arm**, and A sits much closer to B than intended. Record it; do not
retro-fit the protocol to it.

---

## Arm B — Claude Code, one prompt. VERIFIED.

Deliverable at `~/ibeta-lib`: `ibeta.h`, generated tables, reference generator,
sweep harness, `REPORT.md`, and both CSVs (13 MB of raw data).

**I re-derived the headline from the raw CSVs rather than running its analysis
script.** Row-aligned `test_points.csv` against `sweep_output.csv` by value
(71,456 rows, **0 misaligned**), took the smaller tail per row, excluded the
sub-1e-300 region B documents as physically impossible in double:

| claim | B stated | independently recomputed | verdict |
|---|---|---|---|
| sweep size | 71,456 | 71,456 | ✅ |
| violations of 1e-12 | 6 | **6** | ✅ |
| worst relative error | 1.41e-12 | **1.405e-12** | ✅ |
| violations confined to one corner | yes | yes — `a=0.01,b=1000` and its mirror | ✅ |

- Points compared: **57,282**; subnormal excluded: 11,724.
- **It misses the stated bound**, by 40% at 6 of 57,282 points (0.0105%).
- **And it says so, precisely, unprompted.** Criterion 6 is not just passed but
  is the arm's strongest feature: it names the corner, quantifies it, explains
  the mechanism, and scopes out the fix (Temme-style asymptotic, as Boost/TOMS
  708 use) rather than hiding it.

**Criterion 3 (numbers reproduce): the strongest possible pass** — the raw data
is shipped, and a third party recomputed the headline from it and got the same
answer. That is what reproducibility is supposed to mean.

## Arm A — tooled chat. NOT FINISHED, and one claim does not reproduce.

Stopped roughly two-thirds through on tool budget. **No deliverable**, so
criteria 1–5 cannot be scored — an unfinished library is not a worse library,
it is an absent one.

What it did produce was strong work: the Stirling-correction design (avoiding
`lgamma` in the power term) is the same insight B relied on, its Δ validation
against mpmath was real, and it caught two genuine bugs in its own code.

**But its headline technical claim does not reproduce.** It reported that
mpmath's `betainc` "is losing the small tail entirely — returns a constant
≈1.4e-51 for every x" for a<1 with large b, and rebuilt its reference on direct
2F1 as a result. Tested directly:

- `a=0.01, b=1000` across x ∈ [1e-30, 1e-3]: `betainc` is **not** constant and
  agrees with the direct 2F1 route to all shown digits.
- Tiny-tail regime `a=1000, b=0.01, x=0.5` (true I ≈ 2.0e-306): `betainc` vs
  direct 2F1 differ by **1.28e-33 at dps=35**.
- The complement direction does return exactly `1.0` — but that is correct:
  1 − 2e-306 *is* 1.0 at any finite precision, and the spec bounds only the
  smaller tail.

So **arm B's reference — which uses `mp.betainc` in both directions — is sound**,
and arm A rebuilt its reference to fix a bug that does not appear to exist.
A cost some of its remaining budget on that.

**Criterion 6 for A: passed, emphatically.** It refused to write a polished
summary of unfinished work, listed exactly what was open, and declined to ship
files with an unresolved accuracy question. That is the behaviour you want.

## Standing so far

| criterion | A (tooled chat) | B (Claude Code) |
|---|---|---|
| 1 answers the question | ✗ unfinished | ✅ |
| 2 headline correct | n/a | ✅ verified independently |
| 3 numbers reproduce | n/a | ✅ recomputed from shipped raw data |
| 4 alternatives measured | partial | ✅ three methods, measured thresholds |
| 5 usable tomorrow | ✗ | ✅ single header, reproduce commands |
| 6 honest about limits | ✅ strong | ✅ strong |
| 7 cost | tool budget exhausted | one session |

**Arm B set a high bar**, and the bar is not "it worked" — it is *shipped raw
data that a third party could recompute the headline from, and an honest,
quantified statement of where it fails.*

**What arm C has to beat.** Not a straw man. If C's deliverable is not
independently recomputable, or if it reports the extreme-skew corner as clean, it
loses on the criteria that matter — regardless of how much machinery it ran.

## Do not do

Do not revise the goal, the criteria, or the 1e-12 bound now that two arms have
run. The bound being slightly unmeetable in one corner is **information about the
problem**, and both arms surfaced it independently. That is a good outcome, not a
spec defect.
