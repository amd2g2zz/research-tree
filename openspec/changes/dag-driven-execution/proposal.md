# Proposal: dag-driven-execution

## Why

issue #531 (code-verified): the compiled strategy graph is a validated
dependency DAG at compile time, but execution never runs on it.
`select_research_actions` cuts `frontier_node_ids[:max_parallelism]` — a
pure selection-value greedy cut with zero dependency awareness — so a
high-scoring node whose dependencies are unfinished dispatches anyway.
Nodes carry only `parent_id` (single-parent tree): the research tree cannot
even express a DAG structurally, dependencies neither gate dispatch nor
propagate (a worker receives the global execution context and no knowledge
of whose conclusions it stands on). Same disease family as #530: structure
exists at compile time, nothing consumes it at runtime.

## What Changes

1. Node-level dependency edges (recursive_search.py): nodes gain an optional
   `depends_on` list of node ids. `parent_id` keeps lineage semantics;
   `depends_on` carries scheduling semantics. Additive optional field
   (the #492/#495 schema pattern) — legacy nodes without it behave exactly
   as today. Cycles, self-dependencies, and unknown dependencies are
   rejected at merge/ingest time (`apply_research_results`), reusing the
   `_stable_topological_order` pattern already proven in work_items.py
   alongside decision_map's compile-time slot check.
2. Ready-set dispatch: `select_research_actions` computes the ready set —
   every `depends_on` node closed/deferred — and cuts `max_parallelism`
   from it by selection value. A high-value unready node does NOT dispatch;
   if the ready set is smaller than `max_parallelism`, fewer actions are
   returned (no backfill from unready nodes).
3. Dependency context propagation: a dispatched node's execution context
   carries a `dependency_context` list — each dependency's node id, slot,
   question, status, and a deterministic `conclusion_digest` — so the
   worker knows what it stands on. Absent for dependency-free nodes.
4. Convergence semantics: a multi-dependency node's readiness = all
   dependencies closed. The existing triangulation/validation mandatory-node
   machinery keeps working alongside (expressible AS dependencies where
   natural, not removed in this issue).
5. Slot-level propagation: `_slot_state` carries the compiled slot
   `depends_on` through to the research state; a downstream slot's root
   nodes stay out of the ready set until the upstream slot closes.

## Impact

- src/research_tree/recursive_search.py: additive `depends_on` on nodes and
  slots, one ingest-time validation function, ready-set filter in
  `select_research_actions` (+ per-node context injection).
- src/research_tree/decision_map.py: none expected (compile-time checks
  already exist); reserved for reuse if the node-level check needs its
  error type.
- tests/test_dag_execution.py: 9 scenario-named tests (RED first).
- Legacy states (schema-1 nodes without `depends_on`) dispatch exactly as
  today; no forced migration.
