# The architecture, explained

**Written 2026-07-28.** This is the *explanation* — read it start to finish and
you should be able to reason about the whole system and see where to change it.
For the reference tables (every knob, every constant, every defect with a
`file:line`) see `docs/system_map.md`. This document says **why** things are
shaped the way they are, which is what you need to improve them.

---

## 1. There is only one idea

**A free agent, in a loop, with tools.** Everything else is scaffolding around
that primitive.

The system does not have a pipeline. It had one — six stages, gates between them
— and that was purged in July 2026 because a caged agent is *weaker than a plain
chat*, which is the project's cardinal failure. What replaced it is:

- a **director**: a free agent whose tools are "run an experiment", "spawn a
  copy of myself", "call ideation", "stop";
- an **experimenter**: a free agent whose tools are Bash, Read, Write, WebSearch
  and a shelf of scientific instruments;
- a **wall**: deterministic Python, no model, that re-runs any number the
  experimenter wants to keep.

"Manager of managers" is not new machinery. It is the director choosing to spawn
a child director — **recursion of the same primitive**. A three-level research
programme and a one-line arithmetic question run through identical code; the
only difference is how many times the agent chose to recurse.

This matters when you go to improve things: **if a change would make either
agent less capable than a bare Claude chat with tools, it is wrong**, no matter
how much safety or structure it appears to buy. That rule is in `CLAUDE.md` as
the PRIME DIRECTIVE and it is the one thing that overrides everything else.

---

## 2. The four layers

```
    YOU ────────► goal string + ceilings (moves, tokens, substrates)
                          │
    ┌─────────────────────▼──────────────────────────────────────┐
    │  DIRECTOR          decides WHAT to do next                  │
    │  free agent, Opus, in your Python process                   │
    │  one model call per turn → one action                       │
    └─────────────────────┬──────────────────────────────────────┘
                          │  dispatches a move (a subprocess)
    ┌─────────────────────▼──────────────────────────────────────┐
    │  EXPERIMENTER      does the WORK                            │
    │  free agent, Opus, up to 200 turns, full toolset            │
    │  this is 98.7% of everything you spend                      │
    └─────────────────────┬──────────────────────────────────────┘
                          │  proposes numbers it wants to keep
    ┌─────────────────────▼──────────────────────────────────────┐
    │  THE WALL          decides what is TRUE                     │
    │  deterministic Python. no model. ever.                      │
    │  re-runs each claim in a fresh container                    │
    └─────────────────────┬──────────────────────────────────────┘
                          │  verified findings only
    ┌─────────────────────▼──────────────────────────────────────┐
    │  WRITE-UP          paper.md → referee → critic → paper.pdf  │
    │  optional (--paper), and entirely after the fact            │
    └────────────────────────────────────────────────────────────┘
```

Read that as a separation of **authority**, not just of code:

- The director has authority over **what happens next**, and none over truth.
- The experimenter has authority over **how the work is done**, and none over
  truth — it may only *propose*.
- The wall has authority over **truth**, and none over anything else. It cannot
  stop a run, cannot choose work, and has no model in it.

This is the single most important structural idea in the system, and it has a
name in the docs: the **propose/measure boundary**. An agent proposes; a tool
measures; the two are never the same thing. It is what lets you leave the room.

---

## 3. A run, narrated end to end

You type:

```
caffeinate -i venv/bin/python3 -m pi_agent \
  --director free --token-budget 150000000 --max-moves 15 --paper \
  --goal "…"
```

**Setup.** `pi_agent/__main__.py` resolves your ceilings into a `Budget` object
and mints `studies/<timestamp>/`. The study directory is the run's entire
identity — everything else is derived from it.

**The loop begins.** Each turn, in this exact order:

1. **Re-read `arc.jsonl` from disk.** The arc is the list of everything that has
   happened. There is no summarisation layer — the whole file goes into the
   prompt, every turn. Context grows linearly with the study.
2. **Compute tokens spent** by diffing a process-global meter and summing the
   per-move costs recorded in the arc.
3. **Three termination checks**: tokens spent ≥ budget, move pool empty, or
   decision cap hit. Any of them ends the study. These are the only guaranteed
   stops.
4. **One model call** produces one action, as JSON, validated in Python.
5. **Dispatch it.**

**When the action is `run_experiment`** — the interesting case — the director
spends one move and forks a **subprocess**: `supervisor.py`, which builds a
`runs/<study>-m<N>/` directory and calls the free experimenter.

The experimenter gets a briefing that is much richer than your goal: the goal,
up to 12 already-verified findings, the last move's reading, the director's
reasoning for *this* move, its token allowance, and up to 8 re-runnable file
producers from earlier phases. That last one is the **carry bus** — how a
design produced in phase 1 reaches phase 3 without anyone copying bytes around.

Then it works: up to 200 turns of thinking, writing code, running it, reading
results, revising. When it finishes it returns JSON: a summary, a list of
findings, and a `publishable` flag.

**The wall runs.** Every finding the experimenter marked `verified: true` is
treated as a *claim*, not a fact. For each one, deterministic Python re-executes
the artifact the experimenter named — usually a small self-contained Python file
— in a **fresh Docker container with no network**, and compares the number that
comes out. The wall then **overwrites** the experimenter's `verified` flag with
its own verdict. A number that doesn't reproduce becomes an honest caveat.

**The result comes back** as one line appended to `arc.jsonl`, and one record
appended to `memory/journal.jsonl`. The director reads it on its next turn.

**When the director stops**, `report.json` is written. If you passed `--paper`,
*then* the write-up chain runs: a paper writer (which sees only verified
findings, unverified ones separately, and artifact producers — never logs or
narration), a referee, a build critic, and finally deterministic typesetting to
PDF.

---

## 4. How tools actually get called

You asked about this specifically, and it's the least obvious part.

**There is no tool-dispatch layer in this repo.** The system does not implement
tool calling — it delegates to the Claude Agent SDK, which shells out to the
`claude` CLI as a subprocess. The repo's job is only to say *which* tools are
permitted and *what* the agent knows about them.

```
free_experimenter.py
   │ builds a system prompt = base rules
   │                        + the substrate catalogue (what instruments exist)
   │                        + the connector catalogue (MCP servers)
   │                        + the runbook index (operating knowledge)
   ▼
model_call.py  ── the ONE door every model call goes through
   │ picks a capability PROFILE:
   │    SEALED = 0 tools,  1 turn   (for anything that judges a measurement)
   │    FULL   = 10 tools, 200 turns (for anything that does work)
   ▼
claude_agent_sdk.query(...)
   │ allowed_tools = [WebSearch, WebFetch, Read, Glob, Grep,
   │                  Write, Edit, Bash, NotebookEdit, TodoWrite]
   ▼
the `claude` CLI, as a subprocess, cwd = runs/<id>/workspace/
   │
   └─► the agent's actual tool calls happen here
```

**The crucial thing: `Bash` is the universal escape hatch.** The other nine
tools are conveniences. Bash means the agent can run anything on the host —
`python`, `pip`, `docker`, `git`, curl. So the *effective* tool surface is far
wider than the ten names, and that is deliberate. A free agent that cannot run
a command is not free.

**How instruments ("substrates") are reached.** There are ten routable ones —
`python_experiment`, `sympy_symbolic_exact`, `rdkit`, `cobrapy`, `mafft`,
`homology_search`, `ngspice_linear_passive`, `cavity_2d_cfd`,
`calculix_cantilever_fea`, `fenicsx_cantilever_elastic`. They are **not** a
plugin system the agent is routed through. They are plain Python modules in
`tools/`, and the agent calls them *through Bash*:

```python
from tools.run_rdkit import run_rdkit
```

The catalogue in the system prompt tells the agent they exist and what each can
vary and measure. Nothing forces their use. This is the PRIME DIRECTIVE made
concrete: **substrates are tools, not a cage.** An earlier design gated the
agent to registered substrates only; that was purged.

Underneath, a substrate does one of three things:
- **shell into a long-lived Docker container** (`rdkit`, `cobrapy`, `mafft`…)
  via `tools/docker_exec.py`, with a timeout inside the container and a slightly
  longer client-side wait;
- **spawn a fresh ephemeral container** (`python_experiment`) — this is the one
  the wall uses, and its jail is invariant: `--network=none --read-only
  --pids-limit=256 --tmpfs=/tmp:512m`, plus memory and CPU from the profile;
- **call out to the network** (`alphafold_db`, `bio_db_lookup`, MCP connectors).

That last category is worth knowing about, because **the "no network" guarantee
covers the code sandbox, not substrates.** A re-run of a database lookup goes
back over the internet; the code comments are honest that this attests
*provenance*, not correctness.

**MCP connectors** are the newest lane. A connector declared `"_verifiable":
true` in `mcp_servers.json` can back a *kept* number, because `tools/run_mcp_tool.py`
can re-call the same server deterministically with no model in the path. The
purity gate exists because some MCP servers are themselves models — and a model
re-asking a model is not verification.

**Sandbox profiles** let the agent ask for more room: `default` (300s, 4GB,
2 CPU) through `heavy` (1800s, 6GB, 4 CPU), plus domain images
(`atomistic`, `biodesign`, `engineering`). The agent picks; Python validates the
name and clamps the ceilings; the profile travels *on the artifact* so a re-run
uses the same geometry.

---

## 5. How a number becomes trustworthy

This is the part that makes the system more than a chat with a nice loop, so it
is worth being precise.

An agent says "the glide ratio is 12.0". That is a **proposal**. To keep it, the
agent must also hand over an *artifact*: a small, self-contained, deterministic
file that recomputes that number and nothing else. The wall then:

1. resolves the artifact path and **rejects anything outside the run's own
   workspace** (so an agent cannot point at a file it didn't make);
2. re-executes it in a fresh no-network container;
3. compares the result within a tolerance the agent may declare — but the
   declared tolerance **can only loosen, never tighten**, and is clamped at 2%;
4. runs a tripwire that parses the artifact's AST looking for the claimed number
   being *hardcoded* rather than computed;
5. **overwrites** the agent's `verified` flag with its own verdict.

Seven verdicts exist: `reproduced`, `mismatch`, `no_artifact`,
`unrunnable_artifact`, `rerun_failed`, `non_numeric`, `hardcoded_constant`.

There is **no model anywhere in this path** — `verification.py` imports `ast`,
`json`, `math`, `uuid` and `pathlib`, and nothing else. That is checkable and
worth re-checking whenever you touch it.

Three things sit *beside* the wall and are strictly advisory: a **claim review**
(does the code implement the mechanism the label names?), a **referee** (do the
paper's words survive contact with the artifacts?), and a **build critic**
(could a competent person use this tomorrow?). None can change `verified`. The
distinction is deliberate: the wall asks "does this number reproduce", and there
are true failures it structurally cannot see — a perfectly reproducible
computation of the wrong thing. The advisory layers cover that blind spot
without being allowed to gate.

---

## 6. Where intelligence lives, and where mechanism lives

**This is the mental model to keep.** When you want to make the system smarter,
the first question is always: *is this behaviour held by code or by prompt?*

**Mechanism (code — the model cannot violate it):**
the action vocabulary and every field type · budget conservation, so a child's
slice is transferred not copied and the tree total can never exceed the root ·
recursion depth ≤ 5 · three independent termination backstops · the wall and
everything in §5 · the sandbox jail · "no verified findings, no paper" · the
Python-written correction block when a paper over-claims · a handed-off file
must re-derive from its producer before it may cross a phase boundary.

**Intelligence (prompt — a request the model may ignore):**
when to stop · how much verification is enough · whether to decompose · whether
to reach for ideation · "budget is not a target to hit" · "one good check per
claim, then move on" · "say so if you are blocked" · how deep to go.

Two consequences worth internalising:

**First, every quality property of a study is currently a prompt property.** The
code guarantees the run terminates, stays inside its budget tree, and that kept
numbers reproduce. It guarantees *nothing* about whether the work was good. That
is not necessarily wrong — it is the free-agent bet — but it means when output
quality disappoints, the lever is usually the goal or the prompt, not new
machinery.

**Second, a prompt lever loses to a gradient.** The clearest example in this
project's history: the system was scored on verified findings, so it produced
verified findings — including a fraction's numerator and denominator as separate
"findings". Adding prose asking it not to do that helps some; changing what is
*rewarded* helps more. When you are choosing between "add an instruction" and
"change what the code counts as success", prefer the second.

---

## 7. The boundaries, and why each exists

| Boundary | What it stops | Why it is there |
|---|---|---|
| No model in the wall | A model grading its own homework | The whole trust story collapses otherwise |
| Artifact must live in the run's workspace | Pointing at someone else's file | An artifact you didn't make proves nothing |
| Declared tolerance can only loosen, clamped 2% | Widening until anything passes | A tolerance the claimant chooses is not a check |
| Hardcoded-constant tripwire | An "artifact" that just prints the answer | The cheapest way to fake reproduction |
| Sandbox: no network, read-only, capped | Re-runs that phone home or mutate the host | A re-run must be a re-run |
| Budget transfers on spawn, never copies | Infinite recursion eating the budget | The one hard guarantee on a recursive system |
| Nothing below the director ends the arc | A tool failure killing a long study | A recorded failure is data; a crash is lost work |
| Advisory layers cannot set `verified` | Judgement leaking into measurement | Keeps the propose/measure line clean |
| Transcripts are write-only | A stage reading another's reasoning | Fresh contexts must stay fresh |

That last row is a historical invariant from the pipeline era, and it is worth
knowing that **it is not currently enforced for the experimenter** — see the map.

---

## 8. Where you can actually intervene

**Before a run** — this is where most of your leverage is today:
- **The goal string.** Demonstrably the biggest single lever. A goal ending
  "each part must be verified before it is built on" produced a study that was
  90% verification. Say what the deliverable *is*.
- **Ceilings:** `--token-budget` (the real one), `--max-moves` (a structural
  backstop), `--allowed-substrates`.
- **Model tiers:** four of them — `heavy`, `light`, `triage`, `critic` — all
  defaulting to Opus, each overridable by env var. `RESEARCH_MODEL_CRITIC=fable`
  points the build critic at an outside model, which is the intended use.
- **Switches:** `REFEREE=0`, `BUILD_CRITIC=0`, `CLAIM_REVIEW=0`, `BLANK_MEMORY=1`.

**During a run** — almost nothing today, which is why interjection is on the
list. Liveview is strictly read-only (every route is a GET; there is no POST
handler at all), and the director has no file watch, no signal handler, no
control file. **But the director re-reads `arc.jsonl` every single turn** — so
anything appended there appears in the very next decision prompt with no new
plumbing. That is the natural seam, and it needs a typed validated channel
rather than raw arc writes.

**After** — `--resume-study <id>` rebuilds from disk and continues, so "kill,
edit state, relaunch" already works as a coarse form of intervention.

**In the code** — the highest-value places to make it smarter, in order:
1. **Change what counts as success**, not what the prompt asks for. Success is
   currently `publishable`, which means "at least one claim reproduced".
2. **Give the director something to reason with.** It sees moves and tokens; it
   never sees dollars, never sees its own decision cap, and never sees how many
   turns it has left.
3. **Make the soft levers hard where it matters.** `stop` is accepted
   unconditionally — every rule about *when* to stop is prose with nothing
   behind it.
4. **Close the evidence gap.** 98.7% of spend leaves no per-turn record, so
   there is no way to see what the experimenter actually did with its 200 turns.

---

## 9. What is built but does not run

Worth knowing before you spend effort improving something production never calls:

- ~~The ideation apparatus~~ — **CORRECTED 2026-07-28.** It is NOT dead. It has
  run three times (twice successfully, once crashing on a bug since fixed), and
  in both successful cases the director reached for it because the goal made the
  ideas themselves the deliverable. It correctly stays unused on well-specified
  engineering goals.
- **Cross-study memory.** `learned_summary` — the kind ideation reads — has had
  no writer since the July purge; its last entry is 2026-07-20. `write_memory`
  writes a different kind that only `read_memory` reads. So a lesson reaches a
  future study only if that study's director volunteers to look.
- **The enum director** (`pi_agent/loop.py`, `decider.py`) — still the CLI
  default, though every recent study runs `--director free`.
- **`campaign`** — the director's prompt advertises it; the flag reaches a
  module the free path never calls, so a campaign move silently runs as a
  single.

---

## 10. If you remember five things

1. **One primitive:** a free agent in a loop with tools. Recursion is the agent
   choosing to spawn itself. Nothing is mandatory except the measurement
   boundary.
2. **Authority is split three ways:** the director decides what, the
   experimenter decides how, the wall decides what is true — and the wall has no
   model in it.
3. **Tools aren't dispatched by this repo.** The SDK and the `claude` CLI do
   that. Bash is the escape hatch that makes the agent genuinely free;
   substrates are ordinary Python modules it may choose to import.
4. **Code guarantees safety and termination; prompts carry all the quality.**
   Know which one you're touching before you touch it.
5. **98.7% of the money is inside one agentic call**, and that call currently
   leaves no per-turn record. Both facts should shape where you look next.
