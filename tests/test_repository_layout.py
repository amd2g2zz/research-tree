from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "openspec/changes/unify-research-runtime-alpha2/registries/repository-paths-v1.json"


def checker():
    spec = importlib.util.spec_from_file_location(
        "check_repository_layout", ROOT / "scripts/check_repository_layout.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_registry(root: Path, entries: list[dict[str, object]]) -> Path:
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    path = root / "registry.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")
    return path


def report(root: Path, entries: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
    return checker().validate_repository(root, write_registry(root, entries), **kwargs)


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


def local_entry(path: str, **overrides: object) -> dict[str, object]:
    value = entry(
        path,
        asset_class="installed_copy",
        owner="codex",
        mutability="generated_or_link",
        tracked=False,
        cleanup_safety="explicit_confirmation",
        canonical_command="research-tree-setup install --host codex --scope project",
        lifecycle="local",
    )
    value.update(overrides)
    return value


def error(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def test_current_registry_covers_checkout_and_lifecycle() -> None:
    entries = {item["path"]: item for item in json.loads(REGISTRY.read_text(encoding="utf-8"))["entries"]}

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
    assert {entries[path]["asset_class"] for path in {"packages/", ".claude-plugin/"}} == {"generated_distribution"}
    assert checker().validate_repository(ROOT, REGISTRY)["errors"] == []


def test_repository_ignores_generated_verification_and_local_tooling_artifacts() -> None:
    required_rules = {
        ".research-tree/verification-runs/",
        "openspec/changes/**/evidence/*-output.txt",
        "openspec/changes/**/evidence/*-output.log",
        "openspec/changes/**/evidence/*-receipt.json",
        "openspec/changes/**/evidence/verification-*.md",
        "openspec/changes/**/evidence/future-evidence-gaps.json",
        "openspec/changes/**/evidence/integrated-strict-slices.json",
        "openspec/changes/**/evidence/integrated-receipt-byte-preservation-v*.json",
        "openspec/changes/**/evidence/worktree-recovery-inventory-v*.json",
        ".mypy_cache/",
        ".pyright/",
        ".basedpyright/",
        ".pyre/",
        ".pytype/",
        ".dmypy.json",
        ".tox/",
        ".nox/",
        ".hypothesis/",
        ".benchmarks/",
        ".coverage",
        ".coverage.*",
        "coverage.xml",
        "coverage.lcov",
        "coverage.json",
        "htmlcov/",
        "junit.xml",
        "junit-*.xml",
        "pytestdebug.log",
        ".idea/",
        ".vscode-test/",
        ".ropeproject/",
        ".history/",
        ".gitnexus/",
        "/AGENTS.md",
        "/CLAUDE.md",
        "*.prof",
        "*.pstats",
        "*.swp",
        "*.swo",
        "*.swn",
        ".*.swp",
        ".*.swo",
        "*~",
        ".#*",
        "\\#*#",
    }
    rules = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert required_rules <= rules

    ignored_paths = [
        ".research-tree/verification-runs/issue-188/group-188-output.txt",
        "openspec/changes/issue-188/evidence/group-188-output.txt",
        "openspec/changes/issue-188/evidence/group-188-output.log",
        "openspec/changes/issue-188/evidence/group-188-receipt.json",
        "openspec/changes/issue-188/evidence/verification-2026-08-14.md",
        "openspec/changes/issue-188/evidence/future-evidence-gaps.json",
        "openspec/changes/issue-188/evidence/integrated-strict-slices.json",
        "openspec/changes/issue-188/evidence/integrated-receipt-byte-preservation-v1.json",
        "openspec/changes/issue-188/evidence/worktree-recovery-inventory-v1.json",
        ".mypy_cache/3.13/cache.json",
        ".pyright/cache.json",
        ".basedpyright/cache.json",
        ".pyre/config",
        ".pytype/cache",
        ".dmypy.json",
        ".tox/py311/log",
        ".nox/tests/log",
        ".hypothesis/constants",
        ".benchmarks/latest.json",
        ".coverage",
        ".coverage.local",
        "coverage.xml",
        "coverage.lcov",
        "coverage.json",
        "htmlcov/index.html",
        "junit.xml",
        "junit-unit.xml",
        "pytestdebug.log",
        ".idea/workspace.xml",
        ".vscode-test/logs/main.log",
        ".ropeproject/config.py",
        ".history/session.json",
        ".gitnexus/index.db",
        "AGENTS.md",
        "CLAUDE.md",
        "session.prof",
        "session.pstats",
        "session.swp",
        "session.swo",
        "session.swn",
        ".session.swp",
        ".session.swo",
        "session~",
        ".#session",
        "#session#",
    ]
    for candidate in ignored_paths:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", "--", candidate],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, candidate


def test_checker_rejects_registry_shape_and_type_drift(tmp_path: Path) -> None:
    registry = write_registry(tmp_path, [entry("src/")])
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["entries"][0].pop("lifecycle")
    registry.write_text(json.dumps(payload), encoding="utf-8")
    missing = checker().validate_repository(tmp_path, registry, tracked_roots={"src", "README.md"})
    assert missing["errors"] == [
        error("unregistered-tracked-root", "README.md", "add a registry entry for this checkout root"),
        error("invalid-registry", "entries[0].lifecycle", "field is required"),
    ]

    typed = report(
        tmp_path,
        [entry("src/", owner="", tracked="yes", distributed="no", canonical_command=1)],
        tracked_roots={"src"},
    )
    assert typed["errors"] == [
        error("invalid-registry", "entries[0].canonical_command", "canonical_command must be a string or null"),
        error("invalid-registry", "entries[0].distributed", "distributed must be a boolean"),
        error("invalid-registry", "entries[0].owner", "owner must be non-empty"),
        error("invalid-registry", "entries[0].tracked", "tracked must be a boolean"),
    ]


def test_checker_uses_schema_constraints_and_rejects_invalid_envelopes(tmp_path: Path) -> None:
    schema = json.loads(
        (ROOT / "openspec/changes/unify-research-runtime-alpha2/schemas/path-registry-v1.json").read_text()
    )
    schema["$defs"]["entry"]["properties"]["asset_class"]["enum"].append("test_only_asset")
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    entries, errors = checker()._load_registry(
        write_registry(tmp_path, [entry("src/", asset_class="test_only_asset")]), schema_path
    )
    assert entries == [entry("src/", asset_class="test_only_asset")]
    assert errors == []

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"schema_version": 1, "entries": [], "unexpected": True}), encoding="utf-8")
    envelope = checker().validate_repository(
        invalid.parent, invalid, tracked_roots=set(), tracked_paths=set(), checkout_roots=set()
    )
    assert envelope["errors"] == [
        error("invalid-registry", "entries", "registry requires at least one entry"),
        error("invalid-registry", "unexpected", "field is not allowed"),
    ]


def test_checker_requires_complete_operator_migration_metadata(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("research-runs/\n", encoding="utf-8")
    result = report(
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
        tracked_roots=set(),
        tracked_paths=set(),
        checkout_roots=set(),
    )
    assert result["errors"] == [
        error("invalid-registry", "entries[0].migration_target", "migration_target must be non-empty")
    ]


def test_checker_enforces_tracked_and_effective_ignore_policy(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text("{}\n", encoding="utf-8")
    missing = report(tmp_path, [local_entry(".codex/")], tracked_roots=set())
    assert missing["errors"] == [
        error("missing-ignore-rule", ".codex/", "registered untracked root requires an exact .gitignore rule")
    ]
    assert missing["protected_local_paths"] == [".codex/"]

    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    (policy_root / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    tracked = report(
        policy_root,
        [local_entry(".agents/")],
        tracked_roots={".agents"},
        tracked_paths={".agents/skills/research-tree/SKILL.md"},
    )
    assert tracked["errors"] == [
        error("tracked-policy-mismatch", ".agents/", "registry marks this path untracked but Git contains it")
    ]

    (policy_root / ".gitignore").write_text(".agents/\n!.agents/\n", encoding="utf-8")
    negated = report(
        policy_root, [local_entry(".agents/")], tracked_roots=set(), tracked_paths=set(), checkout_roots=set()
    )
    assert negated["errors"] == [
        error(
            "missing-effective-ignore-rule", ".agents/", "registered untracked root is not effectively ignored by Git"
        )
    ]
    expected = report(policy_root, [entry("src/")], tracked_roots=set(), tracked_paths=set())
    assert expected["errors"] == [
        error("tracked-policy-mismatch", "src/", "registry marks this path tracked but Git has no files")
    ]


def test_checker_inventories_cache_roots_and_glob_ignores(tmp_path: Path) -> None:
    missing = report(tmp_path, [entry("src/")], tracked_paths=set(), checkout_roots={".pytest_cache"})
    assert ("unregistered-checkout-root", ".pytest_cache") in {
        (item["code"], item["path"]) for item in missing["errors"]
    }

    (tmp_path / ".gitignore").write_text("*.egg-info/\n", encoding="utf-8")
    (tmp_path / "research_tree.egg-info").mkdir()
    valid = report(
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
        tracked_paths=set(),
        checkout_roots={"research_tree.egg-info"},
    )
    assert valid["errors"] == []
    assert valid["protected_local_paths"] == []


def test_checker_skips_ignored_untracked_checkout_roots(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("/AGENTS.md\n", encoding="utf-8")

    ignored = report(
        tmp_path,
        [entry("src/")],
        tracked_paths={"src/module.py"},
        checkout_roots={"src", "AGENTS.md"},
    )
    assert ignored["errors"] == []

    tracked = report(
        tmp_path,
        [entry("src/")],
        tracked_paths={"src/module.py", "AGENTS.md"},
        checkout_roots={"src", "AGENTS.md"},
    )
    assert tracked["errors"] == [
        error("unregistered-tracked-root", "AGENTS.md", "add a registry entry for this checkout root")
    ]


def test_checker_enforces_generated_and_installed_boundaries(tmp_path: Path) -> None:
    (tmp_path / "packages").mkdir()
    invalid = report(tmp_path, [entry("packages/")], tracked_roots={"packages"})
    assert {item["code"] for item in invalid["errors"]} == {"invalid-package-boundary", "invalid-package-command"}

    generated = entry(
        "packages/",
        asset_class="generated_distribution",
        owner="release",
        mutability="rebuildable",
        distributed=True,
        cleanup_safety="safe_rebuild",
        canonical_command="uv run python scripts/build_skill_packages.py",
        lifecycle="generated",
    )
    command = report(tmp_path, [generated | {"canonical_command": "python build.py"}], tracked_roots={"packages"})
    assert [item["code"] for item in command["errors"]] == ["invalid-package-command"]
    overlap = report(
        tmp_path,
        [generated, entry("packages/source/")],
        tracked_roots={"packages"},
        tracked_paths={"packages/source/template.md"},
        checkout_roots={"packages"},
    )
    assert overlap["errors"] == [
        error(
            "overlapping-generated-source-boundary",
            "packages/source/",
            "packages/source/ overlaps generated distribution packages/",
        )
    ]

    drift_root = tmp_path / "drift"
    drift_root.mkdir()
    (drift_root / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    drift = report(
        drift_root,
        [entry("src/"), entry(".agents/", tracked=False)],
        tracked_roots={"src"},
        checkout_roots={"src", "scratch"},
    )
    assert drift["errors"] == [
        error("invalid-installed-boundary", ".agents/", ".agents/ must be installed_copy and generated_or_link"),
        error("unregistered-checkout-root", "scratch", "add a registry entry or relocate this path"),
    ]


def test_checker_rejects_registered_output_under_authoring_source(tmp_path: Path) -> None:
    (tmp_path / "src" / ".research-tree").mkdir(parents=True)
    (tmp_path / "src" / "raw").mkdir()
    (tmp_path / ".gitignore").write_text(".research-tree/\nraw/\n", encoding="utf-8")
    outputs = [
        entry("src/"),
        local_entry(
            ".research-tree/",
            asset_class="runtime_state",
            owner="runtime",
            mutability="append_only_or_rebuildable",
            cleanup_safety="never_delete",
            canonical_command="research-tree run-status",
            lifecycle="runtime",
        ),
        entry(
            "raw/",
            asset_class="historical_or_runtime",
            owner="research",
            mutability="operator_migrated",
            tracked=False,
            cleanup_safety="never_delete",
            canonical_command=None,
            lifecycle="operator-managed",
            migration_target=".research-tree/raw/",
            migration_disposition="manual_classify_and_relocate",
        ),
    ]
    result = report(tmp_path, outputs, tracked_roots={"src"}, tracked_paths={"src/module.py"}, checkout_roots={"src"})
    assert result["errors"] == [
        error(
            "misplaced-runtime-output",
            "src/.research-tree/",
            "runtime state belongs in .research-tree/ via research-tree run-status",
        ),
        error(
            "misplaced-output",
            "src/raw/",
            "historical_or_runtime output belongs at raw/ via the registered migration workflow",
        ),
    ]


def test_migration_plan_reports_collisions_without_mutation(tmp_path: Path) -> None:
    source, target = tmp_path / "research-runs", tmp_path / ".research-tree" / "evaluation-runs"
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
            local_entry(
                ".research-tree/",
                asset_class="runtime_state",
                owner="runtime",
                mutability="append_only_or_rebuildable",
                cleanup_safety="never_delete",
                canonical_command="research-tree run",
                lifecycle="runtime",
            ),
        ],
    )
    result = checker().migration_plan(tmp_path, registry)
    assert result["status"] == "collision_detected"
    assert result["moves_performed"] == 0
    assert result["confirmation_token"]
    assert result["items"] == [
        {
            "source": "research-runs/",
            "destination": ".research-tree/evaluation-runs/",
            "disposition": "manual_relocate_after_audit",
            "collision": True,
        }
    ]
    assert (source / "user-run.json").read_text(encoding="utf-8") == '{"user": true}\n'


def test_workflow_probe_preserves_checkout_and_revalidates_layout(monkeypatch) -> None:
    module = checker()
    successful = module.workflow_probe(ROOT)
    assert successful["status"] == "valid"
    assert successful["repository_status_unchanged"] is True
    assert successful["installed_project_roots"] == [".agents"]

    expected = error("unregistered-checkout-root", ".env", "add a registry entry or relocate this path")
    monkeypatch.setattr(module, "validate_repository", lambda *_args, **_kwargs: {"errors": [expected]})
    invalid = module.workflow_probe(ROOT)
    assert error("post-probe-layout-invalid", ".env", "unregistered-checkout-root") in invalid["errors"]
