# Proposal: proportionality-assessment-trace

## Why

issue #498 (confirmed): the runtime checks whether a proposal is *feasible*
but never whether it is *necessary or proportionate*; over-engineered
proposals pass as `plausible`, and the mirror case (grand goal, tiny
constraint) has no check either. Per the 2026-09-03 implementation-shape note
under #501: the engine adds ONE trace type and verifies presence + schema;
the judgment content is prompt-layer craft. This is layer 1 of the ladder —
the waiver path and compile-time conflict rejection already exist as layers
2-3.

## What Changes

1. Trace type `proportionality_assessment` appended to the frozen registry
   (required fields: direction, finding, alternative, reframing — presence
   and schema only, never content quality).
2. Proposal-shaped gaps now require the assessment in `required_traces`
   (alongside option-set / possibility-survey); misunderstood-intent gaps
   (guess-statement) do not.
3. Prompt layer: the craft doc marks proportionality-challenge as the
   required trace on proposal-shaped gaps and names the ladder layers.

## Impact

- turn_contract.py: one append-only registry entry (designed extension path).
- alignment_graph.py: `_gap_required_traces` returns the extra name for
  proposal shapes only.
- Existing tests pinning the six-type registry or two-trace derivations are
  updated to the seven-type contract.
