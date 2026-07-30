"""Offline contract tests for discovery-only query-plan execution."""

from __future__ import annotations

import json
import sys
import urllib.error
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import search_executor  # noqa: E402


class _Response:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None, status: int = 200):
        self.body = body
        self.headers = headers or {}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size: int) -> bytes:
        return self.body


class SearchExecutorTests(unittest.TestCase):
    def test_plan_runs_safe_adapters_including_anysearch(self):
        arxiv_result = {
            "total_results": 1,
            "candidates": [{"id": "2401.00001v1", "url": "https://arxiv.org/abs/2401.00001v1"}],
        }
        github_result = {
            "total_results": 1,
            "incomplete_results": False,
            "candidates": [{"full_name": "org/repo", "url": "https://github.com/org/repo"}],
        }
        openalex_result = {"total_results": 1, "candidates": [{"id": "W1", "url": "https://openalex.org/W1"}]}
        crossref_result = {"total_results": 1, "candidates": [{"id": "10.1/example", "url": "https://doi.org/10.1/example"}]}
        anysearch_result = {"total_results": 1, "candidates": [{"id": "a1", "url": "https://example.com"}]}
        with mock.patch("search_executor._search_arxiv", return_value=arxiv_result), mock.patch(
            "search_executor._search_github", return_value=github_result
        ), mock.patch("search_executor._search_openalex", return_value=openalex_result), mock.patch(
            "search_executor._search_crossref", return_value=crossref_result
        ), mock.patch("search_executor._search_anysearch", return_value=anysearch_result):
            result = search_executor.run_plan(
                [{"query": "agent reliability", "max_results": 2}],
                {"selected": [{"provider": "arxiv"}, {"provider": "github"}, {"provider": "openalex"},
                              {"provider": "crossref"}, {"provider": "anysearch"}]},
            )
        self.assertEqual([record["status"] for record in result["records"]], ["ok", "ok", "ok", "ok", "ok"])
        self.assertEqual(result["records"][4]["candidates"], anysearch_result["candidates"])
        self.assertEqual(result["summary"]["success_count"], 5)

    def test_anysearch_markdown_is_normalized_to_bounded_discovery_leads(self):
        rendered = """## Search Results (3 results, 5ms)

### 1. Reliable evidence source
- **URL**: https://example.com/evidence
- A short source description.

### 2. Invalid destination
- **URL**: http://127.0.0.1/private
- Must not become a lead.

### 3. Duplicate URL
- **URL**: https://example.com/evidence
- Must not become a second lead.
"""
        raw_response = '{"jsonrpc":"2.0","id":1,"result":{"content":[]}}'
        with mock.patch("search_executor.anysearch_client.search_with_raw", return_value=(rendered, raw_response)) as search:
            result = search_executor._search_anysearch("agent evidence", 3)
        search.assert_called_once_with("agent evidence", 3)
        self.assertEqual(result["total_results"], 3)
        self.assertEqual(result["candidates"], [{
            "id": search_executor.hashlib.sha256(b"https://example.com/evidence").hexdigest()[:32],
            "url": "https://example.com/evidence",
            "title": "Reliable evidence source",
            "summary": "A short source description.",
        }])
        self.assertEqual(result["_raw_response"], {
            "content_type": "application/json",
            "text": raw_response,
        })

    def test_anysearch_failure_becomes_a_recorded_provider_failure(self):
        error = search_executor.anysearch_client.AnySearchRequestError("network_error")
        with mock.patch("search_executor.anysearch_client.search_with_raw", side_effect=error):
            record = search_executor._execute("anysearch", "agent evidence", 0, 2)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["reason"], "network_error")

    def test_arxiv_calls_internal_adapter_and_restores_its_fetcher(self):
        original_get = search_executor.arxiv._get
        payload = {
            "total_results": 1,
            "candidates": [{
                "arxiv_id": "2401.00001v1", "title": "A Paper", "authors": ["Ada"],
                "summary": "Summary", "published_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z", "withdrawn": False,
            }],
        }
        with mock.patch("search_executor.arxiv.search", return_value=payload) as search:
            result = search_executor._search_arxiv("safe query", 3)
        search.assert_called_once_with(query="safe query", maximum=3, sort="relevance")
        self.assertIs(search_executor.arxiv._get, original_get)
        self.assertEqual(result["candidates"][0]["url"], "https://arxiv.org/abs/2401.00001v1")
        self.assertEqual(result["candidates"][0]["native_metadata"], {
            "provider": "arxiv",
            "url": "https://arxiv.org/abs/2401.00001v1",
            "title": "A Paper",
            "content_kind": "summary",
            "text": "Summary",
            "possibly_truncated": False,
            "source_metadata": {
                "published_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            },
        })

    def test_github_query_is_percent_encoded_and_output_is_normalized(self):
        payload = {
            "total_count": 1,
            "incomplete_results": False,
            "items": [{
                "id": 7, "full_name": "org/repo", "description": "A repo",
                "stargazers_count": 5, "updated_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-01-02T00:00:00Z", "archived": False, "fork": False,
                "html_url": "https://untrusted.invalid/ignored",
            }],
        }
        with mock.patch("search_executor._fetch_json_with_raw", return_value=(payload, json.dumps(payload))) as fetch:
            result = search_executor._search_github("agents & science", 3)
        url = fetch.call_args.args[0]
        self.assertTrue(url.startswith(search_executor.GITHUB_REPOSITORIES_ENDPOINT + "?"))
        self.assertIn("q=agents%20%26%20science", url)
        self.assertEqual(result["candidates"][0]["url"], "https://github.com/org/repo")

    def test_openalex_query_is_fixed_host_and_normalized(self):
        payload = {"meta": {"count": 2}, "results": [{
            "id": "https://openalex.org/W42", "title": "A Work", "publication_date": "2025-01-02",
            "updated_date": "2026-01-01T00:00:00", "cited_by_count": 4,
            "open_access": {"is_oa": True}, "type": "article",
            "primary_location": {"landing_page_url": "https://publisher.example/work"},
            "authorships": [{"author": {"display_name": "Ada"}}],
            "abstract_inverted_index": {
                "A": [0], "reconstructed": [1], "OpenAlex": [2], "abstract": [3],
            },
        }]}
        with mock.patch("search_executor._fetch_json_with_raw", return_value=(payload, json.dumps(payload))) as fetch:
            result = search_executor._search_openalex("agents & science", 3)
        url = fetch.call_args.args[0]
        self.assertTrue(url.startswith(search_executor.OPENALEX_WORKS_ENDPOINT + "?"))
        self.assertIn("search=agents%20%26%20science", url)
        self.assertEqual(result["total_results"], 2)
        self.assertEqual(result["candidates"][0]["id"], "W42")
        self.assertEqual(result["candidates"][0]["landing_page_url"], "https://publisher.example/work")
        self.assertEqual(result["candidates"][0]["native_metadata"]["text"], "A reconstructed OpenAlex abstract")
        self.assertEqual(result["candidates"][0]["native_metadata"]["content_kind"], "abstract")

    def test_crossref_query_is_fixed_host_and_normalized(self):
        payload = {"message": {"total-results": 2, "items": [{
            "DOI": "10.1000/example", "title": ["A Work"],
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "published": {"date-parts": [[2025, 2, 3]]},
            "indexed": {"date-time": "2026-01-01T00:00:00Z"},
            "type": "journal-article", "container-title": ["Journal"], "publisher": "Publisher",
            "is-referenced-by-count": 5,
            "abstract": "<jats:p>A <b>Crossref</b> abstract with &amp; normalized visible text.</jats:p>",
        }]}}
        with mock.patch("search_executor._fetch_json_with_raw", return_value=(payload, json.dumps(payload))) as fetch:
            result = search_executor._search_crossref("agents & science", 3)
        url = fetch.call_args.args[0]
        self.assertTrue(url.startswith(search_executor.CROSSREF_WORKS_ENDPOINT + "?"))
        self.assertIn("query.bibliographic=agents%20%26%20science", url)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["url"], "https://doi.org/10.1000/example")
        self.assertEqual(candidate["published_at"], "2025-02-03")
        self.assertEqual(candidate["authors"], ["Ada Lovelace"])
        self.assertEqual(candidate["native_metadata"]["text"], "A Crossref abstract with & normalized visible text.")
        self.assertEqual(candidate["native_metadata"]["provider"], "crossref")

    def test_fixed_https_endpoint_and_response_limit_are_enforced(self):
        with mock.patch("search_executor.urllib.request.build_opener") as opener_factory:
            with self.assertRaisesRegex(search_executor.ProviderRequestError, "invalid_endpoint"):
                search_executor._fetch_bytes(
                    "https://example.invalid/search/repositories", {},
                    allowed_hosts={"api.github.com"}, expected_path="/search/repositories",
                )
        opener = mock.Mock()
        opener.open.return_value = _Response(b"x" * (search_executor.MAX_RESPONSE_BYTES + 1))
        with mock.patch("search_executor.urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(search_executor.ProviderRequestError, "response_too_large"):
                search_executor._fetch_bytes(
                    search_executor.GITHUB_REPOSITORIES_ENDPOINT, {},
                    allowed_hosts={"api.github.com"}, expected_path="/search/repositories",
                )

    def test_transient_network_failure_retries_once(self):
        opener = mock.Mock()
        opener.open.side_effect = [urllib.error.URLError("temporary"), _Response(b"{}")]
        with mock.patch("search_executor.urllib.request.build_opener", return_value=opener), mock.patch(
            "search_executor.time.sleep"
        ) as sleep:
            result = search_executor._fetch_bytes(
                search_executor.GITHUB_REPOSITORIES_ENDPOINT, {},
                allowed_hosts={"api.github.com"}, expected_path="/search/repositories",
            )
        self.assertEqual(result, b"{}")
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(search_executor.NETWORK_RETRY_DELAY_SECONDS)

    def test_malformed_plan_is_rejected_before_provider_execution(self):
        with mock.patch("search_executor._search_github") as search:
            with self.assertRaisesRegex(ValueError, "control characters"):
                search_executor.run_plan([{"query": "bad\nquery"}], [{"provider": "github"}])
        search.assert_not_called()

    def test_query_plan_size_is_bounded_before_provider_execution(self):
        with mock.patch("search_executor._search_github") as search:
            with self.assertRaisesRegex(ValueError, "exceeds"):
                search_executor.run_plan(
                    [{"query": "q"}] * (search_executor.MAX_QUERY_PLAN_ITEMS + 1),
                    [{"provider": "github"}],
                )
        search.assert_not_called()

    def test_failure_in_one_provider_does_not_abort_the_remaining_provider_jobs(self):
        def response(provider):
            return {
                "total_results": 1,
                "candidates": [{"id": provider, "url": f"https://example.com/{provider}"}],
                "_raw_response": {"content_type": "application/json", "text": json.dumps({"provider": provider})},
            }

        policy = {
            "policy": {"max_parallel": 3},
            "selected": [{"provider": "arxiv"}, {"provider": "github"}, {"provider": "openalex"}],
        }
        with mock.patch("search_executor._search_arxiv", side_effect=search_executor.ProviderRequestError("network_error")) as arxiv_search, \
                mock.patch("search_executor._search_github", return_value=response("github")) as github_search, \
                mock.patch("search_executor._search_openalex", return_value=response("openalex")) as openalex_search:
            result = search_executor.run_plan([{"query": "agent reliability"}], policy, include_raw=True)

        self.assertEqual([record["provider"] for record in result["records"]], ["arxiv", "github", "openalex"])
        self.assertEqual([record["status"] for record in result["records"]], ["failed", "ok", "ok"])
        self.assertEqual(result["summary"]["failure_count"], 1)
        self.assertEqual(result["summary"]["success_count"], 2)
        arxiv_search.assert_called_once()
        github_search.assert_called_once()
        openalex_search.assert_called_once()
        self.assertNotIn("_raw_response", result["records"][0])
        self.assertEqual(result["records"][1]["_raw_response"]["text"], '{"provider": "github"}')

    def test_every_selected_provider_runs_for_every_query_plan_item(self):
        response = {"total_results": 0, "candidates": []}
        policy = {"policy": {"max_parallel": 2},
                  "selected": [{"provider": "arxiv"}, {"provider": "github"}]}
        plan = [{"query": "first question", "max_results": 2}, {"query": "second question", "max_results": 2}]
        with mock.patch("search_executor._search_arxiv", return_value=response) as arxiv_search, \
                mock.patch("search_executor._search_github", return_value=response) as github_search:
            result = search_executor.run_plan(plan, policy)
        self.assertEqual(
            [(record["provider"], record["plan_index"], record["query"]) for record in result["records"]],
            [("arxiv", 0, "first question"), ("github", 0, "first question"),
             ("arxiv", 1, "second question"), ("github", 1, "second question")],
        )
        self.assertEqual(arxiv_search.call_count, 2)
        self.assertEqual(github_search.call_count, 2)
        self.assertEqual(result["summary"]["success_count"], 4)

    def test_raw_provider_response_is_opt_in_for_normalized_results(self):
        result = {"total_results": 0, "candidates": [],
                  "_raw_response": {"content_type": "application/json", "text": "{}"}}
        with mock.patch("search_executor._search_github", return_value=result):
            without_raw = search_executor.run_plan([{"query": "agent reliability"}], [{"provider": "github"}])
        with mock.patch("search_executor._search_github", return_value=result):
            with_raw = search_executor.run_plan([{"query": "agent reliability"}], [{"provider": "github"}], include_raw=True)
        self.assertNotIn("_raw_response", without_raw["records"][0])
        self.assertEqual(with_raw["records"][0]["_raw_response"]["text"], "{}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
