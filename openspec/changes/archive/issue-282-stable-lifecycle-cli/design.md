# Design

## Stable boundary

The public parser only advertises the six lifecycle verbs. `run` creates a
canonical ledger run, appends an immutable lifecycle request, and creates a
project-scoped hook configuration. Users pass normal paths and text fields;
they never provide a HostEvent envelope or a database path.

Each public response has `schema_version: 1`, the contract name, command,
status, run identity with `authority_revision`, readiness data, completion
authority, and command result. `status` reconstructs this projection from the
ledger and project workspace rather than trusting a visible todo list.

## Authority and verification

The lifecycle request is deliberately non-authoritative. Its readiness remains
false until separate aligned authority, oracle evidence, and independent
reviewer receipts reach the canonical coordinator. `verify` returns a pending
receipt and a nonzero status while those obligations are absent. No public
command invokes coordinator completion.

## Compatibility

The former raw coordinator verbs remain available only below `research-tree
internal --acknowledge-internal-contract coordinator`. This lets repository
maintenance preserve low-level regression coverage without presenting internal
storage and HostEvent schemas as a supported host lifecycle interface.

## Cross-host distribution

The generated Codex, Claude Code, and Hermes instructions use the same six
verbs when the checkout runtime is available. Their native adapters remain the
host-specific execution boundary; neither adapter can turn a stable CLI receipt
into completion.
