from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from research_tree import ArtifactRef, LineageEvent


def api():
    from research_tree.run_ledger import (
        LedgerConflictError,
        LedgerIntegrityError,
        RunLedger,
    )

    return RunLedger, LedgerConflictError, LedgerIntegrityError


def test_initialize_is_idempotent_and_applies_durability_settings(tmp_path: Path) -> None:
    RunLedger, _, _ = api()
    ledger = RunLedger(tmp_path)

    ledger.initialize()
    ledger.initialize()

    with ledger._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 7
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='decision_frames'"
            ).fetchone()[0]
            == "decision_frames"
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='preference_observations'"
            ).fetchone()[0]
            == "preference_observations"
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preference_profiles'"
            ).fetchone()[0]
            == "user_preference_profiles"
        )


def test_artifact_append_reconstructs_immutable_lineage(tmp_path: Path) -> None:
    RunLedger, _, _ = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")

    ledger.append_artifact("run-1", "brief", "working-brief", {"goal": "test"}, expected_revision=0)
    second = ledger.append_artifact(
        "run-1",
        "strategy",
        "strategy",
        {"step": 1},
        parent_refs=(ArtifactRef("run-1", "brief", 1),),
        expected_revision=1,
    )
    snapshot = ledger.load_run("run-1")

    assert [artifact.id for artifact in snapshot.artifacts] == ["brief", "strategy"]
    assert second.parent_refs == (ArtifactRef("run-1", "brief", 1),)
    assert snapshot.record.id == "run-1"
    assert ledger.get_revision("run-1") == 2


def test_stale_revision_rejects_without_partial_rows(tmp_path: Path) -> None:
    RunLedger, LedgerConflictError, _ = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")
    ledger.append_artifact("run-1", "one", "finding", {"value": 1}, expected_revision=0)

    with pytest.raises(LedgerConflictError):
        ledger.append_artifact("run-1", "two", "finding", {"value": 2}, expected_revision=0)

    assert ledger.get_revision("run-1") == 1
    assert [artifact.id for artifact in ledger.load_run("run-1").artifacts] == ["one"]


def test_parent_reference_is_checked_before_write(tmp_path: Path) -> None:
    RunLedger, _, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")

    with pytest.raises(LedgerIntegrityError):
        ledger.append_artifact(
            "run-1", "child", "finding", {}, parent_refs=(ArtifactRef("run-1", "missing", 1),), expected_revision=0
        )
    assert ledger.get_revision("run-1") == 0


def test_event_retry_is_idempotent_and_payload_conflict_is_rejected(tmp_path: Path) -> None:
    RunLedger, _, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")
    event = LineageEvent(id="event-fixed", round_id="run-1", kind="checkpoint", created_at="2026-01-01T00:00:00+00:00")

    assert ledger.append_event("run-1", event, expected_revision=0) == event
    assert ledger.append_event("run-1", event, expected_revision=1) == event
    assert ledger.get_revision("run-1") == 1

    conflicting = LineageEvent(id=event.id, round_id=event.round_id, kind="different", created_at=event.created_at)
    with pytest.raises(LedgerIntegrityError):
        ledger.append_event("run-1", conflicting, expected_revision=1)


def test_corrupt_or_dangling_lineage_is_rejected_on_load(tmp_path: Path) -> None:
    RunLedger, _, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")
    ledger.append_artifact("run-1", "one", "finding", {"value": 1}, expected_revision=0)
    database = tmp_path / ".research-tree" / "run-ledger.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM artifacts WHERE artifact_id = 'one'")
        connection.commit()

    with pytest.raises(LedgerIntegrityError):
        ledger.load_run("run-1")


def test_event_rejects_missing_artifact_before_commit(tmp_path: Path) -> None:
    RunLedger, _, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")
    event = LineageEvent(
        id="event-1",
        round_id="run-1",
        kind="evidence-linked",
        created_at="2026-01-01T00:00:00+00:00",
        artifact_ref=ArtifactRef("run-1", "missing", 1),
    )

    with pytest.raises(LedgerIntegrityError, match="artifact parent does not exist"):
        ledger.append_event("run-1", event, expected_revision=0)

    assert ledger.get_revision("run-1") == 0
    assert [item.id for item in ledger.load_run("run-1").lineage_events] != [event.id]


def test_failed_append_rolls_back_before_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    RunLedger, _, _ = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")
    original = ledger._before_commit
    monkeypatch.setattr(ledger, "_before_commit", lambda: (_ for _ in ()).throw(RuntimeError("injected")))

    with pytest.raises(RuntimeError, match="injected"):
        ledger.append_artifact("run-1", "one", "finding", {}, expected_revision=0)

    monkeypatch.setattr(ledger, "_before_commit", original)
    assert ledger.get_revision("run-1") == 0
    assert ledger.load_run("run-1").artifacts == ()


def test_successor_batches_commit_both_runs_with_exact_cross_run_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("research_tree.domain.utc_now", lambda: "2026-08-17T00:00:00+00:00")
    RunLedger, _, _ = api()
    ledger = RunLedger(tmp_path)
    ledger.create_run("prior")
    source = ledger.append_artifact(
        "prior",
        "source",
        "input-ledger-entry",
        {"kind": "source"},
        expected_revision=0,
    )

    successor, successor_artifacts, predecessor_artifacts = ledger.create_successor_with_artifact_batches(
        predecessor_run_id="prior",
        successor_run_id="successor",
        successor_parent_run_id="prior",
        expected_predecessor_revision=ledger.get_revision("prior"),
        successor_entries=(
            ("feedback", "input-ledger-entry", {"kind": "feedback"}, ()),
            (
                "lineage",
                "feedback-lineage",
                {"lineage_kind": "successor"},
                (
                    ArtifactRef("successor", "feedback", 1),
                    ArtifactRef("prior", source.id, source.revision),
                ),
            ),
        ),
        predecessor_entries=(
            (
                "supersession",
                "round-supersession",
                {"status": "superseded"},
                (
                    ArtifactRef("successor", "lineage", 1),
                    ArtifactRef("prior", source.id, source.revision),
                ),
            ),
        ),
    )

    assert successor.parent_round_id == "prior"
    assert [artifact.id for artifact in successor_artifacts] == ["feedback", "lineage"]
    assert predecessor_artifacts[0].parent_refs == (
        ArtifactRef("successor", "lineage", 1),
        ArtifactRef("prior", source.id, source.revision),
    )
    assert ledger.get_revision("successor") == 2
    assert ledger.get_revision("prior") == 2
    assert [event.kind for event in ledger.load_run("successor").lineage_events] == [
        "run-created",
        "artifact-appended",
        "artifact-appended",
    ]
    assert [event.kind for event in ledger.load_run("prior").lineage_events] == [
        "run-created",
        "artifact-appended",
        "artifact-appended",
    ]


def test_successor_batches_reject_stale_predecessor_without_creating_child(tmp_path: Path) -> None:
    RunLedger, LedgerConflictError, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.create_run("prior")
    ledger.append_artifact("prior", "source", "input-ledger-entry", {}, expected_revision=0)

    with pytest.raises(LedgerConflictError, match="stale run revision"):
        ledger.create_successor_with_artifact_batches(
            predecessor_run_id="prior",
            successor_run_id="successor",
            successor_parent_run_id="prior",
            expected_predecessor_revision=0,
            successor_entries=(("feedback", "input-ledger-entry", {}, ()),),
            predecessor_entries=(("supersession", "round-supersession", {}, ()),),
        )

    assert ledger.get_revision("prior") == 1
    with pytest.raises(LedgerIntegrityError, match="run does not exist: successor"):
        ledger.load_run("successor")


def test_successor_batches_roll_back_both_runs_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RunLedger, _, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.create_run("prior")
    source = ledger.append_artifact("prior", "source", "input-ledger-entry", {}, expected_revision=0)
    before = ledger.load_run("prior")
    monkeypatch.setattr(ledger, "_before_commit", lambda: (_ for _ in ()).throw(RuntimeError("injected")))

    with pytest.raises(RuntimeError, match="injected"):
        ledger.create_successor_with_artifact_batches(
            predecessor_run_id="prior",
            successor_run_id="successor",
            successor_parent_run_id="prior",
            expected_predecessor_revision=ledger.get_revision("prior"),
            successor_entries=(("feedback", "input-ledger-entry", {}, ()),),
            predecessor_entries=(
                (
                    "supersession",
                    "round-supersession",
                    {},
                    (ArtifactRef("prior", source.id, source.revision),),
                ),
            ),
        )

    assert ledger.load_run("prior") == before
    with pytest.raises(LedgerIntegrityError, match="run does not exist: successor"):
        ledger.load_run("successor")


def test_successor_batches_roll_back_if_a_later_parent_is_invalid(tmp_path: Path) -> None:
    RunLedger, _, LedgerIntegrityError = api()
    ledger = RunLedger(tmp_path)
    ledger.create_run("prior")
    before = ledger.load_run("prior")

    with pytest.raises(LedgerIntegrityError, match="artifact parent does not exist"):
        ledger.create_successor_with_artifact_batches(
            predecessor_run_id="prior",
            successor_run_id="successor",
            successor_parent_run_id="prior",
            expected_predecessor_revision=0,
            successor_entries=(
                ("feedback", "input-ledger-entry", {}, ()),
                ("lineage", "feedback-lineage", {}, (ArtifactRef("prior", "missing", 1),)),
            ),
            predecessor_entries=(("supersession", "round-supersession", {}, ()),),
        )

    assert ledger.load_run("prior") == before
    with pytest.raises(LedgerIntegrityError, match="run does not exist: successor"):
        ledger.load_run("successor")


def test_concurrent_readers_see_committed_snapshots(tmp_path: Path) -> None:
    RunLedger, _, _ = api()
    ledger = RunLedger(tmp_path)
    ledger.initialize()
    ledger.create_run("run-1")
    errors: list[BaseException] = []

    def reader() -> None:
        try:
            for _ in range(20):
                ledger.load_run("run-1")
        except BaseException as error:  # pragma: no cover - diagnostic path
            errors.append(error)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    ledger.append_artifact("run-1", "one", "finding", {}, expected_revision=0)
    for thread in threads:
        thread.join()

    assert errors == []
