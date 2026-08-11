from __future__ import annotations

import pytest

from research_tree.domain import ArtifactRef, ArtifactRevision
from research_tree.oracles import (
    ORACLE_ATTEMPT_KIND,
    ORACLE_RUN_KIND,
    ORACLE_SPEC_KIND,
    InvalidOracleError,
    OracleAttempt,
    OracleRun,
    OracleSpec,
    validate_oracle_attempt_lineage,
    validate_oracle_run_lineage,
)


ZERO_DIGEST = "0" * 64


def _spec() -> OracleSpec:
    return OracleSpec(
        oracle_spec_id="oracle-check",
        version=1,
        objective="verify the generated result",
        input_schema_digest=ZERO_DIGEST,
        invocation_adapter="pytest",
        permissions={
            "read_roots": ("workspace",),
            "write_roots": (),
            "network": "none",
            "commands": ("pytest",),
        },
        resource_limits={
            "cpu_seconds": 60,
            "memory_bytes": 1024,
            "output_bytes": 4096,
        },
        timeout_seconds=60,
        expected_result_schema_digest=ZERO_DIGEST,
        retry_policy={
            "max_attempts": 2,
            "backoff_seconds": (0, 1.5),
            "switch_method_after": 2,
        },
        flaky_policy="repeat_once_then_inconclusive",
        isolation_profile="sandbox",
        human_only=False,
    )


def _attempt(spec_ref: ArtifactRef, input_ref: ArtifactRef) -> OracleAttempt:
    return OracleAttempt(
        attempt_id="attempt-check",
        oracle_spec_ref=spec_ref,
        input_refs=(input_ref,),
        method="pytest",
        environment_digest=ZERO_DIGEST,
        toolchain_digest=ZERO_DIGEST,
    )


def _run(
    spec_ref: ArtifactRef,
    attempt_ref: ArtifactRef,
    input_ref: ArtifactRef,
    result_ref: ArtifactRef,
    tool_event_ref: ArtifactRef,
) -> OracleRun:
    return OracleRun(
        oracle_run_id="oracle-run-check",
        oracle_spec_ref=spec_ref,
        attempt_ref=attempt_ref,
        input_refs=(input_ref,),
        method="pytest",
        environment_digest=ZERO_DIGEST,
        toolchain_digest=ZERO_DIGEST,
        tool_event_refs=(tool_event_ref,),
        result_artifact_refs=(result_ref,),
        verdict="passed",
        exit_code=0,
        timed_out=False,
        evaluator="core-oracle",
        limitations=(),
        reproducibility_status="reproducible",
    )


def _revision(
    artifact_id: str,
    kind: str,
    payload: dict,
    *,
    parents: tuple[ArtifactRef, ...] = (),
    round_id: str = "round-oracle",
) -> ArtifactRevision:
    return ArtifactRevision.create(
        artifact_id=artifact_id,
        round_id=round_id,
        revision=1,
        kind=kind,
        payload=payload,
        parent_refs=parents,
    )


def test_oracle_spec_payload_round_trip_is_canonical() -> None:
    spec = _spec()

    payload = spec.to_dict()
    restored = OracleSpec.from_dict(payload)

    assert restored == spec
    assert payload["permissions"]["read_roots"] == ["workspace"]
    assert payload["retry_policy"]["backoff_seconds"] == [0, 1.5]
    assert set(payload) == {
        "oracle_spec_id",
        "version",
        "objective",
        "input_schema_digest",
        "invocation_adapter",
        "permissions",
        "resource_limits",
        "timeout_seconds",
        "expected_result_schema_digest",
        "retry_policy",
        "flaky_policy",
        "isolation_profile",
        "human_only",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_schema_digest", "not-a-digest"),
        ("expected_result_schema_digest", "F" * 64),
        ("timeout_seconds", 0),
        ("flaky_policy", "worker-says-passed"),
        ("permissions", {"read_roots": [], "write_roots": [], "network": "all", "commands": []}),
    ],
)
def test_oracle_spec_rejects_unsafe_policy_or_digest(field: str, value: object) -> None:
    payload = _spec().to_dict()
    payload[field] = value

    with pytest.raises(InvalidOracleError):
        OracleSpec.from_dict(payload)


def test_oracle_attempt_requires_exact_spec_and_input_parent_lineage() -> None:
    spec_ref = ArtifactRef("round-oracle", "oracle-check", 1)
    input_ref = ArtifactRef("round-oracle", "input-check", 1)
    attempt = _attempt(spec_ref, input_ref)
    spec_revision = _revision("oracle-check", ORACLE_SPEC_KIND, _spec().to_dict())
    attempt_revision = _revision(
        "attempt-check",
        ORACLE_ATTEMPT_KIND,
        attempt.to_dict(),
        parents=(spec_ref, input_ref),
    )

    assert validate_oracle_attempt_lineage(attempt_revision, spec_revision) == attempt

    forged = _revision(
        "attempt-check",
        ORACLE_ATTEMPT_KIND,
        attempt.to_dict(),
        parents=(spec_ref,),
    )
    with pytest.raises(InvalidOracleError, match="input"):
        validate_oracle_attempt_lineage(forged, spec_revision)


def test_oracle_run_requires_attempt_spec_and_result_event_lineage() -> None:
    spec_ref = ArtifactRef("round-oracle", "oracle-check", 1)
    attempt_ref = ArtifactRef("round-oracle", "attempt-check", 1)
    input_ref = ArtifactRef("round-oracle", "input-check", 1)
    result_ref = ArtifactRef("round-oracle", "result-check", 1)
    tool_event_ref = ArtifactRef("round-oracle", "tool-event-check", 1)
    spec_revision = _revision("oracle-check", ORACLE_SPEC_KIND, _spec().to_dict())
    attempt = _attempt(spec_ref, input_ref)
    attempt_revision = _revision(
        "attempt-check",
        ORACLE_ATTEMPT_KIND,
        attempt.to_dict(),
        parents=(spec_ref, input_ref),
    )
    run = _run(spec_ref, attempt_ref, input_ref, result_ref, tool_event_ref)
    run_revision = _revision(
        "oracle-run-check",
        ORACLE_RUN_KIND,
        run.to_dict(),
        parents=(spec_ref, attempt_ref, input_ref, result_ref, tool_event_ref),
    )

    assert validate_oracle_run_lineage(run_revision, spec_revision, attempt_revision) == run

    stale_attempt = ArtifactRef("round-oracle", "attempt-check", 2)
    stale_run = _run(spec_ref, stale_attempt, input_ref, result_ref, tool_event_ref)
    stale_revision = _revision(
        "oracle-run-check",
        ORACLE_RUN_KIND,
        stale_run.to_dict(),
        parents=(spec_ref, stale_attempt, input_ref, result_ref, tool_event_ref),
    )
    with pytest.raises(InvalidOracleError, match="Attempt"):
        validate_oracle_run_lineage(stale_revision, spec_revision, attempt_revision)


@pytest.mark.parametrize(
    ("verdict", "timed_out", "exit_code"),
    [("passed", True, None), ("passed", False, None), ("inconclusive", True, None)],
)
def test_oracle_run_rejects_inconsistent_terminal_state(
    verdict: str, timed_out: bool, exit_code: int | None
) -> None:
    spec_ref = ArtifactRef("round-oracle", "oracle-check", 1)
    attempt_ref = ArtifactRef("round-oracle", "attempt-check", 1)
    input_ref = ArtifactRef("round-oracle", "input-check", 1)
    result_ref = ArtifactRef("round-oracle", "result-check", 1)
    tool_event_ref = ArtifactRef("round-oracle", "tool-event-check", 1)
    payload = _run(spec_ref, attempt_ref, input_ref, result_ref, tool_event_ref).to_dict()
    payload.update(verdict=verdict, timed_out=timed_out, exit_code=exit_code)

    if verdict == "inconclusive":
        # A timeout is a valid reason for inconclusive; this case is accepted.
        OracleRun.from_dict(payload)
        return

    with pytest.raises(InvalidOracleError):
        OracleRun.from_dict(payload)


