# ADR-003: Separate Graph Boundaries

Status: Accepted

## Context

Intent evolution, work dependencies, evidence relations, and implementation rollout have
different invariants. Treating them as one global research tree obscures authority and
makes pruning unsafe.

## Decision

Maintain separate structures for intent and brief lineage, the work dependency DAG,
typed evidence relations, and decisions-to-implementation. Exact ArtifactRefs connect
layers. A local Research Action Graph is a rebuildable projection, not canonical state.

## Consequences

Each graph can enforce its own cycle, supersession, and pruning rules. Cross-layer queries
require explicit lineage rather than implicit shared node identity.

## Rejected Alternatives

- One heterogeneous multigraph: incompatible invariants become runtime conventions.
- One static decision tree: evidence-driven growth and correction cannot be represented.

## Migration

Existing recursive tree artifacts remain historical projections. Canonical Slot, decision,
evidence, and delivery state is reconstructed from typed ledger artifacts.
