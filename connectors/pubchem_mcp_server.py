"""pubchem_mcp_server — an MCP connector over PubChem PUG-REST. NO AI inside.

WHY THIS ONE. The system can already compute cheminformatics descriptors from a
structure (`tools/run_rdkit.py`), but it had no way to find out what a structure
IS: nothing in the repo could turn "caffeine" into a SMILES string, or reach the
curated experimental record for a compound. PubChem is the canonical public
answer to both, it needs no API key, and its identifiers are stable — so it is a
genuinely useful capability the project lacked, and one anybody can reproduce.

WHAT IT IS. A first-party MCP server, deliberately: it speaks the real protocol
over stdio, so it exercises the same path any third-party connector takes (the
SDK launches it for the agent; `tools/run_mcp_tool.py` launches it for
verification), while keeping the failure modes ours to reason about. Nothing
here is specific to being first-party — swap the config to point at someone
else's server and both paths work unchanged.

DETERMINISTIC BY CONSTRUCTION. One HTTP GET per call against a documented
endpoint, no model, no state, no randomness. The only transformation is a
numeric coercion: PUG-REST returns some properties as JSON strings
("MolecularWeight": "194.19"), and a caller asking for a measurement should get
a number. The coercion happens HERE, at the source, and the raw text travels
beside it in `text` — so nothing downstream has to guess whether a string was a
number, and nothing invents one that was not there.

WHAT THE NUMBERS ARE. PubChem's computed properties are computed by PubChem
from the deposited structure; its records are curated by depositors. A returned
value is authoritative about WHAT THE DATABASE SAYS. That is not the same as
being right, and re-fetching it proves provenance rather than correctness — the
never-trusted-alone doctrine the wrapper's diagnostics carry.

Run: python connectors/pubchem_mcp_server.py   (stdio; configured in
mcp_servers.json — see mcp_servers.example.json)
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

try:  # certifi is already in venv/ (the scholar_search.py precedent)
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover — fallback if certifi is unavailable
    _SSL_CONTEXT = ssl.create_default_context()

from mcp.server.fastmcp import FastMCP

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
TIMEOUT_S = 20.0
USER_AGENT = "research-system/pubchem-mcp (compound property lookup)"

# The namespaces a caller may resolve against. An allowlist, so a malformed
# request is refused before it becomes a URL.
NAMESPACES = ("name", "cid", "smiles", "inchikey", "formula")

# The properties this connector serves, and whether each is numeric. Written out
# rather than passed through, so a typo becomes a named refusal instead of an
# opaque PubChem 400 — and so the numeric/text split is a declared fact rather
# than something inferred from whatever came back this time.
PROPERTIES = {
    "MolecularWeight": True,
    "ExactMass": True,
    "MonoisotopicMass": True,
    "XLogP": True,
    "TPSA": True,
    "Complexity": True,
    "Charge": True,
    "HBondDonorCount": True,
    "HBondAcceptorCount": True,
    "RotatableBondCount": True,
    "HeavyAtomCount": True,
    "MolecularFormula": False,
    "SMILES": False,
    "ConnectivitySMILES": False,
    "InChIKey": False,
    "IUPACName": False,
    "Title": False,
}

# log_level WARNING: FastMCP's INFO chatter goes to stderr, which lands in a
# run's captured output and says nothing a reader needs. Errors still surface.
mcp = FastMCP("pubchem", log_level="WARNING")


class PubChemError(RuntimeError):
    """The lookup could not be completed. Raised so the MCP layer reports a tool
    error — never a fabricated value."""


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S,
                                    context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise PubChemError(
                "not_found: PubChem has no record matching that identifier "
                "(HTTP 404) — no value was fabricated") from e
        raise PubChemError(
            f"PubChem returned HTTP {e.code} — the lookup could not run") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PubChemError(
            f"PubChem is unreachable ({type(e).__name__}: {e}) — the lookup "
            "could not run") from e
    except ValueError as e:
        raise PubChemError(f"PubChem returned unreadable JSON: {e}") from e


def _first_record(payload: dict) -> dict:
    """The first Properties row, or a raised error. PubChem answers a name that
    matches several compounds with several rows; taking the first is PubChem's
    own best match and is stated in the returned `matches` count, so a caller
    can see that the query was ambiguous rather than being told it was not."""
    try:
        rows = payload["PropertyTable"]["Properties"]
    except (KeyError, TypeError) as e:
        raise PubChemError(
            "PubChem's reply carried no PropertyTable — nothing to read") from e
    if not rows:
        raise PubChemError(
            "not_found: PubChem matched no compound for that identifier")
    return rows[0], len(rows)


def _resolve(identifier: str, namespace: str, properties: list) -> tuple:
    if namespace not in NAMESPACES:
        raise PubChemError(
            f"namespace {namespace!r} is not one of {', '.join(NAMESPACES)}")
    if not str(identifier).strip():
        raise PubChemError("identifier must be a non-empty string")
    url = (f"{BASE}/{namespace}/{urllib.parse.quote(str(identifier).strip(), safe='')}"
           f"/property/{','.join(properties)}/JSON")
    row, matches = _first_record(_get(url))
    return row, matches, url


@mcp.tool()
def compound_property(identifier: str, property: str,
                      namespace: str = "name") -> dict:
    """Look up one property of one compound in PubChem.

    identifier: what to look up — a name ("caffeine"), a CID ("2519"), a SMILES
        string, an InChIKey, or a formula, matching `namespace`.
    property: one of PubChem's computed/curated properties, e.g. MolecularWeight,
        TPSA, XLogP, HBondDonorCount, MolecularFormula, SMILES, IUPACName.
    namespace: name | cid | smiles | inchikey | formula (default: name).

    Returns {cid, property, value, text, matches, source_url}. `value` is the
    number when the property is numeric and null otherwise; `text` is always the
    raw value as PubChem sent it. Select `value` for a measurement.
    """
    if property not in PROPERTIES:
        raise PubChemError(
            f"property {property!r} is not served by this connector; available: "
            f"{', '.join(sorted(PROPERTIES))}")
    row, matches, url = _resolve(identifier, namespace, [property])
    if property not in row:
        raise PubChemError(
            f"PubChem returned no {property} for that compound (it carries "
            f"{', '.join(sorted(row))}) — no value was fabricated")
    raw = row[property]
    value = None
    if PROPERTIES[property]:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise PubChemError(
                f"PubChem returned {raw!r} for {property}, which is declared "
                "numeric but does not parse as a number — refusing to coerce")
    return {
        "cid": row.get("CID"),
        "property": property,
        "value": value,
        "text": str(raw),
        "matches": matches,
        "source_url": url,
    }


@mcp.tool()
def compound_identity(identifier: str, namespace: str = "name") -> dict:
    """Resolve a compound to its structure and identifiers — the lookup the
    system could not do before (a local descriptor library needs a structure;
    this is where the structure comes from).

    Returns {cid, smiles, formula, inchikey, iupac_name, matches, source_url}.
    Feed `smiles` straight into a cheminformatics tool.
    """
    fields = ["SMILES", "MolecularFormula", "InChIKey", "IUPACName"]
    row, matches, url = _resolve(identifier, namespace, fields)
    return {
        "cid": row.get("CID"),
        "smiles": row.get("SMILES"),
        "formula": row.get("MolecularFormula"),
        "inchikey": row.get("InChIKey"),
        "iupac_name": row.get("IUPACName"),
        "matches": matches,
        "source_url": url,
    }


if __name__ == "__main__":
    mcp.run()
