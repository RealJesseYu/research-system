"""registry_row_fragment.py — STAGED. The Wave Guide merges this; nothing
imports it today.

LANDS IN: tools/substrate_registry.py, inside the _REGISTRY tuple, appended
AFTER the code_sklearn_eval row and BEFORE the web_search row (web_search sits
last because it is outside the routable ladder; enrollment order is preserved by
all_substrates() and is asserted by a test — see MERGE_NOTES.md).

    SubstrateRecord(
        substrate_id="ngspice_linear_passive",
        wrapper="tools/run_ngspice.py",
        card_path="docs/envelope_card_ngspice_linear_passive.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="battery assembled (15 cases), unexecuted — owner-OK'd slot pending",
    ),

=============================================================================
THE PROMPT SAID TO ADD A _CONTRACTS ENTRY. DO NOT. THE TESTS PROVE IT WRONG.
=============================================================================

The session-2 brief asked for the contract to be "imported as a CONSTANT (the
registry's _CONTRACTS map imports it — mirror how cavity's row does it)".
Mirroring cavity is exactly the wrong precedent, and following it would turn a
green suite red:

  tests/test_contract_registry.py::
      test_never_falls_back_to_cavity_for_a_contractless_substrate
  derives `contractless` as EVERY enrolled substrate except cavity_2d_cfd and
  asserts contract_for(sid) RAISES for each one. Adding ngspice to _CONTRACTS
  would make contract_for("ngspice_linear_passive") RETURN instead of raise, and
  that test fails.

Cavity is the wrong model because cavity is PROVISIONAL and ROUTABLE. The right
precedent is the two substrates that are actually at this rung — FEA and code —
and substrate_registry.py's own module comment is explicit about them:

    "Enrolling FEA/code here is a SEPARATE future ruling (they are unroutable
     and uncalibrated today) — their absence from this map is deliberate, not an
     oversight, and is the fail-loud escape the Part-A tests prove."

So this fragment is a ROW ONLY. ngspice enters at `calibrating` / unroutable,
with NO _CONTRACTS entry, exactly like FEA and code. contract_for(
"ngspice_linear_passive") must RAISE LookupError until a recorded ruling makes
this substrate routable — that raise IS the invariant, not a gap to fill.

WHEN THE _CONTRACTS ENTRY LANDS (a later, separate ruling — not this merge):
add, alongside promoting `routable`,

    from substrates import NGSPICE_LINEAR_PASSIVE_CONTRACT   # at the imports
    ...
    _CONTRACTS: dict[str, str] = {
        "cavity_2d_cfd": CAVITY_2D_CONTRACT,
        "ngspice_linear_passive": NGSPICE_LINEAR_PASSIVE_CONTRACT,
    }

and note that sole_routable_id() RAISES the moment a second substrate becomes
routable — by design, because multi-substrate node selection (Step 35, task
typing) does not exist. That raise is the seam naming the missing work; it is
not a bug to route around.

WHICH CONSTANT. When it lands, the value must be the IMPORTED
NGSPICE_LINEAR_PASSIVE_CONTRACT object (the ~10.2k five-section runtime
contract), never a pasted copy and never the battery's 700-char
NGSPICE_LINEAR_PASSIVE_SUBSTRATE_TEXT. Those are two different artifacts with
two different readers — see contract.py's module docstring.
"""

# Nothing executable. This file is a staged note, not a module to import.
# The registry is plain Python data edited under a recorded ruling, by hand,
# by a human — never assembled at runtime from a fragment like this one.
