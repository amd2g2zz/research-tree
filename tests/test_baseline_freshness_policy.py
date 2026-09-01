"""Issue #327: repository baseline freshness is an explicit admission policy."""

from __future__ import annotations

import pytest

from research_tree.freshness import (
    FreshnessError,
    FreshnessPolicy,
    assess,
)


def test_repo_inputs_bind_authorized_remote_and_ref() -> None:
    policy = FreshnessPolicy(
        authorized_remote="git@github.com:amd2g2zz/research-tree.git",
        authorized_ref="refs/heads/dev",
        allowed_ahead=5,
        allowed_behind=5,
        relevant_paths=("src/", "tests/"),
    )
    assert policy.authorized_remote is not None
    assert policy.authorized_ref == "refs/heads/dev"


def test_admission_records_inspected_authority_observation_and_changes() -> None:
    policy = FreshnessPolicy(
        authorized_remote="r",
        authorized_ref="refs/heads/dev",
        allowed_ahead=5,
        allowed_behind=0,
        relevant_paths=("src/",),
    )
    record = assess(
        inspected_commit="aaa",
        authority_commit="bbb",
        ahead=3,
        behind=1,
        changed_paths=("src/coordinator.py", "docs/x.md"),
        policy=policy,
    )
    assert record.inspected_commit == "aaa"
    assert record.authority_commit == "bbb"
    assert record.ahead == 3
    assert record.behind == 1
    assert "src/coordinator.py" in record.relevant_path_changes
    assert "docs/x.md" not in record.relevant_path_changes
    assert record.observed_at  # ISO timestamp present
    assert record.policy is policy


def test_stale_relevant_path_triggers_revalidation_disposition() -> None:
    policy = FreshnessPolicy(allowed_ahead=0, relevant_paths=("src/",))
    record = assess(
        inspected_commit="aaa",
        authority_commit="bbb",
        ahead=10,
        behind=None,
        changed_paths=("src/coordinator.py",),
        policy=policy,
    )
    assert record.disposition == "stale_relevant"


def test_stale_irrelevant_path_is_recorded_but_not_blocking() -> None:
    policy = FreshnessPolicy(allowed_ahead=0, relevant_paths=("src/",))
    record = assess(
        inspected_commit="aaa",
        authority_commit="bbb",
        ahead=10,
        behind=None,
        changed_paths=("docs/typo.md",),
        policy=policy,
    )
    assert record.disposition == "stale_irrelevant"


def test_explicit_historical_analysis_authorization_records_disposition() -> None:
    policy = FreshnessPolicy(allowed_ahead=0, allow_historical_analysis=True)
    record = assess(
        inspected_commit="aaa",
        authority_commit="bbb",
        ahead=50,
        behind=None,
        changed_paths=("src/coordinator.py",),
        policy=policy,
        historical_analysis_authorized=True,
    )
    assert record.disposition == "historical_analysis_authorized"


def test_offline_authority_is_freshness_unknown_not_current_not_blocked() -> None:
    policy = FreshnessPolicy(allowed_ahead=0, relevant_paths=("src/",))
    record = assess(
        inspected_commit="aaa",
        authority_commit=None,  # remote unreachable
        ahead=0,
        behind=None,
        changed_paths=(),
        policy=policy,
    )
    assert record.disposition == "freshness_unknown"


def test_within_allowed_divergence_and_no_overlap_is_current() -> None:
    policy = FreshnessPolicy(allowed_ahead=5, allowed_behind=5, relevant_paths=("src/",))
    record = assess(
        inspected_commit="aaa",
        authority_commit="bbb",
        ahead=2,
        behind=1,
        changed_paths=("docs/",),
        policy=policy,
    )
    assert record.disposition == "current"


def test_assess_rejects_malformed_inputs() -> None:
    policy = FreshnessPolicy()
    with pytest.raises(FreshnessError, match="inspected_commit"):
        assess(
            inspected_commit="",
            authority_commit="bbb",
            ahead=0,
            behind=None,
            changed_paths=(),
            policy=policy,
        )


def test_policy_from_dict_whitelist_enforced() -> None:
    policy = FreshnessPolicy.from_dict(
        {"authorized_remote": "r", "authorized_ref": "refs/heads/dev", "allowed_ahead": 0, "relevant_paths": ["src/"]}
    )
    assert policy.relevant_paths == ("src/",)
    with pytest.raises(FreshnessError, match="non-negative integer"):
        FreshnessPolicy.from_dict({"allowed_ahead": -1})


def test_intake_carries_freshness_record_when_policy_provided(tmp_path) -> None:
    from research_tree.freshness import FreshnessPolicy
    from research_tree.intake import RepositoryInspector

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text("print('hello')\n")

    inspector = RepositoryInspector(
        freshness_policy=FreshnessPolicy(
            authorized_remote="git@example:owner/repo.git",
            authorized_ref="refs/heads/dev",
            allowed_ahead=5,
            allowed_behind=5,
            relevant_paths=("src/",),
        )
    )
    payload = inspector.inspect(repo)
    assert "freshness" in payload
    freshness = payload["freshness"]
    assert freshness["policy"]["authorized_ref"] == "refs/heads/dev"
    assert freshness["disposition"] in {
        "current",
        "stale_relevant",
        "stale_irrelevant",
        "freshness_unknown",
        "historical_analysis_authorized",
    }


def test_intake_no_freshness_when_policy_omitted(tmp_path) -> None:
    from research_tree.intake import RepositoryInspector

    repo = tmp_path / "repo"
    repo.mkdir()
    inspector = RepositoryInspector()
    payload = inspector.inspect(repo)
    assert "freshness" in payload  # keys present, value None when no policy
    assert payload["freshness"] is None
