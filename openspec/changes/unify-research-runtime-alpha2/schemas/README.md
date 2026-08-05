# Alpha2 Contract Registry

This directory is the implementation and CI input for the alpha2 contract
specifications. The OpenSpec prose explains behavior; these files freeze the
wire shape used by Python validators, SQLite rows, host adapters, migration
tools, and release evidence.

## Registry

| File | Contract | Authority |
| --- | --- | --- |
| entity-envelope-v1.json | Common immutable artifact envelope | canonical runtime |
| input-record-v1.json | Typed user/repository/document/image/experiment intake | intake/acquisition |
| permission-profile-v1.json | Read/write/network/execute capability boundary | security/adapters |
| decision-slot-v1.json | Decision Slot and closure obligations | coordinator |
| research-action-v1.json | Policy-selected action proposal and score inputs | policy/coordinator |
| attempt-lease-v1.json | Work attempt and lease state | scheduler/coordinator |
| work-item-v1.json | Executable research assignment | scheduler/coordinator |
| evidence-artifact-v1.json | Immutable acquired evidence object | acquisition/evidence resolver |
| evidence-anchor-v1.json | Exact evidence selector | evidence resolver |
| oracle-spec-v1.json | Reproducible validation contract | oracle runner |
| oracle-attempt-v1.json | Exact OracleSpec/action-attempt execution binding | oracle runner/coordinator |
| oracle-run-v1.json | Executed validation result | oracle runner |
| slot-closure-assessment-v1.json | Closure token inputs and lifecycle | closure evaluator |
| p0-closure-aggregate-v1.json | Run-level aggregation of active P0 Slot tokens | closure evaluator/coordinator |
| host-event-v1.json | Cross-host event wire protocol | event ingestion |
| insight-digest-v1.json | Synthesized facts, gaps, and contradictions | insight service |
| research-run-v1.json | Canonical run state | coordinator |
| delivery-manifest-v1.json | Claim-to-lineage delivery index | delivery compiler |
| delivery-acceptance-v1.json | Exact-revision human acceptance | delivery service |
| alignment-message-v1.json | One-prompt alignment turn and response binding | alignment service |
| feedback-event-v1.json | Material post-handoff correction lineage | feedback/coordinator |
| readiness-record-v1.json | Field-level readiness and risk checks | readiness service |
| release-manifest-v1.json | Immutable release gate evidence | release evaluator |
| path-registry-v1.json | Repository path ownership and lifecycle | layout checker |
| examples/index-v1.json | Smallest valid, P0, and negative contract fixtures | contract harness |
| sqlite-v1.sql | Initial workspace ledger DDL and constraints | storage migration |
| compatibility-matrix.md | Alpha1 to alpha2 field and authority mapping | migration verifier |
| ../registries/legacy-field-map-v1.json | Field-level legacy import rules | migration verifier |

The companion registries freeze the lifecycle matrix, error catalog, host capability
negotiation, task execution metadata, delivery coverage, documentation authority,
evaluation paths, and repository paths. They are part of the same change and must
be validated together; a schema passing in isolation is not a release decision.

All schemas use JSON Schema 2020-12, reject unknown fields, and require
canonical UTF-8-without-BOM JSON hashing: NFC-normalized strings, sorted keys,
no insignificant whitespace, finite JSON numbers, and SHA-256 over the object
with its content_hash member omitted. A schema change requires a new version, a
compatibility row, a valid and invalid example, and a lossless migration or an
explicit rejection disposition.

## Legacy Mapping

| Alpha1 surface | Alpha2 disposition |
| --- | --- |
| round_id | compatibility alias mapped to run_id and lineage revision |
| filesystem RunStore | imported through migration tool; source remains digest-addressable |
| alignment SQLite | imported as alignment artifacts and event history; no independent completion writes |
| research-tree-state | projection only; coordinator owns Slot and run status |
| native/Hermes state.json | read-only import/projection; host events become canonical |
| human-brief | legacy delivery kind; imported as unverified and cannot satisfy acceptance |
| validation_result.status | observation only; OracleRun is authoritative |

## Validation

The implementation SHALL validate this directory in the same test command used
for runtime contract validation. Schema validation alone is insufficient:
examples must also pass domain invariants, lineage resolution, and transition
guards.
