# Bio-substrate status archive (moved out of CLAUDE.md, 2026-07-21)

These two status blocks were lifted verbatim out of CLAUDE.md's "Current status"
tail so they are **not loaded into every session's context**. Nothing was
deleted or changed — this is the full, unedited record of the bio-substrate
promotions. CLAUDE.md carries a one-line pointer here. The bio wrappers,
contracts, onboarding modules, and tests are all untouched and fully wired.

---

BIO Wave D.4 PROMOTION COMPLETE (2026-07-19, flip commit 5bc037c; era-of-
record ADVANCES 6befb63 -> 5bc037c): rdkit + cobrapy + mafft flipped
routable=False->True AND maturity=CALIBRATING->MATURE together — the FIRST
mature substrates, so an in-envelope trust verdict routed to them finally
STANDS (the maturity hook no longer names them; the old five stay
non-mature and still gate every trust decision on their account). Routable
5->8, mature 0->3, enrollment 19. Owner-ruled on the calibration evidence:
rdkit + mafft CLEAN at N=3 (in-envelope 30/30 trust, out 30/30 defer);
cobrapy on the N=7 wash-out (calibration_cobrapy_20260719T052035Z.json:
in-envelope 34 trust / 1 refine — the lone G02/iML1515 refine, 1 of 7 draws;
out 35/35 defer — the D.3 split WASHED OUT). Six runtime surfaces wired per
substrate, one source each (never a pasted copy): (1) CONTRACT graduated to
substrates.py (RDKIT_DESCRIPTOR_CONTRACT/COBRAPY_FBA_CONTRACT/MAFFT_CONTRACT),
re-exported by the onboarding module (the ngspice R2-flip precedent), wired
into registry _CONTRACTS; (2) SIGNATURE = each wrapper's _REQUIRED_FIELDS;
(3) VOCAB = FixedSummaryVocab over each wrapper's QOI_FIELDS with three new
single-{notes} regime shapes (descriptor_computation/fba_steady_state/
msa_alignment); (4) stage2_spec._validate_regime dispatch for the three new
shapes; (5) DISPATCH = a NEW fixed-summary THREADED adapter — these wrappers
take the QoI selector `quantity` as a typed input and return a SCALAR qoi
(the ngspice execution shape, NOT the cantilevers' dict-of-numbers), so the
adapter threads the translated quantity into the wrapper input and the run
entry reuses ngspice_run_entry (byte-identical summary shape); (6) registry
ROW flip. Proofs (tests/test_d4_bio_promotion.py, 22 tests, call-free): (a)
NO new R-B-1 tie — each bio spec routes uniquely, the shared 'quantity'
signature key is a superset never a declared param (a bare quantity-only spec
loud-stops); (b) both growing fixtures re-captured ADDITIVE-ONLY
(feasibility_nudge.txt five->eight blocks, chooser_retry_user_turn_v235.txt
five->eight ids; pre-D.4 originals preserved append-only as *_pred4); (c)
cavity byte-identical (frozen anchor test_d0_stage5_input green); (d)
acceptance #6 — a trust verdict never names a promoted MATURE substrate in
the maturity-hook signoff. Full suite 89/89 test files green; FAST GREEN
(hard-gate 3/3, ledger 0/0, rejects 0/6; the case-13 refine->trust watch
miss is warn-only and pre-existing). homology_search HELD from this wave: a
separate G03/G05 card fix (calibration_cases_homology_search.json — G03/G05
reframed strictly as similarity-significance, matching the clean G01/G02/G04,
pre-registered trust labels intact) + an owner re-run, no gate change. The 8
DEFERRED bio tools are untouched. repo_facts §8 RE-STAMPED (the once-after-D.4
re-stamp the D.2/D.3 notes deferred): routable 5->8, mature 0->3, enrollment
19, era 6befb63->5bc037c.

BIO Wave D.4 PROMOTION #2 COMPLETE (2026-07-19, flip commit 3ee3873; era
ADVANCES 5bc037c -> 3ee3873): homology_search — HELD from the first merge for
the G03/G05 card fix — PROMOTED on the trust-dominant N=7 re-run
(calibration_homology_search_20260719T071928Z.json: in-envelope 30 trust / 5
refine / 0 defer, EVERY in-envelope case MODAL TRUST; out 35/35 defer). The 5
residual in-envelope refines are STRUCTURAL trust-with-caveat texture
(e_value=significance sits one careful step from the homology C1-hole), NOT
miscalibration — G01/G02 deliberately NOT reworded further. routable=True AND
maturity=MATURE flipped together — the FOURTH and LAST mature substrate this
environment supports. Routable 8->9, mature 3->4
(rdkit/cobrapy/mafft/homology_search). Same six-surface recipe, one source
each; homology_search is fixed-summary shaped like the trio (`quantity`=
"e_value" threaded into the wrapper input, the min-reduction done internally —
so FixedSummaryVocab, NOT the earlier staging note's NamedQuantityVocab), with
signature {database, query, tool, quantity} (the three content keys unique to
it -> unique routing) and a new HomologySearchRegime. ITS ONE DIFFERENCE: a
THREE-state wrapper summary — valid=False (could-not-run), valid=True/qoi=e_value
(a hit), valid=True/qoi=None (a CLEAN NO-HIT, a real 'no homolog at cutoff') —
handled by a dedicated homology_search_run_entry that maps the no-hit to
converged=True + qoi_error (the honest line), NEVER a fabricated 0. Proofs
(tests/test_d4_bio_promotion.py, now 27 tests): the FOUR-tool R-B-1 re-proof (a
bare quantity-only spec now loud-stops naming all four mature bio substrates;
homology routes uniquely on {database,query,tool}); growing fixtures
additive-only again (feasibility_nudge 8->9 blocks, chooser 8->9 ids, in
enrollment order before mafft; 8-routable state preserved as *_pred4hs); cavity
byte-identical; acceptance #6; the three-state run entry incl. schema-validity
and the broken-contract fail-loud guard. Full suite 89/89 files green; FAST
GREEN. repo_facts §2/§8 RE-STAMPED (routable 8->9, mature 3->4, era
5bc037c->3ee3873). FINAL bio state: 4 live-and-mature (rdkit, cobrapy, mafft,
homology_search), 8 deferred/parked unchanged.
