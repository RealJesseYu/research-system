# STAGED — schema fragment for `sympy_symbolic_exact`

> **STAGED, NOT MERGED.** `schemas.py` is **FROZEN** (baton schemas are locked —
> Step 15; changes require a recorded ruling, same discipline as frozen prompts).
> Nothing below has been applied. The Wave Guide merges serially.

---

## 1. The honest answer first: **no `schemas.py` change is needed today**

The enforced baton boundary is **post-gate-1**, and this substrate is
**UNREGISTERED and UNROUTABLE**: nothing in `stages/`, the supervisor,
`substrates.py`, or any schema imports `tools/run_scipy.py`. No baton carries a
Regime-A payload, because no stage can reach the substrate. **A schema change now
would be schema for a path that does not exist** — precisely the "expand only on
evidence" line.

This fragment therefore records **what the shape WOULD be** when registration is
ruled, so the eventual ruling starts from a written proposal rather than an
improvisation. It is a proposal, not a pending edit.

## 2. The typed job spec (already enforced — in code, not in a schema)

**Anything we can't afford broken goes in code, never a prompt** — and, here, not
in a schema either. The spec is enforced **today** by
`tools/run_scipy.validate_input`, field-by-field, with **named** rejections,
against the allowlists in `onboarding/sympy_symbolic_exact/contract.py` (the one
runtime source of truth). Reproduced here for the reader; **the module is
authoritative**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `operation` | str | ✔ | must be in `contract.OPERATIONS` (S1) |
| `expression` | str | ✔ | goes through the layer-1 AST allowlist |
| `symbols` | list[str] | ✔ | **every free name in `expression` must appear here** (the typo trap, §4D) |
| `assumptions` | dict[str, list[str]] | optional | values from `contract.ALLOWED_ASSUMPTIONS`; **changes the mathematical meaning** (S5) |
| `var` | str | per-op | must be a declared symbol |
| `lower`, `upper`, `point` | str \| number | per-op | **expressions** — allowlist-checked like `expression` |
| `order` | int ≥ 1 | per-op | |
| `func` | str | `dsolve` | the ODE function name; a legal bare name inside `expression` |
| `ics` | dict[str, number] | `dsolve`, optional | **keys are expressions** (`"y(0)"`) and are allowlist-checked |

Unknown fields are rejected **by name**. The exact legal set is derived per
operation from `contract.OP_FIELDS`, so the vocabulary cannot drift from the
contract.

## 3. The wrapper return — the shape a future baton would carry

```
{"valid": bool,
 "state": "solved_verified" | "unevaluated" | "error",
 "result": str | None,          # non-null ONLY in solved_verified
 "residual": float | None,
 "crosscheck": {...} | None,    # definite integrals only; DIAGNOSTIC, never a result
 "reason": str | None,          # named; non-null ONLY in error
 "diagnostics": str,            # <= 800 chars, never raw container output
 "runtime_s": float}
```

## 4. ⚠ The one thing a future schema MUST NOT do: collapse the three states

**This is the load-bearing constraint, and it is the whole reason this fragment
exists.** Every other substrate's wrapper is two-valued — `valid` true/false with
a `qoi` or a `None` (`run_cfd`, `run_fea`, `run_code` all share that shape). **A
schema that reflexively mirrors that pattern would destroy this substrate's
central honesty**, because Regime A has a **third** outcome that is neither:

| state | `valid` | `result` | `reason` | meaning |
|---|---|---|---|---|
| `solved_verified` | `true` | the expression | `null` | verified answer |
| **`unevaluated`** | **`true`** | **`null`** | **`null`** | **an HONEST NON-ANSWER** — SymPy correctly declined; the substrate worked |
| `error` | `false` | `null` | named | invalid input / jail kill / `verification_failed` |

`unevaluated` carries `valid=true` **and** `result=null` **and** `reason=null`
simultaneously. A schema requiring "`result` non-null whenever `valid`" — the
obvious mirror of the other three wrappers — would force `x**x` to be reported as
either a fabricated answer or a failure. **Both are lies.** `x**x` genuinely has
no elementary antiderivative; SymPy declining is the instrument being *correct*,
and misfiling that as failure is the system slandering its own instrument (card
§4B, S4).

Any future schema must therefore encode the three states as a **closed
enumeration** with per-state field constraints, **not** a `valid` boolean with an
optional payload.

## 5. Not proposed, and why

- **No `substrates.py` contract constant.** The contract lives at
  `onboarding/sympy_symbolic_exact/contract.py` — **one runtime source of truth**;
  a `substrates.py` copy would be the forbidden third copy.
- **No `_CONTRACTS` entry** in the registry. `contract_for()` must keep raising
  `LookupError` — the fail-loud escape (see `registry_row.md` §2).
- **No Stage-2 spec-schema change.** FROZEN this wave, and nothing routes here.
