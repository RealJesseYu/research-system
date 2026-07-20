# Session report — 2026-07-20

The day began with a paper that reported its own configuration error and ended
with a system whose agents can act. Sixteen commits, 43 files, ~5,700 lines.
This is the account, including what was got wrong along the way.

---

## 1. The presenting problem

Run `20260720T080610Z` completed all six stages with zero crashes and wrote a
lint-clean paper containing no data. Three cobrapy mini-runs were rejected
before the solver started:

    input rejected: missing required field(s): model

The owner's reading was that the system was fundamentally bad. The diagnosis
was narrower and more embarrassing.

## 2. What was actually wrong

Four independent defects, none of them a reasoning failure.

**No carriage for categorical inputs.** `validate_spec` rejects non-numeric
parameters by design, so stage 2 put `model: "iJO1366"` in `spec.regime` — the
only place left — and nothing carried it to the wrapper. Fixed in `ba7c16d`
(pre-existing, landed 16 minutes after the failing run finished).

**A closed set the caller could not see.** The cobrapy contract said "one of the
baked allowlist models" and never named them. The strings `e_coli_core` and
`iML1515` appear nowhere in what stage 2 received — verified against the
transcript. It inferred "a genome-scale E. coli model" and answered `iJO1366`,
which is exactly that and one of the most-cited such models in the literature.
A correct inference from information that had been withheld. Fixed in the same
commit by publishing closed sets into the capability table.

**No loop-back for executional failure.** The existing retry fires on
`is_total_defer`: zero executed runs AND a defer verdict. This run had
`verdict=trust` and `status=executed` with three runs in the list. It looked
successful to every check the relay had. The system owned loop-backs for the
thought layer's scientific judgments and nothing at all for "the experiment
measured nothing."

**A reference pipeline broken at both ends.** The paper cited a CMS/LHCb dimuon
decay, ATLAS detector performance, and an IceCube/LIGO neutrino search — in a
paper about E. coli metabolism.

## 3. What changed

### Barren-run gate (`d70779b`)

`is_barren` catches a run that finished stage 4 having produced zero usable
measurements. Such a run never reaches stage 5 or 6; it loops back to stage 2
carrying the wrapper's **verbatim** rejection strings, so the redesign is a
diagnosis rather than a re-roll. Default on in both modes, bounded at 2 on its
own counter.

Deliberately NOT barren: a partially empty run. If one run returned a value
there is data, and an absent value elsewhere may be the finding itself — a
cobrapy infeasibility onset is a result.

### Desk-rejection screen (`01b82a9`)

One Opus call standing where a journal editor stands: not peer review, just
"send this out or return it." Rejects for conclusions without data, unsupported
numbers, unrelated or uncited references, unreproducible method, internal
contradiction. Explicitly does not judge novelty — a correct, dull, honestly
reported negative result must pass.

Screened against the failing paper: rejected it, `remedy=redesign`, naming the
absent data, the unsupported resolution claim, and all three physics references.

### Reference pipeline (`01b82a9`)

arXiv's `all:` field ORs unquoted terms, so a full-sentence hypothesis scored
enormous heavily-indexed collaboration papers above anything on the subject —
a known issue since Step 17 chunk 3 that nothing downstream rechecked.
`build_arxiv_query` ANDs the salient terms, measured live: 8 terms returns
nothing, 5 returns *"Statistical mechanics for metabolic networks during
steady-state growth"*, 4 drifts to solar maxima. Opens at 6, relaxes only when
a rung returns nothing.

Separately, the References prompt said to list every reference *provided*
rather than every reference *used*. `prune_uncited_references` deletes uncited
entries at write time — in code, because an unrelated citation is a desk
rejection on its own.

### Model pins (`d70779b`)

All stage pins moved to `claude-opus-4-8` on owner instruction. Recorded
honestly at the time: this would not have saved the motivating run, since
stage 4 makes no model calls and stage 2's inference was sound.

### Campaign budget (`3584450`)

`MAX_CAMPAIGN_ITERS` 4 → 100, `CAMPAIGN_MAX_ITERS` overrides, 0 = unbounded
(a large int, never `float("inf")`, since the budget reaches the planner and
the logs). High-but-finite because an unterminating campaign never reaches
stage 6 and so produces no paper at all.

### The autonomy inversion (`aa42ae4`)

The day's largest change, and the one the owner had been asking for since the
first message.

Every stage was a Claude Code agent with `allowed_tools=[]` and `max_turns=1`.
One blind shot, no lookups, no reacting to a result. That is what the
architecture's invariants require — deterministic supervisor, typed batons,
tool output summarized at the wrapper — but it was applied to **every** stage
when it was only ever needed on the path that produces measurements.

`model_call.py` now takes a capability profile. `FULL` is a Claude Code agent
undiminished: browser, shell, files, 200 turns. Wired into all 22 ideation,
reflection, evolution, ranking and design call sites.

`SEALED` survives for stages that **judge a measurement**, enforced by a
stage→profile table rather than convention. The reason is calibration: the
`CALIBRATING → MATURE` pipeline rests on batteries measuring verdict
distributions on byte-identical inputs. A judge whose input includes the live
web cannot be calibrated, and four substrates hold `MATURE` on that basis.

`capability_guard.py` denies, in code: reading other stages' transcripts (the
cross-context covert channel), reading calibration answer keys, mutating
`memory/` or `runs/`, reading credentials. Denials are logged and non-fatal.

### Verification (`c810087`)

The half that justifies the other half. The old design bought trust with
**permission**; this buys it with **re-execution**. No number becomes a claim
until a deterministic pass regenerates it from a recorded artifact.

The emitter is the dispatch boundary itself, so what is recorded and what ran
are the same object. Artifacts live in their own file rather than in
`results.json`, whose cavity byte-identity is pinned. The reproduced value is
read through the substrate's **own** run-entry constructor — a simpler reader
would be a second opinion about what the instrument said. The supervisor gate
fails closed.

Proven: cobrapy `0.8769972144269406` and rdkit `46.069` reproduced exactly, a
fabricated `99.9` caught, a bare number refused.

### The experimenting agent (`023a301`, `d9b8830`, `af90a78`)

Stage 4 was never the execution step — it is one measurement. Experimentation
is the loop around it. `bench_agent` registers beside the deterministic
planners; the socket widened by **signature introspection** rather than arity,
because widening the call would have made every three-argument fake raise
`TypeError` instead of asserting, silently vacating a family of contract tests.

The campaign loop, `run_one_point`, `compare_prediction`, `CampaignDegraded`
and all 51 existing tests survive unmodified. Only the fixed-spec assumption
died.

Acceptance case: handed the failing spec, the agent reads that `iJO1366` is not
a baked allowlist model, repairs it, and point 2 returns a real growth rate —
inside stage 4, one history note, no relay loop-back.

### Zero-run status (`001bac7`)

The bench agent concluding "this instrument cannot test this hypothesis" on
iteration 1 — which the design explicitly asks it to say — was recorded as a
corrupted baton, because the locked schema requires an `executed` result to
carry at least one run entry. Now reports `halted_synthesis` with a reason.

## 4. Found, not fixed

- **Cost accounting is blind.** `cost_meter.record_call` fires once per agentic
  loop regardless of turn count. A 200-turn call and a 1-turn call both count
  as one "call". No turn or token cap exists anywhere, and every pin is Opus.
- `retrieval/web_search.py` keeps its own tool list, unfolded.
- `tools/meta_induce.py` bypasses the model door entirely — no transcript, no
  action trail.
- Calibration `--repeats` would conflate model entropy with live web state if
  a judge were ever unsealed.
- The transcript write-only invariant is enforced by the guard now, but nothing
  tests that no code path reads one back.

## 5. Mistakes made in this session

Recorded because the pattern matters more than the individual errors.

1. **Assert-without-looking, three times.** "There is no experimentation step" —
   Step 29 existed. "There is no code-execution substrate" — `tools/run_code.py`
   existed since Step 28.5, registered, `routable=False`, "owner decision
   pending". "The campaign loop isn't built" — built, and switched off by an
   unset flag. Each cost the owner real distress.
2. **Built an unrequested substrate.** `run_python_experiment.py`, duplicating
   more rigorous existing work.
3. **Overcorrected into a smaller cage.** A tiered `DISCOVERY`/`BUILDER` split
   that the owner correctly identified as supervision rather than autonomy.
4. **A quality gate that failed open.** The desk screen's first version returned
   "pass" when the reviewer's reply failed schema — passing the paper it had
   correctly rejected.
5. **A guard that only matched absolute paths**, allowing
   `Write("memory/journal.jsonl")`.
6. **A regex edit landing in the wrong function call.**

## 6. State at close

- Suite: 1589 tests, 1 failure (`test_report_path.MemoryPin`, pre-existing
  journal-md5 drift, unrelated).
- FAST gate green.
- Verification live at `supervisor.py:1704`, fails closed.
- `bench_agent` reachable via `CAMPAIGN_STRATEGY`.
- Cavity byte-identity holds; no calibration invalidated.

**Never witnessed in a complete supervised run:** the campaign loop, the bench
agent under real conditions, tooled stages 1–2, the barren gate, the desk
screen, verification against real claims. `runs/` contains no completed run
from after 09:56 today.
