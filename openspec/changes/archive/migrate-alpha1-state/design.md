## Boundary

`Alpha1MigrationService` inventories only known legacy paths underneath one
workspace. It records path metadata and SHA-256 digests, never raw checkpoint
content, and assigns every entry `completion_authority: none`.

The service writes a rebuildable Alpha2 compatibility projection under
`.research-tree/projections/legacy/`; it never writes into an Alpha1 path.
Malformed, unsupported, stale-host, and duplicate state gets a stable
diagnostic and leaves no partial migration authority.

## Cutover

`cut_over` accepts only a registered release-gate result with `status: pass`.
Its result makes the retirement disposition explicit: legacy completion writes
are retired and canonical completion remains coordinator-only. Rollback simply
disables the cutover command and retains the projection and source data as
read-only evidence.
