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

An adapter's job is INPUT + QoI translation (repo_facts §10.5 (i)+(ii), D.4):
map one mini-run's spec params to the wrapper's own typed input, and hand on
the substrate's translated QoI request. A non-cavity adapter returns its
wrapper summary VERBATIM. Return-shape adaptation (§10.5 (iii)) is D.5's:
a SEPARATE per-substrate entry constructor (ngspice_run_entry below) maps a
wrapper summary to the stage-4 conclusions-only run entry, under the R1
option-4 ruling — the per-substrate converged mapping lives in that
substrate's contract §3, and valid -> converged is honest for ngspice
precisely because §3 now states converged means completed-and-parsed there
(repo_facts §10.6). Entry construction stays OUT of the adapters so evidence
keeps the full summary; stage 4 reaches the constructor through
run_entry_constructor_for (wired at the R2 promotion flip, owner 2026-07-17,
exactly as deferred), and the spec-QoI translation through
qoi_translation_for — both keyed by the STRUCTURALLY selected substrate id,
fail-loud on an unwired one, so stage code never branches on a substrate
name.

The ngspice adapter IS registered since the R2 flip (owner, 2026-07-17) —
before it, the run_ngspice precedent held (built, unregistered; tests
registered it on a constructed registry).

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
from tools.run_scipy import (
    OP_FIELDS as _SCIPY_OP_FIELDS,
    UNIVERSAL_OPTIONAL_FIELDS as _SCIPY_UNIVERSAL_OPTIONAL_FIELDS,
    UNIVERSAL_REQUIRED_FIELDS as _SCIPY_UNIVERSAL_REQUIRED_FIELDS,
)

# The full sympy typed-key set, derived from the wrapper's own re-exported
# constants (imported, never copied) — the structural membership screen the
# sympy adapter applies before handing params to the wrapper, whose own
# validate_input remains the single source for content checks.
_SCIPY_INPUT_KEYS: tuple = tuple(
    dict.fromkeys(
        list(_SCIPY_UNIVERSAL_REQUIRED_FIELDS)
        + list(_SCIPY_UNIVERSAL_OPTIONAL_FIELDS)
        + [
            name
            for fields in _SCIPY_OP_FIELDS.values()
            for group in ("required", "optional")
            for name in fields[group]
        ]
    )
)

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
    (D.4). In _ADAPTERS since the R2 promotion flip (owner, 2026-07-17);
    before it, tests registered it on a constructed registry (the built-
    unregistered precedent). case_name and roles are cavity-class
    concepts (the wrapper composes its own deck in its own job dir, and a
    derived spec parameter would already fail the strict key check below) —
    accepted for the uniform adapter signature, unused.

    Builds run_ngspice's typed input {netlist_body, analysis, qoi} from one
    mini-run's params plus the substrate's translated QoI request, failing
    loud (ValueError naming every offender) on anything untranslatable —
    never a silent drop or default. Returns the wrapper summary VERBATIM:
    entry construction for the {valid, qoi, diagnostics, runtime_s} shape is
    ngspice_run_entry's job (D.5), kept out of the adapter so stage-4
    evidence keeps the full summary."""
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


def _sympy_adapter(substrate_id, params, case_name, roles, qoi_request):
    """SYMBOLIC-RESULT (exact-CAS class) execution adapter — INPUT ONLY
    (Packet B Phase 1 flip, owner 2026-07-17). case_name and roles are
    cavity-class concepts, accepted for the uniform adapter signature,
    unused. qoi_request is likewise unused here: this substrate's wrapper
    takes NO QoI request (the QoI IS the operation's verified result), so
    nothing from it enters the typed input.

    Structural screen only: params must be a dict whose keys are members of
    the wrapper's own typed-key set (imported above) — unknown keys fail
    loud naming every offender, mirroring the ngspice adapter. CONTENT
    validation (per-operation required fields, allowlists, the AST jail) is
    the wrapper's own validate_input, the single source: content problems
    come back as honest error-state summaries, never as adapter crashes.
    Returns the wrapper summary VERBATIM: entry construction for the
    tri-state {valid, state, result, ...} shape is sympy_run_entry's job,
    kept out of the adapter so stage-4 evidence keeps the full summary."""
    if not isinstance(params, dict):
        raise ValueError(
            f"cannot translate mini-run params: expected an object, got "
            f"{type(params).__name__}"
        )
    unknown = sorted(set(params) - set(_SCIPY_INPUT_KEYS))
    if unknown:
        raise ValueError(
            "cannot translate mini-run params to the sympy typed input: "
            f"unknown key(s) {', '.join(unknown)} (the wrapper input takes "
            f"only keys from {', '.join(_SCIPY_INPUT_KEYS)})"
        )
    return wrapper_callable(substrate_id)(dict(params))


# The run_ngspice summary key set, per the wrapper's own documented return
# shape (tools/run_ngspice.py:28: {valid, qoi, diagnostics, runtime_s}) —
# the wrapper defines no constant for it, so the contract line is the cite.
_NGSPICE_SUMMARY_KEYS = ("valid", "qoi", "diagnostics", "runtime_s")


def ngspice_run_entry(summary) -> dict:
    """D.5 (R1 option 4): one conclusions-only stage-4 run entry
    {converged, wall_clock_s, qoi_value | qoi_error} from a run_ngspice
    summary {valid, qoi, diagnostics, runtime_s}. NOT wired into stage 4 —
    the _ngspice_adapter precedent (built, unregistered): stage 4 dispatches
    entry construction per substrate at promotion (R2), never before.

    The mapping, ruled in the staged contract §3 (option 4): converged :=
    (valid is True) — for this substrate converged means COMPLETED-AND-
    PARSED, stated plainly there; wall_clock_s := runtime_s; valid=False ->
    converged=False plus qoi_error from diagnostics, NEVER a fabricated
    qoi_value. NO `state` key is wired: run_ngspice's summary carries no
    own-vocabulary state field (only the boolean valid), and inventing one
    here would fabricate vocabulary the wrapper does not emit.

    FAIL LOUD (ValueError naming every offender) on structurally missing or
    ill-typed wrapper fields — never a default: a summary that breaks the
    wrapper's own contract must not become a well-formed entry."""
    if not isinstance(summary, dict):
        raise ValueError(
            f"cannot construct a run entry: expected a run_ngspice summary "
            f"object, got {type(summary).__name__}"
        )
    missing = [k for k in _NGSPICE_SUMMARY_KEYS if k not in summary]
    if missing:
        raise ValueError(
            "cannot construct a run entry: run_ngspice summary is missing "
            f"field(s) {', '.join(missing)} — the wrapper contract is "
            f"exactly {{{', '.join(_NGSPICE_SUMMARY_KEYS)}}}; refusing to "
            "default"
        )
    valid = summary["valid"]
    if not isinstance(valid, bool):
        raise ValueError(
            f"cannot construct a run entry: summary valid must be a bool, "
            f"got {valid!r}"
        )
    runtime_s = summary["runtime_s"]
    if not isinstance(runtime_s, (int, float)) or isinstance(runtime_s, bool):
        raise ValueError(
            f"cannot construct a run entry: summary runtime_s must be a "
            f"number, got {runtime_s!r}"
        )
    entry = {"converged": valid is True, "wall_clock_s": runtime_s}
    if valid:
        qoi = summary["qoi"]
        if not isinstance(qoi, (int, float)) or isinstance(qoi, bool):
            raise ValueError(
                f"cannot construct a run entry: summary claims valid=true "
                f"but qoi is {qoi!r}, not a number — the wrapper contract "
                "says valid=true always carries one scalar; refusing to "
                "fabricate a qoi_value"
            )
        entry["qoi_value"] = qoi
    else:
        diagnostics = summary["diagnostics"]
        if not isinstance(diagnostics, str) or not diagnostics.strip():
            raise ValueError(
                f"cannot construct a run entry: summary valid=false but "
                f"diagnostics is {diagnostics!r} — a failed run must carry "
                "its named reason; refusing to invent a qoi_error"
            )
        entry["qoi_error"] = diagnostics
    return entry


# substrate_id -> its execution adapter, mirroring _CONTRACTS (registry),
# _SIGNATURES (selection) and _VOCABS (qoi_vocab): wired only alongside a
# routability ruling — ngspice entered at the R2 flip (owner, 2026-07-17);
# the still-unrouted substrates are deliberately absent.
_ADAPTERS: dict = {
    "cavity_2d_cfd": _cavity_adapter,
    "ngspice_linear_passive": _ngspice_adapter,
    # Packet B Phase 1 flip (owner, 2026-07-17)
    "sympy_symbolic_exact": _sympy_adapter,
}


# --- per-substrate spec-QoI translation (stage 4's seam, R2 flip) ----------

def _cavity_qoi_translation(spec_qoi, vocab):
    """Field-reduction translation — stage 4's own translate_qoi, LATE-BOUND
    (stages.stage4_simulation imports this module at module level; a
    top-level import back would be a cycle). Same (request, refusal) return
    shape, byte-identical behavior."""
    from stages.stage4_simulation import translate_qoi

    return translate_qoi(spec_qoi, vocab)


def _ngspice_qoi_translation(spec_qoi, vocab):
    """Named-quantity translation in stage 4's honest-refusal return shape:
    (request, None) on success, (None, reason) on anything untranslatable —
    ngspice_qoi_request's loud ValueError becomes the refusal reason, so the
    stage records an honest qoi_error path instead of crashing on QoI
    CONTENT. `vocab` is accepted for the uniform (spec_qoi, vocab) signature
    and deliberately unused: content validation is the wrapper's own
    _validate_qoi, the single source."""
    try:
        return ngspice_qoi_request(spec_qoi), None
    except ValueError as exc:
        return None, str(exc)


def _sympy_qoi_translation(spec_qoi, vocab):
    """Symbolic-result translation in stage 4's (request, refusal) shape:
    this substrate's wrapper takes NO QoI request — the QoI IS the
    operation's own verified result, extractable by construction for any
    well-formed prose QoI. The returned marker is NOT a wrapper input (the
    adapter ignores it); it exists so stage 4's None-means-unextractable
    fallback path — which would file every run under qoi_error — is never
    taken for this substrate. A non-object spec qoi is refused honestly."""
    if not isinstance(spec_qoi, dict):
        return None, (
            f"spec qoi must be an object, got {type(spec_qoi).__name__} — "
            "refusing to invent a request"
        )
    return {"symbolic_result": True}, None


_QOI_TRANSLATIONS: dict = {
    "cavity_2d_cfd": _cavity_qoi_translation,
    "ngspice_linear_passive": _ngspice_qoi_translation,
    # Packet B Phase 1 flip (owner, 2026-07-17)
    "sympy_symbolic_exact": _sympy_qoi_translation,
}


def qoi_translation_for(substrate_id: str):
    """The spec-QoI translation callable for one substrate — uniform
    signature (spec_qoi, vocab) -> (request | None, refusal | None). Read
    STRUCTURALLY from this map keyed by substrate_id (R-28H-1). FAIL LOUD
    (contract_for's style): a substrate with no wired translation raises
    LookupError; an unknown id raises KeyError first (via registry.get)."""
    registry.get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _QOI_TRANSLATIONS[substrate_id]
    except KeyError:
        record = registry.get(substrate_id)
        raise LookupError(
            f"no spec-QoI translation wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "stage 4 must NOT fall back to the cavity translation — wire an "
            "entry in tools/substrate_dispatch.py under a recorded ruling "
            "before routing execution to this substrate."
        )


# --- per-substrate conclusions-only run-entry construction (R2 flip) -------

def _cavity_run_entry(summary: dict, qoi_error_fallback: str | None) -> dict:
    """Conclusions only: {converged, qoi_value | qoi_error, wall_clock_s} —
    MOVED VERBATIM from stages.stage4_simulation._payload_run_entry at the
    R2 flip (owner, 2026-07-17); the cavity data surface is fixture-pinned
    byte-identical (tests/fixtures/d4/)."""
    entry = {
        "converged": bool(summary.get("converged")),
        "wall_clock_s": summary.get("runtime", {}).get("wall_clock_s"),
    }
    if "qoi" in summary:
        entry["qoi_value"] = summary["qoi"]["value"]
    elif "qoi_error" in summary:
        entry["qoi_error"] = summary["qoi_error"]
    elif qoi_error_fallback is not None:
        entry["qoi_error"] = qoi_error_fallback
    return entry


def _ngspice_run_entry_with_fallback(summary, qoi_error_fallback) -> dict:
    """ngspice_run_entry under the uniform (summary, qoi_error_fallback)
    constructor signature. The fallback is deliberately unused: a
    named-quantity substrate never executes without a translated QoI request
    (_ngspice_adapter refuses), so a summary always carries its own
    qoi / diagnostics truth."""
    return ngspice_run_entry(summary)


# The run_scipy summary key set, per the wrapper's own documented return
# shape (tools/run_scipy.py:56-58) — the structural fields the constructor
# reads; residual/crosscheck stay in the full summary (stage-4 evidence).
_SCIPY_SUMMARY_KEYS = ("valid", "state", "result", "reason", "diagnostics",
                       "runtime_s")

_SCIPY_STATES = ("solved_verified", "unevaluated", "error")


def sympy_run_entry(summary, qoi_error_fallback=None) -> dict:
    """Packet B Phase 1.0 ruling items 3/4 (owner, 2026-07-17): one
    conclusions-only stage-4 run entry from a run_scipy tri-state summary.
    THE TRI-STATE SURVIVES: the wrapper's state travels VERBATIM in the
    entry's optional `state` key, and no bool anywhere overwrites it.

    The mapping, stated in the graduated contract §3: converged := (valid
    is True) — completed-and-answered, true for solved_verified AND
    unevaluated (an honest non-answer is a completed answer about the
    question), false only for error. Per state:
      solved_verified -> qoi_expression carrying the exact result STRING
        (ruling item 4: never a fabricated float);
      unevaluated -> qoi_error carrying the wrapper's own honest-non-answer
        diagnostics line VERBATIM (ruling item 3: the locked schema's
        answer slot, with state beside it saying machine-readably that this
        is a decline, not a failure);
      error -> qoi_error carrying the diagnostics line (which names the
        wrapper's machine-greppable reason).

    qoi_error_fallback is accepted for the uniform constructor signature
    and deliberately unused: this substrate's summary always carries its
    own truth (the translation never refuses a well-formed prose QoI).
    FAIL LOUD (ValueError naming every offender) on structurally missing,
    ill-typed, or state-contradicting wrapper fields — never a default."""
    if not isinstance(summary, dict):
        raise ValueError(
            f"cannot construct a run entry: expected a run_scipy summary "
            f"object, got {type(summary).__name__}"
        )
    missing = [k for k in _SCIPY_SUMMARY_KEYS if k not in summary]
    if missing:
        raise ValueError(
            "cannot construct a run entry: run_scipy summary is missing "
            f"field(s) {', '.join(missing)} — the wrapper contract is "
            f"exactly {{{', '.join(_SCIPY_SUMMARY_KEYS)}}} plus residual/"
            "crosscheck; refusing to default"
        )
    state = summary["state"]
    if state not in _SCIPY_STATES:
        raise ValueError(
            f"cannot construct a run entry: summary state must be one of "
            f"{', '.join(_SCIPY_STATES)}; got {state!r} — an unknown state "
            "must not become a well-formed entry"
        )
    valid = summary["valid"]
    if not isinstance(valid, bool) or valid is not (state != "error"):
        raise ValueError(
            f"cannot construct a run entry: summary valid={valid!r} "
            f"contradicts state={state!r} — the wrapper contract ties "
            "valid=true to the two non-error states; refusing to pick one"
        )
    runtime_s = summary["runtime_s"]
    if not isinstance(runtime_s, (int, float)) or isinstance(runtime_s, bool):
        raise ValueError(
            f"cannot construct a run entry: summary runtime_s must be a "
            f"number, got {runtime_s!r}"
        )
    entry = {"converged": valid is True, "wall_clock_s": runtime_s,
             "state": state}
    if state == "solved_verified":
        result = summary["result"]
        if not isinstance(result, str) or not result.strip():
            raise ValueError(
                f"cannot construct a run entry: state=solved_verified but "
                f"result is {result!r}, not a non-empty string — the "
                "wrapper contract says solved_verified always carries the "
                "exact result; refusing to fabricate a qoi_expression"
            )
        entry["qoi_expression"] = result
    else:
        diagnostics = summary["diagnostics"]
        if not isinstance(diagnostics, str) or not diagnostics.strip():
            raise ValueError(
                f"cannot construct a run entry: state={state!r} but "
                f"diagnostics is {diagnostics!r} — a non-answer or failure "
                "must carry the wrapper's own line; refusing to invent a "
                "qoi_error"
            )
        entry["qoi_error"] = diagnostics
    return entry


_RUN_ENTRY_CONSTRUCTORS: dict = {
    "cavity_2d_cfd": _cavity_run_entry,
    "ngspice_linear_passive": _ngspice_run_entry_with_fallback,
    # Packet B Phase 1 flip (owner, 2026-07-17): the tri-state carrier.
    "sympy_symbolic_exact": sympy_run_entry,
}


def run_entry_constructor_for(substrate_id: str):
    """The conclusions-only run-entry constructor for one substrate —
    uniform signature (summary, qoi_error_fallback) -> entry. Read
    STRUCTURALLY from this map keyed by substrate_id (R-28H-1). FAIL LOUD
    (contract_for's style): a substrate with no wired constructor raises
    LookupError; an unknown id raises KeyError first (via registry.get)."""
    registry.get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _RUN_ENTRY_CONSTRUCTORS[substrate_id]
    except KeyError:
        record = registry.get(substrate_id)
        raise LookupError(
            f"no run-entry constructor wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "stage 4 must NOT fall back to the cavity entry shape — wire an "
            "entry in tools/substrate_dispatch.py under a recorded ruling "
            "before routing execution to this substrate."
        )


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
