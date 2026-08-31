## ADDED Requirements

### Requirement: The runtime carries no compatibility shims

The package `src/research_tree` SHALL NOT contain compatibility shims of any
kind: no legacy vocabulary sets or status translation maps, no rename maps
between field and obligation names, no sentinel evidence-class branches, no
dual-schema payload acceptance, no non-canonical ingress wrappers in front of
a canonical entry point, and no old-workspace auto-migration machinery. The
grep gate `grep -rniE "legacy" src/research_tree --include="*.py"` SHALL
return no matches.

#### Scenario: Retired-word grep gate stays empty

- **WHEN** maintainers run `grep -rniE "legacy" src/research_tree --include="*.py"`
- **THEN** the command reports zero matches (exit status 1)

#### Scenario: Single obligation name at the single source

- **WHEN** completion obligations or the causal trace service report an unmet
  completion input
- **THEN** the reported name is the completion-manifold field name itself,
  with no rename map between the field and the obligation

#### Scenario: One canonical HostEvent ingress

- **WHEN** a caller submits a host event to the research run coordinator
- **THEN** only the canonical `ingest_host_event` entry point exists, and a
  non-mapping event is rejected by the HostEvent envelope validation

### Requirement: Payload validation accepts the current schema only

Readiness record payloads SHALL validate against the current schema only:
`technical_package_ref`, `delivery_readiness`, `diagnostics`,
`repository_anchor_checks`, `source_refs`, and `risk_verification` are all
required, and every diagnostic entry SHALL carry `failure_category`. Human
deliveries SHALL declare only the canonical kind. Evidence artifacts SHALL
resolve, close, and publish only with explicit, current evidence classes; no
sentinel class value is special-cased.

#### Scenario: Stale readiness record is rejected

- **WHEN** a readiness record payload is missing `risk_verification` (or a
  diagnostic entry is missing `failure_category`)
- **THEN** readiness validation raises an unexpected-keys error naming the
  missing fields

#### Scenario: Non-canonical human delivery kind is rejected

- **WHEN** semantic delivery validation receives a human delivery whose kind
  is not the canonical human-research-report kind
- **THEN** validation raises the single non-canonical-kind acceptance error

### Requirement: Canonical state regions project without a translation table

`self_state` SHALL project the five orthogonal regions from the canonical
lifecycle state recorded in the state payload, with no single-string state
translation table and no silent default for unmapped states. States without a
canonical region projection SHALL fail closed.

#### Scenario: Unknown state fails closed

- **WHEN** `self_state` encounters a state without a canonical region
  projection
- **THEN** the coordinator raises `IllegalTransitionError` instead of
  silently projecting a different state's regions

### Requirement: Run workspaces initialize without auto-migration

`initialize_project_run` SHALL NOT inspect, reject, or migrate old-format run
workspace roots; run roots contain only the current run directories, and the
run manifest SHALL NOT carry a migrated-roots record.

#### Scenario: Initialize on a repository with old-format workspace roots

- **WHEN** `initialize_project_run` runs in a repository that still contains
  old-format roots
- **THEN** the new run workspace is created under the current project/run
  authority and the old roots are left untouched on disk

#### Scenario: Breaking change is documented

- **WHEN** an operator reads the README Quick Start
- **THEN** a breaking-change note states that run workspaces created by
  previous releases are no longer migrated automatically and must be recreated
  or migrated manually
