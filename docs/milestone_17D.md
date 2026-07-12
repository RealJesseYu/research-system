# Milestone: Step 17-D — Evolution (CLOSE)

**Date closed:** 2026-07-12 (doc-only close session; zero model/API calls).
**Built:** `e599e47521bf529e39ec2379a9b3462050c06582` on `build-17D`.
**Merged:** `04d27e8` (true merge; build commit preserved verbatim).
**Witness launched from:** `14f96e6` (launch HEAD carried by hand per the prep
record; confirmed in-session — `git rev-parse HEAD` = `14f96e6` at close, and
the four witness runs postdate the merge).
**Close commit:** recorded in CLAUDE.md's status section post-commit (this doc
cannot know its own hash).

**Evidence:** `harness/witness_17D.log` (1208 lines),
`harness/killrate_last_run.json` (timestamp 2026-07-11T13:46:06Z), runs
`killrate-20260711T093310Z-same1`, `-104401Z-same2`, `-113749Z-alt1`,
`-124123Z-alt2`. Every number below was re-derived from these disk artifacts
in the close session; dictation-vs-disk mismatches are listed in the
Asterisks section at the end.

---

## 1. Verdict

**Mechanism witnessed PASS; competition path live-unexercised.**

Re-derived from disk:

- **4/4 slots resolved, zero relaunches** — each slot has exactly one attempt
  in the battery JSON; no relaunch lines in the witness log.
- **Memory md5 `373c886b` on 4/4**, all slots `comparable: true`.
- **6 variants emitted** — 2 per Evolution-running slot (same1, alt1, alt2);
  **same2 halted pre-Evolution at zero parents** (its exception: all 2
  filter-stage hypotheses judged 'known', zero survivors — no
  `evolution_variants.json` exists for same2). **0 variants accepted.**
- **Emission schema rejects 0/6 on pin `claude-sonnet-4-6`** —
  `stage1_evolution_simplification` 3 calls / 0 rejects,
  `stage1_evolution_out_of_box` 3 calls / 0 rejects; every variant record's
  provenance carries `model: claude-sonnet-4-6`
  (`EVOLUTION_MODEL = "claude-sonnet-4-6"` in `stages/evolution_strategies.py:81`).
- **Zero-accept tolerance fired 3/3 without crash** — "zero variants accepted
  — proceeding over parents alone" appears once per Evolution-running slot
  (witness log lines 318, 895, 1195) and all three runs completed to scored
  status.
- **Combination guard fell back twice, logged** — alt1 and alt2 both:
  "rotation landed on combination with 1 parent(s) — fell back" (lines 858,
  1158). same1's rotation landed on out_of_box directly.
- **survivors.json integrity holds** — exactly 7 fields per record
  (`addressable_notes, critique, id, novelty, quality, rationale, statement`),
  zero ev-ids anywhere (same1: h4/h1/h2; alt1: h9; alt2: h1), and record
  counts equal battery k (3/–/1/1): **k counts Generation survivors only**.
- **Cost: 275 total calls (228 model_call + 47 web_search)**, mean
  **68.75 calls / 61.0 min per slot** excluding the 3×180 s designed
  inter-run sleeps (`INTER_RUN_SLEEP_S = 180`; total wall 15175.3 s minus
  slot walls 4070.4+3048.4+3633.8+3882.7 = 14635.3 s leaves exactly 540 s;
  14635.3/4 = 60.98 min).
- **Reject rate 0.031** (7 rejects / 228 model calls; bar 0.04; 17-C was
  0.028 per docs/milestone_17C.md).

---

## 2. MANDATORY dedup check — CLOSED, outcome (c)

**Method deviation, disclosed:** zero variants reached any tournament pool
(all six were rejected by the Reflection chain before pooling), so the live
dedup flags could not fire — every `tournament_state.json` has
`dedup_flags: []`. The **pre-registered offline salvage** ran instead, on the
identical vectorizer path (`stages/tournament.py::proximity_matrix`:
`expand_identifiers` preprocessing + `TfidfVectorizer(ngram_range=(1,2),
min_df=1, stop_words="english")` over statement+rationale).

**Vectorizer-path proof:** a parents-only refit reproduced same1's live
tournament matrix **to the last digit** (h4_vs_h1 = 0.0,
h4_vs_h2 = 0.14007679534918446, h1_vs_h2 = 0.04452769505665517).

**Provenance note:** the overnight salvage left no persisted artifact; it was
**re-executed in this close session** (deterministic Python, zero model
calls) and reproduced every dictated value exactly. The full table:

| pair (parents+variants refit, per run) | strategy | similarity |
|---|---|---|
| same1 ev1 vs h4 (parent) | simplification | 0.2266 |
| alt2 ev1 vs h1 (parent) | simplification | 0.1947 |
| alt1 ev1 vs h9 (parent) | simplification | 0.1170 |
| same1 ev2 vs h4 (parent) | out_of_box | 0.2290 |
| alt2 ev2 vs h1 (parent) | out_of_box | 0.1677 |
| alt1 ev2 vs h9 (parent) | out_of_box | 0.0581 |

Distinct-parent controls: all 18 off-diagonal pairs across the five live
tournament matrices (17-C's four witness runs + tonight's same1) span
**0.0 – 0.1971**.

**Finding:** hand-labeled sibling band (simplification variants vs their
parent) **0.117–0.227**; departure band (out_of_box) **0.058–0.229**;
distinct-parent controls **0–0.197** across 17-C and tonight. **The bands
interleave.** The sharpest exhibit: alt2's ev1 is the parent minus its
qualifiers — parent h1 "Secondary corner eddy size increases monotonically
with Reynolds number throughout the laminar regime (Re < 30,000)" vs ev1
"Secondary corner eddy size in two-dimensional laminar lid-driven cavity
flow increases with Reynolds number" — and it scores **0.1947, BELOW
genuinely distinct pairs** (control max 0.1971). No tf-idf threshold
separates siblings from distinct hypotheses.

**RULING:** the 0.85 threshold **stands as a near-verbatim detector**;
recalibration is **refused on evidence** (any threshold low enough to catch
siblings would flag genuinely distinct pairs); an embedding-class similarity
upgrade is **queued post-deadline**. **Recorded pattern:** the Reflection
chain is the de-facto sibling filter upstream of dedup — it killed all six
variants, including the qualifier-stripped sibling, before dedup could see
them.

---

## 3. Kill shape (evidence for 17-E)

- **simplification → known, 3/3**: 2 `initial_review_discard` (alt1, alt2) +
  1 `judged_known` at the full-review filter (same1).
- **out_of_box → fundamental_flaw, 3/3** at deep verification.
- **All three out_of_box review rounds ran on OpenAlex zero-hit retrieval**
  (witness log: every ev2 round shows `openalex=0`; same1's ev1 round, by
  contrast, had `openalex=3`).

Exhibits, verbatim from the `evolution_variants.json` files:

> **initial_review_discard** (alt1 ev1): "Restates textbook/classic result:
> the steady-to-unsteady transition in lid-driven cavity flows with
> increasing Re is well-established in literature (Ghia et al. and
> successors)."

> **fundamental_flaw** (alt1 ev2): "The hypothesis is fatally undermined by
> a qualitative inversion in its core premise: Moffatt eddy theory implies
> that velocity amplitude decays geometrically with depth into the corner
> hierarchy so that inner eddies are the most viscosity-dominated, not
> least, directly negating the claimed inward-to-outward instability
> cascade mechanism."

---

## 4. Parent-pool watch — ARMED

- k distribution **[3, 0] same / [1, 1] alt** vs 17-C's **[3, 4] / [3, 3]**.
- **same2 k=0, `all_known_at_filter`** — the first zero-survivor run since
  17-fix-A. Its two filter kills (h2, h8) cite **R10/R11/R12** with grounded
  rationales and read defensible; its seven deep-verify kills each name a
  specific qualitative physics defect.
- Deep-verify kill rates **0.5 / 0.778 / 0.7 / 0.5** — same2's 0.778 is
  above fix-A's same-domain top (0.67).
- Frozen-file check: `git diff acd7dd0 14f96e6 --
  stages/generation_strategies.py stages/reflection_reviews.py` is **empty**
  (re-verified live in this close session) — the parent-pool shift is not
  explained by code drift.

**TRIGGER (ruled):** the 17-E witness read audits same-domain kill
rationales; **any k=0 slot OR ≥2 slots at k≤1 → dedicated forensic session
before 17-CLOSE, and Step 18 does not launch until it resolves.**

---

## 5. Carried to 17-E

- **variant-in-tournament** and **variant-in-debate** never fired live (zero
  variants accepted; all tournament matrices contain only h-ids).
- **combination** and **grounding_enhancement** never fired live. The
  build-time claim that 4 slots cover all four strategies was **wrong** —
  independent per-run seeded draws do not cycle (all three Evolution runs
  drew simplification + out_of_box, twice via the combination fallback).
  Deliberate coverage at 17-CLOSE's supervised run if still unfired.
- **Zero-parent ordering demonstrated live** — Evolution evolves parents and
  cannot rescue a zero-survivor run (same2), as designed.
- **Accepted-regime cost projection 84–89 calls/run** (provenance:
  strategist recon estimate, first recorded here) — **unvalidated**; tonight
  is the zero-accept regime.
- **S2 429'd all 38 non-zero-hit retrieval rounds** (zero-hit repair proven
  live on 9 rounds; 47 rounds total). The controlled re-probe debt stands.
  *(Dictated as 39; disk says 38 — see Asterisks.)*

---

## 6. Instrument notes

- Battery JSON lacks `variants_emitted` / `variants_accepted` (17-D spec
  gap — the counter computes them, the battery never copies them; additive
  fix ruled into 17-E).
- Dry-run pin listing omits `EVOLUTION_MODEL` (the battery JSON's
  `model_pins` block does not name it; queued 17-CLOSE).
- Battery git-HEAD recording queued 17-CLOSE (no HEAD field in the battery
  JSON; tonight's launch HEAD was carried by hand).
- `fence_stripped`: **214 NOTEs** across the four run logs (60/44/55/55) ≈
  **94% of the 228 model calls** — standing evidence for the parked
  strip_fence ruling.

---

## 7. Asterisks (dictation vs disk)

1. **S2 429 round count: dictated 39, disk says 38.** The witness log holds
   exactly 47 retrieval-round summary lines: 38 with `s2=error` (all
   HTTP 429) + 9 with `s2=0` (zero-hit repaired). The disk value (38) is
   recorded in section 5.
2. **Dedup salvage provenance:** the overnight salvage persisted no artifact;
   the numbers in section 2 come from a re-execution of the pre-registered
   salvage in this close session (deterministic, zero model calls), which
   reproduced every dictated value exactly — including the parents-only
   refit matching same1's live matrix to the last digit.

No other mismatches: every remaining dictated number was re-derived from
disk and matched (275/228/47, 68.75, 61.0 min, 0.031, md5 ×4, k
distributions, kill rates, bands, 0.1947, 214 NOTEs, empty frozen diff).
