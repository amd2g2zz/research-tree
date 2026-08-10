# ADR-003: Separate Graph Boundaries

Status: Accepted

## Context

Intent evolution, work dependencies, evidence relations, and implementation
rollout have different invariants. A single global graph hides authority and
makes correction, cycle detection, and pruning ambiguous.

## Decision

Maintain separate structures for intent/brief lineage, work dependency DAG,
typed evidence relations, and decisions-to-implementation. Exact
`ArtifactRef` lineage connects layers. A Research Action Graph is a local,
rebuildable projection for one Decision Slot; it is not canonical global state.

## Consequences

Each structure can enforce its own supersession, acyclicity, contradiction, or
rollout invariants. Cross-layer claims require explicit lineage rather than
implicit shared node identity.

## Rejected Alternatives

- One heterogeneous multigraph: incompatible invariants become informal runtime
  conventions.
- One static decision tree: it cannot represent evidence-triggered growth or
  material correction.

## Migration

Existing recursive tree artifacts remain historical projections. Canonical slot,
decision, evidence, and delivery state is reconstructed from typed ledger
artifacts.
