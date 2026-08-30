# Proposal: shared-brief-workspace

## Why

issue #321: the cognitive spaces need a durable artifact boundary.  A single
mutable brief cannot prove how requester and Agent forests changed, what
evidence was added, or why a node entered the Shared Forest.

## What Changes

NEW `src/research_tree/shared_brief.py`:
- `BriefNode`: space/identity/role/source/timestamp/version/body
- `EvidenceLink`: per-node audit chain
- `BriefWorkspace`: mutable workspace with requester/agent/shared buckets,
  reconciliation edges, and an evidence_chain list
- `SharedBrief.from_workspace(...)`: read-only projection — consensus nodes +
  consensus mappings + visible unresolved deltas (issue: Shared Forest only
  aligned; unresolved live outside but visible)
- `append_node` / `record_evidence_link`: workspace mutation helpers
- `to_dict()`: canonical serialization (used by humans/agents for audit)

## Impact

- src/research_tree/shared_brief.py (new)
- No behavior change to existing modules

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| Node carries space/identity/role/source/timestamp/version | test_brief_node_carries_space_identity_role_source_timestamp_version |
| Evidence chain records per node | test_append_node_records_evidence_chain |
| Consensus hides unresolved | test_shared_brief_hides_unresolved_deltas |
| Consensus only includes resolved mappings | test_consensus_brief_only_includes_resolved_mappings |
| Workspace serializes canonically | test_brief_workspace_to_dict_is_canonical |
