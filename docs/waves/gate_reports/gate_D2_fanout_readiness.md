# Gate report — BIO Wave D.2 fan-out readiness (env measured, plan locked)

**2026-07-18, era `6befb63`. Corrections 1 & 2 LANDED; substrate builds are the
next phase. This report surfaces a disk-measured constraint that changes HOW the
fan-out runs (disk beats dictation).**

## What landed this turn
- **A-table corrections 1 & 2** ruled and committed (`84fda01`): six regime
  shapes replaced with real task regimes; every trust-split rewritten to gate
  only on checkable inputs; training-distribution moved to the C1-hole; BLAST+
  HMMER bundled to `homology_search` (census **12**). Canonical A =
  `gate_reports/gate_D2_pre_fanout.md`; the draft's stale 13-row Part A marked
  SUPERSEDED (drift guard).
- **Confirmed:** all backend/tool/database selectors are typed SPEC FIELDS.
- No wrapper/substrate built yet; no test added; no code touched (docs only).

## The measured constraint (why fan-out isn't "just start typing")
Probed the environment on disk:

| Fact | Measured |
|---|---|
| Python | 3.14.2 |
| Bio libs installed | **none** (`rdkit`, `cobra`, `Bio` all missing) |
| Bio CLI tools on PATH | **none** (cas-offinder, blastn, hmmsearch, mafft, vina) |
| PyPI reachable | yes — `pip --dry-run rdkit` resolves `rdkit-2026.3.4` (cp314 wheel) |
| Network to bio APIs | partial — `rest.uniprot.org` returns **HTTP 403** |
| Docker/colima | up: `ngspice-prod`, `dolfinx-prod`, `ccx-prod` (the existing substrate containers) — no bio containers |

**The architecture invariant decides the dep-home:** every existing substrate
runs its tool in a **Docker container** (`*-prod`), and the wrapper reaches it by
`docker exec` — the main venv stays clean (proven repeatedly by the "pip
fingerprint identical" checks). Bio tools inherit this: **each buildable bio tool
gets its own `<tool>-prod` container; the wrapper does `docker exec`; nothing is
pip-installed into the project venv.** (Applying the invariant, not inventing a
policy. One-line owner override available: pure-Python tools like RDKit/COBRApy
*could* share a dedicated bio venv instead of a container each — lighter, but a
new pattern. Default = container-per-tool, per the invariant.)

## Per-tier buildability (honest, from the probe)
| Tier | Substrates | Buildable-here reality |
|---|---|---|
| **T1** | `rdkit`, `cobrapy`, `cas_offinder` | rdkit/cobrapy: **real build now** (pip into a container). cas_offinder: needs a compiled binary (bioconda/build) — real but heavier. |
| **T2** | `autodock_vina`, `crispr_guide_scoring`, `homology_search`, `mafft` | CLI tools — **real build**, but need non-pip installs into containers (bioconda/brew). |
| **T3** | `boltz2`, `proteinmpnn`, `retrosynthesis` | **cannot run here** (no GPU; large weights). Wrapper + 7 surfaces + card + row build; execution jails proven by triggering real subprocess/timeout failures; **real battery only once provisioned** (packet binding). |
| **T4** | `alphafold_db`, `bio_db_lookup` | network APIs; partly blocked (UniProt 403). Wrapper + surfaces + card + row build; **jails proven by triggering a real network failure** (unreachable host / timeout), not config; **battery deferred** (packet binding). |

## Honest scope statement
12 substrates × a full `56e16d9`-class unit (wrapper + 7 dispatch surfaces +
R-CARD-2 card built from REAL measured evidence + state-key confidence + registry
row + tests, staged to `onboarding/<substrate>/`, serial FAST-green merges) is a
**phased multi-session build**, not a single-turn one — the reference unit
(ngspice) is a ~400-line evidence-cited card plus wrapper plus slate plus tests.
Cards must be filled from real runs (the doctrine: "a check that cannot fail is
not a proof"), so T1/T2 cards need the tool actually run; T3/T4 cards are honest
about un-run execution and prove only what can be triggered here.

**Recommended execution:** build in tier order, ONE substrate per increment, each
in its own container/worktree, FAST-green each merge, Gate-D.2 report updated per
increment. Start `rdkit` (cleanest real build). Nothing promoted (D.4) until a
real passing battery.

## Gate D.2 status line (this turn)
- Era holds (`6befb63`); cavity byte-identical (untouched — docs only this turn).
- Routable **5 / 0 mature** (no registry change).
- Tests **added: 0** this turn (docs only); suite unchanged at 1219 collected.
- FAST: green as of D.1b; **unaffected** — no code changed since (docs-only commits).

## Tasks (owner)
- [ ] Confirm dep-home = **container-per-bio-tool** (default, per the invariant), or override to a shared bio venv for the pure-Python T1 tools.
- [ ] Green-light starting the build at **T1 `rdkit`**, one substrate per increment, serial FAST-green merges (or reorder).
- [ ] Acknowledge T3 (GPU) / T4 (network) build here to the enrollment+card+jail level, with **real batteries deferred to provisioning** per the packet bindings (no stub battery).
