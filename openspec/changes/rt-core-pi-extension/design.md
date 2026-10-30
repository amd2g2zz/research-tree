# design — rt-core-pi-extension

The structural `PiSubagentsApi` port keeps rt-core testable without the pi
host (fakes) and the real extension is a drop-in at composition. The 4-type
mapping is compiler-checked (const tuple). Dispatch policy (concurrency,
blind verification contracts) stays engine-side; session/fleet management
stays extension-side.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- rt-core-owned session/fleet management (pi-subagents is the substrate — the
  2026-10-30 amendment).
- A bash bridge to the Python core (cancelled with the full-TS ruling).
- Behavior strategy in agent definitions beyond the class contract (two-layer
  contract: prompts carry strategy, engine verifies structure).
