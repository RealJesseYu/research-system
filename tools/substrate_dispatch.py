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
from tools.run_cobrapy import (
    _OPTIONAL_FIELDS as _COBRAPY_OPTIONAL_FIELDS,
    _REQUIRED_FIELDS as _COBRAPY_REQUIRED_FIELDS,
)
from tools.run_fea import _REQUIRED_FIELDS as _FEA_INPUT_KEYS
from tools.run_fenicsx import _REQUIRED_FIELDS as _FENICSX_INPUT_KEYS
from tools.run_homology_search import _REQUIRED_FIELDS as _HS_REQUIRED_FIELDS
from tools.run_mafft import _REQUIRED_FIELDS as _MAFFT_REQUIRED_FIELDS
from tools.run_ngspice import _REQUIRED_FIELDS, _REQUIRED_QOI_FIELDS
from tools.run_rdkit import _REQUIRED_FIELDS as _RDKIT_REQUIRED_FIELDS

# BIO Wave D.4 (owner, 2026-07-19): the fixed-summary threaded adapters take
# the mini-run CONTENT fields as params and THREAD the QoI selector 'quantity'
# into the wrapper input from the translated request (the ngspice execution
# pattern). So each content-key set is the wrapper's own required-field set
# MINUS 'quantity' (imported, never a pasted literal). cobrapy additionally
# admits its one OPTIONAL typed field (min_growth); the serve-ability signature
# stays required-only (min_growth not in it), and this admits the full wrapper
# content vocabulary at the adapter's structural screen.
_RDKIT_CONTENT_KEYS = tuple(k for k in _RDKIT_REQUIRED_FIELDS if k != "quantity")
_MAFFT_CONTENT_KEYS = tuple(k for k in _MAFFT_REQUIRED_FIELDS if k != "quantity")
_COBRAPY_CONTENT_KEYS = tuple(
    k for k in (tuple(_COBRAPY_REQUIRED_FIELDS) + tuple(_COBRAPY_OPTIONAL_FIELDS))
    if k != "quantity"
)
# homology_search content keys = {database, query, tool} (required minus the
# threaded 'quantity'). Promotion #2 (owner, 2026-07-19).
_HS_CONTENT_KEYS = tuple(k for k in _HS_REQUIRED_FIELDS if k != "quantity")
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


def _cantilever_adapter(substrate_id, params, case_name, roles, qoi_request,
                        input_keys):
    """FIXED-SUMMARY (cantilever class) execution adapter core — INPUT ONLY
    (Packet B Phase 2 flip, build chat under the owner's standing
    delegation, 2026-07-17). case_name and roles are cavity-class concepts,
    accepted for the uniform adapter signature, unused. qoi_request is
    likewise not part of the typed input: these wrappers take NO QoI
    request (both named numbers return on every valid run; the request is
    consumed at ENTRY CONSTRUCTION, which picks the one requested number).

    Structural screen only, mirroring the sympy adapter: params must be a
    dict whose keys are members of the owning wrapper's own typed-key set
    (imported) — unknown keys fail loud naming every offender. CONTENT
    validation (missing fields, positivity, nu bounds, the element_degree
    typed floor) is the wrapper's own _validate_input, the single source:
    content problems come back as honest valid=false summaries whose
    diagnostics name the offender, never as adapter crashes. Returns the
    wrapper summary VERBATIM so stage-4 evidence keeps the full summary."""
    if not isinstance(params, dict):
        raise ValueError(
            f"cannot translate mini-run params: expected an object, got "
            f"{type(params).__name__}"
        )
    unknown = sorted(set(params) - set(input_keys))
    if unknown:
        raise ValueError(
            "cannot translate mini-run params to the cantilever typed input: "
            f"unknown key(s) {', '.join(unknown)} (the wrapper input takes "
            f"only keys from {', '.join(input_keys)})"
        )
    return wrapper_callable(substrate_id)(dict(params))


def _fea_adapter(substrate_id, params, case_name, roles, qoi_request):
    """calculix_cantilever_fea: the cantilever adapter over run_fea's own
    typed-key set (imported — the FEA seven)."""
    return _cantilever_adapter(
        substrate_id, params, case_name, roles, qoi_request, _FEA_INPUT_KEYS
    )


def _fenicsx_adapter(substrate_id, params, case_name, roles, qoi_request):
    """fenicsx_cantilever_elastic: the cantilever adapter over
    run_fenicsx's own typed-key set (imported — the seven plus
    element_degree, the regime-boundary field the wrapper REQUIRES with no
    default)."""
    return _cantilever_adapter(
        substrate_id, params, case_name, roles, qoi_request, _FENICSX_INPUT_KEYS
    )


def _fixed_summary_threaded_adapter(substrate_id, params, case_name, roles,
                                    qoi_request, content_keys):
    """FIXED-SUMMARY THREADED execution adapter core (BIO Wave D.4, owner
    2026-07-19). These wrappers (rdkit/cobrapy/mafft) differ from the
    cantilevers: they take the QoI selector `quantity` as a TYPED INPUT field
    and return a single SCALAR qoi — the run_ngspice execution shape (the QoI
    request goes INTO the wrapper input) but with a fixed_summary vocabulary
    (`quantity` is a membership pick, not the ngspice {kind,target,reduction}).
    So the adapter THREADS the translated quantity into the wrapper input,
    exactly as _ngspice_adapter threads the qoi request into ngspice's `qoi`
    field. case_name and roles are cavity-class concepts, accepted for the
    uniform signature, unused.

    content_keys is the wrapper's typed-key set MINUS 'quantity' (the threaded
    field). Structural screen: params must be a dict whose keys are members of
    content_keys — unknown keys fail loud naming every offender. The translated
    qoi_request must carry 'quantity' (a fixed-summary request always does once
    the spec's qoi validated); a missing one fails loud, mirroring the ngspice
    adapter's refusal to invent a default. CONTENT validation (SMILES
    parse/sanitize, the model allowlist, the alphabet/input gate, the FBA
    status gate) is each wrapper's own _validate_input, the single source:
    content problems come back as honest valid=false summaries. Returns the
    wrapper summary VERBATIM so stage-4 evidence keeps the full summary.

    ALL THREE STRUCTURAL REFUSALS RAISE CaseSynthesisError (2026-07-20), not
    a bare ValueError: each one means "this spec cannot be executed by this
    substrate", which is precisely stage 4's honest halted_synthesis path —
    the relay records the reason and moves on. Raised as ValueError they
    escaped stage 4's own except clause and terminated the run
    (20260719T231117Z, twice, exhausting the crash-recovery budget on a
    condition that was never a crash). qoi_vocab's quantity_required now
    catches the missing-quantity case at stage 2, so this is the net under
    that, not the primary guard."""
    if not isinstance(params, dict):
        raise stage4_case_builder.CaseSynthesisError(
            f"cannot translate mini-run params: expected an object, got "
            f"{type(params).__name__}"
        )
    unknown = sorted(set(params) - set(content_keys))
    if unknown:
        raise stage4_case_builder.CaseSynthesisError(
            "cannot translate mini-run params to the fixed-summary typed "
            f"input: unknown key(s) {', '.join(unknown)} (the wrapper input "
            f"takes only content keys {', '.join(content_keys)} plus the "
            "threaded 'quantity')"
        )
    if not (isinstance(qoi_request, dict) and "quantity" in qoi_request):
        raise stage4_case_builder.CaseSynthesisError(
            "no translated 'quantity' — fixed-summary threaded execution "
            "requires one (translate the spec qoi via "
            "_fixed_summary_qoi_translation); refusing to invent a default"
        )
    typed = dict(params)
    typed["quantity"] = qoi_request["quantity"]
    return wrapper_callable(substrate_id)(typed)


def _rdkit_adapter(substrate_id, params, case_name, roles, qoi_request):
    """rdkit (BIO Wave D.4): the fixed-summary threaded adapter over
    run_rdkit's content keys (imported — {smiles}; 'quantity' is threaded from
    the QoI request). The wrapper parses and sanitizes the molecule; an
    unparseable SMILES comes back as an honest valid=false summary, never a
    fabricated descriptor."""
    return _fixed_summary_threaded_adapter(
        substrate_id, params, case_name, roles, qoi_request, _RDKIT_CONTENT_KEYS
    )


def _cobrapy_adapter(substrate_id, params, case_name, roles, qoi_request):
    """cobrapy (BIO Wave D.4): the fixed-summary threaded adapter over
    run_cobrapy's content keys (imported — {model} plus the optional
    min_growth; 'quantity' is threaded from the QoI request). The wrapper's
    STRUCTURAL status gate means a non-optimal LP solve comes back valid=false
    with qoi None (never the stale objective)."""
    return _fixed_summary_threaded_adapter(
        substrate_id, params, case_name, roles, qoi_request, _COBRAPY_CONTENT_KEYS
    )


def _mafft_adapter(substrate_id, params, case_name, roles, qoi_request):
    """mafft (BIO Wave D.4): the fixed-summary threaded adapter over
    run_mafft's content keys (imported — {sequences}; 'quantity' is threaded
    from the QoI request). The wrapper's STRICT INPUT GATE (>=2 alignable
    same-alphabet sequences, refused pre-run) comes back as an honest
    valid=false summary, never a trusted alignment of un-alignable input."""
    return _fixed_summary_threaded_adapter(
        substrate_id, params, case_name, roles, qoi_request, _MAFFT_CONTENT_KEYS
    )


def _homology_search_adapter(substrate_id, params, case_name, roles, qoi_request):
    """homology_search (BIO Wave D.4 #2): the fixed-summary threaded adapter
    over run_homology_search's content keys (imported — {database, query, tool};
    'quantity' is threaded from the QoI request). The wrapper's DID-IT-WORK /
    DB+profile-integrity gate distinguishes a search that COULD NOT RUN
    (valid=False) from a clean no-hit (valid=True, qoi=None) from a hit
    (valid=True, qoi=e_value) — the wrapper's own three-state summary passes
    through verbatim."""
    return _fixed_summary_threaded_adapter(
        substrate_id, params, case_name, roles, qoi_request, _HS_CONTENT_KEYS
    )


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
    # Packet B Phase 2 flip (build chat under the owner's standing
    # delegation, 2026-07-17)
    "calculix_cantilever_fea": _fea_adapter,
    "fenicsx_cantilever_elastic": _fenicsx_adapter,
    # BIO Wave D.4 promotion flip (owner, 2026-07-19): three fixed-summary
    # INPUT-only adapters over each wrapper's own typed-key set.
    "rdkit": _rdkit_adapter,
    "cobrapy": _cobrapy_adapter,
    "mafft": _mafft_adapter,
    # BIO Wave D.4 promotion #2 (owner, 2026-07-19)
    "homology_search": _homology_search_adapter,
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


def _fixed_summary_qoi_translation(spec_qoi, vocab):
    """Fixed-summary (cantilever class) translation in stage 4's
    (request, refusal) shape: the ONE machine key is "quantity" — which of
    the wrapper's returned numbers is THE quantity of interest, membership-
    checked against the record's `names` (imported from the wrapper's own
    QOI_FIELDS). A missing or unknown quantity is an honest refusal (the
    qoi_error fallback path), never a guess — the wrapper returns both
    numbers regardless; the request is consumed at entry construction."""
    if not isinstance(spec_qoi, dict):
        return None, (
            f"spec qoi must be an object, got {type(spec_qoi).__name__} — "
            "refusing to invent a request"
        )
    if "quantity" not in spec_qoi:
        return None, (
            "spec qoi carries no machine-readable 'quantity' key — a "
            "fixed-summary request names which of the wrapper's returned "
            f"numbers ({', '.join(vocab.names)}) is THE quantity of "
            "interest; free-text definitions are not translated"
        )
    quantity = spec_qoi["quantity"]
    if quantity not in vocab.names:
        return None, (
            f"spec qoi quantity {quantity!r} is not one of the wrapper's "
            f"returned numbers ({', '.join(vocab.names)}); refusing to guess"
        )
    return {"quantity": quantity}, None


_QOI_TRANSLATIONS: dict = {
    "cavity_2d_cfd": _cavity_qoi_translation,
    "ngspice_linear_passive": _ngspice_qoi_translation,
    # Packet B Phase 1 flip (owner, 2026-07-17)
    "sympy_symbolic_exact": _sympy_qoi_translation,
    # Packet B Phase 2 flip (build chat under the owner's standing
    # delegation, 2026-07-17): one translation, two substrates — the
    # membership set is per-record (each wrapper's own imported names).
    "calculix_cantilever_fea": _fixed_summary_qoi_translation,
    "fenicsx_cantilever_elastic": _fixed_summary_qoi_translation,
    # BIO Wave D.4 (owner, 2026-07-19): the same fixed-summary translation —
    # the ONE machine key "quantity" is membership-checked against each
    # record's own imported `names`.
    "rdkit": _fixed_summary_qoi_translation,
    "cobrapy": _fixed_summary_qoi_translation,
    "mafft": _fixed_summary_qoi_translation,
    # BIO Wave D.4 promotion #2 (owner, 2026-07-19): same fixed-summary
    # translation — "quantity" membership-checked against ("e_value",).
    "homology_search": _fixed_summary_qoi_translation,
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

def _cavity_run_entry(summary: dict, qoi_error_fallback: str | None,
                      qoi_request=None) -> dict:
    """Conclusions only: {converged, qoi_value | qoi_error, wall_clock_s} —
    MOVED VERBATIM from stages.stage4_simulation._payload_run_entry at the
    R2 flip (owner, 2026-07-17); the cavity data surface is fixture-pinned
    byte-identical (tests/fixtures/d4/). qoi_request joined the uniform
    constructor signature ADDITIVELY at Packet B Phase 2.0 (ruled, option
    V-A) for fixed-summary substrates whose wrapper returns several named
    numbers; deliberately IGNORED here — the cavity wrapper already
    extracts the one requested QoI itself, and the entry stays
    byte-identical (proven by exact-dict asserts)."""
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


def _ngspice_run_entry_with_fallback(summary, qoi_error_fallback,
                                     qoi_request=None) -> dict:
    """ngspice_run_entry under the uniform (summary, qoi_error_fallback,
    qoi_request) constructor signature. The fallback is deliberately
    unused: a named-quantity substrate never executes without a translated
    QoI request (_ngspice_adapter refuses), so a summary always carries its
    own qoi / diagnostics truth. qoi_request (additive, Packet B Phase 2.0
    ruled option V-A) is likewise ignored: the wrapper already extracted
    the one requested quantity — the entry stays byte-identical (proven by
    exact-dict asserts)."""
    return ngspice_run_entry(summary)


def _fixed_summary_scalar_run_entry(summary, qoi_error_fallback=None,
                                    qoi_request=None) -> dict:
    """BIO Wave D.4 (owner, 2026-07-19): the run-entry constructor for the
    rdkit/cobrapy/mafft class. Their wrapper summary shape is BYTE-IDENTICAL to
    run_ngspice's — {valid, qoi(scalar), diagnostics, runtime_s} — because these
    wrappers also take the QoI selector as a typed input and return the ONE
    requested number as a scalar (unlike the cantilevers' dict-of-numbers qoi).
    So ngspice_run_entry IS the single source (reused, never copied): converged
    := (valid is True) — COMPLETED-AND-PARSED (a finite descriptor / an optimal
    LP growth / a well-formed alignment identity); wall_clock_s := runtime_s;
    valid=False -> converged=False plus qoi_error from diagnostics, NEVER a
    fabricated qoi_value. NO `state` key (the summaries carry only the boolean
    valid). qoi_error_fallback and qoi_request are ignored: the adapter threaded
    the quantity into the wrapper input, so a valid summary already carries its
    one scalar and an invalid one its named diagnostics."""
    return ngspice_run_entry(summary)


# homology_search shares run_ngspice's summary key set (scalar qoi), but adds a
# THIRD state the scalar constructor cannot map: valid=True with qoi=None (a
# clean 0-hits run — a real "no significant homolog at this cutoff"), which is
# NOT an error and NOT a number.
_HS_SUMMARY_KEYS = ("valid", "qoi", "diagnostics", "runtime_s")


def homology_search_run_entry(summary, qoi_error_fallback=None,
                              qoi_request=None) -> dict:
    """BIO Wave D.4 #2 (owner, 2026-07-19): the run-entry constructor for
    homology_search's THREE-state summary {valid, qoi, diagnostics, runtime_s}.
    Unlike rdkit/cobrapy/mafft (a number whenever valid), a homology search can
    complete cleanly with NO significant hit — valid=True, qoi=None — a real
    biological result, not a failure. The mapping:
      valid=False                 -> converged=False, qoi_error=diagnostics
                                     (the search COULD NOT RUN — bad DB /
                                     malformed profile / rejected input);
      valid=True, qoi=<number>    -> converged=True,  qoi_value=the best e_value;
      valid=True, qoi=None        -> converged=True,  qoi_error=diagnostics
                                     (the honest "0 significant hits" line — the
                                     search RAN, so converged, but there is no
                                     number to trust; NEVER a fabricated 0).
    converged := (valid is True) — COMPLETED-AND-PARSED (the DID-IT-WORK gate
    passed), the same meaning as the scalar constructor. qoi_error_fallback and
    qoi_request are ignored: the adapter threaded the quantity in and the
    wrapper's own three-state truth is authoritative. FAIL LOUD (ValueError) on
    a structurally broken summary — never a default."""
    if not isinstance(summary, dict):
        raise ValueError(
            f"cannot construct a run entry: expected a run_homology_search "
            f"summary object, got {type(summary).__name__}"
        )
    missing = [k for k in _HS_SUMMARY_KEYS if k not in summary]
    if missing:
        raise ValueError(
            "cannot construct a run entry: run_homology_search summary is "
            f"missing field(s) {', '.join(missing)} — the wrapper contract is "
            f"exactly {{{', '.join(_HS_SUMMARY_KEYS)}}}; refusing to default"
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
    qoi = summary["qoi"]
    if valid and isinstance(qoi, (int, float)) and not isinstance(qoi, bool):
        entry["qoi_value"] = qoi
        return entry
    # valid=False, OR valid=True with qoi=None (clean no-hit): both carry the
    # wrapper's own named line as qoi_error; a non-None non-number qoi on a
    # valid run is a broken contract.
    if valid and qoi is not None:
        raise ValueError(
            f"cannot construct a run entry: summary claims valid=true but qoi "
            f"is {qoi!r} — the wrapper contract says a valid run carries either "
            "a numeric e_value or None (a clean no-hit); refusing to fabricate"
        )
    diagnostics = summary["diagnostics"]
    if not isinstance(diagnostics, str) or not diagnostics.strip():
        raise ValueError(
            f"cannot construct a run entry: qoi is absent but diagnostics is "
            f"{diagnostics!r} — a could-not-run or a clean no-hit must carry "
            "the wrapper's own named line; refusing to invent a qoi_error"
        )
    entry["qoi_error"] = diagnostics
    return entry


# The run_scipy summary key set, per the wrapper's own documented return
# shape (tools/run_scipy.py:56-58) — the structural fields the constructor
# reads; residual/crosscheck stay in the full summary (stage-4 evidence).
_SCIPY_SUMMARY_KEYS = ("valid", "state", "result", "reason", "diagnostics",
                       "runtime_s")

_SCIPY_STATES = ("solved_verified", "unevaluated", "error")


def sympy_run_entry(summary, qoi_error_fallback=None, qoi_request=None) -> dict:
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
    qoi_request (additive, Packet B Phase 2.0 ruled option V-A) is likewise
    ignored: this wrapper takes no QoI request at all — the entry stays
    byte-identical (proven by exact-dict asserts).
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


# The cantilever wrappers' summary key set, per both wrappers' documented
# return shape (tools/run_fea.py:22-26 / tools/run_fenicsx.py:33-37:
# {valid, qoi, diagnostics, runtime_s}) — neither wrapper defines a
# constant for it, so the contract lines are the cite.
_CANTILEVER_SUMMARY_KEYS = ("valid", "qoi", "diagnostics", "runtime_s")


def fixed_summary_run_entry(summary, qoi_error_fallback=None,
                            qoi_request=None) -> dict:
    """Packet B Phase 2 flip (ruled option V-A, build chat under the
    owner's standing delegation, 2026-07-17): one conclusions-only stage-4
    run entry from a cantilever fixed-summary wrapper summary.

    The mapping, stated in both graduated contracts §3: converged :=
    (valid is True) — COMPLETED AND PARSED, never mesh-converged, never
    in-regime; wall_clock_s := runtime_s; NO `state` key (these wrappers
    carry no state vocabulary of their own, only the boolean valid). The
    wrapper returns BOTH named numbers on every valid run, and the locked
    run entry carries ONE numeric qoi_value — qoi_request (the additive
    third constructor parameter this substrate class exists for) names
    which: {"quantity": <name>} picks summary["qoi"][<name>]. A valid run
    with NO translated request files honestly under qoi_error via the
    stage-4 fallback; valid=false carries the wrapper's own diagnostics.
    FAIL LOUD (ValueError naming every offender) on structurally missing,
    ill-typed, or contract-breaking wrapper fields — never a default."""
    if not isinstance(summary, dict):
        raise ValueError(
            f"cannot construct a run entry: expected a cantilever wrapper "
            f"summary object, got {type(summary).__name__}"
        )
    missing = [k for k in _CANTILEVER_SUMMARY_KEYS if k not in summary]
    if missing:
        raise ValueError(
            "cannot construct a run entry: cantilever wrapper summary is "
            f"missing field(s) {', '.join(missing)} — the wrapper contract "
            f"is exactly {{{', '.join(_CANTILEVER_SUMMARY_KEYS)}}}; "
            "refusing to default"
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
    if not valid:
        diagnostics = summary["diagnostics"]
        if not isinstance(diagnostics, str) or not diagnostics.strip():
            raise ValueError(
                f"cannot construct a run entry: summary valid=false but "
                f"diagnostics is {diagnostics!r} — a failed run must carry "
                "its named reason; refusing to invent a qoi_error"
            )
        entry["qoi_error"] = diagnostics
        return entry
    qoi = summary["qoi"]
    if not isinstance(qoi, dict):
        raise ValueError(
            f"cannot construct a run entry: summary claims valid=true but "
            f"qoi is {qoi!r}, not an object — the wrapper contract says "
            "valid=true always carries both named numbers; refusing to "
            "fabricate a qoi_value"
        )
    if isinstance(qoi_request, dict) and "quantity" in qoi_request:
        quantity = qoi_request["quantity"]
        if quantity not in qoi:
            raise ValueError(
                f"cannot construct a run entry: requested quantity "
                f"{quantity!r} is absent from the wrapper qoi object "
                f"(keys: {', '.join(sorted(qoi))}) — the wrapper contract "
                "says every valid run carries both named numbers; refusing "
                "to substitute"
            )
        value = qoi[quantity]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"cannot construct a run entry: quantity {quantity!r} is "
                f"{value!r}, not a number — refusing to fabricate a "
                "qoi_value"
            )
        entry["qoi_value"] = value
        return entry
    if qoi_error_fallback is not None:
        entry["qoi_error"] = qoi_error_fallback
        return entry
    raise ValueError(
        "cannot construct a run entry: a valid cantilever run arrived with "
        "neither a translated qoi_request nor a qoi_error fallback — "
        "refusing to pick a number silently"
    )


_RUN_ENTRY_CONSTRUCTORS: dict = {
    "cavity_2d_cfd": _cavity_run_entry,
    "ngspice_linear_passive": _ngspice_run_entry_with_fallback,
    # Packet B Phase 1 flip (owner, 2026-07-17): the tri-state carrier.
    "sympy_symbolic_exact": sympy_run_entry,
    # Packet B Phase 2 flip (build chat under the owner's standing
    # delegation, 2026-07-17): one constructor, two substrates — the
    # request-named pick is per-call, the contract mapping identical.
    "calculix_cantilever_fea": fixed_summary_run_entry,
    "fenicsx_cantilever_elastic": fixed_summary_run_entry,
    # BIO Wave D.4 (owner, 2026-07-19): the SCALAR fixed-summary constructor —
    # these wrappers return a bare scalar qoi (the ngspice summary shape),
    # NOT the cantilevers' dict-of-numbers, so ngspice_run_entry is reused.
    "rdkit": _fixed_summary_scalar_run_entry,
    "cobrapy": _fixed_summary_scalar_run_entry,
    "mafft": _fixed_summary_scalar_run_entry,
    # BIO Wave D.4 promotion #2 (owner, 2026-07-19): the THREE-state
    # constructor (a clean no-hit is valid=True/qoi=None -> qoi_error, not a
    # fabricated number).
    "homology_search": homology_search_run_entry,
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
