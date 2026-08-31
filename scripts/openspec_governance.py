from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

LIFECYCLE_STATES = frozenset({"planned", "in_progress", "blocked", "unavailable", "verified", "superseded"})
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


@dataclass(frozen=True)
class GroupDefinition:
    group: int
    depends_on: tuple[int, ...]
    owner: str
    outputs: tuple[str, ...]
    acceptance_command: str
    rollback: str


@dataclass(frozen=True)
class VerificationRecord:
    group: int
    state: str
    evidence_refs: tuple[str, ...]
    command_receipt: Mapping[str, Any] | None
    rollback: str | None
    blocker: str | None


@dataclass(frozen=True)
class IssueExecutionMapping:
    issue: int
    primary_group: int
    supporting_groups: tuple[int, ...]
    capabilities: tuple[str, ...]
    openspec_change: str


@dataclass(frozen=True)
class CapabilityRow:
    capability: str
    issue: int
    task_groups: tuple[int, ...]


@dataclass(frozen=True)
class GovernanceInputs:
    groups: tuple[GroupDefinition, ...]
    verification: tuple[VerificationRecord, ...]
    issues: tuple[IssueExecutionMapping, ...]
    capabilities: tuple[CapabilityRow, ...]


@dataclass(frozen=True)
class GovernanceViolation:
    code: str
    subject: int | str
    message: str
    path: tuple[int, ...] = ()
    observed_state: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "subject": self.subject,
            "message": self.message,
            "path": list(self.path),
            "observed_state": self.observed_state,
        }


@dataclass(frozen=True)
class GovernanceReport:
    valid: bool
    release_ready: bool
    verified_groups: tuple[int, ...]
    unverified_groups: tuple[int, ...]
    unavailable_groups: tuple[int, ...]
    violations: tuple[GovernanceViolation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "release_ready": self.release_ready,
            "verified_groups": list(self.verified_groups),
            "unverified_groups": list(self.unverified_groups),
            "unavailable_groups": list(self.unavailable_groups),
            "violations": [violation.as_dict() for violation in self.violations],
        }


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    if payload.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version: {path}")
    return payload


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _int_list(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return tuple(_positive_int(item, field) for item in value)


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return tuple(_string(item, field) for item in value)


def _load_groups(path: Path) -> tuple[GroupDefinition, ...]:
    payload = _read_json(path)
    raw_groups = payload.get("groups")
    if not isinstance(raw_groups, list):
        raise ValueError("groups must be a list")
    groups: list[GroupDefinition] = []
    for raw in raw_groups:
        if not isinstance(raw, dict):
            raise ValueError("group must be an object")
        groups.append(
            GroupDefinition(
                group=_positive_int(raw.get("group"), "group"),
                depends_on=_int_list(raw.get("depends_on"), "depends_on"),
                owner=_string(raw.get("owner"), "owner"),
                outputs=_string_list(raw.get("outputs"), "outputs"),
                acceptance_command=_string(raw.get("acceptance_command"), "acceptance_command"),
                rollback=_string(raw.get("rollback"), "rollback"),
            )
        )
    return tuple(groups)


def _load_verification(path: Path) -> tuple[VerificationRecord, ...]:
    payload = _read_json(path)
    raw_records = payload.get("groups")
    if not isinstance(raw_records, list):
        raise ValueError("verification groups must be a list")
    records: list[VerificationRecord] = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError("verification record must be an object")
        state = _string(raw.get("state"), "state")
        if state not in LIFECYCLE_STATES:
            raise ValueError(f"unknown lifecycle state: {state}")
        evidence = raw.get("evidence_refs", [])
        if not isinstance(evidence, list) or not all(isinstance(value, str) and value for value in evidence):
            raise ValueError("evidence_refs must be a string list")
        receipt = raw.get("command_receipt")
        if receipt is not None and not isinstance(receipt, dict):
            raise ValueError("command_receipt must be an object")
        rollback = raw.get("rollback")
        blocker = raw.get("blocker")
        if rollback is not None and not isinstance(rollback, str):
            raise ValueError("rollback must be a string")
        if blocker is not None and not isinstance(blocker, str):
            raise ValueError("blocker must be a string")
        records.append(
            VerificationRecord(
                group=_positive_int(raw.get("group"), "verification group"),
                state=state,
                evidence_refs=tuple(evidence),
                command_receipt=receipt,
                rollback=rollback,
                blocker=blocker,
            )
        )
    return tuple(records)


def _load_issues(path: Path) -> tuple[IssueExecutionMapping, ...]:
    payload = _read_json(path)
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raise ValueError("issues must be a list")
    issues: list[IssueExecutionMapping] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            raise ValueError("issue mapping must be an object")
        issues.append(
            IssueExecutionMapping(
                issue=_positive_int(raw.get("issue"), "issue"),
                primary_group=_positive_int(raw.get("primary_group"), "primary_group"),
                supporting_groups=_int_list(raw.get("supporting_groups"), "supporting_groups"),
                capabilities=_string_list(raw.get("capabilities"), "capabilities"),
                openspec_change=_string(raw.get("openspec_change"), "openspec_change"),
            )
        )
    return tuple(issues)


def _load_capabilities(path: Path) -> tuple[CapabilityRow, ...]:
    payload = _read_json(path)
    raw_rows = payload.get("capability_rows")
    if not isinstance(raw_rows, list):
        raise ValueError("capability_rows must be a list")
    rows: list[CapabilityRow] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("capability row must be an object")
        raw_issue = _string(raw.get("github_issue"), "github_issue")
        if re.fullmatch(r"#[1-9][0-9]*", raw_issue) is None:
            raise ValueError("github_issue must use #<positive integer>")
        rows.append(
            CapabilityRow(
                capability=_string(raw.get("capability"), "capability"),
                issue=int(raw_issue[1:]),
                task_groups=_int_list(raw.get("task_groups"), "task_groups"),
            )
        )
    return tuple(rows)


def load_governance_inputs(
    group_path: Path,
    verification_path: Path,
    issue_path: Path,
    capability_path: Path,
) -> GovernanceInputs:
    return GovernanceInputs(
        groups=_load_groups(group_path),
        verification=_load_verification(verification_path),
        issues=_load_issues(issue_path),
        capabilities=_load_capabilities(capability_path),
    )


def _violation_key(violation: GovernanceViolation) -> tuple[Any, ...]:
    return (
        violation.code,
        str(violation.subject),
        violation.path,
        violation.observed_state or "",
        violation.message,
    )


def _find_cycles(groups: Mapping[int, GroupDefinition]) -> list[tuple[int, ...]]:
    cycles: set[tuple[int, ...]] = set()
    visiting: list[int] = []
    visited: set[int] = set()

    def visit(group_id: int) -> None:
        if group_id in visiting:
            cycle = tuple(visiting[visiting.index(group_id) :] + [group_id])
            rotated = min(tuple(cycle[index:-1] + cycle[:index] + (cycle[index],)) for index in range(len(cycle) - 1))
            cycles.add(rotated)
            return
        if group_id in visited or group_id not in groups:
            return
        visiting.append(group_id)
        for dependency in groups[group_id].depends_on:
            visit(dependency)
        visiting.pop()
        visited.add(group_id)

    for group_id in sorted(groups):
        visit(group_id)
    return sorted(cycles)


def _verification_is_complete(record: VerificationRecord, definition: GroupDefinition | None) -> bool:
    if record.state != "verified":
        return True
    receipt = record.command_receipt
    if definition is None or not record.evidence_refs or not record.rollback or not isinstance(receipt, Mapping):
        return False
    command = receipt.get("command")
    exit_code = receipt.get("exit_code")
    environment = receipt.get("environment_digest")
    output = receipt.get("output_digest")
    source_revision = receipt.get("source_revision")
    raw_output_ref = receipt.get("raw_output_ref")
    recorded_at = receipt.get("recorded_at")
    return (
        command == definition.acceptance_command
        and exit_code == 0
        and isinstance(environment, str)
        and _DIGEST.fullmatch(environment) is not None
        and isinstance(output, str)
        and _DIGEST.fullmatch(output) is not None
        and isinstance(source_revision, str)
        and _COMMIT.fullmatch(source_revision) is not None
        and isinstance(raw_output_ref, str)
        and bool(raw_output_ref)
        and isinstance(recorded_at, str)
        and bool(recorded_at)
    )


def _entrypoint_exists_at_source_revision(repository: Path, source_revision: str, entrypoint: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "cat-file", "-e", f"{source_revision}:{entrypoint}"],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return completed.returncode == 0


def _source_revision_is_ancestor(repository: Path, source_revision: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_revision, "HEAD"],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return completed.returncode == 0


def _missing_acceptance_entrypoints(
    command: str,
    repository: Path,
    source_revision: str | None,
) -> tuple[str, ...]:
    tokens = shlex.split(command, posix=False)
    missing: list[str] = []
    for raw_token in tokens:
        token = raw_token.strip("\"'")
        candidate = Path(token)
        if candidate.suffix != ".py" or candidate.is_absolute():
            continue
        if (repository / candidate).is_file():
            continue
        if (
            source_revision is not None
            and _source_revision_is_ancestor(repository, source_revision)
            and _entrypoint_exists_at_source_revision(
                repository,
                source_revision,
                candidate.as_posix(),
            )
        ):
            continue
        missing.append(candidate.as_posix())
    return tuple(sorted(set(missing)))


def _dependency_violation(
    group_id: int,
    groups: Mapping[int, GroupDefinition],
    verification: Mapping[int, VerificationRecord],
) -> GovernanceViolation | None:
    queue: deque[tuple[int, tuple[int, ...]]] = deque([(group_id, (group_id,))])
    seen = {group_id}
    while queue:
        current, path = queue.popleft()
        definition = groups.get(current)
        if definition is None:
            continue
        for dependency in sorted(definition.depends_on):
            dependency_path = path + (dependency,)
            if dependency not in groups:
                return GovernanceViolation(
                    code="missing_task_group",
                    subject=group_id,
                    message=f"dependency group {dependency} is not registered",
                    path=dependency_path,
                )
            record = verification.get(dependency)
            if record is None:
                return GovernanceViolation(
                    code="missing_verification_record",
                    subject=group_id,
                    message=f"dependency group {dependency} has no verification record",
                    path=dependency_path,
                )
            if record.state != "verified":
                return GovernanceViolation(
                    code="unverified_dependency",
                    subject=group_id,
                    message=f"dependency group {dependency} is {record.state}",
                    path=dependency_path,
                    observed_state=record.state,
                )
            if dependency not in seen:
                seen.add(dependency)
                queue.append((dependency, dependency_path))
    return None


def validate_governance(inputs: GovernanceInputs, *, repository: Path | None = None) -> GovernanceReport:
    violations: list[GovernanceViolation] = []
    groups: dict[int, GroupDefinition] = {}
    for definition in inputs.groups:
        if definition.group in groups:
            violations.append(
                GovernanceViolation(
                    code="duplicate_task_group",
                    subject=definition.group,
                    message=f"task group {definition.group} is declared more than once",
                )
            )
        groups[definition.group] = definition

    verification: dict[int, VerificationRecord] = {}
    for record in inputs.verification:
        if record.group in verification:
            violations.append(
                GovernanceViolation(
                    code="duplicate_verification_record",
                    subject=record.group,
                    message=f"task group {record.group} has multiple verification records",
                )
            )
        verification[record.group] = record
        if record.group not in groups:
            violations.append(
                GovernanceViolation(
                    code="verification_for_unknown_group",
                    subject=record.group,
                    message=f"verification record targets unknown group {record.group}",
                )
            )

    for group_id in sorted(groups):
        record = verification.get(group_id)
        if record is None:
            violations.append(
                GovernanceViolation(
                    code="missing_verification_record",
                    subject=group_id,
                    message=f"task group {group_id} has no verification record",
                )
            )
            continue
        if not _verification_is_complete(record, groups.get(group_id)):
            violations.append(
                GovernanceViolation(
                    code="verified_record_incomplete",
                    subject=group_id,
                    message=f"verified group {group_id} lacks complete evidence or receipt",
                )
            )
        if repository is not None and record.state == "verified":
            receipt = record.command_receipt
            source_revision = receipt.get("source_revision") if isinstance(receipt, Mapping) else None
            for entrypoint in _missing_acceptance_entrypoints(
                groups[group_id].acceptance_command,
                repository,
                source_revision if isinstance(source_revision, str) else None,
            ):
                violations.append(
                    GovernanceViolation(
                        code="missing_acceptance_entrypoint",
                        subject=group_id,
                        message=(f"verified group {group_id} acceptance entrypoint does not exist: {entrypoint}"),
                    )
                )

    for cycle in _find_cycles(groups):
        violations.append(
            GovernanceViolation(
                code="dependency_cycle",
                subject=cycle[0],
                message="dependency cycle detected",
                path=cycle,
            )
        )

    for group_id in sorted(groups):
        record = verification.get(group_id)
        if record is not None and record.state == "verified":
            violation = _dependency_violation(group_id, groups, verification)
            if violation is not None:
                violations.append(violation)

    issue_map: dict[int, IssueExecutionMapping] = {}
    primary_owners: dict[int, int] = {}
    for mapping in inputs.issues:
        if mapping.issue in issue_map:
            violations.append(
                GovernanceViolation(
                    code="duplicate_issue_mapping",
                    subject=mapping.issue,
                    message=f"issue #{mapping.issue} is mapped more than once",
                )
            )
        issue_map[mapping.issue] = mapping
        prior = primary_owners.get(mapping.primary_group)
        if prior is not None:
            violations.append(
                GovernanceViolation(
                    code="duplicate_primary_group_owner",
                    subject=mapping.primary_group,
                    message=(f"task group {mapping.primary_group} is owned by issues #{prior} and #{mapping.issue}"),
                )
            )
        primary_owners[mapping.primary_group] = mapping.issue
        for group_id in (mapping.primary_group, *mapping.supporting_groups):
            if group_id not in groups:
                violations.append(
                    GovernanceViolation(
                        code="missing_task_group",
                        subject=mapping.issue,
                        message=f"issue #{mapping.issue} references missing group {group_id}",
                        path=(group_id,),
                    )
                )

    for row in inputs.capabilities:
        mapping = issue_map.get(row.issue)
        if mapping is None:
            violations.append(
                GovernanceViolation(
                    code="missing_issue_mapping",
                    subject=row.capability,
                    message=f"capability {row.capability} references unmapped issue #{row.issue}",
                )
            )
            continue
        if row.capability not in mapping.capabilities:
            violations.append(
                GovernanceViolation(
                    code="capability_owner_mismatch",
                    subject=row.capability,
                    message=(f"issue #{row.issue} does not own capability {row.capability}"),
                )
            )
        allowed_groups = {mapping.primary_group, *mapping.supporting_groups}
        for group_id in row.task_groups:
            if group_id not in groups:
                violations.append(
                    GovernanceViolation(
                        code="missing_task_group",
                        subject=row.capability,
                        message=f"capability {row.capability} references missing group {group_id}",
                        path=(group_id,),
                    )
                )
            elif group_id not in allowed_groups:
                violations.append(
                    GovernanceViolation(
                        code="capability_owner_mismatch",
                        subject=row.capability,
                        message=(f"group {group_id} is not owned or supported by issue #{row.issue}"),
                        path=(group_id,),
                    )
                )

    ordered_violations = tuple(sorted(set(violations), key=_violation_key))
    verified_groups = tuple(sorted(group_id for group_id, record in verification.items() if record.state == "verified"))
    unavailable_groups = tuple(
        sorted(group_id for group_id, record in verification.items() if record.state == "unavailable")
    )
    unverified_groups = tuple(sorted(group_id for group_id in groups if group_id not in verified_groups))
    valid = not ordered_violations
    return GovernanceReport(
        valid=valid,
        release_ready=valid and not unverified_groups,
        verified_groups=verified_groups,
        unverified_groups=unverified_groups,
        unavailable_groups=unavailable_groups,
        violations=ordered_violations,
    )


def default_registry_paths(repository: Path) -> tuple[Path, Path, Path, Path]:
    registry_root = repository / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"
    return (
        registry_root / "task-execution-v1.json",
        registry_root / "task-verification-v1.json",
        registry_root / "issue-execution-map-v1.json",
        registry_root / "delivery-matrix-v1.json",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Alpha2 OpenSpec execution governance")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--task-registry", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--issue-map", type=Path)
    parser.add_argument("--delivery-matrix", type=Path)
    parser.add_argument("--require-release-ready", action="store_true")
    args = parser.parse_args(argv)

    defaults = default_registry_paths(args.repo)
    paths = (
        args.task_registry or defaults[0],
        args.verification or defaults[1],
        args.issue_map or defaults[2],
        args.delivery_matrix or defaults[3],
    )
    try:
        report = validate_governance(load_governance_inputs(*paths), repository=args.repo.resolve())
    except ValueError as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, sort_keys=True))
        return 2
    print(json.dumps(report.as_dict(), sort_keys=True))
    return 0 if report.valid and (not args.require_release_ready or report.release_ready) else 1
