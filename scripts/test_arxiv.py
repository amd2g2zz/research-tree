"""Offline contract tests for the ArXiv research adapter."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import arxiv  # noqa: E402


ATOM_FEED = b'''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>https://arxiv.org/abs/2402.03300v7</id>
    <published>2024-02-05T12:00:00Z</published><updated>2024-03-01T12:00:00Z</updated>
    <title> Versioned Paper </title><summary> A paper summary. </summary>
    <author><name>Ada Lovelace</name></author><category term="cs.AI" />
    <arxiv:primary_category term="cs.AI" />
    <link title="pdf" href="https://arxiv.org/pdf/2402.03300v7" />
  </entry>
</feed>'''


class _Response:
    def __init__(self, payload: bytes): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


class ArxivTests(unittest.TestCase):
    def test_search_parses_versioned_candidate_and_encodes_query(self):
        with mock.patch("arxiv.urllib.request.urlopen", return_value=_Response(ATOM_FEED)) as opened:
            result = arxiv.search(query="agent writing", maximum=1, sort="submitted")
        request = opened.call_args.args[0]
        params = dict(item.split("=", 1) for item in request.full_url.split("?", 1)[1].split("&"))
        self.assertIn("search_query", params)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["arxiv_id"], "2402.03300v7")
        self.assertEqual(candidate["url"], "https://arxiv.org/abs/2402.03300v7")
        self.assertEqual(candidate["pdf_url"], "https://arxiv.org/pdf/2402.03300v7")
        self.assertEqual(candidate["primary_category"], "cs.AI")

    def test_ids_are_validated_before_network_access(self):
        with self.assertRaisesRegex(ValueError, "invalid arXiv id"):
            arxiv.search(ids="https://internal.example/metadata")

    def test_semantic_enrichment_uses_fixed_endpoint_and_optional_key(self):
        with mock.patch("arxiv.urllib.request.urlopen", return_value=_Response(json.dumps({"paperId": "x"}).encode())) as opened:
            result = arxiv.semantic("2402.03300v7", "citations", limit=3)
        request = opened.call_args.args[0]
        self.assertTrue(request.full_url.startswith(arxiv.SEMANTIC_SCHOLAR_API + "/ARXIV:2402.03300v7/citations?"))
        self.assertEqual(result["relation"], "citations")
