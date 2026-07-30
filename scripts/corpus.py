"""Local research corpus: chunking, vectorisation, inverted indexing, retrieval.

This module never fetches or calls an LLM.  It turns the pages already persisted
by the research phase into a portable corpus that chapter agents can retrieve
from.  The default vectoriser is deterministic feature hashing, so the skill has
no model/download dependency.  A production orchestrator may replace ``vector``
with provider embeddings while keeping the JSONL/index contract unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_DIMENSIONS = 256
_WORD = re.compile(r"[a-z0-9][a-z0-9_+.#/-]{1,}", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u9fff]")


def workspace() -> Path:
    return Path(os.environ.get("RESEARCH_WORKSPACE", os.getcwd()))


def corpus_dir() -> Path:
    return workspace() / "research_corpus"


def tokens(text: str) -> list[str]:
    """Tokenise Latin terms and CJK characters without a language-model dependency."""
    lowered = (text or "").lower()
    result = _WORD.findall(lowered)
    cjk = _CJK.findall(lowered)
    result.extend(cjk)
    result.extend("".join(cjk[i:i + 2]) for i in range(len(cjk) - 1))
    return result


def _vector(term_counts: Counter[str], dimensions: int) -> list[float]:
    values = [0.0] * dimensions
    for term, count in term_counts.items():
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        values[slot] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in values))
    return [round(value / norm, 8) for value in values] if norm else values


def _paragraph_chunks(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if current and len(candidate) > max_chars:
            chunks.append(current)
            tail = current[-overlap_chars:].strip() if overlap_chars else ""
            current = (tail + "\n\n" + paragraph).strip() if tail else paragraph
        else:
            current = candidate
        while len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars - overlap_chars:].strip()
    if current:
        chunks.append(current)
    return chunks


def _iter_pages(pages_dir: Path):
    if not pages_dir.exists():
        return
    for path in sorted(p for p in pages_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt", ".html"}):
        yield path


def build(pages_dir: Path, max_chars: int = 1200, overlap_chars: int = 160,
          dimensions: int = DEFAULT_DIMENSIONS, allowed_paths: set[str] | None = None) -> dict:
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("max_chars must be positive and overlap_chars must be in [0, max_chars)")
    chunks = []
    inverted: dict[str, dict[str, int]] = defaultdict(dict)
    doc_freq: Counter[str] = Counter()
    for path in _iter_pages(pages_dir) or []:
        source = str(path.relative_to(workspace())).replace("\\", "/")
        if allowed_paths is not None and source not in allowed_paths:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for ordinal, body in enumerate(_paragraph_chunks(text, max_chars, overlap_chars)):
            term_counts = Counter(tokens(body))
            if not term_counts:
                continue
            chunk_id = "c_" + hashlib.sha256(f"{source}\0{ordinal}\0{body}".encode("utf-8")).hexdigest()[:16]
            record = {
                "id": chunk_id,
                "source_path": source,
                "ordinal": ordinal,
                "text": body,
                "token_count": sum(term_counts.values()),
                "vector": _vector(term_counts, dimensions),
            }
            chunks.append(record)
            for term, count in term_counts.items():
                inverted[term][chunk_id] = count
            doc_freq.update(term_counts.keys())
    out = corpus_dir()
    out.mkdir(parents=True, exist_ok=True)
    with (out / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for record in chunks:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    index = {
        "schema": 1,
        "vectorizer": {"name": "hashing-tfidf-v1", "dimensions": dimensions},
        "document_count": len(chunks),
        "average_length": (sum(chunk["token_count"] for chunk in chunks) / len(chunks)) if chunks else 0.0,
        "document_frequency": dict(doc_freq),
        "postings": dict(inverted),
    }
    (out / "inverted_index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    manifest = {"schema": 1, "pages_dir": str(pages_dir), "chunk_count": len(chunks),
                "vector_dimensions": dimensions, "chunk_max_chars": max_chars,
                "chunk_overlap_chars": overlap_chars,
                "allowed_paths": sorted(allowed_paths) if allowed_paths is not None else None}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _load_files(chunks_path: Path, index_path: Path) -> tuple[list[dict], dict]:
    if not chunks_path.exists() or not index_path.exists():
        raise FileNotFoundError("corpus missing; run `project.py index` after persisting pages")
    chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return chunks, json.loads(index_path.read_text(encoding="utf-8"))


def _load() -> tuple[list[dict], dict]:
    out = corpus_dir()
    return _load_files(out / "chunks.jsonl", out / "inverted_index.json")


def search_files(chunks_path: Path, index_path: Path, query: str, top: int = 8) -> list[dict]:
    chunks, index = _load_files(chunks_path, index_path)
    terms = Counter(tokens(query))
    if not terms or not chunks:
        return []
    dimensions = index["vectorizer"]["dimensions"]
    qvec = _vector(terms, dimensions)
    n_docs = index["document_count"]
    avg_length = index["average_length"] or 1.0
    postings = index["postings"]
    lookup = {chunk["id"]: chunk for chunk in chunks}
    scores: Counter[str] = Counter()
    for term, qtf in terms.items():
        posting = postings.get(term, {})
        if not posting:
            continue
        idf = math.log(1 + (n_docs - len(posting) + 0.5) / (len(posting) + 0.5))
        for chunk_id, tf in posting.items():
            length = lookup[chunk_id]["token_count"]
            scores[chunk_id] += qtf * idf * (tf * 2.0) / (tf + 1.2 * (1 - 0.75 + 0.75 * length / avg_length))
    bm25_max = max(scores.values(), default=1.0)
    results = []
    # Include vector-only candidates too. This keeps retrieval useful when a
    # query uses different wording from the page and lets a real embedding
    # provider drop into the same file contract without changing the scorer.
    for chunk_id, chunk in lookup.items():
        bm25 = scores.get(chunk_id, 0.0)
        cosine = sum(a * b for a, b in zip(qvec, chunk["vector"]))
        fused = 0.6 * (bm25 / bm25_max) + 0.4 * max(0.0, cosine)
        if fused <= 0:
            continue
        results.append({"chunk_id": chunk_id, "score": round(fused, 6),
                        "bm25": round(bm25, 6), "cosine": round(cosine, 6),
                        "source_path": chunk["source_path"], "text": chunk["text"]})
    return sorted(results, key=lambda item: item["score"], reverse=True)[:top]


def search(query: str, top: int = 8) -> list[dict]:
    chunks_path = corpus_dir() / "chunks.jsonl"
    index_path = corpus_dir() / "inverted_index.json"
    return search_files(chunks_path, index_path, query, top)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpus", description="build and query the local research corpus")
    subs = parser.add_subparsers(dest="command", required=True)
    build_parser = subs.add_parser("build")
    build_parser.add_argument("--pages-dir", default="research_drift/pages")
    build_parser.add_argument("--max-chars", type=int, default=1200)
    build_parser.add_argument("--overlap-chars", type=int, default=160)
    build_parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    search_parser = subs.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)
    if args.command == "build":
        print(json.dumps(build(workspace() / args.pages_dir, args.max_chars, args.overlap_chars, args.dimensions), ensure_ascii=False))
    else:
        print(json.dumps(search(args.query, args.top), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
