"""
substrate_dispatch.py — D.4: per-substrate execution dispatch for stage 4,
retiring stage4_simulation's hardcoded run_cfd call.

THE WRAPPER BINDING IS THE REGISTRY'S — NEVER A SECOND TABLE. Each registry
row's `wrapper` field is a repo-relative module path ('tools/run_cfd.py')
whose stem names the module's entry-point function (run_cfd, run_ngspice,
run_fea, ... — the convention every enrolled wrapper follows, web_search_stub
included). wrapper_callable() resolves the callable FROM that field, at call
time; an id -> wrapper-function map here would be a forbidden second copy of
the binding the registry row already owns.

ADAPTERS ARE TRANSLATION GLUE, wired like _CONTRACTS (registry), _SIGNATURES
(selection) and _VOCABS (qoi_vocab): cavity ALONE in production; absence is
deliberate (an adapter is wired alongside a routability ruling, never
before); adapter_for fails loud (LookupError) on an unwired id and
KeyError-first on an unknown id (via registry.get). NEVER a cavity fallback:
a substrate stage 4 has no adapter for is refused at dispatch, not executed
down the wrong path.

An adapter's D.4 job is INPUT + QoI translation ONLY (repo_facts §10.5
(i)+(ii)): map one mini-run's spec params to the wrapper's own typed input,
and hand on the substrate's translated QoI request. Return-shape adaptation
(§10.5 (iii)) is D.5's material and is deliberately NOT built here — a
non-cavity adapter returns its wrapper summary VERBATIM, and mapping
valid -> converged anywhere would be dishonest (repo_facts §10.6: `valid`
means "ran and parsed", exactly what the cavity contract says converged is
not).

The ngspice adapter is DEFINED here but NOT registered — the run_ngspice
precedent (built, unregistered): tests register it on a constructed
registry; promotion adds the _ADAPTERS entry under a recorded ruling.

UNIFORM ADAPTER SIGNATURE:
    adapter(substrate_id, params, case_name, roles, qoi_request) -> summary
where qoi_request is the SUBSTRATE'S OWN translated request — cavity: the
field-reduction request from stage4_simulation.translate_qoi; ngspice: the
named-quantity request from ngspice_qoi_request below.
"""

from __future__ import annotations

import importlib
from pathlib import PurePosixPath

from stages import stage4_case_builder
from tools import substrate_registry as registry
from tools.run_ngspice import _REQUIRED_FIELDS, _REQUIRED_QOI_FIELDS

# The wrapper input fields one mini-run's params must supply for ngspice:
# the wrapper's own required-field set (imported, never copied) minus 'qoi',
# the one field filled by the spec's translated QoI request instead.
_NGSPICE_INPUT_KEYS = tuple(k for k in _REQUIRED_FIELDS if k != "qoi")


def wrapper_callable(substrate_id: str):
    """Resolve one substrate's wrapper entry point FROM the registry row's
    `wrapper` field, at call time — never a second wrapper table. An unknown
    id raises KeyError first (via registry.get); a wrapper module that breaks
    the stem-names-the-entry-point convention raises LookupError rather than
    guess a callable."""
    record = registry.get(substrate_id)  # KeyError on an unknown id — never silent
    path = PurePosixPath(record.wrapper)
    module = importlib.import_module(".".join(path.with_suffix("").parts))
    fn = getattr(module, path.stem, None)
    if fn is None:
        raise LookupError(
            f"registry wrapper {record.wrapper!r} for substrate "
            f"{substrate_id!r} defines no entry-point function {path.stem!r} "
            "— the stem-names-the-entry-point convention is broken; fix the "
            "wrapper or the registry row, never guess a callable."
        )
    return fn


def _cavity_adapter(substrate_id, params, case_name, roles, qoi_request):
    """Field-reduction (cavity-class) execution: synthesize the case via the
    builder, then the IDENTICAL wrapper call stage 4 has always made —
    (case_name, qoi_request=...). Late-bound on purpose (builder as a module
    attribute, wrapper resolved at call time) so the seams stay patchable and
    single-sourced. CaseSynthesisError propagates to stage 4's honest
    halted_synthesis path, exactly as before D.4."""
    stage4_case_builder.build_case(params, case_name, roles=roles)
    return wrapper_callable(substrate_id)(case_name, qoi_request=qoi_request)


def ngspice_qoi_request(spec_qoi) -> dict:
    """Translate a spec's NAMED-QUANTITY QoI object into run_ngspice's typed
    qoi dict {kind, target, reduction[, at]} — the key set is the wrapper's
    own _REQUIRED_QOI_FIELDS, imported, never copied. FAIL LOUD on anything
    untranslatable, naming every missing key — never a silent drop or a
    default. Content validation (kinds / reductions / the target-name
    grammar) is the wrapper's own _validate_qoi, the single source — it is
    deliberately not re-implemented here."""
    if not isinstance(spec_qoi, dict):
        raise ValueError(
            f"cannot translate QoI: spec qoi must be an object, got "
            f"{type(spec_qoi).__name__} — refusing to invent a request"
        )
    missing = [k for k in _REQUIRED_QOI_FIELDS if k not in spec_qoi]
    if missing:
        raise ValueError(
            "cannot translate QoI: spec qoi carries no machine-readable "
            f"{', '.join(missing)} key(s) — a named-quantity request "
            f"requires exactly {', '.join(_REQUIRED_QOI_FIELDS)} (plus 'at' "
            "for value_at reductions); free-text definitions are not "
            "translated"
        )
    request = {k: spec_qoi[k] for k in _REQUIRED_QOI_FIELDS}
    if spec_qoi.get("at") is not None:
        request["at"] = spec_qoi["at"]
    return request


def _ngspice_adapter(substrate_id, params, case_name, roles, qoi_request):
    """NAMED-QUANTITY (ngspice-class) execution adapter — INPUT + QoI ONLY
    (D.4). NOT in _ADAPTERS: tests register it on a constructed registry;
    promotion is a recorded ruling. case_name and roles are cavity-class
    concepts (the wrapper composes its own deck in its own job dir, and a
    derived spec parameter would already fail the strict key check below) —
    accepted for the uniform adapter signature, unused.

    Builds run_ngspice's typed input {netlist_body, analysis, qoi} from one
    mini-run's params plus the substrate's translated QoI request, failing
    loud (ValueError naming every offender) on anything untranslatable —
    never a silent drop or default. Returns the wrapper summary VERBATIM:
    entry construction for the {valid, qoi, diagnostics, runtime_s} shape is
    D.5's material, and a valid -> converged mapping here would be dishonest
    (repo_facts §10.6)."""
    if not isinstance(params, dict):
        raise ValueError(
            f"cannot translate mini-run params: expected an object, got "
            f"{type(params).__name__}"
        )
    unknown = sorted(set(params) - set(_NGSPICE_INPUT_KEYS))
    missing = [k for k in _NGSPICE_INPUT_KEYS if k not in params]
    if unknown or missing:
        offenses = []
        if unknown:
            offenses.append(
                f"unknown key(s) {', '.join(unknown)} (the wrapper input "
                f"takes exactly {', '.join(_NGSPICE_INPUT_KEYS)})"
            )
        if missing:
            offenses.append(f"missing required key(s) {', '.join(missing)}")
        raise ValueError(
            "cannot translate mini-run params to the ngspice typed input: "
            + "; ".join(offenses)
        )
    if not isinstance(qoi_request, dict):
        raise ValueError(
            "no translated named-quantity qoi_request — ngspice execution "
            "requires one (translate the spec qoi via ngspice_qoi_request); "
            "refusing to invent a default"
        )
    typed = {
        k: (qoi_request if k == "qoi" else params[k]) for k in _REQUIRED_FIELDS
    }
    return wrapper_callable(substrate_id)(typed)


# substrate_id -> its execution adapter. cavity ALONE in production,
# mirroring _CONTRACTS (registry), _SIGNATURES (selection) and _VOCABS
# (qoi_vocab): absence is deliberate, wired only alongside a routability
# ruling. The ngspice adapter above exists but is NOT registered.
_ADAPTERS: dict = {
    "cavity_2d_cfd": _cavity_adapter,
}


def adapter_for(substrate_id: str):
    """The execution adapter for one substrate, read STRUCTURALLY from this
    map keyed by substrate_id (R-28H-1: never parsed from a payload name).
    FAIL LOUD (contract_for's style): a substrate with no wired adapter
    raises LookupError — stage 4 must NOT fall back to the cavity execution
    path for a substrate that has none. An unknown id raises KeyError first
    (via registry.get) — an unenrolled substrate is never silently treated
    as anything."""
    record = registry.get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _ADAPTERS[substrate_id]
    except KeyError:
        raise LookupError(
            f"no execution adapter wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "stage 4 must NOT fall back to the cavity execution path — wire "
            "an adapter in tools/substrate_dispatch.py from the substrate's "
            "own wrapper vocabulary under a recorded ruling before routing "
            "execution to this substrate."
        )
