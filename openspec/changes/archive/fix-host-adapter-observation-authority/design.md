## Context

`native_execution_adapter.py` owns a host-local projection. Its prior
`verify_task` implementation promoted a submitted artifact to `completed`,
while accepting missing or inconclusive validation and only a reviewer string.
That contradicts the coordinator's sole-writer lifecycle model.

## Decisions

- A host review produces a verified submission observation, never a completed
  task. Dependency scheduling may consume a submitted task only when its
  observation is independently reviewed and its artifact hash remains intact.
- `verify` requires a passed Finding Pack validation result plus a reviewer
  host, agent, session, and lease identity recorded by the lifecycle hook for
  the same project run. Each identity must differ from the worker binding.
- `verify` requires a separate in-workspace custody copy whose digest equals
  the submitted artifact digest. This makes the reviewed bytes explicit and
  prevents the worker artifact path from being reused as the review evidence.
- Submission retains worker and attempt bindings. Recovery clears review
  observations together with invalidated artifact state.
- Hermes remains a non-authoritative bridge and no longer reports an observed
  completed run without evidence supplied by the canonical coordinator.

## Risks

- Older scripts that call `verify` need the explicit reviewer receipt fields.
  The adapter fails closed rather than treating labels as authority.
- Host hooks are observational provenance, not an implementation completion
  authority; the canonical closure manifold remains required for final state.
