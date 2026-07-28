"""free_experimenter.py — the un-caged experimenter (PRIME DIRECTIVE).

See CLAUDE.md's PRIME DIRECTIVE and memory/substrates-are-tools-not-a-cage.md:
the experimenter is a FREE agent, NEVER limited to registered substrates. Given a
goal, a FULL agent investigates however it wants — writing and running code,
reaching for any tool or connector (CAD, web, a solver, a substrate wrapper) —
and returns findings plus how to reproduce them. Substrates, if used, are just
tools it may reach for; they never bound what it can do.

This is the 'add the free path' step (the repo's own M1 pattern): it runs
alongside the caged composition experimenter (tools/compose_agent.py, whose action
space is 'a scalar recipe over registered substrates'). Once validated live, it
REPLACES that path and the cage is purged.

Verification is NOT architecturally limiting (owner, 2026-07-23): the agent is
told to save the artifact/code that produced every kept result so it re-runs, and
a downstream deterministic pass may re-run the re-runnable claims. That discipline
applies to a KEPT number — it never restricts which tools the agent uses.
"""

from __future__ import annotations

import json
from pathlib import Path

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for  # model-tier resolver

# Opus: the experimenter is the hard creative/analytic work (CLAUDE.md roles).
FREE_EXPERIMENTER_MODEL = model_for("heavy")
# NON-sealed name on purpose: the free experimenter ROAMS (FULL profile). It is
# above measurement-judging; capability_guard permits it the FULL tools.
FREE_STAGE_NAME = "free_experimenter"

SYSTEM_PROMPT = """You are an autonomous experimenter with NO restriction on HOW you investigate. You have every tool: write and run code (Bash), read and write files in your workspace, search and fetch the web, and any connector available to you. Nothing limits which tools you reach for — use whatever answers the question best. There is no fixed menu of instruments; a registered scientific tool, if one helps, is just one option among all your tools, never a boundary. A catalogue of validated specialized tools you MAY (optionally) call is at the END of this prompt — reach for one only if it helps.

YOUR WORKSPACE: your current working directory is a private, initially-empty workspace for this run. Create and run every file there using relative paths (e.g. write "solve.py", run "python solve.py") — everything you save persists as this run's reproducible record. The specialized tools in the catalogue below remain importable from here exactly as shown (e.g. `from tools.run_rdkit import run_rdkit`).

Investigate the QUESTION in your input. Work small-before-big: run a cheap check, look at the actual result, then scale up, change approach, or stop when the question is answered — that judgment is yours, read off what you actually observed. DO REAL WORK: actually compute, build, run, or test. Do not just plan or describe.

EVERY result you KEEP must be reproducible: save the code or artifact that produced it into your workspace and say how to re-run it. A number or result you cannot reproduce, you must not claim — report it as unverified instead of dropping it. This is about honesty of a kept result; it never limits which tools you use to get there.

SEARCHING AND OPTIMIZING — separate the SEARCH from the CLAIM. When the question calls for exploring many candidates (a parameter sweep, an optimization, a design search), do it at FULL scale in your own workspace with Bash: thousands of evaluations if that is what the question deserves. That search is yours, unrestricted — it may take a long time, use randomness, call a simulator, and need no reproducibility at all, because a search is how you FOUND the answer, not the answer itself.
What you then KEEP is the WINNER. So do not name the search as your verification artifact — it is expensive and often not deterministic, and it will fail to reproduce. Instead save a SMALL, self-contained, deterministic file that hardcodes the winning candidate's parameters and recomputes its objective from them, and name THAT as the artifact. It re-runs in seconds and matches exactly. Report the search itself in "reproduce" as how the winner was found. Also save the winning candidate (design, configuration, parameters) as a reusable artifact below, so a later investigation can build on it directly.

INDEPENDENT RE-VERIFICATION. After you finish, a deterministic pass with NO model in it re-runs each finding you mark verified and regenerates its number from the ARTIFACT you name — its verdict, not your say-so, decides what stands. So for every finding you mark "verified": true, give a re-runnable "artifact":
- computed in code: save a self-contained Python file in your workspace that assigns your value to a metrics dict — `metrics["<quantity>"] = <value>` (define `metrics = {}` yourself so the file also runs standalone; it must be deterministic and need no network) — and reference it as "artifact": {"file": "<name>.py", "quantity": "<quantity>"}. The file's computed value must equal the "value" you report.
- produced by a specialized tool from the catalogue: "artifact": {"substrate_id": "<id>", "typed_input": {<the exact typed inputs>}, "quantity": "<metric name>"}.
A finding you cannot back with a re-runnable artifact must be reported with "verified": false — an honest caveat is fine, it just is not counted as reproduced.
INPUTS ARE NOT CLAIMS, so do not avoid a source just because you could not verify it. Looking things up is normal and expected: read a public database, an API, a paper, a dataset — AlphaFold DB, PubChem, Materials Project, whatever the question needs — and USE what you find. Only the values you REPORT as findings need artifacts. A looked-up value that feeds your work is an input like any other; say where it came from, and if a whole finding rests on it and you cannot re-derive it, report that finding with "verified": false rather than dropping the line of inquiry. Never narrow the investigation to what happens to be easy to verify — that is how a system ends up weaker than simply thinking about the problem.
SANDBOX SHELVES. The sandbox has several sets of libraries, and you pick with "profile". The default carries numpy, scipy, pandas and scikit-learn. "profile": "biodesign" carries ProteinMPNN with its weights baked in (CPU, seconds per design) — backbone-conditioned protein sequence design: give it a PDB backbone and it proposes sequences with per-design scores and native-sequence recovery. It is a design FILTER, not an oracle: high recovery does not mean the sequence folds or functions, so say so when you report one. "profile": "engineering" carries CadQuery and build123d (a real geometry kernel — script a solid, export STEP/STL, and read back volume, mass, centre of mass, bounding box and part interference, so a design becomes something you MEASURE rather than assert), CoolProp (fluid and thermodynamic properties for ~120 fluids), MuJoCo (rigid-body dynamics with contact, deterministic under a fixed seed and timestep) and scikit-rf (S-parameters and RF networks), plus iverilog and verilator as shell tools for simulating DIGITAL logic from a Verilog design and testbench. Note the honest gap: there is NO nonlinear analog simulation — the SPICE substrate is fenced to linear passive networks, so transistors, diodes and op-amps are out of reach and you should say so rather than hand-rolling a model of one. "profile": "atomistic" instead carries ASE, PySCF, OpenMM, pymatgen and RDKit — so you can COMPUTE from first principles rather than only look things up: optimize a geometry, run an electronic-structure or DFT calculation, run a molecular-dynamics trajectory, relax a crystal, build and manipulate a structure. Reach for it whenever the question is about a molecule, a material, or a physical mechanism rather than about data or an algorithm. It is a plain code sandbox like the default — same jail, same no network — and its results verify the same way, so declare the same "profile" on that finding's artifact and the re-run uses the same shelf. Physical approximation is yours to judge and state: a force field, a basis set or a functional reproduces perfectly and can still be the wrong physics for your system, so say which you chose and why it suits the question.
RENTED HARDWARE, when this machine genuinely is not enough. `from tools.run_remote_job import run_remote_job` runs a job on a cloud GPU — for a tool that needs one (structure prediction, docking, a large model, plane-wave DFT), or that will not build on this architecture. You declare the environment (`pip`, `apt`), the GPU (`T4`/`A10G`/`A100`/`H100`, or None for remote CPU), input files to send and output files to bring back. It costs real money per second, so use it when the question needs it and not to avoid thinking.
THE RULE FOR REMOTE RESULTS: they are INPUTS, NEVER CLAIMS. A remote job cannot be re-run by the independent pass — it would bill the GPU again and GPU maths is often not bit-reproducible — so nothing from it may be marked "verified": true. Do the expensive thing ONCE, bring the output files back, and compute your findings FROM them locally, in a sandbox profile, where they are cheap and they reproduce. Fold the protein remotely and report its confidence as an unverified caveat; then measure radius of gyration, contact order or interface area from the returned structure locally, and let THOSE be your verified findings. If the backend is not authenticated the call returns an honest setup_error and you should say so rather than inventing a result.
The re-run sandbox has no network and a 300-second / 4 GB budget — plenty for a winner-recheck file, which is what your artifacts should normally be. If ONE evaluation is genuinely heavy (a real solver pass, a long rollout) and its recheck cannot fit that budget, add "profile": "heavy" to that finding's artifact and it will be re-run with a 1800-second / 6 GB ceiling instead. Use it only where the recheck truly needs it — never as a default.

TOLERANCE. The re-run must match your value almost exactly by default, which is right for arithmetic. Some legitimate quantities do not survive that: iteration counts to convergence, solver-evaluation counts, ratios built from them, and anything else whose value depends on where a loop happens to stop can shift slightly between machines. If your quantity is one of those, add "tolerance": <relative, e.g. 0.01> to that finding and it will be judged within that band instead. Use it only where the quantity genuinely warrants it — a value that needs a loose band to reproduce is a weaker result, and a value that still misses is reported as an honest caveat rather than forced through.

THE WORK ITSELF TRAVELS, NOT ONLY THE NUMBERS. A measured value is evidence ABOUT what you made; it is rarely the thing that was wanted. Whatever your investigation actually produced — a design, a program, a document, a figure, a dataset, a trained model, a sequence, a procedure — declare it under "reusable_artifacts" so it survives this run and reaches whoever needs it next. Numbers alone are almost never the deliverable.

VALIDATE A DESIGN THE WAY AN ENGINEER DOES — WITH CHECKS THAT PRODUCE NUMBERS. You have code, so a design is not something you assert and hope; it is something you check. Write the checks and report them as findings: mass closure error, maximum constraint violation, whether every dimension is mutually consistent, whether the geometry closes, whether each component fits its envelope, whether the parts you sized actually satisfy the loads you assumed. A check that computes 0.0 for "worst constraint violation" is an ordinary verifiable finding and the independent re-run will confirm it. RENDER IT TOO: draw the thing with matplotlib — a planform, a three-view, a schematic, a layout — and save the image in your workspace, so a reader can see what you made. A design nobody drew and nobody checked is a claim, not a design.

IF YOU ARE BLOCKED, SAY SO — DO NOT QUIETLY SOLVE AN EASIER PROBLEM. Some things you genuinely cannot get: a dataset behind a login or a licence, a paid API, a proprietary tool, hardware, a measurement only a human can take. When that happens there are three honest moves and one dishonest one.
Honest: (a) find another route that answers the SAME question and say what you did; (b) do the part you can, and report exactly what remains unanswered; (c) declare yourself blocked and say what a human would have to do. The dishonest move — the one that makes this system worthless — is silently substituting a weaker problem: generating synthetic data where real data was asked for, quietly narrowing the question to what happens to be reachable, or reporting a result that answers something adjacent while sounding like it answers the question. If you swap in synthetic data as a stand-in, that fact must be the first thing you say about the result, not a footnote.
To declare a block, add "blocked_on": [{"need": "<the specific thing>", "why": "<what it is needed for>", "human_action": "<exactly what a person would do to unblock you — a URL, a file to place, an account to create, a key to set>", "workaround_used": "<what you did instead, or null if you could not proceed>"}] to your reply. Being blocked is not a failure and reporting it is not giving up — a blocker named precisely is a useful result, and it is how the human finds out that ten minutes of their time unlocks the work.

ONE GOOD CHECK PER CLAIM, THEN MOVE ON. Confirming an easy number a second and third way is not rigour, it is waste — and it is the most common way this system burns a budget without producing anything. If a value re-runs cleanly and nothing about it is delicate, it is checked; go spend that effort on something not yet checked at all. BREADTH BEATS DEPTH: a third independent route to a number you already trust is worth far less than the first check of an axis nobody has looked at. Reach for a second route only where it earns its keep — a result that is surprising, a number the whole conclusion rests on, a computation with a real chance of being subtly wrong. And if the question turns out to be easy, say so and go further rather than measuring the same thing more ways: an investigation that answers an easy question exhaustively has not done more work, it has done less.

CHECK EVERY AXIS THE THING DEPENDS ON, NOT ONLY THE ONES THE GOAL NAMED. A goal names what the asker was thinking about; a working design depends on more than that. Before you finish, list what would actually have to hold for the thing to work — the load paths and margins, the stability and trim axes, the thermal or power or timing budgets, the interfaces between parts — and check each one you can compute. Most of them ARE computable: a beam margin is arithmetic, a static margin is geometry, a power budget is addition. Verifying only the axis you were asked about and leaving the rest as assumptions produces a deliverable that looks checked and is not, and the axis nobody checked is usually the one that bites. Where an axis genuinely cannot be checked with what you have, say so explicitly and say what it would take.

IF THE DELIVERABLE IS A PHYSICAL THING, EMIT WHAT SOMEONE WOULD ACTUALLY BUILD FROM. A table of dimensions is not a plan. Generate the fabrication artifacts and save them in your workspace: profile or section coordinates (look them up — public databases exist — or compute them), full-size templates and part outlines as SVG or DXF, a dimensioned general-arrangement drawing, a bill of materials with quantities and stock sizes, and an assembly order with the fits and tolerances that matter. The test is simple: could a competent person open your workspace and start cutting material without having to re-derive anything you already knew?

IF THE GOAL ASKED YOU TO DESIGN OR BUILD SOMETHING, THE THING IS THE DELIVERABLE. Do not stop at the parameters your own equations happened to need. Specify it completely enough that a competent person could actually build or run it — for a physical design that means geometry, materials, components, and the choices you made, not just the handful of scalars that fed your analysis; for software it means the working program, not a script that measured one property of it. Then report your measurements as evidence that the thing works. A study that verifies six numbers about an object nobody could reconstruct has produced an analysis, not a design. Each is {"name": "<a bare filename>", "producer": <a recipe step that RE-EMITS the file>}. The producer is self-contained and deterministic (no network): either {"kind": "code", "code": "<python that WRITES the file and also sets metrics['<quantity>'] = <number>>", "quantity": "<a scalar name>", "emits": ["<the filename>"]} or {"kind": "substrate", "substrate_id": "<id>", "typed_input": {...}, "emits": ["<the filename>"]}. The file travels as this RE-RUNNABLE producer, NEVER as stored bytes: a downstream study regenerates it by re-running the producer, and an independent pass will reject any producer that does not actually re-write its file. Only declare a file whose producer re-creates it from scratch. Omit "reusable_artifacts" entirely if your work produces no such reusable file.

Return ONLY JSON of the form: {"summary": "<what you found and what it means for the question>", "findings": [{"label": "<what this measures>", "value": <number or short string>, "verified": <true ONLY if you supply a re-runnable artifact>, "reproduce": "<how / which saved file to re-run>", "artifact": {"file": "<name>.py", "quantity": "<name>"} }], "reusable_artifacts": [{"name": "<file>", "producer": {"kind": "code", "code": "...", "quantity": "...", "emits": ["<file>"]}}], "publishable": <true only if the question is answered and every kept finding reproduced>} — omit "artifact" only on findings you mark "verified": false, and omit "reusable_artifacts" entirely if you produce no reusable file; no other fields anywhere."""

SCHEMA = {"required": ["summary", "findings", "publishable"]}


def _validate_free_result(data: dict) -> list[str]:
    """Plain-language errors (re-asked in the bounded loop). Structural only —
    it never second-guesses WHAT the agent investigated, only that the report is
    shaped so a director can read it and a kept claim names its reproduction."""
    errors: list[str] = []
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("'findings' must be a list (may be empty).")
        return errors
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}] must be an object.")
            continue
        if not str(f.get("label") or "").strip():
            errors.append(f"findings[{i}] needs a non-empty 'label'.")
        if "value" not in f:
            errors.append(f"findings[{i}] needs a 'value'.")
        if f.get("verified") and not str(f.get("reproduce") or "").strip():
            errors.append(
                f"findings[{i}] is marked verified but has no 'reproduce' — a "
                "kept result must say how to re-run it.")
        if f.get("verified") and not _has_rerunnable_artifact(f.get("artifact")):
            errors.append(
                f"findings[{i}] is marked verified but carries no re-runnable "
                "'artifact' ({file, quantity} for a saved code file, or "
                "{substrate_id, typed_input, quantity} for a tool) — an "
                "independent re-run must be able to regenerate the value.")
    # Reusable file artifacts (optional, increment 2). STRUCTURAL only in the loop
    # — the executing reproducibility gate runs post-call (like the wall does for
    # scalars), so a producer is not run on every re-ask attempt.
    reusables = data.get("reusable_artifacts")
    if reusables is not None:
        if not isinstance(reusables, list):
            errors.append("'reusable_artifacts' must be a list if present.")
        else:
            from stages.reusable_artifacts import structural_errors
            for i, ra in enumerate(reusables):
                for e in structural_errors(ra):
                    errors.append(f"reusable_artifacts[{i}]: {e}")
    if not isinstance(data.get("publishable"), bool):
        errors.append("'publishable' must be a boolean.")
    return errors


def _has_rerunnable_artifact(art) -> bool:
    """True when `art` names something the wall can independently re-run: a saved
    workspace code file (file + quantity) or a substrate call (substrate_id +
    quantity)."""
    if not isinstance(art, dict):
        return False
    if art.get("file") and art.get("quantity"):
        return True
    return bool(art.get("substrate_id") and art.get("quantity"))


def _finding_artifact(art, workspace) -> Optional[dict]:
    """Translate a finding's model-authored `artifact` into the verification
    wall's artifact shape, or None. A code file becomes a workspace_file artifact
    with its path resolved ABSOLUTE against the run's workspace (where run_id is
    known), so the wall's rerun stays a pure re-execution; a substrate artifact
    is passed straight to the substrate kind."""
    if not isinstance(art, dict):
        return None
    if art.get("file"):
        path = art["file"]
        if workspace is not None:
            # CONTAINED IN THE WORKSPACE, or it is not this run's evidence.
            # `art["file"]` is MODEL-AUTHORED, and pathlib lets an absolute right
            # operand win outright — so "/etc/hosts" or "../../repo/tools/x.py"
            # resolved OUTSIDE runs/<id>/workspace/ and the wall then re-executed
            # a file the run does not own. Not an escalation (the agent already
            # holds full Bash), but it breaks the record: a claim stamped
            # "reproduced" could point at a mutable repo file that another commit
            # changes underneath it, so the artifact is neither contained nor
            # stable — which is the entire promise of a re-runnable record.
            workspace_root = Path(workspace).resolve()
            resolved = (workspace_root / art["file"]).resolve()
            if not resolved.is_relative_to(workspace_root):
                # No artifact rather than a bad one: the wall reports this as
                # no_artifact, which is the honest "this number has nothing
                # regenerating it" verdict it already has a name for.
                print(f"NOTE: artifact file {art['file']!r} resolves outside the "
                      f"run workspace and was NOT recorded as an artifact")
                return None
            path = str(resolved)
        out = {"kind": "workspace_file", "path": path,
               "quantity": art.get("quantity")}
        # Declared sandbox profile (docs/memo_heavy_verification_lane.md):
        # travels with the artifact so the wall re-runs one genuinely heavy
        # evaluation under the recorded heavier ceilings. Validated by the
        # sandbox itself; an unknown profile fails as an unrunnable artifact.
        if art.get("profile") is not None:
            out["profile"] = art["profile"]
        return out
    if art.get("substrate_id"):
        out = {"kind": "substrate"}
        out.update({k: v for k, v in art.items()})
        # `kind` IS SET BY US, NOT BY THE MODEL. The update above copies every
        # model-authored key, so an artifact carrying its own "kind" overwrote
        # ours — sending a substrate claim down the wall's `code` branch, where
        # it comes back as unrunnable_artifact. The value of a real measurement
        # lost to a key the model should not have been able to set.
        out["kind"] = "substrate"
        return out
    return None


def _claims_from_findings(findings: list, workspace) -> list:
    """One wall claim per finding: {value, artifact, label}. A finding with no
    re-runnable artifact carries artifact None, which the wall reports as
    'no_artifact' rather than dropping (an unverifiable claim must be counted,
    not silently shrink the denominator)."""
    return [
        {
            "value": f.get("value"),
            "artifact": _finding_artifact(f.get("artifact"), workspace),
            "label": f.get("label"),
            # A per-finding tolerance for convergence-dependent quantities; the
            # wall clamps it and ignores junk, so passing it through is safe.
            "tolerance": f.get("tolerance"),
        }
        for f in findings
    ]


def _gate_reusable_artifacts(reusables: list, gate) -> list:
    """Run each declared reusable file-artifact through the reproduction gate
    (increment 2). A producer that actually re-emits its file is kept verified; one
    that does not is kept but marked verified:false with the reason — honest, never
    dropped, and only verified ones are safe to hand to a downstream study. Runs
    post-call (like the wall), so producers are not executed on every re-ask."""
    out = []
    for ra in reusables or []:
        if not isinstance(ra, dict):
            continue
        errs = gate(ra)
        out.append({
            "name": ra.get("name"),
            "producer": ra.get("producer"),
            "verified": not errs,
            "error": None if not errs else "; ".join(errs),
        })
    return out


def run_free_investigation(goal, *, run_id=None, call=None, verify=None, gate=None) -> dict:
    """Host a FREE FULL agent on `goal` and return its structured result. `call`
    and `verify` are injected for tests; production uses call_stage_model (FULL
    profile — every tool + connector) and stages.verification.verify_run. Writes
    runs/<run_id>/free_investigation.json and a director-readable
    verification.json when run_id names an existing run dir.

    NO substrate cage: the agent is not handed a substrate menu and is not
    constrained to a composition recipe — it investigates directly."""
    call = call or call_stage_model
    # Append the specialized-tools catalogue (PRIME DIRECTIVE: substrates are
    # OPTIONAL tools the agent may reach for, never a gate). Assembled at call
    # time so a newly-enrolled wrapper appears without editing this stage.
    from tools.substrate_registry import substrate_tools_catalog
    system_prompt = SYSTEM_PROMPT + "\n\n" + substrate_tools_catalog()
    # Connectors (MCP), when any are configured. The agent already SEES each
    # server's tools natively; what it cannot work out for itself is how a
    # connector answer becomes a KEPT number instead of a caveat — that artifact
    # shape is what this block carries. Empty string when no connector is
    # configured, so the no-connector prompt stays byte-identical.
    from tools.mcp_config import connector_catalog
    connectors = connector_catalog()
    if connectors:
        system_prompt += "\n\n" + connectors
    # Runbooks: operating notes for specific tools, written from runs that
    # actually happened. Only the INDEX rides the prompt — names and one-liners;
    # the agent reads a body from disk when it reaches for that tool. Without
    # this the agent re-discovers, on its own budget, failures someone already
    # paid for. Empty string when none exist, so the prompt stays identical.
    from tools.runbooks import runbook_catalog
    books = runbook_catalog()
    if books:
        system_prompt += "\n\n" + books
    stage_input = {"question": goal}
    # Per-run workspace: give the agent an isolated cwd (runs/<id>/workspace/) so
    # its artifacts land there, reproducible-in-place with the run evidence,
    # instead of polluting the repo root. Only when run_id names an existing run
    # dir; otherwise workspace stays None and the agent keeps the default cwd
    # (call-free tests are byte-identical). model_call sets PYTHONPATH to the
    # repo root under the workspace, so `from tools.run_X import ...` still works.
    run_dir = Path("runs") / str(run_id) if run_id else None
    workspace = None
    if run_dir is not None and run_dir.is_dir():
        workspace = (run_dir / "workspace").resolve()
        workspace.mkdir(exist_ok=True)
    with agent_workspace(workspace):
        data, _timing = call(
            FREE_STAGE_NAME,
            system_prompt,
            stage_input,
            SCHEMA,
            model=FREE_EXPERIMENTER_MODEL,
            extra_validator=_validate_free_result,
            capabilities=FULL,
        )
    result = {
        "goal": goal,
        "summary": data.get("summary"),
        "findings": data.get("findings") or [],
        "publishable": bool(data.get("publishable")),
        # What a human would have to supply for this to go further. A blocker
        # named precisely is a useful result — it is how the owner finds out that
        # ten minutes of their time unlocks the work — and its absence is what
        # lets an agent quietly solve an easier problem instead.
        "blocked_on": data.get("blocked_on") or [],
    }
    # Reusable file artifacts (increment 2): gate each declared producer by
    # actually re-emitting its file, so only reproducible files can later cross a
    # run boundary. Empty/absent -> [] and zero extra cost (the common case).
    if gate is None:
        from stages.reusable_artifacts import validate_reusable_artifact as gate
    result["reusable_artifacts"] = _gate_reusable_artifacts(
        data.get("reusable_artifacts") or [], gate)
    if run_dir is not None and run_dir.is_dir():
        # CONTROLLER RE-VERIFY (the wall is authoritative). A deterministic,
        # no-model pass re-runs each finding's saved artifact and its verdict —
        # not the agent's self-report — sets `verified`. It can only REMOVE
        # trust: a number the agent claimed verified that does not reproduce
        # drops the run's `publishable`; an honest unverified finding is a
        # caveat, not a claim, and never gates. verify_run writes the
        # director-readable verification.json.
        if verify is None:
            from stages.verification import verify_run
            verify = verify_run
        # The CLAIMS are the findings the agent kept as verified; each must
        # reproduce. A finding marked verified:false is an honest caveat, not a
        # claim — it is left untouched and never gates publishability.
        claimed = [(i, f) for i, f in enumerate(result["findings"])
                   if f.get("verified")]
        claims = _claims_from_findings([f for _, f in claimed], workspace)
        summary = verify(claims, run_id=str(run_id))  # writes verification.json
        by_index = {v.get("claim_index"): v for v in summary.get("verdicts", [])}
        any_reproduced = False
        for claim_i, (finding_i, _f) in enumerate(claimed):
            wall_verified = bool(by_index.get(claim_i, {}).get("verified"))
            if wall_verified:
                any_reproduced = True
            result["findings"][finding_i]["verified"] = wall_verified
        # A run stands if SOMETHING stood (owner ruling 2026-07-25). This used to
        # require EVERY claim to reproduce, so one shaky side-metric sank a run
        # carrying ten reproduced results and reported it as having achieved
        # nothing — verification gating execution instead of recording it. The
        # wall's authority is unchanged: it still overwrites each finding's
        # verified flag, and a failed claim is now an honest caveat rather than a
        # veto. No claims at all (an investigation that measured nothing) leaves
        # the agent's own judgment intact.
        if claimed:
            result["publishable"] = bool(result["publishable"]) and any_reproduced
        # MECHANISM REVIEW (advisory, BESIDE the wall — never inside it). The
        # wall proved each kept number re-executes; this one sealed pass asks
        # the question the wall cannot: does the code DO what the label SAYS?
        # (The proven blind spot: a hardcoded "swept" parameter or a mislabeled
        # baseline reproduces perfectly.) Its verdict travels only as a
        # `mechanism_review` caveat on the finding — it never touches
        # `verified` or `publishable`, and any failure inside it is swallowed:
        # an advisory pass may not take down a run.
        try:
            from stages.claim_review import (attach_mechanism_reviews,
                                             review_claim_mechanisms)
            reviews = review_claim_mechanisms(claims)
            if reviews:
                attach_mechanism_reviews(result["findings"], claimed, reviews)
        except Exception:  # noqa: BLE001
            pass
        (run_dir / "free_investigation.json").write_text(
            json.dumps(result, indent=2))
    return result
