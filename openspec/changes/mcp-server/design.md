# design — mcp-server

The tool handler is transport-independent (`McpToolCaller`): tests call tools
directly; the SDK binds the same handler to stdio in the CLI wiring. Errors
are `LedgerIntegrityError` (ledger boundary failures).

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Direct ledger mutation from tools (MCP is projection + steering, the same
  correction path as chat).
- A bespoke protocol (MCP is the ecosystem standard — the exit the ruling keeps).
- State merge into the harness (projection-only is the LoopX/DSH lesson).
