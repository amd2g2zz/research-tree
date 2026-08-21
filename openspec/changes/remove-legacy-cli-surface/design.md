## Context

The installed `research-tree` entrypoint currently registers legacy round,
tree, and project-profile subcommands. The separate `research-tree-migrate`
entrypoint exposes Alpha1 compatibility inventory, projection, cutover, and
rollback operations. Earlier containment returned an `authority_blocked`
payload and retained no-write reads, but the product now rejects every
old-version compatibility surface.

## Goals / Non-Goals

**Goals:**

- Make every retired `research-tree` command fail parser recognition before it
  can resolve a caller path or construct a legacy or canonical store.
- Remove the standalone migration console script and all code reachable only
  through that public compatibility surface.
- Remove maintained public command references from documentation and source
  templates, then rebuild generated packages from those sources.
- Keep the minimal `research-tree` parser importable as the reserved canonical
  entrypoint without claiming an unfinished canonical command exists.

**Non-Goals:**

- Adding canonical command verbs, coordinator routing, HostEvent ingress,
  aliases, refusal payloads, inventory guidance, or automatic data migration.
- Modifying user-owned historical data.
- Retiring `LegacyRunStoreImporter` or the broader filesystem `RunStore`
  runtime; #165 owns that separate removal.

## Decisions

1. **Remove registrations rather than classify them.** `cli.py` retains only
   an argument parser with no legacy subparsers, store imports, dispatch, or
   compatibility constants. Argparse rejects a retired command with its normal
   nonzero parse failure, before any persistence path is used.

2. **Retire migration as a complete surface.** Remove the console-script
   registration, `migration.py`, `migration_cli.py`, root-package exports,
   migration tests, and the layout workflow probe that invokes the module. No
   redirect, inventory response, or migration recommendation remains.

3. **Remove public references at their sources.** Replace command-specific
   README and historical-spec examples with the supported Python API boundary;
   remove command registrations from host templates and research references.
   Rebuild packages so generated copies do not retain old instructions.

4. **Keep the canonical boundary intentionally inert.** The minimal
   `research-tree` parser remains the published entrypoint needed for a future
   canonical CLI. It registers no replacement subcommand and does not call the
   coordinator, so #164 neither guesses nor exposes incomplete authority.

## Risks / Trade-offs

- **[Existing automation exits with a parse failure]** -> This is deliberate
  breaking removal. No compatibility answer can preserve a second public
  authority.
- **[A generated package retains a source reference]** -> Rebuild every host
  package and validate it after changing the authoring sources.
- **[The remaining runtime is mistaken for in-scope]** -> Tests and this
  change remain limited to public CLI/migration removal; #165 owns further
  runtime retirement.

## Breaking Cutover

The retired command paths and migration modules are removed from the working
tree. Existing user data is neither inspected nor changed. The prior
implementation remains recoverable only through Git history; this change adds
no compatibility, migration, or rollback interface.
