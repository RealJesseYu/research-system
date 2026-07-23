# Defects surfaced by the 2026-07-22 live director run

Root-caused during the second director run (read-only; fixes NOT yet applied).
The evidence-read-back gap from the same run is already fixed (`efea7ef`).

## Defect A — a single SDK glitch kills a whole investigation
**Symptom:** move m3 stopped after ONE probe with
`"compose agent unavailable: Exception: Claude Code returned an error result: success"`.

**Root cause:** `tools/compose_agent.py:311` — the compose-agent call
(`call_stage_model(..., capabilities=BENCH)`, a tooled Claude Code SDK call) has
**no transport retry** (the comment says so outright: "a tooled call gets no
transport retry"). So one transient SDK/transport glitch on a probe-proposal call
returns `{"stop": True, stop_reason: "compose agent unavailable: ..."}` and the
experimenter loop ends the investigation immediately. Regular stage calls got a
transport retry in Step 16; the tooled compose call never did, and it is exactly
the call most exposed to SDK streaming/transport flakiness (cf. the memory note
on prior "SDK streaming/transport unblock" fixes).

**Fix design:** give the compose-agent call a **bounded transport retry** (2–3
attempts, same input) on transport-class exceptions — mirroring `model_call.py`'s
Step-16 retry — so a transient glitch retries instead of aborting the arc.
Validation failures already go through the `extra_validator` re-ask loop and are
unaffected; this retry is only for the whole-call transport exception. Only after
the retries are exhausted does the investigation stop with the honest reason.

## Defect B — a truncated run still self-labels "publishable"
**Symptom:** m3 was cut short by Defect A after one cheap wiring probe, yet the
run reported `publishable=True` (and the director, once it can read results, would
see a "publishable" move that never did the intended analysis).

**Root cause:** publishability is "something ran AND everything that ran
reproduced" — it does not distinguish a **judged stop** (the strategy chose to
stop because the question was answered) from an **error/truncation stop** (compose
agent unavailable, or the iteration budget hit mid-investigation). A run
truncated by an error can still be all-reproduced-so-far and thus "publishable."
Related to the earlier note: publishability should key off the probes the *final
claim* rests on and whether the investigation *completed its intent*, not
any-probe-reproduced.

**Fix design:** carry the stop *kind* out of the experimenter loop (judged vs
error/truncated). A run whose investigation was truncated by a compose-agent
error (or otherwise did not reach a judged stop) is **not publishable** — surface
it as `incomplete` rather than `publishable`, even if its probes reproduced. The
verified numbers are still recorded and re-runnable; the run is just not claimed
as a standing result. This keeps the honest-floor discipline (never over-claim).

## Sequencing
Both are experimenter-loop / compose-agent hardening, independent of ④.3. Apply
after the current director run finishes (tree is frozen during it). Defect A is
the higher priority (it aborts real arcs); Defect B makes the label honest when
truncation still happens. Neither touches the wall, the locked schema, cavity, or
the approximate path.
