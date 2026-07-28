"""
materials_lookup.py — Materials Project lookup for the Step-17 ideation
rebuild: when a hypothesis names a solid material, this tool supplies real
scalar properties instead of letting a model invent numbers.

Talks to api.materialsproject.org's materials/summary endpoint directly
over REST (a recorded ruling: the official mp-api client and its pymatgen
dependency tree are deliberately NOT installed). The API key is mandatory
and personal; it is read as MP_API_KEY from the project root's .env file
via python-dotenv (already in venv/). HTTP style copied from
fetch_literature.py: stdlib urllib + certifi, descriptive User-Agent,
bounded retry.

Summarize-at-the-wrapper: the caller gets a small scalar-only dict —
{"source": "materialsproject:<mp-id>", "formula", <requested properties>}.
The full summary document (structures, metadata, everything non-scalar)
never leaves this module. On ANY failure — no key, rejected key, no match,
missing property, non-scalar property, HTTP error — this raises a
plain-language error and never returns a fabricated number.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

try:
    # certifi is already present in venv/ (pulled in transitively by the
    # Claude SDK's HTTP stack); this is not a new dependency of this module.
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

#: Ceiling on an honoured Retry-After. The header is SERVER-CONTROLLED, and it was
#: taken at face value: `int(e.headers.get("Retry-After", 20))`. Two failures came
#: with that. A server sending the HTTP-DATE form ("Wed, 21 Oct 2026 07:28:00 GMT")
#: raised an uncaught ValueError, so a plain 429 surfaced as a crash instead of a
#: retry. And a large numeric value was slept in full — multiplied by the retry
#: count, a misconfigured or hostile server could park a study in time.sleep for
#: hours, with the run looking exactly like normal quiet work.
MAX_RETRY_AFTER_S = 120


def _retry_after_seconds(headers, default: int = 20) -> int:
    """Seconds to wait from a Retry-After header: numeric only, clamped, never
    raising. A date-form value falls back to `default` — waiting the default is
    always better than crashing on a retryable status."""
    raw = None
    try:
        raw = headers.get("Retry-After")
    except Exception:  # noqa: BLE001 — a header map that misbehaves is not fatal
        raw = None
    try:
        wait = int(str(raw).strip())
    except (TypeError, ValueError):
        wait = default
    return max(0, min(wait, MAX_RETRY_AFTER_S))


MP_API_URL = "https://api.materialsproject.org/materials/summary/"
USER_AGENT = "research-system/step17-materials_lookup.py (ideation materials retrieval)"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

# Locked before URL interpolation, same discipline as run_cfd's field-name
# regex: a chemical formula is letters, digits, parentheses and dots.
_FORMULA_RE = re.compile(r"^[A-Za-z0-9().]+$")
_PROPERTY_RE = re.compile(r"^[a-z0-9_]+$")

DEFAULT_PROPERTIES = ("density",)

# Fields needed to identify the ground-state entry among polymorphs; always
# requested, independent of what the caller asked for.
_SELECTION_FIELDS = ("material_id", "formula_pretty", "energy_above_hull")

MAX_RETRIES = 5


def _http_get(url: str, headers: dict[str, str], retries: int = MAX_RETRIES) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(
                    "Materials Project rejected the API key (HTTP "
                    f"{e.code}). Check that the key pasted after MP_API_KEY= in "
                    f"{_ENV_PATH} is your current key from your materialsproject.org "
                    "profile dashboard. No result was returned — nothing was fabricated."
                ) from e
            last_error = e
            if e.code in (429, 503) and attempt < retries - 1:
                wait = _retry_after_seconds(e.headers)
                print(f"  Materials Project: HTTP {e.code}, waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"Materials Project request failed with HTTP {e.code} and was not "
                "retried further. No result was returned — nothing was fabricated."
            ) from e
        except (TimeoutError, urllib.error.URLError) as e:
            last_error = e
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  Materials Project: request failed ({e}), waiting {wait}s before retry...")
                time.sleep(wait)
                continue
    raise RuntimeError(
        f"Materials Project was unreachable after {retries} attempts "
        f"(last error: {last_error}). No result was returned — nothing was fabricated."
    )


def _load_api_key() -> str:
    load_dotenv(_ENV_PATH)
    key = os.environ.get("MP_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            f"No Materials Project API key found. Open {_ENV_PATH} and paste your "
            "key directly after MP_API_KEY= (no quotes, no spaces). Keys are free: "
            "log in at materialsproject.org and copy the key from your profile "
            "dashboard. No result was returned — nothing was fabricated."
        )
    return key


def lookup_material(formula: str, properties: list[str] | None = None) -> dict:
    """Look up scalar properties of the ground-state entry for `formula`.

    Returns {"source": "materialsproject:<mp-id>", "formula": <pretty formula>,
    <one key per requested property>}. `properties` defaults to
    DEFAULT_PROPERTIES; names must be summary-document field names in
    snake_case (e.g. "density", "volume", "band_gap"). Among polymorphs the
    entry with the lowest energy_above_hull (the thermodynamic ground state)
    is chosen deterministically; ties break by API return order.
    """
    if not formula or not _FORMULA_RE.match(formula):
        raise ValueError(
            f"lookup_material: formula {formula!r} is not a plain chemical formula "
            "(letters, digits, parentheses and dots only)"
        )
    props = list(properties) if properties else list(DEFAULT_PROPERTIES)
    for p in props:
        if not _PROPERTY_RE.match(p):
            raise ValueError(
                f"lookup_material: property {p!r} is not a valid summary field name "
                "(lowercase snake_case only)"
            )

    api_key = _load_api_key()

    fields = list(dict.fromkeys([*_SELECTION_FIELDS, *props]))
    params = {"formula": formula, "_fields": ",".join(fields), "_limit": 25}
    url = f"{MP_API_URL}?{urllib.parse.urlencode(params)}"
    body = _http_get(url, headers={"User-Agent": USER_AGENT, "X-API-KEY": api_key})

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Materials Project replied but its response was not parseable JSON ({e}). "
            "No result was returned — nothing was fabricated."
        ) from e

    entries = parsed.get("data") if isinstance(parsed, dict) else None
    if not entries:
        raise RuntimeError(
            f"Materials Project has no entry matching formula {formula!r}. "
            "No result was returned — nothing was fabricated."
        )

    def _hull(entry: dict) -> float:
        v = entry.get("energy_above_hull")
        return v if isinstance(v, (int, float)) else float("inf")

    ground_state = min(entries, key=_hull)

    result = {
        "source": f"materialsproject:{ground_state.get('material_id')}",
        "formula": ground_state.get("formula_pretty"),
    }
    for p in props:
        value = ground_state.get(p)
        if value is None:
            raise RuntimeError(
                f"Materials Project's entry {ground_state.get('material_id')} for "
                f"{formula!r} carries no value for property {p!r}. "
                "No number was returned — nothing was fabricated."
            )
        if not isinstance(value, (int, float, str, bool)):
            raise RuntimeError(
                f"Property {p!r} on {ground_state.get('material_id')} is not a scalar "
                f"(got {type(value).__name__}) — this wrapper returns scalar summaries only."
            )
        result[p] = value
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: materials_lookup.py <formula> [property ...]")
        sys.exit(1)
    print(json.dumps(lookup_material(sys.argv[1], sys.argv[2:] or None), indent=2))
