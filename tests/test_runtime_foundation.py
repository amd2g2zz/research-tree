from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest
def runtime_api():
    from research_tree import (
        ArtifactNotFoundError,
        ArtifactRef,
        DataIntegrityError,
        InvalidIdentifierError,
        InvalidPayloadError,
        RoundAlreadyExistsError,
        RunStore,
    )

    return {
        "ArtifactNotFoundError": ArtifactNotFoundError,
        "ArtifactRef": ArtifactRef,
        "DataIntegrityError": DataIntegrityError,
        "InvalidIdentifierError": InvalidIdentifierError,
        "InvalidPayloadError": InvalidPayloadError,
        "RoundAlreadyExistsError": RoundAlreadyExistsError,
        "RunStore": RunStore,
    }


def test_rounds_are_isolated_and_duplicate_creation_never_overwrites(tmp_path: Path) -> None:
    api = runtime_api()
    store = api["RunStore"](tmp_path / "store")

    with ThreadPoolExecutor(max_workers=2) as executor:
        alpha, beta = list(
            executor.map(store.create_round, ("round-alpha", "round-beta"))
        )
    alpha_artifact = store.append_artifact(
        alpha.id,
        "artifact-brief",
        "working-brief",
        {"outcome": "alpha only"},
    )

    assert [artifact.id for artifact in store.load_round(alpha.id).artifacts] == [
        alpha_artifact.id
    ]
    assert store.load_round(beta.id).artifacts == ()
    assert (tmp_path / "store" / "rounds" / alpha.id).is_dir()
    assert (tmp_path / "store" / "rounds" / beta.id).is_dir()

    with pytest.raises(api["RoundAlreadyExistsError"]):
        store.create_round(alpha.id)

    assert store.load_round(alpha.id).artifacts[0].payload["outcome"] == "alpha only"


def test_artifact_revisions_preserve_prior_payload_and_hash(tmp_path: Path) -> None:
    api = runtime_api()
    store = api["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-revisions")
    original_payload = {"nested": {"answer": 1}, "labels": ["initial"]}

    first = store.append_artifact(
        round_record.id,
        "artifact-intent",
        "intent-model",
        original_payload,
    )
    original_payload["nested"]["answer"] = 2
    original_payload["labels"].append("caller-mutated")
    second = store.append_artifact(
        round_record.id,
        "artifact-intent",
        "intent-model",
        original_payload,
        parent_refs=(api["ArtifactRef"](round_record.id, first.id, first.revision),),
    )

    snapshot = store.load_round(round_record.id)
    revisions = [
        artifact
        for artifact in snapshot.artifacts
        if artifact.id == "artifact-intent"
    ]

    assert [artifact.revision for artifact in revisions] == [1, 2]
    assert revisions[0].payload["nested"]["answer"] == 1
    assert revisions[0].payload["labels"] == ("initial",)
    assert revisions[0].content_hash == first.content_hash
    assert revisions[1].content_hash == second.content_hash
    assert first.content_hash != second.content_hash


def test_fresh_store_rehydrates_round_and_cross_round_lineage(tmp_path: Path) -> None:
    api = runtime_api()
    root = tmp_path / "store"
    store = api["RunStore"](root)
    parent = store.create_round("round-parent")
    parent_artifact = store.append_artifact(
        parent.id,
        "artifact-context",
        "context-bundle",
        {"input_ids": ["input-001"]},
    )
    child = store.create_round("round-child", parent_round_id=parent.id)
    parent_ref = api["ArtifactRef"](
        parent.id,
        parent_artifact.id,
        parent_artifact.revision,
    )
    child_artifact = store.append_artifact(
        child.id,
        "artifact-brief",
        "working-brief",
        {"selected_input_ids": ["input-001"]},
        parent_refs=(parent_ref,),
    )

    rehydrated = api["RunStore"](root).load_round(child.id)

    assert rehydrated.record.id == child.id
    assert rehydrated.record.parent_round_id == parent.id
    assert rehydrated.artifacts == (child_artifact,)
    assert rehydrated.artifacts[0].parent_refs == (parent_ref,)
    assert {event.kind for event in rehydrated.lineage_events} == {
        "round-created",
        "artifact-appended",
    }


def test_store_rejects_unsafe_or_unresolvable_inputs_without_writing(tmp_path: Path) -> None:
    api = runtime_api()
    store = api["RunStore"](tmp_path / "store")

    with pytest.raises(api["InvalidIdentifierError"]):
        store.create_round("../round-escape")

    round_record = store.create_round("round-safe")
    unknown_ref = api["ArtifactRef"]("round-safe", "artifact-missing", 1)

    with pytest.raises(api["ArtifactNotFoundError"]):
        store.append_artifact(
            round_record.id,
            "artifact-brief",
            "working-brief",
            {"value": "safe"},
            parent_refs=(unknown_ref,),
        )
    with pytest.raises(api["InvalidPayloadError"]):
        store.append_artifact(
            round_record.id,
            "artifact-brief",
            "working-brief",
            {"unsupported": {"set-value"}},
        )

    assert store.load_round(round_record.id).artifacts == ()


def test_tampered_artifact_content_is_rejected_on_reload(tmp_path: Path) -> None:
    api = runtime_api()
    root = tmp_path / "store"
    store = api["RunStore"](root)
    round_record = store.create_round("round-integrity")
    artifact = store.append_artifact(
        round_record.id,
        "artifact-package",
        "technical-package",
        {"outcome": "original"},
    )

    artifact_path = (
        root
        / "rounds"
        / round_record.id
        / "artifacts"
        / artifact.id
        / f"{artifact.revision:06d}.json"
    )
    tampered = json.loads(artifact_path.read_text(encoding="utf-8"))
    tampered["payload"]["outcome"] = "tampered"
    artifact_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(api["DataIntegrityError"]):
        api["RunStore"](root).load_round(round_record.id)


@pytest.mark.parametrize(
    ("parent_round", "child_round"),
    [
        ("round-lineage", "round-lineage"),
        ("round-parent", "round-child"),
    ],
)
def test_load_rejects_artifact_with_deleted_parent_revision(
    tmp_path: Path, parent_round: str, child_round: str
) -> None:
    api = runtime_api()
    root = tmp_path / "store"
    store = api["RunStore"](root)
    parent = store.create_round(parent_round)
    parent_artifact = store.append_artifact(
        parent.id, "artifact-parent", "working-brief", {"state": "present"}
    )
    child = parent if child_round == parent_round else store.create_round(
        child_round, parent_round_id=parent.id
    )
    store.append_artifact(
        child.id,
        "artifact-child",
        "technical-package",
        {"state": "depends-on-parent"},
        parent_refs=(api["ArtifactRef"](parent.id, parent_artifact.id, parent_artifact.revision),),
    )

    parent_path = (
        root
        / "rounds"
        / parent.id
        / "artifacts"
        / parent_artifact.id
        / f"{parent_artifact.revision:06d}.json"
    )
    parent_path.unlink()

    with pytest.raises(api["DataIntegrityError"], match="stored lineage reference does not resolve"):
        api["RunStore"](root).load_round(child.id)


def test_load_rejects_artifact_appended_event_with_missing_artifact(
    tmp_path: Path
) -> None:
    api = runtime_api()
    root = tmp_path / "store"
    store = api["RunStore"](root)
    round_record = store.create_round("round-event-integrity")
    artifact = store.append_artifact(
        round_record.id, "artifact-package", "technical-package", {"state": "present"}
    )
    event_root = root / "rounds" / round_record.id / "events"
    event_path = next(
        path
        for path in event_root.glob("*.json")
        if json.loads(path.read_text(encoding="utf-8"))["kind"] == "artifact-appended"
    )
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["artifact_ref"]["revision"] = artifact.revision + 1
    event_path.write_text(json.dumps(event), encoding="utf-8")

    with pytest.raises(api["DataIntegrityError"], match="stored lineage reference does not resolve"):
        api["RunStore"](root).load_round(round_record.id)


def test_store_requires_an_explicit_root_and_ignores_ambient_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = runtime_api()
    with pytest.raises(TypeError):
        api["RunStore"]()

    ambient_root = tmp_path / "ambient"
    explicit_root = tmp_path / "explicit"
    monkeypatch.setenv("RESEARCH_WORKSPACE", str(ambient_root))
    store = api["RunStore"](explicit_root)
    store.create_round("round-explicit")

    assert (explicit_root / "rounds" / "round-explicit" / "round.json").is_file()
    assert not ambient_root.exists()
