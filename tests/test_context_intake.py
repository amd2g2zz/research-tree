from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


def intake_api():
    from research_tree import (
        ArtifactRef,
        CanonicalInputIntakeService,
        InputIntakeService,
        InvalidContextBundleError,
        RepositoryInspector,
        RepositorySafetyPolicy,
        RunLedger,
        RunStore,
    )

    return {
        "ArtifactRef": ArtifactRef,
        "CanonicalInputIntakeService": CanonicalInputIntakeService,
        "InputIntakeService": InputIntakeService,
        "InvalidContextBundleError": InvalidContextBundleError,
        "RepositoryInspector": RepositoryInspector,
        "RepositorySafetyPolicy": RepositorySafetyPolicy,
        "RunLedger": RunLedger,
        "RunStore": RunStore,
    }


def write_file(root: Path, relative_path: str, content: str | bytes) -> Path:
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        destination.write_bytes(content)
    else:
        destination.write_text(content, encoding="utf-8")
    return destination


def git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def create_repository_fixture(root: Path) -> Path:
    repository = root / "repository"
    write_file(
        repository,
        "src/app.py",
        """class Application:\n    pass\n\n\ndef main() -> None:\n    return None\n""",
    )
    write_file(repository, "tests/test_app.py", "from src.app import main\n\ndef test_main():\n    assert main() is None\n")
    write_file(repository, "pyproject.toml", "[project]\nname = 'fixture'\nversion = '0.0.0'\n")
    write_file(repository, "Dockerfile", "FROM python:3.11-slim\n")
    write_file(repository, ".github/workflows/verify.yml", "name: verify\non: push\n")
    write_file(repository, "api/openapi.yaml", "openapi: 3.0.0\ninfo:\n  title: Fixture\n")
    write_file(repository, "README.md", "fixture\n")
    git(repository, "init", "--quiet")
    git(repository, "config", "user.email", "fixture@example.test")
    git(repository, "config", "user.name", "Fixture")
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", "initial fixture")
    return repository


def test_text_inputs_are_independent_and_reingestion_preserves_prior_revision(
    tmp_path: Path,
) -> None:
    api = intake_api()
    ledger = api["RunLedger"](tmp_path / "ledger")
    ledger.initialize()
    round_record = ledger.create_run("round-intake")
    intake = api["CanonicalInputIntakeService"](ledger)

    brief = intake.ingest_text(
        round_id=round_record.id,
        input_id="input-brief",
        kind="brief",
        content="Build an autonomous reverse-engineering agent.",
        origin_type="user",
        origin_locator="conversation:1",
        role="signal",
        expected_revision=ledger.get_revision(round_record.id),
    )
    article = intake.ingest_text(
        round_id=round_record.id,
        input_id="input-article",
        kind="article",
        content="A supplied article presents one implementation direction.",
        origin_type="url",
        origin_locator="https://example.test/article",
        role="evidence",
        expected_revision=ledger.get_revision(round_record.id),
    )
    first_note = intake.ingest_text(
        round_id=round_record.id,
        input_id="input-note",
        kind="note",
        content="Prefer an isolated local-first demo.",
        origin_type="user",
        origin_locator="conversation:1",
        role="constraint",
        expected_revision=ledger.get_revision(round_record.id),
    )
    second_note = intake.ingest_text(
        round_id=round_record.id,
        input_id="input-note",
        kind="note",
        content="Prefer a cloud-hosted demo after all.",
        origin_type="user",
        origin_locator="conversation:2",
        role="constraint",
        expected_revision=ledger.get_revision(round_record.id),
    )

    assert [brief.id, article.id, first_note.id] == [
        "input-brief",
        "input-article",
        "input-note",
    ]
    assert brief.kind == article.kind == first_note.kind == "input-ledger-entry"
    assert brief.payload["origin"] == {"type": "user", "locator": "conversation:1"}
    assert brief.payload["revision"]["sha256"]
    assert brief.payload["used_by_rounds"] == (round_record.id,)
    assert brief.payload["material"] == {
        "kind": "inline-text",
        "content": "Build an autonomous reverse-engineering agent.",
    }
    assert second_note.revision == 2

    note_revisions = [
        artifact
        for artifact in ledger.load_run(round_record.id).artifacts
        if artifact.id == "input-note"
    ]
    assert [artifact.revision for artifact in note_revisions] == [1, 2]
    assert note_revisions[0].payload["material"]["content"] == "Prefer an isolated local-first demo."
    assert note_revisions[1].payload["material"]["content"] == "Prefer a cloud-hosted demo after all."


def test_context_bundle_preserves_conflicting_member_revisions_and_lineage(
    tmp_path: Path,
) -> None:
    api = intake_api()
    ledger = api["RunLedger"](tmp_path / "ledger")
    ledger.initialize()
    round_record = ledger.create_run("round-bundle")
    intake = api["CanonicalInputIntakeService"](ledger)
    first_note = intake.ingest_text(
        round_id=round_record.id,
        input_id="input-local",
        kind="note",
        content="The first demo must run locally.",
        origin_type="user",
        origin_locator="conversation:1",
        role="constraint",
        expected_revision=ledger.get_revision(round_record.id),
    )
    second_note = intake.ingest_text(
        round_id=round_record.id,
        input_id="input-cloud",
        kind="note",
        content="The first demo must be cloud-hosted.",
        origin_type="user",
        origin_locator="conversation:1",
        role="constraint",
        expected_revision=ledger.get_revision(round_record.id),
    )

    bundle = intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=("input-local", "input-cloud"),
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-local",
        kind="note",
        content="The local requirement is now optional.",
        origin_type="user",
        origin_locator="conversation:2",
        role="constraint",
        expected_revision=ledger.get_revision(round_record.id),
    )

    assert bundle.payload["kind"] == "context_bundle"
    assert bundle.payload["grouping"] == "user_provided"
    assert bundle.payload["member_input_ids"] == ("input-local", "input-cloud")
    assert bundle.parent_refs == (
        api["ArtifactRef"](round_record.id, "input-local", first_note.revision),
        api["ArtifactRef"](round_record.id, "input-cloud", second_note.revision),
    )
    assert bundle.payload["member_refs"] == (
        {"round_id": round_record.id, "artifact_id": "input-local", "revision": 1},
        {"round_id": round_record.id, "artifact_id": "input-cloud", "revision": 1},
    )
    assert "The first demo must run locally." not in bundle.payload
    assert "The first demo must be cloud-hosted." not in bundle.payload


def test_context_bundle_rejects_unknown_duplicate_and_nested_members_without_writing(
    tmp_path: Path,
) -> None:
    api = intake_api()
    ledger = api["RunLedger"](tmp_path / "ledger")
    ledger.initialize()
    round_record = ledger.create_run("round-bundle-invalid")
    intake = api["CanonicalInputIntakeService"](ledger)
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-note",
        kind="note",
        content="A note.",
        origin_type="user",
        origin_locator="conversation:1",
        role="signal",
        expected_revision=ledger.get_revision(round_record.id),
    )
    existing_bundle = intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-existing-bundle",
        member_input_ids=("input-note",),
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )
    updated_bundle = intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-existing-bundle",
        member_input_ids=("input-note",),
        origin_type="user",
        origin_locator="conversation:2",
        role="baseline",
        expected_revision=ledger.get_revision(round_record.id),
    )
    assert updated_bundle.revision == 2

    invalid_bundle_ids = (
        ("input-unknown",),
        ("input-note", "input-note"),
        (existing_bundle.id,),
    )
    for index, member_ids in enumerate(invalid_bundle_ids):
        with pytest.raises(api["InvalidContextBundleError"]):
            intake.create_context_bundle(
                round_id=round_record.id,
                input_id=f"input-invalid-{index}",
                member_input_ids=member_ids,
                origin_type="user",
                origin_locator="conversation:1",
                role="baseline",
                expected_revision=ledger.get_revision(round_record.id),
            )

    artifact_revisions = [
        (artifact.id, artifact.revision)
        for artifact in ledger.load_run(round_record.id).artifacts
    ]
    assert artifact_revisions == [
        ("input-existing-bundle", 1),
        ("input-existing-bundle", 2),
        ("input-note", 1),
    ]


def test_repository_intake_records_resolvable_git_baseline_without_running_repository_code(
    tmp_path: Path,
) -> None:
    api = intake_api()
    repository = create_repository_fixture(tmp_path)
    write_file(
        repository,
        "src/never_execute.py",
        "from pathlib import Path\nPath('execution-marker').write_text('bad')\n",
    )
    before_status = git(repository, "status", "--porcelain")

    store = api["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-repository")
    intake = api["InputIntakeService"](store)
    artifact = intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository,
        origin_type="workspace",
        role="baseline",
    )

    payload = artifact.payload
    baseline = payload["repository_baseline"]
    paths = {anchor["path"] for anchor in baseline["anchors"]}
    categories = {fact["category"] for fact in baseline["facts"]}
    symbols = {
        anchor["symbol"]
        for anchor in baseline["anchors"]
        if anchor["path"] == "src/app.py" and anchor["symbol"] is not None
    }

    assert payload["kind"] == "repository"
    assert payload["revision"]["commit"] == git(repository, "rev-parse", "HEAD")
    assert payload["revision"]["branch"] == git(repository, "branch", "--show-current")
    assert baseline["repository_root"] == str(repository.resolve())
    assert baseline["read_scope"] == (".",)
    assert {"src/app.py", "tests/test_app.py", "pyproject.toml", "Dockerfile"} <= paths
    assert {"source", "symbol", "dependency", "test", "deployment", "interface", "change_surface"} <= categories
    assert {"Application", "main"} <= symbols
    assert not (repository / "execution-marker").exists()
    assert git(repository, "status", "--porcelain") == before_status


def test_context_bundle_can_join_text_material_and_repository_without_flattening(
    tmp_path: Path,
) -> None:
    api = intake_api()
    repository = create_repository_fixture(tmp_path)
    store = api["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-heterogeneous-bundle")
    intake = api["InputIntakeService"](store)
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-brief",
        kind="brief",
        content="Build an implementation-ready technical blueprint.",
        origin_type="user",
        origin_locator="conversation:1",
        role="signal",
    )
    intake.ingest_text(
        round_id=round_record.id,
        input_id="input-article",
        kind="article",
        content="An article describes one potentially relevant technique.",
        origin_type="url",
        origin_locator="https://example.test/technique",
        role="evidence",
    )
    intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository,
        origin_type="workspace",
        role="baseline",
    )

    bundle = intake.create_context_bundle(
        round_id=round_record.id,
        input_id="input-context",
        member_input_ids=("input-brief", "input-article", "input-repository"),
        origin_type="user",
        origin_locator="conversation:1",
        role="baseline",
    )

    assert bundle.payload["member_input_ids"] == (
        "input-brief",
        "input-article",
        "input-repository",
    )
    assert [reference.artifact_id for reference in bundle.parent_refs] == [
        "input-brief",
        "input-article",
        "input-repository",
    ]
    assert "material" not in bundle.payload
    assert "repository_baseline" not in bundle.payload


def test_repository_reingestion_preserves_prior_baseline_revision(tmp_path: Path) -> None:
    api = intake_api()
    repository = create_repository_fixture(tmp_path)
    store = api["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-repository-revisions")
    intake = api["InputIntakeService"](store)

    first = intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository,
        origin_type="workspace",
        role="baseline",
    )
    write_file(repository, "src/app.py", "def main() -> str:\n    return 'changed'\n")
    git(repository, "add", "src/app.py")
    git(repository, "commit", "--quiet", "-m", "change fixture")
    second = intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository,
        origin_type="workspace",
        role="baseline",
    )

    revisions = [
        artifact
        for artifact in store.load_round(round_record.id).artifacts
        if artifact.id == "input-repository"
    ]
    assert [artifact.revision for artifact in revisions] == [1, 2]
    assert revisions[0] == first
    assert revisions[1] == second
    assert first.payload["revision"]["commit"] != second.payload["revision"]["commit"]
    assert first.payload["repository_baseline"]["revision"]["sha256"] != second.payload["repository_baseline"]["revision"]["sha256"]


def test_repository_boundary_controls_record_unsafe_material_without_aborting_safe_scan(
    tmp_path: Path,
) -> None:
    api = intake_api()
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    write_file(repository, "src/safe.py", "def safe() -> None:\n    return None\n")
    write_file(repository, ".env", "API_TOKEN=must-not-be-read\n")
    write_file(repository, "private.pem", "private key material\n")
    write_file(repository, "binary.bin", b"\x00binary")
    write_file(repository, "large.txt", "x" * 256)
    write_file(repository, "node_modules/dependency.js", "module.exports = {}\n")
    write_file(outside, "outside.py", "outside\n")
    external_link = repository / "external-link.py"
    link_created = False
    try:
        os.symlink(outside / "outside.py", external_link)
        link_created = True
    except OSError:
        # This uses the same pure classification method as the scanner, so the
        # safety rule remains covered when Windows does not grant link rights.
        assert (
            api["RepositoryInspector"].symlink_reason(repository, outside / "outside.py")
            == "external_symlink"
        )

    store = api["RunStore"](tmp_path / "store")
    round_record = store.create_round("round-boundaries")
    policy = api["RepositorySafetyPolicy"](max_file_bytes=64, max_total_bytes=512)
    intake = api["InputIntakeService"](store, policy=policy)
    artifact = intake.ingest_repository(
        round_id=round_record.id,
        input_id="input-repository",
        repository_root=repository,
        origin_type="workspace",
        role="baseline",
        include_paths=(".", "../outside"),
    )

    baseline = artifact.payload["repository_baseline"]
    unreadable = {(item["path"], item["reason"]) for item in baseline["unreadable"]}
    anchors = {anchor["path"] for anchor in baseline["anchors"]}

    assert "src/safe.py" in anchors
    assert (".env", "secret") in unreadable
    assert ("private.pem", "secret") in unreadable
    assert ("binary.bin", "binary") in unreadable
    assert ("large.txt", "too_large") in unreadable
    assert ("node_modules", "excluded_directory") in unreadable
    if link_created:
        assert ("external-link.py", "external_symlink") in unreadable
    assert ("../outside", "outside_repository") in unreadable
    assert all("must-not-be-read" not in str(item) for item in baseline["unreadable"])
