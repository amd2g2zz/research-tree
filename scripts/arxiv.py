"""Version-aware arXiv discovery and citation enrichment for research Frames.

This adapter only returns discovery metadata. A Gatherer must still save the
versioned paper's full content and submit it through ``engine evidence`` before
it can support a Cognition.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ARXIV_API = "https://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
_NEW_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?$")
_OLD_ID = re.compile(r"[A-Za-z-]+(?:\.[A-Za-z-]+)?/\d{7}(?:v\d+)?$")
_CATEGORY = re.compile(r"[A-Za-z-]+\.[A-Za-z-]+$")
_SORT = {"relevance": "relevance", "submitted": "submittedDate", "updated": "lastUpdatedDate"}


def _text(element: ET.Element, name: str) -> str:
    return " ".join((element.findtext(ATOM + name) or "").split())


def versioned_id(value: str) -> str:
    candidate = (value or "").strip()
    if not (_NEW_ID.fullmatch(candidate) or _OLD_ID.fullmatch(candidate)):
        raise ValueError("invalid arXiv id")
    return candidate


def build_query(query: str | None, author: str | None, category: str | None) -> str:
    clauses = []
    if query and query.strip():
        clauses.append(f'all:"{query.strip()}"')
    if author and author.strip():
        clauses.append(f'au:"{author.strip()}"')
    if category:
        if not _CATEGORY.fullmatch(category):
            raise ValueError("invalid arXiv category")
        clauses.append(f"cat:{category}")
    if not clauses:
        raise ValueError("provide --query, --author, --category, or --id")
    return " AND ".join(clauses)


def _get(url: str, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "research-tree/arxiv-adapter/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"remote API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"remote API unavailable: {exc.reason}") from exc


def _entry(entry: ET.Element) -> dict:
    raw_id = _text(entry, "id")
    paper_id = versioned_id(raw_id.rsplit("/abs/", 1)[-1])
    links = entry.findall(ATOM + "link")
    pdf_url = next((link.get("href") for link in links if link.get("title") == "pdf"),
                   f"https://arxiv.org/pdf/{paper_id}")
    summary = _text(entry, "summary")
    primary = entry.find(ARXIV + "primary_category")
    return {
        "provider": "arxiv",
        "arxiv_id": paper_id,
        "url": f"https://arxiv.org/abs/{paper_id}",
        "pdf_url": pdf_url,
        "html_url": f"https://arxiv.org/html/{paper_id}",
        "title": _text(entry, "title"),
        "authors": [_text(author, "name") for author in entry.findall(ATOM + "author")],
        "summary": summary,
        "categories": [item.get("term") for item in entry.findall(ATOM + "category") if item.get("term")],
        "primary_category": primary.get("term") if primary is not None else None,
        "published_at": _text(entry, "published"),
        "updated_at": _text(entry, "updated"),
        "withdrawn": "withdrawn" in summary.lower() or "retracted" in summary.lower(),
    }


def search(query: str | None = None, author: str | None = None, category: str | None = None,
           ids: str | None = None, maximum: int = 10, sort: str = "relevance", start: int = 0) -> dict:
    if not 1 <= maximum <= 100:
        raise ValueError("--max must be between 1 and 100")
    if start < 0:
        raise ValueError("--start must not be negative")
    if sort not in _SORT:
        raise ValueError("--sort must be relevance, submitted, or updated")
    params = {"start": start, "max_results": maximum, "sortBy": _SORT[sort], "sortOrder": "descending"}
    if ids:
        versioned = [versioned_id(item) for item in ids.split(",") if item.strip()]
        if not versioned:
            raise ValueError("--id requires at least one arXiv id")
        params["id_list"] = ",".join(versioned)
    else:
        params["search_query"] = build_query(query, author, category)
    root = ET.fromstring(_get(ARXIV_API + "?" + urllib.parse.urlencode(params)))
    total = root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
    candidates = [_entry(entry) for entry in root.findall(ATOM + "entry")]
    return {"provider": "arxiv", "total_results": int(total) if total and total.isdigit() else None,
            "start": start, "candidates": candidates}


def semantic(arxiv_id: str, relation: str, limit: int = 20) -> dict:
    paper_id = versioned_id(arxiv_id)
    if not 1 <= limit <= 100:
        raise ValueError("--limit must be between 1 and 100")
    if relation not in {"details", "citations", "references"}:
        raise ValueError("--relation must be details, citations, or references")
    encoded_id = urllib.parse.quote(f"ARXIV:{paper_id}", safe=":")
    fields = "title,authors,year,citationCount,referenceCount,influentialCitationCount,abstract,externalIds"
    suffix = "" if relation == "details" else f"/{relation}"
    params = {"fields": fields}
    if relation != "details":
        params["limit"] = limit
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"x-api-key": api_key} if api_key else None
    payload = json.loads(_get(f"{SEMANTIC_SCHOLAR_API}/{encoded_id}{suffix}?" + urllib.parse.urlencode(params), headers))
    return {"provider": "semantic_scholar", "arxiv_id": paper_id, "relation": relation, "result": payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arxiv", description="search versioned arXiv metadata and optional citation graph")
    sub = parser.add_subparsers(dest="command", required=True)
    search_cmd = sub.add_parser("search", help="search arXiv metadata")
    search_cmd.add_argument("--query"); search_cmd.add_argument("--author"); search_cmd.add_argument("--category")
    search_cmd.add_argument("--id"); search_cmd.add_argument("--max", type=int, default=10)
    search_cmd.add_argument("--sort", choices=sorted(_SORT), default="relevance"); search_cmd.add_argument("--start", type=int, default=0)
    semantic_cmd = sub.add_parser("semantic", help="get optional Semantic Scholar paper graph metadata")
    semantic_cmd.add_argument("--id", required=True); semantic_cmd.add_argument("--relation", choices=["details", "citations", "references"], default="details")
    semantic_cmd.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    result = search(args.query, args.author, args.category, args.id, args.max, args.sort, args.start) if args.command == "search" else semantic(args.id, args.relation, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
