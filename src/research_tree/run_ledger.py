"""Canonical storage boundary for the alpha2 run ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class RunLedgerProtocol(Protocol):
    """Operations domain services may use without depending on a backend layout."""

    database: Path

    def create_run(
        self,
        run_id: str,
        *,
        task_identity: Mapping[str, Any] | None = None,
        authority: Mapping[str, Any] | None = None,
        parent_run_id: str | None = None,
    ) -> dict[str, Any]: ...

    def append_artifact(
        self,
        *,
        run_id: str,
        artifact_id: str,
        kind: str,
        payload: Mapping[str, Any],
        actor_kind: str,
        actor_id: str,
        status: str,
        parent_refs: Sequence[Mapping[str, Any]] = (),
        expected_revision: int | None = None,
        expected_run_revision: int | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]: ...

    def resolve(self, run_id: str, artifact_id: str, revision: int) -> dict[str, Any]: ...

    def reconstruct(self, run_id: str) -> dict[str, Any]: ...

    def events(self, run_id: str) -> list[dict[str, Any]]: ...

    def put_content(
        self,
        *,
        run_id: str,
        data: bytes,
        media_type: str,
        metadata: Mapping[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]: ...
