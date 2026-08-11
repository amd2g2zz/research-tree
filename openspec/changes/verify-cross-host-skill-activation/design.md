## Context

Setup verifies paths but collapses stale links into conflicts and cannot prove live activation. Codex requires text plus typed skill input; Claude Code and Hermes use independent slash paths. The builder owns generated copies.

## Goals / Non-Goals

**Goals:** Distinguish discovered/static/live evidence, construct pure native probes, bind safe receipts, diagnose stale links without mutation, and retain independent unavailable results.

**Non-Goals:** Prove later compliance/completion, auto-launch hosts, rewrite user configuration, or change lifecycle authority.

## Decisions

### Pure contract, explicit execution
A dependency-free module computes canonical digests, constructs probes, and validates exact responses; a repository script launches hosts only when explicitly requested. Static status never starts a process.

### Preserve native formats
Codex uses `$research-tree activation-probe ...` plus typed skill input. Claude uses `/research-tree` with a plugin-qualified alternative. Hermes uses `/research-tree` with `/skill research-tree` as explicit load. A text-only common form was rejected because it erases Codex's typed-input requirement.

### Bound receipts
The sentinel is `research-tree-activation:v1:<host>:<correlation-id>`. Receipts retain only versions, host, safe correlation, relative package ref, package/body/sentinel digests, state, and non-proof claims. Extra output, wrong identity/path, or drift fails.

### Explicit stale-link refresh
Classify links/reparse points before copies: selected source is `current`, accepted old root `legacy`, other/broken link `stale_link`, equal copy `current`, and other content `conflict`. Only confirmed refresh replaces a stale link and failure restores its target.

### Generated material
Adapters own sentinel rules; shared reference/helper are builder inputs; generated packages use a separate commit; validation rejects missing, drifted, or cross-host material.

## Risks / Trade-offs

- [Sentinel echo is bounded] -> Receipt grants no research/completion authority.
- [Junctions vary] -> Inspect reparse flags and test Windows fixtures.
- [Host absent] -> Record `unavailable`, never success.
- [Refresh fails] -> Restore the prior target.

## Migration Plan

Add red contracts, implement activation/setup behavior, generate packages separately, then bind group-32 evidence. Rollback disables live receipts/refresh while retaining diagnostics.
