## Context

The coordinator currently derives completion candidates by selecting the latest
artifact of each expected kind and reading shallow payload fields. The generic
ledger append API is intentionally useful for non-authoritative observations,
but it has no issuer capability and therefore cannot distinguish an official
closure, insight, readiness, or evaluation result from a look-alike artifact.

The merged #152 closure service already provides `SlotClosureAssessor.is_current()`
for replaying a closure assessment. #153 supplies transitive quarantine and
#151 supplies canonical event admission. This child consumes those boundaries;
it does not replace them.

## Goals / Non-Goals

**Goals:**

- Register only exact validated closure, insight, readiness, and evaluation
  revisions as completion inputs in one optimistic-concurrency transaction.
- Bind every registration to a dedicated writer identity and immutable issuer
  record that generic appends cannot manufacture.
- Make duplicate registration idempotent and every rejection leave no partial
  registration state.
- Expose a typed read model for later #158 manifold resolution.

**Non-Goals:**

- Change `ResearchRunCoordinator.complete()` or decide the final completion
  manifold.
- Register delivery or acceptance inputs, expose CLI verbs, or alter HostEvent
  ingress.
- Reimplement closure evidence graph replay, correction traversal, or token
  currentness.

## Decisions

### Dedicated registration capability

`RunLedger` will expose a narrowly typed completion-input registration method
that creates an immutable registration artifact in the same transaction as its
issuer record. Generic append rejects the authoritative registration and issuer
kinds. This is preferred over an allowlist in the coordinator because authority
is enforced at the write boundary and remains testable without a completion
transition.

### Exact refs, not latest-kind discovery

The registration payload contains one exact ref per input role, the registering
issuer ref, and the run revision. Readers resolve those refs and validate their
currentness instead of selecting the latest artifact by kind. This makes stale,
mixed-lineage, and replacement-issuer submissions fail closed.

### Reuse role validators

Closure registration calls `SlotClosureAssessor.is_current()`. Insight,
readiness, and evaluation registration use their existing typed validators and
require current ledger revisions. The boundary orchestrates these validators;
it does not duplicate their domain rules.

### Incremental migration

This slice supplies dedicated writer/registrar APIs and migrates the four input
roles. The coordinator retains its present completion state machine until #158
consumes the exact registration manifold. The temporary coexistence is safe
because registration itself is authoritative while generic artifacts are not
admitted to it.

## Risks / Trade-offs

- [Existing writers use generic append] → migrate only the four named writers
  and reject their old output at the registration boundary.
- [Issuer identity is incorrectly modeled as a string] → persist and resolve a
  dedicated issuer artifact with exact parent and revision binding.
- [A domain validator becomes stale] → registration requires current refs and
  reruns the validator at admission time.
- [Scope grows into final completion] → keep coordinator completion consumption
  unchanged; #158 owns that replacement.

## Migration Plan

1. Add the typed models, issuer records, registration write API, and rejection
   tests.
2. Migrate closure, insight, readiness, and evaluation writers to emit an
   issuer-bound registration.
3. Add group-43 registry ownership and record the focused source-bound receipt.
4. Roll back by Git revert; immutable historical artifacts remain, while new
   unprovable registrations are rejected.

## Open Questions

- The exact public service names will follow the nearest existing writer APIs;
  no public CLI surface is introduced in this child.
