"""study_deliverable.py — C1: package a finished study into ONE directory a
reader can open and use, without excavating run workspaces.

WHY THIS EXISTS. Experiment 1's head-to-head comparison (docs/debrief_experiment1.md
§5) found this system beat a single Claude Code session on accuracy and LOST to it
on "usable tomorrow": Claude Code shipped one clean directory with a README and
reproduce commands; this system's winning study left its deliverable (betainc.h)
scattered inside a 961 MB run workspace, with the paper in a different directory
and no README anywhere. A study that is right but unusable loses the comparison
that matters most to a reader who was not in the room.

WHO NAMES THE DELIVERABLE. Not the whole of `reusable_artifacts` — the study that
motivated this file produced 7 reusable artifacts across 5 moves and the actual
40 KB deliverable header, betainc.h, was not one of them (it was never declared a
producer). The file that answers the goal and the files that prove a headline
number are not the same thing as "a producer some phase happened to register."
So a FRESH model call, reading the FINISHED paper (same pattern as referee.py and
build_critic.py: a separate context reads completed work, nothing grades its own
breath), is given a Python-built CANDIDATE list per move workspace — never asked
to invent a path — and chooses. Python then does the mechanical, disciplined half:
copies EXACTLY the chosen files (nothing else), size-caps evidence so a chosen
848 MB dump can never make it into the package even if named, and writes the
README itself so the one document making claims about what is and is not here is
never the thing being described.

THE CANDIDATE LIST REUSES tools/run_code_snapshot.py RATHER THAN A SECOND
SELECTOR. Its `kept` output (size-capped, extension-whitelisted, symlink- and
credential-safe) is offered as the likely DELIVERABLE candidates; its `skipped`
entries that were rejected only for being big or off the code whitelist — never
the ones rejected for being credential-shaped, a dotfile, a symlink, or outside
the workspace — are offered as the likely EVIDENCE candidates (grid.bin, errs.bin,
sweep dumps: exactly the un-code-shaped files a headline number is recomputed
from). A file the snapshot selector would never expose to a git commit is never
offered to this model either.

WHERE IT LANDS. studies/<id>/deliverable/ — studies/<id>/ is already the study's
public-facing home (paper.md, figures, report.json all live there; only
director_workspace/ is scratch), so the deliverable joins the paper rather than
opening a fourth location a reader has to be told about.

NEVER FATAL, NEVER GATES. Exactly the referee/build_critic discipline: a failed
or skipped packaging pass returns {error} and leaves the study exactly as it was.
No model call anywhere touches stages/verification.py or the wall's verdicts —
this module only arranges files the wall (or the wall-fed paper) already vouched
for; it never re-judges a number. Kill switch: PACKAGE_DELIVERABLE=0.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from model_call import FULL, agent_workspace, call_stage_model
from models import model_for

DELIVERABLE_MODEL = model_for("heavy")
DELIVERABLE_STAGE = "study_deliverable"

# How much of each workspace's file listing reaches the prompt. The study this
# was built against has 5 moves and each workspace's `kept` list runs to a few
# dozen entries at most — this bounds a pathological workspace, not the normal
# case.
MAX_CANDIDATES_PER_WORKSPACE = 120

# Evidence caps — the reason this module exists at all. Measured on the study
# that motivated it: grid.bin (2 MB) + errs.bin (6.9 MB) is everything a third
# party needs to recompute the headline; advres.bin sits alongside them at
# 848 MB and is not needed for that. A single file above MAX_EVIDENCE_FILE_BYTES
# is refused outright; the running total is capped separately so five
# individually-small choices cannot add up to a second copy of the workspace.
# Both are far above what any headline recompute in this repo has needed and far
# below the multi-hundred-MB dumps that must never be blanket-copied.
MAX_EVIDENCE_FILE_BYTES = 20_000_000
MAX_EVIDENCE_TOTAL_BYTES = 75_000_000

# Deliverable files come from run_code_snapshot's own `kept` list, which already
# caps every entry at 1 MB (source) or 64 KB (data-shaped). These are a second,
# generous backstop, not the load-bearing rule.
MAX_DELIVERABLE_FILE_BYTES = 1_500_000
MAX_DELIVERABLE_TOTAL_BYTES = 20_000_000
MAX_DELIVERABLE_FILES = 40
MAX_EVIDENCE_FILES = 20

SYSTEM_PROMPT = """You are packaging a FINISHED study's deliverable so a competent person can open ONE directory tomorrow and use it, without digging through run workspaces. You did not run the investigation and you did not write the paper you are given — a fresh perspective on completed work, same reason a referee reads a paper it did not author.

You are given the finished paper, the study's verified findings, its reusable-artifact producers, and — for each move's workspace — two CANDIDATE lists you must choose from. You may NOT name any file that is not in these lists; anything else is refused.
  - "kept": small, code/text/figure-shaped files (already size-capped and extension-filtered). The deliverable itself — the header, the library, the design output — and the code that generates it (table generators, reference implementations) usually live here.
  - "other": everything else in that workspace, with byte sizes (data dumps, generated binaries, sweep output, build artifacts). The raw evidence someone would need to independently recompute the paper's headline number usually lives here — but so does a lot of intermediate junk nobody needs. Choose the MINIMUM sufficient set, not everything that touched the result. A multi-hundred-MB dump is very rarely what recomputing a headline actually requires; say why the ones you pick are enough.

You have Read and Bash. The candidates are grouped by "run_id" — for a move that is one of the study's own run_id (e.g. "study-xyz-m5"), its files are at runs/<run_id>/workspace/<path> from the repository root; for the pseudo run_id "director" they are at studies/<study_id>/director_workspace/<path> (the study's own scratch dir, where the paper/referee/critic regenerated things like an assembled region map). Open the files you are considering before deciding, especially before writing a reproduce command you have not actually confirmed against the code — the correct evidence for a headline is often narrower than "everything that touched it" (read the script that produced the number, not just its output file names).

Return ONLY JSON:
{
  "deliverable_summary": "<1-3 sentences: what this deliverable actually is>",
  "deliverable_files": [{"run_id": "<exact candidate run_id, incl. 'director' if applicable>", "path": "<exact candidate path>", "note": "<why this belongs — one sentence>"}],
  "evidence_files": [{"run_id": "<exact candidate run_id>", "path": "<exact candidate path>", "note": "<what this proves and why it is sufficient>"}],
  "reproduce_steps": ["<shell command>", "..."]
}
reproduce_steps are exact commands, in order, run from INSIDE the packaged directory once it exists: every deliverable_files entry lands there as its bare filename, every evidence_files entry lands under evidence/<bare filename> (if two chosen files share a basename, the second is prefixed run_id__ — avoid choosing duplicate basenames where you can). Reference only the bare/evidence-prefixed names your commands will actually find. Do not invent a command you have not verified is what the code actually needs — read it first.

deliverable_files or evidence_files MAY be empty lists if nothing in the candidates genuinely qualifies (do not force a choice), but say so honestly in deliverable_summary rather than reaching for something irrelevant."""


def _validate(data: dict) -> list:
    errs = []
    if not str(data.get("deliverable_summary") or "").strip():
        errs.append("'deliverable_summary' must be a non-empty sentence.")
    for key in ("deliverable_files", "evidence_files"):
        v = data.get(key)
        if not isinstance(v, list):
            errs.append(f"'{key}' must be a list (may be empty).")
            continue
        for i, item in enumerate(v):
            if not (isinstance(item, dict) and str(item.get("run_id") or "").strip()
                    and str(item.get("path") or "").strip()):
                errs.append(f"{key}[{i}] must be an object with non-empty "
                            "'run_id' and 'path', copied EXACTLY from a candidate.")
    if not isinstance(data.get("reproduce_steps"), list):
        errs.append("'reproduce_steps' must be a list of shell command strings "
                    "(may be empty).")
    return errs


SCHEMA = {"required": ["deliverable_summary", "deliverable_files", "evidence_files",
                       "reproduce_steps"]}


def _enabled() -> bool:
    return os.environ.get("PACKAGE_DELIVERABLE", "").strip() != "0"


# ---------------------------------------------------------------------------
# Candidate lists — built entirely from tools/run_code_snapshot.py's own
# classification, never a second selector.
# ---------------------------------------------------------------------------

# The pseudo workspace-id for the study's OWN scratch dir (studies/<id>/
# director_workspace/) — where the paper agent, referee and build critic
# actually regenerate producers (region maps, assembled tables) while writing
# up the study. tools/run_code_snapshot.py's own `workspaces()` helper already
# treats runs/*/workspace and studies/*/director_workspace as the same kind of
# thing; a real deliverable doc like region_map_assembled.md lives ONLY there,
# never inside a single move's workspace, so leaving it out would miss exactly
# the kind of file this module exists to find.
DIRECTOR_WORKSPACE_ID = "director"


def _workspace_root(study: Any, workspace_id: str) -> Optional[Path]:
    """The on-disk root for a workspace id, or None if it does not exist.
    `study` is threaded through explicitly (rather than resolved from a module-
    global) so this stays correct if a study's studies_root is ever non-default."""
    if workspace_id == DIRECTOR_WORKSPACE_ID:
        root = study.dir / "director_workspace"
    else:
        root = Path("runs") / workspace_id / "workspace"
    return root if root.is_dir() else None


def _candidate_workspaces(study: Any) -> list:
    """(workspace_id, root) for every move workspace still on disk, in arc
    order, de-duplicated, PLUS the study's own director_workspace last if it
    exists. A fan/sub-study move whose run_id does not resolve to
    runs/<run_id>/workspace simply contributes no candidates — packaging
    degrades gracefully rather than guessing at a different shape."""
    from pi_agent.study import study_arc

    out, seen = [], set()
    for e in study_arc(study):
        run_id = e.get("run_id")
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        root = _workspace_root(study, run_id)
        if root is not None:
            out.append((run_id, root))
    director_root = _workspace_root(study, DIRECTOR_WORKSPACE_ID)
    if director_root is not None:
        out.append((DIRECTOR_WORKSPACE_ID, director_root))
    return out


def _legit_data_skip(reason: str) -> bool:
    """True for a run_code_snapshot skip reason that means 'not code-shaped or
    too big for code', i.e. a legitimate evidence candidate. False for every
    safety-motivated skip (credential-shaped name, dotfile, symlink, escapes the
    workspace, unreadable) — those must never reach a model as a choice, full
    stop, regardless of what packaging is trying to do."""
    return reason.startswith("extension ") or "cap (" in reason


def workspace_candidates(study: Any) -> dict:
    """{workspace_id: {"kept": [...], "other": [...]}} — workspace_id is a move's
    run_id, or DIRECTOR_WORKSPACE_ID for the study's own scratch dir. Pure read
    of on-disk state; makes no judgement about what matters."""
    from tools.run_code_snapshot import select

    out = {}
    for run_id, root in _candidate_workspaces(study):
        kept, skipped = select(root)
        kept_list = []
        for rel in kept:
            try:
                size = (root / rel).stat().st_size
            except OSError:
                continue
            kept_list.append({"path": str(rel), "bytes": size})
        other_list = []
        for rel, reason in skipped:
            if not _legit_data_skip(reason):
                continue
            try:
                size = (root / rel).stat().st_size
            except OSError:
                continue
            other_list.append({"path": str(rel), "bytes": size,
                               "skipped_because": reason})
        other_list.sort(key=lambda d: -d["bytes"])
        budget = MAX_CANDIDATES_PER_WORKSPACE - len(kept_list)
        if budget < len(other_list):
            other_list = other_list[: max(0, budget)]
        out[run_id] = {"kept": kept_list, "other": other_list}
    return out


def _candidate_set(candidates: dict) -> set:
    return {
        (run_id, c["path"])
        for run_id, groups in candidates.items()
        for group in ("kept", "other")
        for c in groups[group]
    }


# ---------------------------------------------------------------------------
# Resolving choices to real files, copying, README.
# ---------------------------------------------------------------------------

def _resolve(study: Any, workspace_id: str, relpath: str):
    """Absolute Path + size for a chosen (workspace_id, path), or None if it no
    longer exists / would escape its own workspace. Defense in depth: the
    candidate set already proves this path was inside the workspace when
    listed, but files can vanish between listing and copy (a run cleaning up
    its own scratch), so this re-checks rather than trusting the earlier proof."""
    root = _workspace_root(study, workspace_id)
    if root is None:
        return None
    root = root.resolve()
    src = (root / relpath).resolve()
    try:
        if not src.is_relative_to(root) or not src.is_file():
            return None
        return src, src.stat().st_size
    except OSError:
        return None


def _assign_final_names(chosen: list) -> list:
    """Bare basename, unless two chosen files collide, in which case every entry
    after the first sharing that basename is prefixed run_id__. Deterministic
    (arc/candidate order), so it never depends on dict iteration order across
    Python versions."""
    seen = {}
    out = []
    for e in chosen:
        base = Path(e["path"]).name
        if base not in seen:
            seen[base] = True
            out.append({**e, "final_name": base})
        else:
            out.append({**e, "final_name": f"{e['run_id']}__{base}"})
    return out


def _drop_src(e: dict) -> dict:
    """An entry without the internal-only `_src` Path — every entry that leaves
    this module (into a skip list, the manifest, the README) must be JSON- and
    string-safe, never carrying the live filesystem handle."""
    return {k: v for k, v in e.items() if k != "_src"}


def _copy_chosen(study: Any, chosen: list, dest_dir: Path, *, max_file_bytes: int,
                 max_total_bytes: int, max_files: int) -> tuple:
    """Copy files smallest-first so a cap is hit only after keeping as much
    genuinely-small evidence as possible, never by letting one large file starve
    several small ones that would otherwise have fit. Returns (copied, skipped).
    Never creates dest_dir when nothing ends up copied — an honest "nothing was
    packaged" must not leave a stray empty directory behind."""
    resolved = []
    skipped = []
    for e in chosen:
        got = _resolve(study, e["run_id"], e["path"])
        if got is None:
            skipped.append({**e, "reason": "no longer resolves inside its workspace"})
            continue
        src, size = got
        resolved.append({**e, "_src": src, "bytes": size})
    resolved.sort(key=lambda e: e["bytes"])

    copied = []
    total = 0
    dir_made = False
    for e in resolved:
        if len(copied) >= max_files:
            skipped.append(_drop_src({**e, "reason": f"over the {max_files}-file "
                                          "cap for this section"}))
            continue
        if e["bytes"] > max_file_bytes:
            skipped.append(_drop_src({**e, "reason": f"{e['bytes']:,} bytes over "
                                          f"the {max_file_bytes:,}-byte cap"}))
            continue
        if total + e["bytes"] > max_total_bytes:
            skipped.append(_drop_src({**e, "reason": "would exceed this section's "
                                          f"{max_total_bytes:,}-byte total cap"}))
            continue
        if not dir_made:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dir_made = True
        dest = dest_dir / e["final_name"]
        try:
            shutil.copyfile(e["_src"], dest)
        except OSError as exc:
            skipped.append(_drop_src({**e, "reason": f"copy failed ({type(exc).__name__})"}))
            continue
        total += e["bytes"]
        copied.append(_drop_src(e))
    return copied, skipped


def _filter_to_candidates(entries: list, candidate_set: set) -> tuple:
    """Split model-chosen entries into (real, hallucinated). A choice not present
    in the candidate set exactly as offered is dropped, never re-asked — the same
    silent-skip discipline study_paper.py uses for a named-but-unwritten figure."""
    real, bad = [], []
    for e in entries:
        key = (e.get("run_id"), e.get("path"))
        (real if key in candidate_set else bad).append(e)
    return real, bad


def _substitute_final_names(steps: list, renamed: dict) -> list:
    """If a collision forced a rename, rewrite the agent's reproduce commands so
    they still refer to a file that actually exists under the new name. `renamed`
    maps original basename -> final basename; only entries that actually changed
    are present, so the common (no collision) case never touches the text."""
    if not renamed:
        return list(steps)
    out = []
    for s in steps:
        for old, new in renamed.items():
            if old != new:
                s = s.replace(old, new)
        out.append(s)
    return out


def _render_readme(study: Any, evidence: dict, data: dict, deliverable_copied: list,
                   deliverable_skipped: list, evidence_copied: list,
                   evidence_skipped: list, reproduce_steps: list) -> str:
    """Written entirely by Python, never by the model that chose the files — the
    one document making claims about what is and is not in this directory must
    not be authored by the party being described (same discipline as
    build_critic's _block and study_paper's correction block)."""
    lines = [f"# {study.study_id} — deliverable\n\n",
            "Assembled automatically at study close. Every file below was copied "
            "byte-for-byte from the run workspace that produced it; nothing here "
            "was regenerated, edited, or summarized.\n\n",
            "## What this is\n\n", f"{data.get('deliverable_summary', '')}\n\n",
            f"**Goal:** {study.goal}\n\n"]

    lines.append("## Deliverable files\n\n")
    if deliverable_copied:
        lines.append("| file | source | notes |\n|---|---|---|\n")
        for e in deliverable_copied:
            note = (e.get("note") or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| `{e['final_name']}` | {e['run_id']}:`{e['path']}` | {note} |\n")
    else:
        lines.append("_None were named as deliverable files._\n")
    lines.append("\n")

    lines.append("## Evidence (recompute the headline)\n\n")
    if evidence_copied:
        lines.append("| file | source | bytes | notes |\n|---|---|---|---|\n")
        for e in evidence_copied:
            note = (e.get("note") or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| `evidence/{e['final_name']}` | {e['run_id']}:`{e['path']}` "
                        f"| {e['bytes']:,} | {note} |\n")
    else:
        lines.append("_None were named as evidence files._\n")
    lines.append("\n")

    lines.append("## Reproduce\n\n")
    if reproduce_steps:
        lines.append("As reported by the packaging step's review agent, from "
                    "inside this directory. **Not independently executed by the "
                    "packaging step itself** — check before relying on it.\n\n")
        lines.append("```sh\n" + "\n".join(reproduce_steps) + "\n```\n\n")
    else:
        lines.append("_No reproduce steps were recorded._\n\n")

    lines.append("## Paper\n\n")
    lines.append("See [`../paper.md`](../paper.md)"
                + (" and `../paper.pdf`" if (study.dir / "paper.pdf").is_file() else "")
                + " for the full write-up, including the referee review and build "
                  "critique appended to it, if either ran.\n\n")

    skipped_total = len(deliverable_skipped) + len(evidence_skipped)
    lines.append("## Provenance and what was left out\n\n")
    lines.append(f"Copied from `{study.dir}` (studies/ is evidence, gitignored — "
                "this directory is the exception meant to be handed to a reader "
                "directly). ")
    if skipped_total:
        lines.append(f"{skipped_total} candidate file(s) the review agent named were "
                    "**not** copied (size cap, vanished since listing, or a "
                    "duplicate no-op) — see `deliverable_manifest.json` beside this "
                    "README for the full list and each reason.\n\n")
    else:
        lines.append("Every file the review agent named was copied.\n\n")

    verified = evidence.get("verified_findings") or []
    if verified:
        lines.append("## Verified findings this deliverable rests on\n\n")
        lines.append("Independently reproduced by this system's verification wall "
                    "(not this packaging step, and not the model that chose the "
                    "files above):\n\n")
        for f in verified[:15]:
            lines.append(f"- {f.get('label')}: **{f.get('value')}**\n")
        lines.append("\n")

    return "".join(lines)


def package_study_deliverable(study: Any, *, call=None) -> dict:
    """Assemble studies/<id>/deliverable/. Returns
    {deliverable_dir, deliverable_files, evidence_files, skipped, readme_path}
    on success, else {error}. Never raises — a packaging failure leaves the study
    exactly as it was; the paper and its wall-verified findings stand regardless."""
    if not _enabled():
        return {"error": "packaging disabled (PACKAGE_DELIVERABLE=0)"}
    call = call or call_stage_model

    if not (study.dir / "paper.md").is_file():
        return {"error": "no paper.md to package around"}

    try:
        from stages.study_paper import collect_study_evidence
        evidence = collect_study_evidence(study)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not read the study: {type(e).__name__}: {e}"}

    try:
        candidates = workspace_candidates(study)
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not list workspace candidates: {type(e).__name__}: {e}"}

    if not any(g["kept"] or g["other"] for g in candidates.values()):
        return {"error": "no move workspaces are still on disk to package from"}

    try:
        paper_text = (study.dir / "paper.md").read_text()
    except OSError:
        paper_text = ""

    stage_input = {
        "goal": study.goal,
        "paper": paper_text[:60000],
        "verified_findings": evidence.get("verified_findings"),
        "reusable_artifacts": evidence.get("reusable_artifacts"),
        "workspace_candidates": candidates,
    }

    from pi_agent.study import study_scratch_dir
    try:
        scratch = study_scratch_dir(study)
    except Exception:  # noqa: BLE001
        scratch = None

    with agent_workspace(scratch):
        try:
            data, _t = call(DELIVERABLE_STAGE, SYSTEM_PROMPT, stage_input, SCHEMA,
                            model=DELIVERABLE_MODEL, extra_validator=_validate,
                            capabilities=FULL)
        except Exception as e:  # noqa: BLE001
            return {"error": f"deliverable selection failed: {type(e).__name__}: {e}"}

    candidate_set = _candidate_set(candidates)
    deliv_real, deliv_bad = _filter_to_candidates(
        data.get("deliverable_files") or [], candidate_set)
    ev_real, ev_bad = _filter_to_candidates(
        data.get("evidence_files") or [], candidate_set)

    deliv_named = _assign_final_names(deliv_real)
    ev_named = _assign_final_names(ev_real)

    dest = study.dir / "deliverable"
    deliv_copied, deliv_skipped = _copy_chosen(
        study, deliv_named, dest,
        max_file_bytes=MAX_DELIVERABLE_FILE_BYTES,
        max_total_bytes=MAX_DELIVERABLE_TOTAL_BYTES,
        max_files=MAX_DELIVERABLE_FILES)
    ev_copied, ev_skipped = _copy_chosen(
        study, ev_named, dest / "evidence",
        max_file_bytes=MAX_EVIDENCE_FILE_BYTES,
        max_total_bytes=MAX_EVIDENCE_TOTAL_BYTES,
        max_files=MAX_EVIDENCE_FILES)

    for e in deliv_bad + ev_bad:
        (deliv_skipped if e in (data.get("deliverable_files") or []) else ev_skipped) \
            .append({**e, "reason": "not one of the offered candidates — refused"})

    renamed = {e["path"].rsplit("/", 1)[-1]: e["final_name"]
              for e in deliv_copied + ev_copied
              if Path(e["path"]).name != e["final_name"]}
    reproduce_steps = _substitute_final_names(
        data.get("reproduce_steps") or [], renamed)

    if not deliv_copied and not ev_copied:
        # Honest no-op, not an empty directory nobody asked for. paper.md still
        # stands as the study's deliverable; packaging simply had nothing to add.
        return {"error": "nothing was copied — the review agent named no files "
                         "from the offered candidates (or none survived the caps); "
                         "see deliverable_summary: "
                         f"{data.get('deliverable_summary')!r}"}

    try:
        dest.mkdir(parents=True, exist_ok=True)
        readme = _render_readme(study, evidence, data, deliv_copied, deliv_skipped,
                                ev_copied, ev_skipped, reproduce_steps)
        (dest / "README.md").write_text(readme)
        manifest = {
            "study_id": study.study_id,
            "deliverable_summary": data.get("deliverable_summary"),
            "deliverable_files": deliv_copied,
            "deliverable_skipped": deliv_skipped,
            "evidence_files": ev_copied,
            "evidence_skipped": ev_skipped,
            "reproduce_steps": reproduce_steps,
            "candidates_offered": {
                run_id: {"kept": len(g["kept"]), "other": len(g["other"])}
                for run_id, g in candidates.items()
            },
        }
        (dest / "deliverable_manifest.json").write_text(json.dumps(manifest, indent=2))
    except OSError as e:
        return {"error": f"could not write the package: {type(e).__name__}: {e}"}

    return {
        "deliverable_dir": str(dest),
        "readme_path": str(dest / "README.md"),
        "deliverable_files": [e["final_name"] for e in deliv_copied],
        "evidence_files": [e["final_name"] for e in ev_copied],
        "skipped": len(deliv_skipped) + len(ev_skipped),
    }


def package_study_deliverable_by_id(study_id: str, *, studies_root: Optional[Path] = None,
                                    call=None) -> dict:
    """Convenience entry: load the study by id and package it. Never raises."""
    from pi_agent.study import STUDIES_ROOT, load_study
    try:
        study = load_study(study_id, studies_root=studies_root or STUDIES_ROOT)
    except Exception as e:  # noqa: BLE001
        return {"error": f"no such study {study_id!r}: {type(e).__name__}: {e}"}
    return package_study_deliverable(study, call=call)
