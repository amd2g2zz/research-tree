## Design
`SearchPortfolioService` is the canonical persistence adapter for strict typed values. It accepts exact current `ArtifactRevision` inputs for the intent model, working brief, strategy, decision map, and method registry; the portfolio payload contains bounded subquestions, query references, selected method/provider boundaries, and exact parent lineage, without raw query or private prompt text.

`record_batch` appends immutable `method-execution-outcome` children and one `portfolio-batch` projection after resolving current captures, receipts, checkpoints, and finding packs; failed outcomes cannot claim captures. `record_assessment` atomically appends `batch-coverage-assessment` and `portfolio-decision`, including the typed stop/rewrite/switch/deepen/experiment/pivot/blocked disposition and human-only reopen state.

Coordinator dispatch validates the portfolio against the current displayed strategy and target, then puts its reference in the attempt lease. Canonical `HostEvent` ingress keeps existing revision, lease, sequence, causation, and payload checks first, then validates the current portfolio assessment before acquisition `worker_finished`; generic ingress cannot append a substitute artifact.

`AdaptiveResearchPolicy.evaluate` accepts a normalized assessment projection and derives bounded signals without calling the ledger. An autonomous contradiction can persist a successor only when its parent is the superseded strategy; `requires_requester_reopen` remains `blocked` with `awaiting-human-reopen`, and no authority expansion is inferred.

All new artifacts use ordinary `parent_refs`, so #153's dependency traversal quarantines unknown and future descendants conservatively. Quarantined portfolios, batches, assessments, decisions, leases, and late events fail closed on latest-reference and authority checks while immutable history remains readable.
