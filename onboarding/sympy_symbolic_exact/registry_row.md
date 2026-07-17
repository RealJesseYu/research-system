# STAGED — registry row for `sympy_symbolic_exact`

> **STAGED, NOT MERGED.** The maturity registry (`tools/substrate_registry.py`)
> is **FROZEN for this wave**. The Wave Guide merges serially. Nothing below has
> been applied to any file.
>
> **Enrolling this substrate as `calibrating` / unroutable does NOT authorize the
> pipeline to route to it** — that is a separate owner ruling, exactly as the
> registry's own module docstring says for FEA and code.

---

## 1. The row — append to `_REGISTRY` in `tools/substrate_registry.py`

Enrollment order is preserved by `all_substrates()`, so this appends **after**
`code_sklearn_eval` and **before** `web_search` (which sits in its own
retrieval-provisional class outside the routable ladder).

```python
    SubstrateRecord(
        substrate_id="sympy_symbolic_exact",
        wrapper="tools/run_scipy.py",
        card_path="docs/envelope_card_sympy_symbolic_exact.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes=(
            "sci-Python Regime A (exact symbolic CAS); card provisionally "
            "signed (owner, 2026-07-16), S1-S6 + S2a/S4a/S4b all RULED (owner, "
            "2026-07-16); battery pending owner OK. Regime B "
            "(scipy_numeric_quad) is QUEUED and has no row."
        ),
    ),
```

| Field | Value | Why |
|---|---|---|
| `substrate_id` | `sympy_symbolic_exact` | The **(substrate, regime)** pair is the card unit, and sci-Python is two regimes — so the id names the **regime**, not the image. `scipy-img` would be the wrong id: Regime B will ship its own row from the same image. |
| `wrapper` | `tools/run_scipy.py` | — |
| `card_path` | `docs/envelope_card_sympy_symbolic_exact.md` | Regime A only. **Provenance state `provisionally-signed`** (owner, 2026-07-16); S1–S6 + S2a/S4a/S4b **RULED** — the card and `onboarding/sympy_symbolic_exact/contract.py` are the sources, not this row. |
| `maturity` | `CALIBRATING` | **Everything enters at `calibrating` = unroutable.** Promotion is a separate owner ruling. |
| `routable` | `False` | Ditto. Keeps `sole_routable_id()` returning exactly `cavity_2d_cfd` — see §3. |
| `cost_tier` | `low` | **Measured**, not guessed: 0.617–1.403 s/job across 8 live jobs this session (n=8), container-startup-dominated. Same tier as FEA/code, both `low`. See `router_entry.md`. |

## 2. `_CONTRACTS` — deliberately NOT added

`contract_for()` **must keep raising `LookupError`** for this substrate. Its
absence from `_CONTRACTS` is the fail-loud escape the R-S3-1 Part-A tests prove:
an unroutable, uncalibrated substrate has **no routing contract**, and the gate
must never fall back to cavity for it. Wiring a contract here is a **separate
future ruling**, exactly as the registry docstring already records for FEA and
code.

## 3. Invariant check — `sole_routable_id()` stays unambiguous

`sole_routable_id()` **raises** unless the routable set is exactly one. This row
is `routable=False`, so the routable set stays `('cavity_2d_cfd',)` and the
function keeps working. **A future promotion of this row to `routable=True`
without building Step-35 task typing would make that function raise** — which is
the intended seam, naming the missing work rather than silently picking a
substrate.

## 4. ⚠ THE UNBUILT SEAM — the calibration battery cannot load this slate

**This is the one thing that blocks the battery run, and it was out of scope.**

`harness/calibration_battery.py` resolves a substrate through **two hardcoded
module-level structures**, neither registry-driven:

```python
_CASE_FILES = {
    "calculix_cantilever_fea": "calibration_cases_fea.json",
    "code_sklearn_eval": "calibration_cases_code.json",
}
```
and `_wrapper_validator(substrate_id)`, an `if/elif` over the same two ids that
ends in `raise KeyError(f"no wrapper validator wired for substrate ...")`.
`main()` further pins `--substrate` to `choices=sorted(_CASE_FILES)`, so
`--substrate sympy_symbolic_exact` is rejected **at argument parsing**, before
any code runs.

`harness/calibration_battery.py` is **outside this session's scope**, so the
registration below is **staged, not applied**:

```python
# in _CASE_FILES:
    "sympy_symbolic_exact": "calibration_cases_sympy_symbolic_exact.json",

# in _wrapper_validator():
    if substrate_id == "sympy_symbolic_exact":
        from tools.run_scipy import ScipyInputError, validate_input

        return validate_input, ScipyInputError
```

**Verified this session** (so the merge is a two-hunk edit, not a discovery):

- The generated JSON satisfies `load_cases`' checks exactly — `substrate_id`
  matches, every gate case has a non-empty `acceptable_labels`, and every label
  is in `VALID_LABELS = ('trust', 'refine', 'defer')`. Replicated and **passed**.
- `run_gate_case`'s **RULE-1 answer-key tripwire passes on all 10 gate cases**:
  no answer-key key name (`expected_class`, `acceptable_labels`, `note`,
  `right_instrument`) appears in the serialized `stage_input`.
- `validate_input` raises `ScipyInputError`, matching the
  `(callable, exception_class)` shape `_wrapper_validator` returns and
  `run_wrapper_case` catches.

### 4.1 A THIRD hunk the merger must not miss — the drift test WILL fail

`tests/test_calibration_battery.py::test_answer_key_blocklist_covers_every_hidden_gate_field`
derives, per gate case, *(all keys) − `_MODEL_VISIBLE_GATE_FIELDS`* and asserts
the remainder is covered by `_ANSWER_KEY_KEYS`. **Measured this session against
the real module constants:**

```
_MODEL_VISIBLE_GATE_FIELDS = ('id', 'experiment')
_ANSWER_KEY_KEYS           = ('expected_class', 'acceptable_labels', 'note', 'right_instrument')
this slate's gate-case keys = [acceptable_labels, expected_class, experiment, id,
                               label_provenance, note, right_instrument]
=> uncovered: {'label_provenance'}   <-- WOULD FAIL
```

**Timing, precisely (I checked rather than assumed):** the test loops
`for sid in (FEA, CODE)` — a **hardcoded tuple**. So it does **NOT** cover this
slate today and will **pass unchanged** after the two `_CASE_FILES` /
`_wrapper_validator` hunks above. But the moment the merger adds
`sympy_symbolic_exact` to that tuple — which coverage plainly demands, or the new
slate sits outside the guard that exists precisely to stop blocklists drifting
out of coverage — **it fails on `label_provenance`.**

`label_provenance` is required by the build prompt (every case marked
`drafted-by-agent`) and is **not** model-visible: `run_gate_case` builds
`stage_input` from `id`/`experiment` alone, so it cannot leak. The failure would
be the guard **working as designed**, not a bug. The merger rules on which fix:
add it to `_ANSWER_KEY_KEYS` (simplest — it is non-model-visible metadata, and
the blocklist is the complement set), add it to `_MODEL_VISIBLE_GATE_FIELDS`
(**wrong** — it is not sent to the model), or lift it out of the per-case dicts
to the file header (it is already at the file's top level too). **This session
did not choose** — `harness/` test files and the battery were both out of scope.
