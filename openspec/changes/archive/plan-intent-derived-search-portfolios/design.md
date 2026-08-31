## Design

`IntentDerivedSearchPortfolioPlanner` consumes a strict `MethodRegistry` and
revision identifiers for the intent, Working Brief, strategy, Decision Slot,
and evidence deficit. It returns a strict `SearchPortfolio` together with a
pure planning projection.

The projection always creates six bounded coverage obligations: mechanism,
counterevidence, implementation, edge-case, validation, and consequence. Each
records its expected evidence class, decision effect, closure oracle, and
stop/replan trigger. Query rewrites use only stable query references so the
#163 public contract continues to exclude raw queries and private prompts.

The planner has no RunStore dependency and cannot retrieve, persist, dispatch,
or assess a batch. Routine evidence and implementation changes remain an
autonomous replan; only `authority`, `safety`, or `requester-outcome` marks the
result as requiring a human-decision reopen.
