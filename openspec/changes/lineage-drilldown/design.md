# design — lineage-drill-down

The drill-down reads the committed version snapshot — the claim's evidence
refs are the raw-evidence layer (snapshots preserve their own references per
A7). The three steps map to the UI's canvas-node → detail-drawer → raw-source
navigation. The historical-version rule holds because snapshots are
content-addressed and immutable.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Streaming framework (克制清单).
- Fake lineage for unknown claims (return null — no fabrication).
- >3 click paths (the rule is the product requirement).
