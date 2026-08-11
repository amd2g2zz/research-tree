## Why

The runtime has a coordinator as its lifecycle authority, but adaptive growth
and recursive-search code can still make opaque local decisions from incomplete
evidence. Research expansion, pruning, and insight synthesis need deterministic
inputs, durable lineage, and a non-authoritative compatibility boundary before
they can safely guide future coordinator actions.

## What Changes

- Add a host-neutral, deterministic `AdaptiveResearchPolicy` that emits typed,
  evidence-bound action proposals or explicit deferrals without mutating a run.
- Replace scalar realized-delta reasoning with an auditable six-component
  baseline and replayable selection trace.
- Upgrade Insight Digest validation and synthesis so covered, uncovered, thin,
  contested, qualified, and converging signals retain exact evidence lineage.
- Demote legacy recursive-search completion and delivery paths to compatibility
  projection behavior that cannot close a Slot or ResearchRun.
- Add TDD receipts that run focused pytest plus Ruff lint and format checks at
  each red/green slice.

## Capabilities

### New Capabilities

- `adaptive-research-policy`: deterministic, evidence-bound policy proposals,
  score traces, replay, pruning, and authority-safe compatibility projection.

### Modified Capabilities

- `adaptive-research-execution`: policy selection and optional frontier growth
  become reproducible, lineage-bound, and non-authoritative.
- `insight-synthesis`: Insight Digest gains explicit classified signals,
  six-component delta input, lineage validation, and replay requirements.

## Impact

Affected runtime modules are `policy.py`, `evidence_delta.py`, `insights.py`,
and the compatibility surface in `recursive_search.py`, with focused policy,
delta, insight, replay, and recursive-search tests. The coordinator remains
the only persistence and lifecycle authority; HostEvent protocol, alignment,
SearchPortfolio acquisition, and worker scheduling are out of scope.
