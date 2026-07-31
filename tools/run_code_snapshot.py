"""tools/run_code_snapshot.py — WHICH files a run's workspace would contribute
to a code commit. Selection only; this module NEVER touches git.

WHY IT STOPS HERE. The owner asked for the code a run produces to be committed
automatically. Choosing the files is the half that can be decided on evidence
and proven offline; choosing WHERE those commits land (a dedicated branch, an
orphan ref namespace, the current branch) was a ruling, and a wrong auto-commit
scheme is worse than none. So this file answers "what" and nothing here writes a
ref, an object, an index, or a working-tree file.

That ruling was made on 2026-07-30 (a dedicated `run-artifacts` branch, plumbing
only) and tools/run_artifacts_commit.py answers "where". The separation stays:
the writer IMPORTS this module and has no opinion about files, so a selection
change is made here and nowhere else. A test holds that line in both directions.

Run it to see exactly what a commit WOULD contain:

    venv/bin/python3 -m tools.run_code_snapshot runs/<id>/workspace
    venv/bin/python3 -m tools.run_code_snapshot --all
    venv/bin/python3 -m tools.run_code_snapshot --all --skips

THE RULES, and the evidence behind each.

1. WHITELIST EXTENSIONS, never blacklist. A blacklist is wrong the first time a
   run invents a file type nobody anticipated, and it is wrong in the direction
   that leaks.

2. PRUNE DIRECTORIES FIRST, then apply the whitelist. Measured on this repo:
   two run workspaces contain a .venv, and the workspaces hold 5,020 .py files
   in total — the overwhelming majority of which are installed packages, not
   the agent's work. An extension whitelist alone would have swept an entire
   virtualenv into the history.

3. A SIZE CAP. Source the agent wrote is small. A 40 MB .json is a data dump,
   and data belongs in the run evidence, not in the code history.

4. A NAME DENYLIST ON TOP OF THE WHITELIST, for the few things that are
   textual, plausible-looking, and must never be committed: .env, private keys,
   credential files. Belt and braces — none of their extensions are on the
   whitelist either.

5. NOTHING OUTSIDE THE GIVEN WORKSPACE. Every kept path is resolved and must
   still be under the root; a symlink pointing out is skipped, not followed.

6. FIGURES ONLY FROM A DELIVERABLE (owner ruling, 2026-07-30). .png/.svg/.pdf
   are kept under studies/<id>/deliverable/ — the curated boundary
   stages/study_deliverable.py already assembles — and skipped everywhere else.
   MEASURED on this tree the day the ruling was made: across 87 workspaces the
   figure-class extensions were 380 files / 189.8 MB, of which 306 files /
   178.3 MB were .pdf — papers the agent FETCHED off the web while working, not
   anything it produced. Alongside them sit scratch plots regenerated a dozen
   times a run. The deliverable's 11 figures / 1.2 MB are the ones a paper
   actually cites. The tradeoff being accepted is written down in
   docs/memo_auto_commit_run_code.md: PNGs do not delta-compress, so figures
   grow this history in undeltifiable blobs, and the deliverable boundary is
   where that cost buys something.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Source-like extensions an agent actually authors, plus the small text
# artifacts that make a workspace readable later (notes, manifests, figures).
# Deliberately conservative: anything not listed is skipped and REPORTED, so a
# missing type shows up as a skip line rather than as a silent loss.
KEPT_EXTENSIONS = frozenset({
    # code
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".f", ".f90", ".jl", ".r",
    ".rs", ".go", ".js", ".ts", ".sh", ".m", ".sql", ".lua",
    # build / declaration
    ".toml", ".cfg", ".ini", ".mk", ".cmake", ".yaml", ".yml",
    # small structured results and notes
    ".json", ".csv", ".tsv", ".md", ".txt", ".rst", ".tex", ".bib",
    # figures a paper cites — DELIVERABLE ONLY, see FIGURE_EXTENSIONS below
    ".png", ".svg", ".pdf",
})

# Kept only under a deliverable root (rule 6). Elsewhere these are scratch plots
# and fetched papers, and they are the bytes that do not delta-compress.
FIGURE_EXTENSIONS = frozenset({".png", ".svg", ".pdf"})

# The directory name stages/study_deliverable.py assembles into. A root with
# this name is the curated boundary figures are kept from.
DELIVERABLE_DIRNAME = "deliverable"

# Extensionless files that are still source-like by convention.
KEPT_NAMES = frozenset({"Makefile", "makefile", "Dockerfile", "CMakeLists.txt"})

# Pruned wholesale, at any depth. These hold installed or generated content,
# never the agent's own work.
PRUNED_DIRS = frozenset({
    ".venv", "venv", "env", "site-packages", "node_modules", "__pycache__",
    ".git", ".hg", ".svn", ".tox", ".mypy_cache", ".pytest_cache",
    ".ipynb_checkpoints", "build", "dist", ".eggs", "postProcessing",
})

# Directory-name SUFFIXES pruned wholesale (packaging metadata).
PRUNED_DIR_SUFFIXES = ("egg-info", "dist-info")

# Never committed, whatever their extension says.
DENIED_NAMES = frozenset({
    ".env", ".env.local", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credentials.json", ".netrc", ".npmrc", ".pypirc",
    "mcp_servers.json",
})
DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")

# Source the agent wrote is small. Above this a file is data, and data lives in
# the run evidence.
MAX_FILE_BYTES = 1_000_000

# TWO CAPS, because one cap answered the wrong question. Measured over all 61
# workspaces in this tree: a single 1 MB cap kept 560 files / 30.3 MB, of which
# 23.1 MB was 146 .json result dumps and only 1.7 MB was the 317 .py files that
# are the actual point. Those dumps are already run evidence; a code history is
# not where they belong. A 64 KB cap on the data-shaped extensions gives 503
# files / 7.0 MB — every source file kept, the dumps left where they already
# live. Re-derive with `--all` before changing either number.
DATA_EXTENSIONS = frozenset({".json", ".csv", ".tsv", ".txt", ".dat"})
MAX_DATA_BYTES = 65_536

# A dotfile is configuration or state, not authored source. Skipped by default
# so the denylist above never has to be exhaustive.
SKIP_DOTFILES = True


def _pruned_dir(name: str) -> bool:
    return name in PRUNED_DIRS or name.endswith(PRUNED_DIR_SUFFIXES)


def _denied_name(name: str) -> bool:
    lower = name.lower()
    return lower in DENIED_NAMES or lower.endswith(DENIED_SUFFIXES)


def is_deliverable_root(root: Path) -> bool:
    """Whether `root` is a packaged deliverable — the curated boundary figures
    are kept from. Name-based on purpose: the caller may point this at a copy in
    a temp dir, and the thing that makes a directory a deliverable is that
    study_deliverable.py assembled it under that name."""
    return Path(root).name == DELIVERABLE_DIRNAME


def classify(path: Path, root: Path, figures: bool = None) -> tuple[bool, str]:
    """(keep, reason). Pure apart from a stat() for the size; no git, no writes.

    `reason` is empty on a keep and names the rule on a skip, because the point
    of a dry run is that a human can see WHY a file was left out.

    `figures` says whether figure-class files are kept from this root; None
    (the default) derives it from the root being a deliverable."""
    name = path.name
    if figures is None:
        figures = is_deliverable_root(root)
    if _denied_name(name):
        return False, "denylisted name (credential-shaped)"
    if SKIP_DOTFILES and name.startswith("."):
        return False, "dotfile (config or state, not authored source)"
    if path.is_symlink():
        return False, "symlink (never followed out of the workspace)"
    suffix = path.suffix.lower()
    if name not in KEPT_NAMES and suffix not in KEPT_EXTENSIONS:
        return False, f"extension {suffix or '(none)'} not on the whitelist"
    if suffix in FIGURE_EXTENSIONS and not figures:
        return False, (f"{suffix} outside a deliverable (scratch plot or fetched "
                       "page; figures are kept from studies/<id>/deliverable/)")
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"unreadable ({type(exc).__name__})"
    cap = MAX_DATA_BYTES if suffix in DATA_EXTENSIONS else MAX_FILE_BYTES
    if size > cap:
        kind = "result dump, already run evidence" if cap == MAX_DATA_BYTES \
            else "data, not source"
        return False, f"{size:,} bytes over the {cap:,} cap ({kind})"
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return False, "resolves outside the workspace"
    return True, ""


def select(root: Path, figures: bool = None) -> tuple[list, list]:
    """(kept, skipped) for one workspace. kept is a sorted list of paths
    relative to `root`; skipped is a list of (relative path, reason).

    `figures` overrides the deliverable-derived figure rule; None means derive.

    Never raises on a missing or unreadable root — a snapshot of nothing is an
    empty snapshot, not a failure."""
    root = Path(root)
    if figures is None:
        figures = is_deliverable_root(root)
    kept: list = []
    skipped: list = []
    if not root.is_dir():
        return kept, skipped
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _pruned_dir(d))
        for filename in sorted(filenames):
            full = Path(dirpath) / filename
            rel = full.relative_to(root)
            keep, reason = classify(full, root, figures=figures)
            (kept if keep else skipped).append(rel if keep else (rel, reason))
    kept.sort()
    return kept, skipped


def workspaces(project_root: Path) -> list:
    """Every directory a run or study produced that a code snapshot draws from,
    sorted. Three shapes: runs/<id>/workspace, studies/<id>/director_workspace,
    and studies/<id>/deliverable — the last added 2026-07-30 by owner ruling,
    because the packaged deliverable is the curated boundary (and the only place
    figures are kept from; see rule 6)."""
    found = []
    for pattern in ("runs/*/workspace", "studies/*/director_workspace",
                    f"studies/*/{DELIVERABLE_DIRNAME}"):
        found.extend(p for p in project_root.glob(pattern) if p.is_dir())
    return sorted(found)


def _report(root: Path, show_skips: bool) -> tuple:
    kept, skipped = select(root)
    total = 0
    for rel in kept:
        try:
            total += (root / rel).stat().st_size
        except OSError:
            pass
    print(f"\n{root}: {len(kept)} file(s), {total:,} bytes "
          f"({len(skipped)} skipped)")
    for rel in kept:
        print(f"  keep  {rel}")
    if show_skips:
        for rel, reason in skipped:
            print(f"  skip  {rel}  — {reason}")
    return len(kept), total, len(skipped)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Show which workspace files a code commit WOULD contain. "
                    "Read-only: this never writes to git or to disk.")
    parser.add_argument("workspace", nargs="*", help="workspace directories")
    parser.add_argument("--all", action="store_true",
                        help="every runs/*/workspace and studies/*/director_workspace")
    parser.add_argument("--skips", action="store_true",
                        help="also list what was skipped, and why")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parent.parent
    roots = [Path(w) for w in args.workspace]
    if args.all:
        roots.extend(workspaces(project_root))
    if not roots:
        parser.error("give a workspace path or --all")

    files = size = skips = 0
    for root in roots:
        f, s, k = _report(root, args.skips)
        files, size, skips = files + f, size + s, skips + k
    print(f"\nTOTAL: {files:,} file(s), {size:,} bytes, {skips:,} skipped "
          f"across {len(roots)} workspace(s).")
    print("Nothing was committed: choosing WHERE these commits land is an "
          "owner ruling — see docs/memo_auto_commit_run_code.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
