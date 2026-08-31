## Context

Issue #66 and PR #103 added the Alpha2 ADRs and ratification tests, but task group 14 remains planned. Its acceptance command names a missing script, while the umbrella task description also assigns schemas owned by downstream groups 25-27 to group 14. Governance already validates cycles and source-bound receipt fields, but it does not check whether a verified group's repository-relative Python entrypoints exist.

## Goals / Non-Goals

**Goals:**

- Make group 14 independently executable from the merged ratification sources.
- Detect missing repository-relative Python entrypoints for verified groups.
- Keep the task dependency graph acyclic and make downstream output ownership explicit.
- Bind verification evidence to an immutable source revision.

**Non-Goals:**

- Implement schemas or runtime behavior owned by groups 25-27.
- Require planned future groups to have their acceptance entrypoints before implementation.
- Mark downstream groups verified or declare Alpha2 release-ready.

## Decisions

1. `scripts/validate_contracts.py` is a small tracked acceptance adapter over the focused ratification tests. Reusing the test oracle avoids creating a second contract parser whose rules could drift.
2. Governance validates repository-relative `.py` command operands only when a group is verified and a repository root is supplied. Planned commands remain design intent; verified commands must be executable at their recorded source.
3. Group 14's umbrella tasks describe only the ADR, lifecycle, traceability, and registry checks delivered by issue #66. SourceCapture, NativeWorkflowRun, and SearchPortfolio remain exclusively in groups 25-27.
4. The receipt is recorded only after an implementation commit exists. The command output and environment are digested, and the receipt references that commit and raw output. A follow-up evidence commit may add the receipt without falsifying the source revision.

## Risks / Trade-offs

- [Risk] The acceptance adapter delegates to pytest and therefore requires the development environment. -> Mitigation: the registered command already uses `uv`, and CI/maintainer verification is the intended execution context.
- [Risk] Command parsing could become a shell implementation. -> Mitigation: only repository-relative `.py` operands are extracted; execution stays with the original command.
- [Risk] A receipt produced before commit would not bind the implementation. -> Mitigation: keep receipt publication as the final post-implementation step and reject placeholder revisions.

## Migration Plan

1. Add red governance and contract-entrypoint tests.
2. Add the validator and source-resolution check; narrow group 14 task ownership.
3. Commit the implementation, run the acceptance command from that revision, and record output/digests in a second evidence commit.
4. Roll back the registry state, validator, receipt, and ownership text together if verification fails.

## Open Questions

None.
