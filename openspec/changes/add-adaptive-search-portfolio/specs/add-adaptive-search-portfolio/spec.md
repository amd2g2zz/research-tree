# add-adaptive-search-portfolio Specification Delta

## ADDED Requirements

### Requirement: Plans fan out across every distinct available provider

The intent-derived portfolio planner SHALL select every registered
method/provider boundary whose availability is not `unavailable` (registry
availability semantics unchanged) and SHALL fail closed when a produced plan
does not cover every distinct available provider. Each plan SHALL expose
`provider_fanout`: the count of distinct available providers it fans out
across.

#### Scenario: Two available providers fan out into one batch

- **WHEN** the registry declares two distinct providers available for the
  intent
- **THEN** the plan selects both providers and `provider_fanout` is `2`

#### Scenario: Unavailable providers are neither selected nor counted

- **WHEN** a registered provider is marked `unavailable`
- **THEN** the plan does not select it and `provider_fanout` excludes it,
  while a `degraded` provider remains selectable and counted

### Requirement: Batch cross-comparison measures outcomes across providers

After each portfolio batch, the cross-comparison stage SHALL deduplicate
captured results through the provenance-clustering upstream identity reused
from `research_tree.claims`, score per-provider relevance against the intent
terms, and write measured `novelty`, `coverage`, `source_quality`, and
`contradictions` back into the batch's `MethodExecutionOutcome` fields.
Captures with no declared identity SHALL be rejected rather than silently
clustered.

#### Scenario: Same URL captured via two providers collapses to one identity

- **WHEN** two providers capture results resolving to the same upstream
  identity
- **THEN** the comparison reports a single upstream identity group, the later
  capture is tagged as a duplicate of the origin provider, and
  `dedup_ratio` measures the duplicate share

#### Scenario: Measured values replace placeholder outcome fields

- **WHEN** the stage is applied to a batch
- **THEN** each measured outcome carries measured novelty, coverage,
  source quality, and content-conflict contradictions, and outcomes without
  captures are left unchanged

### Requirement: Recursion continues on evidence signals and stops early inside the guardrail

The recursive search SHALL continue only while an unresolved contradiction
exists, a coverage gap vs the intent remains, or marginal novelty is above
the declared threshold; otherwise it SHALL defer remaining optional actions
with `terminal_reason` `evidence-saturated`. A declared transition budget,
when consumed while signals still say continue, SHALL report
`budget-exhausted`. The `max_depth` guardrail SHALL keep its value, its
first-position ordering, its mandatory-node exemption, and the exact string
`maximum depth guardrail reached` as the unchanged hard backstop.

#### Scenario: Saturated search stops before the guardrail

- **WHEN** a search batch reports no novelty, no contradictions, and coverage
  is met while optional frontier actions remain within `max_depth`
- **THEN** the optional actions are deferred with `evidence-saturated` and
  the receipt's `terminal_reason_distribution` records the stop

#### Scenario: Live contradictions still reach the hard guardrail

- **WHEN** a slot accumulates unresolved contradictions across transitions
- **THEN** the descent continues until a node exceeds `max_depth` and is
  deferred with exactly `maximum depth guardrail reached`

### Requirement: Recursion confidence damps with measured quality

Each evidence ingest SHALL measure `expandability`, `completeness`,
`heuristic_value`, and `implicit_association` with declared weights recorded
in the receipt, and SHALL compute
`confidence(child) = confidence(parent) * (1 - damping)` where
`damping = d_min + (d_max - d_min) * (1 - quality)` stays inside the declared
band and is always positive, so confidence descends monotonically and never
increases through recursion.

#### Scenario: Quality separates damping at equal depth

- **WHEN** a high-quality ingest and a low-quality ingest expand nodes at the
  same depth
- **THEN** the high-quality child shows strictly smaller damping and strictly
  higher confidence than the low-quality child, both dampings within the
  declared band

### Requirement: Low-confidence evidence is quarantined until independently corroborated

A finding whose ingest confidence falls below the declared threshold SHALL be
quarantined from satisfied evidence, SHALL be excluded from slot minimum
evidence (findings and anchors), and SHALL remain quarantined until a trusted
independent finding shares one of its anchors or an explicit verification
pass clears it. Verification failures SHALL be recorded objectively with
attempts and reason and counted in the receipt; none shall be dropped
silently.

#### Scenario: Quarantined findings cannot satisfy evidence

- **WHEN** a slot's trusted findings or trusted anchors fall below the
  minimum because of quarantine
- **THEN** the slot reports insufficient independent evidence and cannot
  close

#### Scenario: Verification failure is recorded

- **WHEN** a cross-validation attempt fails for a quarantined finding
- **THEN** the cross-validation record stores `failed` with the attempt count
  and reason, the finding stays quarantined, and the receipt's
  `cross_validation_failures` counts it

### Requirement: Runs expose falsifiable recursion receipts

Every research state SHALL carry a `recursion_receipt` exposing per-run
provider fan-out count, dedup ratio, `terminal_reason_distribution`,
confidence distribution with declared damping parameters and quality
weights, quarantine count, and cross-validation failure count, so a run whose
stop reasons are all `maximum depth guardrail reached` is directly visible as
a strategy failure.

#### Scenario: Guardrail-only termination is visible

- **WHEN** every deferred node in a run stopped at the depth guardrail
- **THEN** the receipt's `terminal_reason_distribution` contains only
  `maximum depth guardrail reached` entries
