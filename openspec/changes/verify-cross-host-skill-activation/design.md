## Context
Setup cannot prove live activation and collapses stale links into conflicts. Codex requires typed input; Claude and Hermes retain independent slash paths; the builder owns packages.
## Goals / Non-Goals
**Goals:** Three evidence states, pure native probes, safe receipts, non-mutating diagnostics, and independent unavailable results.
**Non-Goals:** Prove later work, auto-launch hosts, rewrite configuration, or change lifecycle authority.
## Decisions
### Native probes and bounded receipts
Construction and status are pure; only explicit execution starts hosts. Codex uses `$research-tree` plus typed skill input, Claude `/research-tree` plus its plugin alternative, and Hermes `/research-tree` plus `/skill research-tree`. Exact sentinels bind safe correlations and package/body digests; extra text, wrong identity/path, or drift fails.
### Explicit stale-link refresh
Classify selected links as `current`, accepted old roots as `legacy`, other/broken links as `stale_link`, equal copies as `current`, and other content as `conflict`. Only confirmed refresh replaces a stale link; failure restores it.
### Generated material
Adapters/reference/helper are builder inputs, packages use a generated-only commit, and validation rejects missing, drifted, or cross-host material.
## Risks / Trade-offs
- Sentinel receipts grant no research/completion authority.
- Junctions need reparse fixtures; missing hosts stay `unavailable`; failed refresh restores its target.
## Migration Plan
Add red contracts, implement, regenerate separately, and bind group 32. Rollback disables receipts/refresh while retaining diagnostics.
