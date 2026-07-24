# research-tree

A Claude Code **skill** for deep research. Takes a vague, broad question,
discovers the sub-questions that *actually* matter (including cross-cutting ones
ordinary deep-research misses), resolves them, and writes a layered
progressive-disclosure report with full provenance.

Core algorithm: **recursive descent over an emergent DAG of sub-questions**,
with **weighted PageRank** as the priority signal. Relevance is *emerged* from
the grown graph, never pre-specified — so it works even when you don't yet know
what you're looking for.

## Why it's different

Naive deep research (a) can't see **cross-cutting problems** (tree exploration is
isolated per branch) and (b) **expands but loses relevance** (no priority
signal). research-tree grows a **DAG** where shared sub-problems become
multi-parent nodes, and **PageRank** ranks them — so the central, cross-cutting
questions surface automatically and research budget goes where it matters.

## How it works — two layers

- **`scripts/engine.py`** — the mechanical core. Holds the DAG (networkx),
  computes weighted PageRank + community centroids, runs the phase machine
  (seed → grow → resolve → converged), and **decides the next action**. The
  engine never asks the LLM to do graph maths.
- **The agent** — fills three judgment slots: decompose a question, formulate
  queries + gather evidence, synthesise an answer. It invokes the **anysearch**
  and **ddg** sub-skills directly for search (they are skills, not subprocessed).
- **`scripts/hits.py`** — pure helper to normalise/dedupe/credibility-score the
  hits the agent collected before feeding them to the engine.

The engine decides **what** to do next; the agent decides **how**.

## Install

```bash
# option A: symlink into your skills dir (edits stay in this repo)
ln -s "$PWD" ~/.claude/skills/research-tree        # macOS/linux
# or copy:
cp -r . ~/.claude/skills/research-tree
```

Dependencies:
- **networkx** (required) — `pip install networkx`. PageRank is in-process; no scipy needed.
- **ddgs** (optional, for the DuckDuckGo backend) — `pip install ddgs`. Without
  it, the skill degrades to anysearch-only.
- **anysearch** skill (required for search) — install separately; it's a sub-skill.

## Quick start

```bash
ENG="scripts/engine.py"
python "$ENG" init --question "how to fully automate reverse engineering with agents"
python "$ENG" next          # -> tells you the next action (decompose/formulate/...)
# ... agent loop: act on each `next`, then record (grow/formulate/search-result/resolve)
# ... until `next` returns {"action":"done"}
python "$ENG" status        # phase, top centroids, unresolved
python "$ENG" export --format md   # DAG outline
```

See `SKILL.md` for the full loop, analysis (conscript subagents per cluster), and
the progressive-disclosure report.

## Layout

```
research-tree/
├── SKILL.md                     # identity + the full orchestration protocol
├── README.md
├── references/                  # read on demand (progressive disclosure)
│   ├── algorithm.md             # why recursive descent + DAG + PageRank
│   ├── contracts.md             # exact JSON shapes
│   ├── search-subskills.md      # anysearch + ddg usage
│   └── report-rubric.md         # per-layer quality bar + checklist
├── scripts/
│   ├── engine.py                # the mechanical algorithm (core)
│   └── hits.py                  # post-search normalise/dedupe/credibility
└── assets/report_template.md    # progressive-disclosure report skeleton
```

## Config (at seed time)

`engine init --question ".." --config <k=v>..`. Defaults (in `engine.py`):

| knob | default | meaning |
|---|---|---|
| `max_depth` | 4 | recursion bound |
| `max_retries` | 2 | backtrack budget per node |
| `grow_step_budget` | 30 | growth steps before forcing resolve |
| `pr_epsilon` | 0.02 | PageRank L1 delta counts as "stable" |
| `pr_stable_rounds` | 2 | stable growth rounds needed to converge |
| `lateral_every` | 5 | steps between intersection queries |
| `merge_threshold` | 0.6 | lexical Jaccard to reuse a node (cross-link) |
| `synthesize_threshold` | 0.6 | confidence below this triggers backtrack |

## Status

Core (`engine.py`, `hits.py`, `SKILL.md`, references, template) is complete and
the engine is smoke-tested (PageRank varies; multi-parent cross-cutting nodes
rise to the top; no spurious convergence). `evals/` for skill-creator benchmarking
is the remaining optional piece.
