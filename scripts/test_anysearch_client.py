"""Offline contract tests for the fixed-host AnySearch JSON-RPC client."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import anysearch_client  # noqa: E402


class _Response:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None, status: int = 200):
        self.body = body
        self.headers = headers or {}
        self.status = status
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size: int) -> bytes:
        return self.body

    def iter_content(self, chunk_size: int):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index:index + chunk_size]


class AnySearchClientTests(unittest.TestCase):
    def _rpc_response(self, text: str) -> _Response:
        return _Response(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "image", "data": "ignored"}, {"type": "text", "text": text}],
        }}).encode("utf-8"))

    def test_search_posts_to_fixed_endpoint_without_implicit_credentials(self):
        opener = mock.Mock()
        opener.return_value = self._rpc_response("## Search Results (0 results, 1ms)")
        with mock.patch.dict(os.environ, {"ANYSEARCH_API_KEY": ""}, clear=False), mock.patch(
            "anysearch_client.requests.post", opener
        ):
            text = anysearch_client.search("agent evidence", 2)
        self.assertEqual(opener.call_args.args[0], anysearch_client.ENDPOINT)
        self.assertIsNone(opener.call_args.kwargs["headers"].get("Authorization"))
        self.assertFalse(opener.call_args.kwargs["allow_redirects"])
        self.assertTrue(opener.call_args.kwargs["verify"])
        self.assertTrue(opener.call_args.kwargs["stream"])
        payload = json.loads(opener.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(payload["method"], "tools/call")
        self.assertEqual(payload["params"], {"name": "search", "arguments": {"query": "agent evidence", "max_results": 2}})
        self.assertEqual(text, "## Search Results (0 results, 1ms)")

    def test_search_with_raw_preserves_the_successful_json_rpc_envelope(self):
        raw_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "result"}],
        }}, separators=(",", ":"))
        opener = mock.Mock()
        opener.return_value = _Response(raw_response.encode("utf-8"))
        with mock.patch("anysearch_client.requests.post", opener):
            text, raw = anysearch_client.search_with_raw("agent evidence", 1)
        self.assertEqual(text, "result")
        self.assertEqual(raw, raw_response)
        self.assertEqual(json.loads(raw)["jsonrpc"], "2.0")

    def test_explicit_environment_key_is_sent_but_never_part_of_returned_text(self):
        opener = mock.Mock()
        opener.return_value = self._rpc_response("result")
        with mock.patch.dict(os.environ, {"ANYSEARCH_API_KEY": "configured-key"}, clear=False), mock.patch(
            "anysearch_client.requests.post", opener
        ):
            self.assertEqual(anysearch_client.search("agent evidence", 1), "result")
        self.assertEqual(opener.call_args.kwargs["headers"]["Authorization"], "Bearer configured-key")

    def test_provider_error_and_missing_text_are_sanitized(self):
        provider_error = _Response(json.dumps({"error": {"message": "secret diagnostic"}}).encode("utf-8"))
        opener = mock.Mock(); opener.return_value = provider_error
        with mock.patch("anysearch_client.requests.post", opener):
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "provider_api_error"):
                anysearch_client.search("agent evidence", 1)
        no_text = _Response(json.dumps({"result": {"content": [{"type": "image"}]}}).encode("utf-8"))
        opener.return_value = no_text
        with mock.patch("anysearch_client.requests.post", opener):
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "empty_provider_response"):
                anysearch_client.search("agent evidence", 1)

    def test_all_text_content_items_are_retained_in_order(self):
        response = _Response(json.dumps({"result": {"content": [
            {"type": "text", "text": "first section"},
            {"type": "image", "data": "ignored"},
            {"type": "text", "text": "second section"},
        ]}}).encode("utf-8"))
        post = mock.Mock(); post.return_value = response
        with mock.patch("anysearch_client.requests.post", post):
            self.assertEqual(anysearch_client.search("agent evidence", 1), "first section\n\nsecond section")

    def test_fixed_endpoint_and_public_extract_url_are_enforced(self):
        with mock.patch("anysearch_client.ENDPOINT", "https://other.example/mcp"):
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "invalid_endpoint"):
                anysearch_client.call_tool("search", {"query": "safe"})
        self.assertEqual(anysearch_client.validate_extract_url("https://example.com/a?q=1"), "https://example.com/a?q=1")
        for value in ("http://example.com", "https://localhost/a", "https://127.0.0.1/a", "https://user:pass@example.com", "https://example.com:444/a"):
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "invalid_extract_url"):
                anysearch_client.validate_extract_url(value)

    def test_extractor_never_silently_truncates_provider_content(self):
        opener = mock.Mock()
        opener.return_value = self._rpc_response("x" * (anysearch_client.MAX_EXTRACTED_TEXT_CHARS + 1))
        with mock.patch("anysearch_client.requests.post", opener):
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "extracted_content_too_large"):
                anysearch_client.extract("https://example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
