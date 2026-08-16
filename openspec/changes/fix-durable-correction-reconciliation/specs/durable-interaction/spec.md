## ADDED Requirements

### Requirement: Corrections invalidate dependent durable action statuses atomically

The durable interaction controller SHALL reduce a correction before publishing its successor and SHALL remove only persisted action IDs that disappeared from semantic pending actions during that correction transition in the same revisioned mutation.

#### Scenario: A correction invalidates one started action

- **WHEN** a correction removes a dependent action from semantic state while another started action remains authorized
- **THEN** the persisted action map omits the invalidated action, retains the unrelated action as `started`, and publishes the repair state at one new revision

### Requirement: Unrelated action statuses are preserved

Durable action reconciliation SHALL preserve the exact existing status of every action ID not invalidated by the reconciled semantic transition, including tracked execution IDs that are not semantic action strings. It SHALL NOT add a second action-completion or action-authorization authority.

#### Scenario: Reconciliation sees unrelated work

- **WHEN** a correction removes one dependent action and leaves another action authorized
- **THEN** the unrelated action's status and identifier are unchanged

### Requirement: Recovery cannot restore a correction-invalidated action

Checkpoint recovery SHALL NOT restore an action status invalidated by a correction transition after the checkpoint. Recovery SHALL preserve other checkpointed execution statuses, except that `started` becomes `unknown`, and SHALL fail closed if post-checkpoint episode names or correction payloads needed to preserve this boundary are malformed.

#### Scenario: Recovery selects a checkpoint before the correction

- **WHEN** recovery restores a checkpoint made immediately before a later correction that invalidated a started action
- **THEN** the invalidated action is absent from durable pending actions while unrelated checkpointed action state remains recoverable

### Requirement: Correction replay is idempotent for durable action authority

Submitting the same correction event again SHALL either deterministically retain the reconciled state or be rejected as stale. It SHALL NOT restore an action removed by the earlier correction.

#### Scenario: The same correction event ID is submitted twice

- **WHEN** the duplicate submission is accepted at the current revision or rejected as stale
- **THEN** semantic state and persisted action authority both continue to omit the invalidated action
