from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "openspec/changes/unify-research-runtime-alpha2/registries/repository-paths-v1.json"


def checker():
    path = ROOT / "scripts/check_repository_layout.py"
    spec = importlib.util.spec_from_file_location("check_repository_layout", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_registry(root: Path, entries: list[dict[str, object]]) -> Path:
    path = root / "registry.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")
    return path


def entry(path: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "path": path,
        "asset_class": "authoring_source",
        "owner": "maintainers",
        "mutability": "source",
        "tracked": True,
        "distributed": False,
        "cleanup_safety": "never_delete",
        "canonical_command": "uv run pytest -q",
        "lifecycle": "active",
    }
    value.update(overrides)
    return value


def test_registry_covers_tracked_roots_and_required_lifecycle() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    entries = {item["path"]: item for item in registry["entries"]}
    assert set(entries) >= {
        ".claude-plugin/",
        ".github/",
        ".research-tree-hermes/",
        ".research-tree-native/",
        "src/",
        "tests/",
        "packages/",
        "pyproject.toml",
        "README.md",
    }
    assert all(item["lifecycle"] for item in entries.values())
    assert entries["packages/"]["asset_class"] == "generated_distribution"
    assert entries[".claude-plugin/"]["asset_class"] == "generated_distribution"
    assert checker().validate_repository(ROOT, REGISTRY)["errors"] == []


def test_checker_reports_missing_lifecycle_and_unregistered_tracked_root(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "runtime.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("root\n", encoding="utf-8")
    registry = write_registry(tmp_path, [entry("src/")])
    malformed = json.loads(registry.read_text(encoding="utf-8"))
    malformed["entries"][0].pop("lifecycle")
    registry.write_text(json.dumps(malformed), encoding="utf-8")

    report = checker().validate_repository(tmp_path, registry, tracked_roots={"src", "README.md"})

    assert report["errors"] == [
        {
            "code": "unregistered-tracked-root",
            "path": "README.md",
            "detail": "add a registry entry for this checkout root",
        },
        {
            "code": "invalid-registry",
            "path": "entries[0].lifecycle",
            "detail": "field is required",
        },
    ]


def test_checker_rejects_schema_type_drift(tmp_path: Path) -> None:
    malformed = entry(
        "src/",
        owner="",
        tracked="yes",
        distributed="no",
        canonical_command=1,
    )
    registry = write_registry(tmp_path, [malformed])

    report = checker().validate_repository(tmp_path, registry, tracked_roots={"src"})

    assert report["errors"] == [
        {
            "code": "invalid-registry",
            "path": "entries[0].canonical_command",
            "detail": "canonical_command must be a string or null",
        },
        {
            "code": "invalid-registry",
            "path": "entries[0].distributed",
            "detail": "distributed must be a boolean",
        },
        {
            "code": "invalid-registry",
            "path": "entries[0].owner",
            "detail": "owner must be non-empty",
        },
        {
            "code": "invalid-registry",
            "path": "entries[0].tracked",
            "detail": "tracked must be a boolean",
        },
    ]


def test_checker_reads_field_constraints_from_the_schema(tmp_path: Path) -> None:
    schema = json.loads(
        (ROOT / "openspec/changes/unify-research-runtime-alpha2/schemas/path-registry-v1.json").read_text(
            encoding="utf-8"
        )
    )
    schema["$defs"]["entry"]["properties"]["asset_class"]["enum"].append("test_only_asset")
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    registry = write_registry(tmp_path, [entry("src/", asset_class="test_only_asset")])

    entries, errors = checker()._load_registry(registry, schema_path)

    assert entries == [entry("src/", asset_class="test_only_asset")]
    assert errors == []


def test_checker_rejects_invalid_registry_envelope(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps({"schema_version": 1, "entries": [], "unexpected": True}),
        encoding="utf-8",
    )

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_roots=set(),
        tracked_paths=set(),
        checkout_roots=set(),
    )

    assert report["errors"] == [
        {
            "code": "invalid-registry",
            "path": "entries",
            "detail": "registry requires at least one entry",
        },
        {
            "code": "invalid-registry",
            "path": "unexpected",
            "detail": "field is not allowed",
        },
    ]


def test_checker_rejects_empty_operator_migration_target(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("research-runs/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry(
                "research-runs/",
                asset_class="evaluation_output",
                owner="quality",
                mutability="operator_migrated",
                tracked=False,
                cleanup_safety="never_delete",
                canonical_command="research-tree run-export-audit",
                lifecycle="operator-managed",
                migration_target="",
                migration_disposition="manual_relocate_after_audit",
            )
        ],
    )

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_roots=set(),
        tracked_paths=set(),
        checkout_roots=set(),
    )

    assert report["errors"] == [
        {
            "code": "invalid-registry",
            "path": "entries[0].migration_target",
            "detail": "migration_target must be non-empty",
        }
    ]


def test_checker_reports_missing_exact_ignore_and_protects_registered_local_root(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry(
                ".codex/",
                asset_class="installed_copy",
                owner="codex",
                mutability="generated_or_link",
                tracked=False,
                cleanup_safety="explicit_confirmation",
                canonical_command="research-tree-setup install --host codex --scope project",
                lifecycle="local",
            )
        ],
    )

    report = checker().validate_repository(tmp_path, registry, tracked_roots=set())

    assert report["errors"] == [
        {
            "code": "missing-ignore-rule",
            "path": ".codex/",
            "detail": "registered untracked root requires an exact .gitignore rule",
        }
    ]
    assert report["protected_local_paths"] == [".codex/"]
    assert (tmp_path / ".codex" / "hooks.json").is_file()


def test_checker_rejects_git_tracked_installed_copy(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry(
                ".agents/",
                asset_class="installed_copy",
                owner="codex",
                mutability="generated_or_link",
                tracked=False,
                cleanup_safety="explicit_confirmation",
                canonical_command="research-tree-setup install --host codex --scope project",
                lifecycle="local",
            )
        ],
    )

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_roots={".agents"},
        tracked_paths={".agents/skills/research-tree/SKILL.md"},
    )

    assert report["errors"] == [
        {
            "code": "tracked-policy-mismatch",
            "path": ".agents/",
            "detail": "registry marks this path untracked but Git contains it",
        }
    ]


def test_checker_rejects_registered_tracked_path_missing_from_git(tmp_path: Path) -> None:
    registry = write_registry(tmp_path, [entry("src/")])

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_roots=set(),
        tracked_paths=set(),
    )

    assert report["errors"] == [
        {
            "code": "tracked-policy-mismatch",
            "path": "src/",
            "detail": "registry marks this path tracked but Git has no files",
        }
    ]


def test_checker_rejects_invalid_generated_package_boundaries(tmp_path: Path) -> None:
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages" / "skill.md").write_text("generated\n", encoding="utf-8")
    registry = write_registry(tmp_path, [entry("packages/")])

    boundary_report = checker().validate_repository(tmp_path, registry, tracked_roots={"packages"})
    assert {error["code"] for error in boundary_report["errors"]} == {
        "invalid-package-boundary",
        "invalid-package-command",
    }

    command_registry = write_registry(
        tmp_path,
        [
            entry(
                "packages/",
                asset_class="generated_distribution",
                owner="release",
                mutability="rebuildable",
                cleanup_safety="safe_rebuild",
                canonical_command="python build.py",
                lifecycle="generated",
            )
        ],
    )
    command_report = checker().validate_repository(tmp_path, command_registry, tracked_roots={"packages"})
    assert [error["code"] for error in command_report["errors"]] == ["invalid-package-command"]


def test_checkout_inventory_does_not_skip_registered_cache_roots(tmp_path: Path) -> None:
    (tmp_path / ".pytest_cache").mkdir()
    registry = write_registry(tmp_path, [entry("src/")])

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_paths=set(),
        checkout_roots={".pytest_cache"},
    )

    assert {(error["code"], error["path"]) for error in report["errors"]} >= {
        ("unregistered-checkout-root", ".pytest_cache")
    }


def test_checkout_inventory_accepts_registered_egg_info_pattern(tmp_path: Path) -> None:
    (tmp_path / "research_tree.egg-info").mkdir()
    (tmp_path / ".gitignore").write_text("*.egg-info/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry(
                "*.egg-info/",
                asset_class="cache",
                owner="maintainers",
                mutability="disposable",
                tracked=False,
                cleanup_safety="safe_ignore",
                canonical_command="uv build",
                lifecycle="local",
            )
        ],
    )

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_paths=set(),
        checkout_roots={"research_tree.egg-info"},
    )

    assert report["errors"] == []
    assert report["protected_local_paths"] == []


def test_checker_reports_unregistered_checkout_root_and_install_boundary_drift(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry("src/"),
            entry(
                ".agents/",
                tracked=False,
                asset_class="authoring_source",
                mutability="source",
            ),
        ],
    )

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_roots={"src"},
        checkout_roots={"src", "scratch"},
    )

    assert report["errors"] == [
        {
            "code": "invalid-installed-boundary",
            "path": ".agents/",
            "detail": ".agents/ must be installed_copy and generated_or_link",
        },
        {
            "code": "unregistered-checkout-root",
            "path": "scratch",
            "detail": "add a registry entry or relocate this path",
        },
    ]


def test_checker_rejects_runtime_output_under_authoring_source(tmp_path: Path) -> None:
    (tmp_path / "src" / ".research-tree").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text(".research-tree/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry("src/"),
            entry(
                ".research-tree/",
                asset_class="runtime_state",
                owner="runtime",
                mutability="append_only_or_rebuildable",
                tracked=False,
                cleanup_safety="never_delete",
                canonical_command="research-tree run-status",
                lifecycle="runtime",
            ),
        ],
    )

    report = checker().validate_repository(tmp_path, registry, tracked_roots={"src"})

    assert report["errors"] == [
        {
            "code": "misplaced-runtime-output",
            "path": "src/.research-tree/",
            "detail": "runtime state belongs in .research-tree/ via research-tree run-status",
        }
    ]


def test_migration_plan_reports_collision_without_touching_user_material(tmp_path: Path) -> None:
    source = tmp_path / "research-runs"
    target = tmp_path / ".research-tree" / "evaluation-runs"
    source.mkdir()
    target.mkdir(parents=True)
    (source / "user-run.json").write_text('{"user": true}\n', encoding="utf-8")
    (target / "existing-run.json").write_text('{"existing": true}\n', encoding="utf-8")
    (tmp_path / ".gitignore").write_text("research-runs/\n.research-tree/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry(
                "research-runs/",
                asset_class="evaluation_output",
                owner="quality",
                mutability="operator_migrated",
                tracked=False,
                cleanup_safety="never_delete",
                canonical_command="research-tree run-export-audit",
                lifecycle="operator-managed",
                migration_target=".research-tree/evaluation-runs/",
                migration_disposition="manual_relocate_after_audit",
            ),
            entry(
                ".research-tree/",
                asset_class="runtime_state",
                owner="runtime",
                mutability="append_only_or_rebuildable",
                tracked=False,
                cleanup_safety="never_delete",
                canonical_command="research-tree run",
                lifecycle="runtime",
            ),
        ],
    )

    report = checker().migration_plan(tmp_path, registry)

    assert report["status"] == "collision_detected"
    assert report["moves_performed"] == 0
    assert report["confirmation_token"]
    assert report["items"] == [
        {
            "source": "research-runs/",
            "destination": ".research-tree/evaluation-runs/",
            "disposition": "manual_relocate_after_audit",
            "collision": True,
        }
    ]
    assert (source / "user-run.json").read_text(encoding="utf-8") == '{"user": true}\n'


def test_checker_requires_migration_map_for_operator_migrated_path(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("research-runs/\n", encoding="utf-8")
    registry = write_registry(
        tmp_path,
        [
            entry(
                "research-runs/",
                asset_class="evaluation_output",
                owner="quality",
                mutability="operator_migrated",
                tracked=False,
                cleanup_safety="never_delete",
                canonical_command="research-tree run-export-audit",
                lifecycle="operator-managed",
            )
        ],
    )

    report = checker().validate_repository(
        tmp_path,
        registry,
        tracked_roots=set(),
        tracked_paths=set(),
        checkout_roots=set(),
    )

    assert report["errors"] == [
        {
            "code": "invalid-registry",
            "path": "entries[0].migration_target",
            "detail": "operator-migrated paths require a target and disposition",
        }
    ]


def test_supported_workflow_probe_uses_temporary_project_and_preserves_checkout() -> None:
    report = checker().workflow_probe(ROOT)

    assert report["status"] == "valid"
    assert report["repository_status_unchanged"] is True
    assert report["installed_project_roots"] == [".agents"]
    assert report["sample_run"] == "migration_inventory"
