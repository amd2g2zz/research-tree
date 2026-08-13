## Context

`research-tree-setup` currently recognizes a checkout-root or old Claude
plugin link as `legacy`, removes that target, and creates a new current link.
It also exposes an explicit `refresh` command that repoints stale links. Both
flows alter a path the user already owns, which conflicts with the current-only
policy introduced by #164 and tracked by #165.

## Goals / Non-Goals

**Goals:**

- Preserve installation into a missing target and idempotent recognition of a
  current target for Codex, Claude Code, and Hermes.
- Treat every existing non-current target as unsupported and leave it exactly
  as found.
- Remove migration-specific result states, helper functions, CLI options, and
  tests rather than returning a compatibility action.
- Register group 57 for #169 without claiming verification before its receipt.

**Non-Goals:**

- Repointing, unlinking, moving, copying over, cleaning up, or recovering an
  existing legacy or stale target.
- Changing host target layouts, current package content, host activation
  semantics, or user-owned runtime data.
- Removing the remaining `RunStore` or legacy evidence compatibility surfaces
  owned by sibling #165 slices.

## Decisions

1. **Existing non-current paths are unsupported.** `installation_status` keeps
   only `missing`, `current`, and `unsupported`. A stale link, a former legacy
   target, and an arbitrary conflicting directory all collapse to
   `unsupported`; this is a present-state safety classification, not a legacy
   reader.

2. **Install never mutates an existing target.** It preflights all selected
   hosts, rejects any `unsupported` target, and performs writes only for
   `missing` targets. Dry-run returns `planned` only for missing targets and
   fails unchanged for an unsupported target.

3. **Retire refresh entirely.** Remove the public subcommand, confirmation
   flag, source-reading helper, and link-removal path. Normal rollback only
   removes targets created in the same failed install transaction; it cannot
   restore or mutate a pre-existing target.

4. **Use Git for rollback.** Reverting this narrow deletion restores the prior
   source revision; no runtime fallback or migration interface is added.

## Risks / Trade-offs

- Existing legacy setup users must remove or relocate their own target before
  installing; this is intentional and avoids agent-owned mutation.
- Collapsing status detail sacrifices migration advice but prevents a
  compatibility protocol from remaining reachable.
- Package content changes must be generated from source and committed
  separately from authoring changes when the builder produces them.

## Verification

Focused tests prove a legacy checkout link and an old Claude package link both
remain byte-for-byte and path-for-path unchanged after `install`, `status`, and
the retired `refresh` parser path. They also prove missing/current installs for
all supported hosts retain their behavior. Group 57 runs the focused setup,
activation, and package tests plus Ruff and package validation.
