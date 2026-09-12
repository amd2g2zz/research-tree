# Design: transformation-trace

## Approach

Same philosophy as #498: finite verifiable trace types + presence/schema
checks; composition quality stays generative.

### Registry (digest-first + viewpoint-hints)

- `digest-first` requires `point`, `decision_relevance`, `source_pointer` —
  the 1-2 sentence point, why it matters to the decision, and where to read
  more. It replaces the forwarded-source dump as the user-update primitive.
- `viewpoint-hints` requires `alternatives` — entries shaped like the
  delivery document's material_alternatives/trade_off (position + trade_off),
  so mid-research viewpoints round-trip into the final brief without a
  second schema.

### Ingestion transformation record

`CanonicalFindingPackCompiler.compile(transformation={"ratio": <0..1>})` —
when present it must be exactly `{ratio}` with a numeric value in [0, 1];
the normalized value is persisted in the pack payload. The structural
half of "agent-phrased with anchors" is already enforced: strict mode
requires every observation to carry a canonical EvidenceAnchor, and
repository anchors are validated against the slot. Quote-ratio regex
policing of the text remains the rejected design.

### Ratio semantics

`turn_shape.transformation_ratio` (#493 slot) is composer-reported. The
engine cannot measure "analyzed vs forwarded" without content policing
(rejected); it can require the digest-first trace on user-facing
mid-research updates — that requirement lands with #500's interactive turn
layer, which owns the composition flow.

## impact_scope

- `DEFAULT_TRACE_REGISTRY` / `INITIAL_TRACE_TYPES` (seven → nine entries)
- `CanonicalFindingPackCompiler.compile` (additive optional parameter)
- new `_normalize_transformation` (ledger.py)
- tests/test_transformation_trace.py (new), tests/test_turn_contract.py pin

## rejected_designs

- **Quote-ratio regex policing** of observation text (explicitly rejected in
  the issue comment): brittle, gameable, and content policing violates the
  two-layer contract.
- **Requiring `transformation` on every compile() call site**: 106 call
  sites would churn mechanically; flows that require the record declare it
  (#500 wires the user-facing requirement).
- **A separate transformation validator module**: one turn-record / one pack
  payload carries it; no second gate system.
