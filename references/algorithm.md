# Algorithm: recursive descent + emergent DAG + PageRank

This reference explains *why* the skill is shaped the way it is. For the exact
commands see `SKILL.md`; for data shapes see `contracts.md`.

## The problem

Ordinary deep research fails two ways on a complex, vaguely-scoped question:

1. **It can't see cross-cutting problems.** Tree exploration is isolated per
   branch, so a sub-problem that several branches actually depend on never
   surfaces as the shared, central thing it is.
2. **It expands but loses relevance.** "Find more about X" drifts; breadth grows
   while precision collapses, because there is no priority signal.

This skill attacks both by growing a **DAG** (intersections become explicit) and
using **PageRank** (an objective priority signal) — and both *emerge from the
graph*, never pre-judged.

## Recursive descent — the resolver

A research question is parsed like a grammar. `parse(Q)`:

- **terminal** (an atomic, searchable fact) → search → extract → answer.
- **nonterminal** (compound) → decompose into sub-questions → `parse` each →
  synthesise the children's answers into one answer.
- **backtrack** on failure: if synthesis confidence < threshold (or children
  contradict), re-decompose or add queries, within a per-node budget. This is
  exactly a parser retrying the next production when one fails to match.

Traversal is depth-first, bounded by `max_depth` and `max_retries`. Recursive
descent is the **resolution mechanism** — it answers "how do I resolve *this*
node?" It does not decide *which* node to resolve next; PageRank does.

## Why a DAG, not a tree — memoisation surfaces cross-cuts

If the same sub-question is reached from two different parents, a tree
duplicates it (and never realises they're the same). A **DAG links to the
existing node instead** (`engine grow --cross`). A node with multiple parents =
a sub-problem that several branches depend on = a **cross-cutting problem** —
precisely the high-value, hard-to-find one. The DAG is the data structure that
makes intersections first-class. Edges are cycle-safe: `engine` rejects any edge
that would create a cycle (a question can't depend on itself).

## PageRank — emergent importance, the scheduler

Edges are `parent → child` with a weight = how strongly the parent depends on
the child (set by the agent at growth time, 0–1). Weighted PageRank then gives
each node an importance = the weighted sum of the importances pointing at it.

- **High in-degree from important parents ⇒ high PageRank ⇒ central /
  cross-cutting.** This is *computed*, not judged — which dissolves the
  relevance paradox: we never need to know upfront what matters; the grown graph
  tells us, and it updates every round as the structure grows.
- **Centroids:** communities are detected (Louvain) on the undirected projection
  of the DAG; each community's highest-PageRank node is its **centroid** — the
  representative "real question" of that cluster. Communities map roughly to
  report chapters; centroids are their anchors.
- **Proximity:** lexical Jaccard overlap with the (vague) root phrase is a *loose*
  relevance anchor, never a hard filter. Pruning uses the **double-low rule**:
  drop a node only if PageRank is low **and** root-proximity is low. Single-low
  nodes are kept (they may be an emerging cross-cut nobody has linked yet).

## The emergence argument — why relevance is not pre-specified

The whole value of research is discovering what you didn't know to ask. So
requiring the agent to pre-write a "relevance contract" for each sub-question
would be circular — if it already knew what mattered, it wouldn't need to
research. Instead:

1. **Grow structure from evidence** (seed → broad search → extract sub-topics →
   link, including cross-links to existing nodes).
2. **Recompute PageRank** → centroids reveal the real questions.
3. **Reframe** — rewrite the research frame from the centroids ("the vague
   question actually resolves into these N central questions, M cross-cutting").
   The root question is *sharpened by what was found*, and shown to the user
   mid-research (progressive disclosure starts early).

## Phase machine + convergence

`seed` (only the root) → `grow` (broaden: decompose centroids, search their
neighbourhoods, fire lateral intersection queries) → `resolve` (deepen: resolve
all centroids and high-PageRank terminals) → `converged`.

Convergence is mechanical: the PageRank L1 delta between consecutive **real
growth rounds** (not no-op recomputes) stays below `pr_epsilon` for
`pr_stable_rounds` rounds **and** every centroid is synthesised. Then analysis
begins.

## Lateral intersection queries

Every `lateral_every` steps, if ≥ 2 centroids exist, the engine emits a
`lateral` action naming the top centroid pair. The agent forms **one** query
combining both vocabularies and searches — this actively probes the
intersection of two central sub-problems and tends to create new cross-links
(the richest source of cross-cutting findings).

## Division of labour (why this split)

Deterministic control flow — graph maths, ordering, budgets, convergence, drift
— is exactly what LLMs are unreliable at, so it lives in `engine.py` (mechanical
script). Genuine judgment — *what* the sub-questions are, *what* queries to ask,
*what* the answer is — is what LLMs are good at, so the agent fills those three
slots. Search is delegated to the anysearch + ddg **sub-skills**, which the agent
invokes directly. **The agent never decides priority; PageRank does.**
