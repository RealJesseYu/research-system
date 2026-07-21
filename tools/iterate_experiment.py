"""
iterate_experiment — the bounded author -> run -> diagnose -> re-author loop.

WHAT THIS IS. run_python_experiment runs caller-authored code ONCE and returns
an honest summary: valid=True with a qoi, or valid=False with a bounded
diagnostic (a crash's stderr tail, a missing-metric note, a timeout). That
single shot is correct and stays untouched — the wrapper has no AI inside it and
never will. What it cannot do is what a person at a laptop does: read the
failure, fix the code, and run again. THIS module is that loop, and ONLY that
loop.

WHY IT LIVES HERE AND NOT IN THE WRAPPER. The loop needs something that can
author code from a failure, which is a judgment — a model. The wrapper must stay
deterministic and model-free (the summarize-at-the-wrapper invariant depends on
it). So the loop sits one level up, exactly where model_call.py's re-ask loop
already sits: call_stage_model re-asks up to 3 times when a reply is malformed
JSON, feeding the validation error back each time. This is the SAME pattern with
a second trigger — the reply parsed fine but the experiment it described did not
produce a valid result — so the honest execution diagnostic is fed back and the
code is re-authored. Bounded attempts, and ONLY the wrapper's already-bounded
summary flows back (never raw stdout): both invariants hold.

MODEL-FREE BY CONSTRUCTION. This module calls no model. The code author is an
injected callable (`author_fn`) — the same dependency-injection seam
substrate_dispatch/dispatch use for command_builder/record_reader. The
production wiring passes a Sonnet-backed author; tests pass fakes. The runner is
injected too (defaults to the real wrapper) so the loop is unit-testable with no
container.

    author_fn(attempt: int, prior_diagnostic: str | None) -> str
        attempt is 1-based; prior_diagnostic is None on the first attempt and
        the previous run's bounded diagnostic on every retry. Returns the code
        string for this attempt.

Return (the ONLY thing that leaves this module):
    {
      "outcome": "solved" | "gave_up",
      "attempts": int,                 # how many runs it took / used
      "summary": <the wrapper summary of the LAST run>,   # valid iff solved
      "qoi": float | None,             # convenience: summary["qoi"]
      "trail": [                       # one entry per attempt, evidence
        {"attempt": int, "valid": bool, "qoi": float | None,
         "diagnostics": str, "runtime_s": float, "code_bytes": int},
        ...
      ],
    }
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from tools.run_python_experiment import run_python_experiment

# Mirrors model_call.py's re-ask bound. A budget, not a guarantee: the loop
# stops at the first valid run, or gives up honestly after this many tries.
DEFAULT_MAX_ATTEMPTS = 3


class ExperimentIterationError(ValueError):
    """The loop was called with an unusable configuration (not an experiment
    failure — those come back as outcome='gave_up', never as a raise)."""


def iterate_experiment(
    quantity: str,
    author_fn: Callable[[int, Optional[str]], str],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout_s: Optional[int] = None,
    runner: Callable[[dict], dict] = run_python_experiment,
) -> dict:
    """Author code, run it once through `runner`, and — if the run did not
    produce a valid result — feed the honest diagnostic back to `author_fn` and
    re-author, up to `max_attempts` times. Returns the first valid run's
    summary, or an honest give-up with the full attempt trail. Never fabricates
    a qoi and never raises for an experiment that simply keeps failing.
    """
    if not isinstance(quantity, str) or not quantity.strip():
        raise ExperimentIterationError("'quantity' must be a non-empty string")
    if not callable(author_fn):
        raise ExperimentIterationError("'author_fn' must be callable")
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ExperimentIterationError(
            f"'max_attempts' must be a positive int, got {max_attempts!r}")

    quantity = quantity.strip()
    trail: list[dict] = []
    prior_diagnostic: Optional[str] = None
    summary: dict = {}

    for attempt in range(1, max_attempts + 1):
        code = author_fn(attempt, prior_diagnostic)
        if not isinstance(code, str) or not code.strip():
            raise ExperimentIterationError(
                f"author_fn returned no code on attempt {attempt} "
                f"(got {type(code).__name__})")

        spec: dict[str, Any] = {"code": code, "quantity": quantity}
        if timeout_s is not None:
            spec["timeout_s"] = timeout_s
        summary = runner(spec)

        trail.append({
            "attempt": attempt,
            "valid": bool(summary.get("valid")),
            "qoi": summary.get("qoi"),
            "diagnostics": summary.get("diagnostics", ""),
            "runtime_s": summary.get("runtime_s"),
            "code_bytes": len(code.encode("utf-8")),
        })

        if summary.get("valid"):
            return {
                "outcome": "solved",
                "attempts": attempt,
                "summary": summary,
                "qoi": summary.get("qoi"),
                "trail": trail,
            }

        # Not valid: carry the bounded diagnostic forward for the next author.
        prior_diagnostic = summary.get("diagnostics", "") or "(no diagnostic)"

    return {
        "outcome": "gave_up",
        "attempts": max_attempts,
        "summary": summary,
        "qoi": None,
        "trail": trail,
    }
