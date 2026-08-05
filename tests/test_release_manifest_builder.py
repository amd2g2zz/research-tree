import pytest

from scripts.create_release_manifest import build_manifest, write_manifest
from scripts.verify_release_manifest import verify


def test_release_manifest_builder_hashes_hosts_and_is_immutable(tmp_path):
    for host in ("codex", "claude-code", "hermes"):
        package = tmp_path / "packages" / host / "research-tree"
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(host, encoding="utf-8")
    manifest = build_manifest(repository=tmp_path, source_revision="rev-1", commands=[{"command": "pytest", "status": "passed"}], evaluations=[], gates=[{"name": "false_completion", "status": "passed"}], created_at="2026-08-05T00:00:00+00:00")
    assert len({item["package_digest"] for item in manifest["host_packages"]}) == 3
    output = write_manifest(tmp_path / "release.json", manifest)
    assert verify(output)["valid"] is True
    with pytest.raises(FileExistsError):
        write_manifest(output, manifest)
