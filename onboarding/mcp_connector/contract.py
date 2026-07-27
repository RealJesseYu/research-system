"""contract.py — STAGED. Contract for (mcp_connector, external_lookup).
The connector bridge (R-MCP-1, 2026-07-26; docs/memo_connector_bridge.md).

STAGED, NOT GRADUATED: mcp_connector is enrolled routable=False, so
contract_for('mcp_connector') MUST raise — nothing routes to it and no adapter
or QoI translation is wired. The text lives here rather than in substrates.py
for exactly that reason (the bio_db_lookup / alphafold_db precedent); it would
move to substrates.py only under a promotion ruling that does not exist and is
not implied.

What IS wired, and is all that is needed for the bridge: the registry row (so
wrapper_callable resolves tools/run_mcp_tool.py) and the run-entry constructor
(so stages/verification.py can read a re-run summary mechanically, R-MCP-3).

The operative documents are the wrapper's own docstring (tools/run_mcp_tool.py)
and docs/envelope_card_mcp_connector.md; this is the contract in the house
five-section form.
"""

MCP_CONNECTOR_CONTRACT = """INSTRUMENT: mcp_connector — one call to a configured MCP connector.

1. WHAT IT IS.
A `lookup`-class instrument: one tool call to an external service reached over
the Model Context Protocol, made by deterministic Python with no model in the
loop (tools/run_mcp_tool.py). It exists so a connector's answer can be a KEPT
number rather than an unverified caveat — the artifact records the CALL, and an
independent pass re-makes that exact call and must get the same number back.

The free agent reaches the same connectors natively as mcp__<server>__<tool>
while it explores. This instrument is not a second, narrower door onto them: it
is the door VERIFICATION uses, which is why the call must be re-makeable from a
typed input alone.

2. WHAT YOU CONTROL.
Exactly four typed fields: `server` (a connector name from mcp_servers.json),
`tool` (that server's tool name, without the mcp__<server>__ prefix),
`arguments` (the object passed to the tool, verbatim), and `select` (a dotted
path naming the number inside the tool's result — dictionary keys and list
indices only, e.g. "value" or "properties.0.MolecularWeight"). Nothing else is
accepted, and the select path is a locator, never an expression: a path that
could compute would be a second, unverified experiment hiding inside the
verifier.

3. REGIME (mcp_connector, external_lookup).
In-regime: a call whose answer is a scalar the service returns for a stable
query — a curated database record, a computed property, a catalogued constant.
Out of regime, and NOT keepable this way: anything volatile (a value that
changes by the hour will fail its own re-run and be reported as a mismatch,
correctly); anything non-numeric (a name, a formula, a sequence — real results,
but not measurements, and never coerced); and any server not declared
"_verifiable": true by the operator, which is refused outright, because
verification runs with NO model in it and an undeclared MCP server may itself be
a model.

4. WHAT IT RETURNS.
One scalar QoI — the number at `select` — returned ONLY when the connector
answered and that path held a real number. An unconfigured server, an
undeclared one, an unreachable endpoint, a tool error, a missing path, or a
non-numeric value each produce NO number: an honest valid=false summary naming
which of those happened, never a fabricated value.

5. THE DID-IT-WORK GATE AND THE PERMANENT TRUST CLAIM.
The gate is that the connector round-tripped and the named path held a number.
*** NEVER TRUSTED ALONE *** (permanent, the LOOKUP-class doctrine shared with
bio_db_lookup and web_search): re-running attests PROVENANCE — the service still
answers this way — and NOT correctness. The source's own curation currency and
accuracy are unverifiable from inside, and a stale or erroneous record looks
identical to a good one. Corroboration is required before a conclusion rests on
one; every success diagnostic says so.
"""
