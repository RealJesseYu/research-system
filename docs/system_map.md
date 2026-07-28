# System map — how this actually operates

**Written 2026-07-28** against HEAD `aaa2279`. Purpose: let the owner find
places to make the system smarter without re-reading 38k lines. Every claim has
a `file:line`. Claims marked **VERIFIED** were re-checked by the coordinating
session directly, not taken from a subagent.

Companion docs: `docs/roadmap_status.md` (the checklist),
`docs/findings_2026-07-28.md` (the cost and value evidence).

---

## 1. The shape of it, in one page

```
$ python -m pi_agent --director free --goal "…" --token-budget N [--paper]
│
├─ __main__.py            argv → ceiling → Budget → free_investigate
│
├─ free_director.py       ══ THE LOOP, in-process ═════════════════════
│   every turn:
│     1. re-read arc.jsonl from disk           (no summarisation, ever)
│     2. compute tokens spent
│     3. three termination checks: tokens / moves / decision-cap
│     4. ONE model call → an action            free_decider.py  (Opus, FULL)
│     5. dispatch it
│
│   ├─ run_experiment ──► SUBPROCESS ─────────────────────────────────┐
│   │                                                                 │
│   ├─ call_ideation / validation / data_analysis   IN-PROCESS        │
│   ├─ spawn_sub_investigation → a child director   IN-PROCESS        │
│   ├─ read_memory / write_memory                   free              │
│   └─ stop                                         unconditional     │
│                                                                     │
│                                            supervisor.py ◄──────────┘
│                                              └─ free_experimenter.py
│                                                   ONE Opus call, FULL profile,
│                                                   200 turns, 10 tools + Bash
│                                                   ↓
│                                                 THE WALL  verification.py
│                                                   deterministic, no model,
│                                                   one Docker container per claim
│                                                   ↓ overwrites `verified`
│                                                 runs/<id>/free_investigation.json
│                                                 memory/journal.jsonl (+1 record)
│                                                 studies/<id>/arc.jsonl (+1 line)
│
└─ report.json  ◄── written HERE, before anything below
   └─ --paper: study_paper → referee → build_critic → typeset_paper
      FOUR more Opus agents, 200 turns each, spend NOT in report.json
```

**The one data structure that matters** is an `arc.jsonl` line. Everything the
director ever knows is a list of these:

```
seq · at · move_type · run_id · succeeded · outcome · publishable
results[{label, value, verified}] · cost{calls, tokens} · reusable_artifacts[]
tool_output{…} · finding  (= the director's own reasoning for that move)
```

**Two hard architectural facts:**
- **The arc is never summarised.** `free_director.py:646` re-reads the whole
  file each turn and the entire thing goes into the prompt. There is no
  compaction layer. Context grows linearly with the study.
- **Nothing below the director can end a run.** `_survive`
  (`free_director.py:315-348`) catches every exception beneath it and turns it
  into an arc row.

---

## 2. Where the money goes

| Layer | Model calls | Counted in `report.json`? |
|---|---|---|
| Director decisions | 1 per turn (Opus, FULL, 200 turns) | yes — `process_spend` |
| **Experiment moves** | **1 per move, and this is 98.7% of spend** | yes — `runs_spend` |
| In-process capabilities (ideation etc.) | 1+ each, uncapped | yes, but folded into `process_spend` |
| Child directors (spawn) | recursive | only in the child's own report |
| The wall | **zero** — Docker only | n/a (no tokens) |
| claim_review | 1 sealed call | no — after the run |
| **paper + referee + 2× build_critic** | **4 FULL 200-turn Opus agents** | **NO — after `report.json`** |

**~$1 per million reported tokens** at the observed cache ratio. A study is
~$53, not the ~$270 the raw token sum implies (see findings doc).

**VERIFIED:** `report.json` is written at `free_director.py:829`, inside
`free_investigate`; the `--paper` block runs afterwards at `__main__.py:225`.
So paper/referee/critic spend never appears in any study total or in
`cost_report`. All four run at `capabilities=FULL` (`study_paper.py:167`,
`referee.py:205`, `build_critic.py:171,214`) and **nothing sets the token
allowance for them.**

---

## 3. CODE vs PROMPT — which levers actually hold

This is the table to read before trying to change behaviour. A PROMPT lever is
a request the model may ignore; a CODE lever it cannot.

### Held by CODE (these are real)
- The action vocabulary, envelope shape, and every field type — validator +
  3-attempt re-ask, then hard fail (`free_decider.py:119-238`).
- Budget conservation: a child's slice is *transferred*, never copied; depth ≤ 5;
  tree total ≤ root total (`budget.py:12-28, 181-209`).
- Termination is guaranteed — three independent backstops
  (`free_director.py:658, 667, 673`).
- **The wall.** No model anywhere in the path (`verification.py` imports only
  `ast, json, math, uuid, pathlib`). It *overwrites* the model's `verified`
  flag (`free_experimenter.py:317-321`). Declared tolerance can only loosen,
  clamped at 2% (`verification.py:61-73`).
- Re-run code runs `--network=none --read-only --pids-limit=256`
  (`run_python_experiment.py:263-272`).
- An artifact file must resolve inside the run's own workspace; the model
  cannot set an artifact's `kind` (`free_experimenter.py:154-181`).
- No verified findings → no paper (`study_paper.py:148-153`).
- A paper citing a wall-rejected value gets a Python-written Correction section
  (`study_paper.py:188-198`).
- A handed-off file must re-derive from its producer (`reusable_artifacts.py:99-113`).

### Held by PROMPT ONLY (these are wishes)
- **When to stop.** `stop` is accepted unconditionally
  (`free_director.py:735-740`). Every rule about *not* stopping mid-decomposition,
  or *not* stopping with budget left, is prose.
- **"Budget is not a target to hit"** (`free_decider.py:109-110`) — the fix for
  the glider's padding. Prose.
- **"ONE GOOD CHECK PER CLAIM, THEN MOVE ON"** (`free_experimenter.py:66`) — the
  single biggest cost lever in the system. Prose. Nothing counts checks.
- **"IF YOU ARE BLOCKED, SAY SO"** — `blocked_on` is the only human-actionable
  output and is never schema-validated (`free_experimenter.py:62-64, 288`).
- **"Remote GPU results may never be marked verified"** — prose; a remote
  artifact simply fails the wall later, after the GPU is paid for
  (`free_experimenter.py:53`).
- **Referee "changes nothing"** — prose, while holding Write/Edit/Bash
  (`referee.py:75, 205`).
- **`publishable` means "every kept finding reproduced"** — prose, and the code
  means "at least one" (`free_experimenter.py:74` vs `:331`).

---

## 4. VERIFIED DEFECTS — the actionable list

Ordered by consequence. Each was re-checked directly.

### 4.1 The tool guard never fires — two mechanisms are inert ⚠️ BIGGEST
`model_call.py:520-523` delivers **both** the capability guard and today's
token-allowance wind-up denial via `can_use_tool`. Line 530 puts every FULL
tool on `allowed_tools`. The SDK is explicit
(`claude_agent_sdk/types.py:1804-1812`): `can_use_tool` "is *not* invoked for
tool calls already permitted by `allowed_tools`… To observe or gate *every*
tool call regardless of permission rules, use a `PreToolUse` hook."
**Grep for `PreToolUse` or `hooks=` across production code: zero hits.**

Consequences:
- `capability_guard`'s protections (transcripts, `memory/`, `runs/`, answer
  keys, home dir) **never fire for the experimenter's Bash/Write/Edit**.
- **Layer 1 of today's token ceiling is dead.** Item A rests on layer 2
  (derived `max_turns`) and layer 3 (pre-attempt refusal) only.

**Fix:** move both to a `PreToolUse` hook. Small, and it restores two
protections you currently believe you have.

### 4.2 The token ceiling barely binds
Layer 2 lowers `max_turns` only when remaining < 200 × 20,000 = **4M tokens**
(`model_call.py:337-341`). Above that the cap is unchanged at 200 turns. With
layer 1 dead (4.1), a move with a large remaining budget is effectively
uncapped — which is why the 5M-budget run reached 7.9M.

### 4.3 In-process capabilities get no allowance at all — **VERIFIED**
`run_experiment` passes `allowance=move_allowance`
(`free_director.py:760-765`); the generic capability branch (`:819-823`) passes
nothing, and `capabilities.py` never mentions an allowance (0 occurrences).
So `call_ideation` at `depth:"full"` — measured at **176 calls / 17.5M tokens**
in one study — costs **one move** and is uncapped.

### 4.4 `novelty_priority` is unreachable — **VERIFIED**
`capabilities.py:91` reads it. It is **not** in `_ENVELOPE_FIELDS`
(`free_decider.py:69-73`), and the validator rejects any key not on that list
(`:129-134`). The prompt never mentions it (0 occurrences). So the owner ruling
of 2026-07-27 making novelty "the director's dial" is **unimplemented** — it is
permanently `balanced`.

### 4.5 No per-turn evidence for 98.7% of spend
`_write_transcript` and `_append_action_trail` key on `stage_input["run_id"]`
(`model_call.py:999-1001, 1042-1043`), but the experimenter's stage input is
`{"question": goal}` (`free_experimenter.py:257`). So no
`runs/<id>/transcripts/`, no action trail, and RE-ASK / fence / retry lines are
printed but never reach `log.txt`. **Confirmed on disk:** a run dir contains
only `log.txt`, `verification.json`, `free_investigation.json`, `workspace/`.

### 4.6 `campaign` is a dead knob
`MoveType.CAMPAIGN` sets `RESEARCH_CAMPAIGN=1` (`dispatch.py:302-303`), read
only by `campaign_controller.py:58` via `stage4_simulation.py:305`, which the
free path never calls. The director's prompt still advertises it
(`free_decider.py:90`); a campaign move silently runs as a single.

### 4.7 No wind-down reserve — **VERIFIED**
`_move_allowance` (`free_director.py:56-66`) hands a dispatched move the
**entire** remaining budget. One move can consume everything; "land the
investigation cleanly" is prose.

### 4.8 A run that measures nothing can self-declare success — **VERIFIED**
`if claimed:` (`free_experimenter.py:330`) — with zero submitted claims the
model's own `publishable` stands unchecked, and `dispatch.py:482` sets
`succeeded = bool(result.publishable)`. Deliberate and documented in-code, but
the consequence is that a move which measured nothing reads to the director as
a success.

### 4.9 Transport retry is off exactly where failure is most expensive
A tooled call gets retry budget **0** (`model_call.py:756-757`), so one SDK
hiccup destroys a move that may have burned millions of tokens. The director's
cheap call gets 4 attempts (`free_director.py:290`).

### 4.10 Validation re-asks are full agentic runs
Attempts 2 and 3 are complete 200-turn runs with fresh context
(`model_call.py:1128-1136`). A persistently invalid director reply can burn up
to 12 FULL agentic calls in one turn (3 re-asks × 4 decide attempts).

### 4.11 The report write is silently swallowed
`free_director.py:828-831` wraps it in a bare `except: pass` — a study can
complete leaving no `report.json`, which also breaks resume accounting.

---

## 4b. The capabilities, and what a spawn actually carries

**Only `run_experiment` and `call_integration` fork a subprocess.** Everything
else — including a whole recursive child director and a full Co-Scientist
ideation pass — runs inside the director's own process. That is why
`decider_spend` was renamed `process_spend`: 15.17M ideation tokens were sitting
in a field named for the PI's decisions.

| action | moves | process | notable |
|---|---|---|---|
| `run_experiment` | 1 | subprocess | the 98.7% |
| `call_integration` | 1 | subprocess | it *is* an experiment; the wall verifies the joint number |
| `call_ideation` | 1 | in-process | uncapped (4.3); `depth:"full"` = the whole apparatus |
| `call_validation` | 1 | in-process | **advisory only** — never sets `verified`/`publishable` |
| `call_data_analysis` | 1 | in-process | one heavy FULL call |
| `spawn_sub_investigation` | 0 + the slice | **in-process recursion** | budget *transfers*, never copies |
| `read_memory` / `write_memory` | **0** | in-process | no model call at all |
| `stop` | 0 | — | unconditional (4.x) |

**Spawn.** `allocate(k)` moves `k` out of the parent pool (`budget.py:181-209`),
so tree total is conserved; tokens divide proportionally. Depth ≤ 5, checked in
`can_allocate` only — a node at max depth can still work, it just cannot
delegate. What comes back (`_bubble_findings`, `capabilities.py:389-411`): up to
**8** findings `{label, value, verified}` and 8 artifact producers, plus the
child's termination reason. **Narration never crosses** — the child's analysis,
its director's reasoning and its paper stay in the child.

⚠️ **Silent truncation:** `out[:_MAX_ITEMS]` takes the **first 8 in arc order**
(`capabilities.py:411`). A child that produced 12 verified findings loses its
last four to the parent, with no signal.

## 4c. The paper path

`--paper` is **opt-in and off by default**. `collect_study_evidence`
(`study_paper.py:88-134`) does the verified/unverified split **in Python, never
in the model's judgment**, and the writer receives only: goal, ≤60 verified
findings, ≤60 unverified findings separately, ≤40 arc phases, and artifact
*producers* (so it can regenerate). It never sees run logs, decision
transcripts, or the experimenter's narration.

Two deterministic protections worth knowing: the model-authored `paper_file`
path is resolved and rejected if it escapes the scratch root
(`study_paper.py:176-183` — an absolute path used to win), and the citation
check (`:263-300`) flags any line claiming reproduction of a wall-**rejected**
value and appends a **Python-written** Correction block, on the principle that
a correction about a model's over-claim must not itself be model-authored.

`typeset_paper` is deterministic, zero model calls, and runs last because the
referee and critic both append to `paper.md`.

⚠️ `stages/free_paper.py` (the run-level paper) is unreachable from the director
path *and* has a bug: it copies `paper.md` to `runs/<id>/` but leaves the PNGs
in `workspace/`, so every image link is broken.

## 4d. Memory — the cross-study channel is write-dead — **VERIFIED**

| kind | writer | status |
|---|---|---|
| `run_record` | `supervisor.py:170` | **live** — last 2026-07-28 |
| `director_note` | `write_memory` (`capabilities.py:512`) | **live** — last 2026-07-27 |
| `learned_summary` | `stage5_thought_layer.py` | **DEAD** — last 2026-07-20 |
| `milestone`, `final_output` | no writer | dead — last 2026-07-18 |

`stage5_thought_layer` is the sole writer of `learned_summary` and has **no
production caller** (only `capability_guard.py`'s name list, `schemas.py`, and
itself). It went with the 2026-07-23 purge. **Ideation still reads
`learned_summary`** (`stage1_ideation.py:867, 922`) — so it reads a frozen
window of pre-2026-07-20 entries forever.

Meanwhile `write_memory` writes `director_note`, which **only `read_memory`
reads**. So a lesson affects a future study only if that study's director
voluntarily calls `read_memory`. **Cross-study memory is effectively nil today**
— which is independent confirmation of the decision to drop it from the list.

The memory that *does* work is per-study and is not the journal at all: the arc
plus the carry bus (verified findings and re-runnable file producers handed down
through `_integration_context` / `_carry_block` / `inherited_artifacts`).

## 5. The knobs

**CLI:** `--goal · --resume-study · --mode · --max-moves (6) · --cost-cap ·
--allowed-substrates · --director (defaults to enum!) · --token-budget ·
--paper`

**Models:** four tiers — `heavy / light / triage / critic` — **all default to
`claude-opus-5`** (`models.py:75`). Override with `RESEARCH_MODEL_HEAVY` etc.
The director, the experimenter, the paper and the referee are all `heavy`.

**Behaviour env vars:** `RESEARCH_MOVE_TOKEN_ALLOWANCE` (set automatically per
move, but see 4.3) · `ALLOWED_SUBSTRATES` · `REFEREE=0` · `BUILD_CRITIC=0` ·
`CLAIM_REVIEW=0` · `RESEARCH_GPU_BUDGET_USD` · `RESEARCH_EST_COST_PER_MOVE_USD`
· `RESEARCH_IDEATION_*` · `BLANK_MEMORY`

**Load-bearing constants:** `FULL = 200 turns, 10 tools` (`model_call.py:212`) ·
`MAX_ATTEMPTS = 3` · `EST_TOKENS_PER_TURN = 20_000` · `MIN_GRANTED_TURNS = 8` ·
`WIND_UP_RESERVE_TURNS = 4` · `MAX_DEPTH = 5` · `DEFAULT_MAX_MOVES = 6` ·
decision cap = `moves × 3 + 10` · `MAX_BRIEFED_FINDINGS = 12` ·
`MAX_CARRIED_FILES = 8` · `DEFAULT_REL_TOL = 1e-6`, clamp `0.02`

**Sandbox profiles** (`run_python_experiment.py:113-197`): `default` (300s/4GB/
2cpu) · `heavy` (1800s/6GB/4cpu) · `atomistic` · `biodesign` · `engineering`,
each with a `-heavy` variant. Invariant jail regardless of profile:
`--network=none --read-only --pids-limit=256 --tmpfs=/tmp:512m`.

**10 routable substrates:** `python_experiment · sympy_symbolic_exact · rdkit ·
cobrapy · mafft · homology_search · ngspice_linear_passive · cavity_2d_cfd ·
calculix_cantilever_fea · fenicsx_cantilever_elastic`

---

## 6. What is built but never runs

- ~~The ideation apparatus~~ **CORRECTION 2026-07-28: this was WRONG.**
  `call_ideation` HAS fired — three times, verified from every arc on disk:
  `study-20260725T073215Z` (ideation_done), `study-20260726T010756Z`
  (ideation_done), and `study-20260727T045848Z` (crashed —
  `call_ideation_failed`, fixed by `dbb9469`). In both successful cases the goal
  made the IDEAS the deliverable, and the director said so in its reasoning.
  It did not fire in the two runs of 2026-07-28 because one goal was a
  placeholder and the other was a well-specified optimisation — neither warranted
  it. **The apparatus is live and the director reaches for it correctly.** The
  earlier "never fires" claim came from looking at two runs instead of all of
  them.
- **The referee and build critic** — no `referee.json` or `build_critique.json`
  exists in any study on disk. The critic's own code comment records that it
  "never once ran on a successful study" until a recent indentation fix.
- **`claims_from_run`** (`verification.py:810`) — zero production callers.
- **`campaign`** — see 4.6.
- **`stage5_thought_layer`** — sole writer of `learned_summary`; purged path.
- **`stage6_paper`, `desk_review`, `free_paper`** — no reachable caller from the
  director path (`free_paper` only via a hand-run `supervisor.py --paper`).
- **`pi_agent/loop.py` + `decider.py`** (the enum director) — still the CLI
  **default**, but every recent study reports `"director": "free"`.
- **`memory/ledgers.py`**, **`tools/pi_gate.pi_enforce_verdict`** ("wired
  NOWHERE", its own comment), **`study.run_study_fan`**.

---

## 7. Where a human can intervene today

Almost nowhere, which matters for the planned interjection feature.

- **Before:** the goal string, the CLI flags, the env vars above.
- **During:** `python -m liveview` is **strictly read-only by design** — every
  web route is `do_GET`, there is no POST handler at all (`web.py:313-347`), and
  it binds 127.0.0.1 only. The director loop has **no** file watch, no signal
  handler, no queue, no control file (`free_director.py:645-823`).

  **Three seams exist for building interjection, in descending bandwidth:**
  1. **`arc.jsonl` is re-read every turn** (`free_director.py:646`), so anything
     appended lands in the very next decision prompt with no new plumbing. This
     is the highest-bandwidth seam — but `study_arc` does a bare `json.loads`
     per line, so it needs a *typed, validated* channel, not raw arc writes.
  2. **`memory/journal.jsonl` + `read_memory`.** Append a `director_note` and
     the director will see it — but only if it voluntarily calls `read_memory`
     on a later turn. Closest thing to an existing channel; unreliable.
  3. **`--resume-study`** — kill, edit disk state, relaunch. Coarse, but it
     already works and loses nothing.

  How liveview infers state, which any interjection UI can reuse: **a decision
  file is written before its action runs; an arc line is appended after it
  finishes** (`reader.py:16-23`). So `n_decisions > n_arc` means the decided
  action is in flight, and the decision file says which.
- **After:** `--resume-study <id>` rebuilds from disk and continues.
- **Escape hatch:** a run reports `blocked_on`, printed as "BLOCKED — HUMAN
  ACTION" (`__main__.py:207-218`) — but it is prose-only and never validated
  (4.5 above).
