# Envelope Card — (cas_offinder, bounded_enumeration)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING.** This substrate is re-tiered
> **T1 → DEFERRED** (owner-ruled 2026-07-18): Cas-OFFinder's OpenCL kernel does
> NOT compute correctly on this colima/aarch64 host (pocl exits 0 with 0
> matches), so its MEASURED envelope cannot be built here and MUST NOT be filled
> from kernel-produced numbers. The ruled fields (regime/class/trust-split/
> C1-hole) and the failure-honesty (input jails + the known-answer guard) ARE
> proven now; only §3A defers. HUMAN-FACING ONLY (R-20.5-1). ENROLLED
> `calibrating`/`routable=False` — inert (`contract_for("cas_offinder")` raises).

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, regime) pair |
| Substrate | `cas_offinder` (**ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **bounded_enumeration**: exhaustive enumeration of near-match sites to a guide+PAM in a reference genome within a fixed mismatch budget. No scoring model — pure string search. |
| Tool | **Cas-OFFinder 2.4.1** + **pocl 7.1** (bioconda/conda-forge, aarch64), in `cas-offinder-prod` (from `cas-offinder-img`, the reusable bioconda base). **PINNED.** |
| Wrapper | `tools/run_cas_offinder.py` (deterministic Python, no AI) |
| Class | **answer** — the count IS the tool's exact enumeration output (when the kernel is validated) |
| Contract text (staged) | `onboarding/cas_offinder/contract.py` — moves to `substrates.py` at D.4 |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | input-jail + known-answer-guard behaviour MEASURED in `cas-offinder-prod`; **no measured enumeration envelope** — the kernel is unvalidated on this host (see §3A). |
| Signature | `unsigned` |
| Provenance state | `drafted-by-agent` — and **DEFERRED**: the measured envelope has not been produced |

## 3. Validated envelope

### 3A. Measured ranges — **PENDING-PROVISIONING (do not fill from this host)**
**No measured enumeration numbers appear here, by ruling.** On this colima/aarch64
host, Cas-OFFinder's pocl OpenCL kernel returns **0 matches for a genome that
provably contains the site** (an all-N query at mismatch budget 10 returns 0;
`grep` confirms the site is present). The tool exits 0 — so a naive read would
record a fabricated "0 off-targets", the DANGEROUS wrong answer for CRISPR.

**RE-VALIDATION GATE (the un-defer condition).** The real battery may run ONLY
in an environment where the kernel is first validated against a **known-answer
case**: a baked genome containing exactly one known-present guide+PAM site must
be **found** (≥1 match) before any measured count is trusted. This gate is built
into the wrapper as the KNOWN-ANSWER GUARD (§4) and is proven to FIRE on this
host (the probe finds 0 → the wrapper refuses). Un-deferring `cas_offinder` = the
guard passing on the target host, then filling this §3A from that host's runs.

### 3B. Ruled envelope bounds (R-CARD-2 — from the A-table; the trust story does not depend on §3A)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **K1 — THE KNOWN-ANSWER GUARD** | The kernel must find a known-present probe site | `CHECKABLE:membership` (in code, per run) | the baked known-answer probe returns ≥1 match, BEFORE the real query runs | probe found → the enumeration is trustworthy, **TRUST the count**; probe not found → **defer/setup_error**, qoi=None (never a fabricated count) |
| **K2** | Guide is a 20-nt DNA protospacer | `CHECKABLE:membership` (pre-run) | `guide` matches `^[ACGT]{20}$` | valid → eligible; else → **setup_error**, rejected pre-run |
| **K3** | Genome on the baked allowlist | `CHECKABLE:membership` (pre-run) | `genome ∈ GENOME_ALLOWLIST` | on list → eligible; off list → **setup_error** |
| **K4** | Mismatch budget in range | `CHECKABLE:numeric` | `0 ≤ mismatches ≤ 10`, int | in range → eligible; else → **setup_error** |
| **K5 (C1-hole)** | Sequence match ≠ functional off-target | **JUDGMENT / KNOWN GAP** | **none the gate can read** — chromatin accessibility and actual cutting efficiency are outside every text this system holds | any claim that the count is a set of FUNCTIONAL off-targets → **defer**; the count is a SEQUENCE-match enumeration only |

## 4. Known failure modes
- **4A. Silent-wrong-kernel → fabricated 0 (structural, K1).** The phase's worst "check that cannot fail": Cas-OFFinder exits 0 and returns 0 matches from a kernel that did not compute; a wrapper CANNOT distinguish that from a real 0. **The known-answer guard is the only defense** — the wrapper runs a baked known-present probe every call and refuses (qoi=None) unless it is found. Proven by triggering on this host (probe → 0 → refuse). This is why §3A defers.
- **4B. Length-mismatch input → critical error, no output (kernel-independent).** MEASURED: a query whose length ≠ the pattern length makes Cas-OFFinder print "Critical error! The length of target sequences should match…" and write NO output file. Caught by the wrapper (no COUNT → refuse).
- **4C. Missing/unindexed genome directory → error, no output (kernel-independent).** MEASURED: a non-existent genome path prints "An error has occured while opening directory…" and writes no output. Caught.
- **4D. Bad guide / genome / mismatch input → setup_error (K2–K4).** Rejected by name pre-run.
- **4E. Sequence match read as functional off-target → defer (K5, the C1-hole).**

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Whether the known-answer probe found its site (K1) — the load-bearing signal | Whether a sequence match is a FUNCTIONAL off-target (K5) |
| Input validity: guide/genome/mismatch (K2–K4) | Whether the mismatch budget captures all biologically-relevant off-targets |
| A length-mismatch / missing-genome error, no-output | The measured enumeration envelope on this host (kernel unvalidated) |

## 6. Extraction contract + QoI status
Typed input `{genome, guide, mismatches, quantity}`. QoI = `off_target_count`
(the number of enumerated near-match sites), returned ONLY behind the K1
known-answer guard. `GENOME_ALLOWLIST` / `QOI_FIELDS` are the single source,
imported at promotion. **Status: DEFERRED** — no measured value is endorsed until
the re-validation gate passes on the target host.

## 7. Cost model
**PENDING-PROVISIONING** — no trustworthy timing on this host (the kernel does not
compute). Install/exec overhead ~1 s; enumeration cost scales with genome size on
a validated host.

## 8. Negative space + open watches
Out of scope: functional/epigenetic off-target relevance (K5); genomes outside the
baked allowlist; PAMs other than SpCas9 NGG (v1); non-20-nt guides. **Open
watches:** (1) **THE RE-VALIDATION GATE (§3A)** — un-defer only after the
known-answer guard passes on a validated-kernel host; fill §3A there. (2) External
reviewer — pending. (3) Registration deferred — `contract_for("cas_offinder")`
must keep raising until a D.4 ruling. (4) Real reference genomes are baked at
provisioning; today only the known-answer probe genome exists.
