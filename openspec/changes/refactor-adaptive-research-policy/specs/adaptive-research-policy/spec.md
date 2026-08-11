## ADDED Requirements

### Requirement: Policy produces bounded evidence-bound proposals

The runtime SHALL provide a host-neutral `AdaptiveResearchPolicy` that accepts
only normalized Decision Slot deficits, verified evidence references, Insight
Digest signals, prior outcomes, a versioned configuration, and a deterministic
seed. It SHALL produce only `landscape`, `deep_dive`, `adversarial`,
`validation`, or `method_switch` proposals, or a retained explicit deferral or
rejection. Every proposal SHALL name its Slot, evidence trigger or deficit,
missing dimension, method boundary, closure oracle, score components, and
causal references. Generic worker suggestions without a verified trigger SHALL
be rejected.

#### Scenario: No evidence covers an open Slot
- **WHEN** a normalized open Decision Slot has no verified evidence coverage
- **THEN** the policy returns a bounded landscape proposal with required
  evidence classes and an exact closure oracle

#### Scenario: Worker-only suggestion is submitted
- **WHEN** a proposed branch has no verified deficit or evidence reference
- **THEN** the policy returns a rejection disposition and creates no action

### Requirement: Policy replay and pruning are deterministic

The policy SHALL derive selection order from policy version, configuration,
canonical input digest, and seed. It SHALL retain score components,
normalization, tie-break value, and optional duplicate/dominance disposition in
its audit trace. P0 validation, counterevidence, and unresolved contradictions
SHALL remain eligible regardless of frontier capacity or optional-action score.

#### Scenario: Identical inputs are replayed
- **WHEN** the policy is evaluated twice with the same version, configuration,
  normalized input digest, and seed
- **THEN** selected and deferred identifiers, scores, tie-break order, and
  reasons are identical

#### Scenario: Mandatory validation has low optional score
- **WHEN** a P0 Slot requires validation but its optional score is low
- **THEN** the validation proposal remains eligible and is not score-pruned

### Requirement: Realized delta is six-component and attributable

The policy SHALL compare immutable baseline and current state for
evidence-class coverage, provenance independence, contradiction state, oracle
state, implementation uncertainty, and Slot-closure change. The comparison
SHALL identify the references and contribution for each component. A historical
baseline or repeated state SHALL produce zero realized delta and a no-change
penalty rather than an expansion trigger.

#### Scenario: Repeated evidence is ingested
- **WHEN** current evidence and lineage match the baseline for all components
- **THEN** the delta is zero and the trace records a no-change penalty

### Requirement: Compatibility projection cannot close research

Legacy recursive-search compatibility APIs SHALL project policy proposals,
deferrals, or blockers only. They SHALL NOT write canonical Slot status,
delivery, or run completion and SHALL NOT treat a worker return, empty
frontier, task count, report presence, report byte count, or heading count as
successful completion.

#### Scenario: Frontier drains with closure obligations
- **WHEN** a legacy projection has no executable local action and an open
  closure obligation remains
- **THEN** it returns a blocker, fallback, or method-switch proposal and does
  not mark a Slot or run complete
