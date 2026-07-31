"""Small application use cases above the immutable store boundary."""

from __future__ import annotations

from typing import Any, Iterable

from .domain import ArtifactRef, ArtifactRevision, RoundRecord, RoundSnapshot
from .storage import RunStore


def create_round(
    store: RunStore,
    round_id: str | None = None,
    *,
    parent_round_id: str | None = None,
) -> RoundRecord:
    return store.create_round(round_id, parent_round_id=parent_round_id)


def append_artifact(
    store: RunStore,
    round_id: str,
    artifact_id: str,
    kind: str,
    payload: Any,
    *,
    parent_refs: Iterable[ArtifactRef] = (),
) -> ArtifactRevision:
    return store.append_artifact(
        round_id,
        artifact_id,
        kind,
        payload,
        parent_refs=parent_refs,
    )


def load_round(store: RunStore, round_id: str) -> RoundSnapshot:
    return store.load_round(round_id)
