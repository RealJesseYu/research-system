"""The connector bridge: an MCP connector's answer as a KEPT, re-runnable number.

Offline in full. Every live-network path is exercised through the wrapper's
injection seams (`config_path` for the connector definition, `call` for the
protocol round trip), so the whole outcome table — success, refusal, transport
failure, tool error, missing path, non-numeric value — is provable without a
server. The live proof lives in docs/memo_connector_bridge.md.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages import verification
from tools import mcp_config, run_mcp_tool as mcp_tool
from tools import substrate_dispatch as dispatch
from tools import substrate_registry as registry

SID = "mcp_connector"


def _config(**servers) -> str:
    """Write a connector config to a temp file and return its path. The caller
    is responsible for the temp dir's lifetime (tests use TemporaryDirectory)."""
    d = tempfile.mkdtemp()
    p = Path(d) / "mcp_servers.json"
    p.write_text(json.dumps(servers))
    return str(p)


class FakeResult:
    """The shape tools/run_mcp_tool reads off an MCP CallToolResult: structured
    content when the server sent it, text blocks otherwise, plus isError."""

    class _Block:
        def __init__(self, text):
            self.text = text

    def __init__(self, structured=None, text=None, is_error=False):
        self.structuredContent = structured
        self.content = [self._Block(text)] if text is not None else []
        self.isError = is_error


# ---------------------------------------------------------------------------
# mcp_config — the ONE reader both doors use
# ---------------------------------------------------------------------------
class TestMcpConfig(unittest.TestCase):
    def test_absent_file_is_empty_everywhere(self):
        missing = "/no/such/mcp_servers.json"
        self.assertEqual(mcp_config.load_servers(missing), {})
        self.assertEqual(mcp_config.sdk_servers(missing), {})
        self.assertIsNone(mcp_config.server_config("x", missing))
        self.assertFalse(mcp_config.is_verifiable("x", missing))
        self.assertEqual(mcp_config.connector_catalog(missing), "")

    def test_malformed_file_degrades_to_no_connectors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mcp_servers.json"
            p.write_text("{not json")
            self.assertEqual(mcp_config.load_servers(p), {})

    def test_comment_entries_are_not_servers(self):
        # mcp_servers.example.json documents the format with `_comment` and
        # `_example_*` keys. Copied verbatim, those must not become two servers
        # the SDK is asked to launch.
        path = _config(**{
            "_comment": "docs",
            "_example_stdio": {"type": "stdio", "command": "x"},
            "real": {"type": "stdio", "command": "y"},
        })
        self.assertEqual(list(mcp_config.load_servers(path)), ["real"])
        self.assertEqual(list(mcp_config.sdk_servers(path)), ["real"])

    def test_sdk_map_is_stripped_of_extension_keys(self):
        path = _config(pub={"type": "stdio", "command": "y", "_verifiable": True,
                            "_description": "d"})
        self.assertEqual(mcp_config.sdk_servers(path),
                         {"pub": {"type": "stdio", "command": "y"}})

    def test_a_config_without_extension_keys_reaches_the_sdk_unchanged(self):
        servers = {"cad": {"type": "stdio", "command": "x", "args": ["-m", "s"]}}
        path = _config(**servers)
        self.assertEqual(mcp_config.sdk_servers(path), servers)

    def test_servers_key_is_unwrapped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mcp_servers.json"
            p.write_text(json.dumps({"servers": {"cad": {"type": "stdio"}}}))
            self.assertEqual(mcp_config.load_servers(p), {"cad": {"type": "stdio"}})

    def test_env_references_resolve_for_the_deterministic_client(self):
        path = _config(api={"type": "http", "url": "https://x/${MCP_TEST_TOKEN}",
                            "headers": {"A": "Bearer ${MCP_TEST_TOKEN}"}})
        with mock.patch.dict(os.environ, {"MCP_TEST_TOKEN": "sekret"}):
            cfg = mcp_config.server_config("api", path)
        self.assertEqual(cfg["url"], "https://x/sekret")
        self.assertEqual(cfg["headers"]["A"], "Bearer sekret")
        # ...and the raw map keeps the reference, so nothing writes a secret back.
        self.assertIn("${MCP_TEST_TOKEN}", mcp_config.load_servers(path)["api"]["url"])

    def test_unset_env_reference_becomes_empty_not_a_crash(self):
        path = _config(api={"type": "http", "url": "https://x/${NO_SUCH_VAR_HERE}"})
        os.environ.pop("NO_SUCH_VAR_HERE", None)
        self.assertEqual(mcp_config.server_config("api", path)["url"], "https://x/")

    def test_verifiable_is_read_never_inferred(self):
        path = _config(
            yes={"type": "stdio", "_verifiable": True},
            stringy={"type": "stdio", "_verifiable": "true"},
            numeric={"type": "stdio", "_verifiable": 1},
            explicit_no={"type": "stdio", "_verifiable": False},
            absent={"type": "stdio"},
        )
        self.assertTrue(mcp_config.is_verifiable("yes", path))
        for name in ("stringy", "numeric", "explicit_no", "absent", "unknown"):
            self.assertFalse(mcp_config.is_verifiable(name, path), name)

    def test_catalog_names_servers_and_the_keeping_recipe(self):
        path = _config(
            pub={"type": "stdio", "_verifiable": True, "_description": "chem db"},
            scratch={"type": "stdio"},
        )
        text = mcp_config.connector_catalog(path)
        self.assertIn("pub", text)
        self.assertIn("chem db", text)
        self.assertIn("KEEPABLE", text)
        self.assertIn("EXPLORATION ONLY", text)      # the undeclared one
        self.assertIn('"substrate_id": "mcp_connector"', text)
        self.assertIn("select", text)


# ---------------------------------------------------------------------------
# select_value — a locator, never an expression
# ---------------------------------------------------------------------------
class TestSelectValue(unittest.TestCase):
    def test_walks_keys_and_list_indices(self):
        payload = {"PropertyTable": {"Properties": [{"MolecularWeight": 194.19}]}}
        self.assertEqual(
            mcp_tool.select_value(payload, "PropertyTable.Properties.0.MolecularWeight"),
            194.19)

    def test_negative_index_walks_from_the_end(self):
        self.assertEqual(mcp_tool.select_value({"a": [1, 2, 7]}, "a.-1"), 7)

    def test_missing_key_names_where_the_walk_stopped(self):
        with self.assertRaises(KeyError) as ctx:
            mcp_tool.select_value({"a": {"b": 1}}, "a.zzz")
        self.assertIn("zzz", str(ctx.exception))
        self.assertIn("a", str(ctx.exception))

    def test_index_out_of_range_is_named(self):
        with self.assertRaises(KeyError) as ctx:
            mcp_tool.select_value({"a": [1]}, "a.5")
        self.assertIn("out of range", str(ctx.exception))


# ---------------------------------------------------------------------------
# run_mcp_tool — the full outcome table, offline
# ---------------------------------------------------------------------------
class TestRunMcpTool(unittest.TestCase):
    def setUp(self):
        self.path = _config(pub={"type": "stdio", "command": "x",
                                 "_verifiable": True},
                            undeclared={"type": "stdio", "command": "x"})
        self.ok = {"server": "pub", "tool": "compound_property",
                   "arguments": {"identifier": "caffeine"}, "select": "value"}

    def _run(self, spec, call=None, **kw):
        return mcp_tool.run_mcp_tool(spec, config_path=self.path, call=call, **kw)

    def test_success_returns_the_selected_scalar(self):
        call = mock.Mock(return_value=FakeResult(structured={"value": 194.19}))
        got = self._run(self.ok, call)
        self.assertTrue(got["valid"])
        self.assertEqual(got["qoi"], 194.19)
        self.assertIn("NEVER-TRUSTED-ALONE", got["diagnostics"])
        # The call went to the configured server with the arguments as written.
        cfg, tool, args = call.call_args[0]
        self.assertEqual(cfg["command"], "x")
        self.assertEqual(tool, "compound_property")
        self.assertEqual(args, {"identifier": "caffeine"})

    def test_text_content_json_is_read_when_there_is_no_structured_output(self):
        call = mock.Mock(return_value=FakeResult(text=json.dumps({"value": 3.5})))
        self.assertEqual(self._run(self.ok, call)["qoi"], 3.5)

    def test_int_result_is_a_number(self):
        call = mock.Mock(return_value=FakeResult(structured={"value": 7}))
        self.assertEqual(self._run(self.ok, call)["qoi"], 7.0)

    def test_undeclared_server_is_refused_before_any_call(self):
        call = mock.Mock()
        got = self._run(dict(self.ok, server="undeclared"), call)
        self.assertFalse(got["valid"])
        self.assertIsNone(got["qoi"])
        self.assertIn("_verifiable", got["diagnostics"])
        call.assert_not_called()   # the purity gate fires BEFORE the connector runs

    def test_unknown_server_names_the_configured_set(self):
        got = self._run(dict(self.ok, server="nope"), mock.Mock())
        self.assertFalse(got["valid"])
        self.assertIn("setup_error", got["diagnostics"])
        self.assertIn("pub", got["diagnostics"])

    def test_transport_failure_is_a_could_not_run(self):
        def boom(*a):
            raise mcp_tool.McpTransportError("TimeoutError: no answer")
        got = self._run(self.ok, boom)
        self.assertFalse(got["valid"])
        self.assertIn("setup_error", got["diagnostics"])
        self.assertIn("could not be reached", got["diagnostics"])

    def test_tool_error_carries_the_servers_own_text(self):
        call = mock.Mock(return_value=FakeResult(text="not_found: no record",
                                                 is_error=True))
        got = self._run(self.ok, call)
        self.assertFalse(got["valid"])
        self.assertIn("not_found: no record", got["diagnostics"])

    def test_missing_select_path_never_fabricates(self):
        call = mock.Mock(return_value=FakeResult(structured={"other": 1}))
        got = self._run(self.ok, call)
        self.assertFalse(got["valid"])
        self.assertIsNone(got["qoi"])
        self.assertIn("no value at select path", got["diagnostics"])

    def test_non_numeric_value_is_reported_never_coerced(self):
        call = mock.Mock(return_value=FakeResult(structured={"value": "194.19"}))
        got = self._run(self.ok, call)
        self.assertFalse(got["valid"])
        self.assertIsNone(got["qoi"])
        self.assertIn("not a number", got["diagnostics"])

    def test_a_boolean_is_not_a_measurement(self):
        call = mock.Mock(return_value=FakeResult(structured={"value": True}))
        self.assertFalse(self._run(self.ok, call)["valid"])

    def test_empty_reply_is_an_honest_failure(self):
        call = mock.Mock(return_value=FakeResult())
        got = self._run(self.ok, call)
        self.assertFalse(got["valid"])
        self.assertIn("no content", got["diagnostics"])

    def test_input_jail(self):
        for spec, expect in [
            ({"server": "pub", "tool": "t", "arguments": {}}, "missing required"),
            (dict(self.ok, extra=1), "unsupported field"),
            (dict(self.ok, server=""), "'server'"),
            (dict(self.ok, arguments="x"), "'arguments'"),
            ("not a dict", "must be a dict"),
        ]:
            got = self._run(spec, mock.Mock())
            self.assertFalse(got["valid"])
            self.assertIn(expect, got["diagnostics"])

    def test_summary_shape_is_the_scalar_wrapper_contract(self):
        got = self._run(self.ok, mock.Mock(return_value=FakeResult(
            structured={"value": 1.0})))
        self.assertEqual(sorted(got), ["diagnostics", "qoi", "runtime_s", "valid"])
        self.assertIsInstance(got["runtime_s"], float)


# ---------------------------------------------------------------------------
# Registry enrollment — reachable by verification, NOT routable
# ---------------------------------------------------------------------------
class TestRegistryEnrollment(unittest.TestCase):
    def test_enrolled_but_deliberately_unroutable(self):
        record = registry.get(SID)
        self.assertEqual(record.wrapper, "tools/run_mcp_tool.py")
        self.assertFalse(record.routable)
        self.assertNotIn(SID, registry.routable_ids())
        self.assertNotIn(SID, registry.permitted_ids())

    def test_not_offered_in_the_free_agents_substrate_catalogue(self):
        # The catalogue lists routable instruments. Connectors are offered by
        # the connector catalogue instead, which knows what is configured.
        self.assertNotIn(SID, registry.substrate_tools_catalog())

    def test_lookup_class_is_approximate_so_it_is_never_blindly_trusted(self):
        self.assertTrue(registry.is_approximate(SID))

    def test_wrapper_resolves_to_the_deterministic_client(self):
        self.assertIs(dispatch.wrapper_callable(SID), mcp_tool.run_mcp_tool)

    def test_verification_can_read_a_summary_but_stage_4_cannot_route(self):
        # The one wired surface is the run-entry constructor (R-MCP-3): it is
        # what lets verification read a re-run mechanically. Routing surfaces
        # stay unwired, so execution dispatch still refuses loudly.
        self.assertIsNotNone(dispatch.run_entry_constructor_for(SID))
        with self.assertRaises(LookupError):
            dispatch.adapter_for(SID)
        with self.assertRaises(LookupError):
            dispatch.qoi_translation_for(SID)

    def test_run_entry_maps_the_scalar_summary(self):
        entry = dispatch.run_entry_constructor_for(SID)(
            {"valid": True, "qoi": 194.19, "diagnostics": "ok", "runtime_s": 0.8})
        self.assertEqual(entry["qoi_value"], 194.19)
        failed = dispatch.run_entry_constructor_for(SID)(
            {"valid": False, "qoi": None, "diagnostics": "setup_error: x",
             "runtime_s": 0.1})
        self.assertNotIn("qoi_value", failed)          # never a fabricated number
        self.assertIn("setup_error", failed["qoi_error"])


# ---------------------------------------------------------------------------
# THE BRIDGE ITSELF — a connector answer surviving the verification wall
# ---------------------------------------------------------------------------
def _artifact(**over) -> dict:
    art = {"kind": "substrate", "substrate_id": SID,
           "typed_input": {"server": "pub", "tool": "compound_property",
                           "arguments": {"identifier": "caffeine",
                                         "property": "MolecularWeight"},
                           "select": "value"},
           "quantity": "molecular_weight_g_per_mol"}
    art.update(over)
    return art


def _fake_wrapper(value=None, valid=True, diagnostics="ok"):
    """A stand-in for the connector round trip, so the WALL is what is under
    test here rather than the network."""
    def wrapper(spec):
        return {"valid": valid, "qoi": value, "diagnostics": diagnostics,
                "runtime_s": 0.01}
    return mock.patch.object(mcp_tool, "run_mcp_tool", side_effect=wrapper)


class TestConnectorClaimsCrossTheWall(unittest.TestCase):
    def test_a_connector_number_verifies(self):
        with _fake_wrapper(194.19):
            verdict = verification.verify_claim(
                {"value": 194.19, "artifact": _artifact()})
        self.assertTrue(verdict["verified"])
        self.assertEqual(verdict["reason"], "reproduced")

    def test_a_number_the_connector_does_not_return_fails(self):
        with _fake_wrapper(194.19):
            verdict = verification.verify_claim(
                {"value": 250.0, "artifact": _artifact()})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "mismatch")
        self.assertEqual(verdict["reproduced"], 194.19)

    def test_a_connector_that_cannot_run_fails_the_claim(self):
        with _fake_wrapper(None, valid=False, diagnostics="setup_error: down"):
            verdict = verification.verify_claim(
                {"value": 194.19, "artifact": _artifact()})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "rerun_failed")
        self.assertIn("setup_error", verdict["detail"])

    def test_the_recorded_artifact_is_what_gets_re_called(self):
        seen = {}

        def wrapper(spec):
            seen.update(spec)
            return {"valid": True, "qoi": 194.19, "diagnostics": "", "runtime_s": 0}

        with mock.patch.object(mcp_tool, "run_mcp_tool", side_effect=wrapper):
            verification.verify_claim({"value": 194.19, "artifact": _artifact()})
        self.assertEqual(seen["server"], "pub")
        self.assertEqual(seen["arguments"]["property"], "MolecularWeight")
        self.assertEqual(seen["select"], "value")

    def test_a_connector_step_can_feed_a_composition(self):
        # The shape that makes a connector genuinely useful: a real-world value
        # fetched from the service, combined with local computation. The recipe
        # records the WIRING, so the re-run re-fetches rather than re-reading —
        # and the combine's number is not a constant anyone typed.
        recipe = {
            "kind": "composition",
            "steps": [dict(_artifact(), step_id="mw")],
            "combine": {"kind": "code", "inputs": ["mw"],
                        "quantity": "millimoles_per_gram",
                        "code": "metrics = {'millimoles_per_gram': 1000.0 / inputs['mw']}"},
        }
        with _fake_wrapper(194.19):
            out = verification.run_composition(recipe)
        self.assertIsNone(out["error"])
        self.assertEqual(out["steps"]["mw"], 194.19)
        self.assertAlmostEqual(out["value"], 1000.0 / 194.19, places=9)
        with _fake_wrapper(194.19):
            verdict = verification.verify_claim(
                {"value": out["value"], "artifact": out["artifact"]})
        self.assertTrue(verdict["verified"])

    def test_a_pasted_connector_value_is_still_rejected_as_hardcoded(self):
        # The workaround the bridge exists to replace: fetch the number, write it
        # into a script. It reproduces perfectly and is still not a measurement.
        verdict = verification.verify_claim({
            "value": 194.19,
            "artifact": {"kind": "code", "quantity": "molecular_weight",
                         "code": "metrics = {'molecular_weight': 194.19}"}})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "hardcoded_constant")


class TestFreeExperimenterSeesConnectors(unittest.TestCase):
    def test_prompt_carries_the_connector_block_when_configured(self):
        from stages import free_experimenter as fe

        captured = {}

        def fake_call(stage, system_prompt, stage_input, schema, **kw):
            captured["prompt"] = system_prompt
            return {"summary": "s", "findings": [], "publishable": False}, {}

        with mock.patch.object(mcp_config, "connector_catalog",
                               return_value="CONNECTORS (MCP) configured"):
            fe.run_free_investigation("q", call=fake_call)
        self.assertIn("CONNECTORS (MCP) configured", captured["prompt"])

    def test_prompt_is_unchanged_when_no_connector_is_configured(self):
        from stages import free_experimenter as fe

        prompts = []

        def fake_call(stage, system_prompt, stage_input, schema, **kw):
            prompts.append(system_prompt)
            return {"summary": "s", "findings": [], "publishable": False}, {}

        with mock.patch.object(mcp_config, "connector_catalog", return_value=""):
            fe.run_free_investigation("q", call=fake_call)
        self.assertNotIn("CONNECTORS", prompts[0])
        # The substrate catalogue is still composed in. It is no longer the LAST
        # block — the runbook index follows it (2026-07-27) — so this asserts
        # presence rather than position; pinning position would make every
        # future prompt block a test edit.
        self.assertIn(registry.substrate_tools_catalog(), prompts[0])


if __name__ == "__main__":
    unittest.main()


class TestAnAmbiguousIdentifierYieldsNoNumber(unittest.TestCase):
    """The one failure class an independent re-run is BLIND to.

    _first_record returns rows[0] for any query, and the ambiguity was recorded
    in a sibling field `matches` that the substrate wrapper never reads
    (run_mcp_tool keeps payload[select], and select is "value"). So a name
    resolving to several CIDs returned the FIRST one's number as a measurement of
    record — and the wall, re-running the same call, got the same first row and
    stamped it reproduced. Perfectly, forever.

    That is why this must be refused at the connector and not caught downstream:
    re-verification attests PROVENANCE, not identity, so nothing later in the
    chain can notice that the number belongs to an arbitrary one of several
    compounds.
    """

    MULTI = {"PropertyTable": {"Properties": [
        {"CID": 335, "XLogP": 1.9},
        {"CID": 342, "XLogP": 2.0},
        {"CID": 2879, "XLogP": 1.9},
    ]}}

    def test_first_record_reports_the_match_count(self):
        import connectors.pubchem_mcp_server as pubchem
        row, matches = pubchem._first_record(self.MULTI)
        self.assertEqual(matches, 3)
        self.assertEqual(row["CID"], 335)

    def test_a_multi_match_query_refuses_instead_of_returning_row_zero(self):
        import connectors.pubchem_mcp_server as pubchem
        original = pubchem._resolve
        pubchem._resolve = lambda i, n, p: ({"CID": 335, "XLogP": 1.9}, 3, "u")
        try:
            with self.assertRaises(pubchem.PubChemError) as cm:
                pubchem.compound_property("cresol", "XLogP")
        finally:
            pubchem._resolve = original
        self.assertIn("ambiguous", str(cm.exception))
        self.assertIn("3 compounds", str(cm.exception))

    def test_the_refusal_says_how_to_disambiguate(self):
        """A caller that cannot act on the refusal will work around it."""
        import connectors.pubchem_mcp_server as pubchem
        original = pubchem._resolve
        pubchem._resolve = lambda i, n, p: ({"CID": 335, "XLogP": 1.9}, 2, "u")
        try:
            with self.assertRaises(pubchem.PubChemError) as cm:
                pubchem.compound_property("cresol", "XLogP")
        finally:
            pubchem._resolve = original
        self.assertIn("CID", str(cm.exception))

    def test_a_single_match_still_returns_its_number(self):
        import connectors.pubchem_mcp_server as pubchem
        original = pubchem._resolve
        pubchem._resolve = lambda i, n, p: ({"CID": 2519, "XLogP": -0.07}, 1, "u")
        try:
            result = pubchem.compound_property("caffeine", "XLogP")
        finally:
            pubchem._resolve = original
        self.assertEqual(result["value"], -0.07)
        self.assertEqual(result["matches"], 1)
