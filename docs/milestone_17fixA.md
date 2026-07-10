# Journal — Step 17-fix-A: The Deep-Verification Fix
## Session closed at commit 6e4796b (atop b000274). Baseline: 18.7 Haiku (a4dd853).

## WHERE THIS SESSION STARTED
Steps 16.6 and 18.7 were closed. The Sonnet→Haiku downgrade on the Haiku-pinned
stages had HELD. We had a locked 10-run Haiku baseline that everything downstream
measures against. And we had a known, diagnosed problem waiting: tournament
starvation. The whole instruments-first reorder of Phase C had been built
specifically to enable THIS fix — get the ideation stage producing a rankable pool
so the tournament (17-C) has something to work on.

The starting decision was already made going in: build all three parts of the fix
as ONE coordinated chunk rather than separately. The reasoning — they're coupled.
Fixing generation without fixing the reviewer wouldn't move the survivor count;
fixing the reviewer's kill logic without the constant-guard would leave a whole
class of bad kills intact. Three coupled changes, measure once. If we'd done them
separately we'd have spent three scored runs (30 hours) and still not have a clean
attribution, because each partial fix confounds the next.

## THE READ-ONLY RECON FIRST — AND WHY IT CHANGED EVERYTHING
We did NOT start by building. We started with a read-only reality check to locate
the three code sites and understand what they actually did. This was the right
call and it paid off immediately, because the recon revealed the fix was NOT the
shape we'd planned:

  - We'd planned to "stop asking Generation for numbers." The recon found Generation
    was never ASKED for numbers — it was inventing them emergently. So "stop asking"
    was a no-op. The real fix had to forbid unsupported numbers, not remove a request
    that didn't exist.

  - We'd planned to "add a fundamental-vs-addressable distinction to the reviewer."
    The recon found that distinction was ALREADY IN THE PROMPT — the reviewer was
    explicitly told not to kill on non-fundamental flaws, and was ignoring it. The
    real problem was structural: a single boolean `fundamental_flaw` with nowhere to
    record a non-fatal concern. The model had no data channel to express "keep but
    note," so it defaulted to kill. This reframed the entire fix: the lesson wasn't
    "write a better instruction," it was "give the model a structured field to act
    through." (This became our #1 paper claim.)

  - We'd planned to "make the constant-guard check numbers against retrieval." The
    recon found deep verification runs retrieval-FREE by design — its docstring
    literally says "no retrieval." So there's nothing to check numbers against. The
    fix had to be logical, not retrieval-based: any objection resting on a remembered
    number is, in a retrieval-free context, addressable by definition — so it can
    never justify a kill.

The recon also cleared the single most important safety question — would the fix
break the before/after comparison? The survivor-counter reads two specific keys and
counts survivors as entries in survivors.json. As long as we never renamed those
keys and never routed an addressable-flaw survivor into the discard list, a "keep +
note" hypothesis would flow to survivors.json, raise the count, and the counter would
stay valid with zero edits. That became a HARD INVARIANT for the whole build. This is
the thing that would have silently invalidated the baseline if we'd missed it.

## THE JUDGMENT CALLS WE RULED ON (and what we rejected)
  A. Generation fix — prompt-only, or prompt + validator? RULED: prompt + a WARN-ONLY
     validator on strategy 1. The validator does NOT reject (rejecting on a fuzzy
     number-match would bounce good hypotheses on formatting noise and inflate the
     reject rate, a metric we watch). It just LOGS unsupported numbers as a signal so
     we can see at measurement time whether the prompt worked. The prompt is the
     enforcement; the validator is the instrument. Rejected: hard-reject validation
     (too brittle, tested-first says don't build it until the prompt proves
     insufficient).

  B. Parts 2 and 3 — separate or merged? RULED: merged. The constant problem IS a
     special case of the addressable problem — a kill resting on a remembered number
     is definitionally an addressable objection, not a fundamental one. One mechanism
     handles both. Rejected: two separate changes (would have been redundant code for
     one conceptual fix).

  C. Constant-guard — deep-verify only, or also initial review? RULED: deep-verify
     ONLY. Initial review also kills from general knowledge, but its discards feed the
     DENOMINATOR of the kill-rate metric — touch it and the before/after denominator
     shifts and the comparison breaks. And the evidence showed the false-constant kills
     were all in deep-verify anyway. Rejected: guarding initial review too (would have
     broken the metric to fix a problem that wasn't there).

  D. Where does the carried note live? RULED: on the reflection/ranking evidence,
     stopping at gate 1 — NEVER on the chosen-hypothesis object. A note that crosses
     gate 1 would hit the locked CHOSEN_HYPOTHESIS_KEYS schema and break the locked-
     artifact ruling. This wasn't really a veto — crossing gate 1 was never an option;
     we recorded it so the constraint is explicit.

  E. The success criterion itself — CORRECTED mid-session. The plan said "rankable
     pool, ideally 3–6 survivors." The recon found MAX_SURVIVORS=4 — a hard ceiling.
     "Ideally 3–6" was never achievable as coded. Corrected the honest target to
     "reliably ≥2, up to the ceiling of 4." Left MAX_SURVIVORS itself alone — it
     wasn't implicated in the diagnostic and changing it would have been unscoped
     scope-creep. This correction matters: without it we'd have measured against an
     impossible bar and called a real success a partial failure.

## WHAT WE BUILT (main chunk + one follow-up)
The main build implemented all three parts as ruled. Then a follow-up caught a real
bug in our own fix: the carried note reached the reflection record but got DROPPED
one hop later, where stage1_ideation rebuilds survivor records with an explicit key
list that didn't include addressable_notes. So the note reached reflections but never
reached the RANKING evidence — meaning the tournament (when it exists) would rank a
carried-note hypothesis as if the concern were never raised. That's not "carried
forward." We caught it, ruled it a two-line schema-free fix (the recon had already
cleared that a note staying inside Stage 1 touches no schema), and closed it BEFORE
the scored run — so the number we locked in measures the CORRECT fix, not one we'd
have to amend later. Also added a durable per-run log of WHICH numbers fired the
signal (a bare count across a 4-run battery is thin evidence for "did the prompt
suppress invention").

## THE MEASUREMENT (scored kill-rate batch, --repeats 5, b000274 vs baseline)

  Baseline same-domain:  k = {0,0,0,0,1}   (4 of 5 = ZERO survivors)
  Baseline alt-domain:   k = {2,1,1,1,0}
  Baseline kill rate:    86–100% same / 70–90% alt

  AFTER THE FIX:
  Same-domain:  k = {1,1,3,1}   — ZERO zero-survivor runs (was 4/5)
  Alt-domain:   k = {2,1,3,4}   — alt5 hit the ceiling of 4
  Kill rate:    25–67% same / 20–67% alt   — roughly HALVED
  Elo ranking FIRED in the k≥2 runs (structurally impossible at baseline k≤1)
  Invented-number signal: 7 total across ~15 rounds; 0 in most scored runs
  Reject rate: 0.013 (BELOW baseline 0.04 — no format churn added)
  Ledger 0/0; all comparable runs matched memory md5 373c886b

  THE CAVEAT WE WILL NOT ROUND AWAY: only 8 of 10 slots produced data. same5 and
  alt1 went UNRESOLVED — they exhausted the relaunch cap (MAX_RELAUNCHES=2) on
  arXiv HTTP 429/503 errors. This is arXiv rate-limiting under heavy overnight load,
  a GROUNDING-TRANSPORT failure, NOT the fix failing. same5 burned all three attempts
  on 429/429/503; alt1 on three straight 429s. 17-fix-B (already built) fixes exactly
  this by moving novelty grounding to OpenAlex.

## WE READ THE HYPOTHESES — THE NUMBER GOING UP IS ONLY HALF THE WIN
The critical second check: are the REMAINING kills genuinely fundamental, or did the
fix just make the reviewer soft and let garbage survive? We read the actual run files
rather than trusting the aggregate.

  same1 (killed 6, kept 1) — every kill was legitimate and STRUCTURAL:
    · one for claiming a scaling exponent its own mechanism can't produce
    · two for circular reasoning (the hypothesis assumed its own conclusion)
    · one for a mechanism operating at a scale where the invoked effect is negligible
    · two as near-duplicates of the survivor
    NOT ONE killed on a remembered constant. We specifically searched for the Moffatt-
    ratio pattern (the diagnostic's smoking gun — cited as ~0.036 in one baseline run
    and ~1e-5 in another, four orders of magnitude apart, both used as kill-grounds).
    It is GONE. The constant-guard works.

  alt5 (k=4) — four distinct real mechanisms, and several survived SPECIFICALLY because
    of the new addressable_notes channel. They carried caveats like "parameter range
    needs empirical calibration" that under the old boolean would have been forced to
    fundamental_flaw=true and killed. The full mechanism, visible working in the data.

  same1's lone survivor is CORRECT behavior — a genuinely hard domain where only one
    hypothesis was structurally sound. k=1 there is honesty, not starvation.

## VERDICT
PASS with disclosed caveats. Both criteria met: starvation eliminated + remaining
kills verified fundamental. Caveats: 8/10 comparability (arXiv ate 2); behavior is
"reliably ≥1, frequently ≥2, occasionally ceiling-4," not clean always-≥2.

## THE THREE CLAIMS THIS SESSION ESTABLISHED FOR THE PAPER
  1. STRUCTURED DISPOSITION BEATS INSTRUCTION. The reviewer was already told not to
     kill on addressable flaws and ignored it — until given a structured field to act
     through. "Give the model a data channel," not "write a better prompt." The recon
     that discovered the instruction already existed is what makes this claim rigorous
     — we can show the prompt-only version failing and the structured version working.
  2. HALLUCINATED-CONSTANT KILLS ARE REAL AND CATCHABLE. A retrieval-free reviewer
     asserting made-up numbers as authority (Moffatt 0.036 vs 1e-5) is a specific,
     demonstrable failure mode, and forbidding ungrounded-numeric kills measurably
     changed outcomes. Ties to the paper's unreliable-source-literature limitation.
  3. EMERGENT OVER-SPECIFICATION. Models invent unsupported numbers even when never
     asked. Relevant to any "grounded generation" claim.

## CARRIED FORWARD
  17-fix-B (commit cfa767e, fixB worktree branch, NOT on main): S2 zero-hit fix +
  keyed-free OpenAlex hard-required grounding (fixes the arXiv-429 slot-loss).
  Owes: merge to main, own witnessed kill-rate run, live S2 re-probe. OpenAlex key
  in gitignored .env, env var OPENALEX_API_KEY, in both checkouts.

---
## RECORD CORRECTION — appended at file creation, 2026-07-10
This file was reconstructed on 2026-07-10 from the strategist's retained copy. The
17-fix-A close session wrote its milestone entry to memory/journal.jsonl but never
wrote this doc to disk; the absence was discovered during the 17-fix-B merge preflight.
Two corrections against the original text:
1. The header originally read "closed at commit 8fdef41" — a narrated hash that does
   not exist as a git object in this repo (cat-file exit 128; main's reflog shows
   plain commits only — no amend, reset, or rebase). The true close commit is 6e4796b,
   corrected in the header above. The baseline hash a4dd853 was verified real.
2. The CARRIED FORWARD section ("NOT on main") was true at close time and is preserved
   as written. As of 2026-07-10, 17-fix-B (cfa767e) has been merged to main as fc0c6b7
   (true merge, parents 6e4796b + cfa767e; the journal.jsonl conflict resolved by
   byte-exact union of both sides in timestamp order, 66 lines). 17-fix-B still owes
   its witnessed kill-rate run and its live S2 re-probe.
Standing rule adopted from this incident: no hash enters any record except pasted
from raw git output.
