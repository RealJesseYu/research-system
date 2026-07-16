"""battery_wiring.py — the STAGED harness/calibration_battery.py amendments.

STAGING ONLY — THIS SESSION DOES NOT MERGE. `harness/calibration_battery.py` is
frozen to this build. These are the three edits the Wave Guide must make for the
battery to be able to run this substrate's case file, written against the battery
code as it actually is (read at HEAD 07816ba).

*** MERGE BLOCKER — READ ITEM 2 FIRST. It is a SAFETY amendment, not a
    convenience, and without it the merged tree FAILS its own drift guard. ***

--------------------------------------------------------------------------------
1. `_CASE_FILES` — teach the battery this substrate's case file.

    _CASE_FILES = {
        "calculix_cantilever_fea": "calibration_cases_fea.json",
        "code_sklearn_eval": "calibration_cases_code.json",
        "fenicsx_cantilever_elastic": "calibration_cases_fenicsx_cantilever_elastic.json",
    }

   This dict is also the `--substrate` argparse `choices` (it is passed as
   `sorted(_CASE_FILES)`), so this one edit both loads the file and exposes the
   CLI flag. Nothing else is needed for
   `--mode calibration --substrate fenicsx_cantilever_elastic` to resolve.

--------------------------------------------------------------------------------
2. `_ANSWER_KEY_KEYS` — REQUIRED. Two new names.  *** MERGE BLOCKER ***

    _ANSWER_KEY_KEYS = ("expected_class", "acceptable_labels", "note",
                        "right_instrument", "label_provenance", "label_rationale")

   WHY THIS IS NOT OPTIONAL, in two parts:

   (a) SAFETY. `label_rationale` states WHY a case carries the label it carries
       ("G5 excludes trust for degree < 2 ... a 'trust' draw here is the
       dangerous false-trust error"). That is answer key in its purest form. It
       must never reach the model. `run_gate_case` copies only `id` and
       `experiment` into `stage_input`, so it does not leak TODAY — but
       `_assert_no_answer_key_leak` is the defense-in-depth scan that catches a
       future change to that construction, and a scan that does not know a key's
       name cannot catch it. The tripwire must know the name to be a tripwire.

   (b) THE FROZEN DRIFT GUARD WILL FAIL WITHOUT IT.
       `tests/test_calibration_battery.py::test_answer_key_blocklist_covers_every
       _hidden_gate_field` derives, per gate case, `hidden = set(case) -
       {"id", "experiment"}` and asserts `hidden - set(_ANSWER_KEY_KEYS) == set()`.
       Every case on this slate carries `label_provenance` and `label_rationale`
       (the wave packet REQUIRES them on every label), so the moment this
       substrate's id is added to that test's `for sid in (...)` tuple, the guard
       fails on all 10 gate cases until this amendment lands. The guard is
       working exactly as designed — it is refusing to let a hidden field drift
       out of coverage. Do not delete the fields to satisfy it; add them here.

   `_MODEL_VISIBLE_GATE_FIELDS` needs NO change: `id` and `experiment` remain the
   only model-visible fields, and this slate adds none.

--------------------------------------------------------------------------------
3. `_wrapper_validator` — the substrate's OWN validator, imported and called.

    if substrate_id == "fenicsx_cantilever_elastic":
        from tools.run_fenicsx import FenicsxInputError, _validate_input

        return _validate_input, FenicsxInputError

   Mirrors the existing FEA/code branches exactly: the wrapper is imported and
   called, never modified, and the wrapper track needs no docker (X11-X15 all
   reject at `_validate_input` before any container call).

--------------------------------------------------------------------------------
4. `tests/test_calibration_battery.py` — add the id to the two suite-wide loops
   (`test_acceptable_labels_are_vocabulary`, and the drift guard in item 2). A
   composition test mirroring `test_fea_composition` (gate 10 = in 5 / out 5,
   wrapper 5) already exists in `tests/test_run_fenicsx.py::TestCaseFileGeneration`
   and need not be duplicated.

--------------------------------------------------------------------------------
5. THE PROOFS (Wave Guide merge condition, 2026-07-16). Both live in
   `tests/test_run_fenicsx.py` — NOT in this file — because a proof that does not
   run in the suite is a claim, not a proof; `onboarding/` is not collected by
   `pytest tests/`. They SIMULATE the patched state by substituting the blocklist
   on the real, imported `harness.calibration_battery`, since it is frozen here.
   At merge they should move to `tests/test_calibration_battery.py` beside the
   guard they defend.

   THE FAILING ESCAPE — `TestStagedBatteryWiring`:
     * `test_escape_succeeds_unpatched_then_guard_trips_patched` — takes X06's
       REAL label_rationale, MUTATES it, drifts it into a model input, and
       exercises BOTH states: UNPATCHED the escape SUCCEEDS (no raise — the gap
       is real, not hypothetical); PATCHED the guard TRIPS, naming
       `label_rationale` and the case id. A guard shown only to pass under the
       patch would prove nothing.
     * `test_patched_guard_trips_on_each_new_field_individually` — both added
       names caught alone, not merely as a pair.
     * `test_patched_guard_still_passes_a_clean_input` — the patched guard does
       NOT fire on the real construction path (a tripwire that trips on
       everything is also not a proof).
     * `test_merge_blocker_is_real_and_the_amendment_resolves_it` — runs the
       frozen drift guard's OWN derivation against this slate: UNPATCHED it fails
       on all 10 gate cases (the blocker is real); PATCHED it passes on all 10
       (the amendment is sufficient, and no further name is needed).

   THE OLD-PATH PROPERTY — `TestOldPathUnchangedByThePatch`:
     * `test_fea_and_code_prompts_are_byte_identical_before_and_after` — runs the
       REAL `run_gate_case` construction over ALL 21 existing gate cases (FEA 10 +
       code 11) with only the model call stubbed, under both blocklists, and
       asserts the serialized `stage_input`s are byte-identical case for case.
     * `test_the_two_new_names_raise_no_false_positive_on_the_old_slates` — the
       ONLY way this patch could break the old path: if FEA's or code's prompt
       text already contained the literal `"label_rationale"`, the patched guard
       would abort a battery that works today. Proven it does not.

   HONEST NOTE on discriminating power: the byte-identity half is structural —
   construction never reads the blocklist, so equality is close to tautological.
   Its teeth are in the raise: a false-positive blocklist would abort inside the
   comparison run. The false-positive test is the independent check.

--------------------------------------------------------------------------------
NOT REQUESTED, deliberately: no `_CONTRACTS` entry (see registry_row.py), no
maturity promotion, and no battery EXECUTION. The battery spends real Opus calls
and must be launched from a plain Terminal under caffeinate per the run-venue
rule — never from a builder-session background task. The slate itself is an OWNER
RULING first (precedent R-CAL-2).
"""

from __future__ import annotations

# The amendments as DATA, so a merge can assert against them rather than re-type.
CASE_FILES_ENTRY = {
    "fenicsx_cantilever_elastic": "calibration_cases_fenicsx_cantilever_elastic.json",
}

# The two names that MUST join _ANSWER_KEY_KEYS. See item 2 — merge blocker.
ANSWER_KEY_KEYS_ADDITIONS = ("label_provenance", "label_rationale")

WRAPPER_VALIDATOR_IMPORT = (
    "from tools.run_fenicsx import FenicsxInputError, _validate_input"
)
