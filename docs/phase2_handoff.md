# Phase 2 hand-off — the live composing experimenter agent

Written 2026-07-21 (session continuation). Phase 1 and the Phase-2 *deterministic
controller* are built, tested, and committed. What remains is the **live agent**
that authors composition recipes — the one brick that needs a real Terminal
outing to validate, so it was deliberately not shipped blind.

## What is already done (committed on `iterate-experiment-loop`)

- **Phase 1** (`2b8fbb8`) — `docs/memo_phase1_composition.md` (R-COMP-1..6);
  `stages/verification.py` gained `kind:"composition"`; `run_composition(recipe)`;
  the hardcoded-combine tripwire. Proven on real `rdkit`×`cobrapy`
  (`tests/test_composition.py`, 11 tests).
- **Phase 2 controller** (`964b094`) — `stages/experiment_investigation.py`:
  `run_investigation(strategy, *, max_iters, rel_tol, run_id)`. A strategy
  proposes a probe (a composition recipe), the controller runs and independently
  verifies it, verified results feed the next decision. Proposes-not-measures
  boundary holds; small-before-big is a strategy decision reading a verified
  result; an un-reproducible probe sinks `publishable`. Proven with a scripted
  strategy (`tests/test_experiment_investigation.py`, 6 tests).

## The remaining brick: `tools/compose_agent.py`

A `FULL`-capability strategy — the exact shape of `tools/bench_agent.py`, which is
the template — that authors the next composition recipe instead of numeric points.

**Signature:** `propose_composition_probe(state, context=None) -> action`, where
`state` is what `run_investigation` passes (`measurements`, `budget_remaining`,
`iteration`) and `action` is what `_validate_action` accepts:

```
{"reasoning": "...", "recipe": <composition artifact> | null,
 "predicted_value": <number|null>, "stop": <bool>, "stop_reason": "..."}
```

**The recipe schema the agent must emit** (validated in-loop by
`verification._validate_recipe`, so a malformed one is re-asked, not accepted):

```json
{"kind": "composition",
 "steps": [
   {"step_id": "<unique>", "kind": "substrate", "substrate_id": "<routable id>",
    "call_style": "typed_dict", "typed_input": {<wrapper fields incl. quantity>},
    "quantity": "<metric>", "qoi_request": {"quantity": "<metric>"}},
   {"step_id": "<unique>", "kind": "code", "code": "metrics['x']=...", "quantity": "x"}
 ],
 "combine": {"kind": "code",
   "code": "metrics['out'] = inputs['<step_id>'] / inputs['<step_id>']",
   "quantity": "out", "inputs": ["<step_id>", ...]}}
```

**Wiring that is already true, so you do NOT need to touch it:**
- **No `capability_guard` edit.** `assert_profile_allowed` denies only the
  `SEALED_ONLY_STAGES` prefixes (`stage3/4/5/6`, `fidelity_case`, `calibration`).
  Name the stage `experiment_compose_agent` (non-sealed, like
  `experiment_bench_agent`) and it may hold tools.
- **Capability profile.** Reuse `bench_agent.BENCH` (FULL tools, tighter turn
  cap) or make a sibling; do not mutate `FULL`.
- **Toolbox for the prompt.** `substrate_registry.routable_contracts_block()`
  gives every routable substrate's contract verbatim; the code sandbox is the
  `code` step. The mature ones are `rdkit`, `cobrapy`, `mafft`, `homology_search`,
  plus `python_experiment`.
- **The boundary.** Same as bench_agent: the agent never states a measured value;
  `predicted_value` is compared, not recorded. `run_investigation` already
  enforces this — the recorded number comes from `run_composition`.
- **Never-raise.** A tooled call gets no transport retry; catch and return a
  `stop` action (bench_agent's pattern), never fall back to a blind probe.

**Prove it offline** with a faked judgment (patch the transport seam, like
`test_verification_wiring`/the bench tests), then the FIRST LIVE OUTING from a
plain Terminal under `caffeinate` — never a builder-session background task:

```
caffeinate -i env BENCH_AGENT_MAX_TURNS=40 \
  venv/bin/python3 -c "from tools.compose_agent import propose_composition_probe; \
     from stages.experiment_investigation import run_investigation; \
     print(run_investigation(propose_composition_probe, max_iters=3))"
```

Small on purpose. The prompt WILL need iteration against real outings to reliably
emit a valid recipe — that is why it was not shipped blind. Expect the re-ask
validator to fire early and often; read the `RE-ASK` lines.

## Carried forward (unchanged from `docs/next_session_debrief.md`)

- Wiring the investigation into the real pipeline / PI action space is a later
  brick (it runs standalone today).
- File-artifact hand-off between substrates stays deferred (R-COMP-6).
