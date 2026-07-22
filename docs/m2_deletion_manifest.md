# M2 — exact-tool ceremony deletion manifest

**Written:** 2026-07-21. **Status:** PREPARED, not executed. Read-only tracing;
zero deletions performed. Feeds Phase B / audit §7 move M2.

**Preconditions before ANY deletion here:**
1. The in-flight live run confirms M1 works end-to-end (exact route ran,
   publishable, `run_record` on disk). M2 removes the fallback ceremony — do not
   delete it until the new path is proven unattended.
2. M1 is committed.
3. Owner signs off **per tier** below (deletions of trust-bearing config are
   STOP-and-rule).
4. Standard rules: stage explicit paths, never `git add -A`; preserve nothing
   the approximate path needs.

**Scope:** the four **mature + exact** tools only — `rdkit, cobrapy, mafft,
homology_search`. `python_experiment` is also mature+exact but has **no**
ceremony at all (no calibration case file, no envelope card, no `onboarding/`
dir — verified), so it needs nothing. Everything for the approximate frontier
(`cavity_2d_cfd, calculix_cantilever_fea, fenicsx_cantilever_elastic`, and the
parked tools) is **out of scope and stays** — it's their live promotion track.

---

## Tier 1 — clean deletions (`git rm`, no/minimal code change)

Safe because nothing reads them at runtime (audit Bucket 1) and no test goes red.

### 1a. Envelope cards (4 files)
```
docs/envelope_card_rdkit.md
docs/envelope_card_cobrapy.md
docs/envelope_card_mafft.md
docs/envelope_card_homology_search.md
```
- **Runtime refs:** none — `card_path` is stored in the registry but never opened
  (proven: python_experiment's `card_path` points at a nonexistent file yet
  routes fine).
- **Dangling after delete:** `substrate_registry.py` `card_path=` literals
  (:249, :271, :316, :347) + prose `notes` (:259, :284) become stale strings.
  **Harmless** (never read as paths). Optional scrub = Tier 3.
- **Test impact:** `tests/test_capability_guard.py:93` uses
  `docs/envelope_card_cobrapy.md` as its "reading a card is ALLOWED" example.
  The guard matches path **patterns**, not file existence, so the test stays
  **green** — but it references a deleted file. Optional: swap the example to a
  surviving card (e.g. `envelope_card_cavity2d.md`). Not required for green.

### 1b. Onboarding dirs (4 dirs)
```
onboarding/rdkit/
onboarding/cobrapy/
onboarding/mafft/
onboarding/homology_search/
```
- **Runtime refs:** none — no module imports `onboarding.*` (audit). The
  dependency runs the other way (onboarding re-exports the contract *from*
  `substrates.py`), so deleting these dirs cannot orphan a live contract.
- **Dangling after delete:** prose `notes` in `substrate_registry.py`
  (:263, :286, :337, :365, :607) mention `onboarding/<tool>/contract.py`. Stale
  comment text only. Optional scrub = Tier 3.
- **Test impact:** none — no test imports these dirs.

### 1c. Calibration report artifacts (7 files)
```
harness/calibration_rdkit_20260719T045938Z.json
harness/calibration_cobrapy_20260719T045947Z.json
harness/calibration_cobrapy_20260719T052035Z.json
harness/calibration_mafft_20260719T045959Z.json
harness/calibration_homology_search_20260719T045954Z.json
harness/calibration_homology_search_20260719T053300Z.json
harness/calibration_homology_search_20260719T071928Z.json
```
- **Runtime refs:** none — timestamped battery outputs, referenced by name
  nowhere in code.
- **Test impact:** `tests/test_capability_guard.py:49` uses
  `calibration_cobrapy_20260719T052035Z.json` as its "reading a calibration
  answer-key is BLOCKED" example. Path-pattern check (`calibration_` segment),
  no stat → stays **green**. Same optional-scrub note as 1a.

### 1d. Dead helper `fidelity_gate_applies`
```
tools/substrate_registry.py:760-766   (the function)
tests/test_instrument_class.py:61,65  (its only callers — assertions)
```
- **Runtime refs:** none — no production caller; the live route decision uses
  `is_approximate()` directly.
- **Action:** delete the function + the two test assertions (or the small test
  method wrapping them). Suite stays green.

**Tier 1 total: 15 files + 1 function + 2 test lines. No behavior change.**

---

## Tier 2 — calibration case files (needs battery + test surgery)

```
harness/calibration_cases_rdkit.json
harness/calibration_cases_cobrapy.json
harness/calibration_cases_mafft.json
harness/calibration_cases_homology_search.json
```
**Not a clean `git rm`** — these are wired into the battery:
- `harness/calibration_battery.py` `_CASE_FILES` maps each of the four ids →
  its case file (:97-100). Deleting the files requires removing these 4 entries.
- The battery's per-substrate input-validator dispatch (:169-182) branches on
  `rdkit/cobrapy/homology_search/mafft`; those branches become dead once the
  ids leave `_CASE_FILES`.
- `tests/test_calibration_battery.py` exercises the battery across the enrolled
  substrates and will need its exact-tool expectations updated.

**Decision the owner must make:** deleting these permanently removes the ability
to re-calibrate the four exact tools. Defensible — they are *mature* (re-running
calibration cannot change a deterministic tool's already-settled verdict) — but
it's battery surgery, not a file delete. **Recommendation:** do Tier 1 first
(pure win, zero risk); treat Tier 2 as a separate, explicit yes because it edits
live harness code and a test. If in any doubt, **keep the case files** — they're
offline-only and cost nothing to leave.

---

## Tier 3 — optional registry prose scrub (defer / lowest priority)

Blank the now-dangling `card_path` values and scrub the calibration/onboarding
mentions in the four tools' `notes` in `tools/substrate_registry.py`
(:249,259,263,271,284,286,316,337,347,365,607).
- **Risk:** low — no test asserts these specific `card_path`/`notes` values for
  the four tools (checked); `card_path`/`notes` are **not** model-visible
  surfaces, so cavity/byte-identity is untouched. But the registry is
  trust-bearing config → STOP-and-rule discipline; do it deliberately, not as a
  reflex. Leaving the stale strings is harmless.

---

## Explicitly NOT touched (guardrails)
- Approximate tools' calibration cases/reports, envelope cards, `onboarding/`
  dirs — their live promotion track.
- `cavity_2d_cfd` anything; the frozen-anchor byte-identity surfaces.
- `stages/verification.py` (the wall); locked `schemas.py`; `vocab_for`;
  the `substrate_id` payload key.
- The calibration battery/ledger machinery itself (only the four exact-tool
  *entries* are in scope, and only in Tier 2).

## Test-impact summary
| Tier | Files/edits | Tests that move |
|---|---|---|
| 1a cards | 4 rm | none red; `test_capability_guard.py:93` example stale (optional) |
| 1b onboarding | 4 dirs rm | none |
| 1c reports | 7 rm | none red; `test_capability_guard.py:49` example stale (optional) |
| 1d dead helper | 1 fn + 2 lines | `test_instrument_class.py` (remove 2 assertions) |
| 2 case files | 4 rm + battery edits | `test_calibration_battery.py` (update), battery `_CASE_FILES` + dispatch |
| 3 registry prose | edits only | none |

## Execution checklist (when unblocked)
1. `git rm` the Tier-1 explicit paths (15 files) + `git rm -r` the 4 onboarding
   dirs.
2. Delete `fidelity_gate_applies` + its 2 test assertions.
3. Run full suite → green (modulo the unrelated `MemoryPin` journal-md5 pin).
4. Commit Tier 1 with explicit paths.
5. Tier 2 only on a separate explicit yes; Tier 3 optional/deferred.
