## Context

`src/research_tree/scheduler.py` provides a legacy `RunStore` writer for
`work-portfolio` artifacts. The only current package-level caller is the root
export block, and the dedicated behavior suite is `tests/test_scheduler.py`.
No supported CLI or runtime module imports the scheduler.

Issue #178 is deliberately the first of two deletion slices. Its output is an
unreachable source module: no root export, runtime caller, active contract,
registry, current documentation claim, or dedicated behavior test remains.
Issue #179 will delete the private source file after this slice is merged.

## Goals / Non-Goals

**Goals:**

- Remove every supported public scheduler symbol and current authority claim.
- Delete scheduler-specific behavior coverage and replace it with minimal API
  absence coverage.
- Register group 62 with a source-only acceptance command and current-only
  rollback boundary.
- Preserve `docs/specs/RT-010.md` as historical material and retain the
  physically present source file only as an unreachable implementation detail.

**Non-Goals:**

- Deleting or refactoring `scheduler.py`; that is #179.
- Replacing, wrapping, renaming, aliasing, adapting, migrating, or falling back
  from the scheduler boundary.
- Reading, importing, moving, repairing, or changing user-owned RunStore or
  portfolio data.
- Rewriting independently current `orchestration.py` behavior.

## Decisions

### Remove publication rather than retain a compatibility response

The root import and `__all__` names are deleted. A warning, exception shim, or
deprecated facade would remain a supported boundary and contradict the
current-only policy.

### Treat the retained module as unreachable private source

The source file remains because its physical removal is a distinct size-bounded
review slice. The regression only proves that its symbols are not reachable
from the public root package; it does not turn the module into a supported
private API or add any access path.

### Update active authority, preserve historical material

The active Alpha2 change, registries, current operating documentation, and
current contract requirements remove scheduler claims. `docs/specs/RT-010.md`
remains governed historical material and is not rewritten. Older archived
OpenSpec artifacts remain audit history, not active behavior.

### Use group 62 without unmerged dependencies

Group 62 owns issue #178 independently. It depends only on already merged
groups 54 and 55 because the deletion needs no evidence, FindingPack, or
insight compatibility work to remove an unreachable public surface.

## Risks / Trade-offs

- [Existing package users lose imports] -> Deliberate breaking cutover; recover
  only by reverting the release revision.
- [The source module remains importable by its file path] -> Accepted temporary
  private residue, with no current caller, contract, or public export; #179
  deletes it.
- [A future registry reintroduces the boundary] -> An absence test reads the
  active authorities and rejects scheduler claims.

## Migration Plan

1. Register group 62 and the removal requirements as planned.
2. Add the failing root-surface absence regression.
3. Delete root exports, the dedicated scheduler suite, and active scheduler
   authority claims; leave the source file untouched.
4. Run focused, governance, strict OpenSpec, and full tests, then commit source
   changes. A later source-bound receipt is outside this source-only commit.

## Open Questions

None. #179 owns physical source deletion after #178 is merged.
