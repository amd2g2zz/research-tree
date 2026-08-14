# Resolve the registered completion manifold

Issue #158 / Alpha2 group 45 closes the completion-authority gap left after
typed completion-input and delivery registration. Completion is admitted only
when the current run has one exact registered manifold: every P0 closure slot,
one insight, readiness record, evaluation, delivery pair, and human acceptance.

Generic artifact lookalikes remain ordinary immutable lineage. The terminal
completion record stores the resolved manifold and its digest, while
`why_not_complete` exposes field-level diagnostics. Replacing or quarantining a
registered parent makes the completed run non-current without deleting its
historical record.

This change does not alter public CLI routing, HostEvent ingress, provider
support, or the semantic replay contract; those remain owned by later issues.
