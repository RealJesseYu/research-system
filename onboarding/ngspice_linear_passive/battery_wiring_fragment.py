"""battery_wiring_fragment.py — STAGED. NOT in the session brief's fragment
list; added because without it the calibration battery cannot run this slate at
all, and shipping a 15-case file that no driver can load would be a silent
no-op.

LANDS IN: harness/calibration_battery.py, two places.

WHY IT IS NEEDED
=============================================================================
harness/calibration_cases_ngspice_linear_passive.json now exists, but
`calibration_battery` is keyed by an explicit allowlist and knows nothing about
it. Both of these RAISE today:

    load_cases("ngspice_linear_passive")
        -> KeyError: unknown substrate 'ngspice_linear_passive';
           known: ['calculix_cantilever_fea', 'code_sklearn_eval']

    _wrapper_validator("ngspice_linear_passive")
        -> KeyError: no wrapper validator wired for substrate
           'ngspice_linear_passive'

That is the driver behaving correctly — an unenrolled substrate is never
silently treated as anything — but it means the battery is un-runnable for
ngspice until these two edits land. They are the merge's actual blocker.

=============================================================================
EDIT 1 — the case-file allowlist (calibration_battery.py, ~line 88)
=============================================================================

    _CASE_FILES = {
        "calculix_cantilever_fea": "calibration_cases_fea.json",
        "code_sklearn_eval": "calibration_cases_code.json",
        "ngspice_linear_passive": "calibration_cases_ngspice_linear_passive.json",
    }

=============================================================================
EDIT 2 — the wrapper validator (calibration_battery.py, ~line 129)
=============================================================================
Inside _wrapper_validator, before the terminal `raise KeyError`:

    if substrate_id == "ngspice_linear_passive":
        from tools.run_ngspice import NgspiceInputError, _validate_input

        return _validate_input, NgspiceInputError

The import stays INSIDE the function, matching the two siblings: the battery
must not import every wrapper at module load.

NOTE THE PRIVATE NAME. `_validate_input` is underscore-prefixed, exactly like
run_fea's `_validate_input` (run_code exposes a public `validate_spec`). The
battery already reaches for the FEA private name, so this follows the
established precedent rather than inventing a new public alias — but it is worth
one line in the review: this is the second consumer of that private, and if a
third appears the wrappers should probably grow a public validator name.

=============================================================================
WHAT THE WRAPPER TRACK DOES AND DOES NOT COVER — read before scoring
=============================================================================
run_wrapper_case calls the validator ONLY ("No model, no container"). For
ngspice that means the five wrapper cases exercise the five PRE-SOLVE layers
(dot-line, value, arity, typed-field, letter) and nothing else. The substrate's
POST-SOLVE defense — the log-marker scan that catches a floating node ngspice
reports a fabricated voltage for and exits 0 on — is unreachable from this
harness by construction. It is proven in selfcheck_evidence.json (adversarial
probe `floating node (no DC path)`) and in
tests/test_run_ngspice.py::TestMarkerScanLayerIsWhereTheFloatingNodeIsCaught.
The slate's W01 was amended off that case by owner ruling for exactly this
reason (2026-07-16). A future battery track that actually solves would be the
place to cover it; none is proposed here.

=============================================================================
TESTS THAT MUST BE UPDATED IN THE SAME COMMIT
=============================================================================
Adding to _CASE_FILES widens two loops that iterate the known substrates.
Neither is a failure — both are deliberate coverage that must be extended:

  tests/test_calibration_battery.py::TestCaseFileIntegrity
      `for sid in (FEA, CODE)` — add ngspice, or the new slate is not covered
      by test_acceptable_labels_are_vocabulary / the RULE-1 leak check /
      test_answer_key_blocklist_covers_every_hidden_gate_field.

      (Until then, tests/test_calibration_cases_ngspice.py runs the identical
      derivations against this slate directly, so the coverage is not missing —
      just housed separately. Fold it in at merge and delete the duplication.)

  tests/test_calibration_battery.py::test_*_wrapper_cases_reject_as_registered
      the FEA and code versions are per-substrate; add the ngspice twin, or
      reuse tests/test_calibration_cases_ngspice.py::
      TestWrapperCasesRejectAtTheirRegisteredLayer, which already asserts the
      LAYER per case and proves zero overlap by failing the escape.

=============================================================================
WHAT THIS FRAGMENT DOES **NOT** AUTHORIZE
=============================================================================
Wiring the battery is NOT registration and NOT routing. After both edits:
  - registry maturity stays `calibrating`, routable stays False;
  - contract_for("ngspice_linear_passive") still RAISES (no _CONTRACTS entry —
    see registry_row_fragment.py);
  - the battery still needs an owner-OK'd run slot before it costs a single
    model call.
The battery reads its OWN case file and calls the Stage-3 gate directly; it
never consults _CONTRACTS. So these two edits make the slate runnable and
change nothing about what the pipeline may route to.
"""

# Nothing executable. Staged note only — the allowlist is hand-edited under a
# recorded ruling, never assembled at runtime.
