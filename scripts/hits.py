"""hits.py — pure post-search helper (no network, no sub-skill calls).

The agent invokes the anysearch + ddg SUB-SKILLS to gather raw hits, then pipes
the combined list through this module to: normalise the many field names the two
engines use, dedupe the same page seen via different engines (keeping the more
credible witness and recording the others in `also_seen_from`), and score
per-host credibility. The cleaned list is fed to `engine search-result`.

This is deliberately a leaf utility: it never reaches out to the network and
never calls the sub-skills (the agent does that). It only does mechanical work
on whatever hits it is handed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from urllib.parse import urlparse

# Per-host credibility heuristics (substring matched against the host).
# Tunable; the agent may override `credibility` on any individual hit.
_HOST_RULES = [
    (0.90, ("arxiv.org", "ieeexplore.ieee.org", "dl.acm.org", "acm.org",
            "springer.com", "sciencedirect.com", "wiley.com", "nist.gov",
            "iso.org", "ietf.org", "rfc-editor.org", "cve.mitre.org",
            "kernel.org", "python.org", "go.dev", "rust-lang.org")),
    (0.80, ("github.com", "gitlab.com", "stackoverflow.com", "mathoverflow.net")),
    (0.60, ("wikipedia.org", "britannica.com", "nature.com", "sciencemag.org")),
    (0.40, ("reddit.com", "medium.com", "substack.com", "forum", "forums")),
]


def credibility_by_host(host: str) -> float:
    host = (host or "").lower()
    for score, hosts in _HOST_RULES:
        if any(h in host for h in hosts):
            return score
    return 0.5


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except Exception:
        return ""


def _ref(url: str, title: str) -> str:
    return "e_" + hashlib.sha1((url or title).encode()).hexdigest()[:10]


def normalize_hit(raw: dict) -> dict:
    """Collapse any engine's field names into one shape and score credibility."""
    url = (raw.get("url") or raw.get("href") or raw.get("link") or "").strip()
    title = (raw.get("title") or raw.get("name") or "").strip()
    snippet = (raw.get("snippet") or raw.get("description") or raw.get("abstract")
               or raw.get("body") or raw.get("text") or "").strip()
    host = _host_of(url)
    return {
        "ref": _ref(url, title),
        "url": url,
        "host": host,
        "title": title,
        "snippet": snippet[:600],
        "backend": raw.get("backend", "unknown"),
        "credibility": float(raw.get("credibility") or credibility_by_host(host)),
        "raw_url_title": f"{title} - {url}",
    }


def dedupe(hits: list) -> list:
    """Dedupe by host+path; keep the highest-credibility witness, note alts."""
    out: dict = {}
    for h in hits:
        if not h.get("url"):
            key = "title::" + h.get("title", "").lower()
        else:
            p = urlparse(h["url"])
            key = (p.netloc.lower() + p.path.lower()).rstrip("/") or h["url"].lower()
        if key in out:
            kept = out[key]
            kept.setdefault("also_seen_from", [])
            if h["backend"] not in kept["also_seen_from"]:
                kept["also_seen_from"].append(h["backend"])
            if h["credibility"] > kept["credibility"]:
                alts = kept.get("also_seen_from", [])
                h2 = dict(h)
                h2["also_seen_from"] = alts
                out[key] = h2
        else:
            out[key] = dict(h)
    return list(out.values())


def clean(raw_hits: list, top: int | None = None) -> list:
    norm = [normalize_hit(h) for h in raw_hits if isinstance(h, dict)]
    deduped = dedupe(norm)
    deduped.sort(key=lambda h: h["credibility"], reverse=True)
    if top:
        deduped = deduped[:top]
    return deduped


def _read_hits(arg: str) -> list:
    if arg == "-":
        return json.loads(sys.stdin.read() or "[]")
    return json.loads(arg)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="hits", description="normalise/dedupe/score raw hits")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clean", help="clean a JSON list of raw hits -> engine-ready evidence")
    c.add_argument("--hits", required=True, help="JSON list, or '-' to read stdin")
    c.add_argument("--top", type=int, help="keep only the top-N most credible")
    a = sub.add_parser("cred", help="score one host")
    a.add_argument("--host", required=True)
    args = ap.parse_args()
    if args.cmd == "clean":
        print(json.dumps(clean(_read_hits(args.hits), args.top), ensure_ascii=False, indent=2))
    elif args.cmd == "cred":
        print(credibility_by_host(args.host))
