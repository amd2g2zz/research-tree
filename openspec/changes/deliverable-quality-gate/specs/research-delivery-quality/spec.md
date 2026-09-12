## ADDED Requirements

### Requirement: delivery-pending requires a passing deliverable-quality review

A tree may not enter `delivery_pending` merely because draft report manifests
exist. A fresh-context deliverable-quality review — independent (identity
pair), bound to the exact manifest digests, with per-oracle verdicts — must
have passed for the current draft bytes.

#### Scenario: manifests without a quality review stay blocked
- **WHEN** both report manifests are registered and no quality review has passed
- **THEN** the tree status is `blocked` and the stop reason names the deliverable-quality gate as pending

#### Scenario: passing review flips delivery-pending
- **WHEN** a passing quality review bound to the current manifest digests is registered
- **THEN** the tree status is `delivery_pending` with the coordinator stop reason

#### Scenario: stale review is rejected
- **WHEN** a quality review's recorded digests do not match the current manifest digests
- **THEN** registration fails naming the mismatch, and the tree stays blocked

#### Scenario: non-independent review is rejected fail-closed
- **WHEN** the payload lacks `verifier_identity` or `session_context`
- **THEN** an `IndependentReviewError` naming the field is raised and no state changes

### Requirement: failed quality reviews reopen named remediation work

A failed review must convert every named gap into mandatory frontier work on
its target slot — not a pass-with-notes.

#### Scenario: named gaps become frontier remediation nodes
- **WHEN** a failed review with one unmet oracle and one named gap is registered
- **THEN** a mandatory remediation node exists on the target slot, the slot is reopened to `researching`, the gate records `failed` with the remediation node ids, and the tree status is `searching` with a stop reason naming the gap count

#### Scenario: a gap may revive a discarded node
- **WHEN** a named gap references a node recorded in `discarded_evidence`
- **THEN** that node returns to the frontier with its `terminal_reason` cleared and mandatory priority, and the registry entry is retained

### Requirement: pruned work stays queryable

Every node the pruner defers or marks duplicate is recorded in a
`discarded_evidence` registry with its terminal reason, oracle, evidence
need, slot, and selection value.

#### Scenario: pruned node is registered as discarded evidence
- **WHEN** the pruner defers a node (e.g. below selection threshold)
- **THEN** a `discarded_evidence` entry exists for it carrying `terminal_reason`, `decision_oracle`, `evidence_needed`, `decision_slot_id`, and `selection_value`

#### Scenario: registry entries are deduped per node
- **WHEN** the same node id would be recorded twice
- **THEN** only one entry exists

### Requirement: saturation requires measured coverage

A landscape-required slot cannot be declared evidence-saturated on novelty
alone when no batch comparison has ever been recorded for it.

#### Scenario: novelty zero without any comparison does not saturate
- **WHEN** a landscape-required slot has marginal novelty 0 and no recorded batch captures
- **THEN** `_slot_evidence_saturated` is False

#### Scenario: measured coverage still gates saturation
- **WHEN** a slot has a recorded comparison with `coverage_met = 0` and novelty 0
- **THEN** saturation stays False; with `coverage_met = 1` it becomes True
