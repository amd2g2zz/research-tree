---
name: research-tree
description: Deep research via RECURSIVE DESCENT over an emergent DAG of sub-questions, using weighted PageRank to DISCOVER the real (often cross-cutting) questions that naive deep-research misses. The input question is expected to be VAGUE — the skill sharpens it. Use whenever the user wants thorough research on a complex or broad topic, wants cross-domain intersections surfaced, or says deep research "expands but stays shallow / loses relevance." Triggers: "深度调研/系统梳理/彻底搞清楚/综述 X", "research/map the landscape of", "dig deep into", any complex multi-faceted question where current tools give breadth without precision. Produces a layered progressive-disclosure report with full provenance.
---

# research-tree

## What this skill does

Takes a **vague, broad** research question and finds what's *actually* worth
asking — then answers it. It does this by growing a **DAG of sub-questions from
the evidence** (structure emerges, it is not pre-specified), running **weighted
PageRank** to surface the central and **cross-cutting** sub-problems (nodes many
branches depend on), and resolving them by **recursive descent**. The output is
a **progressive-disclosure report** (TL;DR → findings → deep dive → evidence).

This directly fixes the two failure modes of ordinary deep research:
**it can't see cross-cutting problems** (tree exploration is isolated per
branch) and **it expands but loses relevance** (no priority signal). Here the
DAG makes intersections explicit and PageRank decides where to invest — both
*emerge from the graph*, never pre-judged.

## Two layers — who does what

| Layer | Who | Job |
|---|---|---|
| **Mechanical core** | `scripts/engine.py` | Holds the DAG; computes PageRank/communities/centroids; runs the phase machine; **decides the next action**; enforces budgets/convergence; writes all state + drift. |
| **Judgment** | you (the agent) | Three slots only: (1) decompose a question into sub-questions, (2) turn a question into search queries + gather evidence via the **anysearch** and **ddg** sub-skills, (3) synthesise an answer + confidence. |
| **Search** | anysearch + ddg **sub-skills** | You invoke them directly — do **not** shell out to them from Python. They are skills; the agent calls skills. |
| **Report** | you | Write `report.md` from the converged graph (progressive disclosure). |

**The engine decides WHAT to do next; you decide HOW.** Never decide priority
yourself — always let `engine next` pick the target.

## Workspace layout

```
<project>/
├── research_drift/        # the descent trajectory (append-only, resumable)
│   ├── dag.json           # the live DAG (nodes + weighted edges + meta/phase)
│   ├── drift_log.jsonl    # every action with rationale
│   ├── frame.md           # the sharpened research frame (mid-research deliverable)
│   └── pages/             # extracted page contents (via anysearch extract)
├── research/              # per-cluster analyses written by conscripted subagents
│   └── cluster-<id>.md
└── report.md              # final progressive-disclosure report
```

## The core loop

```bash
# scripts/ live under the skill dir; ENGINE = <skill>/scripts/engine.py
ENGINE="scripts/engine.py"
```

**1. Seed.** `engine init --question "<the vague question>"`

**2. Loop** until `engine next` returns `{"action":"done"}`:

Run `engine next`. Read `action` and do exactly that judgment, then record it:

| `action` | You do (judgment) | Record with |
|---|---|---|
| `decompose` | Propose sub-questions for `node`. Mark each `terminal` (a searchable fact) or `nonterminal` (needs further splitting). If a sub-question already seems to exist, link it instead of duplicating — **that cross-link is how cross-cutting problems get discovered.** | `engine grow --parent <node> --nodes '[{"question":"..","kind":"terminal","weight":0.8}]' --cross '[{"v":"<existing_node>","weight":0.7}]'` |
| `formulate` | Write 2–4 search queries for the `node`. | `engine formulate --node <node> --queries '["q1","q2"]'` |
| *(search)* | Invoke **anysearch** (primary) + **ddg** (secondary, if `ddgs` is installed) sub-skills with the node's queries. Collect hits, normalise/dedupe via `hits.py`. Extract the top 2–3 pages via anysearch `extract` into `research_drift/pages/`. | `engine search-result --node <node> --evidence '<hits.json>'` |
| `synthesize` | Read the node's evidence (terminal) or its children's answers (nonterminal). Write a concise answer + a calibrated `confidence` 0–1. Note contradictions. | `engine resolve --node <node> --answer ".." --confidence 0.7` |
| `lateral` | The engine picked two centroids — form ONE query that combines both vocabularies (to probe their intersection), then search + grow as above. | `grow`/`search-result` as needed |
| `reframe` | Structure has emerged. Read the returned `centroids` and rewrite the **research frame** in plain prose: "the vague question really resolves into these N central questions, M of them cross-cutting." **Show this to the user** (progressive disclosure starts during research, not at the end). | `engine reframe --frame ".."` |
| `await_children` | A nonterminal can't synthesise yet — its children aren't resolved. Just call `engine next` again; it will descend into the highest-PageRank child automatically. | *(no record — loop)* |
| `done` | Convergence reached. Go to **Analysis**. | — |

Notes:
- If `resolve` records `outcome: low_confidence_backtrack`, the engine already
  reset the node for retry — propose a *different* decomposition or extra
  queries next time you touch it. Budget is enforced by the engine.
- Run `engine status` anytime to see phase, top centroids, unresolved nodes.
- `engine export --format md` prints the DAG as an outline (★ = centroid).

## Search: use the sub-skills directly

For any `formulate`/search work, **invoke the `anysearch` and `ddg` skills
yourself** (they are sub-skills; the agent calls them — do not subprocess into
them from Python):

- **anysearch** (primary, keyless): `search`, `batch_search`, `get_sub_domains`
  for discovery, `extract` for full pages. Always fan out to it.
- **ddg** / duckduckgo-search (secondary, keyless, needs `pip install ddgs`):
  use for a second opinion / broader coverage. If `ddgs` isn't installed, skip
  silently — the skill degrades to anysearch-only.
- **Fan out both** for each query, then merge. Pipe the combined raw hits
  through `scripts/hits.py clean --hits '<json>'` to normalise field names,
  dedupe by host+path (keep the higher-credibility witness, record the other
  backend in `also_seen_from`), and score per-host credibility. Feed the result
  to `engine search-result`.
- Credibility defaults: official standards/arXiv/ACM/IEEE/vendor docs `.9`,
  GitHub `.75`, Wikipedia/major outlets `.6`, forums/blogs `.4`, unknown `.5`.

## Analysis — conscript subagents

When `engine next` returns `done`, the search/descent is finished. Now analyse
in parallel:

1. Read `engine export --format json`. Partition resolved nodes by `community`
   (each community ≈ a chapter; its centroid is the chapter's anchor question).
2. **Spawn one subagent per cluster** (parallel, single message). Each reads its
   slice of `dag.json` + relevant `drift_log` + `pages/` and **writes**
   `research/cluster-<id>.md` with:
   - `summary` (1–2 paragraphs)
   - `findings`: `[{claim, confidence, evidence_refs:[...]}]`
   - `gaps`: what couldn't be resolved
   - `contradictions`: `[{a, b}]`
   - `provenance`: `{evidence_ref: url}`
3. Centroid / cross-cutting clusters (multi-parent nodes, high PageRank) are the
   headline material — flag them.

## Report — progressive disclosure

Compose `report.md` from `research/cluster-*.md` + `frame.md`, layers in order
(reader can stop at any layer):

- **L0 — TL;DR**: the root answer in 3–5 sentences + overall confidence.
- **L1 — Key findings**: headline claims with confidence badges; **cross-cutting
  / centroid findings first** (that's what other tools miss).
- **L2 — Deep dive**: one section per cluster, anchored at its centroid.
- **L3 — Evidence & provenance**: source list with credibility, contradictions,
  pointers into `research_drift/`.
- **L4 — Appendix**: full DAG outline (`engine export --format md`), query log
  (from `drift_log.jsonl`), methodology, limitations, gaps.

Use `assets/report_template.md` as the skeleton.

## Config & references

Override mechanical knobs at seed time: `engine init --question ".." --config
max_depth=5 grow_step_budget=40 pr_epsilon=0.015`. Defaults are tuned for
medium research depth.

Read these only when needed (progressive disclosure):
- `references/algorithm.md` — full formalisation: why recursive descent + DAG,
  why PageRank surfaces cross-cuts, convergence math, the emergence argument.
- `references/contracts.md` — exact JSON shapes for `dag.json`, drift records,
  cluster analyses, evidence.
- `references/search-subskills.md` — detailed anysearch/ddg usage + extraction.
- `references/report-rubric.md` — quality bar + checklist per report layer.
