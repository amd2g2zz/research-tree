# Search sub-skills: anysearch + ddg

The agent does the searching by **invoking these two sub-skills directly**. Do
not shell out to them from Python — they are skills, and the agent calls skills.
This reference just documents their interfaces so you fan them out correctly.

## anysearch — primary, keyless

Always fan out to anysearch. Its CLI lives at
`~/.claude/skills/anysearch/scripts/anysearch_cli.py` (the skill itself tells you
the runtime; Python is the usual one here).

- `search "<query>" --max_results N` → **Markdown**, not JSON. Blocks look like:
  ```
  ## Search Results (N results, Xms)
  ### 1. <title>
  - **URL**: <url>
  - <snippet...>
  ```
  Read title/URL/snippet from each `### ` block.
- `batch_search --queries '[...]'` for several independent queries at once.
- `get_sub_domains --domain <finance|health|security|...>` then `search ... --sub_domain <...> --sdp key=value` for **vertical** queries (CVE / DOI / patent / IP / etc.) — much better than web search for domain-shaped lookups.
- `extract "<url>"` → the page as Markdown. Use for the top 2–3 hits per node;
  save to `research_drift/pages/<host>-<ref>.md` and reference that path.

## ddg (duckduckgo-search) — secondary, keyless

A second opinion / broader coverage. Needs `pip install ddgs` (check with
`command -v ddgs`). If absent, **skip silently** — the skill degrades to
anysearch-only; do not block.

- `ddgs text -q "<query>" -m N -o json` → **JSON** list of `{title, href, body}`.
- `ddgs news -q "..." -m N` for recent news; `-r us-en` region, `-t w` time
  (day/week/month/year).

Source: NousResearch/hermes-agent `duckduckgo-search` skill.

## Per-terminal-node workflow

1. The engine emitted `formulate` for a node → you wrote queries
   (`engine formulate`). Then:
2. **Fan out** every query to **both** anysearch and ddg (parallel). For
   domain-shaped queries, prefer anysearch vertical (`get_sub_domains` first).
3. Collect the raw hits from both (anysearch markdown blocks + ddg JSON). Assemble
   them into one JSON list, tagging each with `"backend": "anysearch"|"ddg"`.
4. Pipe through `scripts/hits.py clean --hits '<json>' --top 8` → normalised,
   deduped (same page via both engines merges; alt backend recorded in
   `also_seen_from`), credibility-scored, truncated.
5. `engine search-result --node <node> --evidence '<cleaned json>'`.
6. Extract the 2–3 most credible pages via anysearch `extract` →
   `research_drift/pages/`; mention their paths in the node's eventual answer.

## Credibility (defaults in `hits.py`; override per-hit when warranted)

official standards / arXiv / ACM / IEEE / vendor docs → `.9` · GitHub / Stack
Overflow → `.8` · Wikipedia / major outlets → `.6` · forums / blogs → `.4` ·
unknown → `.5`. LLM-derived surveys count as `.5` unless peer-reviewed.

## Provenance discipline

Every claim in the final report must trace to an evidence `ref` that points at a
real URL (and, if extracted, a local page). No unsupported narrative chains — if
a hit only asserts without sourcing, mark its finding lower-confidence and say so.
