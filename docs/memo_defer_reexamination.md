# Memo — re-examining every defer, by testing rather than reading

**Written:** 2026-07-27. **Status:** complete; two capabilities unblocked, one
defer confirmed, two lookups made verifiable. Suite green.

---

## 1. Why

`proteinmpnn` sat unavailable for nine days because its row said "needs a GPU"
and that was false (R-BIO-1). A defer records a judgment made on one day's
evidence and nothing re-examines it unless someone deliberately does. So: every
remaining defer, **tested**, not read.

The rule applied throughout — and the one the ProteinMPNN episode taught —
is that **importable is not runnable**. Two of the five survived a shallow check
and failed a real one, and one of my own tests was wrong before it was right.

## 2. Results

| Substrate | Stated blocker | What the test showed | Verdict |
|---|---|---|---|
| `proteinmpnn` | needs a GPU | 4 designs on CPU in ~2.9 s, recovery 0.5526 | **REFUTED** — acted on (R-BIO-1) |
| `autodock_vina` | no aarch64 build anywhere | remote x86_64: `pip install vina` works and it **docks** — 1iep imatinib/ABL, score −12.513, best pose **−13.286 kcal/mol** | **BLOCKER DEAD** via the remote lane |
| `crispr_guide_scoring` | no verified py3 Doench/CFD scorer | Azimuth 2.0 **imports** under py3, then dies on first use: `SyntaxError: Missing parentheses in call to 'print'` (model_comparison.py:269) — the scoring module is still Python-2 source | **STILL HOLDS**, exactly as written |
| `boltz2` | GPU + downloaded weights | a GPU **is** now reachable (T4 witnessed, `cuda_available=1.0`) | **PATH EXISTS**, boltz2 itself untested |
| `retrosynthesis` | heavy models **and** a reaction route DB | `aizynthfinder` 4.4.1 is on PyPI (so the data dependency is solvable via its `download_public_data`), but pip found **no distribution for Python 3.14** | **PARTLY MOVED** — see §4 |
| `cas_offinder` | OpenCL kernel miscomputes on aarch64 | not in apt on the remote, not on PyPI — needs bioconda or a source build on x86_64 | **UNRESOLVED**, plausible but untested |
| `alphafold_db` | (already un-deferred) | works; its numbers could not be kept | **FIXED** — see §3 |
| `bio_db_lookup` | (already un-deferred) | works; its numbers could not be kept | **FIXED** — see §3 |
| `code_sklearn_eval` | "battery not on the run manifest — owner decision pending" | not a technical blocker | owner's call |

Every row above was truth-edited in `tools/substrate_registry.py` to record what
was found, including the one that was **confirmed**. A defer that survives
re-examination is a more useful record afterwards than before.

### A note on my own testing

My first Vina test reported `FAILED: HTTPError 404` — which was my URL being
wrong, not Vina failing. Reported as unknown rather than as a failure, the real
example paths were then found via the GitHub API, and the second test docked.
Worth recording because the cheap read of the first result would have *confirmed*
the defer wrongly, which is the same error in the opposite direction.

## 3. The two lookups that already worked

`alphafold_db` and `bio_db_lookup` were un-deferred on network grounds in July
2026 and have returned real values ever since. But **no run-entry constructor
was wired**, so the verification wall could not read a re-run and every value
they produced was stuck as an unverified caveat. Exactly the gap the connector
bridge closed for MCP, still open for these two.

One line each. Proven live:

- AlphaFold DB mean pLDDT for P0DP23 → **85.25, reproduced at `rel_error 0.0`**;
  the same claim asserted at 99.9 → `mismatch`.
- PDB round-trip for 4HHB → **reproduced**; a non-resolving id (`9ZZZ`) stays
  `qoi_error` rather than becoming a fabricated 1.0.

Same class and same reasoning as `mcp_connector` (R-MCP-3/5): these are
LOOKUP-class tools, so reproduction attests **provenance** — the service still
answers this way — and never correctness. **No routing authority is granted**:
both rows stay `routable=False`, adapter and QoI translation stay unwired,
`contract_for` still raises, and `tests/test_lookup_verification.py` asserts all
of that so a reader cannot later be mistaken for a promotion.

## 4. A limitation this exercise exposed in the remote lane

`aizynthfinder` failed to install remotely with "no matching distribution" — and
the cause is **ours, not theirs**. `tools/run_remote_job.py` pins the remote
Python to the *client's* version, because Modal ships the entry point as a
serialized closure and refuses a mismatch. The venv is on 3.14, so any package
that does not yet support 3.14 is unreachable remotely.

That is a real constraint on a lane whose whole purpose is reaching tools this
machine cannot run. Two ways out, neither built:

1. the job's own code builds a different-Python environment inside the container
   (`apt install python3.12` or `uv`) and shells into it — works today, entirely
   in the caller's code, no wrapper change;
2. a non-serialized dispatch path, which removes the version coupling but is a
   larger change to how the runner is shipped.

Recorded rather than fixed: it has one real customer so far.

## 5. What changed in capability terms

**Reachable now that was not this morning:** molecular docking (AutoDock Vina,
remotely, proven), GPU model inference generally (proven), protein sequence
design (locally, proven), and verified numbers from AlphaFold DB and the four
biological databases.

**Still genuinely blocked:** CRISPR guide scoring (no py3 scorer exists — the
prohibition on hand-transcribing coefficients stands), Cas-OFFinder (untested on
x86_64), retrosynthesis (reachable in principle, blocked by §4).

## 6. What is next

- Test `cas_offinder` on remote x86_64 via bioconda — the last untested blocker.
- If retrosynthesis matters, use workaround §4.1 from inside a job's code.
- `code_sklearn_eval` needs an owner decision, not a test.
