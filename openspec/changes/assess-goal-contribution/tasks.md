# Assess Goal Contribution — Tasks

## 1. Red Tests

- [x] 1.1 Add `tests/test_goal_contribution.py` with the named B2 contract tests:
      verdict truth table (advances/partial/no_contribution/contradicts), high
      confidence without effects, excluded from tree consumption, retry successor
      guidance defect, second no_contribution triggers method_switch, replan slot
      granularity.

## 2. Pure Truth Table

- [x] 2.1 Add coordinator module-level `assess_goal_contribution(pack, slot,
      projection) -> (verdict, reason)` with the short-circuit truth table and the
      confidence hard rule; `no_contribution` fail-closed on unverifiable serves wiring.

## 3. Assessment Artifact + Ingestion Wiring

- [x] 3.1 Append the `goal-contribution-assessment` artifact in the compile acceptance
      flow (after the existing contradiction hook), with exact lineage and
      `parent_refs = (finding_pack, strategy_projection)`.
- [x] 3.2 Split candidate packs into contributing/deferred at tree consumption via
      `partition_goal_contributions` consulted by recursive ingest and restart
      recovery; runs without a confirmed projection keep prior behavior.

## 4. Guidance-Adjust Retry and Escalation

- [x] 4.1 Extend `record_same_round_replan` (feedback service + coordinator) with
      slot-granularity payload keys `affected_slot_ids` and `guidance_defect`,
      validator accepting both as optional keys.
- [x] 4.2 Compile a successor Work Item with adjusted guidance recording the defect;
      second consecutive `no_contribution` consults the policy with a `method_switch`
      deficit and flags the successor `redecomposition_flagged: true`.

## 5. Gates

- [x] 5.1 Run the full gate battery: pytest, ruff check/format, package check,
      openspec strict validation, docs and repository layout checks.

## 6. Review Fixes (alpha3 batch-3)

- [x] 6.1 Make the method_switch consult reachable on the only wired path: the
      consult falls back to a default `AdaptiveResearchPolicy` when the caller
      injects none (the ledger compile hook constructs a bare coordinator).
- [x] 6.2 Enforce rule 3/4 oracle mapping: corroborated claims advance only when
      their evidence tokens intersect a served oracle's `evidence_standard_ids`;
      unrelated packs fail closed to `no_contribution`.
- [x] 6.3 Fail the partition closed for packs without an assessment in
      confirmed-projection runs (defer + log; recovery honors it).
- [x] 6.4 Cap the method_switch escalation at one consult per slot and deduplicate
      the streak by logical pack identity; lock cross-slot isolation and
      advances-interrupt reset with tests.
