# MERGE_NOTES — `ngspice_linear_passive` (for the Wave Guide)

Session 2, 2026-07-16. Everything in `onboarding/ngspice_linear_passive/` is
**staged**: nothing outside this directory imports any of it, and the substrate
is unregistered, unroutable, and uncalibrated. This file is the checklist.

> **Read `registry_row_fragment.py` before touching the registry.** The session
> brief instructed a `_CONTRACTS` entry. Following that instruction turns the
> suite red. The fragment explains why and what to do instead.

---

## 0. Where this work lives (read first)

The session-2 brief said "Branch: `build-ngspice` (same worktree as session 1)".
That is not where a session opened at `/Users/jesseyu/research-system` lands —
that path is the **`build-scipy`** worktree. The ngspice work is at:

| | |
|---|---|
| Worktree | `/Users/jesseyu/research-system-ngspice` |
| Branch | `build-ngspice` |
| HEAD at session-2 start | `07816ba` (the shared pre-scipy base — **no ngspice commits exist**) |

**Everything from session 1 and session 2 is UNCOMMITTED** (`git status` shows
`?? onboarding/`, `?? tools/run_ngspice.py`, `?? tests/test_run_ngspice.py`,
`?? retrieval/ngspice_docs_*`). The branch carries no ngspice history at all.
First merge action: **commit this tree**, or a stray `git checkout` loses the
whole substrate.

### The `cases_ngspice/` split (mildly surprising, worth 30 seconds)

`tools/run_ngspice.py:119` pins the case root to an **absolute path in the OTHER
worktree**:

```python
SHARED_HOST = Path("/Users/jesseyu/research-system/cases_ngspice")  # Mac side
```

and the `ngspice-prod` container bind-mounts exactly that
(`/Users/jesseyu/research-system/cases_ngspice -> /work/cases`). So run evidence
lands in `/Users/jesseyu/research-system/cases_ngspice/` (516 files at time of
writing) **no matter which worktree the code runs from**. Consequences:

- The staged `.gitignore` line is needed in **`build-scipy`'s** `.gitignore` to
  keep that directory untracked *where it actually appears*, and in
  `build-ngspice`'s for when the paths converge at merge.
- If the wrapper ever moves to a repo-relative case root, that is a behaviour
  change for the container mount too — not a tidy-up. Left alone this session.

---

## 1. The fragments

| Fragment | Lands in | Kind |
|---|---|---|
| `registry_row_fragment.py` | `tools/substrate_registry.py` `_REGISTRY` | one row, hand-pasted |
| `battery_wiring_fragment.py` | `harness/calibration_battery.py` | **two edits — the actual blocker** |
| `schema_fragment.py` | `stages/stage2_spec.py` | **NOT a paste — a ruling** |
| `router_entry.md` | `docs/substrate_registry.md` | one table row + prose |
| `gitignore_line.txt` | `.gitignore` | one line |

### `registry_row_fragment.py` — row only, NO `_CONTRACTS` entry
`calibrating` / `routable=False` / `cost_tier="low"`, appended after the
`code_sklearn_eval` row and **before** `web_search` (enrollment order is
asserted). **No `_CONTRACTS` entry** — `contract_for("ngspice_linear_passive")`
must keep raising `LookupError`, exactly as it does for FEA and code. That raise
is the invariant `tests/test_contract_registry.py::
test_never_falls_back_to_cavity_for_a_contractless_substrate` exists to prove.

### `battery_wiring_fragment.py` — without this the slate is inert
Two edits: add the case file to `_CASE_FILES`, add the validator to
`_wrapper_validator`. Both `load_cases("ngspice_linear_passive")` and
`_wrapper_validator("ngspice_linear_passive")` raise `KeyError` today, so the
15-case file cannot be loaded by anything. **This fragment was not in the
session brief's list**; it is here because shipping the slate without it would
be shipping a file no driver can read.

### `schema_fragment.py` — stop and read; do not paste
`stages/stage2_spec.py` is **CFD-pinned** (it imports its QoI vocabulary from
`tools.run_cfd`). ngspice's QoI shape (`kind`/`target`/`reduction`/`at`) is not
a superset of CFD's (`field`/`operation`/`component`/`mask`) — only `max` and
`min` collide, and by coincidence of English. Naively merging the vocabularies
would make `volAverage` a legal circuit reduction and `corner_3db` a legal
cavity operation, and `validate_spec` would pass both. The fragment names the
dispatch-by-substrate design this actually needs, and records that **nothing
blocks on it**: ngspice is unroutable, Stage 2 never authors an ngspice spec,
and the battery does not touch `stage2_spec` at all. Wake it when routing is
proposed.

### `gitignore_line.txt` — `/cases_ngspice/`
**Correction to the brief:** it said the sibling session "has it checked out
modified; do not touch the real file". In this worktree `.gitignore` is
**unmodified vs HEAD** (`git diff --quiet .gitignore` is clean) — worktrees hold
independent working copies, and `build-scipy`'s `/cases_scipy/` line is
*committed* on that branch, not a dirty edit blocking this one. The line was
staged rather than applied anyway, because `.gitignore` was on the brief's
FROZEN list. Applying it is a safe one-line change whenever you want it.

---

## 2. `contract.py` — the path update this merge owes

`contract.py` holds **three** constants (see its module docstring for why they
are not one):

| Constant | Size | Job at merge |
|---|---|---|
| `NGSPICE_LINEAR_PASSIVE_CONTRACT` | 10,178 | **moves to `substrates.py`** — the runtime/registry artifact (peer: `CAVITY_2D_CONTRACT`, 8,622). No consumer until routable. |
| `NGSPICE_LINEAR_PASSIVE_SUBSTRATE_TEXT` | 700 | **moves to `substrates.py`** — the battery's `substrate_text` (peers: FEA 303, code 607). |
| `NGSPICE_LINEAR_PASSIVE_ENVELOPE` | 2,290 | **moves to `substrates.py`** — the battery's `envelope_text` (peers: FEA 1,451, code 1,547). |

**The one-line change.** The case generator imports them by path through a single
named constant at the top of the file:

```python
# onboarding/ngspice_linear_passive/generate_calibration_cases.py
CONTRACT_IMPORT = Path(__file__).resolve().parent / "contract.py"
```

At merge that block becomes:

```python
from substrates import (
    NGSPICE_LINEAR_PASSIVE_ENVELOPE as ENVELOPE_TEXT,
    NGSPICE_LINEAR_PASSIVE_SUBSTRATE_TEXT as SUBSTRATE_TEXT,
)
```

**Then re-run the generator and commit the result.** The constants' bytes do not
change, so the JSON should not either —
`tests/test_calibration_cases_ngspice.py::
test_committed_json_is_byte_identical_to_a_fresh_generation` is the check that
this went right. If that test fails after the path swap, the text drifted in the
move; fix the text, never the JSON.

**Also update these path references** (they name the staging path):

- `docs/envelope_card_ngspice_linear_passive.md` §1 (Contract text row) and §6
- `docs/ngspice_calibration_cases_v1.md` (source-of-truth pointer)
- `tests/test_calibration_cases_ngspice.py` `GEN_PATH` — only if the generator
  itself moves; leaving the generator under `onboarding/` is fine and keeps the
  slate's provenance next to its evidence.

**Do not** move `SUBSTRATE_TEXT` and `CONTRACT` into one constant on the way
past. They are two artifacts with two readers, ruled 2026-07-16 — the summary is
a hand-held abstract of the contract with **no mechanical link**, deliberately,
so that an unrelated contract edit cannot silently reshape a battery already in
flight. The binding is a review obligation, stated in `contract.py`'s docstring:
any edit to CONTRACT sections 1–3 re-reads SUBSTRATE_TEXT in the same change.

---

## 3. Tests to extend in the merge commit

Adding the registry row and the `_CASE_FILES` entry widens loops that
enumerate known substrates. All three are deliberate coverage, not breakage:

| Test | What happens | Fix |
|---|---|---|
| `test_substrate_registry.py::test_all_four_substrates_enrolled` | **FAILS** — asserts an exact 4-id list | add `"ngspice_linear_passive"` in enrollment order; rename (it is five now) |
| `test_contract_registry.py::test_never_falls_back_to_cavity_for_a_contractless_substrate` | **PASSES and gets stronger** — derives `contractless` automatically, so ngspice joins it for free and proves `contract_for` raises | nothing, *provided* no `_CONTRACTS` entry was added |
| `test_calibration_battery.py::TestCaseFileIntegrity` (`for sid in (FEA, CODE)`) | passes but **does not see** the new slate | add ngspice to the tuple; then fold in / delete the duplicated coverage in `test_calibration_cases_ngspice.py` |

`test_calibration_cases_ngspice.py` currently runs the RULE-1 leak check and the
answer-key blocklist-drift derivation against this slate directly, precisely
because the battery's own loops cannot reach it yet. After the merge that
duplication should collapse into the battery's tests.

---

## 4. State of play

- **Slate:** 15 cases (10 gate + 5 wrapper), owner-ruled 2026-07-16, W01
  dot-line amendment owner-ruled the same day. **Unexecuted** — an owner-OK'd
  run slot is pending. Zero model calls have ever been spent on it.
- **Card:** `docs/envelope_card_ngspice_linear_passive.md`, `unsigned`,
  provenance `drafted-by-agent`, owner provisional signature requested,
  external reviewer dispatch pending. Human-facing only (R-20.5-1) — no code
  reads it, no model sees it.
- **Wrapper:** `tools/run_ngspice.py`, one additive change this session (the
  per-run `corner_3db` fstart-bias note). sha `53bf1d09…` → `e79afa62…`.
- **Open watches** live in card §8 — K coupling, `+` continuations, a future
  device-model card (N5), and the marker-scan layer's absence from the battery
  track.
