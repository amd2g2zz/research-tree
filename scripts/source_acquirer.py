"""Persist bounded source captures without mutating the research DAG.

The normal path saves Markdown returned by the fixed AnySearch extractor.  A
provider-native metadata path can instead save an explicitly metadata-limited
record that was normalized during discovery.  Neither path takes a destination
path or writes graph state directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import anysearch_client
from research_repository import atomic_write_text, pages_dir, workspace


SCHEMA = 1
MAX_TITLE_CHARS = 1_024
MAX_DISCOVERY_PROVENANCE = 64
MAX_PROVIDER_METADATA_TEXT_CHARS = 4_000
MAX_PROVIDER_METADATA_CAPTURE_CHARS = 10_000
_PROVIDER = re.compile(r"[a-z0-9_-]{1,64}\Z")
_CONTENT_KIND = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


def acquire_anysearch(
    url: str,
    title: str | None = None,
    *,
    discovered_by: list[dict] | None = None,
    source_metadata: dict | None = None,
) -> dict:
    """Extract one public page and preserve its discovery and capture provenance.

    ``anysearch`` is the controlled page-extraction transport.  It is not
    necessarily the engine that found the lead, so the two facts are emitted
    separately instead of collapsing every materialised page to AnySearch.
    """

    normalized_url = anysearch_client.validate_extract_url(url)
    content = anysearch_client.extract(normalized_url)
    if _is_extractor_error(content):
        raise anysearch_client.AnySearchRequestError("extract_upstream_error")
    normalized_title = _title(title)
    normalized_provenance = _discovery_provenance(discovered_by)
    discovery_providers = list(dict.fromkeys(item["provider"] for item in normalized_provenance))
    normalized_metadata = _source_metadata(source_metadata)
    digest = hashlib.sha256((normalized_url + "\0" + content).encode("utf-8")).hexdigest()
    target = pages_dir() / f"anysearch-{digest}.md"
    atomic_write_text(target, content)
    captured_at = _now_iso()
    capture_status = "possibly_truncated" if len(content) >= anysearch_client.MAX_EXTRACTED_TEXT_CHARS else "complete"
    local_path = str(target.relative_to(workspace())).replace("\\", "/")
    evidence = {
        "url": normalized_url,
        "title": normalized_title,
        # ``provider`` remains the legacy primary discovery label.  The
        # complete origin set and the independent page-capture transport are
        # authoritative for new consumers.
        "provider": discovery_providers[0] if discovery_providers else "unknown",
        "discovery_providers": discovery_providers,
        "discovered_by": normalized_provenance,
        "capture_provider": "anysearch",
        "local_path": local_path,
        "retrieved_at": captured_at,
        "capture": {
            "status": capture_status,
            "method": "anysearch.extract",
            "character_count": len(content),
            "limit_chars": anysearch_client.MAX_EXTRACTED_TEXT_CHARS,
        },
    }
    evidence.update(normalized_metadata)
    return {
        "schema": SCHEMA,
        "kind": "saved_source",
        "evidence": evidence,
        "path": local_path,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def acquire_provider_metadata(
    url: str,
    title: str | None = None,
    *,
    provider: str,
    content_kind: str,
    content: str,
    possibly_truncated: bool = False,
    discovered_by: list[dict] | None = None,
    source_metadata: dict | None = None,
) -> dict:
    """Save a provider's normalized metadata record, never an inferred page.

    The caller supplies only text already normalized from the discovery
    provider's own response.  This is deliberately not represented as full
    text: the durable capture remains ``possibly_truncated`` and exposes a
    ``metadata_limited`` completeness marker for the semantic aggregator.
    """

    normalized_url = anysearch_client.validate_extract_url(url)
    normalized_provider = _provider_name(provider)
    normalized_kind = _content_kind(content_kind)
    normalized_content = _metadata_content(content)
    if not isinstance(possibly_truncated, bool):
        raise ValueError("possibly_truncated must be a boolean")
    normalized_title = _title(title)
    normalized_provenance = _discovery_provenance(discovered_by)
    discovery_providers = list(dict.fromkeys(item["provider"] for item in normalized_provenance))
    if normalized_provider not in discovery_providers:
        raise ValueError("provider metadata capture requires matching discovery provenance")
    normalized_metadata = _source_metadata(source_metadata)
    rendered = _render_provider_metadata(
        normalized_provider,
        normalized_url,
        normalized_title,
        normalized_kind,
        normalized_content,
        normalized_metadata,
    )
    if len(rendered) > MAX_PROVIDER_METADATA_CAPTURE_CHARS:
        raise ValueError("provider metadata capture exceeds its bounded limit")
    digest = hashlib.sha256(
        (normalized_provider + "\0" + normalized_url + "\0" + rendered).encode("utf-8")
    ).hexdigest()
    target = pages_dir() / f"provider-metadata-{normalized_provider}-{digest}.md"
    atomic_write_text(target, rendered)
    local_path = str(target.relative_to(workspace())).replace("\\", "/")
    evidence = {
        "url": normalized_url,
        "title": normalized_title,
        # This capture is directly produced from this provider's normalized
        # response, unlike AnySearch's independent page-extraction transport.
        "provider": normalized_provider,
        "discovery_providers": discovery_providers,
        "discovered_by": normalized_provenance,
        "capture_provider": normalized_provider,
        "local_path": local_path,
        "retrieved_at": _now_iso(),
        "capture": {
            # The current graph invariant accepts complete or possibly
            # truncated. Metadata-only records are inherently incomplete, so
            # they use the conservative accepted state and an explicit scope.
            "status": "possibly_truncated",
            "method": f"provider_metadata.{normalized_provider}",
            "character_count": len(rendered),
            "limit_chars": MAX_PROVIDER_METADATA_CAPTURE_CHARS,
            "completeness": "metadata_limited",
            "full_text": False,
            "content_kind": normalized_kind,
            "metadata_character_count": len(normalized_content),
            "metadata_limit_chars": MAX_PROVIDER_METADATA_TEXT_CHARS,
            "text_possibly_truncated": possibly_truncated,
        },
    }
    evidence.update(normalized_metadata)
    return {
        "schema": SCHEMA,
        "kind": "saved_source",
        "evidence": evidence,
        "path": local_path,
        "content_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


def _is_extractor_error(content: str) -> bool:
    """Do not materialise a known extractor error page as source evidence."""

    normalized = content.strip().lower()
    return normalized.startswith("extract_upstream_error") or normalized.startswith("upstream returned error:")


def _discovery_provenance(value: list[dict] | None) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_DISCOVERY_PROVENANCE:
        raise ValueError("discovered_by must be a bounded list")
    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("discovered_by entries must be objects")
        provider = item.get("provider")
        plan_index = item.get("plan_index")
        candidate_id = item.get("candidate_id")
        candidate_url = item.get("candidate_url")
        if not isinstance(provider, str) or not _PROVIDER.fullmatch(provider):
            raise ValueError("discovered_by provider is invalid")
        if isinstance(plan_index, bool) or not isinstance(plan_index, int) or plan_index < 0:
            raise ValueError("discovered_by plan_index is invalid")
        if candidate_id is not None and (not isinstance(candidate_id, (str, int)) or len(str(candidate_id)) > 1024):
            raise ValueError("discovered_by candidate_id is invalid")
        if not isinstance(candidate_url, str) or len(candidate_url) > 4096:
            raise ValueError("discovered_by candidate_url is invalid")
        try:
            candidate_url = anysearch_client.validate_extract_url(candidate_url)
        except anysearch_client.AnySearchRequestError as exc:
            raise ValueError("discovered_by candidate_url is invalid") from exc
        normalized_item = {
            "provider": provider,
            "plan_index": plan_index,
            "candidate_id": str(candidate_id) if candidate_id is not None else None,
            "candidate_url": candidate_url,
        }
        key = tuple(normalized_item.items())
        if key not in seen:
            normalized.append(normalized_item)
            seen.add(key)
    return normalized


def _source_metadata(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("source_metadata must be an object")
    normalized = {}
    for key in ("published_at", "updated_at", "event_at"):
        item = value.get(key)
        if item is None:
            continue
        if not isinstance(item, str) or not item.strip() or len(item) > 128 or any(ord(character) < 32 for character in item):
            raise ValueError(f"source_metadata {key} is invalid")
        normalized[key] = item.strip()
    return normalized


def _provider_name(value: str) -> str:
    if not isinstance(value, str) or not _PROVIDER.fullmatch(value):
        raise ValueError("provider is invalid")
    return value


def _content_kind(value: str) -> str:
    if not isinstance(value, str) or not _CONTENT_KIND.fullmatch(value):
        raise ValueError("content_kind is invalid")
    return value


def _metadata_content(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("provider metadata content must be a string")
    normalized = " ".join(value.split())
    if (
        not normalized
        or len(normalized) > MAX_PROVIDER_METADATA_TEXT_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise ValueError("provider metadata content is invalid")
    return normalized


def _render_provider_metadata(
    provider: str,
    url: str,
    title: str,
    content_kind: str,
    content: str,
    source_metadata: dict,
) -> str:
    """Render a stable, auditable wrapper around normalized provider metadata."""

    lines = [
        "# Provider Metadata Capture",
        "",
        "This record contains normalized provider metadata only, not full text.",
        "",
        f"Provider: {provider}",
        f"Record URL: {url}",
        f"Content kind: {content_kind}",
    ]
    if title:
        lines.extend(["", "## Title", "", title])
    if source_metadata:
        lines.extend(["", "## Provider Dates", ""])
        lines.extend(f"{key}: {source_metadata[key]}" for key in ("published_at", "updated_at", "event_at") if key in source_metadata)
    lines.extend(["", f"## Normalized Provider {content_kind.title()}", "", content, ""])
    return "\n".join(lines)


def _title(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("title must be a string")
    value = " ".join(value.split())
    if len(value) > MAX_TITLE_CHARS or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("invalid title")
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="source-acquirer", description="save an AnySearch-extracted source page safely")
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract", help="extract one public HTTPS page through AnySearch")
    extract.add_argument("--url", required=True)
    extract.add_argument("--title")
    args = parser.parse_args(argv)
    if args.command != "extract":
        raise AssertionError(f"unhandled command: {args.command}")
    print(json.dumps(acquire_anysearch(args.url, args.title), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
