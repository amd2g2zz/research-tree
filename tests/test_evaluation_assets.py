from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "openspec/changes/unify-research-runtime-alpha2/registries/evaluation-paths-v1.json"


def checker():
    import importlib.util

    path = ROOT / "scripts/check_evaluation_assets.py"
    spec = importlib.util.spec_from_file_location("check_evaluation_assets", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_registry(root: Path, *, result_limit: int = 65_536) -> Path:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry["limits"]["tracked_result_bytes"] = result_limit
    path = root / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


def retained_asset(*, asset_id: str = "result-1", case_id: str = "public-case") -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": asset_id,
        "case_id": case_id,
        "source_revision": "a" * 40,
        "environment": "python:3.12@sha256:" + "b" * 64,
        "producer": "evaluation-harness-v1",
        "recorded_at": "2026-08-12T00:00:00Z",
        "artifact_refs": ["artifact:public-summary"],
        "limitations": ["Public validation does not execute hidden oracles."],
        "content_digest": "sha256:" + "c" * 64,
    }


def test_registry_defines_one_canonical_root_and_non_overlapping_classes() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert registry["canonical_root"] == "evaluation/"
    assert registry["disposable_root"] == ".research-tree/evaluation-runs/"
    paths = [entry["path"] for entry in registry["entries"]]
    assert len(paths) == len(set(paths))
    assert next(entry for entry in registry["entries"] if entry["path"] == "evals/")["mutable"] == "forbidden"
    assert set(registry["entrypoints"]) == {
        "unit",
        "integration",
        "public_alpha1",
        "black_box",
        "cross_host",
        "expert_review",
        "claude_glm_regression",
    }


def test_repository_assets_and_public_baseline_are_deterministic() -> None:
    module = checker()

    report = module.validate_repository(ROOT, REGISTRY)
    first = module.run_public_alpha1(ROOT, REGISTRY)
    second = module.run_public_alpha1(ROOT, REGISTRY)

    assert report["errors"] == []
    assert first == second
    assert first["status"] == "validated"
    assert first["manifest"] == "evaluation/cases/alpha1-adversarial-v1.json"
    assert first["manifest_digest"].startswith("sha256:")


@pytest.mark.parametrize(
    ("relative_path", "payload", "code"),
    [
        ("evals/result.json", {"id": "ambiguous"}, "misplaced-path"),
        ("evaluation/results/raw.json", {**retained_asset(), "provider_transcript": "private"}, "hidden-material"),
        ("evaluation/results/dangling.json", retained_asset(case_id="missing-case"), "dangling-reference"),
    ],
)
def test_governance_rejects_misplaced_leaking_and_dangling_assets(
    tmp_path: Path, relative_path: str, payload: dict[str, object], code: str
) -> None:
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(payload), encoding="utf-8")

    report = checker().validate_repository(tmp_path, write_registry(tmp_path))

    assert any(error["code"] == code and error["path"] == relative_path for error in report["errors"])


def test_governance_rejects_oversized_tracked_result(tmp_path: Path) -> None:
    cases = tmp_path / "evaluation/cases/cases.json"
    cases.parent.mkdir(parents=True)
    cases.write_text(json.dumps({"schema_version": 1, "cases": [{"id": "public-case"}]}), encoding="utf-8")
    target = tmp_path / "evaluation/results/result.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({**retained_asset(), "padding": "x" * 512}), encoding="utf-8")

    report = checker().validate_repository(tmp_path, write_registry(tmp_path, result_limit=128))

    assert report["errors"] == [
        {
            "code": "oversized-asset",
            "path": "evaluation/results/result.json",
            "detail": "tracked asset exceeds 128 bytes",
        }
    ]


def test_legacy_inventory_is_path_only_and_non_destructive(tmp_path: Path) -> None:
    target = tmp_path / "evaluation/experiences/private-session.jsonl"
    target.parent.mkdir(parents=True)
    original = b'credential="do-not-read-or-change"\n'
    target.write_bytes(original)
    before = target.stat()

    report = checker().validate_repository(tmp_path, write_registry(tmp_path))

    after = target.stat()
    assert report["errors"] == []
    assert report["legacy_candidates"] == ["evaluation/experiences/"]
    assert target.read_bytes() == original
    assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size)
    assert hashlib.sha256(original).hexdigest() not in json.dumps(report)
