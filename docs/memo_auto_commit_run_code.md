# memo: auto-committing the code a run produces — design, ruling, and the build

**2026-07-28.** The owner wants the code a run produces committed to git
automatically. This memo records what was built (file selection, read-only),
what was NOT built (any git write), and the single decision that needs an owner
ruling before the second half exists.

**~~Status: HALF BUILT ON PURPOSE.~~ COMPLETE 2026-07-30.** §3's ruling was
made and the write half is built: `tools/run_artifacts_commit.py`. §§1–4 below
are the original design and stand as written; **§6 records the rulings and what
they changed**, and is the current state. Read §6 before acting on anything
above it.

`tools/run_code_snapshot.py` still decides which files a commit contains and
still touches no git — `tests/test_run_code_snapshot.py` keeps that line, and
the writer imports the selection rather than reimplementing any of it.

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

*(All three were ruled on 2026-07-30 — see §6.)*

---

## 6. THE RULINGS, AND THE BUILD (2026-07-30)

### 6.1 The three rulings

**MECHANISM — (b), a dedicated `run-artifacts` branch, plumbing only.** The
memo's own recommendation, for the reason it gave: the want is that this code
*is* committed and findable by ordinary git commands six months later, which an
orphan ref namespace satisfies in letter and loses in spirit.

**BACKFILL — YES.** This reverses §5's "safer default". The reason it reversed:
**the purpose here is BACKUP.** `runs/` and `studies/` are gitignored with zero
tracked files, so every study's output — including the only deliverable of value
this project has produced — exists on exactly one laptop. Skipping the backfill
leaves the existing work unprotected for no gain.

**FIGURES — deliverable only.** Include the figures that are part of a
deliverable (`studies/<id>/deliverable/`, assembled by
`stages/study_deliverable.py` — a curated, already-existing boundary). Exclude
scratch images and fetched pages from workspaces.

**The tradeoff being accepted, stated as the ruling required:** PNGs do not
delta-compress. Every revision of a figure enters this history as a fresh,
undeltifiable blob, so at roughly 4 MB of figures per hundred studies the branch
grows in a way ordinary source history does not. That cost is accepted at the
deliverable boundary and nowhere else, because a figure a paper cites is part of
the thing being backed up and a scratch plot regenerated eleven times during a
run is not.

### 6.2 THE SIZE ESTIMATE WAS WRONG BY 3.5x, AND NOTHING FLAGGED IT

**§1 predicted 7.0 MB. The first backfill selected 24.5 MB.** Nothing in the
tooling said so; the gap surfaced only because a human went looking, and what it
was hiding was 9.7 MB of scraped third-party journal text (§6.2b).

Two things follow, and both are now built:

- **The current measured figure is 1,088 files / 10.3 MB** (89 roots,
  2026-07-30, after the figure ruling and rule 7). That is the number to check a
  future backfill against — not §1's 7.0 MB, which is stale by 26 workspaces and
  two rules.
- **The writer now always prints the selection size before it writes anything**,
  and names the heaviest directories whenever it exceeds
  `LARGE_SELECTION_BYTES` (2 MB). Directory-level, not file-level, deliberately:
  the surprise was 221 files of 64 KB each in one directory, and a top-ten-files
  list would have shown ten unremarkable files and hidden the 9.7 MB behind
  them.

An estimate nobody can check against a printed actual is how a 3.5x miss goes
unnoticed for a full backfill.

### 6.2b FETCHED THIRD-PARTY CONTENT — rule 7

**The first backfill put 241 files / 9.9 MB of fetched third-party content on
the ref**, chiefly `runs/study-20260730T034915Z-m4/workspace/bztxt/` (221 files,
9.7 MB of scraped journal text; `058.txt` opens *"Copyright 1973 by The American
Ceramic Society"*) plus LTPP database exports, one shipping its own
*"Recommended Citation.txt"*. **Pushing that would have republished third-party
copyrighted material.** The ref was rebuilt from scratch rather than patched on
top, because a push publishes every reachable object.

Fixed in the **selection**, not the writer: a run's artifacts are what it
**wrote**, not what it **fetched**. Downloaded data is re-fetchable by
definition — the fetch code is itself committed. Same class as the existing
`.venv`/`site-packages` prune, simply never anticipated.

**PROVENANCE IS NOT DECIDABLE FROM THE FILESYSTEM.** Nothing on disk records
that the agent downloaded a file rather than wrote it — no stat bit, no xattr,
no manifest. So rule 7 does not ask that question. It asks one it can answer,
and the answer is sufficient:

> **A directory whose entire subtree is data-shaped files with no source file
> anywhere beneath it is a data drop, and is pruned whole.**

It is honest because it does not need to decide provenance: such a directory is
derivable *either way*. Fetched → the fetch script is in the commit. Generated →
the generator is in the commit. What is never bulk-homogeneous is authored
source — an agent's own writing is a handful of differently-named files mixed
in with the code that produced them, which is why mixed directories survive
untouched.

**Measured:** 21 such subtrees exist in this tree and every single one is a data
drop (`bztxt`, `bakcal`, `raw`, `csv`, `sdr`, `db`, `pages`, `pages2`, `pages3`,
`arcs`, `out`, `results`, `clean`, `data`). Not one is authored work. The
threshold (2 files) is not load-bearing: 1 gives 10.28 MB and 4 gives 10.62 MB.

**What rule 7 does not catch, stated so nobody assumes it does:** a fetched file
sitting *mixed in with source* is kept, because at that point it is
indistinguishable from an analysis output. A copyright / citation / DOI audit
over the 1,088 survivors found exactly one marker — `oa1.json`, an OpenAlex
search response (bibliographic metadata, CC0), not copyrighted text.

### 6.2c The selection change the figure ruling forced

`tools/run_code_snapshot.py`, and only there — the writer has no opinions about
files. Two changes:

- `studies/<id>/deliverable/` **was not in scope** and now is (`workspaces()`
  globbed only `runs/*/workspace` and `studies/*/director_workspace`).
- `.png/.svg/.pdf` are kept **only** from a deliverable root (rule 6).

**Re-measured on this tree the day of the ruling** — the numbers in §1 are from
two days and 26 workspaces earlier, and the composition changed a great deal:

| | files | bytes |
|---|---|---|
| §1's measurement (61 workspaces, 2026-07-28) | 503 | 7.0 MB |
| the same rules, 89 roots, 2026-07-30 | 1,983 | 215.4 MB |
| …of which figure-class in a *workspace* | 380 | **189.8 MB** |
| …of which `.pdf` in a workspace | 306 | 178.3 MB |
| figure-class in a *deliverable* | 11 | 1.2 MB |
| after the figure ruling | 1,603 | 25.7 MB |
| …of which bulk data drops (rule 7, §6.2b) | 515 | **15.4 MB** |
| **after both rules — the current figure** | **1,088** | **10.3 MB** |

The 306 workspace PDFs are papers the agent **fetched off the web** while
working. They were the single largest thing the pre-ruling selection would have
committed, and they are exactly what the ruling excludes.

25.7 MB rather than §1's 7.0 MB. The growth is real work, not a leak: 10.4 MB is
fetched `.txt` corpora and 4.9 MB `.csv` data, all already under the 64 KB
data cap. No cap or rule was changed to reach this number — only the figure rule
the owner set. It is recorded here rather than quietly tuned further.

### 6.3 The writer: `tools/run_artifacts_commit.py`

Five properties, each a rule and not a preference. They are in the module's
docstring too, because that is where the next person edits.

1. **Plumbing only** — `hash-object` / `mktree` / `commit-tree` / `ls-tree` /
   `update-ref`. The index is never opened, HEAD never moves, nothing is
   checked out, and `git add` appears nowhere. `GIT_INDEX_FILE` is pointed at a
   path that does not exist so a future edit reaching for the index fails
   loudly instead of touching the shared one.
2. **Never fatal** — every failure is printed and dropped, exactly like the cost
   meter. Every public function returns a result dict and raises nothing.
3. **Compare-and-swap on the ref** — `update-ref` is always given the expected
   old value, and a lost race is handled by re-reading the new tip and
   *rebuilding on it*, never by forcing. A lost artifact commit is bad; a
   clobbered ref is worse.
4. **The tree accumulates** — each commit's tree is the parent's tree with this
   study's files overlaid, so the branch tip holds everything ever committed and
   `git show run-artifacts:<path>` finds a study from months ago. Unchanged
   subtrees are reused by sha, so a commit costs O(changed directories).
5. **The secret scan runs every time, before any object is written** — see 6.4.

One commit per study, subject line naming the study id and its arc position,
parented on the previous tip so `git log --oneline run-artifacts` reads
chronologically. A study's commit covers its `director_workspace`, its
`deliverable`, the workspace of every run in its arc, and the same three for
every sub-study spawned beneath it. `--backfill` walks root studies oldest-first
and finishes with one commit for run workspaces no study's arc claims — backup
means backup.

**Wiring:** opt-in via `RESEARCH_COMMIT_RUN_CODE=1` or `--commit-code` on
`python -m pi_agent`; fires once at the end of `main()`, after `report.json`
*and* after the deliverable is packaged (the deliverable is where the figures
come from, so a commit fired earlier would snapshot a study without its own
product). Absent the flag, every path is byte-identical to before.
`.gitignore` is untouched and `git status` on the working branch is unchanged.

### 6.4 The secret scan

This content **has never been reviewed by anyone.** The tracked-tree audit done
earlier does not cover it: agent workspaces hold whatever the agent fetched,
wrote or printed, and this project keeps an `MP_API_KEY` in a `.env` an agent
could in principle have echoed into a file.

The scan is **part of the writer, not a one-off** — it runs on every commit,
before any object is hashed. A file that trips it is **withheld from the
commit entirely** (never hashed, so a secret cannot sit reachable in the object
store while being absent from the tree) and reported **by path and rule name
only** — never by content, so the report itself cannot leak the value. Eleven
credential shapes, plus a check for the literal values in this tree's own `.env`
(the precise half: a copied `MP_API_KEY` carries no recognisable prefix).

**First-push audit, 2026-07-30: CLEAN, and re-run on the rebuilt ref.** 1,603
selected files across 89 roots on the first build (zero withheld) and 1,088 on
the rebuild after rule 7 (zero withheld). A deliberately noisier supplementary
sweep (any
`key|token|secret|password` assignment, `Authorization:` headers, credentials in
URLs, `os.environ[...KEY]`, long opaque base64) returned 113 hits, every one
read by hand and every one a false positive: shell/Python variable assignments
(`NORMAL=2.2250738585072014e-308`, `STATIONS="723890-…`), a sha256 provenance
digest, and gzip/zlib base64 **data** blobs (`H4sIA…`, `eNr…`) embedded in
analysis scripts. Nothing credential-shaped exists in the selected fileset.

### 6.5 Testing, and what is deliberately not done

`tests/test_run_artifacts_commit.py` (31 tests) runs **entirely against
throwaway git repos in temp dirs.** Nothing in the suite writes a ref, an
object, or a byte into this project's `.git` — that is the most expensive
mistake available here, and the fixture makes it impossible rather than
unlikely. The cases that carry weight: index/HEAD/`git status` byte-identical
after a commit; a lost ref race rebuilding on the winner and keeping both; every
retry lost leaving the winner's ref untouched; a withheld secret absent from the
object store, not just from the tree; a torn `arc.jsonl` and a file vanishing
mid-snapshot both surviving.

**Nothing here pushes.** The first push of `run-artifacts` is the owner's call,
because it is the moment unreviewed content leaves the laptop.
