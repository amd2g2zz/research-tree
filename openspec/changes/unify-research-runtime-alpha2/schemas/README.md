# Alpha2 Contract Registry

This directory is the implementation and CI input for the alpha2 contract
specifications. The OpenSpec prose explains behavior; these files freeze the
wire shape used by Python validators, SQLite rows, host adapters, and release
evidence.

## Registry

| File | Contract | Authority |
| --- | --- | --- |
| entity-envelope-v1.json | Common immutable artifact envelope | canonical runtime |
| input-record-v1.json | Typed user/repository/document/image/experiment intake | intake/acquisition |
| permission-profile-v1.json | Read/write/network/execute capability boundary | security/adapters |
| decision-slot-v1.json | Decision Slot and closure obligations | coordinator |
| research-action-v1.json | Policy-selected action proposal and score inputs | policy/coordinator |
| search-portfolio-v1.json | Intent-derived subquestions, query rewrites, method boundaries, and reassessment policy | acquisition/coordinator |
| attempt-lease-v1.json | Work attempt and lease state | coordinator |
| work-item-v1.json | Executable research assignment | coordinator |
| source-capture-v1.json | Immutable raw acquisition capture | acquisition/CAS |
| acquisition-receipt-v1.json | Durable acquisition outcome and provider lineage | acquisition/CAS |
| analysis-checkpoint-v1.json | Bounded resumable analysis state without private reasoning | worker/coordinator |
| evidence-artifact-v1.json | Immutable acquired evidence object | acquisition/evidence resolver |
| evidence-anchor-v1.json | Exact evidence selector | evidence resolver |
| oracle-spec-v1.json | Reproducible validation contract | oracle runner |
| oracle-run-v1.json | Executed validation result | oracle runner |
| slot-closure-assessment-v2.json | Replayable graph-derived closure assessment | closure evaluator |
| host-event-v1.json | Cross-host event wire protocol | event ingestion |
| native-workflow-run-v1.json | Non-authoritative host workflow projection | host adapter/coordinator |
| preference-observation-v1.json | Privacy-bounded project preference evidence | alignment/coordinator |
| user-preference-profile-v1.json | Hysteretic project preference read model | alignment/coordinator |
| insight-digest-v1.json | Complete versioned insight lineage, deltas, signals, and actions | insight service |
| research-run-v1.json | Canonical run state | coordinator |
| delivery-manifest-v1.json | Claim-to-lineage delivery index | delivery compiler |
| delivery-acceptance-v1.json | Exact-revision human acceptance | delivery service |
| alignment-message-v1.json | One-prompt alignment turn and response binding | alignment service |
| feedback-event-v1.json | Material post-handoff correction lineage | feedback/coordinator |
| correction-event-v1.json | Exact revision-bound material correction/reopen control event | feedback/coordinator |
| readiness-record-v1.json | Field-level readiness and risk checks | readiness service |
| release-manifest-v1.json | Immutable release gate evidence | release evaluator |
| path-registry-v1.json | Repository path ownership and lifecycle | layout checker |
| examples/index-v1.json | Smallest valid, P0, and negative contract fixtures | contract harness |
| sqlite-v1.sql | Initial workspace ledger DDL and constraints | storage schema |

The companion registries freeze the lifecycle matrix, error catalog, host capability
negotiation, task execution metadata, delivery coverage, documentation authority,
evaluation paths, and repository paths. They are part of the same change and must
be validated together; a schema passing in isolation is not a release decision.

All schemas use JSON Schema 2020-12, reject unknown fields, and require
canonical UTF-8-without-BOM JSON hashing: NFC-normalized strings, sorted keys,
no insignificant whitespace, finite JSON numbers, and SHA-256 over the object
with its content_hash member omitted. A schema replacement removes the prior
active schema and examples; no compatibility row, compatibility reader, or
migration path is retained.

## Validation

The implementation SHALL validate this directory in the same test command used
for runtime contract validation. Schema validation alone is insufficient:
examples must also pass domain invariants, lineage resolution, and transition
guards.
