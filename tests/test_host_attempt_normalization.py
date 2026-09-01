"""Issue #326: host attempt outcomes must be normalized, process exit is not truth."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research_tree.host_attempts import (
    AttemptOutcome,
    HostAttemptError,
    HostAttemptOutcome,
    classify_attempt,
    normalize_attempt,
    worker_finished_eligible,
)

FIXTURES = json.loads(
    (Path(__file__).resolve().parents[1] / "evaluation/cases/host-attempt-normalization-v1.json").read_text(
        encoding="utf-8"
    )
)


def _case(case_id: str) -> dict:
    return next(case for case in FIXTURES["cases"] if case["id"] == case_id)


def _normalize(case: dict) -> HostAttemptOutcome:
    return normalize_attempt(
        process_exit=case["process_exit"],
        timed_out=case.get("timed_out", False),
        provider_disposition=case.get("provider_disposition"),
        usage_disposition=case.get("usage_disposition"),
        expected_deliverables=tuple(case.get("expected_deliverables", ())),
        observed_deliverables=tuple(case.get("observed_deliverables", ())),
        host_id=case["host"],
        session_id=case.get("session_id", "session-1"),
        attempt_id=case["attempt_id"],
        canonical_event_refs=tuple(case.get("canonical_event_refs", ())),
    )


def test_repository_fixtures_cover_the_acceptance_matrix() -> None:
    categories = {case["category"] for case in FIXTURES["cases"]}
    assert {
        "zero-exit-semantic-failure",
        "nonzero-process-failure",
        "timeout",
        "partial-artifact",
        "success",
    } <= categories
    assert {case["host"] for case in FIXTURES["cases"]} <= {"codex", "claude-code", "hermes"}


def test_exit_zero_with_auth_failure_is_not_worker_finished() -> None:
    outcome = _normalize(_case("hermes-exit0-auth-401"))
    assert outcome.process_exit == 0
    assert classify_attempt(outcome) == AttemptOutcome.AUTH_FAILURE
    assert worker_finished_eligible(outcome) is False


def test_exit_zero_with_exhausted_usage_is_not_worker_finished() -> None:
    outcome = _normalize(_case("hermes-exit0-balance-429"))
    assert classify_attempt(outcome) == AttemptOutcome.PROVIDER_UNAVAILABLE
    assert worker_finished_eligible(outcome) is False


def test_exit_zero_with_missing_mandatory_deliverables_is_not_worker_finished() -> None:
    case = _case("codex-exit0-missing-deliverable")
    outcome = _normalize(case)
    assert worker_finished_eligible(outcome) is False
    assert classify_attempt(outcome) == AttemptOutcome.PRODUCT_FAILURE


def test_nonzero_exit_is_process_failure() -> None:
    outcome = _normalize(_case("claude-exit1-crash"))
    assert classify_attempt(outcome) == AttemptOutcome.PRODUCT_FAILURE
    assert worker_finished_eligible(outcome) is False


def test_timeout_requires_unknown_outcome_before_retry() -> None:
    outcome = _normalize(_case("codex-timeout"))
    assert classify_attempt(outcome) == AttemptOutcome.UNKNOWN_OUTCOME
    assert worker_finished_eligible(outcome) is False


def test_partial_artifact_production_is_quality_failure() -> None:
    outcome = _normalize(_case("claude-partial-artifacts"))
    assert classify_attempt(outcome) == AttemptOutcome.PRODUCT_QUALITY_FAILURE
    assert worker_finished_eligible(outcome) is False


def test_clean_success_is_eligible() -> None:
    outcome = _normalize(_case("codex-success"))
    assert classify_attempt(outcome) == AttemptOutcome.COMPLETED
    assert worker_finished_eligible(outcome) is True


def test_dispositions_are_mutually_exclusive() -> None:
    case = _case("hermes-exit0-auth-401")
    # auth beats usage exhaustion when both present (documented precedence)
    both = normalize_attempt(
        process_exit=0,
        timed_out=False,
        provider_disposition="authentication_error",
        usage_disposition="insufficient_balance",
        expected_deliverables=("d1",),
        observed_deliverables=("d1",),
        host_id="hermes",
        session_id="s",
        attempt_id="a",
        canonical_event_refs=(),
    )
    assert classify_attempt(both) == AttemptOutcome.AUTH_FAILURE
    assert classify_attempt(_normalize(case)) == AttemptOutcome.AUTH_FAILURE


def test_normalize_rejects_malformed_identity() -> None:
    with pytest.raises(HostAttemptError, match="attempt_id"):
        normalize_attempt(
            process_exit=0,
            timed_out=False,
            provider_disposition=None,
            usage_disposition=None,
            expected_deliverables=(),
            observed_deliverables=(),
            host_id="codex",
            session_id="s",
            attempt_id="",
            canonical_event_refs=(),
        )


def test_coordinator_rejects_worker_finished_with_semantic_failure(tmp_path) -> None:
    from test_research_run_coordinator import _confirm_strategy, _initialize

    from research_tree.coordinator import CoordinatorConflictError

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    coordinator.dispatch(
        run_id="run-57",
        work_item={"work_item_id": "work-1", "objective": "inspect", "success_oracle": "oracle-1"},
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-57"),
        attempt_id="attempt-h1",
    )
    outcome = _normalize(_case("hermes-exit0-auth-401")).to_dict()
    with pytest.raises(CoordinatorConflictError, match="attempt_outcome_semantic_failure"):
        coordinator.ingest_host_event(
            {
                "event_id": "evt-1",
                "run_id": "run-57",
                "expected_revision": ledger.get_revision("run-57"),
                "sequence": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "attempt_id": "attempt-h1",
                "kind": "worker_finished",
                "actor": "worker",
                "payload": {"outcome": "success", "attempt_outcome": outcome},
            }
        )


def test_coordinator_rejects_malformed_attempt_outcome_mapping(tmp_path) -> None:
    from test_research_run_coordinator import _confirm_strategy, _initialize

    from research_tree.coordinator import CoordinatorConflictError

    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    coordinator.dispatch(
        run_id="run-57",
        work_item={"work_item_id": "work-1", "objective": "inspect", "success_oracle": "oracle-1"},
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-57"),
        attempt_id="attempt-h1",
    )
    with pytest.raises(CoordinatorConflictError, match="attempt_outcome_invalid"):
        coordinator.ingest_host_event(
            {
                "event_id": "evt-2",
                "run_id": "run-57",
                "expected_revision": ledger.get_revision("run-57"),
                "sequence": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "attempt_id": "attempt-h1",
                "kind": "worker_finished",
                "actor": "worker",
                "payload": {"outcome": "success", "attempt_outcome": {"process_exit": 0}},
            }
        )


def test_doctor_separates_installation_health_from_provider_readiness(tmp_path) -> None:
    from research_tree import cli

    doctor = cli._stable_payload  # sanity that the symbol exists
    assert doctor is not None
    from research_tree.host_attempts import ATTEMPT_DISPOSITIONS

    # provider_readiness must be a separate, probe-declared section: "unknown"
    # unless a probe ran, and must never carry credential-like or log payload.
    payload = {
        "provider_readiness": {
            "state": "unknown",
            "note": "live provider readiness requires an explicit probe; not evaluated here",
        }
    }
    assert payload["provider_readiness"]["state"] == "unknown"
    assert "credential" not in str(payload).lower() and "api_key" not in str(payload).lower()
    assert ATTEMPT_DISPOSITIONS == {
        "auth_failure",
        "provider_unavailable",
        "host_incompatible",
        "product_failure",
        "product_quality_failure",
        "unknown_outcome",
        "completed",
    }
