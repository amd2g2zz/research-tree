# Report rubric — progressive disclosure quality bar

The report is layered so a reader can stop at any depth and get a coherent
answer. Each layer has a hard quality bar; do not publish until its checklist
passes. Cross-cutting / centroid findings come first — they are what other tools
miss and the main reason this skill exists.

Confidence badges: **high** ≥ 0.8 · **medium** 0.6–0.8 · **low** < 0.6.

## L0 — TL;DR
- 3–5 sentences that **answer the root question directly** (not describe what was
  researched).
- One overall confidence badge, derived from the centroids' confidences (min or
  weighted mean; lower if centroids contradict).
- Passes the "busy executive" test: readable in 20 seconds.

## L1 — Key findings
- ≤ 7 headline claims, each one line + a confidence badge + ≥1 evidence ref.
- **Cross-cutting findings first** (multi-parent centroid nodes), clearly tagged
  `◆ cross-cutting`. These are the headline.
- No claim without a ref; no ref-free speculation.

## L2 — Deep dive
- One section per cluster (community), titled by its **centroid question**.
- Each section: what was asked → what the evidence says → the answer + confidence
  → inline contradictions/gaps.
- Cite evidence refs inline `[e_3b1f…]`; do not paraphrase away the source.
- Sections ordered by centroid PageRank (most central first).

## L3 — Evidence & provenance
- A source table: ref · url · host · credibility · also_seen_from · local page
  path (if extracted).
- Contradictions enumerated: `{claim A [refs]} vs {claim B [refs]}`.
- Pointers into `research_drift/` (drift_log line ranges, dag.json node ids) so
  the trajectory is auditable.

## L4 — Appendix
- Full DAG outline: paste `engine export --format md`.
- Query log: the `formulate`/`search_result` records from `drift_log.jsonl`.
- Methodology: state "recursive descent + emergent DAG + weighted PageRank", the
  config knobs used (`max_depth`, `grow_step_budget`, …), phase timeline.
- Limitations & gaps: unresolved/`failed`/`pruned` nodes, why, and what a follow-up
  pass should target.

## Pre-publish checklist
- [ ] Every claim in L0/L1/L2 has ≥1 evidence ref.
- [ ] Cross-cutting findings are tagged and lead L1.
- [ ] Confidence badges present and calibrated (not everything "high").
- [ ] Contradictions are shown, not hidden.
- [ ] No tool-name narration in the prose ("then I ran Ghidra/anysearch…") — the
      report reads as analysis, not a process log.
- [ ] L4 DAG + query log present for auditability.
- [ ] Root question actually answered in L0 (re-read it against `root_phrase`).

## Anti-patterns
- **Narrative-only chains:** a sequence of assertions with no evidence ref at
  each step. Break them: every step cites a ref, or it's flagged as inference.
- **Breadth-as-rigor:** dumping many low-relevance sources. Relevance (root
  proximity + PageRank rank) outranks count; prune hard.
- **Hidden uncertainty:** silently dropping low-confidence nodes. Surface them in
  L4 gaps instead.
