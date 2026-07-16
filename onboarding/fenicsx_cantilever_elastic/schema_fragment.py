"""schema_fragment.py — the STAGED Stage-2 spec-schema extension.

STAGING ONLY — THIS SESSION DOES NOT MERGE. `stages/stage2_spec.py` is frozen to
this build (and everything in `stages/` is frozen to this wave). This fragment
records the canonical vocabulary Stage 2 would have to learn for a model to
author a spec against this substrate, written against the schema code as it
actually is (read at HEAD 07816ba).

HOW STAGE 2 ACTUALLY CONSUMES A VOCABULARY (read, not assumed):
  * `validate_spec` checks a `parameters` LIST of objects, each with `name`,
    `units`, and a `role` in {"sweep", "fixed", "derived"}; sweeps carry
    numeric min/max, fixed carry a numeric `value`, derived carry a non-empty
    decomposition statement.
  * Unknown parameter names inside `mini_experiment` runs are flagged against
    "the declared parameter names" — i.e. Stage 2 validates a spec's INTERNAL
    consistency. The SUBSTRATE's canonical vocabulary is enforced further down,
    at the wrapper's own typed input (`run_fenicsx._validate_input`), which
    rejects unknown fields BY NAME.
  * Machine-readable QoI keys are validated against the wrapper's own
    vocabularies, never parsed from free text.

THE HONEST STATUS — and why this fragment stays a fragment:

This substrate is UNREGISTERED and UNROUTABLE. Nothing in `stages/` imports
`tools/run_fenicsx.py`, no spec can name it, and `contract_for` raises for it by
design. There is therefore NO live consumer for this fragment, and wiring one is
a separate future ruling — the same standing position the FEA and code substrates
hold. This file exists so the vocabulary is recorded ONCE, beside the contract it
comes from, rather than re-derived at merge time.

THE ONE THING A FUTURE WIRING MUST NOT GET WRONG:

`element_degree` is NOT an ordinary numeric parameter. It is a REGIME BOUNDARY
(envelope card ruling G5). A spec that sweeps it, or that omits it and lets some
default fill in, is not expressing a preference — it is silently choosing between
a trustworthy number and a confident wrong one (measured: degree 1 returns 0.28x
the closed-form deflection at mesh_density 8 and is still 5.5% too stiff at
mesh_density 64, while degree 2 is within 1.31% at mesh_density 8). The wrapper
therefore REQUIRES it explicitly with no default: an omitted `element_degree` is
a named rejection, never a guess. Any Stage-2 wiring must preserve that: the
field is required, and its value is the fidelity gate's business.
"""

from __future__ import annotations

# The canonical parameter vocabulary, as DATA. Mirrors
# tools.run_fenicsx._REQUIRED_FIELDS exactly; a test asserts they cannot drift
# apart (tests/test_run_fenicsx.py pins the wrapper side).
CANONICAL_PARAMETERS = (
    {"name": "length", "units": "m",
     "meaning": "beam length, spanning X; clamped at x=0", "rule": "> 0"},
    {"name": "width", "units": "m",
     "meaning": "section width, spanning Y", "rule": "> 0"},
    {"name": "height", "units": "m",
     "meaning": "section height, spanning Z; the load direction", "rule": "> 0"},
    {"name": "E", "units": "Pa",
     "meaning": "Young's modulus", "rule": "> 0"},
    {"name": "nu", "units": "-",
     "meaning": "Poisson's ratio", "rule": "in (-1, 0.5)"},
    {"name": "tip_load", "units": "N",
     "meaning": "total transverse load at x=length in -Z, distributed over the tip face",
     "rule": "> 0"},
    {"name": "mesh_density", "units": "int",
     "meaning": "hex element count along the length; width/height counts scale by aspect ratio",
     "rule": ">= 1"},
    {"name": "element_degree", "units": "int",
     "meaning": ("Lagrange polynomial degree. A REGIME BOUNDARY, not a preference "
                 "(card ruling G5): >= 1 accepted, >= 2 validated. Required; no default."),
     "rule": ">= 1 (typed); >= 2 (validated — the gate's judgment, not the wrapper's)"},
)

# The QoI keys the wrapper actually returns. Both come from every valid run; this
# family has no per-run QoI selection (contrast cavity_2d's requestable single QoI).
QOI_KEYS = (
    {"name": "tip_displacement", "units": "m",
     "status": "VALIDATED within family v1 at element_degree >= 2 (card §3A)"},
    {"name": "max_von_mises", "units": "Pa",
     "status": "REPORTED-ONLY, not validated (card ruling G4)"},
)

# No live consumer today — see the module docstring. Wiring is a separate ruling.
WIRED = False
