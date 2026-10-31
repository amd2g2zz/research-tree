# design — minimal-canvas

The projection reads the ledger's event stream directly (same-source); the
react-flow rendering is host-side. Gates are the class's only mutating
methods — the type system enforces the five-gate rule (no other method
mutates state). PARK without revival conditions is rejected (red line).

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- The projection holding mutable state (read-only + gates).
- Color-only status (red line).
- Bypassing gates for internal mutations (the gates ARE the write surface).
