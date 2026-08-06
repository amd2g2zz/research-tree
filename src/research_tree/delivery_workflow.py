from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ReviewLimit:
    files: int
    non_generated_lines: int


@dataclass(frozen=True)
class DeliveryPolicy:
    schema_version: int
    repository_default_branch: str
    integration_branch: str
    release_branch: str
    delivery_branch_pattern: str
    release_branch_pattern: str
    delivery_issue_pattern: str
    split_review: ReviewLimit
    hard_limit: ReviewLimit
    generated_paths: tuple[str, ...]
    canonical_generation_inputs: tuple[str, ...]
    protected_branches: Mapping[str, Mapping[str, bool]]


@dataclass(frozen=True)
class ValidationResult:
    command: str
    exit_code: int
    summary: str


@dataclass(frozen=True)
class BootstrapReceipt:
    schema_version: int
    repository: str
    default_branch: str
    integration_branch: str
    source_ref: str
    source_sha: str
    created_at: str
    validation_results: tuple[ValidationResult, ...]
    unavailable_baseline_checks: tuple[tuple[str, str], ...]
    branch_protection: Mapping[str, Mapping[str, bool]]
    bootstrap_exception: str


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    receipt: Mapping[str, Any]


@dataclass(frozen=True)
class PullRequestResult:
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    details: Mapping[str, Any]


@dataclass(frozen=True)
class WorktreeRecord:
    path: str
    branch: str | None
    head: str
    dirty: bool
    reachable_from_dev: bool
    pr_state: str | None
    branch_has_later_commits: bool


@dataclass(frozen=True)
class CleanupDisposition:
    action: str
    reason: str
    destructive: bool = False


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


def _positive_integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def load_delivery_policy(path: Path) -> DeliveryPolicy:
    payload = _load_json(path)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported delivery policy schema_version")

    limits = payload.get("review_limits")
    if not isinstance(limits, dict):
        raise ValueError("review_limits must be an object")
    split_payload = limits.get("split_review")
    hard_payload = limits.get("hard_limit")
    if not isinstance(split_payload, dict) or not isinstance(hard_payload, dict):
        raise ValueError("review limit entries must be objects")
    split = ReviewLimit(
        files=_positive_integer(split_payload.get("files"), "split file limit"),
        non_generated_lines=_positive_integer(
            split_payload.get("non_generated_lines"),
            "split non-generated line limit",
        ),
    )
    hard = ReviewLimit(
        files=_positive_integer(hard_payload.get("files"), "hard file limit"),
        non_generated_lines=_positive_integer(
            hard_payload.get("non_generated_lines"),
            "hard non-generated line limit",
        ),
    )
    if hard.files <= split.files:
        raise ValueError("hard file limit must exceed split file limit")
    if hard.non_generated_lines <= split.non_generated_lines:
        raise ValueError(
            "hard non-generated line limit must exceed split non-generated line limit"
        )

    strings = {
        name: payload.get(name)
        for name in (
            "repository_default_branch",
            "integration_branch",
            "release_branch",
            "delivery_branch_pattern",
            "release_branch_pattern",
            "delivery_issue_pattern",
        )
    }
    if any(not isinstance(value, str) or not value for value in strings.values()):
        raise ValueError("branch names and patterns must be non-empty strings")
    if strings["repository_default_branch"] != strings["release_branch"]:
        raise ValueError("repository default branch must be the release branch")
    if strings["integration_branch"] == strings["release_branch"]:
        raise ValueError("integration and release branches must be distinct")
    for field in (
        "delivery_branch_pattern",
        "release_branch_pattern",
        "delivery_issue_pattern",
    ):
        try:
            re.compile(strings[field])
        except re.error as exc:
            raise ValueError(f"invalid {field}") from exc

    generated_paths = payload.get("generated_paths")
    canonical_inputs = payload.get("canonical_generation_inputs")
    protected = payload.get("protected_branches")
    if not isinstance(generated_paths, list) or not all(
        isinstance(item, str) and item for item in generated_paths
    ):
        raise ValueError("generated_paths must be a non-empty string list")
    if not isinstance(canonical_inputs, list) or not all(
        isinstance(item, str) and item for item in canonical_inputs
    ):
        raise ValueError("canonical_generation_inputs must be a string list")
    if not isinstance(protected, dict):
        raise ValueError("protected_branches must be an object")
    for branch in (strings["integration_branch"], strings["release_branch"]):
        rules = protected.get(branch)
        if not isinstance(rules, dict):
            raise ValueError(f"missing protection policy for {branch}")
        for key in (
            "required_pull_request",
            "allow_force_pushes",
            "allow_deletions",
            "required_conversation_resolution",
        ):
            if not isinstance(rules.get(key), bool):
                raise ValueError(f"invalid protection field {branch}.{key}")

    return DeliveryPolicy(
        schema_version=1,
        repository_default_branch=strings["repository_default_branch"],
        integration_branch=strings["integration_branch"],
        release_branch=strings["release_branch"],
        delivery_branch_pattern=strings["delivery_branch_pattern"],
        release_branch_pattern=strings["release_branch_pattern"],
        delivery_issue_pattern=strings["delivery_issue_pattern"],
        split_review=split,
        hard_limit=hard,
        generated_paths=tuple(generated_paths),
        canonical_generation_inputs=tuple(canonical_inputs),
        protected_branches=protected,
    )


def load_bootstrap_receipt(path: Path, policy: DeliveryPolicy) -> BootstrapReceipt:
    payload = _load_json(path)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported bootstrap receipt schema_version")
    source_sha = payload.get("source_sha")
    if not isinstance(source_sha, str) or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("source_sha must be a lowercase 40-character Git SHA")
    default_branch = payload.get("repository_default_branch")
    integration_branch = payload.get("integration_branch")
    if default_branch != policy.repository_default_branch:
        raise ValueError("bootstrap default branch does not match delivery policy")
    if integration_branch != policy.integration_branch:
        raise ValueError("bootstrap integration branch does not match delivery policy")

    raw_results = payload.get("validation_results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError("validation_results must be non-empty")
    results: list[ValidationResult] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise ValueError("validation result must be an object")
        command = raw.get("command")
        exit_code = raw.get("exit_code")
        summary = raw.get("summary")
        if not isinstance(command, str) or not command:
            raise ValueError("validation command must be non-empty")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise ValueError("validation exit_code must be an integer")
        if not isinstance(summary, str) or not summary:
            raise ValueError("validation summary must be non-empty")
        results.append(ValidationResult(command, exit_code, summary))
    if any(result.exit_code != 0 for result in results):
        raise ValueError("bootstrap validation results must all pass")

    raw_unavailable = payload.get("unavailable_baseline_checks")
    if not isinstance(raw_unavailable, list):
        raise ValueError("unavailable_baseline_checks must be an array")
    unavailable: list[tuple[str, str]] = []
    for raw in raw_unavailable:
        if not isinstance(raw, dict):
            raise ValueError("unavailable baseline check must be an object")
        command = raw.get("command")
        reason = raw.get("reason")
        if not isinstance(command, str) or not command:
            raise ValueError("unavailable baseline command must be non-empty")
        if not isinstance(reason, str) or not reason:
            raise ValueError("unavailable baseline reason must be non-empty")
        unavailable.append((command, reason))

    protection = payload.get("branch_protection")
    if not isinstance(protection, dict):
        raise ValueError("branch_protection must be an object")
    for branch, expected in policy.protected_branches.items():
        actual = protection.get(branch)
        if not isinstance(actual, dict):
            raise ValueError(f"bootstrap receipt lacks protection for {branch}")
        for key, value in expected.items():
            if actual.get(key) is not value:
                raise ValueError(f"bootstrap protection mismatch: {branch}.{key}")

    repository = payload.get("repository")
    source_ref = payload.get("source_ref")
    created_at = payload.get("created_at")
    bootstrap_exception = payload.get("bootstrap_exception")
    for value, field in (
        (repository, "repository"),
        (source_ref, "source_ref"),
        (created_at, "created_at"),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
    try:
        datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise ValueError("created_at must be an ISO-8601 timestamp") from exc
    if not isinstance(bootstrap_exception, str) or not bootstrap_exception:
        raise ValueError("bootstrap_exception must be a non-empty string")

    return BootstrapReceipt(
        schema_version=1,
        repository=repository,
        default_branch=default_branch,
        integration_branch=integration_branch,
        source_ref=source_ref,
        source_sha=source_sha,
        created_at=created_at,
        validation_results=tuple(results),
        unavailable_baseline_checks=tuple(unavailable),
        branch_protection=protection,
        bootstrap_exception=bootstrap_exception,
    )


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {message}")
    return completed.stdout.strip()


def _run(
    command: Sequence[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"{' '.join(command)} failed: {message}")
    return completed


def _branch_issue(policy: DeliveryPolicy, branch: str) -> int | None:
    match = re.fullmatch(policy.delivery_branch_pattern, branch)
    if match is None:
        return None
    return int(match.group("issue"))


def _canonical_worktree_path(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    if os.name == "nt" or re.match(r"^[A-Za-z]:/", normalized):
        return normalized.casefold()
    return normalized


def run_preflight(
    repository: Path,
    *,
    issue: int,
    base_ref: str,
    policy: DeliveryPolicy,
    remote_issue_owners: Mapping[int, Sequence[str]] | None,
    registered_worktree_paths: Sequence[str] | None = None,
) -> CheckResult:
    repository = repository.resolve()
    branch = _git(repository, "branch", "--show-current")
    head = _git(repository, "rev-parse", "HEAD")
    base = _git(repository, "rev-parse", base_ref)
    status = _git(repository, "status", "--porcelain", "--untracked-files=all")
    errors: list[str] = []

    branch_issue = _branch_issue(policy, branch)
    if branch_issue != issue:
        errors.append("invalid_branch_name")
    if status:
        errors.append("worktree_not_clean")
    if head != base:
        errors.append("stale_or_diverged_base")
    if registered_worktree_paths is None:
        registered_worktree_paths = [
            str(record.get("worktree"))
            for record in _parse_worktree_porcelain(
                _git(repository, "worktree", "list", "--porcelain")
            )
            if record.get("worktree") is not None
        ]
    current_path = _canonical_worktree_path(str(repository))
    matching_paths = [
        path
        for path in registered_worktree_paths
        if _canonical_worktree_path(path) == current_path
    ]
    if len(matching_paths) != 1:
        errors.append("duplicate_worktree_path")
    if remote_issue_owners is None:
        errors.append("remote_metadata_unavailable")
        owners: Sequence[str] = ()
    else:
        owners = remote_issue_owners.get(issue, ())
        normalized = {owner.casefold() for owner in owners}
        if len(normalized) != 1 or branch.casefold() not in normalized:
            errors.append("duplicate_issue_owner")

    receipt = {
        "schema_version": 1,
        "issue": issue,
        "repository": str(repository),
        "branch": branch,
        "head_sha": head,
        "base_ref": base_ref,
        "base_sha": base,
        "clean": not bool(status),
        "remote_issue_owners": list(owners),
        "registered_path_matches": len(matching_paths),
    }
    return CheckResult(
        passed=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=(),
        receipt=receipt,
    )


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def evaluate_pull_request(
    *,
    policy: DeliveryPolicy,
    base_branch: str,
    head_branch: str,
    title: str,
    body: str,
    changed_files: Sequence[str],
    non_generated_lines: int,
    commit_file_sets: Sequence[set[str]],
    approved_exception: bool = False,
    release_derived_from_dev: bool | None = None,
    release_has_unintegrated_commits: bool | None = None,
) -> PullRequestResult:
    del title
    errors: list[str] = []
    warnings: list[str] = []
    is_release = re.fullmatch(policy.release_branch_pattern, head_branch) is not None
    if is_release:
        if base_branch != policy.release_branch:
            errors.append("invalid_release_base")
        if release_derived_from_dev is not True:
            errors.append("release_not_derived_from_dev")
        if release_has_unintegrated_commits is not False:
            errors.append("release_contains_unintegrated_commits")
    elif base_branch != policy.integration_branch:
        errors.append("invalid_base_branch")

    branch_issue = _branch_issue(policy, head_branch)
    issue_ids = {
        int(match.group("issue"))
        for match in re.finditer(policy.delivery_issue_pattern, body)
    }
    if not is_release:
        if len(issue_ids) > 1:
            errors.append("multiple_delivery_issues")
        elif len(issue_ids) == 0:
            errors.append("missing_delivery_issue")
        elif branch_issue not in issue_ids:
            errors.append("branch_issue_mismatch")

    generated = {
        path for path in changed_files if _matches_any(path, policy.generated_paths)
    }
    non_generated = set(changed_files) - generated
    file_count = len(non_generated)
    if (
        file_count > policy.hard_limit.files
        or non_generated_lines > policy.hard_limit.non_generated_lines
    ) and not approved_exception:
        errors.append("hard_review_limit_exceeded")
    elif (
        file_count > policy.split_review.files
        or non_generated_lines > policy.split_review.non_generated_lines
    ):
        warnings.append("split_review_required")

    canonical_changed = any(
        _matches_any(path, policy.canonical_generation_inputs)
        for path in non_generated
    )
    if generated and not canonical_changed:
        errors.append("generated_output_without_source_change")
    for commit_paths in commit_file_sets:
        commit_generated = {
            path for path in commit_paths if _matches_any(path, policy.generated_paths)
        }
        if commit_generated and commit_generated != commit_paths:
            errors.append("generated_output_mixed_with_source_commit")
            break

    return PullRequestResult(
        passed=not errors,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
        details={
            "base_branch": base_branch,
            "head_branch": head_branch,
            "delivery_issues": sorted(issue_ids),
            "non_generated_files": file_count,
            "generated_files": len(generated),
            "non_generated_lines": non_generated_lines,
            "release_derived_from_dev": release_derived_from_dev,
            "release_has_unintegrated_commits": release_has_unintegrated_commits,
        },
    )


def classify_cleanup(record: WorktreeRecord) -> CleanupDisposition:
    if record.dirty:
        return CleanupDisposition(
            action="preserve_dirty",
            reason="worktree contains tracked or untracked changes",
        )
    if record.branch is None:
        return CleanupDisposition(
            action="requires_disposition",
            reason="detached worktree requires an explicit owner disposition",
        )
    if record.pr_state == "MERGED" and record.reachable_from_dev:
        if not record.branch_has_later_commits:
            return CleanupDisposition(
                action="eligible_for_explicit_removal",
                reason="clean merged head is reachable from dev",
            )
    return CleanupDisposition(
        action="requires_disposition",
        reason="worktree is not proven safe for removal",
    )


def discover_issue_owners(
    repository: Path, policy: DeliveryPolicy
) -> Mapping[int, tuple[str, ...]]:
    owners: dict[int, set[str]] = {}
    current_branch: str | None = None
    for line in _git(repository, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("branch refs/heads/"):
            current_branch = line.removeprefix("branch refs/heads/")
            issue = _branch_issue(policy, current_branch)
            if issue is not None:
                owners.setdefault(issue, set()).add(current_branch)
        elif not line:
            current_branch = None

    remote = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "headRefName",
        ],
        cwd=repository,
        check=False,
    )
    if remote.returncode != 0:
        raise ValueError("remote PR metadata is unavailable")
    try:
        pull_requests = json.loads(remote.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("remote PR metadata is invalid JSON") from exc
    if not isinstance(pull_requests, list):
        raise ValueError("remote PR metadata must be an array")
    for pull_request in pull_requests:
        if not isinstance(pull_request, dict):
            continue
        branch = pull_request.get("headRefName")
        if not isinstance(branch, str):
            continue
        issue = _branch_issue(policy, branch)
        if issue is not None:
            owners.setdefault(issue, set()).add(branch)
    return {issue: tuple(sorted(branches)) for issue, branches in owners.items()}


def _diff_summary(
    repository: Path, base_ref: str, policy: DeliveryPolicy
) -> tuple[list[str], int]:
    output = _git(repository, "diff", "--numstat", f"{base_ref}...HEAD")
    files: list[str] = []
    non_generated_lines = 0
    for line in output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        files.append(path)
        if _matches_any(path, policy.generated_paths):
            continue
        if added.isdigit():
            non_generated_lines += int(added)
        if deleted.isdigit():
            non_generated_lines += int(deleted)
    return files, non_generated_lines


def _commit_file_sets(repository: Path, base_ref: str) -> list[set[str]]:
    commits = _git(repository, "rev-list", "--reverse", f"{base_ref}..HEAD")
    results: list[set[str]] = []
    for commit in commits.splitlines():
        paths = _git(
            repository,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
        )
        results.append({path for path in paths.splitlines() if path})
    return results


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    return (
        _run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repository,
            check=False,
        ).returncode
        == 0
    )


def _parse_worktree_porcelain(output: str) -> list[dict[str, str | None]]:
    records: list[dict[str, str | None]] = []
    current: dict[str, str | None] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key in {"detached", "bare", "prunable", "locked"}:
            current[key] = "true"
        else:
            current[key] = value
    return records


def _pr_metadata(repository: Path, branch: str) -> tuple[str | None, str | None]:
    completed = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--head",
            branch,
            "--limit",
            "1",
            "--json",
            "state,headRefOid",
        ],
        cwd=repository,
        check=False,
    )
    if completed.returncode != 0:
        return None, None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, list) or not payload:
        return None, None
    item = payload[0]
    if not isinstance(item, dict):
        return None, None
    state = item.get("state")
    head = item.get("headRefOid")
    return (
        state if isinstance(state, str) else None,
        head if isinstance(head, str) else None,
    )


def inventory_worktrees(
    repository: Path, *, dev_ref: str = "origin/dev"
) -> tuple[WorktreeRecord, ...]:
    records: list[WorktreeRecord] = []
    raw = _git(repository, "worktree", "list", "--porcelain")
    for item in _parse_worktree_porcelain(raw):
        raw_path = item.get("worktree")
        head = item.get("HEAD")
        if not isinstance(raw_path, str) or not isinstance(head, str):
            continue
        worktree = Path(raw_path).resolve()
        raw_branch = item.get("branch")
        branch = None
        if isinstance(raw_branch, str) and raw_branch.startswith("refs/heads/"):
            branch = raw_branch.removeprefix("refs/heads/")
        status = _git(worktree, "status", "--porcelain", "--untracked-files=all")
        reachable = (
            _run(
                ["git", "merge-base", "--is-ancestor", head, dev_ref],
                cwd=repository,
                check=False,
            ).returncode
            == 0
        )
        pr_state: str | None = None
        pr_head: str | None = None
        if branch is not None:
            pr_state, pr_head = _pr_metadata(repository, branch)
        records.append(
            WorktreeRecord(
                path=str(worktree),
                branch=branch,
                head=head,
                dirty=bool(status),
                reachable_from_dev=reachable,
                pr_state=pr_state,
                branch_has_later_commits=bool(pr_head and pr_head != head),
            )
        )
    return tuple(records)


def _default_change_root() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "openspec"
        / "changes"
        / "establish-dev-integration-governance"
    )


def _json_dump(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    output: Path | None = None,
) -> None:
    if output is None:
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        print(rendered, end="")
        return
    rendered = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def _worktree_payload(record: WorktreeRecord) -> dict[str, Any]:
    return {
        "path": record.path,
        "branch": record.branch,
        "head": record.head,
        "dirty": record.dirty,
        "reachable_from_dev": record.reachable_from_dev,
        "pr_state": record.pr_state,
        "branch_has_later_commits": record.branch_has_later_commits,
    }


def main(argv: Sequence[str] | None = None) -> int:
    change_root = _default_change_root()
    parser = argparse.ArgumentParser(description="Validate issue-isolated delivery")
    parser.add_argument(
        "--policy",
        type=Path,
        default=change_root / "registries" / "delivery-policy-v1.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument(
        "--receipt",
        type=Path,
        default=change_root / "evidence" / "dev-bootstrap-v1.json",
    )

    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--repo", type=Path, default=Path.cwd())
    preflight_parser.add_argument("--issue", type=int, required=True)
    preflight_parser.add_argument("--base-ref", default="origin/dev")
    preflight_parser.add_argument("--owners-json", type=Path)

    pr_parser = subparsers.add_parser("check-pr")
    pr_parser.add_argument("--repo", type=Path, default=Path.cwd())
    pr_parser.add_argument("--event", type=Path)
    pr_parser.add_argument("--base")
    pr_parser.add_argument("--head")
    pr_parser.add_argument("--title", default="")
    pr_parser.add_argument("--body", default="")
    pr_parser.add_argument("--approved-exception", action="store_true")

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--repo", type=Path, default=Path.cwd())
    inventory_parser.add_argument("--dev-ref", default="origin/dev")
    inventory_parser.add_argument("--output", type=Path)

    cleanup_parser = subparsers.add_parser("cleanup-plan")
    cleanup_parser.add_argument("--repo", type=Path, default=Path.cwd())
    cleanup_parser.add_argument("--dev-ref", default="origin/dev")
    cleanup_parser.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        policy = load_delivery_policy(args.policy)
        if args.command == "validate":
            receipt = load_bootstrap_receipt(args.receipt, policy)
            _json_dump(
                {
                    "valid": True,
                    "policy_schema": policy.schema_version,
                    "receipt_schema": receipt.schema_version,
                    "default_branch": policy.repository_default_branch,
                    "integration_branch": policy.integration_branch,
                }
            )
            return 0
        if args.command == "preflight":
            owners: Mapping[int, Sequence[str]] | None
            if args.owners_json is not None:
                raw_owners = _load_json(args.owners_json)
                owners = {
                    int(issue): tuple(branches)
                    for issue, branches in raw_owners.items()
                    if isinstance(branches, list)
                    and all(isinstance(branch, str) for branch in branches)
                }
            else:
                owners = discover_issue_owners(args.repo, policy)
            result = run_preflight(
                args.repo,
                issue=args.issue,
                base_ref=args.base_ref,
                policy=policy,
                remote_issue_owners=owners,
            )
            _json_dump(
                {
                    "passed": result.passed,
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                    "receipt": dict(result.receipt),
                }
            )
            return 0 if result.passed else 1
        if args.command == "check-pr":
            base = args.base
            head = args.head
            title = args.title
            body = args.body
            if args.event is not None:
                event = _load_json(args.event)
                pull_request = event.get("pull_request")
                if not isinstance(pull_request, dict):
                    raise ValueError("event does not contain pull_request")
                base = pull_request.get("base", {}).get("ref")
                head = pull_request.get("head", {}).get("ref")
                title = pull_request.get("title", "")
                body = pull_request.get("body") or ""
            if not isinstance(base, str) or not isinstance(head, str):
                raise ValueError("pull request base and head are required")
            base_ref = f"origin/{base}"
            changed_files, non_generated_lines = _diff_summary(
                args.repo, base_ref, policy
            )
            result = evaluate_pull_request(
                policy=policy,
                base_branch=base,
                head_branch=head,
                title=str(title),
                body=str(body),
                changed_files=changed_files,
                non_generated_lines=non_generated_lines,
                commit_file_sets=_commit_file_sets(args.repo, base_ref),
                approved_exception=args.approved_exception,
                release_derived_from_dev=(
                    _is_ancestor(
                        args.repo,
                        f"origin/{policy.integration_branch}",
                        "HEAD",
                    )
                    if re.fullmatch(policy.release_branch_pattern, head)
                    else None
                ),
                release_has_unintegrated_commits=(
                    bool(
                        _git(
                            args.repo,
                            "rev-list",
                            "--count",
                            f"origin/{policy.integration_branch}..HEAD",
                        )
                        != "0"
                    )
                    if re.fullmatch(policy.release_branch_pattern, head)
                    else None
                ),
            )
            _json_dump(
                {
                    "passed": result.passed,
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                    "details": dict(result.details),
                }
            )
            return 0 if result.passed else 1
        records = inventory_worktrees(args.repo, dev_ref=args.dev_ref)
        if args.command == "inventory":
            _json_dump(
                {
                    "schema_version": 1,
                    "integration_ref": args.dev_ref,
                    "records": [_worktree_payload(record) for record in records],
                },
                output=args.output,
            )
            return 0
        if args.command == "cleanup-plan":
            payload = []
            for record in records:
                disposition = classify_cleanup(record)
                payload.append(
                    {
                        **_worktree_payload(record),
                        "cleanup_action": disposition.action,
                        "cleanup_reason": disposition.reason,
                        "destructive": disposition.destructive,
                    }
                )
            _json_dump(
                {
                    "schema_version": 1,
                    "integration_ref": args.dev_ref,
                    "records": payload,
                },
                output=args.output,
            )
            return 0
    except ValueError as exc:
        _json_dump({"passed": False, "errors": [str(exc)]})
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
