<!--
PR checklist (mandatory per openspec/changes/establish-dev-integration-governance
and ADR-008). Fill every section; a reviewer will not start a review while a
checkbox is unchecked, and no CI failure may be ignored (no admin override).
-->

## Closes

Closes #N

## OpenSpec change

- Change id: `<change-id>` (openspec/changes/<change-id>/, archived after merge)

## GitNexus impact report

> Run before edits: `node .gitnexus/run.cjs impact "<symbol>" --direction upstream`
> for every modified symbol; index freshness is guaranteed by the wave system
> (rebuild after each merge). State the bound identity:
> Repository: `<name> (<path>)  Worktree: <path>  Index: <commit>`

| Symbol | Change | Risk | Direct upstream callers | Affected processes |
|---|---|---|---|---|
| | | | | |

- Blast radius risk level: **LOW / MEDIUM / HIGH / CRITICAL**
- [ ] If HIGH or CRITICAL: flagged here AND reviewer escalation requested (AGENTS.md forbids proceeding on an unflagged HIGH/CRITICAL radius)

## detect_changes ↔ impact_scope consistency

- [ ] `node .gitnexus/run.cjs detect-changes --scope compare --base-ref dev` output saved to `openspec/changes/<change-id>/evidence/`
- [ ] Reconciled with the change's declared `impact_scope` via `uv run python scripts/check_impact_scope.py` — **pass** (changed symbols/files fall entirely inside the declared scope)
- [ ] Any deviation from `impact_scope` is listed here with a reason

## Scenario → test mapping

| Spec scenario (openspec change) | Test |
|---|---|
| | |

## Local gates (all must be green before opening the PR)

- [ ] `uv run --frozen pytest -q` — <result, no NEW failures vs baseline>
- [ ] `uv run --frozen ruff check . && uv run --frozen ruff format --check .` — <result>
- [ ] `uv run --frozen python scripts/check_delivery_workflow.py validate` — <result>
- [ ] `uv run --frozen python scripts/check_openspec_governance.py` — <result>
- [ ] `uv run --frozen python scripts/build_skill_packages.py --check` — <result> (required if `skill-src/`, `references/`, or `assets/` changed)

## Rejected-design compliance (reviewer)

- [ ] The diff does not reintroduce rejected designs: engine behavior
  enumeration (13-action menus, fixed selection ladders), quote-ratio regex
  policing, or prompt-layer prose pretending to be enforced (ADR-008 design
  test: enum entry for what the model says = violation; verifiable trace
  type = conforms)

## PR size

- Files changed: <n> (split-review limit 25, hard 50)
- Non-generated lines: <n> (split-review limit 800, hard 1500; `packages/**` lines are generated)
