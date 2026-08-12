## Context

The runtime already has Decision Slot deficits, AdaptiveResearchPolicy action
selection, SourceCapture/AcquisitionReceipt persistence, and AnalysisCheckpoint
recovery. The missing boundary is the acquisition plan between intent and
worker dispatch: a typed object that explains which subquestions matter, which
methods are materially independent, what failure modes trigger deeper work, and
why a batch is or is not enough for the current decision.

## Goals / Non-Goals

**Goals:**

- Persist SearchPortfolio artifacts before acquisition dispatch.
- Keep method/provider independence explicit and separate from query count.
- Reassess every acquisition batch through coverage, depth, contradiction,
  provenance, implementation uncertainty, and oracle-readiness dimensions.
- Feed portfolio outcomes into AdaptiveResearchPolicy while leaving coordinator
  state, source capture, checkpoints, closure, and completion authority intact.

**Non-Goals:**

- Adding live network integrations or new provider dependencies in this issue.
- Treating generated subquestions, provider count, or source volume as research
  quality.
- Replacing #80 capture/checkpoint validation or #58 scoring policy.
- Persisting hidden evaluator content, private prompts, or chain-of-thought.

## Decisions

1. **Use pure portfolio contracts first.** The implementation adds validators
   and deterministic planners for SearchPortfolio, MethodBoundary, and
   BatchCoverageAssessment before adding host adapters. This keeps unit tests
   source-bound and avoids live provider instability. Direct live execution can
   consume the same contract later.

2. **Model boundary independence explicitly.** A method boundary contains method
   id, provider id, corpus id, extraction path, provenance group, permission
   profile, retryability, and limitation. Several query variants sent through
   one provider/corpus remain one boundary. A direct repository read, official
   source extraction, documentation index, scholarly archive, or bounded
   experiment may form a distinct boundary when its provenance or failure mode
   differs.

3. **Make post-batch disposition the handoff point to policy.** The coverage
   assessment returns `deepen`, `broaden`, `pivot`, `validate`,
   `sufficient_for_slot`, or `blocked`, with causal refs and next action
   proposals. The scheduler can consume these proposals, but the coordinator
   still owns lifecycle transitions and completion.

4. **Bind every portfolio to #80 artifacts when evidence exists.** Portfolio
   outcomes reference SourceCapture, AcquisitionReceipt, and AnalysisCheckpoint
   ids; missing or unavailable captures are explicit dispositions rather than
   absent evidence.

## Risks / Trade-offs

- **[Synthetic method registry overstates live capability]** -> Record capability
  as declared, unavailable, failed, or degraded and require later host evidence
  before claiming parity.
- **[Portfolio generation becomes speculative planning]** -> Require every
  subquestion to name the originating deficit, expected decision effect, and
  stop/replan trigger.
- **[Pivot logic silently changes requester authority]** -> Strategy pivots are
  allowed only inside confirmed authority; requester-controlled outcome,
  permission, or safety changes reopen the human decision.
- **[Too much schema surface for one PR]** -> Keep the first implementation to
  focused dataclasses/validators, deterministic policy hooks, and fixtures.

## Migration Plan

1. Add failing tests for portfolio validation, method boundary independence,
   degraded capability, shallow-wave deepening, contradiction/pivot, and #80
   lineage.
2. Add runtime contracts and deterministic helper functions.
3. Register group-27 evidence and umbrella tasks.
4. Roll back by disabling portfolio generation and using the existing bounded
   acquisition projection with an explicit degraded-capability note.

## Open Questions

- Live host-specific method probes remain future evidence; this issue records
  unavailable/degraded capability rather than claiming live multi-provider
  parity.
