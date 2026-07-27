# Envelope Card — (mcp_connector, external_lookup)

*The card unit is the (substrate, regime) pair. This one is unusual and the
unusual part is the point: `mcp_connector` is not an instrument, it is a
**transport**. What it can and cannot do is therefore stated about the CALL —
the round trip and the read — and never about the science of whatever service
sits on the far end. Each connector you configure brings its own truthfulness,
which this card cannot vouch for and does not try to.*

Written 2026-07-26 alongside `docs/memo_connector_bridge.md` (R-MCP-1..6).

## 1. Identity

- **Substrate id:** `mcp_connector`
- **Wrapper:** `tools/run_mcp_tool.py` (deterministic Python; no model in the path)
- **Regime:** `external_lookup` — one Model Context Protocol tool call whose
  answer is a scalar the service returns for a stable query.
- **Typed input:** `{server, tool, arguments, select}` — exactly four fields.
- **Returns:** the scalar wrapper summary `{valid, qoi, diagnostics, runtime_s}`.
- **Configured connectors:** `mcp_servers.json` (gitignored). The bundled
  reference connector is `connectors/pubchem_mcp_server.py`.

## 2. Provenance

**State: `drafted-by-agent`.** No expert review, no calibration battery. The
substrate is enrolled **`routable=False`** and stays there: nothing routes to it,
and the only surface wired for it is the run-entry constructor verification needs
(R-MCP-3). Promotion is a separate ruling and is not implied by anything here.

## 3. Validated envelope

### 3A. Measured, from REAL calls (2026-07-26, against `pubchem`)

| Check | Result |
|---|---|
| Round trip through a live stdio MCP server | `caffeine` MolecularWeight → **194.19**, ~0.85 s including server launch |
| Re-run determinism (the property the bridge rests on) | identical value on re-call; `verify_claim` → `reproduced`, rel_error 0.0 |
| A wrong claimed value | `verify_claim` → `mismatch` (250.0 vs 194.19), correctly rejected |
| Second tool on the same server | `compound_identity("aspirin")` → CID **2244** |
| Composition step feeding local computation | connector scalar → combine, re-verified end-to-end (offline harness) |

### 3B. Ruled bounds (not measured, ruled in the memo)

- **Numeric only.** A non-numeric answer (a name, a formula, a SMILES string)
  is a real result and is **not** a measurement; it is never coerced (R-MCP-4).
- **Stable queries only.** A value that genuinely changes between calls will
  fail its own re-run and be reported as a `mismatch`. That is correct behavior,
  not a defect — but it means volatile quantities cannot be *kept* this way.
- **Declared connectors only.** A server without `"_verifiable": true` is
  refused by the wrapper (R-MCP-2).

## 4. Known failure modes

Each produces an honest `valid=false` with a named reason and **no number** —
all six proven by triggering, live, 2026-07-26:

1. server not configured → `setup_error`, naming the configured set;
2. server not declared `_verifiable` → refusal, **before** any call is made;
3. endpoint unreachable / timeout → `setup_error` (could-not-run);
4. the tool itself errored → the server's own error text, bounded;
5. `select` path absent → names where the walk stopped and what was there;
6. value at `select` is not numeric → reported, never coerced.

## 5. Diagnostics CAN / CANNOT see

**CAN:** whether the connector round-tripped; whether the named path held a
number; which of the six failures above occurred; wall-clock per call.

**CANNOT:** whether the number is *right*. The wrapper sees an answer, not the
service's curation process, its currency, or its silent revisions. A stale or
erroneous record is indistinguishable from a good one from this side.

## 6. Extraction contract (verbatim)

`select` is a **locator**: dotted dictionary keys and list indices, walked
against the tool's structured content (or its text content parsed as JSON).
Nothing is evaluated, nothing is computed, no wildcards. A path that could
compute would be a second, unverified experiment hiding inside the verifier.

## 7. Cost model

One network round trip per call, plus stdio server launch for local connectors:
**~0.85 s measured** for the reference connector including launch. Negligible
spend; no model tokens at all — this wrapper never calls one.

## 8. Negative space + open watches

- **PERMANENT trust claim (LOOKUP class, shared with `bio_db_lookup` and
  `web_search`): never trusted alone.** Re-running attests **provenance** — the
  service still answers this way — and **not correctness**. Every success
  diagnostic says so. This is standing, not a provisioning gate: no future
  promotion lifts it.
- **The purity boundary is a human declaration, not a machine check.** Nothing
  in the code can tell whether an MCP server has a model inside it. `_verifiable`
  is the operator asserting it does not. Watch: if connectors proliferate, that
  declaration is the thing to audit.
- **Per-connector envelopes are absent by design.** This card covers the call.
  A connector whose *answers* need an envelope (accuracy, coverage, units)
  deserves its own card and, if it is to be routed, its own registry row.
- **Not exercised yet:** the `http`/`sse` transports (the reference connector is
  stdio), and a third-party server. Both are written and unit-tested; neither has
  a live proof, and this card does not claim one.
