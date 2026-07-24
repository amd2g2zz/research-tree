# Data contracts

Exact shapes the engine writes and the agent/subagents read. The engine is the
single writer of `dag.json` and `drift_log.jsonl`; the agent writes `frame.md`,
`pages/*`, `research/cluster-*.md`, and `report.md`.

## `research_drift/dag.json` — the live DAG

```jsonc
{
  "root": "n_001_abc123",
  "root_phrase": "how to fully automate reverse engineering with agents",
  "phase": "seed|grow|resolve|converged",
  "step": 12,                 // monotonic action counter
  "seq": 27,                  // node-id sequence
  "pr_stable_count": 1,       // consecutive stable growth rounds
  "pr_delta": 0.011,          // last PageRank L1 delta
  "grew_since_recompute": false,
  "config": { "...": "see DEFAULTS in engine.py" },
  "research_frame": "optional - the sharpened frame text (also in frame.md)",
  "prev_pagerank": { "n_001_abc123": 0.168 },   // internal, for delta
  "nodes": {
    "n_001_abc123": {
      "id": "n_001_abc123",
      "question": "how to fully automate reverse engineering with agents",
      "kind": "nonterminal",            // terminal | nonterminal
      "state": "open",                  // open|querying|growing|synthesized|failed|pruned
      "answer": null,                   // string once synthesised
      "confidence": 0.0,                // 0..1, set on resolve
      "pagerank": 0.168,                // recomputed by engine
      "community": 0,                   // louvain community id (or null)
      "is_centroid": false,             // true = max-PR node of its community
      "root_proximity": 1.0,            // lexical Jaccard to root_phrase
      "depth": 0,
      "queries": [],                    // for terminals: search query strings
      "evidence": [],                   // evidence refs/hits from search-result
      "retries": 0,
      "created_step": 0,
      "resolved_step": null
    }
  },
  "edges": [["n_001_abc123", "n_002_def456", 0.9]]   // [parent, child, weight]
}
```

State semantics: `open`/`querying`/`growing` = unresolved; `synthesized` =
answered; `failed` = budget exhausted; `pruned` = double-low, excluded.

## `research_drift/drift_log.jsonl` — append-only descent trace

One JSON object per line. `action` ∈ `init | phase | grow | formulate |
search_result | resolve | backtrack | reframe`.

```jsonc
{"step": 4, "action": "resolve", "ts": "2026-07-24T06:14:53+00:00",
 "node": "n_004_040a22", "confidence": 0.7, "outcome": "synthesized"}
{"step": 4, "action": "phase", "ts": "2026-07-24T06:14:53+00:00",
 "from": "grow", "to": "resolve"}
{"step": 3, "action": "grow", "ts": "...", "parent": "n_001_abc123",
 "created": ["n_002_def456"], "reused": ["n_005_ghi789"],
 "cross_edges": [{"v": "n_005_ghi789", "weight": 0.7}]}
```

`ts` is ISO-8601 UTC. `reused` lists nodes linked (not duplicated) — each is a
surfaced cross-cutting sub-problem.

## Evidence list (input to `engine search-result --evidence`)

Output of `hits.py clean`. Fed verbatim:

```jsonc
[{"ref": "e_3b1f9a2c1d", "url": "https://arxiv.org/abs/2401.00001",
  "host": "arxiv.org", "title": "Autonomous RE Agents",
  "snippet": "...", "backend": "anysearch", "credibility": 0.9,
  "also_seen_from": ["ddg"], "raw_url_title": "Autonomous RE Agents - https://..."}]
```

## `research/cluster-<id>.md` — per-community analysis (written by a subagent)

```markdown
---
cluster_id: 0
centroid: n_007_xyz         # the anchor node id
centroid_question: "..."
cross_cutting: true         # any node in this cluster has >=2 parents
---

## Summary
1-2 paragraphs.

## Findings
- claim: "..."  confidence: 0.8  evidence: [e_3b1f9a2c1d, e_9a2c...]

## Gaps
- what could not be resolved

## Contradictions
- a: "..."  vs  b: "..."

## Provenance
- e_3b1f9a2c1d: https://arxiv.org/abs/2401.00001
```

## `report.md` — progressive disclosure layers

- **L0 TL;DR** — root answer, 3–5 sentences + overall confidence.
- **L1 Key findings** — headline claims w/ confidence badges; cross-cutting first.
- **L2 Deep dive** — one section per cluster, anchored at its centroid.
- **L3 Evidence & provenance** — sources + credibility + contradictions + drift pointers.
- **L4 Appendix** — full DAG outline, query log, methodology, limitations, gaps.

Skeleton in `assets/report_template.md`.
