# Envelope Card — (autodock_vina, rigid_pocket_dock)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. RE-TIERED T2 → DEFERRED**
> (owner-ruled 2026-07-18): AutoDock Vina is an x86 C++ tool with NO aarch64
> build (no bioconda package, no pip wheel), so it will not install on this
> colima/aarch64 host. The ruled fields (regime/class/trust-split/C1-hole) and
> the pure-Python input jails ARE proven now; the docking envelope defers.
> HUMAN-FACING ONLY (R-20.5-1). ENROLLED `calibrating`/`routable=False` — inert
> (`contract_for("autodock_vina")` raises).

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, regime) pair |
| Substrate | `autodock_vina` (**ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **rigid_pocket_dock**: dock a flexible ligand into a RIGID receptor pocket within a defined search box, empirical scoring. |
| Tool | **AutoDock Vina** (x86-only). **Pinned attempt: NO aarch64 build available** — bioconda `autodock-vina` → "No entries matching"; `pip install vina` (aarch64) → "No matching distribution ... from versions: none". |
| Wrapper | `tools/run_autodock_vina.py` (deterministic Python, no AI; docking logic written, exercised at provisioning) |
| Class | **filter** — the docking score is a RELATIVE screen, not absolute affinity |
| Contract text (staged) | `onboarding/autodock_vina/contract.py` — moves to `substrates.py` at D.4 |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | pure-Python input-jail behaviour MEASURED; **no docking envelope** — Vina does not install on this host (see §3A). |
| Signature | `unsigned` |
| Provenance state | `drafted-by-agent` — and **DEFERRED** (measured envelope not produced) |

## 3. Validated envelope

### 3A. Measured ranges — **PENDING-PROVISIONING (needs a DIFFERENT ARCHITECTURE)**
**No docking numbers appear here, by ruling.** AutoDock Vina has no aarch64
binary; it cannot run on this host.

**THE UN-DEFER REQUIREMENT (specific to THIS tool — different from cas_offinder).**
Two tools now defer for DIFFERENT hardware reasons, and they do NOT un-defer under
the same conditions:
- `cas_offinder` installs anywhere but computes silently wrong on aarch64 — it
  needs a **VALIDATED ENVIRONMENT** (prove kernel correctness via the known-answer
  probe before trusting).
- **`autodock_vina` needs a DIFFERENT ARCHITECTURE** — it will not install on
  aarch64 at all, but runs normally on x86.

So Vina un-defers only on: **an x86 host where AutoDock Vina installs**, AND real
docking §3A produced there, AND **fixed-seed determinism proven** (an identical
repeat returns an identical score with `VINA_SEED`), AND **the convergence jail
triggered** (a failed/degenerate search returns no number). Until all four hold on
that host, no docking number is trusted.

### 3B. Ruled envelope bounds (R-CARD-2 — from the A-table + owner rulings)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **V1 — DETERMINISM** | Fixed seed (`VINA_SEED`) | `CHECKABLE` (at provisioning) | an identical repeat returns an identical score | reproducible → the §3A number is trustworthy; not reproducible → the envelope is not signed |
| **V2 — THE CONVERGENCE GATE (did-it-work)** | The search must converge to a valid pose | `CHECKABLE:semantic` (in code) | Vina exits cleanly AND a scored pose (mode 1 affinity) is returned | converged → **TRUST the score as a RELATIVE screen**; failed/degenerate search (error, no scored pose) → **defer/setup_error**, no number |
| **V3** | Receptor/ligand on the allowlist; box well-formed | `CHECKABLE:membership+numeric` (pre-run) | allowlist membership; box center finite, sizes in (0, 100] Å | valid → eligible; else → **setup_error** (proven now) |
| **V4 (C1-hole) — HARD** | docking_score is a RELATIVE screen within a GIVEN setup | **JUDGMENT / KNOWN GAP** | **none the gate can read** — the search converging says NOTHING about whether the receptor was prepared correctly or the box placed sensibly | trust side = a **relative** screen within a **human-validated** receptor+box; NEVER absolute affinity, NEVER "the pose is correct". **Receptor prep + box placement are UNVALIDATED UPSTREAM inputs**: a confident, converged score on a *bad* setup is indistinguishable from one on a good setup (silent-wrong, but UPSTREAM of the tool — so the card carries it, not a structural guard). |

## 4. Known failure modes
- **4A. No aarch64 binary → can't run here (install-time, honest).** Total failure at the install step — nothing to run, nothing to mislead. Un-defer needs an x86 host (§3A).
- **4B. Failed/degenerate search → defer (V2, convergence gate).** Proven at provisioning by triggering.
- **4C. A converged score on a wrongly-prepared receptor / mis-placed box → the un-catchable case (V4, the C1-hole).** The search DID work; the inputs were wrong upstream, where the tool can't see. Not wrapper-catchable — the card carries it.
- **4D. Bad input (receptor/ligand/box) → setup_error (V3).** Proven now.

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Whether the search converged to a scored pose (V2) | Whether the receptor was prepared correctly (V4) |
| Input validity: allowlist + box (V3) | Whether the box is placed on the real pocket (V4) |
| (at provisioning) determinism under the fixed seed (V1) | Whether the score reflects true binding affinity (V4) |

## 6. Extraction contract + QoI status
Typed input `{receptor, ligand, box, quantity}`. QoI = `docking_score` (best-mode
affinity, kcal/mol), returned only behind the V2 convergence gate, with a fixed
seed (V1). `RECEPTOR_ALLOWLIST`/`LIGAND_ALLOWLIST`/`QOI_FIELDS` are the single
source, imported at promotion. **Status: DEFERRED** — no measured value endorsed
until the §3A un-defer requirement holds on an x86 host.

## 7. Cost model
**PENDING-PROVISIONING** — no trustworthy timing here (Vina does not run). Docking
cost scales with exhaustiveness and box size on an x86 host.

## 8. Negative space + open watches
Out of scope: flexible-receptor docking; absolute binding-affinity claims (V4);
receptors/ligands outside the baked allowlist; box placement / receptor-prep
validation (upstream, human). **Open watches:** (1) **THE UN-DEFER REQUIREMENT
(§3A)** — an x86 host + real §3A + fixed-seed determinism + convergence jail
triggered. (2) External reviewer — pending. (3) Registration deferred —
`contract_for("autodock_vina")` must keep raising until a D.4 ruling. (4) Real
receptor/ligand PDBQTs baked at provisioning.
