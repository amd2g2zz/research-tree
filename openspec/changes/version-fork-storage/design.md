# design — version-fork-storage

VersionStore shares the LedgerStore's SQLite connection (one store file, one
migration authority — v3 rides LedgerStore's registry). Draft working sets are
canonical-JSON rows; the version hash covers the whole snapshot so any partial
commit is structurally impossible; verifyIntegrity re-hashes for tamper
evidence. commit_hash uniqueness is **per task**: identical snapshots across
tasks are the fork inheritance semantics (分叉即继承), identical re-commits
within a task are rejected.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Global commit_hash uniqueness (would outlaw fork inheritance — the A7 axiom).
- UPDATE paths on versions (append-only; tamper detected by re-hash).
- Draft deletion at freeze (the draft persists as the working state; the next
  freeze requires content change — git-like nothing-to-commit).
- Content-hash excluding deleted_nodes (产物删除 must be snapshot-addressable
  and disclosed).
