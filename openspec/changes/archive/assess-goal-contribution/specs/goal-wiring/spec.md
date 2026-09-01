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
  a supports effect; a supports effect on a slot alternative yields `advances`; a
  corroborated claim yields `advances` only when its evidence actually grounds a served
  oracle's evidence standard — the verdict intersects the served oracles'
  `evidence_standard_ids` with the claim's grounding identities, provenance clusters,
  and grounding evidence artifact ids; effects on slot alternatives, claims whose
  evidence maps to a served oracle, or validation against the slot yield `partial`;
  a pack that touches none of these fails closed to `no_contribution`

#### Scenario: Unmapped corroborated claim never advances

- **WHEN** a pack's corroborated claim carries grounding evidence that names none of the
  served oracles' evidence standards, and nothing else in the pack touches the served
  slot (no effect on a slot alternative, no mapped claim, no validation result)
- **THEN** the verdict is `no_contribution` (rule 4 touch judgment), never `advances`,
  and the reason describes the executed mapping check instead of asserting one

#### Scenario: Unverifiable serves wiring fails closed

- **WHEN** the slot's `serves.target_id` or `serves.oracle_ids` does not resolve against
  the confirmed projection's decision targets or success oracles
- **THEN** the verdict is `no_contribution` naming the unverifiable serves field

#### Scenario: Run without a confirmed projection is not assessed

- **WHEN** the run has no confirmed StrategyProjection
- **THEN** no assessment is appended and ingestion keeps its prior behavior

### Requirement: Blocking verdicts are excluded from tree consumption

`no_contribution` and `contradicts` packs MUST NOT enter the tree transition consumed
set; `advances` and `partial` packs keep the prior consumption behavior. In a run with
a confirmed projection, a pending pack with no recorded assessment MUST be deferred as
well (fail closed): the compile hook assesses every compile-passed pack, so a missing
assessment means the hook was interrupted, and the pack stays pending with a visible
reason instead of being waved into the consumed set. Runs without a confirmed
projection keep the prior behavior (every pack contributes). Restart recovery MUST
honor the recorded verdicts and the unassessed fail-closed rule as well.

#### Scenario: No contribution pack is excluded from consumed findings

- **WHEN** an advancing pack and a no_contribution pack are ingested together
- **THEN** the tree state consumed set contains only the advancing pack
- **AND** restart recovery does not resurrect the excluded pack

#### Scenario: Unassessed pending pack is deferred, not consumed

- **WHEN** a pending pack has no goal-contribution-assessment record in a run with a
  confirmed projection
- **THEN** the pack is deferred (stays pending, never enters the consumed set) and the
  deferral is logged
- **AND** restart recovery does not launder the unassessed pack into consumption either

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
assessment chain (append order) after deduplication by logical pack identity: only the
latest assessment per finding pack id participates, so recompiling the same finding at
revision+1 never double-counts the streak. The second consecutive `no_contribution`
MUST consult the scheduling policy with a `method_switch` deficit (ADR-006) exactly
once per slot and MUST flag the successor item `redecomposition_flagged: true`. The
policy consult MUST be reachable on every wired path: when the caller (e.g. the ledger
compile hook's bare coordinator) injects no policy, the consult falls back to a default
`AdaptiveResearchPolicy` (local to the consult; the coordinator is never mutated).
Third and further verdicts in the streak MUST still record the slot-granularity replan
and a retry successor, but never repeat the consult or the flag.

#### Scenario: Second no contribution triggers method switch and re-decomposition flag

- **WHEN** a second consecutive `no_contribution` is recorded for the same slot
- **THEN** the successor Work Item carries `redecomposition_flagged: true`,
  `policy_proposal_kind: method_switch`, and a `policy_proposal_id`
- **AND** each retry still records the slot-granularity replan with the guidance defect
- **AND** the first retry remains a plain guidance adjustment

#### Scenario: Hook path consults the policy without manual injection

- **WHEN** the ledger compile hook's bare `ResearchRunCoordinator(ledger)` records a
  second consecutive `no_contribution` for a slot with no prior method_switch consult
- **THEN** the successor carries a `policy_proposal_id` — the consult ran on the
  injected policy, or a default policy when none was injected

#### Scenario: Method switch escalation is one-shot per slot

- **WHEN** a third or later consecutive `no_contribution` follows an already recorded
  method_switch consult for the slot
- **THEN** the retry successor stays a plain guidance adjustment: the repeated
  `policy_proposal_id`, the repeated `policy_proposal_kind: method_switch`, and the
  repeated `redecomposition_flagged` marker are all suppressed
- **AND** the slot-granularity replan with the guidance defect is still recorded

#### Scenario: Streak deduplication by logical pack identity

- **WHEN** the same finding is recompiled at revision+1 and reassessed as
  `no_contribution`
- **THEN** the streak counts the finding once (its latest assessment supersedes the
  superseded revision's assessment) and does not escalate on the recount

#### Scenario: Streak counters are slot-scoped and verdict-interrupted

- **WHEN** slot A records a second consecutive `no_contribution` while slot B records
  its first, or an `advances` verdict lands between two `no_contribution` verdicts of
  one slot
- **THEN** slot B's retry stays a plain guidance adjustment and the interrupted slot's
  counter restarts from zero (escalation again requires two fresh consecutive
  `no_contribution` verdicts)
