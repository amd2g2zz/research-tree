# design — product-state-machine

Legal-transition matrix as data; fail-closed guards run ahead of the matrix
(sign gate, pause scope, freeze gate). Task birth = openTask (chat). fork =
VersionStore.fork + chat birth + lineage edge. Commit is transient: the
machine lands in chat (inherit-and-realign) emitting both transitions
(converged→committed, committed→chat). State is event-sourced — rehydrate
scans task.transition events.

## impact_scope

As proposal. GitNexus: new modules; engine.ts accessor is additive.

## rejected_designs

- Persisted phase column (state is derivable from transition events —
  event-sourcing keeps one truth).
- freeze from non-converged phases (the #530-class bypass this machine exists
  to kill).
- Auto-continue after commit (inherit-and-realign is an explicit chat landing).
- Confirming decompositions inside the machine (the #549 engine owns it; the
  machine only checks the confirmed status at the sign gate).
