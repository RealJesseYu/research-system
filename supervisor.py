"""
supervisor.py — the deterministic entry point. NO AI calls anywhere in this
file, ever.

PRIME DIRECTIVE (CLAUDE.md): the system is a FREE agent. A production run goes
STRAIGHT to the free experimenter — a full agent with every tool and connector
plus the substrate-tools catalogue — which investigates the domain directly and
writes a director-readable verification.json. There is NO gate-1 collapse, NO
static six-stage pipeline, NO registry gate.

The old deterministic six-stage relay (ideation -> experiment-design ->
fidelity-gate -> simulation -> thought-layer -> paper) with its three human
gates and bounded loop-back machinery was DELETED 2026-07-23 (the free-agent
purge — see docs/handoff_free_agent_purge.md). What remains here is the thin
run-id / journal / free-entry plumbing plus record_run_outcome bookkeeping.

Usage:
    python3 supervisor.py --mode human --domain "<goal>"
    python3 supervisor.py --mode auto  --domain "<goal>"
(default mode is human). The mode is carried on the baton and recorded; the
free experimenter is the same either way.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from baton import Baton
from memory.journal import blank_memory_active, journal_append


class Logger:
    """Writes every line to both the terminal and runs/<run_id>/log.txt."""

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def log(self, line: str) -> None:
        print(line)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def record_run_outcome(baton: Baton, how_far: str, retry_on_total_defer: int = 0) -> None:
    """Append one run_record to the journal: deterministic bookkeeping, no AI involved.

    `how_far` is e.g. "completed" or "halted at gate after_stage_2".
    `retry_on_total_defer` (19-lite/retry build): number of total-defer retries
    this run consumed; when >0 it is stamped into the record's extras and text.
    Default 0 keeps the record byte-identical to the pre-build shape.
    """
    iterate_decision = baton.payload.get("iterate_decision")
    text = f"run {baton.run_id} ({baton.mode} mode): {how_far}"
    extras = {"how_far": how_far}
    if iterate_decision is not None:
        text += f", iterate_decision={iterate_decision}"
        extras["iterate_decision"] = iterate_decision
    if retry_on_total_defer:
        text += f", retry_on_total_defer={retry_on_total_defer}"
        extras["retry_on_total_defer"] = retry_on_total_defer
    # STEP 28: the substrate-maturity hook (apply_substrate_maturity_hook)
    # stashes its signoff decision on the baton as a NON-payload attribute
    # (the payload schema is locked; this fact never travels the baton). When
    # a trust decision touched a non-mature substrate, every terminal
    # run_record carries needs_human_signoff prominently — in extras and in
    # the human-readable text. No hook / mature-only route => key absent =>
    # record byte-identical to the pre-Step-28 shape.
    signoff = getattr(baton, "_maturity_signoff", None)
    if isinstance(signoff, dict) and signoff.get("required"):
        rungs = signoff.get("substrates") or []
        extras["needs_human_signoff"] = True
        extras["needs_human_signoff_substrates"] = rungs
        text += f", needs_human_signoff=[{', '.join(rungs)}]"
    # Phase-1 Lane-2: blank-memory disclosure. When the ablation is active
    # (env BLANK_MEMORY=1, default off) the run_record carries blank_memory=true
    # prominently — both in extras and in the human-readable text — so the
    # record is never silently ambiguous about whether memory was starved.
    # Flag off (default): the key is not added and the record is byte-identical.
    if blank_memory_active():
        extras["blank_memory"] = True
        text = f"[BLANK_MEMORY] {text}"
    # SUBSTRATE CONSTRAINT disclosure. A run restricted to a subset of the
    # routable substrates must say so permanently: a reader comparing two runs
    # has to be able to tell "this instrument was never chosen" from "this
    # instrument was never offered". Unconstrained (the default) => the key is
    # absent and the record is byte-identical to the pre-constraint shape.
    # Never raises: a malformed constraint has already stopped the run long
    # before this point, and a record must not fail to be written.
    try:
        from tools import substrate_registry as registry

        constrained_to = registry.allowed_constraint()
    except Exception:  # noqa: BLE001
        constrained_to = None
    if constrained_to is not None:
        extras["allowed_substrates"] = sorted(constrained_to)
        text += f", allowed_substrates=[{', '.join(sorted(constrained_to))}]"
    # VERIFICATION (2026-07-20). The free experimenter stashes its verification
    # summary on the baton as a NON-payload attribute (the payload schema is
    # locked). Whether the run's numbers survived reproduction belongs in the
    # permanent record, not only in the log: a reader of the journal must be able
    # to tell a standing paper from one whose numbers did not reproduce.
    verification = getattr(baton, "_verification", None)
    if isinstance(verification, dict):
        extras["verification"] = {
            "publishable": verification.get("publishable"),
            "verified": verification.get("verified"),
            "total": verification.get("total"),
        }
        text += (
            f", verification={verification.get('verified')}/{verification.get('total')}"
            f" publishable={verification.get('publishable')}"
        )
    # PER-RUN COST (free-director Phase 1). This run is a fresh subprocess, so its
    # cost meter started at zero and now holds the WHOLE run's model spend (both
    # doors report into it). A dispatching parent cannot see a subprocess's
    # in-process meter, so the spend must be persisted here — it rides the
    # run_record extras exactly like verification, and read_run_result surfaces it
    # back to the PI. This is what turns a cost-cap from a launch-time estimate
    # into a ceiling the director can enforce against real spend (R-FD-2). A run
    # that dies without journaling leaves no record and no cost — correctly the
    # same has_run_record=False signal already used for outcome. Never raises: a
    # record must not fail to be written.
    try:
        import cost_meter

        snap = cost_meter.read()
        calls = snap.get("model_calls", {}).get("total", 0)
        tokens = sum(
            v for v in snap.get("tokens", {}).get("total", {}).values()
            if isinstance(v, int)
        )
        extras["cost"] = {"calls": calls, "tokens": tokens}
        # Text stays byte-identical when nothing was spent (the codebase's
        # minimal-text-unless-active convention, guarded by existing record-shape
        # tests); a real run always spends, so its text carries the cost.
        if calls or tokens:
            text += f", cost={calls} calls/{tokens} tokens"
    except Exception:  # noqa: BLE001
        pass
    journal_append({"run_id": baton.run_id, "kind": "run_record", "text": text, "extras": extras})


def run_exact_route(logger: Logger, baton: Baton, run_dir: Path, mode: str,
                    free_investigate=None) -> None:
    """The experiment path: a FREE experimenter — a full agent with NO substrate
    limit, every tool and connector on the table (PRIME DIRECTIVE, CLAUDE.md) —
    investigates the goal DIRECTLY and ends the run. It writes its own
    director-readable verification.json (findings + how to reproduce); a kept
    number is honest because the agent saves what re-runs it, never because a
    registry gated which tools it could touch.

    This is the sole production path (run_relay calls it unconditionally). The
    caged composition loop — compose_agent proposing scalar recipes over
    registered substrates — was PURGED 2026-07-23 (brick 4a); the static
    six-stage relay + gates were purged the same day. `free_investigate` is
    injected in tests; production defaults to
    stages.free_experimenter.run_free_investigation."""
    if free_investigate is None:
        from stages.free_experimenter import run_free_investigation as free_investigate

    # The research question: the gate-1 hypothesis' statement, else the domain.
    # A production run carries only {domain}; the chosen_hypothesis branch is
    # tolerated for a caller that hands one in. Never raises.
    chosen = baton.payload.get("chosen_hypothesis") or {}
    goal = (chosen.get("statement") if isinstance(chosen, dict) else None) \
        or baton.payload.get("domain")

    # IDEATION ROUTE: when a structured ideation pass produced ranked hypotheses,
    # hand the free agent the WHOLE ranked set as candidate leads (breadth
    # preserved — it chooses what to pursue and is not caged to one). Absent
    # (the default free path) => goal is the bare domain, unchanged.
    hyps = baton.payload.get("hypotheses")
    if isinstance(hyps, list) and hyps and not chosen:
        leads = "\n".join(
            f"  {i + 1}. {h.get('statement')}"
            for i, h in enumerate(hyps) if isinstance(h, dict) and h.get("statement")
        )
        if leads:
            goal = (
                f"{goal}\n\nA structured ideation pass produced these candidate "
                f"hypotheses, ranked strongest-first:\n{leads}\n\nInvestigate the "
                f"most promising one(s); you are not restricted to them."
            )

    logger.log(
        "FREE EXPERIMENTER: investigating the goal directly — no substrate cage, "
        "every tool and connector on the table (PRIME DIRECTIVE)"
    )
    result = free_investigate(goal, run_id=baton.run_id)
    findings = result.get("findings") or []
    verified = sum(1 for f in findings if f.get("verified"))
    publishable = bool(result.get("publishable"))
    logger.log(
        f"FREE EXPERIMENTER: {len(findings)} finding(s), {verified} verified, "
        f"publishable={publishable}"
    )
    # A declared blocker is surfaced loudly and durably: it is the one outcome a
    # human can act on directly, and the alternative to declaring it is an agent
    # quietly substituting a weaker problem.
    for b in result.get("blocked_on") or []:
        logger.log(
            f"BLOCKED ON: {b.get('need')} — {b.get('why')} | HUMAN ACTION: "
            f"{b.get('human_action')} | workaround: {b.get('workaround_used')}"
        )
    baton._verification = {"publishable": publishable, "verified": verified,
                           "total": len(findings)}
    how_far = ("completed free investigation (publishable)" if publishable
               else "completed free investigation (nothing publishable)")
    record_run_outcome(baton, how_far)
    logger.log(f"=== supervisor run {baton.run_id} {how_far} ===")


def _default_ideate(baton: Baton) -> Baton:
    """The Co-Scientist ideation apparatus (stage1_ideation, depth='full'):
    generation across four strategies -> six reviews -> Elo tournament ->
    evolution -> meta-review, up to ROUNDS rounds. Populates
    baton.payload['hypotheses'] with a ranked, pressure-tested set. Imported
    lazily so a run that does not use the route pays nothing for it."""
    from stages import stage1_ideation
    return stage1_ideation.run(baton, depth="full")


def run_relay(logger: Logger, baton: Baton, run_dir: Path, mode: str,
              free_investigate=None, ideate: bool = False, ideate_fn=None,
              paper: bool = False, paper_fn=None) -> None:
    """PRIME DIRECTIVE (CLAUDE.md): the FREE experimenter IS the system. A
    production run goes STRAIGHT to the free agent — a full agent with every tool
    and connector plus the substrate-tools catalogue — investigating the domain
    directly, with NO gate-1 collapse, NO static stages 2-5, NO registry gate.

    OPTIONAL IDEATION ROUTE (ideate=True): first run the Co-Scientist hypothesis
    apparatus and hand the free agent the tournament-ranked, evolution-refined
    hypotheses as candidate leads — strong hypotheses feeding a free
    investigation, NOT a gate (the agent sees the whole ranked set and is not
    restricted to one). Best-effort: an ideation failure falls back to the bare
    domain and the run continues. `ideate_fn` is injected in tests.

    The old deterministic six-stage relay + gates + loop-back machinery was
    DELETED 2026-07-23 (the free-agent purge). `free_investigate` is injected in
    tests; production defaults to run_free_investigation (via run_exact_route)."""
    logger.log(
        "FREE EXPERIMENTER (default entry): the free agent investigates the "
        "domain directly — no gate-1 / stages 2-5 pipeline (PRIME DIRECTIVE)"
    )
    if ideate:
        run_fn = ideate_fn or _default_ideate
        try:
            logger.log(
                "IDEATION ROUTE: generating ranked hypotheses via the "
                "Co-Scientist apparatus (generation x reviews x tournament x "
                "evolution)"
            )
            baton = run_fn(baton)
            n = len(baton.payload.get("hypotheses") or [])
            logger.log(
                f"IDEATION ROUTE: {n} ranked hypotheses produced — handing the "
                "full set to the free agent as candidate leads"
            )
        except Exception as e:  # noqa: BLE001 — ideation is best-effort
            logger.log(
                f"IDEATION ROUTE: ideation failed ({type(e).__name__}: {e}) — "
                "falling back to the bare domain; the run continues"
            )
    run_exact_route(logger, baton, run_dir, mode, free_investigate)

    # OPTIONAL PAPER ROUTE (paper=True): after the investigation and its
    # wall-verification, write up the run as a paper (+figures) from the
    # VERIFIED findings. Best-effort — a failed write-up never undoes the run.
    if paper:
        write_paper = paper_fn
        if write_paper is None:
            from stages.free_paper import write_free_paper as write_paper
        logger.log("PAPER ROUTE: writing up the verified findings as a paper")
        outcome = write_paper(baton.run_id)
        if outcome.get("paper_path"):
            logger.log(f"PAPER ROUTE: wrote {outcome['paper_path']}")
        else:
            logger.log(f"PAPER ROUTE: no paper written ({outcome.get('error')})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["human", "auto"], default="human")
    parser.add_argument("--domain", required=True, help="the research domain to seed this run with")
    # A caller that dispatches runs as subprocesses (the PI control layer) needs
    # to know the run dir BEFORE the child mints it, so it can read the result
    # back. An explicit --run-id lets the caller choose it; omitted, behavior is
    # byte-identical to before (make_run_id()). A caller-supplied id that
    # collides with an existing run dir is the caller's error — the dir is
    # created with exist_ok, the same as a make_run_id() collision would be.
    parser.add_argument(
        "--run-id",
        default=None,
        help="use this run id (and runs/<run-id>/) instead of a fresh "
        "timestamp; for a controller that must locate the run's evidence",
    )
    parser.add_argument(
        "--ideate",
        action="store_true",
        help="OPTIONAL route: run the Co-Scientist hypothesis apparatus first "
        "(generation x reviews x tournament x evolution) and seed the free agent "
        "with the ranked hypotheses. Heavier (many model calls); off by default.",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="OPTIONAL route: after the investigation, write it up as a paper "
        "(+figures) from the WALL-VERIFIED findings into runs/<id>/paper.md. "
        "Off by default.",
    )
    # Model selection: two (three) knobs. heavy = experimenter/director/paper/
    # hard judgments (default Opus); light = generation/reviews/evolution
    # (default Sonnet); triage = web search / sealed passes (default Haiku).
    # Each takes an alias (opus/sonnet/haiku) or a full model id.
    parser.add_argument(
        "--model-heavy", default=None,
        help="model for the HEAVY tier — the experimenter, director, paper, and "
        "hard judgments. Alias (opus/sonnet/haiku/fable) or a full id. "
        "Default opus.",
    )
    parser.add_argument(
        "--model-light", default=None,
        help="model for the LIGHT workhorse tier — hypothesis generation, the "
        "review chain, evolution. Default opus (owner ruling 2026-07-25: the "
        "tiers name roles, not costs). Pass 'sonnet' for a cheaper run.",
    )
    parser.add_argument(
        "--model-triage", default=None,
        help="model for the TRIAGE tier — web search and sealed low-stakes "
        "passes. Default opus, as above; pass 'haiku' for a cheaper run.",
    )
    args = parser.parse_args()

    # Set the model-tier knobs BEFORE anything that pins a model is imported
    # (every model-bearing module is imported lazily, downstream of here), so a
    # flag takes effect everywhere. Env vars RESEARCH_MODEL_HEAVY/LIGHT/TRIAGE do
    # the same and are the fully-reliable route (set before launch).
    import models
    for _tier, _val in (("heavy", args.model_heavy), ("light", args.model_light),
                        ("triage", args.model_triage)):
        if _val:
            models.set_tier(_tier, _val)

    run_id = args.run_id or make_run_id()
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = Logger(run_dir / "log.txt")

    logger.log(f"=== supervisor run {run_id} starting in mode={args.mode} ===")
    logger.log(
        f"MODELS: heavy={models.model_for('heavy')} "
        f"light={models.model_for('light')} triage={models.model_for('triage')}"
    )

    # The constraint is resolved and announced BEFORE the experimenter starts, so
    # a malformed one stops the run early and a valid one is the first thing a
    # reader of log.txt sees.
    from tools import substrate_registry as registry

    _constrained = registry.allowed_constraint()
    if _constrained is not None:
        logger.log(
            f"SUBSTRATE CONSTRAINT: this run may route only to "
            f"{sorted(_constrained)} — permitted set is "
            f"{list(registry.permitted_ids())} "
            f"(from {registry.ALLOWED_SUBSTRATES_ENV})"
        )

    baton = Baton(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=args.mode,
        payload={"domain": args.domain},
    )
    baton.validate()

    run_relay(logger, baton, run_dir, args.mode, ideate=args.ideate,
              paper=args.paper)


if __name__ == "__main__":
    main()
