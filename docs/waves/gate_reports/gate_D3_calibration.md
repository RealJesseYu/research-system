# Gate report — BIO Wave D.3 calibration (the 4 runnable tools)

**2026-07-19. Calibration batteries run in the owner's Terminal (`--repeats 3`,
serial); read here per the packet's rule #3 (in-envelope trust rate and
out-of-envelope defer rate reported SEPARATELY). Nothing promoted — routable
still 5/0 mature (D.4 promotes). Canonical committed copy; result JSONs committed
as evidence.**

## The headline: the defer-fix WORKS on all 4
- **In-envelope: 0 defers across all 4 tools** (0/60 draws). Reflexive
  in-envelope defer is gone.
- **Out-of-envelope: 60/60 defer.** The gate catches everything outside the card.
- **Wrapper track 5/5 each** (input jails); **ledgers fidelity=0 / override=0**
  each (zero silent trusts, hook witnessed non-mature throughout).

## Per-tool confusion matrix (raw gate verdict, N=3)
Each row: 5 in-envelope cases × 3 draws = 15 in draws; 5 out × 3 = 15 out draws.

| tool | IN: trust / refine / defer | **in-envelope trust rate** | OUT: defer | **out-of-envelope defer rate** | wrapper | ledger | verdict |
|---|---|---|---|---|---|---|---|
| `rdkit` | 15 / 0 / 0 | **100%** | 15 | **100%** | 5/5 | 0/0 | **CLEAN (30/30)** → promote |
| `mafft` | 15 / 0 / 0 | **100%** | 15 | **100%** | 5/5 | 0/0 | **CLEAN (30/30)** → promote |
| `cobrapy` | 14 / **1** / 0 | **93.3%** | 15 | **100%** | 5/5 | 0/0 | **SPLIT (29/30)** — G02 one refine, modal trust → N=7 re-run |
| `homology_search` | 13 / **2** / 0 | **86.7%** | 15 | **100%** | 5/5 | 0/0 | **SPLIT (28/30)** — G03 refine 2/3 vs trust → N=7 re-run |

## Reading it (rule #3)
- **The ~50% overall defer is the correct SHAPE** (5-in / 5-out slates by design),
  not gate over-defer.
- **No in-envelope DEFER anywhere** — so no card is too vague in the
  defer-producing direction; the defer-fix (R-CARD-2 decisive cards) holds.
- **The two splits are REFINE, not defer** — a milder signal: the gate is neither
  trusting nor deferring the case, it wants a downstream check. Per the rule,
  splits earn a **higher-N re-run** before promotion:
  - **cobrapy G02** (FBA on genome-scale iML1515 as a relative screen): 1 refine.
  - **homology_search G03** (HMMER profile-search e-value as significance): refine 2/3.
- **rdkit + mafft need no re-run** (clean 30/30).

## Decision (per the owner)
- rdkit + mafft: promote at D.4.
- cobrapy + homology_search: **re-run at `--repeats 7`, serial**. If G02/G03 go
  trust-dominant → promote. If refine **persists** → that case's CARD criterion is
  loose; **fix the CARD (not the gate)**, recommit the slate, re-run. Do not
  promote a miscalibrated card.

## Evidence (committed)
`harness/calibration_rdkit_20260719T045938Z.json`,
`harness/calibration_cobrapy_20260719T045947Z.json`,
`harness/calibration_homology_search_20260719T045954Z.json`,
`harness/calibration_mafft_20260719T045959Z.json` — the raw gate draws + wrapper
records + hook witness + ledger, pre-registered labels in the slates.

## Tasks (owner)
- [ ] Re-run cobrapy + homology_search at `--repeats 7` (serial, Terminal,
      `caffeinate`); rdkit + mafft need none.
- [ ] Send the 2 re-run JSONs — I confirm trust-dominant (→ D.4 promote) or
      persistent-refine (→ fix the card, recommit, re-run).
- [ ] D.4 promotion staged separately (build, not merged until the re-runs
      confirm) — fires in one FAST-green merge.
