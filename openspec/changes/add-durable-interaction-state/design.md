## Design

`DurableInteractionController` is the single writer for `interaction/state.yaml`. Workers submit immutable events with an expected revision. The controller delegates reduction to #245, archives bounded semantic deltas, promotes explicit authority and corrections, and publishes atomically.

JSON is emitted as a YAML 1.2-compatible canonical projection, avoiding a parser dependency. Episodes and durable records are continuity truth; `recall-index/` is rebuildable.
