"""Safe, discovery-only execution for stored research query plans.

This module deliberately returns leads instead of evidence.  A Gatherer must
still retrieve and persist accepted source content before the research domain
can accept evidence.  Network destinations are fixed per provider so a stored
query plan can never turn this executor into a general-purpose URL fetcher.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from typing import Any

import arxiv
import anysearch_client


SCHEMA = 2
REQUEST_TIMEOUT_SECONDS = 10
MAX_NETWORK_ATTEMPTS = 2
NETWORK_RETRY_DELAY_SECONDS = 0.25
MAX_RESPONSE_BYTES = 1_000_000
MAX_QUERY_BYTES = 1_024
MAX_QUERY_PLAN_ITEMS = 32
MAX_RESULTS_PER_PROVIDER = 10
MAX_TEXT_CHARS = 2_000
MAX_OPENALEX_ABSTRACT_POSITIONS = 2_048
MAX_CROSSREF_ABSTRACT_INPUT_CHARS = MAX_TEXT_CHARS * 8
MAX_PROVIDER_WORKERS = 16
GITHUB_REPOSITORIES_ENDPOINT = "https://api.github.com/search/repositories"
OPENALEX_WORKS_ENDPOINT = "https://api.openalex.org/works"
CROSSREF_WORKS_ENDPOINT = "https://api.crossref.org/works"
_REPOSITORY_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_ANYSEARCH_TOTAL_RESULTS = re.compile(r"(?mi)^##\s+Search Results\s*\((\d+)\s+results?")
_ANYSEARCH_ITEM = re.compile(r"(?m)^###\s+\d+\.\s*(?P<title>.+?)\s*$")
_ANYSEARCH_URL = re.compile(r"(?mi)^-\s+\*\*URL\*\*:\s*(?P<url>\S+)\s*$")
_ARXIV_API_LOCK = threading.RLock()


class ProviderRequestError(RuntimeError):
    """A safe, machine-readable failure from a provider request."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Fail closed instead of following a redirect to a different host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class _CrossrefAbstractParser(HTMLParser):
    """Extract visible text from the small HTML/JATS fragment Crossref returns."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def run_plan(plan: list[dict[str, Any]], eligible_providers: Any, *, include_raw: bool = False) -> dict[str, Any]:
    """Execute each stored query against every eligible discovery provider.

    ``eligible_providers`` accepts either ``providers.eligible()["selected"]``
    or the complete mapping returned by ``providers.eligible()``.  Unknown and
    uninstalled providers are recorded explicitly rather than silently omitted.
    Invalid plans are rejected before any network request is attempted.
    """

    queries = _validate_plan(plan)
    provider_names = _provider_names(eligible_providers)
    jobs = []
    for plan_index, item in enumerate(queries):
        query = item["query"]
        maximum = _maximum(item)
        for provider in provider_names:
            jobs.append((provider, query, plan_index, maximum))
    worker_count = _provider_parallelism(eligible_providers, len(jobs))
    if worker_count == 1:
        records = [_execute(*job) for job in jobs]
    else:
        # Every provider receives every stored query. Keep the input ordering
        # in the result so archival and later source balancing are deterministic.
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="research-provider") as executor:
            records = list(executor.map(lambda job: _execute(*job), jobs))
    if not include_raw:
        for record in records:
            record.pop("_raw_response", None)
    return {
        "schema": SCHEMA,
        "kind": "discovery_batch",
        "records": records,
        "summary": {
            "query_count": len(queries),
            "provider_count": len(provider_names),
            "success_count": sum(record["status"] == "ok" for record in records),
            "failure_count": sum(record["status"] == "failed" for record in records),
            "unavailable_count": sum(record["status"] == "unavailable" for record in records),
            "skipped_count": sum(record["status"] == "skipped" for record in records),
        },
    }


def _provider_parallelism(eligible_providers: Any, job_count: int) -> int:
    if job_count < 1:
        return 1
    maximum = 1
    if isinstance(eligible_providers, Mapping):
        maximum = eligible_providers.get("max_parallel")
        if maximum is None:
            policy = eligible_providers.get("policy")
            maximum = policy.get("max_parallel") if isinstance(policy, Mapping) else 1
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_PROVIDER_WORKERS:
        raise ValueError(f"provider max_parallel must be an integer between 1 and {MAX_PROVIDER_WORKERS}")
    return min(maximum, job_count)


def _validate_plan(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, list) or not plan:
        raise ValueError("query plan must be a non-empty list")
    if len(plan) > MAX_QUERY_PLAN_ITEMS:
        raise ValueError(f"query plan exceeds {MAX_QUERY_PLAN_ITEMS} items")
    normalized = []
    for item in plan:
        if not isinstance(item, dict):
            raise ValueError("each query plan item must be an object")
        query = item.get("query")
        if not isinstance(query, str):
            raise ValueError("each query plan item requires a string query")
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if len(query.encode("utf-8")) > MAX_QUERY_BYTES:
            raise ValueError(f"query exceeds {MAX_QUERY_BYTES} UTF-8 bytes")
        if any(ord(character) < 32 for character in query):
            raise ValueError("query must not contain control characters")
        normalized.append({**item, "query": query})
    return normalized


def _maximum(item: Mapping[str, Any]) -> int:
    value = item.get("max_results", MAX_RESULTS_PER_PROVIDER)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_results must be a positive integer")
    return min(value, MAX_RESULTS_PER_PROVIDER)


def _provider_names(eligible_providers: Any) -> list[str]:
    selected = eligible_providers.get("selected") if isinstance(eligible_providers, Mapping) else eligible_providers
    if isinstance(selected, (str, bytes)) or not isinstance(selected, Iterable):
        raise ValueError("eligible providers must be an iterable or a provider policy result")
    names = []
    for provider in selected:
        name = provider.get("provider") if isinstance(provider, Mapping) else provider
        if not isinstance(name, str) or not name:
            raise ValueError("eligible provider entries require a provider name")
        if name not in names:
            names.append(name)
    return names


def _execute(provider: str, query: str, plan_index: int, maximum: int) -> dict[str, Any]:
    base = {
        "provider": provider,
        "plan_index": plan_index,
        "query": query,
        "candidates": [],
    }
    if provider == "arxiv":
        action = _search_arxiv
    elif provider == "github":
        action = _search_github
    elif provider == "openalex":
        action = _search_openalex
    elif provider == "crossref":
        action = _search_crossref
    elif provider == "anysearch":
        action = _search_anysearch
    else:
        return {**base, "status": "skipped", "reason": "unsupported_provider"}
    try:
        result = action(query, maximum)
        if not isinstance(result, Mapping):
            raise ProviderRequestError("invalid_response")
        result = dict(result)
        raw = result.pop("_raw_response", None)
    except ProviderRequestError as exc:
        return {**base, "status": "failed", "reason": exc.code}
    except (AttributeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {**base, "status": "failed", "reason": "invalid_provider_response"}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return {**base, "status": "failed", "reason": "network_error"}
    except RuntimeError:
        return {**base, "status": "failed", "reason": "provider_error"}
    except Exception:
        # A provider implementation must not abort the rest of the declared
        # multi-engine plan. The detailed exception is intentionally not
        # persisted because it can include transport or credential data.
        return {**base, "status": "failed", "reason": "provider_error"}
    record = {**base, "status": "ok", **result}
    if raw is not None:
        record["_raw_response"] = raw
    return record


def _search_arxiv(query: str, maximum: int) -> dict[str, Any]:
    """Use the existing arXiv API while imposing this adapter's I/O limits."""

    captured: list[bytes] = []

    def capture_get(url: str, headers: dict[str, str] | None = None) -> bytes:
        response = _bounded_arxiv_get(url, headers)
        captured.append(response)
        return response

    with _ARXIV_API_LOCK:
        original_get = arxiv._get
        arxiv._get = capture_get
        try:
            payload = arxiv.search(query=query, maximum=maximum, sort="relevance")
        finally:
            arxiv._get = original_get
    if not isinstance(payload, Mapping) or not isinstance(payload.get("candidates"), list):
        raise ProviderRequestError("invalid_response")
    candidates = []
    for item in payload.get("candidates", [])[:maximum]:
        candidate = _normalize_arxiv_candidate(item)
        if candidate is not None:
            candidates.append(candidate)
    raw = _decode_raw(captured[-1], "application/atom+xml") if captured else json.dumps(payload, ensure_ascii=False)
    return {
        "total_results": _nonnegative_int(payload.get("total_results")),
        "candidates": candidates,
        "_raw_response": _raw_response(raw, "application/atom+xml"),
    }


def _bounded_arxiv_get(url: str, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": "research-tree/search-executor/1.0"}
    if headers:
        request_headers.update(headers)
    return _fetch_bytes(
        url,
        request_headers,
        allowed_hosts={"export.arxiv.org"},
        expected_path="/api/query",
    )


def _normalize_arxiv_candidate(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    raw_id = item.get("arxiv_id")
    if not isinstance(raw_id, str):
        return None
    try:
        paper_id = arxiv.versioned_id(raw_id)
    except ValueError:
        return None
    url = f"https://arxiv.org/abs/{paper_id}"
    title = _text(item.get("title"))
    summary, summary_truncated = _native_text(item.get("summary"))
    published_at = _text(item.get("published_at"), limit=128)
    updated_at = _text(item.get("updated_at"), limit=128)
    candidate = {
        "id": paper_id,
        "url": url,
        "title": title,
        "authors": _text_list(item.get("authors")),
        "summary": summary,
        "primary_category": _text(item.get("primary_category"), limit=128),
        "published_at": published_at,
        "updated_at": updated_at,
        "withdrawn": item.get("withdrawn") is True,
    }
    native_metadata = _native_metadata(
        "arxiv",
        url,
        title,
        "summary",
        summary,
        summary_truncated,
        {"published_at": published_at, "updated_at": updated_at},
    )
    if native_metadata is not None:
        candidate["native_metadata"] = native_metadata
    return candidate


def _search_github(query: str, maximum: int) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(
        {"q": query, "per_page": maximum, "page": 1},
        quote_via=urllib.parse.quote,
        safe="",
    )
    payload, raw = _fetch_json_with_raw(
        f"{GITHUB_REPOSITORIES_ENDPOINT}?{encoded}",
        {"Accept": "application/vnd.github+json", "User-Agent": "research-tree/search-executor/1.0"},
        allowed_hosts={"api.github.com"},
        expected_path="/search/repositories",
    )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
        raise ProviderRequestError("invalid_response")
    candidates = []
    for item in payload["items"][:maximum]:
        candidate = _normalize_github_candidate(item)
        if candidate is not None:
            candidates.append(candidate)
    return {
        "total_results": _nonnegative_int(payload.get("total_count")),
        "incomplete_results": payload.get("incomplete_results") is True,
        "candidates": candidates,
        "_raw_response": _raw_response(raw, "application/json"),
    }


def _normalize_github_candidate(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    full_name = item.get("full_name")
    if not isinstance(full_name, str) or not _REPOSITORY_NAME.fullmatch(full_name):
        return None
    repository_id = item.get("id")
    return {
        "id": repository_id if isinstance(repository_id, int) else None,
        "full_name": full_name,
        "url": f"https://github.com/{full_name}",
        "description": _text(item.get("description")),
        "stars": _nonnegative_int(item.get("stargazers_count")),
        "updated_at": _text(item.get("updated_at"), limit=128),
        "pushed_at": _text(item.get("pushed_at"), limit=128),
        "archived": item.get("archived") is True,
        "fork": item.get("fork") is True,
    }


def _search_openalex(query: str, maximum: int) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(
        {"search": query, "per-page": maximum, "page": 1},
        quote_via=urllib.parse.quote,
        safe="",
    )
    payload, raw = _fetch_json_with_raw(
        f"{OPENALEX_WORKS_ENDPOINT}?{encoded}",
        {"Accept": "application/json", "User-Agent": "research-tree/search-executor/1.0"},
        allowed_hosts={"api.openalex.org"},
        expected_path="/works",
    )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
        raise ProviderRequestError("invalid_response")
    meta = payload.get("meta") if isinstance(payload.get("meta"), Mapping) else {}
    candidates = []
    for item in payload["results"][:maximum]:
        candidate = _normalize_openalex_candidate(item)
        if candidate is not None:
            candidates.append(candidate)
    return {
        "total_results": _nonnegative_int(meta.get("count")),
        "candidates": candidates,
        "_raw_response": _raw_response(raw, "application/json"),
    }


def _normalize_openalex_candidate(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    openalex_id = _text(item.get("id"), limit=256)
    if not openalex_id or not openalex_id.startswith("https://openalex.org/"):
        return None
    primary_location = item.get("primary_location")
    landing_page = primary_location.get("landing_page_url") if isinstance(primary_location, Mapping) else None
    authors = []
    raw_authorships = item.get("authorships")
    for authorship in raw_authorships[:20] if isinstance(raw_authorships, list) else []:
        author = authorship.get("author") if isinstance(authorship, Mapping) else None
        name = author.get("display_name") if isinstance(author, Mapping) else None
        normalized = _text(name, limit=256)
        if normalized:
            authors.append(normalized)
    open_access = item.get("open_access") if isinstance(item.get("open_access"), Mapping) else {}
    title = _text(item.get("title") or item.get("display_name"))
    published_at = _text(item.get("publication_date"), limit=32)
    updated_at = _text(item.get("updated_date"), limit=64)
    abstract, abstract_truncated = _reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
    candidate = {
        "id": openalex_id.rsplit("/", 1)[-1],
        "url": openalex_id,
        "landing_page_url": _safe_lead_url(landing_page),
        "doi": _text(item.get("doi"), limit=512),
        "title": title,
        "authors": authors,
        "published_at": published_at,
        "updated_at": updated_at,
        "cited_by_count": _nonnegative_int(item.get("cited_by_count")),
        "is_open_access": open_access.get("is_oa") is True,
        "type": _text(item.get("type"), limit=128),
    }
    native_metadata = _native_metadata(
        "openalex",
        openalex_id,
        title,
        "abstract",
        abstract,
        abstract_truncated,
        {"published_at": published_at, "updated_at": updated_at},
    )
    if native_metadata is not None:
        candidate["native_metadata"] = native_metadata
    return candidate


def _search_crossref(query: str, maximum: int) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(
        {"query.bibliographic": query, "rows": maximum, "offset": 0},
        quote_via=urllib.parse.quote,
        safe="",
    )
    payload, raw = _fetch_json_with_raw(
        f"{CROSSREF_WORKS_ENDPOINT}?{encoded}",
        {"Accept": "application/json", "User-Agent": "research-tree/search-executor/1.0"},
        allowed_hosts={"api.crossref.org"},
        expected_path="/works",
    )
    message = payload.get("message") if isinstance(payload, Mapping) else None
    if not isinstance(message, Mapping) or not isinstance(message.get("items"), list):
        raise ProviderRequestError("invalid_response")
    candidates = []
    for item in message["items"][:maximum]:
        candidate = _normalize_crossref_candidate(item)
        if candidate is not None:
            candidates.append(candidate)
    return {
        "total_results": _nonnegative_int(message.get("total-results")),
        "candidates": candidates,
        "_raw_response": _raw_response(raw, "application/json"),
    }


def _normalize_crossref_candidate(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    doi = _text(item.get("DOI"), limit=512)
    if not doi or any(character.isspace() for character in doi):
        return None
    authors = []
    raw_authors = item.get("author")
    for author in raw_authors[:20] if isinstance(raw_authors, list) else []:
        if not isinstance(author, Mapping):
            continue
        name = " ".join(part for part in (_text(author.get("given"), limit=128), _text(author.get("family"), limit=128)) if part)
        if name:
            authors.append(name)
    indexed = item.get("indexed")
    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/")
    title = _first_text(item.get("title"))
    published_at = _crossref_date(item.get("published") or item.get("issued"))
    updated_at = _text(indexed.get("date-time"), limit=64) if isinstance(indexed, Mapping) else None
    abstract, abstract_truncated = _normalize_crossref_abstract(item.get("abstract"))
    candidate = {
        "id": doi.lower(),
        "url": url,
        "title": title,
        "authors": authors,
        "published_at": published_at,
        "updated_at": updated_at,
        "type": _text(item.get("type"), limit=128),
        "container_title": _first_text(item.get("container-title")),
        "publisher": _text(item.get("publisher"), limit=256),
        "cited_by_count": _nonnegative_int(item.get("is-referenced-by-count")),
    }
    native_metadata = _native_metadata(
        "crossref",
        url,
        title,
        "abstract",
        abstract,
        abstract_truncated,
        {"published_at": published_at, "updated_at": updated_at},
    )
    if native_metadata is not None:
        candidate["native_metadata"] = native_metadata
    return candidate


def _native_text(value: Any, *, limit: int = MAX_TEXT_CHARS) -> tuple[str | None, bool]:
    """Normalize untrusted provider text without promoting control characters."""

    if not isinstance(value, str):
        return None, False
    sanitized = "".join(" " if ord(character) < 32 or ord(character) == 127 else character for character in value)
    normalized = " ".join(sanitized.split())
    if not normalized:
        return None, False
    return normalized[:limit], len(normalized) > limit


def _native_metadata(
    provider: str,
    url: str,
    title: str | None,
    content_kind: str,
    text: str | None,
    possibly_truncated: bool,
    source_metadata: Mapping[str, str | None],
) -> dict[str, Any] | None:
    """Attach only provider-owned normalized text for optional metadata capture."""

    if not text:
        return None
    normalized_title, _ = _native_text(title, limit=1_024)
    normalized_dates = {}
    for key in ("published_at", "updated_at", "event_at"):
        value, truncated = _native_text(source_metadata.get(key), limit=128)
        if value and not truncated:
            normalized_dates[key] = value
    return {
        "provider": provider,
        "url": url,
        "title": normalized_title or "",
        "content_kind": content_kind,
        "text": text,
        "possibly_truncated": possibly_truncated,
        "source_metadata": normalized_dates,
    }


def _reconstruct_openalex_abstract(value: Any) -> tuple[str | None, bool]:
    """Rebuild OpenAlex's inverted abstract index under strict work limits."""

    if not isinstance(value, Mapping):
        return None, False
    by_position: dict[int, str] = {}
    possibly_truncated = False
    for raw_token, raw_positions in value.items():
        if not isinstance(raw_positions, list):
            continue
        token, token_truncated = _native_text(raw_token, limit=128)
        if not token:
            continue
        possibly_truncated = possibly_truncated or token_truncated
        for index, position in enumerate(raw_positions):
            if index >= MAX_OPENALEX_ABSTRACT_POSITIONS:
                possibly_truncated = True
                break
            if isinstance(position, bool) or not isinstance(position, int) or not 0 <= position < MAX_OPENALEX_ABSTRACT_POSITIONS:
                possibly_truncated = True
                continue
            if position not in by_position and len(by_position) >= MAX_OPENALEX_ABSTRACT_POSITIONS:
                possibly_truncated = True
                continue
            # Collisions are malformed provider data. Choosing lexicographically
            # keeps reconstruction stable rather than depending on JSON order.
            previous = by_position.get(position)
            if previous is None or token < previous:
                by_position[position] = token
    if not by_position:
        return None, possibly_truncated
    text, text_truncated = _native_text(" ".join(by_position[position] for position in sorted(by_position)))
    return text, possibly_truncated or text_truncated


def _normalize_crossref_abstract(value: Any) -> tuple[str | None, bool]:
    """Convert Crossref's optional HTML/JATS abstract to bounded visible text."""

    if not isinstance(value, str):
        return None, False
    possibly_truncated = len(value) > MAX_CROSSREF_ABSTRACT_INPUT_CHARS
    parser = _CrossrefAbstractParser()
    try:
        parser.feed(value[:MAX_CROSSREF_ABSTRACT_INPUT_CHARS])
        parser.close()
    except (AssertionError, ValueError):
        return None, possibly_truncated
    text, text_truncated = _native_text(" ".join(parser.parts))
    return text, possibly_truncated or text_truncated


def _search_anysearch(query: str, maximum: int) -> dict[str, Any]:
    """Use AnySearch only for discovery leads, never as direct evidence."""

    try:
        rendered, raw_response = anysearch_client.search_with_raw(query, maximum)
    except anysearch_client.AnySearchRequestError as exc:
        raise ProviderRequestError(exc.code) from exc
    result = _parse_anysearch_results(rendered, maximum)
    # The rendered Markdown is a derived tool result. Preserve the exact
    # successful JSON-RPC envelope so the coordinator can archive what the
    # provider actually returned before it normalizes any discovery leads.
    result["_raw_response"] = _raw_response(raw_response, "application/json")
    return result


def _parse_anysearch_results(rendered: Any, maximum: int) -> dict[str, Any]:
    """Normalize the provider's human-readable Markdown without trusting it.

    AnySearch deliberately returns rendered Markdown rather than a stable
    candidate JSON schema. Only bounded, public HTTPS URLs are promoted into
    normalized lead records; the enclosing JSON-RPC response is archived
    separately by the coordinator.
    """

    if not isinstance(rendered, str) or not rendered.strip():
        raise ProviderRequestError("invalid_response")
    matches = list(_ANYSEARCH_ITEM.finditer(rendered))
    candidates = []
    seen_urls = set()
    for index, match in enumerate(matches):
        if len(candidates) >= maximum:
            break
        end = matches[index + 1].start() if index + 1 < len(matches) else len(rendered)
        block = rendered[match.end():end]
        url_match = _ANYSEARCH_URL.search(block)
        if url_match is None:
            continue
        url = _safe_lead_url(url_match.group("url"))
        title = _text(match.group("title"), limit=512)
        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)
        summary = _text(re.sub(r"(?m)^-\s+", "", _ANYSEARCH_URL.sub("", block)), limit=MAX_TEXT_CHARS)
        candidates.append({
            "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:32],
            "url": url,
            "title": title,
            "summary": summary,
        })
    total_match = _ANYSEARCH_TOTAL_RESULTS.search(rendered)
    total_results = int(total_match.group(1)) if total_match else None
    return {"total_results": total_results, "candidates": candidates}


def _fetch_json(url: str, headers: Mapping[str, str], *, allowed_hosts: set[str], expected_path: str) -> Any:
    return _fetch_json_with_raw(url, headers, allowed_hosts=allowed_hosts, expected_path=expected_path)[0]


def _fetch_json_with_raw(url: str, headers: Mapping[str, str], *, allowed_hosts: set[str], expected_path: str) -> tuple[Any, str]:
    try:
        payload = _fetch_bytes(url, headers, allowed_hosts=allowed_hosts, expected_path=expected_path)
        raw = _decode_raw(payload, "application/json")
        return json.loads(raw), raw
    except UnicodeDecodeError as exc:
        raise ProviderRequestError("invalid_encoding") from exc
    except json.JSONDecodeError as exc:
        raise ProviderRequestError("invalid_json") from exc


def _decode_raw(payload: bytes, _content_type: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderRequestError("invalid_encoding") from exc


def _raw_response(value: str, content_type: str) -> dict[str, str]:
    if not isinstance(value, str) or not value:
        raise ProviderRequestError("invalid_response")
    if len(value.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ProviderRequestError("response_too_large")
    return {"content_type": content_type, "text": value}


def _fetch_bytes(url: str, headers: Mapping[str, str], *, allowed_hosts: set[str], expected_path: str) -> bytes:
    _assert_endpoint(url, allowed_hosts, expected_path)
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    opener = urllib.request.build_opener(_NoRedirect())
    for attempt in range(MAX_NETWORK_ATTEMPTS):
        try:
            with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None)
                try:
                    if status is not None and not 200 <= int(status) < 300:
                        raise ProviderRequestError(f"http_{status}")
                    content_length = getattr(response, "headers", {}).get("Content-Length")
                    if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                        raise ProviderRequestError("response_too_large")
                except (TypeError, ValueError) as exc:
                    raise ProviderRequestError("invalid_response") from exc
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except ProviderRequestError:
            raise
        except urllib.error.HTTPError as exc:
            raise ProviderRequestError(f"http_{exc.code}") from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            if attempt + 1 == MAX_NETWORK_ATTEMPTS:
                raise ProviderRequestError("network_error") from exc
            time.sleep(NETWORK_RETRY_DELAY_SECONDS * (attempt + 1))
            continue
        if not isinstance(body, bytes):
            raise ProviderRequestError("invalid_response")
        if len(body) > MAX_RESPONSE_BYTES:
            raise ProviderRequestError("response_too_large")
        return body
    raise AssertionError("network retry loop did not return or raise")


def _assert_endpoint(url: str, allowed_hosts: set[str], expected_path: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ProviderRequestError("invalid_endpoint") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() not in allowed_hosts
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
    ):
        raise ProviderRequestError("invalid_endpoint")


def _nonnegative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _text(value: Any, *, limit: int = MAX_TEXT_CHARS) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:limit]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_text(item, limit=256) for item in value[:20]) if text]


def _first_text(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        normalized = _text(item)
        if normalized:
            return normalized
    return None


def _crossref_date(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    date_parts = value.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts or not isinstance(date_parts[0], list):
        return None
    parts = date_parts[0]
    if not 1 <= len(parts) <= 3 or any(isinstance(item, bool) or not isinstance(item, int) for item in parts):
        return None
    year = parts[0]
    if not 1 <= year <= 9999:
        return None
    if len(parts) == 1:
        return f"{year:04d}"
    month = parts[1]
    if not 1 <= month <= 12:
        return None
    if len(parts) == 2:
        return f"{year:04d}-{month:02d}"
    day = parts[2]
    if not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _safe_lead_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2_048:
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None
    return value
