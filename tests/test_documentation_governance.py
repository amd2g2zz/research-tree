from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "openspec/changes/unify-research-runtime-alpha2/registries/documentation-authority-v1.json"


def checker():
    path = ROOT / "scripts/check_docs.py"
    spec = importlib.util.spec_from_file_location("check_docs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_registry(root: Path, entries: list[dict[str, object]]) -> Path:
    payload = {
        "schema_version": 1,
        "precedence": ["product", "historical", "generated"],
        "forbidden_active_terms": ["Human Brief"],
        "entries": entries,
    }
    path = root / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def entry(path: str, *, document_class: str = "normative", lifecycle: str = "active") -> dict[str, object]:
    return {
        "path": path,
        "class": document_class,
        "authority": "product",
        "audience": "contributors",
        "owner": "maintainers",
        "lifecycle": lifecycle,
        "canonical_edit": path,
        "update_trigger": "contract change",
        "superseded_by": "PRODUCT.md" if lifecycle in {"historical", "superseded"} else None,
        "validation_rule": "governed",
    }


def test_repository_registry_covers_documentation_classes_and_checker_passes() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    classes = {item["class"] for item in registry["entries"]}
    archived_changes = next(item for item in registry["entries"] if item["path"] == "openspec/changes/archive/")

    assert {"normative", "generated", "historical", "operational", "evaluation"} <= classes
    assert archived_changes["lifecycle"] == "historical"
    assert checker().validate_repository(ROOT, REGISTRY)["errors"] == []


def test_active_documentation_is_grouped_by_audience_and_history_is_stable() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = {item["path"]: item for item in registry["entries"]}

    assert {
        "docs/guides/",
        "docs/contributing/",
        "docs/governance/",
        "docs/architecture/",
        "docs/evaluation/",
        "docs/history/",
    } <= set(entries)
    assert entries["docs/history/"]["class"] == "historical"
    assert entries["docs/history/"]["lifecycle"] == "active"
    assert {
        "docs/guides/agent.md",
        "docs/guides/operator.md",
        "docs/guides/use-cases.md",
        "docs/contributing/development-workflow.md",
        "docs/governance/documentation-authority.md",
        "docs/governance/evaluation-assets.md",
        "docs/evaluation/research/",
    } <= set(entries)
    assert not any(
        (ROOT / path).exists()
        for path in (
            "docs/agent-guide.md",
            "docs/operator-guide.md",
            "docs/use-cases.md",
            "docs/development-workflow.md",
            "docs/documentation-authority.md",
            "docs/evaluation-assets.md",
            "docs/research",
        )
    )
    assert (ROOT / "docs/specs").is_dir()
    assert (ROOT / "docs/reviews").is_dir()
    assert (ROOT / "docs/需求理解.md").is_file()
    assert (ROOT / "docs/方案设计.md").is_file()


def test_checker_rejects_active_legacy_term_broken_link_and_unregistered_document(tmp_path: Path) -> None:
    (tmp_path / "PRODUCT.md").write_text("[missing](missing.md)\nHuman Brief\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("orphan\n", encoding="utf-8")
    registry = write_registry(tmp_path, [entry("PRODUCT.md")])

    errors = checker().validate_repository(tmp_path, registry)["errors"]

    assert {(item["code"], item["path"]) for item in errors} == {
        ("broken-link", "PRODUCT.md"),
        ("legacy-term", "PRODUCT.md"),
        ("undocumented-root", "notes.md"),
    }


def test_checker_skips_ignored_untracked_generated_documents(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("/AGENTS.md\n.claude/\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("generated context\n", encoding="utf-8")
    generated = tmp_path / ".claude" / "skills" / "gitnexus" / "SKILL.md"
    generated.parent.mkdir(parents=True)
    generated.write_text("generated context\n", encoding="utf-8")

    registry = write_registry(tmp_path, [])

    assert checker().validate_repository(tmp_path, registry)["errors"] == []


def test_checker_permits_historical_legacy_term_with_supersession(tmp_path: Path) -> None:
    (tmp_path / "docs/specs/RT-001.md").parent.mkdir(parents=True)
    (tmp_path / "docs/specs/RT-001.md").write_text("Human Brief\n", encoding="utf-8")
    registry = write_registry(tmp_path, [entry("docs/specs/", document_class="historical", lifecycle="historical")])

    assert checker().validate_repository(tmp_path, registry)["errors"] == []


def test_checker_rejects_missing_lifecycle_metadata_and_misplaced_session_log(tmp_path: Path) -> None:
    (tmp_path / "docs/session-log.md").parent.mkdir(parents=True)
    (tmp_path / "docs/session-log.md").write_text("log\n", encoding="utf-8")
    malformed = entry("docs/")
    malformed.pop("validation_rule")
    registry = write_registry(tmp_path, [malformed])

    errors = checker().validate_repository(tmp_path, registry)["errors"]

    assert {(item["code"], item["path"]) for item in errors} == {
        ("invalid-registry", "entries[0].validation_rule"),
        ("misplaced-session-log", "docs/session-log.md"),
    }


def test_checker_reports_stale_generated_package_copy(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "packages/guide.md").parent.mkdir(parents=True)
    (tmp_path / "packages/guide.md").write_text("generated\n", encoding="utf-8")
    package_entry = entry("packages/", document_class="generated", lifecycle="generated")
    package_entry["validation_rule"] = "package-build-check"
    registry = write_registry(tmp_path, [package_entry])
    module = checker()
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="stale copy", stdout="")
    )

    errors = module.validate_repository(tmp_path, registry, check_packages=True)["errors"]

    assert errors == [{"code": "stale-generated-copy", "path": "packages/", "detail": "stale copy"}]
