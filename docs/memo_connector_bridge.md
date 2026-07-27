# Memo — the connector bridge: reach becomes record

**Written:** 2026-07-26. **Status:** built, live-proven, offline-tested.
**Rulings:** R-MCP-1 .. R-MCP-6 (below). No locked schema changed;
`stages/verification.py` is **untouched**.

---

## 1. The problem, stated exactly

`model_call.py` could already hand the free agent MCP connectors
(`load_mcp_servers` + `_mcp_option_kwargs`), and the manifest permits them
(§3: *"Connectors are allowed… the only rule is a kept number must be a
re-runnable artifact"*). Two things were missing.

**No connector had ever been wired.** The plumbing had never carried traffic.

**And a connector result could not be a kept number.** `verification.py`
regenerates a claim by RE-RUNNING its artifact, and nothing could re-run an
agent's connector call: the SDK reaches connectors from inside a *model's* turn,
and no model may enter the verification path. The obvious workaround — fetch the
value, paste it into the verification script — is precisely what
`hardcoded_metric_reason` rejects, and rightly: a number written into source
reproduces perfectly while measuring nothing.

So connectors gave the agent **reach without record**. Anything a connector knew
could only ever be an unverified caveat, which in this system means it does not
reach the paper.

## 2. The bridge

**A connector call is re-runnable — just not by the SDK.** MCP is an open
protocol and the `mcp` Python client was already in `venv/`. So the same server,
named in the same `mcp_servers.json`, can be called by deterministic Python with
no model anywhere. That single observation is the whole design.

```
 agent (SDK, mcp__pubchem__compound_property)   ← exploration: reach
        │  ...decides this number is worth keeping
        ▼
 artifact {kind: substrate, substrate_id: "mcp_connector",
           typed_input: {server, tool, arguments, select}}
        │
        ▼
 verification.rerun_artifact  →  tools/run_mcp_tool.py  →  the SAME server
        (no model in this path)                            (re-asked, not re-read)
```

The artifact records **the call, never the answer**, so a re-run genuinely
re-asks the service. Nothing in `verification.py` needed to change: wrapping the
connector as a substrate made it re-runnable through the door that already
existed — which is what the task's hint (*"wrapping a connector as a substrate
may be most of the answer"*) turns out to mean in this codebase.

### What was built

| Piece | What it does |
|---|---|
| `tools/mcp_config.py` | The **one** reader of `mcp_servers.json`, shared by the SDK door and the deterministic door, so the two can never read different definitions of the same server. Also expands `${VAR}`, drops comment entries, and composes the agent-facing connector catalogue. |
| `tools/run_mcp_tool.py` | The deterministic MCP client wrapper. Typed input `{server, tool, arguments, select}`, scalar summary out, no model. |
| `connectors/pubchem_mcp_server.py` | A real MCP server over PubChem PUG-REST — `compound_property` and `compound_identity`. |
| registry row `mcp_connector` | Enrollment, so `wrapper_callable` resolves. **`routable=False`.** |
| `substrate_dispatch` run-entry constructor | The one wired surface: how verification reads a re-run summary. |
| free-experimenter prompt block | Tells the agent the artifact shape that turns a connector answer into a kept number. |
| `onboarding/mcp_connector/contract.py` | The contract in the house five-section form, **staged not graduated** — it stays out of `substrates.py`/`_CONTRACTS` because nothing routes here, so `contract_for('mcp_connector')` correctly raises (the `bio_db_lookup` precedent). `substrates.py` is untouched. |
| `docs/envelope_card_mcp_connector.md` | The card. Unusual on purpose: `mcp_connector` is a **transport**, so the envelope is stated about the CALL, never about the science of whatever service is on the far end. |

## 3. Rulings

**R-MCP-1 — A connector reaches RECORD by being wrapped as a substrate, and is
enrolled UNROUTABLE.** `mcp_connector` gets a registry row (without one,
`wrapper_callable` raises and no connector claim can be verified), but
`routable=False` with **no adapter and no QoI translation** wired, so stage-4
dispatch still refuses it loudly by name. It has no calibration battery and is
not an instrument a router should ever *choose*; it is a door verification walks
through. Enrollment ≠ routing authority — the registry's own documented pattern.

**R-MCP-2 — A connector may back a kept number only when its config declares
`"_verifiable": true`.** Verification purity is absolute, and an MCP server is an
arbitrary process: some MCP servers **are** language models. Without a gate, a
config edit alone — no code review, no test — would silently put a model inside
the verification path. Nothing in the code can detect this from the outside, so
the gate is the operator's declaration, read strictly (`is True`; not `"true"`,
not `1`). The wrapper refuses an undeclared server **before making any call**.
Exploration is untouched: the agent may call any configured connector freely, and
what it learns is reported as an honest unverified caveat.

**R-MCP-3 — The run-entry constructor is wired for a non-routable substrate.**
This is the one deviation from *"wired only alongside a routability ruling"*, and
it is scoped and deliberate. That map is how `verification.py` reads a re-run
summary **through the substrate's own reader** instead of reaching for
`summary["qoi"]` itself. Leaving it unwired would not keep the connector
unrouted — routing is already refused by the absent adapter — it would make
connector-derived claims *unverifiable*, which is the opposite of the point.

**R-MCP-4 — Numeric only; a string answer is a real result, not a measurement.**
A name, a formula, a SMILES string is genuinely useful and is never coerced into
a number. The agent uses it as context; only scalars become claims.

**R-MCP-5 — Reproduction attests PROVENANCE, not correctness; never trusted
alone, permanently.** Re-running a solver proves a number is a property of the
experiment. Re-calling a database proves it is a property of *the query and the
service*. The source's curation currency and accuracy are unverifiable from
inside, and a stale record looks identical to a good one. This is the LOOKUP-class
doctrine already standing for `bio_db_lookup` and `web_search` (card D3); every
success diagnostic carries it, so the verdict cannot be read as more than it is.

**R-MCP-6 — A volatile value failing its own re-run is correct behavior.** If a
service returns something different, `verify_claim` reports `mismatch` and the
claim does not stand. Nothing is retried, loosened, or smoothed. It means
volatile quantities cannot be *kept* this way — which is true, and better said
loudly than papered over.

## 4. Live proof (2026-07-26)

Against `connectors/pubchem_mcp_server.py`, over real stdio MCP to the real
PubChem API:

- **Deterministic path:** `run_mcp_tool({"server": "pubchem", "tool":
  "compound_property", "arguments": {"identifier": "caffeine", "property":
  "MolecularWeight"}, "select": "value"})` → `valid=true, qoi=194.19` in 0.85 s.
  No model in that call path.
- **The wall:** `verify_claim({"value": 194.19, "artifact": {...}})` →
  `verified: true, reason: "reproduced", rel_error: 0.0`. The same claim asserted
  at 250.0 → `mismatch`, rejected.
- **Second tool:** `compound_identity("aspirin")` → CID 2244.
- **All six failure paths triggered live:** unconfigured server, undeclared
  server (refused before any call), tool error (PubChem 404 on a nonsense
  identifier), missing `select` path, non-numeric value, malformed input.
- **Agent end-to-end:** see §6.

Offline: `tests/test_mcp_connector_bridge.py`, 41 tests, every outcome above
provable without a network via the `config_path` / `call` seams.

## 5. What a user must configure

1. **Copy the template:** `cp mcp_servers.example.json mcp_servers.json`
   (gitignored; it may carry URLs and keys).
2. **Point at a server**, stdio or http/sse, exactly as the SDK expects. **Use
   absolute paths** — a connector is launched both by the agent (whose cwd is its
   per-run workspace) and by the verifier (which may run from anywhere).
3. **Keep secrets out of the file:** write `${SOME_TOKEN}` in a header or env
   value and put the real value in `.env` or the shell. Both doors resolve it.
4. **Decide `_verifiable`.** `true` only if the server is a deterministic data
   source with no model inside it. Omit it otherwise — the connector still works
   for exploration.
5. **Optionally add `_description`** — one line, shown to the agent so it knows
   what the connector is for without calling it to find out.

To run with the bundled PubChem connector, steps 1–2 are the two absolute paths
in the `pubchem` block. Nothing else in the system needs to change: with no
`mcp_servers.json` present, every prompt and code path is byte-identical to
before.

## 6. Open watches

- **The write-up surface does not distinguish a lookup-derived verified number
  from a computed one.** `verify_claim` returns `verified: true` for both, and
  the never-trusted-alone caveat lives in the wrapper's diagnostics and the
  envelope card rather than anywhere a reader of the paper sees. Deliberately not
  patched here: it would mean changing the verdict shape, which is a wider
  decision than this brick. Worth closing if connector claims become common.
- **`_verifiable` is a human declaration, not a machine check** (R-MCP-2 says so
  plainly). It is the thing to audit as connectors proliferate.
- **`http`/`sse` transports, and any third-party server, are written and
  unit-tested but have no live proof.** The reference connector is stdio and
  first-party.

## 7. Agent end-to-end proof

See `docs/journal_2026-07-26_connector_bridge.md` for the supervised run: the
free agent called the connector through the SDK, kept a connector-derived number
as a verified finding, and the run completed with `verification.json` showing the
claim reproduced by the deterministic re-run.
