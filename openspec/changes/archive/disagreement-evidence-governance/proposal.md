# Proposal: disagreement-evidence-governance

## Why

issue #317: dispute disposition was determined by social pressure and repeated assertions rather than evidence quality or independent validation. Pressure-resistant governance is required.

## What Changes

NEW `src/research_tree/dispute.py`:
- `PressureSignal` StrEnum: independent_validation / evidence_quality_change / assumption_change / social_pressure / repeat_assertion.
- `DISPOSITION_PRECEDENCE` table: independent_validation > evidence_quality_change > assumption_change > social_pressure > repeat_assertion.
- `PressureLedger`: append-only audit of pressure events per claim.
- `DisputePacket` frozen dataclass: claim_id + signals + evidence + audit_trail.
- `evaluate_dispute(packet) -> DisputeDisposition` raises `DisputeDispositionError` on invalid input.
- `coordinator.ingest_pressure_signal(...)` accepts signals and routes through evaluate_dispute.

## Impact

src/research_tree/dispute.py (new). Pressure-resistant: only evidence + independent validation rank above social pressure. Audit trail preserved.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| precedence table order is enforced | test_pressure_precedence_table_order |
| evaluate_dispute raises on unknown signal | test_evaluate_dispute_raises_on_unknown_signal |
| PressureLedger append-only | test_pressure_ledger_append_only |
| independent_validation ranks above evidence | test_independent_validation_ranks_above_evidence |
| social_pressure does not flip disposition alone | test_social_pressure_does_not_flip_disposition |
| audit_trail preserves per-signal entries | test_audit_trail_preserves_per_signal |
