# Journal — 2026-07-26: the connector bridge, live

Evidence for `docs/memo_connector_bridge.md` (R-MCP-1..6). Every number below
was re-derived from disk; nothing is dictated from memory.

---

## 1. Deterministic path (no model anywhere)

```
$ venv/bin/python3 -m tools.run_mcp_tool '{"server":"pubchem",
    "tool":"compound_property",
    "arguments":{"identifier":"caffeine","property":"MolecularWeight"},
    "select":"value"}'
{ "valid": true, "qoi": 194.19, "runtime_s": 0.849,
  "diagnostics": "value=194.19 from connector 'pubchem' tool
     'compound_property'. NEVER-TRUSTED-ALONE: ..." }
```

Python → stdio MCP server → PubChem PUG-REST → 194.19 g/mol, which is
caffeine's molecular weight. The server process is launched by the wrapper, so
the connector itself is what re-runs — not a re-implementation of its API.

**Second tool, same server:** `compound_identity("aspirin")` → CID 2244.

**All six failure jails triggered live**, each returning `valid=false`, `qoi=None`
and a named reason — no fabrication in any of them:

| Trigger | Reported as |
|---|---|
| `server: "nosuch"` | `setup_error: no MCP server named 'nosuch' is configured — mcp_servers.json defines ['pubchem']` |
| server without `_verifiable` | refusal naming the missing declaration, **before any call was made** |
| `identifier: "zzzznotacompound"` | the server's own `not_found: ... (HTTP 404)` |
| `select: "nope.deeper"` | `no 'nope' at <result> — the result carries cid, matches, property, source_url, text, value` |
| `select: "text"` (a formula) | `the value at 'text' is 'C8H10N4O2', not a number ... it is not coerced` |
| an extra input field | `input rejected: unsupported field(s): extra` |

## 2. The wall

```python
art = {"kind": "substrate", "substrate_id": "mcp_connector",
       "typed_input": {"server": "pubchem", "tool": "compound_property",
                       "arguments": {"identifier": "caffeine",
                                     "property": "MolecularWeight"},
                       "select": "value"},
       "quantity": "molecular_weight_g_per_mol"}

verify_claim({"value": 194.19, "artifact": art})
  -> {"verified": true, "reason": "reproduced", "rel_error": 0.0}
verify_claim({"value": 250.0,  "artifact": art})
  -> {"verified": false, "reason": "mismatch", "reproduced": 194.19}
```

`stages/verification.py` was **not modified**. Wrapping the connector as a
substrate made it re-runnable through the door that already existed.

## 3. SDK path (the agent's own door)

A narrow probe (`connector_probe`, Opus, FULL profile, 20.7 s) forbidden from
using Bash, the web, any local library, or memory:

```json
{"connector_available": true, "tool_called": "mcp__pubchem__compound_property",
 "cid": 5429, "smiles": "CN1C=NC2=C1C(=O)NC(=O)N2C", "tpsa": 67.2}
```

Correct on all three counts for theobromine. The connector was reachable as a
native SDK tool, which is the half the deterministic wrapper does not exercise.

**One observation, unresolved:** in that probe the model reported that its first
attempt at `mcp__pubchem__compound_identity` came back "No such tool available",
so it used three `compound_property` calls instead. The server demonstrably
exposes both tools (a deterministic `list_tools` returns `compound_property` and
`compound_identity`), and the full run below used `compound_identity`
successfully — so this looks like a transient at server start rather than a
permission gap. Recorded rather than explained away; watch for a recurrence.

## 4. Supervised run, end to end

`runs/connector-20260726T223414Z` — auto mode, Opus, ~3 minutes, 677,780 tokens.

**Goal:** cross-check PubChem's curated molecular weight against a locally
computed one for caffeine, theophylline and theobromine, and report the largest
disagreement. Chosen because it makes the connector load-bearing (only PubChem
can resolve a *name* to a structure) while keeping the arithmetic checkable.

**What the agent did, from its workspace:** called the connector's
`compound_identity` for each compound to get CIDs and SMILES, read each curated
`MolecularWeight` through `compound_property`, fed those exact SMILES to the
`rdkit` substrate, and — unprompted — wrote a third, independent check
(`mw_compare.py`: its own SMILES parser plus IUPAC-2021 atomic weights, no
rdkit, no network). It also wrote `check_mcp_select.py` to confirm its `select`
path returned what it expected before recording it as an artifact, which is
exactly what the prompt block asks for.

**Result: 8 findings, 8 verified, `publishable=True`.** Three of the eight are
`mcp_connector` artifacts:

| Claim | Value | Verdict |
|---|---|---|
| PubChem curated MolecularWeight, caffeine | 194.19 | reproduced, rel_error 0.0 |
| PubChem curated MolecularWeight, theophylline | 180.16 | reproduced, rel_error 0.0 |
| PubChem curated MolecularWeight, theobromine | 180.16 | reproduced, rel_error 0.0 |

That is the deliverable: a number that came from an external service, kept as a
verified result, regenerated by a deterministic pass with no model in it.

**The science, incidentally:** largest disagreement 0.007 g/mol (~3.9e-5
relative), which is what two-decimal rounding of PubChem's displayed record
predicts. No substantive discrepancy — the corroboration the never-trusted-alone
doctrine asks for, and it passed.

## 5. Suite

1635 passed / 1 skipped before. After: **1715 passed / 1 skipped**, including the
41 new tests in `tests/test_mcp_connector_bridge.py`. One pinned-list test
(`test_substrate_registry.py::test_all_enrolled_substrates_in_order`) was updated
for the new registry row — the expected consequence of a governance change, not a
behavior change.

*Caveat on that count: another session was editing this working tree
concurrently (a "heavy verification lane" in `verification.py`,
`run_python_experiment.py` and `free_experimenter.py`, with its own tests). The
+80 is both sessions' tests, not only this work's 41.*

## 6. Open watches

- **The paper surface does not distinguish a lookup-derived verified number from
  a computed one.** The verdict carries `verified: true` either way; the
  never-trusted-alone caveat lives in the wrapper diagnostics and this card, not
  in what a reader of the write-up sees. Worth closing if connector claims become
  common.
- **`_verifiable` is a human declaration, not a machine check.** It is the thing
  to audit if connectors proliferate.
- **`http`/`sse` transports and any third-party server are written and
  unit-tested but have no live proof.** The reference connector is stdio and
  first-party.
