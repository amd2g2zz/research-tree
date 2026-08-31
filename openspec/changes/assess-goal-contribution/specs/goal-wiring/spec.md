# Goal Wiring Specification

## ADDED Requirements

### Requirement: Coordinator assesses goal contribution on accepted Finding Pack ingestion

Every compile-passed Finding Pack MUST be classified by the coordinator against the slot
it serves and the run's confirmed StrategyProjection. The verdict enum is
`advances / partial / no_contribution / contradicts` and the assessment artifact
(`goal-contribution-assessment`) MUST carry exact lineage: `finding_pack_id`,
`finding_pack_revision`, `slot_id`, `projection_id`, `projection_revision`,
`projection_digest`, `verdict`, `reason`, with `parent_refs = (finding_pack,
strategy_projection)`. Worker-supplied confidence MUST NOT be an input to the verdict.

#### Scenario: Compile-passed pack is assessed with exact lineage

- **WHEN** a Finding Pack passes strict compile in a run with a confirmed projection
- **THEN** a goal-contribution-assessment artifact is appended with the finding pack,
  slot, and projection digest lineage and `parent_refs = (finding_pack, strategy_projection)`

#### Scenario: High confidence without effects is no contribution

- **WHEN** a pack carries high worker confidence but its effects and claims touch
  neither the slot alternatives nor the served evidence standards
- **THEN** the verdict is `no_contribution` and the reason does not mention confidence

#### Scenario: Truth table short-circuits in order

- **WHEN** a pack is classified
- **THEN** a contradicts effect on a slot alternative yields `contradicts` even alongside
  a supports effect; a supports effect on a slot alternative or a corroborated claim
  yields `advances`; effects, claims, or validation that only touch the served slot
  yield `partial`; anything else yields `no_contribution`

#### Scenario: Unverifiable serves wiring fails closed

- **WHEN** the slot's `serves.target_id` or `serves.oracle_ids` does not resolve against
  the confirmed projection's decision targets or success oracles
- **THEN** the verdict is `no_contribution` naming the unverifiable serves field

#### Scenario: Run without a confirmed projection is not assessed

- **WHEN** the run has no confirmed StrategyProjection
- **THEN** no assessment is appended and ingestion keeps its prior behavior

### Requirement: Blocking verdicts are excluded from tree consumption

`no_contribution` and `contradicts` packs MUST NOT enter the tree transition consumed
set; `advances` and `partial` packs keep the prior consumption behavior. Restart
recovery MUST honor the recorded verdicts as well.

#### Scenario: No contribution pack is excluded from consumed findings

- **WHEN** an advancing pack and a no_contribution pack are ingested together
- **THEN** the tree state consumed set contains only the advancing pack
- **AND** restart recovery does not resurrect the excluded pack

### Requirement: Blocking verdicts trigger a slot-granularity guidance retry

A blocking verdict MUST record a same-round replan naming the affected slot and the
guidance defect, and MUST compile a successor Work Item with adjusted guidance that
records the defect. The replan payload whitelist MUST accept the slot-granularity keys
`affected_slot_ids` and `guidance_defect`.

#### Scenario: Retry successor records the guidance defect

- **WHEN** a pack is judged `no_contribution`
- **THEN** a same-round replan is recorded with `affected_slot_ids: [<slot_id>]` and
  `guidance_defect: <reason>`
- **AND** a successor Work Item exists for the slot carrying `guidance_defect` and the
  defect inside its adjusted guidance text
- **AND** the first retry does not carry `redecomposition_flagged`

#### Scenario: Same-round replan accepts slot granularity

- **WHEN** `record_same_round_replan` is called with `affected_slot_ids` and
  `guidance_defect`
- **THEN** the persisted replan payload carries both values
- **AND** a legacy call without them still validates with empty/default values

### Requirement: The second consecutive no_contribution escalates to method switch

The escalation counter MUST follow the trailing `no_contribution` run of the slot's
assessment chain (append order). The second consecutive `no_contribution` MUST consult
the scheduling policy with a `method_switch` deficit (ADR-006) and MUST flag the
successor item `redecomposition_flagged: true`.

#### Scenario: Second no contribution triggers method switch and re-decomposition flag

- **WHEN** a second consecutive `no_contribution` is recorded for the same slot
- **THEN** the successor Work Item carries `redecomposition_flagged: true`,
  `policy_proposal_kind: method_switch`, and a `policy_proposal_id`
- **AND** each retry still records the slot-granularity replan with the guidance defect
- **AND** the first retry remains a plain guidance adjustment
