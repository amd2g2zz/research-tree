# Design

`completion_input_registrations` is appended in the same SQLite transaction
as its immutable artifact and lineage event. The row records its role, exact
artifact revision, run revision, issuer, and issuer evidence. It never accepts
an already-written generic artifact as a registration.

`CompletionInputRegistrar` owns four explicit writers. Each validates its
schema and checks the exact payload lineage against the supplied parent refs.
The ledger additionally requires the right run, expected run revision,
non-stale parents, and no correction quarantine. Closure inputs require a
passed v2 assessment from its exact core evaluator with its closure token;
the existing `SlotClosureAssessor.is_current()` remains the source of closure
graph currentness and is not reimplemented here.

Registered retries with the identical artifact id, payload, and parents return
the existing immutable revision. Any failure occurs before commit, so no
artifact, registration, event, or run revision is partially written.
