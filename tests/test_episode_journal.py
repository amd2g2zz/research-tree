from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
KEY = b"evaluator-journal-key-v1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


JOURNAL = load_module("episode_journal", ROOT / "evaluation/harness/episode_journal.py")
FIXTURES = load_module("paired_benchmark_fixtures", ROOT / "tests/test_paired_benchmark.py")


def test_journal_recovers_only_at_episode_boundaries(tmp_path: Path) -> None:
    journal = JOURNAL.EpisodeJournal(tmp_path, attestation_key=KEY)
    manifest = FIXTURES.sealed_manifest()
    run_id = journal.initialize(manifest, harness_revision="test-revision")
    episode_id = manifest["episode_plan"][0]["episode_id"]
    attempt_id = journal.reserve(run_id, episode_id)
    contract = journal._contract(run_id, episode_id)
    observed = {name: contract[name] for name in JOURNAL._OBSERVED_FIELDS}

    journal.start(run_id, episode_id, attempt_id, observed)
    paired_group = tuple(
        entry["episode_id"]
        for entry in manifest["episode_plan"]
        if entry["task_id"] == manifest["episode_plan"][0]["task_id"]
        and entry["role"] == manifest["episode_plan"][0]["role"]
        and entry["repeat"] == manifest["episode_plan"][0]["repeat"]
    )
    assert journal.abandon_started(run_id) == tuple(sorted(paired_group))
    assert set(paired_group).issubset(journal.pending(run_id))

    next_attempt = journal.reserve(run_id, episode_id)
    assert next_attempt.endswith(":2")
    journal.start(run_id, episode_id, next_attempt, observed)
    journal.checkpoint(
        run_id,
        episode_id,
        next_attempt,
        status="completed",
        result_digest=FIXTURES.digest("1"),
        source_capture_set_digest=FIXTURES.digest("2"),
        transcript_digest=FIXTURES.digest("3"),
        synthetic_session_receipt_digest=FIXTURES.digest("4"),
        token_usage={"cache_hit_input_tokens": 7, "cache_miss_input_tokens": 3, "output_tokens": 2},
        integrity={"completion_forgery": False},
    )

    journal.verify(run_id)
    assert episode_id not in journal.pending(run_id)
    journal.close()


def test_journal_rejects_stale_runtime_and_tampered_event_chain(tmp_path: Path) -> None:
    journal = JOURNAL.EpisodeJournal(tmp_path, attestation_key=KEY)
    manifest = FIXTURES.sealed_manifest()
    run_id = journal.initialize(manifest, harness_revision="test-revision")
    episode_id = manifest["episode_plan"][0]["episode_id"]
    attempt_id = journal.reserve(run_id, episode_id)
    contract = journal._contract(run_id, episode_id)
    observed = {name: contract[name] for name in JOURNAL._OBSERVED_FIELDS}
    observed["runtime_digest"] = FIXTURES.digest("f")

    with pytest.raises(JOURNAL.EpisodeJournalError, match="does not match"):
        journal.start(run_id, episode_id, attempt_id, observed)

    with pytest.raises(Exception, match="append-only"):
        journal.connection.execute("UPDATE events SET kind = 'forged' WHERE run_id = ?", (run_id,))
    journal.close()

    wrong_key = JOURNAL.EpisodeJournal(tmp_path, attestation_key=b"different-evaluator-key-v1")
    with pytest.raises(JOURNAL.EpisodeJournalError, match="attestation"):
        wrong_key.verify(run_id)
    wrong_key.close()


def test_terminal_failure_invalidates_the_entire_paired_group(tmp_path: Path) -> None:
    journal = JOURNAL.EpisodeJournal(tmp_path, attestation_key=KEY)
    manifest = FIXTURES.sealed_manifest()
    run_id = journal.initialize(manifest, harness_revision="test-revision")
    episode_id = manifest["episode_plan"][0]["episode_id"]
    attempt_id = journal.reserve(run_id, episode_id)
    contract = journal._contract(run_id, episode_id)
    journal.start(run_id, episode_id, attempt_id, {name: contract[name] for name in JOURNAL._OBSERVED_FIELDS})
    journal.checkpoint(
        run_id,
        episode_id,
        attempt_id,
        status="failed",
        result_digest=FIXTURES.digest("1"),
        source_capture_set_digest=FIXTURES.digest("2"),
        transcript_digest=FIXTURES.digest("3"),
        synthetic_session_receipt_digest=FIXTURES.digest("4"),
        token_usage={"cache_hit_input_tokens": 0, "cache_miss_input_tokens": 0, "output_tokens": 0},
        integrity={"runner_failure": True},
    )

    invalidated = journal.invalidate_group(run_id, episode_id, reason_code="host_command_failed")

    assert len(invalidated) == 6
    assert set(invalidated).issubset(journal.pending(run_id))
    journal.close()
