# memo: auto-committing the code a run produces — design, and the one open ruling

**2026-07-28.** The owner wants the code a run produces committed to git
automatically. This memo records what was built (file selection, read-only),
what was NOT built (any git write), and the single decision that needs an owner
ruling before the second half exists.

**Status: HALF BUILT ON PURPOSE.** `tools/run_code_snapshot.py` decides which
files a commit would contain and prints them. Nothing writes a ref, an object,
an index, or a working-tree file, and `tests/test_run_code_snapshot.py` asserts
the module contains no subprocess/git plumbing at all. The brief said a wrong
auto-commit scheme is worse than none, and the part that can be wrong in an
expensive way is the part that touches the repository.

---

## 1. What runs actually produce (measured, this tree, 2026-07-28)

61 workspaces: 38 `runs/<id>/workspace` + 23 `studies/<id>/director_workspace`.
`runs/` is 590 MB and `studies/` 13 MB on disk, and **both are gitignored
today**.

The naive scheme — whitelist source extensions — fails immediately here:

| | files | bytes |
|---|---|---|
| all `.py` under the workspaces | 5,020 | — |
| …after pruning `.venv` / `site-packages` / caches | **317** | 1.7 MB |
| one flat 1 MB cap, all whitelisted types | 560 | 30.3 MB |
| …of which `.json` result dumps | 146 | 23.1 MB |
| **two caps (64 KB for data-shaped, 1 MB for source)** | **503** | **7.0 MB** |

Two real run workspaces contain a `.venv`. Without directory pruning, an
entire virtualenv enters the history on the first commit.

## 2. The selection rules, and why each exists

Implemented and unit-tested in `tools/run_code_snapshot.py`:

1. **Whitelist extensions, never blacklist.** A blacklist is wrong the first
   time a run invents a file type, and wrong in the leaking direction.
2. **Prune directories first**: `.venv`, `venv`, `site-packages`,
   `node_modules`, `__pycache__`, `.git`, `.tox`, caches, `build`, `dist`,
   `*.egg-info`, `*.dist-info`, `postProcessing`. See the table above.
3. **Two size caps.** 1 MB for source; 64 KB for `.json/.csv/.tsv/.txt/.dat`.
   The dumps are already run evidence — a code history is not where they
   belong, and they were 76% of the bytes.
4. **A name denylist and a dotfile skip** on top of the whitelist: `.env`,
   `id_rsa`, `*.pem`, `credentials*`, `mcp_servers.json`, and any dotfile.
   None of their extensions are whitelisted either; this is belt and braces.
5. **Nothing outside the workspace.** Paths are resolved and re-checked;
   symlinks are skipped, never followed.

Every refusal carries a printed reason, so a dry run shows *why* a file was
left out rather than silently losing it:

```
venv/bin/python3 -m tools.run_code_snapshot --all --skips
```

## 3. THE OPEN RULING — where do the commits land?

This is the question the brief said to write down rather than assume. Three
candidates, with the trade the owner has to make:

**(a) The current branch.** Rejected outright. Other sessions work this tree;
a study finishing at 03:00 would interleave machine commits with the owner's
own on `iterate-experiment-loop`, and any scheme that stages files can collide
with an in-flight `git add` in another session.

**(b) A dedicated branch, e.g. `run-artifacts`** — written with plumbing
(`hash-object -w`, `mktree`, `commit-tree`, `update-ref`) so HEAD, the index
and the working tree are never touched. Discoverable (`git log run-artifacts`,
`git show run-artifacts:<path>`), pushable when the owner wants, never merged
into anything by accident.

**(c) An orphan ref namespace, e.g. `refs/research-runs/<study-id>`** — one ref
per study, same plumbing. Maximum isolation: does not appear in `git branch`,
cannot be checked out by accident, cannot be pushed without naming the
refspec. Costs discoverability — a human has to know the namespace exists.

**RECOMMENDATION: (b), a dedicated `run-artifacts` branch, written with
plumbing only.** Reasoning: the owner's stated want is that the code *is
committed*, which implies it should be findable by ordinary git commands six
months later; (c) satisfies the letter and loses the spirit. (b) with plumbing
has the same non-interference property as (c) — no index, no HEAD, no
checkout — while remaining a normal object anyone can `git log`. One commit per
run or study, message naming the study id and the arc position, parented on the
previous `run-artifacts` commit so the history reads chronologically.

**This is NOT decided.** It is the recommendation; the owner rules.

## 4. The rest of the design, pending that ruling

- **Opt-in, off by default.** `RESEARCH_COMMIT_RUN_CODE=1` (env, so it survives
  into the run subprocess the same way `RESEARCH_MOVE_TOKEN_ALLOWANCE` does)
  plus a `--commit-code` flag on `python -m pi_agent`. Absent, every path is
  byte-identical to today.
- **After the run, never during.** The commit fires once, after `report.json`
  is written — a workspace being written by a live agent is not a snapshot.
- **Never `git add -A`, never the index.** Plumbing writes a tree from the
  selected paths directly; the shared index is never opened, which is what
  makes concurrent sessions safe.
- **Never fatal.** A git failure is printed and dropped, exactly like the cost
  meter: an accounting or record-keeping step may not end an arc.
- **`.gitignore` is not touched.** `runs/` and `studies/` stay ignored on the
  working branch; the artifact commits live only on the artifact ref, so a
  `git status` in the owner's tree looks exactly as it does now.

## 5. What a reviewer should check before the second half is built

- that the recommendation in §3 is the one the owner wants;
- that 7.0 MB / 503 files for the existing 61 workspaces is an acceptable
  one-time backfill, or that backfill should be skipped and only new runs
  committed (the safer default — the tool can list either);
- whether figures (`.png`, 4.3 MB of the 7.0 MB) belong in a *code* history at
  all, or only the sources that regenerate them.
