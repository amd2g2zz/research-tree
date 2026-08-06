from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research_tree.delivery_workflow import (
    WorktreeRecord,
    _canonical_worktree_path,
    _parse_worktree_porcelain,
    classify_cleanup,
    evaluate_pull_request,
    load_bootstrap_receipt,
    load_delivery_policy,
    main,
    run_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
CHANGE_ROOT = ROOT / "openspec" / "changes" / "establish-dev-integration-governance"
POLICY_PATH = CHANGE_ROOT / "registries" / "delivery-policy-v1.json"
RECEIPT_PATH = CHANGE_ROOT / "evidence" / "dev-bootstrap-v1.json"


def git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def make_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-b", "dev")
    git(repository, "config", "user.email", "test@example.com")
    git(repository, "config", "user.name", "Test User")
    (repository / "README.md").write_text("baseline\n", encoding="utf-8")
    git(repository, "add", "README.md")
    git(repository, "commit", "-m", "initial")
    git(repository, "branch", "-M", "chore/issue-88-dev-governance")
    git(repository, "branch", "dev")
    return repository


def test_policy_and_bootstrap_receipt_are_semantically_valid() -> None:
    policy = load_delivery_policy(POLICY_PATH)
    receipt = load_bootstrap_receipt(RECEIPT_PATH, policy)

    assert policy.integration_branch == "dev"
    assert policy.release_branch == "master"
    assert policy.split_review.files == 25
    assert policy.hard_limit.non_generated_lines == 1500
    assert receipt.source_sha == "db7e256b3d0f261487cce8455971244eaf5986bd"
    assert receipt.default_branch == "master"
    assert all(result.exit_code == 0 for result in receipt.validation_results)
    assert receipt.branch_protection["dev"]["allow_force_pushes"] is False
    assert receipt.branch_protection["master"]["allow_deletions"] is False


def test_validate_cli_reports_master_as_default_branch(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "default_branch": "master",
        "integration_branch": "dev",
        "policy_schema": 1,
        "receipt_schema": 1,
        "valid": True,
    }


def test_policy_rejects_invalid_threshold_order(tmp_path: Path) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["review_limits"]["hard_limit"]["files"] = 10
    invalid = tmp_path / "invalid-policy.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="hard file limit"):
        load_delivery_policy(invalid)


def test_preflight_accepts_clean_current_dev_worktree(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    policy = load_delivery_policy(POLICY_PATH)

    result = run_preflight(
        repository,
        issue=88,
        base_ref="dev",
        policy=policy,
        remote_issue_owners={88: ["chore/issue-88-dev-governance"]},
    )

    assert result.passed is True
    assert result.errors == ()
    assert result.receipt["issue"] == 88
    assert result.receipt["clean"] is True


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked", "staged"])
def test_preflight_rejects_dirty_worktree(tmp_path: Path, dirty_kind: str) -> None:
    repository = make_repository(tmp_path)
    if dirty_kind == "tracked":
        (repository / "README.md").write_text("changed\n", encoding="utf-8")
    elif dirty_kind == "untracked":
        (repository / "scratch.txt").write_text("scratch\n", encoding="utf-8")
    else:
        (repository / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(repository, "add", "staged.txt")

    result = run_preflight(
        repository,
        issue=88,
        base_ref="dev",
        policy=load_delivery_policy(POLICY_PATH),
        remote_issue_owners={88: ["chore/issue-88-dev-governance"]},
    )

    assert result.passed is False
    assert "worktree_not_clean" in result.errors


def test_preflight_rejects_invalid_branch_stale_base_and_duplicate_owner(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    git(repository, "branch", "-M", "feature/no-issue")
    (repository / "next.txt").write_text("next\n", encoding="utf-8")
    git(repository, "add", "next.txt")
    git(repository, "commit", "-m", "advance head")

    result = run_preflight(
        repository,
        issue=88,
        base_ref="dev",
        policy=load_delivery_policy(POLICY_PATH),
        remote_issue_owners={
            88: ["feature/no-issue", "chore/issue-88-other-worktree"]
        },
    )

    assert result.passed is False
    assert {
        "invalid_branch_name",
        "stale_or_diverged_base",
        "duplicate_issue_owner",
    }.issubset(result.errors)


def test_preflight_reports_unavailable_remote_metadata(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)

    result = run_preflight(
        repository,
        issue=88,
        base_ref="dev",
        policy=load_delivery_policy(POLICY_PATH),
        remote_issue_owners=None,
    )

    assert result.passed is False
    assert result.errors == ("remote_metadata_unavailable",)


def test_preflight_rejects_duplicate_windows_worktree_path(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository_path = str(repository.resolve())

    result = run_preflight(
        repository,
        issue=88,
        base_ref="dev",
        policy=load_delivery_policy(POLICY_PATH),
        remote_issue_owners={88: ["chore/issue-88-dev-governance"]},
        registered_worktree_paths=[repository_path, repository_path],
    )

    assert result.passed is False
    assert "duplicate_worktree_path" in result.errors


def test_windows_worktree_paths_are_normalized_case_insensitively() -> None:
    assert _canonical_worktree_path("D:\\CodeBase\\Research-Tree\\") == (
        _canonical_worktree_path("d:/codebase/research-tree")
    )


def test_pull_request_gate_enforces_base_issue_and_size_limits() -> None:
    policy = load_delivery_policy(POLICY_PATH)

    wrong_base = evaluate_pull_request(
        policy=policy,
        base_branch="master",
        head_branch="feat/issue-88-governance",
        title="chore: establish delivery governance",
        body="Closes #88",
        changed_files=["scripts/check_delivery_workflow.py"],
        non_generated_lines=100,
        commit_file_sets=[{"scripts/check_delivery_workflow.py"}],
    )
    assert "invalid_base_branch" in wrong_base.errors

    multiple_issues = evaluate_pull_request(
        policy=policy,
        base_branch="dev",
        head_branch="feat/issue-88-governance",
        title="chore: establish delivery governance",
        body="Closes #88\nCloses #89",
        changed_files=["scripts/check_delivery_workflow.py"],
        non_generated_lines=100,
        commit_file_sets=[{"scripts/check_delivery_workflow.py"}],
    )
    assert "multiple_delivery_issues" in multiple_issues.errors

    oversized = evaluate_pull_request(
        policy=policy,
        base_branch="dev",
        head_branch="feat/issue-88-governance",
        title="chore: establish delivery governance",
        body="Closes #88",
        changed_files=[f"src/file_{index}.py" for index in range(51)],
        non_generated_lines=1501,
        commit_file_sets=[{"src/file_0.py"}],
    )
    assert "hard_review_limit_exceeded" in oversized.errors


def test_release_promotion_targets_master_and_is_derived_from_dev() -> None:
    policy = load_delivery_policy(POLICY_PATH)

    accepted = evaluate_pull_request(
        policy=policy,
        base_branch="master",
        head_branch="release/0.0.1-a2",
        title="release: 0.0.1-a2",
        body="Promote the current dev integration revision.",
        changed_files=["CHANGELOG.md"],
        non_generated_lines=10,
        commit_file_sets=[{"CHANGELOG.md"}],
        release_derived_from_dev=True,
        release_has_unintegrated_commits=False,
    )
    assert accepted.passed is True

    wrong_source = evaluate_pull_request(
        policy=policy,
        base_branch="master",
        head_branch="release/0.0.1-a2",
        title="release: 0.0.1-a2",
        body="Promote an unrelated branch.",
        changed_files=["CHANGELOG.md"],
        non_generated_lines=10,
        commit_file_sets=[{"CHANGELOG.md"}],
        release_derived_from_dev=False,
        release_has_unintegrated_commits=False,
    )
    assert "release_not_derived_from_dev" in wrong_source.errors

    extra_commits = evaluate_pull_request(
        policy=policy,
        base_branch="master",
        head_branch="release/0.0.1-a2",
        title="release: 0.0.1-a2",
        body="Promote dev plus an unintegrated feature.",
        changed_files=["src/unintegrated.py"],
        non_generated_lines=10,
        commit_file_sets=[{"src/unintegrated.py"}],
        release_derived_from_dev=True,
        release_has_unintegrated_commits=True,
    )
    assert "release_contains_unintegrated_commits" in extra_commits.errors


def test_review_threshold_warns_and_approved_exception_allows_hard_limit() -> None:
    policy = load_delivery_policy(POLICY_PATH)
    split = evaluate_pull_request(
        policy=policy,
        base_branch="dev",
        head_branch="feat/issue-88-governance",
        title="feat: establish delivery governance",
        body="Closes #88",
        changed_files=[f"src/file_{index}.py" for index in range(26)],
        non_generated_lines=801,
        commit_file_sets=[{"src/file_0.py"}],
    )
    assert split.passed is True
    assert split.warnings == ("split_review_required",)

    excepted = evaluate_pull_request(
        policy=policy,
        base_branch="dev",
        head_branch="feat/issue-88-governance",
        title="feat: establish delivery governance",
        body="Closes #88",
        changed_files=[f"src/file_{index}.py" for index in range(51)],
        non_generated_lines=1501,
        commit_file_sets=[{"src/file_0.py"}],
        approved_exception=True,
    )
    assert excepted.passed is True
    assert excepted.warnings == ("split_review_required",)


def test_pull_request_gate_requires_generated_output_commit_separation() -> None:
    policy = load_delivery_policy(POLICY_PATH)
    mixed = evaluate_pull_request(
        policy=policy,
        base_branch="dev",
        head_branch="chore/issue-88-dev-governance",
        title="chore: establish delivery governance",
        body="Closes #88",
        changed_files=[
            "skill-src/SKILL.template.md",
            "packages/codex/research-tree/SKILL.md",
        ],
        non_generated_lines=20,
        commit_file_sets=[
            {
                "skill-src/SKILL.template.md",
                "packages/codex/research-tree/SKILL.md",
            }
        ],
    )
    assert "generated_output_mixed_with_source_commit" in mixed.errors

    separated = evaluate_pull_request(
        policy=policy,
        base_branch="dev",
        head_branch="chore/issue-88-dev-governance",
        title="chore: establish delivery governance",
        body="Closes #88",
        changed_files=[
            "skill-src/SKILL.template.md",
            "packages/codex/research-tree/SKILL.md",
        ],
        non_generated_lines=20,
        commit_file_sets=[
            {"skill-src/SKILL.template.md"},
            {"packages/codex/research-tree/SKILL.md"},
        ],
    )
    assert separated.passed is True


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            WorktreeRecord(
                path="C:/repo/dirty",
                branch="feat/issue-90-dirty",
                head="a" * 40,
                dirty=True,
                reachable_from_dev=False,
                pr_state="OPEN",
                branch_has_later_commits=False,
            ),
            "preserve_dirty",
        ),
        (
            WorktreeRecord(
                path="C:/repo/merged",
                branch="feat/issue-91-merged",
                head="b" * 40,
                dirty=False,
                reachable_from_dev=True,
                pr_state="MERGED",
                branch_has_later_commits=False,
            ),
            "eligible_for_explicit_removal",
        ),
        (
            WorktreeRecord(
                path="C:/repo/closed",
                branch="feat/issue-92-closed",
                head="c" * 40,
                dirty=False,
                reachable_from_dev=False,
                pr_state="CLOSED",
                branch_has_later_commits=False,
            ),
            "requires_disposition",
        ),
        (
            WorktreeRecord(
                path="C:/repo/later",
                branch="feat/issue-93-later",
                head="d" * 40,
                dirty=False,
                reachable_from_dev=True,
                pr_state="MERGED",
                branch_has_later_commits=True,
            ),
            "requires_disposition",
        ),
        (
            WorktreeRecord(
                path="C:/repo/detached",
                branch=None,
                head="e" * 40,
                dirty=False,
                reachable_from_dev=False,
                pr_state=None,
                branch_has_later_commits=False,
            ),
            "requires_disposition",
        ),
        (
            WorktreeRecord(
                path="C:/repo/orphaned",
                branch="feat/issue-94-orphaned",
                head="f" * 40,
                dirty=False,
                reachable_from_dev=False,
                pr_state=None,
                branch_has_later_commits=False,
            ),
            "requires_disposition",
        ),
    ],
)
def test_cleanup_classification_is_non_destructive(
    record: WorktreeRecord, expected: str
) -> None:
    disposition = classify_cleanup(record)
    assert disposition.action == expected
    assert disposition.destructive is False


def test_worktree_porcelain_parser_preserves_windows_paths() -> None:
    records = _parse_worktree_porcelain(
        "\n".join(
            [
                "worktree D:/codebase/research-tree-worktrees/issue-88-dev-governance",
                "HEAD " + "a" * 40,
                "branch refs/heads/chore/issue-88-dev-governance",
                "",
                "worktree D:/codebase/research tree detached",
                "HEAD " + "b" * 40,
                "detached",
                "",
            ]
        )
    )

    assert records[0]["worktree"].endswith("issue-88-dev-governance")
    assert records[1]["worktree"] == "D:/codebase/research tree detached"
    assert records[1]["detached"] == "true"
