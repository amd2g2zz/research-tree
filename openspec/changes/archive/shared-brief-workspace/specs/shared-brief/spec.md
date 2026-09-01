## ADDED Requirements

### Requirement: Shared Brief workspace is durable and auditable
A BriefWorkspace records requester / agent / shared nodes, reconciliation edges, and per-node evidence links. A SharedBrief projection surfaces only consensus items as the Shared Forest; unresolved deltas remain visible but outside consensus.

#### Scenario: consensus hides unresolved
- **WHEN** a reconciliation edge is unresolved
- **THEN** the SharedBrief projection does NOT include it in consensus_mappings but does include it in unresolved_mappings

#### Scenario: evidence chain is per node
- **WHEN** record_evidence_link is called for a node
- **THEN** the workspace evidence_chain contains an entry with that node_id and the supplied evidence_refs
