---
name: remote_gpu
description: How to run anything on rented hardware — GPU, x86_64, or just a bigger machine. Read this before any remote job.
status: WORKS
requirements: Modal account (already authenticated)
---

# The remote lane — rented hardware, by the second

`from tools.run_remote_job import run_remote_job`. Use it when this machine
genuinely cannot do the job: a tool that needs a GPU, one with no aarch64 build,
or one that wants more machine than is here. It is **not** a way to avoid
thinking, and it costs real money.

## RECORDING THE RESULT — the one rule that shapes everything

**A REMOTE RESULT IS AN INPUT, NEVER A CLAIM.**

The verification wall regenerates a number by re-running its artifact. A remote
job cannot be re-run: it would bill the GPU again, and GPU arithmetic is often
not bit-reproducible, so a perfectly good result would fail as a `mismatch`.
There is deliberately no `remote` artifact kind — the wrapper does not even
return a `qoi`.

So the working pattern, every time:

1. run the expensive thing **once**, remotely;
2. bring its outputs back as **files**;
3. compute your findings **locally** from those files, in a sandbox profile,
   with the data embedded inline in a self-contained artifact;
4. mark anything taken straight from the remote job `"verified": false`, and say
   where it came from.

The fold is the input; the RMSD you compute from it is the finding.

## Invocation

```python
run_remote_job({
    "code": "...",                     # runs on the remote machine
    "gpu": "A10G",                     # T4 L4 A10G A100 A100-80GB H100, or None for CPU
    "python_version": "3.12",          # OPTIONAL — see below, you usually want this
    "pip": ["torch", "transformers"],
    "apt": ["build-essential"],        # OPTIONAL system packages
    "input_files": {"in.pdb": b"..."}, # OPTIONAL, sent to the job
    "output_files": ["out.pdb"],       # OPTIONAL, brought back as bytes
    "timeout_s": 1800,                 # bounded, max 3600
})
# -> {"valid", "metrics", "artifacts", "diagnostics", "runtime_s"}   note: no qoi
```

Your code reports numbers exactly as the local sandbox does — write
`{"metrics": {...}}` to `/work/result.json`. Write files you want back to
`/work/<name>` and declare them in `output_files`.

## `python_version` — you probably need it

The remote image's Python is pinned to this client's (3.14) because the entry
point is shipped as a serialized closure. A lot of scientific software has not
caught up: **Boltz caps at <3.13, aizynthfinder has no 3.14 build**. Setting
`python_version: "3.12"` builds the job a separate venv at that version. If a
package "has no matching distribution", this is almost always why.

## Cost

Billed per second to the owner's card, against a **$100 ceiling** enforced
before dispatch (`tools/gpu_budget.py`). A job is refused if its **worst case** —
the full timeout at that GPU's rate — exceeds what is left. So do not pass
`timeout_s: 3600` on an H100 for a job you expect to take a minute; you will be
refused for money you were never going to spend.

Rough rates per hour: CPU $0.20 · T4 $0.80 · A10G $1.40 · A100 $2.50 · H100 $4.50.
A typical protein fold is **4–20 cents**. Check `gpu_budget.report()` for what
remains.

**Containers are ephemeral, so weights download EVERY run.** That is usually
most of the time and cost. If you have ten sequences to fold, do them in **one**
job, not ten.

## Gotchas already hit

- A **pip console script** (`boltz`, `vina`) is callable by name — the wrapper
  puts the job venv's `bin` on PATH. If you see `FileNotFoundError` for a tool
  that installed fine, that is a wrapper bug, not your code.
- **Check for output files rather than trusting the exit code.** Boltz exited
  `0` having written nothing when its MSA server timed out.
- **External services inside a job are a real failure mode** — `api.colabfold.com`
  timed out, a 5.7 GB embedding download broke mid-transfer. Prefer a mode that
  needs no external call, and if you must depend on one, say so in the finding.
- A job that **runs and fails is still billed**. It consumed the machine.
