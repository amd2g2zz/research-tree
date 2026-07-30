"""Small fixed-endpoint client for AnySearch's JSON-RPC tools.

The client deliberately exposes only the operations that research-tree uses.
It never follows redirects, never accepts a caller-controlled API host, and
does not persist API keys returned by a provider.  ``ANYSEARCH_API_KEY`` is
optional; absent it, the documented anonymous service tier is used.
"""

from __future__ import annotations

import ipaddress
import json
import os
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests


ENDPOINT = "https://api.anysearch.com/mcp"
REQUEST_TIMEOUT_SECONDS = 15
MAX_NETWORK_ATTEMPTS = 2
NETWORK_RETRY_DELAY_SECONDS = 0.25
MAX_RESPONSE_BYTES = 1_000_000
MAX_REQUEST_BYTES = 16_384
MAX_QUERY_BYTES = 1_024
MAX_RESULTS = 10
MAX_EXTRACT_URL_BYTES = 2_048
MAX_EXTRACTED_TEXT_CHARS = 50_000
USER_AGENT = "research-tree/0.1 anysearch-client"
_ALLOWED_TOOLS = frozenset({"search", "extract", "get_sub_domains", "batch_search"})
_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid")


class AnySearchRequestError(RuntimeError):
    """A stable failure reason that is safe to place in a discovery record."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def search(query: str, maximum: int) -> str:
    """Run one general AnySearch query and return its Markdown result packet."""

    return search_with_raw(query, maximum)[0]


def search_with_raw(query: str, maximum: int) -> tuple[str, str]:
    """Return normalized search text together with the exact JSON-RPC body.

    The normalized text is used only to derive bounded leads. The second value
    exists so the discovery coordinator can archive the provider's original
    successful response rather than mistaking rendered text for a raw response.
    """

    if not isinstance(query, str) or not query.strip():
        raise AnySearchRequestError("invalid_query")
    query = query.strip()
    if len(query.encode("utf-8")) > MAX_QUERY_BYTES or _has_control_characters(query):
        raise AnySearchRequestError("invalid_query")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_RESULTS:
        raise AnySearchRequestError("invalid_max_results")
    return call_tool_with_raw("search", {"query": query, "max_results": maximum})


def extract(url: str) -> str:
    """Extract a public HTTPS page through AnySearch and return Markdown only."""

    normalized = validate_extract_url(url)
    content = call_tool("extract", {"url": normalized})
    if len(content) > MAX_EXTRACTED_TEXT_CHARS:
        raise AnySearchRequestError("extracted_content_too_large")
    return content


def validate_extract_url(value: str) -> str:
    """Reject URLs that should never be sent to a third-party extractor.

    The only local network request made by this module is to the fixed
    AnySearch API.  This validation also avoids asking that remote service to
    probe obvious local or private endpoints on a caller's behalf.
    """

    if not isinstance(value, str):
        raise AnySearchRequestError("invalid_extract_url")
    value = value.strip()
    if not value or len(value.encode("utf-8")) > MAX_EXTRACT_URL_BYTES or _has_control_characters(value):
        raise AnySearchRequestError("invalid_extract_url")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise AnySearchRequestError("invalid_extract_url") from exc
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or hostname in {"localhost", "localhost."}
        or hostname.endswith(_LOCAL_HOST_SUFFIXES)
    ):
        raise AnySearchRequestError("invalid_extract_url")
    try:
        ipaddress.ip_address(hostname.rstrip("."))
    except ValueError:
        pass
    else:
        raise AnySearchRequestError("invalid_extract_url")
    return value


def call_tool(name: str, arguments: Mapping[str, Any]) -> str:
    """Call one allowlisted JSON-RPC tool at the fixed HTTPS endpoint."""

    return call_tool_with_raw(name, arguments)[0]


def call_tool_with_raw(name: str, arguments: Mapping[str, Any]) -> tuple[str, str]:
    """Call a fixed tool and retain the bounded successful wire body."""

    if name not in _ALLOWED_TOOLS or not isinstance(arguments, Mapping):
        raise AnySearchRequestError("invalid_tool_request")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": dict(arguments)},
    }
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AnySearchRequestError("invalid_tool_request") from exc
    if len(encoded) > MAX_REQUEST_BYTES:
        raise AnySearchRequestError("request_too_large")
    response, raw_response = _post_json_with_raw(encoded)
    if not isinstance(response, Mapping):
        raise AnySearchRequestError("invalid_provider_response")
    if response.get("error") is not None:
        # Do not return provider text: it may contain credentials or request
        # diagnostics that do not belong in an auditable research log.
        raise AnySearchRequestError("provider_api_error")
    result = response.get("result")
    content = result.get("content") if isinstance(result, Mapping) else None
    if not isinstance(content, list):
        raise AnySearchRequestError("invalid_provider_response")
    texts = [
        item["text"].strip()
        for item in content
        if isinstance(item, Mapping) and item.get("type") == "text" and isinstance(item.get("text"), str)
        and item["text"].strip()
    ]
    if not texts:
        raise AnySearchRequestError("empty_provider_response")
    return "\n\n".join(texts), raw_response


def _post_json(payload: bytes) -> Any:
    return _post_json_with_raw(payload)[0]


def _post_json_with_raw(payload: bytes) -> tuple[Any, str]:
    _assert_fixed_endpoint()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    api_key = _api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    for attempt in range(MAX_NETWORK_ATTEMPTS):
        try:
            with requests.post(
                ENDPOINT,
                data=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
                verify=True,
                stream=True,
            ) as response:
                status = response.status_code
                try:
                    if not 200 <= int(status) < 300:
                        raise AnySearchRequestError(f"http_{status}")
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                        raise AnySearchRequestError("response_too_large")
                except (TypeError, ValueError) as exc:
                    raise AnySearchRequestError("invalid_provider_response") from exc
                body = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not isinstance(chunk, bytes):
                        raise AnySearchRequestError("invalid_provider_response")
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise AnySearchRequestError("response_too_large")
        except AnySearchRequestError:
            raise
        except requests.RequestException as exc:
            if attempt + 1 == MAX_NETWORK_ATTEMPTS:
                raise AnySearchRequestError("network_error") from exc
            time.sleep(NETWORK_RETRY_DELAY_SECONDS * (attempt + 1))
            continue
        body = bytes(body)
        try:
            raw_response = body.decode("utf-8")
            return json.loads(raw_response), raw_response
        except UnicodeDecodeError as exc:
            raise AnySearchRequestError("invalid_encoding") from exc
        except json.JSONDecodeError as exc:
            raise AnySearchRequestError("invalid_json") from exc
    raise AssertionError("network retry loop did not return or raise")


def _assert_fixed_endpoint() -> None:
    try:
        parsed = urllib.parse.urlsplit(ENDPOINT)
        port = parsed.port
    except ValueError as exc:
        raise AnySearchRequestError("invalid_endpoint") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != "api.anysearch.com"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/mcp"
        or parsed.query
        or parsed.fragment
    ):
        raise AnySearchRequestError("invalid_endpoint")


def _api_key() -> str:
    value = os.environ.get("ANYSEARCH_API_KEY", "").strip()
    if len(value) > 512 or _has_control_characters(value):
        raise AnySearchRequestError("invalid_api_key")
    return value


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
