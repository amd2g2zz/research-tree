# Proposal: transformation-trace

## Why

issue #499 (confirmed, code-verified): every validator enforces shape, not
substance — a Finding Pack whose observations paste README text and a Human
Brief whose interpretation forwards a doc snippet both pass; viewpoints exist
only in the delivery document, so mid-research user turns carry no
composition requirement. Per the 2026-09-03 shape note under #501: this
becomes contract traces, not a standalone validator — and explicitly NOT
quote-ratio regex policing.

## What Changes

1. Registry grows the mid-research user-update trace types:
   `digest-first` (point + decision_relevance + source_pointer) and
   `viewpoint-hints` (alternatives, reusing the material_alternatives /
   trade_off schema shape). Presence+schema only.
2. Finding Pack ingestion carries an optional but strictly-validated
   `transformation` record ({ratio: numeric in [0,1]}); the per-observation
   anchor citation that makes observations "agent-phrased with anchors" is
   already enforced by the strict EvidenceAnchor normalization.
3. The #493 turn-shape `transformation_ratio` slot is documented as
   composer-reported until #500 wires the required digest-first trace for
   user-facing mid-research updates.

## Impact

- turn_contract.py: two append-only registry entries (six → nine types across
  #498/#499).
- ledger.py: one optional compile parameter + one pure normalizer.
- No existing call sites break (the record is optional at ingestion; flows
  that require it declare it — #500 owns that wiring).
