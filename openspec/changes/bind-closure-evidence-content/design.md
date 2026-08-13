## Context

`RunLedger` already records immutable artifact revisions and provides exact
content bindings for `SourceCapture` and `EvidenceArtifact` through the CAS
transaction boundary. The original closure assessor only validates a caller's
selected Finding references against a Decision Ledger parent list; it does not
prove that those Findings resolve to durable source content, and it does not
prove that the caller supplied every current Finding for the decision.

Issue #160 is the first child of parent issue #152. It establishes the
content-and-coverage boundary only. Issue #161 will derive provenance,
counterevidence, contradictions, quality, and token currentness after this
child is merged and reachable.

## Goals / Non-Goals

**Goals:**

- Accept closure evidence only when its strict Finding observations resolve to
  exact canonical evidence, a succeeded receipt, a committed capture, and
  content bindings whose readable CAS bytes, digest, media type, and size match
  the typed payloads. Strict anchors must also pass existing selector and
  repository-locator validation. Legacy-unspecified evidence is not authoritative.
- Follow declared capture origins to their canonical, content-bound roots.
- Derive the full current Finding set directly bound to the selected decision,
  target, and slot; reject caller-pruned or caller-expanded input.
- Preserve the existing `assess()` signature and conservative append-only
  assessment behavior.

**Non-Goals:**

- Deriving source independence, producer identity, adversarial coverage,
  contradictions, or counterevidence disposition.
- Changing the assessment token schema, recomputing token currentness, or
  registering parent group 39.
- Altering coordinator completion, delivery, HostEvent, or CLI behavior.

## Decisions

1. **Resolve evidence from immutable ledger relationships.** The assessor will
   parse a strict Finding's anchors, require each exact EvidenceArtifact to be
   a direct Finding parent, reject `legacy_unspecified` evidence, and resolve
   its binding through the existing strict evidence resolver and CAS reader. It
   will then require
   one succeeded AcquisitionReceipt direct parent, one matching SourceCapture
   direct parent, and canonical origin captures. This reuses existing durable
   record validators instead of introducing a second persistence format.

2. **Treat unprovable evidence as inconclusive, not as a passed result.** A
   malformed or unbound graph sets the evidence check false and cannot issue a
   closure token. This preserves the existing durable assessment history while
   making an unverifiable graph non-authoritative.

   Strict repository-path evidence is also unprovable unless its declared
   source revision can be verified through the existing resolver. This child
   fails it closed rather than inventing repository-currentness behavior,
   which is outside this issue.

3. **Treat caller-selected Finding coverage as an input error.** The assessor
   independently enumerates current `finding-pack` parents of the Decision
   Ledger entry that match its target and slot. The supplied reference set must
   equal that set exactly; omission or injection raises
   `ClosureAssessmentError` before an assessment is appended.

4. **Keep quality inputs and token behavior unchanged.** The existing
   `provenance_groups`, `counterevidence_disposition`, and
   `active_contradiction` arguments remain part of the method signature. Their
   authority replacement belongs exclusively to issue #161.

## Risks / Trade-offs

- **[Legacy tests construct shape-only source artifacts]** -> Update focused
  closure fixtures to use the existing durable capture and evidence writers;
  manually appended artifacts intentionally become inconclusive.
- **[A valid historic decision references a superseded Finding]** -> Require
  current exact revisions and report the assessment as invalid rather than
  silently assessing a stale decision graph.
- **[Graph parsing expands the assessor]** -> Limit this child to content and
  parent relationships; defer quality-derived fields and token work to #161.

## Migration Plan

No stored artifact is rewritten. Existing assessments remain immutable history.
New assessments fail closed when content or Finding coverage cannot be proven.
Rollback retains history and disables passed closure issuance for affected
graphs by treating evidence as inconclusive.

## Open Questions

None. The child boundary and acceptance tests are fixed by issue #160; group
39 remains parent-only after #160 and #161 receipts are reachable.
