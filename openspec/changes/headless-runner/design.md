# design — headless-runner

The runner is a thin driver over the #551 machine — no new state, no new
gates: the script's steps are machine signals, and the consent model maps to
the machine's own fail-closed gates (an unhandled pause is the machine's
paused phase; the resume token re-enters runHeadless with the pre-signed
choice). Resume is fork-free by construction: the same ledger instance, the
token only records the pending-decision point.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Silent auto-signing of unhandled gates (the product red line: 问句不是判决 —
  even headless).
- Ledger fork on resume (resume continues the same run).
- Swallowing projection failures inside the runner (the #551 machine's
  fail-closed dual-write semantics apply; divergence is resync-repairable).
