"""tools/run_artifacts_commit.py — WRITE the code a run produced onto a
dedicated `run-artifacts` branch, using git plumbing only.

This is the second half of docs/memo_auto_commit_run_code.md. The first half
(tools/run_code_snapshot.py) decides WHICH files; this decides nothing about
selection and only writes what that module hands it. The memo's §3 ruling is
made: option (b), a dedicated branch, written with plumbing.

WHY THIS EXISTS AT ALL: runs/ and studies/ are gitignored with zero tracked
files, so every study's output — including the only deliverables of value this
project has produced — exists on exactly one laptop. This is BACKUP first and a
code history second.

THE FIVE PROPERTIES THAT MAKE IT SAFE. Each is a rule, not a preference; the
whole point of the design is that several sessions commit to this tree
concurrently and a study can finish at 03:00 while a human is mid-`git add`.

1. PLUMBING ONLY. hash-object / mktree / commit-tree / ls-tree / update-ref.
   The index is never opened, HEAD is never moved, nothing is checked out, and
   `git add` appears nowhere. A `git status` on the working branch is
   byte-identical before and after.

2. NEVER FATAL. Every failure — git missing, ref racing, a file vanishing
   mid-walk — is printed and dropped, exactly like the cost meter. An
   accounting step may not end an arc; nothing ends an arc but the director.
   Every public function here returns a result dict and raises nothing.

3. COMPARE-AND-SWAP ON THE REF. Two studies can finish seconds apart.
   update-ref is always given the expected old value, and a lost race is
   handled by RE-READING the new tip and rebuilding on top of it — never by
   forcing. A lost artifact commit is bad; a clobbered ref is worse.

4. THE TREE ACCUMULATES. Each commit's tree is the parent's tree with this
   study's files overlaid, so the branch TIP holds everything ever committed
   and `git show run-artifacts:<path>` finds a study from six months ago.
   Unchanged subtrees are reused by sha, so a commit costs O(changed dirs).

5. A SECRET SCAN RUNS EVERY TIME, BEFORE ANY OBJECT IS WRITTEN. This content
   has never been reviewed by anyone: agent workspaces hold whatever the agent
   fetched, wrote or printed, and this project keeps an MP_API_KEY in a .env an
   agent could in principle have echoed into a file. A file that trips the scan
   is WITHHELD from the commit and reported by path and rule — never by
   content, so the report itself cannot leak the value.

USE:

    venv/bin/python3 -m tools.run_artifacts_commit --study <study-id>
    venv/bin/python3 -m tools.run_artifacts_commit --study <study-id> --dry-run
    venv/bin/python3 -m tools.run_artifacts_commit --backfill
    venv/bin/python3 -m tools.run_artifacts_commit --scan-only --backfill

Nothing here pushes. The first push of this ref is the owner's call, because it
is the moment unreviewed content leaves the laptop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_code_snapshot as snap  # noqa: E402

# A BRANCH, not an orphan namespace (memo §3, owner ruling 2026-07-30). The want
# is that this code IS committed and findable by ordinary git commands six months
# later; a hidden ref namespace satisfies that in letter and loses it in spirit.
REF = "refs/heads/run-artifacts"

# The env var that turns the production wire on, and the flag that does the same
# from the CLI. Off by default: absent both, every path is byte-identical to
# before this module existed.
ENV_FLAG = "RESEARCH_COMMIT_RUN_CODE"

# How many times to lose the ref race before giving up. Each retry re-reads the
# tip and rebuilds on it, so a retry is correct, not a repeat.
MAX_REF_RETRIES = 5

# git's empty tree, the parent-less starting point.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# Above this, a selection gets an itemised by-directory breakdown printed BEFORE
# anything is written.
#
# WHY THIS EXISTS: the memo predicted 7.0 MB for the backfill and the real
# selection was 24.5 MB — 3.5x — and nothing said so. The number only came out
# because a human went looking, and what it turned out to be hiding was 9.7 MB
# of scraped journal text that had no business being republished. A size that
# surprises you is the cheapest early warning there is, so the writer now always
# prints what it selected, and names the directories responsible whenever the
# figure is large enough to be worth a second look.
LARGE_SELECTION_BYTES = 2_000_000

# How many directories to name in that breakdown.
LARGEST_DIRS_SHOWN = 6


# --------------------------------------------------------------------------
# the secret scan
# --------------------------------------------------------------------------

# Shapes that are a credential wherever they appear. Named, so a hit is
# reportable without ever quoting what matched.
SECRET_PATTERNS = (
    ("anthropic api key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-style api key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws secret access key", re.compile(
        r"aws_secret_access_key\s*[=:]\s*\S{20,}", re.I)),
    ("github token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}")),
    ("github fine-grained pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer token literal", re.compile(
        r"Authorization\s*[=:]\s*['\"]?Bearer\s+\S{20,}", re.I)),
    # .env-LIKE CONTENT: an uppercase secret-shaped name assigned a long opaque
    # value. This is the shape an agent would produce by echoing a key into a
    # file it wrote, which is the specific risk this fileset carries.
    ("env-style secret assignment", re.compile(
        r"^\s*(?:export\s+)?[A-Z][A-Z0-9_]*"
        r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)S?\s*=\s*"
        r"['\"]?[A-Za-z0-9_\-/+.]{16,}", re.M)),
)

# Below this a value in .env is too short to be a credential and matching it
# would flag every ordinary word.
MIN_LOCAL_SECRET_LEN = 16

# Files a scan reads in full. Above this, read the head only: a scan that has to
# hold a 60 MB file in memory to protect a 64 KB one is the wrong trade, and the
# caps in run_code_snapshot mean nothing this large is being committed anyway.
SCAN_READ_BYTES = 2_000_000


def local_secret_values(project_root: Path) -> list:
    """The literal secret VALUES this tree keeps in .env-shaped files, so the
    scan can catch one that was copied verbatim into a workspace.

    This is the precise half of the scan: pattern-matching catches shapes, this
    catches the actual MP_API_KEY that lives in this project's .env. The values
    are returned to be searched FOR and are never printed, logged, or put in a
    commit message — a hit reports the path and the rule name only."""
    values = []
    for name in (".env", ".env.local", ".env.production"):
        path = Path(project_root) / name
        try:
            if not path.is_file():
                continue
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            value = line.split("=", 1)[1].strip().strip("'\"")
            if len(value) >= MIN_LOCAL_SECRET_LEN and not value.startswith("$"):
                values.append(value)
    return values


def scan_file(path: Path, local_values: Iterable[str] = ()) -> list:
    """Rule names this file trips, or [] for a clean file.

    Reports rules, never matches: the whole point is that the report can be
    pasted anywhere, and a report that quotes the secret has leaked it."""
    hits = []
    try:
        with open(path, "rb") as handle:
            raw = handle.read(SCAN_READ_BYTES)
    except OSError as exc:
        # An unreadable file cannot be committed either (hash-object would fail
        # on it), but it must not be silently treated as clean.
        return [f"unreadable during scan ({type(exc).__name__})"]
    if b"\0" in raw:
        # Binary. The figure/PDF class reaches here; a regex over decoded bytes
        # of a PNG is noise, and the credential shapes above are textual.
        return []
    text = raw.decode("utf-8", errors="replace")
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(name)
    for value in local_values:
        if value and value in text:
            hits.append("matches a value in this tree's .env")
            break
    return hits


def scan_fileset(files: Iterable, project_root: Path) -> dict:
    """{repo-relative path: [rule names]} for every file that tripped the scan.

    `files` is the (repo_rel, absolute) pair list a snapshot produced."""
    local = local_secret_values(project_root)
    findings = {}
    for rel, absolute in files:
        hits = scan_file(absolute, local)
        if hits:
            findings[str(rel)] = hits
    return findings


# --------------------------------------------------------------------------
# what a study's commit contains
# --------------------------------------------------------------------------

def _read_arc_run_ids(study_dir: Path) -> list:
    """The run ids this study's arc recorded, in order, de-duplicated.

    Reads arc.jsonl directly rather than importing pi_agent.study, so this
    module stays usable on a tree where a study dir survived but the code that
    wrote it moved. A torn line is skipped, not raised on — the same tolerance
    the journal read side has."""
    ids = []
    seen = set()
    path = study_dir / "arc.jsonl"
    try:
        text = path.read_text()
    except OSError:
        return ids
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        run_id = entry.get("run_id")
        if isinstance(run_id, str) and run_id and run_id not in seen:
            seen.add(run_id)
            ids.append(run_id)
    return ids


def _descendant_study_ids(study_id: str, project_root: Path) -> list:
    """Studies spawned beneath this one, recursively, oldest-id first.

    A free director may spawn a sub-investigation as its own study
    (studies/<parent>-subN with parent_study_id set), and its workspaces are
    part of what the parent produced. Read from study.json's back-pointer, with
    the id prefix as a fallback for a study dir whose identity file is gone."""
    children = []
    for path in sorted(Path(project_root).glob("studies/*/")):
        sid = path.name
        if sid == study_id:
            continue
        parent = None
        try:
            parent = json.loads((path / "study.json").read_text()).get(
                "parent_study_id")
        except (OSError, ValueError):
            parent = None
        if parent == study_id or (parent is None and sid.startswith(study_id + "-sub")):
            children.append(sid)
    out = []
    for sid in children:
        out.append(sid)
        out.extend(_descendant_study_ids(sid, project_root))
    # De-duplicate while keeping order: a mis-recorded back-pointer must not
    # make this loop forever or double-list a directory.
    seen, unique = set(), []
    for sid in out:
        if sid not in seen:
            seen.add(sid)
            unique.append(sid)
    return unique


def study_roots(study_id: str, project_root: Path = Path(".")) -> list:
    """Every directory a study's commit draws from, in a stable order:
    its own director_workspace and deliverable, the workspace of every run in
    its arc, and the same three for every study spawned beneath it.

    Only directories that exist are returned. Nothing here decides WHICH FILES
    — that is run_code_snapshot's job and this module never second-guesses it."""
    project_root = Path(project_root)
    roots = []
    for sid in [study_id] + _descendant_study_ids(study_id, project_root):
        study_dir = project_root / "studies" / sid
        for name in ("director_workspace", snap.DELIVERABLE_DIRNAME):
            candidate = study_dir / name
            if candidate.is_dir():
                roots.append(candidate)
        for run_id in _read_arc_run_ids(study_dir):
            candidate = project_root / "runs" / run_id / "workspace"
            if candidate.is_dir():
                roots.append(candidate)
    # A run can appear in two arcs (a resumed study re-reads its own); commit it
    # once.
    seen, unique = set(), []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def largest_directories(files: Iterable, limit: int = LARGEST_DIRS_SHOWN) -> list:
    """[(bytes, file count, directory)] for the heaviest directories in a
    selection, largest first. Pure over (rel, absolute) pairs it can stat.

    Directory-level, not file-level, because the surprise this exists to catch
    was 221 small files in ONE directory — a top-ten-files list would have shown
    ten unremarkable 64 KB text files and hidden the 9.7 MB behind them."""
    totals: dict = {}
    counts: dict = {}
    for rel, absolute in files:
        parent = str(Path(rel).parent)
        try:
            totals[parent] = totals.get(parent, 0) + Path(absolute).stat().st_size
        except OSError:
            continue
        counts[parent] = counts.get(parent, 0) + 1
    ranked = sorted(((b, counts[d], d) for d, b in totals.items()), reverse=True)
    return ranked[:limit]


def report_selection(label: str, files: list, total: int, say) -> None:
    """Print WHAT WAS SELECTED, every time, before anything is written.

    Always the one-line size; the by-directory breakdown only when the selection
    is large enough that a human should glance at it. See
    LARGE_SELECTION_BYTES for why this is not optional output."""
    say(f"run-artifacts: {label} selects {len(files):,} file(s), "
        f"{total:,} bytes ({total / 1e6:.1f} MB)")
    if total < LARGE_SELECTION_BYTES:
        return
    say(f"run-artifacts: NOTICE — over {LARGE_SELECTION_BYTES / 1e6:.1f} MB; "
        f"the largest directories in it are:")
    for size, count, directory in largest_directories(files):
        say(f"    {size / 1e6:>7.2f} MB  {count:>4} file(s)  {directory}")


def snapshot_files(roots: Iterable, project_root: Path = Path(".")) -> list:
    """[(repo-relative path, absolute path)] across several roots.

    The repo-relative path is the path INSIDE the artifact commit, so
    `git show run-artifacts:runs/<id>/workspace/fit.py` reads exactly the way
    the working tree does. A root outside the project is skipped rather than
    committed at some invented path."""
    project_root = Path(project_root).resolve()
    files = []
    for root in roots:
        root = Path(root)
        try:
            prefix = root.resolve().relative_to(project_root)
        except ValueError:
            continue
        kept, _skipped = snap.select(root)
        for rel in kept:
            files.append((prefix / rel, root / rel))
    files.sort(key=lambda pair: str(pair[0]))
    return files


# --------------------------------------------------------------------------
# git plumbing — the only place in this project that writes a git object
# --------------------------------------------------------------------------

class GitError(RuntimeError):
    """A git invocation failed. Caught at the module boundary and turned into a
    printed line: nothing here may end an arc."""


class Plumbing:
    """The four verbs, and nothing else. No index, no HEAD, no checkout.

    Bound to an explicit git dir so the whole thing is testable against a
    throwaway repo — a test that writes a ref into this project's own .git is
    not acceptable."""

    def __init__(self, git_dir: Path, work_root: Path):
        self.git_dir = Path(git_dir).resolve()
        self.work_root = Path(work_root).resolve()

    def _env(self) -> dict:
        env = dict(os.environ)
        env["GIT_DIR"] = str(self.git_dir)
        # The index is never opened by any command used here; pointing this at a
        # path that does not exist means a future edit that reaches for the
        # index fails loudly instead of touching the shared one.
        env["GIT_INDEX_FILE"] = str(self.git_dir / "run-artifacts-index-never-used")
        env.pop("GIT_WORK_TREE", None)
        return env

    def _run(self, args: list, stdin: bytes = None, binary_out: bool = False):
        try:
            proc = subprocess.run(
                ["git"] + args, input=stdin, cwd=str(self.work_root),
                env=self._env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            raise GitError(f"could not run git: {type(exc).__name__}: {exc}")
        if proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args[:2])} failed ({proc.returncode}): "
                f"{proc.stderr.decode('utf-8', 'replace').strip()}")
        return proc.stdout if binary_out else proc.stdout.decode(
            "utf-8", "replace")

    # -- read ------------------------------------------------------------
    def tip(self, ref: str) -> Optional[str]:
        """The ref's current commit sha, or None if the ref does not exist."""
        try:
            return self._run(["rev-parse", "--verify", "--quiet",
                              f"{ref}^{{commit}}"]).strip() or None
        except GitError:
            return None

    def commit_tree_sha(self, commit: Optional[str]) -> Optional[str]:
        if not commit:
            return None
        try:
            return self._run(["rev-parse", "--verify", "--quiet",
                              f"{commit}^{{tree}}"]).strip() or None
        except GitError:
            return None

    def ls_tree(self, tree: Optional[str]) -> dict:
        """{name: (mode, type, sha)} one level down. Empty for a missing tree."""
        if not tree:
            return {}
        out = self._run(["ls-tree", "-z", tree], binary_out=True)
        entries = {}
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, _, name = record.partition(b"\t")
            mode, type_, sha = meta.decode().split(" ", 2)
            entries[name.decode("utf-8", "surrogateescape")] = (mode, type_, sha)
        return entries

    # -- write -----------------------------------------------------------
    def hash_file(self, path: Path) -> str:
        """Write one file into the object store and return its blob sha.
        --no-filters: the bytes on disk are what gets stored, so this is a
        faithful backup rather than something a .gitattributes rule reshaped."""
        return self._run(
            ["hash-object", "-w", "--no-filters", "--", str(path)]).strip()

    def mktree(self, entries: dict) -> str:
        """entries is {name: (mode, type, sha)}. Returns the tree sha."""
        if not entries:
            return EMPTY_TREE
        payload = b"".join(
            f"{mode} {type_} {sha}\t{name}".encode("utf-8", "surrogateescape")
            + b"\0"
            for name, (mode, type_, sha) in sorted(entries.items()))
        return self._run(["mktree", "-z"], stdin=payload).strip()

    def commit_tree(self, tree: str, parent: Optional[str], message: str) -> str:
        args = ["commit-tree", tree]
        if parent:
            args += ["-p", parent]
        args += ["-F", "-"]
        return self._run(args, stdin=message.encode()).strip()

    def update_ref_cas(self, ref: str, new: str, old: Optional[str]) -> bool:
        """Compare-and-swap. `old` None means the ref must not yet exist.
        Returns False when the race was lost — never forces, never retries here
        (the caller rebuilds on the new tip, which is the only correct retry)."""
        try:
            self._run(["update-ref", ref, new, old or ""])
            return True
        except GitError:
            return False


def _file_mode(path: Path) -> str:
    """100755 for an executable the agent marked runnable, 100644 otherwise.
    Worth preserving: a run's driver script is usually chmod +x, and a restored
    backup that will not execute is a worse backup."""
    try:
        return "100755" if os.access(path, os.X_OK) else "100644"
    except OSError:
        return "100644"


def _nest(files: Iterable) -> dict:
    """[(repo-relative path, absolute path)] -> a nested {name: subdict | Path}
    so the tree builder can walk directories."""
    tree: dict = {}
    for rel, absolute in files:
        parts = Path(rel).parts
        node = tree
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = Path(absolute)
    return tree


def _build_tree(git: Plumbing, parent_tree: Optional[str], new: dict) -> str:
    """The parent's tree with `new` overlaid, written bottom-up.

    THE ACCUMULATION RULE (property 4). Starting from the parent's entries is
    what makes the branch tip hold every study ever committed instead of only
    the last one. A subtree with nothing new under it is reused BY SHA — never
    re-read, never re-hashed — so a commit costs O(changed dirs) no matter how
    large the history is."""
    entries = dict(git.ls_tree(parent_tree))
    for name, node in sorted(new.items()):
        if isinstance(node, dict):
            existing = entries.get(name)
            sub_parent = existing[2] if existing and existing[1] == "tree" else None
            entries[name] = ("040000", "tree", _build_tree(git, sub_parent, node))
        else:
            entries[name] = (_file_mode(node), "blob", git.hash_file(node))
    return git.mktree(entries)


# --------------------------------------------------------------------------
# the public entry point
# --------------------------------------------------------------------------

def _message(study_id: str, project_root: Path, files: list, roots: list,
             total_bytes: int, withheld: dict) -> str:
    """The commit message: study id and arc position on the subject line, so
    `git log --oneline run-artifacts` reads as the research record it is."""
    study_dir = Path(project_root) / "studies" / study_id
    arc_len = len(_read_arc_run_ids(study_dir))
    goal = ""
    try:
        goal = (json.loads((study_dir / "study.json").read_text()).get("goal")
                or "").strip().replace("\n", " ")
    except (OSError, ValueError):
        goal = ""
    if len(goal) > 200:
        goal = goal[:197] + "..."
    lines = [
        f"run artifacts: {study_id} ({arc_len} run(s) in the arc)",
        "",
    ]
    if goal:
        lines += [f"goal: {goal}", ""]
    lines += [
        f"{len(files)} file(s), {total_bytes:,} bytes, from "
        f"{len(roots)} workspace/deliverable root(s).",
        "",
        "Selected by tools/run_code_snapshot.py (whitelist + directory prune +",
        "two size caps + credential denylist; figures only from a deliverable).",
        "Written with git plumbing onto a branch that is never checked out — see",
        "docs/memo_auto_commit_run_code.md.",
    ]
    if withheld:
        lines += ["", f"WITHHELD by the secret scan: {len(withheld)} file(s)."]
        for path in sorted(withheld):
            lines.append(f"  {path}: {', '.join(withheld[path])}")
    return "\n".join(lines) + "\n"


def commit_run_artifacts(
    study_id: str,
    *,
    project_root: Path = Path("."),
    git_dir: Path = None,
    ref: str = REF,
    dry_run: bool = False,
    quiet: bool = False,
) -> dict:
    """Commit one study's produced code onto `ref`. NEVER RAISES.

    Returns a result dict: {committed, commit, files, bytes, roots, withheld,
    error, skipped}. A failure is reported in `error` and printed; the caller —
    a director that has just finished a study — carries on regardless. That is
    property 2, and it is the reason every branch below returns instead of
    raising."""
    project_root = Path(project_root)
    git_dir = Path(git_dir) if git_dir else project_root / ".git"
    result = {
        "study_id": study_id, "committed": False, "commit": None,
        "files": 0, "bytes": 0, "roots": 0, "withheld": {}, "error": None,
        "skipped": None, "ref": ref,
    }

    def say(line: str) -> None:
        if not quiet:
            print(line)

    try:
        roots = study_roots(study_id, project_root)
        files = snapshot_files(roots, project_root)
        result["roots"] = len(roots)

        # THE SCAN, BEFORE ANY OBJECT IS WRITTEN. A withheld file is never
        # hashed, so a secret cannot reach the object store and then be
        # "removed" from a later tree while staying reachable in this commit.
        withheld = scan_fileset(files, project_root)
        result["withheld"] = withheld
        if withheld:
            say(f"run-artifacts: SECRET SCAN withheld {len(withheld)} file(s) "
                f"from the commit (path and rule only, never the value):")
            for path in sorted(withheld):
                say(f"  {path}: {', '.join(withheld[path])}")
        files = [pair for pair in files if str(pair[0]) not in withheld]

        total = 0
        present = []
        for rel, absolute in files:
            try:
                total += absolute.stat().st_size
            except OSError:
                continue  # vanished between the walk and here; not a failure
            present.append((rel, absolute))
        files = present
        result["files"], result["bytes"] = len(files), total

        if not files:
            result["skipped"] = "nothing selected"
            say(f"run-artifacts: nothing to commit for {study_id} "
                f"({len(roots)} root(s) held no selectable file)")
            return result
        # BEFORE anything is written, and unconditionally.
        report_selection(study_id, files, total, say)
        if dry_run:
            result["skipped"] = "dry run"
            say(f"run-artifacts: DRY RUN {study_id} — nothing written")
            return result

        git = Plumbing(git_dir, project_root)
        nested = _nest(files)
        message = _message(study_id, project_root, files, roots, total, withheld)

        # THE RACE LOOP (property 3). Each attempt re-reads the tip, rebuilds
        # the tree ON that tip, and compare-and-swaps against it. Losing means
        # another study committed in between, and the correct response is to
        # build on their commit — not to force past it.
        for attempt in range(1, MAX_REF_RETRIES + 1):
            old = git.tip(ref)
            tree = _build_tree(git, git.commit_tree_sha(old), nested)
            if old is not None and tree == git.commit_tree_sha(old):
                result["skipped"] = "identical to the current tip"
                say(f"run-artifacts: {study_id} already committed "
                    f"(tree unchanged at {old[:12]})")
                return result
            commit = git.commit_tree(tree, old, message)
            if git.update_ref_cas(ref, commit, old):
                result["committed"], result["commit"] = True, commit
                say(f"run-artifacts: committed {commit[:12]} — {study_id}, "
                    f"{len(files)} file(s), {total:,} bytes "
                    f"({ref.rsplit('/', 1)[-1]})")
                return result
            say(f"run-artifacts: ref moved under attempt {attempt}; "
                f"rebuilding on the new tip")
        result["error"] = (f"lost the {ref} race {MAX_REF_RETRIES} times; "
                           "nothing was committed and nothing was forced")
        say(f"run-artifacts: {result['error']}")
        return result
    except Exception as exc:  # noqa: BLE001 — property 2: never fatal
        result["error"] = f"{type(exc).__name__}: {exc}"
        say(f"run-artifacts: NOT committed ({result['error']}); the study is "
            f"unaffected")
        return result


def commit_enabled(flag: bool = False) -> bool:
    """Whether the production wire should fire: the --commit-code flag, or
    RESEARCH_COMMIT_RUN_CODE=1 in the environment (so it survives into a run
    subprocess the way RESEARCH_MOVE_TOKEN_ALLOWANCE does). Off by default."""
    if flag:
        return True
    return (os.environ.get(ENV_FLAG) or "").strip().lower() in {
        "1", "true", "yes", "on"}


def root_study_ids(project_root: Path = Path(".")) -> list:
    """Every study that is not itself a spawned child, oldest first. Backfill
    iterates these: a child's workspaces ride in its parent's commit, so
    committing children separately would write the same blobs twice."""
    project_root = Path(project_root)
    all_ids = sorted(p.name for p in project_root.glob("studies/*") if p.is_dir())
    children = set()
    for sid in all_ids:
        children.update(_descendant_study_ids(sid, project_root))
    return [sid for sid in all_ids if sid not in children]


def orphan_run_roots(project_root: Path = Path(".")) -> list:
    """Run workspaces no study's arc claims — standalone runs, and runs from a
    study whose arc line was lost. Backup means backup: these are exactly the
    runs that would otherwise be dropped on the floor."""
    project_root = Path(project_root)
    claimed = set()
    for study_dir in project_root.glob("studies/*"):
        if study_dir.is_dir():
            claimed.update(_read_arc_run_ids(study_dir))
    return [p for p in sorted(project_root.glob("runs/*/workspace"))
            if p.is_dir() and p.parent.name not in claimed]


def _commit_roots(label: str, roots: list, project_root: Path, git_dir: Path,
                  ref: str, dry_run: bool, quiet: bool) -> dict:
    """The same write path for a set of roots that is not a study (the orphan
    runs). Shares every safety property; only the message differs."""
    result = {"study_id": label, "committed": False, "commit": None,
              "files": 0, "bytes": 0, "roots": len(roots), "withheld": {},
              "error": None, "skipped": None, "ref": ref}
    try:
        files = snapshot_files(roots, project_root)
        withheld = scan_fileset(files, project_root)
        result["withheld"] = withheld
        if withheld and not quiet:
            print(f"run-artifacts: SECRET SCAN withheld {len(withheld)} file(s):")
            for path in sorted(withheld):
                print(f"  {path}: {', '.join(withheld[path])}")
        files = [pair for pair in files if str(pair[0]) not in withheld]
        total = 0
        present = []
        for rel, absolute in files:
            try:
                total += absolute.stat().st_size
            except OSError:
                continue
            present.append((rel, absolute))
        files = present
        result["files"], result["bytes"] = len(files), total
        if not files:
            result["skipped"] = "nothing selected"
            return result
        report_selection(label, files, total,
                         (lambda line: None) if quiet else print)
        if dry_run:
            result["skipped"] = "dry run"
            return result
        git = Plumbing(git_dir, project_root)
        nested = _nest(files)
        message = (f"run artifacts: {label}\n\n{len(files)} file(s), "
                   f"{total:,} bytes from {len(roots)} run workspace(s) that no "
                   f"study arc claims.\n")
        for _attempt in range(MAX_REF_RETRIES):
            old = git.tip(ref)
            tree = _build_tree(git, git.commit_tree_sha(old), nested)
            if old is not None and tree == git.commit_tree_sha(old):
                result["skipped"] = "identical to the current tip"
                return result
            commit = git.commit_tree(tree, old, message)
            if git.update_ref_cas(ref, commit, old):
                result["committed"], result["commit"] = True, commit
                if not quiet:
                    print(f"run-artifacts: committed {commit[:12]} — {label}, "
                          f"{len(files)} file(s), {total:,} bytes")
                return result
        result["error"] = f"lost the {ref} race {MAX_REF_RETRIES} times"
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        if not quiet:
            print(f"run-artifacts: NOT committed ({result['error']})")
        return result


def backfill(
    *,
    project_root: Path = Path("."),
    git_dir: Path = None,
    ref: str = REF,
    dry_run: bool = False,
    quiet: bool = False,
) -> list:
    """One commit per root study, oldest first, then one for the orphan runs.

    Sequential BY DESIGN: the commits then read chronologically in
    `git log run-artifacts`, and no two of them contend for the ref."""
    project_root = Path(project_root)
    git_dir = Path(git_dir) if git_dir else project_root / ".git"
    results = []
    for study_id in root_study_ids(project_root):
        results.append(commit_run_artifacts(
            study_id, project_root=project_root, git_dir=git_dir, ref=ref,
            dry_run=dry_run, quiet=quiet))
    orphans = orphan_run_roots(project_root)
    if orphans:
        results.append(_commit_roots(
            "runs with no study arc", orphans, project_root, git_dir, ref,
            dry_run, quiet))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Commit what a run produced onto the run-artifacts branch, "
                    "with git plumbing only. Never touches the index, HEAD, or "
                    "the working tree; never pushes.")
    parser.add_argument("--study", help="one study id to commit")
    parser.add_argument("--backfill", action="store_true",
                        help="one commit per existing study, oldest first, "
                             "plus one for runs no study arc claims")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be committed; write nothing")
    parser.add_argument("--scan-only", action="store_true",
                        help="run the secret scan over the selection and stop")
    parser.add_argument("--ref", default=REF, help=f"target ref (default {REF})")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parent.parent
    if not (args.study or args.backfill):
        parser.error("give --study <id> or --backfill")

    if args.scan_only:
        if args.study:
            roots = study_roots(args.study, project_root)
        else:
            roots = []
            for sid in root_study_ids(project_root):
                roots.extend(study_roots(sid, project_root))
            roots.extend(orphan_run_roots(project_root))
        files = snapshot_files(roots, project_root)
        findings = scan_fileset(files, project_root)
        print(f"scanned {len(files):,} selected file(s) across {len(roots)} "
              f"root(s)")
        if not findings:
            print("SECRET SCAN CLEAN — no key-shaped string, private-key block, "
                  "or .env-style assignment in the selected fileset.")
            return 0
        print(f"SECRET SCAN: {len(findings)} file(s) tripped a rule "
              f"(paths and rule names only):")
        for path in sorted(findings):
            print(f"  {path}: {', '.join(findings[path])}")
        return 1

    if args.backfill:
        results = backfill(project_root=project_root, ref=args.ref,
                           dry_run=args.dry_run)
    else:
        results = [commit_run_artifacts(args.study, project_root=project_root,
                                        ref=args.ref, dry_run=args.dry_run)]
    committed = sum(1 for r in results if r["committed"])
    files = sum(r["files"] for r in results)
    total = sum(r["bytes"] for r in results)
    withheld = sum(len(r["withheld"]) for r in results)
    print(f"\n{committed} commit(s), {files:,} file(s), {total:,} bytes "
          f"({total / 1e6:.1f} MB), {withheld} file(s) withheld by the "
          f"secret scan.")
    errors = [r for r in results if r["error"]]
    for r in errors:
        print(f"  ERROR {r['study_id']}: {r['error']}")
    print("Nothing was pushed. The first push of this ref is the owner's call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
