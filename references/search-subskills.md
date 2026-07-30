# Search execution

Search providers execute a Frame's query plan; they do not decide what the next
research direction is. The Frame already contains its user-intent clauses,
explicit entity anchors, information gap, local cognition, and time scope.

## Provider policy

Use `uv run python scripts/providers.py eligible` to see the allowed transport pool.
The default is free-first, no paid provider, no high anti-bot-risk provider, and
record-and-continue on failure. There is intentionally no `--intent academic`
or other semantic routing switch.

Run every enabled provider against every stored query plan item, in parallel up
to `policy.max_parallel`. A failure is a Frame-local execution event, not a
reason to alter the recursive DAG or abandon the remaining provider jobs. Each
provider/query pair receives a terminal `ok`, `failed`, `skipped`, or
`unavailable` record.

## Acceptance discipline

1. Use the original user object/wording as an initial anchor when applicable.
2. Compile later queries from the Frame's information gap and applicable clauses.
3. Apply expressible constraints to the provider request, but always apply the
   full `ConstraintEnv` again when accepting sources.
4. Let the coordinator materialize a bounded, balanced union of valid leads
   and save its returned source content under `research_drift/pages/`.
5. Run exactly one Source Aggregator over the saved collection. It performs
   semantic/topic-aware de-duplication and preserves contradiction/context
   distinctions, then supplies source-quality and topic-confidence rationale
   bound to the source-manifest hash.
6. Have the two source-review workers select only from that completed
   aggregation and saved collection, then submit their reviewer-scoped evidence
   commands. A low-quality or non-representative selection needs a documented
   override rationale.
7. Use `engine extract` only after both reviews complete and an Extractor can
   cite a stable source locator.

Search snippets and result pages are discovery leads, never final evidence.

## Built-in discovery executor

Run stored `acquiring` frame plans explicitly through the safe discovery layer:

```bash
uv run python scripts/research_orchestrator.py --discover --write
```

It writes one cached batch per frame under `research_drift/discovery/`, with
the exact successful provider bodies under
`research_drift/discovery/raw/<frame>/<request-sha256>/`. The cache key binds
the query plan and provider policy, so unchanged plans do not repeat network
requests unless `--refresh-discovery` is supplied. A normalized successful lead
without an archived raw response is downgraded to `raw_response_missing` and is
not materialized.

The coordinator then deduplicates leads by normalized public HTTPS URL and
round-robins them across providers before applying
`source_capture_limit_per_frame`. It writes
`research_drift/sources/<frame>.json`; every eligible candidate is recorded as
`captured`, `failed`, or `deferred_budget`. This manifest and the saved pages
must exist before any worker can assess sources. Each captured record binds a
page SHA-256; a missing or altered raw response or captured page makes its
cache invalid and sends the Frame back through coordinator collection. A valid
collection enters `aggregating`, where only the Source Aggregator task is
scheduled. It writes `research_drift/aggregation/<frame>.json`, bound to the
exact manifest hash, before reviewer tasks can appear.

The manifest deliberately distinguishes discovery and capture provenance.
`discovered_by` and `discovery_providers` list every provider that surfaced a
lead; `capture_provider` identifies the transport that saved the selected
content. A lead may have multiple discovery origins but one capture transport.
Substantive arXiv/OpenAlex/Crossref metadata can use its originating provider
capture path, but it is explicitly marked `metadata_limited` and not full text;
short metadata falls back to the controlled AnySearch boundary. Do not treat a
shared `capture_provider` as a claim that all sources were found by that engine
or that they lack independent origin. Inspect `summary.origin_coverage` for
both provenance dimensions.

The bundled adapters use fixed HTTPS hosts, fixed API paths, a timeout, a
response-size cap, and no redirects:

- `anysearch`: anonymous-capable general web discovery through the fixed
  `https://api.anysearch.com/mcp` JSON-RPC endpoint. It reads
  `ANYSEARCH_API_KEY` only when the process already has one; it never reads a
  skill-local `.env`, writes a key, or treats rendered Markdown as evidence.
- `arxiv`: version-pinned academic-paper candidates.
- `openalex`: scholarly-work metadata and landing-page leads.
- `crossref`: DOI-indexed work metadata.
- `github`: public repository candidates.

AnySearch results are parsed defensively into bounded HTTPS leads. The archived
search response is the successful JSON-RPC envelope, not the derived rendered
Markdown. During the coordinator collection stage, selected valid leads are
passed through the controlled AnySearch capture boundary and their returned
Markdown is saved. This makes AnySearch the body capture transport in the
bundled path; it does not overwrite or collapse the lead's discovery-provider
provenance.
Source Triager and Source Adversary workers never fetch a lead themselves. The
same boundary remains available for a coordinator-managed recovery capture:

```bash
uv run python scripts/source_acquirer.py extract --url "https://example.com/source" --title "Source title"
```

It saves the returned Markdown under `research_drift/pages/` and prints a
structured evidence proposal. The acquirer never changes the DAG. In the
normal flow, the coordinator records this proposal in the source manifest and
the reviewers decide whether to submit it as evidence. `host_adapter.py
acquire-source` exposes the same safe operation for a coordinator-managed
recovery workflow.

AnySearch documents its HTML extractor with a 50,000-character limit. A saved
response at that boundary is marked `capture.status: possibly_truncated`: it
can support only cited captured passages, not a claim that the original page
was read in full. Use another accepted acquisition method when complete source
coverage is necessary.

## arXiv Adapter

When `arxiv` is present in the eligible provider pool, use the bundled adapter
for a Frame's academic-paper discovery or metadata verification. It is an
execution adapter, not a semantic routing rule.

```bash
uv run python scripts/arxiv.py search --query "agent writing" --sort submitted --max 10
uv run python scripts/arxiv.py search --author "Yann LeCun" --category cs.LG --max 5
uv run python scripts/arxiv.py search --id 2402.03300v7
uv run python scripts/arxiv.py semantic --id 2402.03300v7 --relation citations --limit 20
```

The adapter emits JSON candidates with the versioned `arxiv_id`, publication and
update dates, category, abstract, and version-pinned abstract/PDF/HTML links.
Preserve the exact version returned by the API; do not replace `v7` with an
unversioned link. Reject candidates whose abstract says withdrawn or retracted.

ArXiv requests use the free Atom API and should be spaced by about three seconds
when issuing more than one request. Semantic Scholar enrichment is optional;
its public API may rate-limit anonymous calls, and `SEMANTIC_SCHOLAR_API_KEY`
is read only when already configured by the user.

An arXiv result is still only a lead. Save the full, versioned paper content
under `research_drift/pages/` using the approved extractor, then submit it to
`engine evidence`. Use the metadata abstract only for screening and query
refinement.
