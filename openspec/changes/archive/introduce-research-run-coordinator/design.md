# Design: Single Runtime Authority

`ResearchRunCoordinator` owns a `RunLedger` and persists a single latest
`research-run-state` artifact plus append-only `lifecycle-event` and
`host-event` artifacts. A transition is accepted only when its `(from,event,to)`
edge exists in the checked-in lifecycle matrix and the actor matches the edge.
The state payload contains lifecycle revision, state digest, unresolved
obligations, and legal next actions. Event and state artifacts are appended in
one SQLite batch under the caller's expected run revision.

Initialization requires exact, same-round `alignment-handoff` and
`blueprint-target` revisions. Completion is never inferred from worker counts,
frontier emptiness, reports, or host events. It requires current evaluator-owned
closure tokens, non-blocking insights, readiness, both delivery manifests, and
exact user acceptance. Missing requirements are returned as stable obligations.

Duplicate event/idempotency keys return the original artifact; a changed payload
for an existing key is rejected. Recovery marks in-flight leases unknown and
replays each event at most once. Supersession preserves the old state and links
the successor run.
