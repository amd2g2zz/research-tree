## Context

Issue #185 creates a pure intent-derived plan and #186 creates pure execution
and assessment values.  The runtime already has one ledger writer
(`ResearchRunCoordinator`), durable capture/receipt/checkpoint artifacts, and
non-authoritative HostEvents.  `worker_finished` validates durable evidence,
but it cannot currently bind that evidence to a SearchPortfolio execution or
use an assessment to record the next bounded research action.

## Goals / Non-Goals

**Goals:**

- Preserve an exact, immutable ledger lineage from the existing SearchPortfolio
  and PortfolioExecution values to their durable evidence and finding refs.
- Make portfolio-backed `worker_finished` events validate that persisted
  lineage at the existing canonical HostEvent ingress.
- Route an inside-authority pivot through #153's authorized CorrectionEvent and
  `apply_correction()` path so stale descendants are quarantined; preserve a
  requester-controlled change as a pending human reopen instead.
- Parent the lineage on all resolved inputs so existing correction invalidation
  quarantines it transitively.

**Non-Goals:**

- Change #163/#185/#186 value schemas, selection rules, or execution
  dispositions.
- Add a second ledger writer, a CLI route, an acquisition fallback, a
  migration/alias reader, or #83 parent acceptance.

## Decisions

### Coordinator-owned immutable lineage artifact

`ResearchRunCoordinator` will accept existing SearchPortfolio and
PortfolioExecution values plus exact ArtifactRefs for their capture, receipt,
checkpoint, and finding evidence.  It will validate identifier/run/attempt
bindings, append one immutable `search-portfolio-lineage` artifact, and retain
the pure value payloads alongside exact refs.  The artifact's parents include
the resolved durable evidence and current state, so #153's existing graph
invalidation can quarantine it without a portfolio-specific invalidator.

Embedding the settled pure values in one coordinator-owned artifact avoids a
second persistence service and avoids changing the #186 typed contract.

### Portfolio-specific worker-finish gate

A dispatched work item that declares `portfolio_id` is portfolio-backed.  Its
`worker_finished` HostEvent MUST carry an exact `portfolio_lineage_ref`; the
coordinator resolves it, verifies its attempt, portfolio id, evidence refs,
and assessment, then applies the existing worker-finish checks.  Ordinary work
items retain their existing worker-finish inputs and do not acquire a portfolio
requirement.

The existing HostEvent envelope and ingress remain the only host boundary;
adding an independent portfolio event protocol would duplicate #151.

### Authorized correction and human reopen projection

For an assessment with `pivot` and
`inside_confirmed_authority`, the caller supplies a CorrectionEvent whose
strategy binding is the exact strategy parent persisted with the lineage.  The
coordinator appends the lineage, then invokes `apply_correction()` so #153's
canonical `stale-state-quarantine` path invalidates affected descendants.  It
does not treat an informational same-round replan as sufficient.  For
`requires_requester_reopen`, it appends a pending
`human-decision-reopen` artifact and does not autonomously replan or mutate
human authority.  Both actions are ledger records rather than worker claims.

## Risks / Trade-offs

- [A pure execution value uses opaque stable ref identifiers] -> resolve those
  identifiers only through the exact ArtifactRefs supplied to the coordinator;
  reject missing, cross-run, stale, or mismatched evidence.
- [A portfolio task may be incorrectly marked ordinary] -> derive the gate from
  the dispatched work item's explicit `portfolio_id`, not a host assertion.
- [A correction invalidates a capture after persistence] -> parent the lineage
  on canonical evidence and invoke the established correction path so its
  transitive stale-state quarantine is authoritative.
- [New ledger artifacts enlarge the run graph] -> use one lineage plus at most
  one bounded next-action artifact per persisted execution and retain Git
  revert as rollback.

## Migration Plan

No data migration exists.  New runs use the coordinator method and
portfolio-backed work-item gate.  Rollback is a Git revert; existing immutable
artifacts remain historical and no legacy reader is restored.
