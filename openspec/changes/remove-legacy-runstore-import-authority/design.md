## Context

The retired importer reads Alpha1 filesystem `RunStore` rounds, writes copied
records into the canonical SQLite ledger, and persists idempotence receipts in
`legacy_imports`. This contradicts the current-only policy because a legacy
payload remains an accepted source of canonical state. Issue #164 already
removed the public CLI and migration entrypoint; issue #167 removes this
remaining programmatic authority.

## Goals / Non-Goals

**Goals:**

- Remove the importer module, its public root exports, dedicated tests, SQLite
  receipt DDL, receipt APIs, and active registry ownership.
- Leave a newly initialized `RunLedger` with only current canonical tables and
  preserve its existing current run, artifact, event, and content behavior.
- Register group 55 as planned before implementation, then bind verification
  to the exact deletion acceptance command.

**Non-Goals:**

- Migrating, dropping, reading, repairing, or mutating existing user-owned
  filesystem or SQLite data.
- Adding a replacement importer, alias, adapter, read projection, rejection
  response, or migration command.
- Changing coordinator, evidence, installation, or broader `RunStore` runtime
  responsibilities.

## Decisions

1. **Delete rather than deprecate.** Remove the module and public names
   entirely. A warning, no-op importer, or an exception type would keep an old
   integration boundary alive and violate the breaking-cutover decision.

2. **Do not migrate existing databases.** Delete `legacy_imports` from the
   creation DDL only. The code neither opens an existing database to remove its
   table nor provides a cleanup command; user data remains untouched.

3. **Retire active ownership, preserve Git history.** Remove group 34 and its
   delivery/issue-map rows because they describe an active runtime capability.
   The completed `import-alpha1-runstore` OpenSpec artifact remains historical
   source evidence in Git rather than a maintained current contract.

4. **Use absence assertions as the regression contract.** Tests prove the
   root module has no old exports, the retired module is not importable, the
   ledger has no receipt methods, and a newly initialized database has no
   `legacy_imports` table while canonical tables remain.

## Risks / Trade-offs

- **[Existing callers receive import errors]** → Deliberate breaking removal;
  the prior source is recoverable only from Git history.
- **[Old database files still contain a retired table]** → Expected: no data
  mutation is in scope, and current runtime never reads or writes that table.
- **[Registry drift hides the removal]** → Group 55 replaces the active group
  34 ownership and strict governance validation checks the registry graph.

## Breaking Cutover

The source tree no longer publishes or implements legacy import authority.
No migration runs during install, import, initialization, or verification.
Rollback, if required before release, is a Git revert rather than a runtime
compatibility mechanism.
