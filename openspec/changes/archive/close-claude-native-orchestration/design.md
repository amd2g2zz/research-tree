# Close Claude Native Orchestration

## Decisions

- Claude probes expose `claude-agent-children`, `claude-native-workflow`, and
  `claude-hybrid-workflow` independently. Agent availability never implies
  Workflow or hybrid availability.
- A projection names its selected `execution_mode` and the capability evidence.
  Agent requires real child delegation; Workflow requires native dynamic phases;
  hybrid requires both a workflow phase identity and bounded child delegation.
- Installed hooks preserve only opaque identity fields, never prompts, tool
  inputs, transcripts, secrets, or child summaries. Missing identity is recorded
  as `unknown_outcome`; it never creates completion.
- `start` creates the canonical attempt before native dispatch. `bind-agent`
  then binds the exact host-returned `agent_id`, session, and causation identity
  to that active attempt. One agent identity cannot bind another attempt.
- Claude Finding Pack submission requires an active exact identity binding and
  the existing attempt/digest/anchor checks. Recovery and status remain
  coordinator-authoritative.

## Verification

Deterministic tests cover identity preservation, unmatched identity, duplicate
identity, mode selection, fallback, faults, and non-completion. A live Claude
2.1.207 stream must show two distinct child identities bound to two attempts.
Workflow and hybrid are claimed only from live surface receipts; otherwise their
exact unavailability is recorded.
