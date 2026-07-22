# Phase 4 memo — file-artifact hand-off between tools (R-ART ruling; wakes R-COMP-6)

Deliverable of the collapse roadmap's highest-leverage brick toward the owner's
north star — *complex, multi-part experiments* (a robot's parts, a protein
pipeline) need one tool's **file** output to feed the next, not just a scalar.
Written 2026-07-21 under the same discipline as `docs/memo_phase1_composition.md`
and `docs/memo_phase3_routing.md`: a direction-changing, new-capability decision
is **recorded before code**. Builder ruling, **owner-amendable**. It wakes
**R-COMP-6** (file hand-off was deferred there, "its own ruling, informed by the
[Jul-20] spike's A1/A2/B analysis") and is informed by that spike verbatim.

---

## The question

Composition today combines **scalars** (`R-COMP-3`: "Scalars only … it does not
pass file artifacts between steps"). A real multi-part experiment needs a step to
emit a **file** (an alignment, a mesh, a CAD part, a structure) that a later step
consumes. How does that hand-off work, **with the verifier able to reproduce the
whole chain, no model**?

## What the collapse already changed (checked against the spike, not assumed)

The Jul-20 artifact-channel spike (`spike_artifact_channel/REPORT.txt`) studied
this and named its own **biggest unmeasured risk (§6.1)**:

> "I MEASURED THE CHANNEL, NOT THE CHAIN. There is today no way to express a
> 2-node experiment at all. A spec routes to exactly ONE substrate
> (`select_substrate`), and a handle can NEVER be a declared parameter …
> `validate_spec` rejects it … So stage 2 cannot author a chain and selection
> cannot route one, REGARDLESS of which channel wins."

**That blocker is gone.** It was a property of the *old* stage-2/routing spine.
In the collapsed architecture a **composition recipe** already expresses an
N-step chain **off the baton** (`verification._validate_recipe`; `steps` +
`combine`), authored directly by the experimenter (`tools/compose_agent.py`),
never by `validate_spec`/`select_substrate`. **The expensive half the spike could
not price is already built.** What remains is the *channel* (the half the spike
did measure) plus verification.

**This also re-opens the spike's A1-vs-B recommendation.** The spike recommended
**A1** (a bare `runs/<id>/artifacts/<node>/` path convention) over **B** (a
checkable typed handle `{artifact_id, artifact_type, sha256}`) for ONE reason:
B's handle, added to the **closed-key baton**, "CASCADES TO ALL BOUNDARIES AT
ONCE" (§2, M1) — 5 key tuples, 5 validators, 6 supervisor sites, a quarantined
test file. **In the collapsed architecture the recipe/artifact channel is
OFF-BATON** (like verification's evidence, `R-COMP` "no `schemas.py` change"), so
**B's entire cascade cost vanishes** — a typed handle can live in the recipe
wiring without touching any locked schema. The spike itself flagged (§6.3) that
this trade-off "should be resolved BEFORE the ruling is treated as final." It is
resolved here: the reason to prefer A1 no longer applies, and B's checkability
(the spike caught a tampered artifact by content hash; A1 "cannot detect a
corrupted or stale artifact at all") is now free.

## What the sandbox already allows (checked)

A **code step already writes a durable file today.** The sealed sandbox is
`--network=none --read-only` with a **writable bind for the run dir only**
(`tools/run_python_experiment.py:94-95`, `DOCKER_RUN_FLAGS`): the script writes
`result.json` to a host-bound dir the wrapper reads back after the container
exits. So a code step can emit a file to that dir; the wrapper simply does not
*capture* it yet. A **code→code** file hand-off therefore needs **no mature
wrapper edit** — it avoids the spike's shared-floor cost (§2, M5: "Make some
wrapper EMIT an artifact. Today none does").

---

## Ruling

**R-ART-1 — The chain is solved; only the file channel + verification remain.**
File hand-off is built as an extension of the **composition recipe**, not a
revival of stage-2 chain authoring. A recipe step may declare that it **emits**
a named file artifact, and a later step may **consume** an upstream step's
artifact. The wiring is typed data in the recipe (off-baton), resolved by the
deterministic orchestrator — never by a model in the loop (R-COMP-3 extended
from scalars to files).

**R-ART-2 — Channel: a checkable typed handle in the off-baton recipe, files
under `runs/<id>/artifacts/<step_id>/`.** A produced artifact is recorded as a
handle `{step_id, name, artifact_type, sha256}` inside the recipe's step-flow
(never on the baton, never in a prompt, never the file's bytes). The bytes live
under `runs/<id>/artifacts/<step_id>/<name>` (A1's storage path, reusing the
`runs/<id>/campaign/` precedent at `campaign_controller.py`). This takes B's
checkability (the `sha256` tamper/staleness guard the spike proved) at A1's
storage cost — the collapse having erased B's schema-cascade cost. Rationale
recorded so it is not re-opened: an unvalidatable artifact reference is exactly
the kind of thing this project puts in code, not a convention (the spike's own
"strongest argument against A1").

**R-ART-3 — Data flow is model-free and RE-DERIVED, never replayed.** A consuming
step names an upstream `step_id`'s artifact by handle; the orchestrator resolves
it deterministically — copying the file into the consumer's input dir (host-side,
via the same bind; the sandbox never reaches out, so `--network=none` is
untouched). On **verification**, every step re-runs and every consumed artifact
is re-resolved from the **RE-RUN** upstream step's freshly-emitted file, **never
the recorded one** — so a nondeterministic producer is caught, not masked
(exactly R-COMP-4 for scalars). The recorded `sha256` is tamper-detection for the
original run's evidence; reproduction regenerates the bytes.

**R-ART-4 — Verification grows with the file channel, or it does not ship (the
load-bearing constraint, R-COMP-4 restated for files).** A file-passing
composition whose recipe cannot be re-executed end-to-end with no model — every
file re-derived, the final scalar(s) regenerated within `rel_tol` — is
**unverifiable and therefore un-publishable**. **If a genuine file hand-off
cannot be made reproducible this way, STOP and rethink — do not ship an
un-verifiable composed number.**

**R-ART-5 — First brick, scope discipline (tested-first).** The first proven file
hand-off is the smallest genuine one: **code→code**. One `code` step writes a
file to its run dir (the sandbox's existing writable bind — no wrapper isolation
change beyond capturing/injecting a *named* file host-side); a downstream `code`
step consumes that file; a combine reduces to one final scalar. Proven on one
concrete case with a test that (i) runs it, (ii) re-runs it through the
composition verification path and confirms the final number regenerates within
`1e-6` **with every file re-derived**, and (iii) confirms a **perturbed/absent
artifact is caught** (the `sha256` guard + a fail-loud missing-artifact, mirroring
the spike's M4 `CaseSynthesisError`). No mature-wrapper edit. This proves the
channel + verification mechanism before any substrate learns to emit.

**R-ART-6 — Deferred to later bricks, on evidence, no gold-plating.** Building on
R-ART-5's proven channel: (a) making a mature **substrate** emit a file — a
wrapper edit (e.g. persist `run_mafft`'s alignment, `run_mafft.py:257`), which is
**STOP-and-rule** and breaks the mature bio family's uniform 4-key summary
(spike §6.2), so its own ruling; (b) the per-consumer **resolver** that reduces a
file to a substrate's typed input (spike M5 floor items 2-3, e.g. mafft→homology
FASTA→query); (c) large/binary artifacts, size caps, and retention under the
`runs/` append-only doctrine. None of these block R-ART-5.

---

## What this ruling deliberately does NOT do

- No `schemas.py` change: the artifact channel rides the off-baton recipe, like
  verification's evidence (R-COMP F4) — the very cost that sank spike option B.
- No mature substrate-wrapper edit (deferred, R-ART-6) — the first brick is
  code→code, so the mature bio family's summary shape is untouched.
- No weakening of the sandbox: `--network=none`/`--read-only` stay; files move
  host-side through the existing run-dir bind, by the deterministic orchestrator.
- No model anywhere in the orchestrator or the verifier (verification purity).
- No `git add -A`.

## Acceptance for this memo

The decision is recorded (this file). The first Phase-4 code brick builds against
R-ART-1..5, proven by a test before the next — a genuine code→code file hand-off,
run and independently reproduced end-to-end, on the real sandbox.

---

## Amendment — R-ART-7 (2026-07-21): a mature substrate emits a file (mafft)

Wakes R-ART-6(a). R-ART-5 proved the channel code→code; this lets a **mature
substrate** put a real file into the channel, so a hand-off is genuinely
tool→tool. Grounded in `tools/run_mafft.py`: MAFFT's aligned FASTA is already
**in-hand as captured stdout** (`out`, `run_mafft.py:244/257`), so emitting it is
returning content the wrapper already holds — this sidesteps the spike's on-disk
concerns (§6.2: concurrent writes, retry/stale-artifact) entirely, since nothing
new is read from disk.

**R-ART-7 — mafft emits its alignment, OPT-IN and ADDITIVE.** `run_mafft` accepts
an optional `emit_artifacts` field (a list of filenames). When present on a
successful alignment, the return carries an extra `artifacts: {name: <aligned
FASTA bytes>}`. **Absent (every existing call), the return is the byte-identical
4-key summary** — the mature bio family's uniform shape is preserved for all
current callers; only a composition step that asks for the file sees the extra
key. The QoI, the strict input gate, the trust claim, and the diagnostics are
untouched.

**R-ART-7b — the composition captures a substrate step's emitted file.** A
`substrate` step may now declare `emits`; the orchestrator threads the wrapper's
returned `artifacts` exactly as it does a code step's, and a downstream **code**
step consumes them. Verification re-runs the substrate step and re-derives the
file (MAFFT is deterministic for fixed input, so it reproduces; a
nondeterministic aligner would be caught, not masked — R-ART-4).

**Still deferred (R-ART-6b):** a substrate *consuming* a file needs a per-consumer
**resolver** (reduce the file to the consumer's typed input — e.g. mafft FASTA →
homology query string, whose closed-key gate rejects a raw handle). Substrate→code
is proven here; substrate→substrate waits on that resolver, its own brick.

---

## Amendment — R-ART-8 (2026-07-21): the resolver — a substrate consumes a file

Wakes R-ART-6b. Completes the tool↔tool file story: one substrate's file feeds
another substrate. Grounded in `tools/run_homology_search.py`: its typed input is
a closed-key gate whose `query` is a protein **sequence string**, and it writes
`query.fa` itself (`:254`) — so a raw file handle is rejected (spike M5). The
**resolver** reduces the upstream file to that typed field.

**R-ART-8 — a substrate consume carries a deterministic `resolve` block.** A
`substrate` step may now `consumes` an upstream artifact **with a `resolve`
{into, method}**: the orchestrator reads the upstream file, applies the named
deterministic reducer, and sets `typed_input[into]` before the wrapper call. No
model in the reducer (verification purity); the reducers live in a small
registry, added on evidence. First reducer: `fasta_first_ungapped` (aligned FASTA
→ the first record's ungapped sequence — the natural homology query). A **code**
consume still injects the file as-is and takes no `resolve`; a **substrate**
consume **must** name a known reducer, else the recipe is refused.

**Proven:** mafft aligns → emits FASTA → homology_search consumes it (resolver →
`query`) → e_value, one composed number, independently reproduced (both real
containers re-run, the file re-derived, the number regenerates — R-ART-4). This
is the first genuine two-instrument science chain with no code step between them.

**Still deferred, on evidence:** more reducer methods (other artifact types /
target fields); case-build-style substrate steps in the file channel; and
persisting artifacts to `runs/<id>/artifacts/` with the R-ART-2 sha256 evidence
guard (the in-memory channel is enough for the chain; the on-disk provenance
record is its own brick when a run_id threads through).
