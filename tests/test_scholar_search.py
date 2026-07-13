"""
test_scholar_search.py — offline tests for the 18-FIX OpenAlex changes:

(a) search= sanitization: a literal "|" in the query is replaced by a single
    space (doubled spaces collapsed), because the OpenAlex server rejects a
    pipe in search= with HTTP 400 (malformed OR syntax; confirmed live
    2026-07-13 — the root cause of the two Step-18 alt-domain aborts).
    Pipe-free queries must pass through byte-identical to the pre-fix code.
(b) key redaction: the RuntimeError raised on an HTTP failure carries the
    request URL with the api_key query parameter's value redacted — the key
    itself must never appear.

Zero model calls and zero live HTTP: search_openalex is driven with
_http_get and _load_openalex_api_key patched out; the HTTPError path is
driven with urllib.request.urlopen patched to raise.

Run directly: venv/bin/python3 tests/test_scholar_search.py
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval import scholar_search
from retrieval.scholar_search import (
    OPENALEX_API_URL,
    OPENALEX_MAILTO,
    OPENALEX_SELECT,
    _http_get,
    _redact_key,
    _sanitize_openalex_search,
    search_openalex,
)

FAKE_KEY = "sk-test-not-a-real-key-12345"
EMPTY_RESULTS_BODY = json.dumps({"results": [], "meta": {"count": 0}}).encode()


def _call_openalex_capturing_url(query: str) -> str:
    """Run search_openalex offline (fake key, fake transport) and return the
    exact URL it handed to _http_get."""
    seen: dict[str, str] = {}

    def fake_http_get(url, headers, what, retries=5):
        seen["url"] = url
        return EMPTY_RESULTS_BODY

    with patch.object(scholar_search, "_load_openalex_api_key", return_value=FAKE_KEY), patch.object(
        scholar_search, "_http_get", side_effect=fake_http_get
    ):
        search_openalex(query)
    return seen["url"]


class TestPipeSanitization(unittest.TestCase):
    def test_single_pipe_becomes_space(self):
        self.assertEqual(_sanitize_openalex_search("cavity|flow"), "cavity flow")

    def test_multiple_pipes(self):
        self.assertEqual(_sanitize_openalex_search("a|b|c"), "a b c")

    def test_pipe_flanked_by_spaces_collapses(self):
        # "a | b" -> "a   b" after replacement; the doubled spaces collapse.
        self.assertEqual(_sanitize_openalex_search("cavity | flow | wake"), "cavity flow wake")

    def test_adjacent_pipes_collapse(self):
        self.assertEqual(_sanitize_openalex_search("cavity||flow"), "cavity flow")

    def test_pipe_free_query_byte_identical(self):
        # Exactly what the pre-fix code sent: query.strip(), untouched —
        # including internal doubled spaces.
        for q in ("cavity flow", "  cavity flow bifurcation ", "cavity  flow"):
            self.assertEqual(_sanitize_openalex_search(q), q.strip())

    def test_search_openalex_sends_sanitized_value(self):
        url = _call_openalex_capturing_url("cavity|flow")
        self.assertIn("search=cavity+flow", url)
        self.assertNotIn("%7C", url)
        self.assertNotIn("|", url)

    def test_search_openalex_pipe_free_url_byte_identical(self):
        # The full URL for a pipe-free query must equal the pre-fix
        # construction byte for byte.
        query = "lid-driven cavity flow bifurcation"
        expected = f"{OPENALEX_API_URL}?" + urllib.parse.urlencode(
            {
                "search": query.strip(),
                "per-page": 3,
                "select": OPENALEX_SELECT,
                "mailto": OPENALEX_MAILTO,
                "api_key": FAKE_KEY,
            }
        )
        self.assertEqual(_call_openalex_capturing_url(query), expected)


class TestKeyRedaction(unittest.TestCase):
    URL = (
        f"{OPENALEX_API_URL}?search=cavity+flow&per-page=3"
        f"&select=id%2Ctitle&mailto=x%40y.z&api_key={FAKE_KEY}"
    )

    def test_redaction_removes_key_preserves_rest(self):
        redacted = _redact_key(self.URL)
        self.assertNotIn(FAKE_KEY, redacted)
        self.assertIn("api_key=REDACTED", redacted)
        # Everything before the api_key value is preserved verbatim.
        prefix = self.URL[: self.URL.index("api_key=") + len("api_key=")]
        self.assertTrue(redacted.startswith(prefix))
        self.assertEqual(redacted, prefix + "REDACTED")

    def test_redaction_mid_url(self):
        url = "https://example.org/works?api_key=SECRET&search=cavity"
        self.assertEqual(
            _redact_key(url), "https://example.org/works?api_key=REDACTED&search=cavity"
        )

    def test_http_error_message_carries_redacted_url(self):
        err = urllib.error.HTTPError(
            self.URL, 400, "Bad Request", hdrs={}, fp=io.BytesIO(b"")
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                _http_get(self.URL, headers={}, what="OpenAlex")
        message = str(ctx.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn(_redact_key(self.URL), message)
        self.assertIn("api_key=REDACTED", message)
        self.assertNotIn(FAKE_KEY, message)


if __name__ == "__main__":
    unittest.main()
