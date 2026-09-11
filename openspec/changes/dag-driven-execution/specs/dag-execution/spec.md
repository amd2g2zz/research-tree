## ADDED Requirements

### Requirement: nodes carry scheduling dependencies as data

A research node MUST be able to declare `depends_on`: a list of node ids it
must see closed before it is dispatchable. `parent_id` keeps lineage
semantics; `depends_on` carries scheduling semantics. The field is additive
and optional — nodes without it MUST dispatch exactly as before.

#### Scenario: legacy nodes without depends_on behave as today
- **WHEN** a persisted state whose nodes carry no `depends_on` key is selected from
- **THEN** the selected actions, their order, and their execution context equal today's
  greedy cut with no dependency gating and no injected dependency context

### Requirement: ingest rejects invalid node dependency edges

Merging finding packs MUST validate the merged node graph: `depends_on`
must reference known node ids, never the node itself, and never form a
cycle. Violations MUST reject the merge before anything dispatches.

#### Scenario: cycle in depends_on rejected at merge time
- **WHEN** `apply_research_results` ingests into a state whose nodes form a
  `depends_on` cycle
- **THEN** the merge raises a node-dependency error naming the cycle members and nothing is dispatched

#### Scenario: unknown dependency rejected at merge time
- **WHEN** a node's `depends_on` references a node id absent from the tree
- **THEN** the merge raises a node-dependency error naming the unknown ids

### Requirement: dispatch draws from the dependency-ready set

`select_research_actions` MUST compute the ready set — every `depends_on`
node closed or deferred — and cut `max_parallelism` from it by selection
value. A high-value unready node MUST NOT dispatch; a ready set smaller
than `max_parallelism` MUST yield fewer actions, never a backfill from
unready nodes.

#### Scenario: open dependency blocks a high-value node
- **WHEN** the highest-selection-value frontier node has an unclosed dependency
- **THEN** it is absent from the selection output while lower-value ready nodes dispatch

#### Scenario: closing the last dependency unlocks dispatch in the same pass
- **WHEN** the last open dependency of a node becomes closed
- **THEN** the very next selection pass admits the node without any extra transition

#### Scenario: ready set smaller than parallelism returns fewer actions
- **WHEN** one ready node exists and `max_parallelism` is four
- **THEN** exactly one action is returned and no unready node is backfilled

#### Scenario: multi-dependency node converges only when all dependencies close
- **WHEN** a node declares several dependencies and only some are closed
- **THEN** it stays blocked until the last one closes

### Requirement: dispatched work carries its dependency conclusions

A dispatched node's execution context MUST carry a `dependency_context`:
per dependency — node id, decision slot, question, status, and a
deterministic `conclusion_digest`. Dependency-free nodes MUST carry no
`dependency_context`.

#### Scenario: dispatched node receives dependency digests in context
- **WHEN** a node with dependencies is dispatched
- **THEN** each entry in its `execution_context.dependency_context` names the
  dependency and carries a digest that changes when the dependency's
  conclusion changes

### Requirement: slot dependencies gate downstream slot roots

The compiled slot-level `depends_on` MUST propagate into the research
state: a downstream slot's root nodes stay out of the ready set until the
upstream slot closes.

#### Scenario: downstream slot roots blocked until upstream slot closes
- **WHEN** slot B depends on slot A and slot A is still researching
- **THEN** `root:B` never appears in the selection output; once slot A is closed,
  `root:B` dispatches
