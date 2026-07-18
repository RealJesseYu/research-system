# BIO WAVE · BUILD PACKET · load the whole non-chain wave, fast
### Issued by the Substrate Wave Guide, 2026-07-18. For a NEW BUILD CHAT (has the repo).
### Owner is on a deadline. This packet is self-contained: phase it, report at the gates, don't wait on the Wave Guide except where a ruling is named.

**Precedence: today's disk > `BIO_DISK_RECON_FINDINGS.md` > `HANDOFF_wave_guide_era_a07f939.md` > `docs/repo_facts.md` > this packet.**
**Era of record: `a07f939`.** Five substrates routable. `repo_facts.md` chapters Q13–Q15 are SUPERSEDED on disk — trust the disk-recon.

---

## BLOCK A — WHAT THIS IS AND HOW FAST IT GOES

**Load the eleven non-chain bio substrates and make them runnable and trusted.** Chains are a separate build (the artifact-channel spike runs in parallel, not here). This packet is everything else.

**The disk-recon priced it: ≈17–25 ruler-units ≈ ~3 build-days of build, MEDIUM confidence.** The ruler is `56e16d9` (the ngspice flip). Two one-time plumbing builds, then eleven mostly-parallel substrate flips, then promotion.

### ⭐ The rule that makes this fast: parallel where disk allows, serial only where it must

The disk-recon (§6) confirmed the dependency graph. Exploit it:

- **The two one-time plumbing builds are INDEPENDENT** (`stage5_thought_layer.py` vs `substrate_selection.py`) — **build them in parallel worktrees.**
- **The eleven wrappers are substrate-local** — no collision (§5). **Build in parallel across worktrees.**
- **Merges are serial** (shared files: registry, `_SIGNATURES`, `_VOCABS`, dispatch maps, the two growing fixtures). Wave Guide merges.
- **Batteries are serial** (Docker contention). **One big battery night at the end** — owner already ruled this.

### ⭐ The defer-defer-defer fix is BUILT INTO this packet, three ways
The owner is done with reflexive defer. The disk-recon proved trust is uniform in code — so the fix is not a gate change, it is three enforced rules:
1. **Every bio card is written R-CARD-2-compliant: every criterion states its consequence, and "inside bound → TRUST" is explicit.** Vague cards defer; decisive cards trust. This is a HARD requirement here, not a nicety. ngspice's decisive card scored 30/30 with zero wrong-defers.
2. **Every substrate gets promoted to `mature` after its battery passes** (Phase 4). Until mature, auto-mode force-downgrades trust→defer — that is the single biggest defer source and it is a switch that flips on promotion.
3. **Batteries are 5-in/5-out by design — do NOT read a 50%-defer battery as "the gate over-defers."** Report the in-envelope trust rate separately from the out-of-envelope defer rate.

### Run rules (BINDING)
- **Run venue (ABSOLUTE):** plain Terminal, `caffeinate -i`. Never inside Claude Code.
- **Run ledger:** every battery on the owner's manifest before launch. FAST exempt.
- **FAST green gates every merge.**
- **Era `a07f939` holds** except where a ruling moves it — the two growing fixtures (`tests/fixtures/d1/feasibility_nudge.txt`, `tests/fixtures/c235/chooser_retry_user_turn_v235.txt`) re-capture per promotion by design; that is expected, not an era break. **Cavity byte-identity still absolute.**
- **Append-only memory. Fail loud. Never a cavity fallback.**

### STOP at each phase gate and report. No `/clear`.

---

## BLOCK B — THE DOCTRINE BLOCK
### (Verbatim. Put in front of Claude Code.)

- **DISK BEATS DICTATION — including the strategist's.** Corrected 10+ times this week across six chats. Structure survives; magnitude estimates don't. **No claim without a `file:line`.**
- **A check that cannot fail is not a proof.**
- **Jails and tripwires are proven by FAILING THE ESCAPE, never by reading the config.**
- **No LLM in the execution step.**
- **Summarize at the wrapper.**
- **Typed input, hard timeout, one retry, capped diagnostics.**
- **Fail loud. Never a silent fallback. Never a cavity fallback.**
- **Everything enters at `calibrating` = unroutable. Promotion is a separate owner ruling.**
- **The card unit is the (substrate, physics-regime) pair.**
- **One runtime source of truth for contract text — the card points at it, the case file imports it, never a third copy.**
- **Anything you can't afford broken goes in code, never the prompt.**

---

## BLOCK C — REFERENCES

**Upload:** `BIO_DISK_RECON_FINDINGS.md` (the plan — §6 build order, §5 collisions, §3 numbers) · `HANDOFF_wave_guide_era_a07f939.md` (the `56e16d9` ruler, R-B-1, §3-regime rule) · `docs/repo_facts.md` · the three signed cards (ngspice/scipy/fenicsx — the card shape to mirror) · `BIO_WAVE_RECON_FINDINGS.md` §4 (the twelve-substrate table + batched ruling checklist).

**Name by path to Claude Code:** `tools/substrate_registry.py` · `tools/substrate_selection.py` · `tools/qoi_vocab.py` · `tools/substrate_dispatch.py` · `stages/stage5_thought_layer.py` · `stages/stage6*.py` · `stages/stage2_spec.py` · `stages/stage3_fidelity_gate.py` · `stages/stage4_simulation.py` · `schemas.py` · `stages/gate1_chooser.py` · `tools/run_ngspice.py` (the wrapper shape) · commit `56e16d9`.

---

## BLOCK D — THE BUILD, PHASED

**Each phase gates the next. Report at each gate. Parallelize inside a phase; the Wave Guide merges serially.**

### ⚠️ D.0 — FIRST: a 30-minute confirm, then GO. Do not re-run the recon.
The disk-recon is thorough and trusted. **Confirm only what a build must not get wrong**, then proceed without waiting:
- The eleven substrates + their trust-class + QoI-shape, from `BIO_WAVE_RECON_FINDINGS.md §4`. (Chains substrate RFdiffusion is EXCLUDED — gen-class, chain-only.)
- The `56e16d9` file list — your unit, and your surface checklist per substrate.
- **Register estimates against the ruler** (units, build-hours, tests, census). Then GO.

### D.1 — PLUMBING (two builds, PARALLEL worktrees) · ~4–7 units total

**D.1a — Stage-5 contract handoff.** (Disk-recon Claim 1, the "it is nowhere" gap — build #1.)
Stage 5 gets no substrate contract; a hard tripwire (`stage5_thought_layer.py:159-163`) forbids a seventh input key. **Widen `PROMPT_INPUT_KEYS`, relax the tripwire, thread `contract_for(payload["substrate_id"])` into `run()`'s `prompt_inputs` (`:219-227`), add one additive "what a human must validate" field to stage 6.** This is what lets the gate write a grounded validation instruction instead of a bare defer.
> ⚠️ **Model-visible surface → era question.** Census the stage-5 fixture (the recon found NO fixture pins stage-5's payload — capture one BEFORE touching). Cavity byte-identical after. Not identical → STOP, escalate.

**D.1b — Step 41 hierarchical routing.** (Disk-recon Claim 3 + §6 sharpening #2 — the harder gate.)
`select_substrate` (`tools/substrate_selection.py:159-203`) loud-stops (R-B-1) when >1 routable signature-subset-matches. At bio scale, near-neighbor **families** (all structure predictors take `{protein_sequence}`, etc.) tie → unroutable-by-default. **Build within-class disambiguation: task-class first, then instance.** The recon notes `experiment_picker._detect` prototypes signature matching — read it.
> **This is a routing POLICY. Design it, show the owner the design (not a description), get the ruling. Do NOT invent a tie-break silently.** It gates the second near-neighbor in every family — most of bio.

**Gate D.1:** both plumbing builds green, cavity byte-identical, era holds, FAST green. **Report.**

### D.2 — THE ELEVEN WRAPPERS (parallel worktrees, serial merges) · ~13–18 units

Per substrate, mirror the `56e16d9` flip + the three signed cards. **The batched ruling checklist (`BIO_WAVE_RECON_FINDINGS.md §4b`) is the owner's column-sheet — every substrate needs its row ruled.**

The eleven (RFdiffusion excluded — chain-only):

| Substrate | class | QoI (scalar) | wrapper note |
|---|---|---|---|
| Cas-OFFinder | answer | off-target count | deterministic enumeration |
| RDKit | answer | descriptors | cheminformatics, deterministic |
| AlphaFold DB | lookup | mean pLDDT | DB lookup — `web_search` precedent, never trusted alone |
| PDB/PubChem/UniProt/ChEMBL | lookup | round-trip id | API bundle, network reliability surface |
| Boltz-2 | filter | RMSD / affinity | structure+affinity predictor |
| AutoDock Vina | filter | docking score | dock into rigid pocket |
| COBRApy | filter | growth rate | flux-balance, deterministic LP |
| CRISPOR/CHOPCHOP | filter | activity score | guide scoring |
| ProteinMPNN | filter | seq recovery | sequence-for-backbone |
| BLAST/HMMER/MAFFT | answer/filter | e-value | sequence search/align |
| AiZynth/ASKCOS | filter | synthesizability | retrosynthesis MCTS |

**Per substrate, all seven surfaces of the `56e16d9` unit** + the three enforced rules:
1. Wrapper (`tools/run_<x>.py`) — typed input, timeout, one retry, capped diagnostics, log-summarized, **no LLM in execution**, jails proven by failing the escape where network/fs matters.
2. **§3-regime stated at enrollment** (R-23.5-5c) — derived from the wrapper's own capabilities, never invented, or the spec fails loud.
3. **Card — R-CARD-2 compliant, consequence on every criterion, "inside → TRUST" explicit.** The trust-split spine (C4 shape), the C1-hole as a declared KNOWN GAP. Points at the one runtime contract constant; case file imports it; **never a third copy.**
4. Contract wired · signature wired (**with its disambiguation plan — §5 collision #1: each bio packet carries a signature plan, not just a staging path**) · vocab · adapter · QoI translation · run-entry constructor.
5. Scalar confidence via the `state`-key pattern (owner ruled scalar — no array plumbing).
6. Registry row at `calibrating`/`routable=False`.
7. Tests; staged to `onboarding/<substrate>/`; **tests ADDED never totals.**

**Gate D.2:** eleven merged serially, each green at merge, era holds at each, FAST green. **Report the reconciled test count and the routable count (should still be 5 — nothing promoted yet).**

### D.3 — BATTERIES (one serial night, owner-OK'd) · the maturity path

Eleven calibration batteries, `--repeats 3`, serial (Docker), one night, on the manifest. **5-in/5-out slates per the calibration template.** Report per substrate: in-envelope trust rate AND out-of-envelope defer rate, SEPARATELY (the defer-reading rule). Splits earn higher-N re-runs.

**Gate D.3:** eleven battery reports. **Report the confusion matrices.**

### D.4 — PROMOTION (owner rulings, batched) · kills the forced defer

For each substrate whose battery is clean, the owner rules **promotion `calibrating` → `mature`**. This is what removes the auto-downgrade-to-defer. Present them as a batch (the owner rules down a column). **`routable=True` + `mature` land together per the promotion pattern.**

**Gate D.4:** promoted substrates are routable AND mature — trust verdicts now stand without forced defer. **Report the final routable+mature count.**

---

## BLOCK E — ACCEPTANCE TESTS

1. ⭐ **ERA `a07f939` holds** at every touched surface incl. any newly-censused (D.1a). Cavity byte-identical. Tripwire proven by firing. Not identical → STOP.
2. **Each substrate's chain closes:** hypothesis → chosen → its-shaped spec → routed → executed/paused. Shown.
3. ⭐ **Step 41 disambiguates near-neighbor families** — a `{protein_sequence}` spec resolves to ONE predictor or stops loudly with a stated reason. Never a coin flip. Proven with ≥2 signature-overlapping substrates routable.
4. **Cavity + the five prior substrates unchanged.** Chains still close.
5. **Fail loud, proven by firing:** unknown substrate raises · missing regime rejects by name · **no cavity fallback**.
6. ⭐ **The defer fix works:** in-envelope cases on a MATURE substrate return trust, not defer. Report in-envelope trust rate — it should be high, and if it isn't, the card is too vague (fix the card, not the gate).
7. **Suite green + FAST green.** Tests ADDED never totals.
8. **`repo_facts.md` refreshed** for every section this wave invalidates (selection, stage 5, routable count) + re-stamped sha. **Standing rule.**

---

## BLOCK F — PRE-REGISTRATION
Register before D.1: units per phase vs recon · build-hours vs the ~3-day estimate · census count (Wave Guide has said "1" and been wrong twice — count) · tests added (last build: registered 25–40, actual 121 — price the fixture harnesses) · the era call for D.1a.

---

## BLOCK G — REPORT-BACK (to the OWNER), at each gate

**Plain language. Bullets. No jargon. End with a task list — tasks only.**
Per gate: what landed · era yes/no (if no, that's the whole report) · **for D.1b: the Step-41 routing design, shown not described — owner rules it** · for D.4: the promotion batch — owner rules the column · tests added · what the owner must rule · scorecard, misses first · where this packet was wrong (not empty).

---

## THE THREE THINGS MOST LIKELY TO GO WRONG
1. **Step 41 gets a tie-break invented instead of designed-and-ruled.** It is routing policy. Show the design, get the ruling.
2. **A card ships vague and the owner blames the gate for deferring.** R-CARD-2 compliance is the defer fix. A criterion with no consequence IS a defer. Enforce it.
3. **The stage-5 fixture isn't captured before D.1a touches the payload.** Then the era is unprovable. Census first — the recon found NO fixture pins stage 5.
