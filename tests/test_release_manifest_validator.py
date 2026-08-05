import hashlib
import json

from scripts.verify_release_manifest import verify


def _manifest():
    digest = hashlib.sha256(b"package").hexdigest()
    return {
        "manifest_version": 1,
        "source_revision": "abc123",
        "created_at": "2026-08-05T00:00:00+00:00",
        "schema_versions": {"runtime": 1},
        "host_packages": [{"host": host, "package_revision": "r1", "package_digest": digest, "smoke_result": "passed"} for host in ("codex", "claude-code", "hermes")],
        "commands": [{"command": "uv run pytest -q", "status": "passed"}],
        "evaluations": [],
        "gates": [{"name": "false_completion", "status": "passed"}],
        "limitations": [],
        "verifier": {"identity": "ci-test"},
    }


def test_release_manifest_matches_current_schema(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    assert verify(path)["valid"] is True


def test_release_manifest_rejects_bom_and_missing_host(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_manifest()).encode("utf-8"))
    assert verify(path)["valid"] is False
    path.write_text(json.dumps({**_manifest(), "host_packages": []}), encoding="utf-8")
    assert verify(path)["valid"] is False
