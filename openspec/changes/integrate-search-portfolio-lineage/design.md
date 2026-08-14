## Design

`SearchPortfolioService` is the canonical persistence adapter for the strict
typed values. It accepts exact current `ArtifactRevision` inputs for the
intent model, working brief, strategy, decision map, and method registry. The
portfolio payload contains bounded subquestions, query references, selected
method/provider boundaries, and an exact parent-reference lineage. No raw query
or private prompt is persisted.

`record_batch` appends immutable `method-execution-outcome` children and one
`portfolio-batch` parent-linked projection. Captures, receipts, checkpoints,
and finding packs are resolved as current artifacts before they become parents;
failed outcomes cannot claim captures. `record_assessment` appends a
`batch-coverage-assessment` and a `portfolio-decision` in one ledger batch.
The decision stores the typed stop/rewrite/switch/deepen/experiment/pivot/
blocked disposition and whether a human-only reopen is required.

Coordinator dispatch validates the portfolio against the current displayed
strategy and target, then puts the portfolio reference in the attempt lease.
The canonical `HostEvent` ingress performs the existing revision, lease,
sequence, causation, and event-payload checks first. For acquisition work it
then validates the current portfolio assessment before allowing a
`worker_finished` event. The generic event path cannot append a substitute
artifact.

`AdaptiveResearchPolicy.evaluate` accepts a normalized assessment projection
and derives bounded signals. It never calls the ledger. An autonomous
contradiction can persist a successor strategy only when the caller supplies
an exact successor whose parent is the superseded strategy. An assessment with
`requires_requester_reopen` is persisted as `blocked` and the decision status
is `awaiting-human-reopen`; no authority expansion is inferred.

All new artifacts use ordinary `parent_refs`, so #153's dependency traversal
quarantines unknown and future descendants conservatively. A quarantined
portfolio, batch, assessment, decision, lease, or late event fails closed on
latest-reference and authority checks while immutable history remains readable.
