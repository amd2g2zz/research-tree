# design — tui-renderer

The frame derives from ledger.graphEvents() + versions + machine.phaseOf —
no separate state. Uncommitted tasks render the 未冻结·不可跟踪 label; tasks
with drafts show the suffix; committed versions show the frozen banner.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- A second behavior implementation (the TUI reads the same event stream —
  same-source discipline).
- Interactive toolkit in rt-core (host-side concern).
