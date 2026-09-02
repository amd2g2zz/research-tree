"""Impact-scope audit gate (issue #501 plan §三).

Covers scripts/check_impact_scope.py: impact_scope sidecar validation, the
detect-changes JSON report mode, the documented git-diff fallback mode, and
fail-closed behavior naming every changed path outside the declared scope.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def auditor():
    spec = importlib.util.spec_from_file_location(
        "check_impact_scope", ROOT / "scripts/check_impact_scope.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_scope(root: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "schema": "impact-scope-v1",
        "change": "adopt-two-layer-contract",
        "files": ["src/research_tree/turn_contract.py", "tests/test_turn_contract.py"],
        "symbols": [
            {"name": "verify_traces", "file": "src/research_tree/turn_contract.py", "status": "added"}
        ],
    }
    payload.update(overrides)
    path = root / "impact-scope.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_report(root: Path, entries: list[object], raw: str | None = None) -> Path:
    path = root / "detect-changes-report.json"
    path.write_text(raw if raw is not None else json.dumps({"changed_symbols": entries}), encoding="utf-8")
    return path


def init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    env_repo = subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    assert env_repo.returncode == 0
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "config", "user.email", "audit@example.com"], check=True)
    subprocess.run([*git, "config", "user.name", "audit"], check=True)
    (repo / "src").mkdir()
    (repo / "src" / "in_scope.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], check=True)
    return repo


def commit_file(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", relative], check=True)


# --- sidecar validation -------------------------------------------------------


def test_sidecar_missing_or_wrong_schema_is_rejected(tmp_path: Path) -> None:
    module = auditor()
    with pytest.raises(module.ImpactScopeError, match="schema"):
        module.load_impact_scope(write_scope(tmp_path, schema=None))
    with pytest.raises(module.ImpactScopeError, match="schema"):
        module.load_impact_scope(write_scope(tmp_path, schema="impact-scope-v2"))


def test_sidecar_files_must_be_declared_paths(tmp_path: Path) -> None:
    module = auditor()
    with pytest.raises(module.ImpactScopeError, match="files"):
        module.load_impact_scope(write_scope(tmp_path, files=["", "ok.py"]))
    with pytest.raises(module.ImpactScopeError, match="symbols"):
        module.load_impact_scope(write_scope(tmp_path, symbols=[{"name": "verify_traces"}]))


def test_valid_sidecar_loads(tmp_path: Path) -> None:
    module = auditor()
    scope = module.load_impact_scope(write_scope(tmp_path))
    assert scope["change"] == "adopt-two-layer-contract"
    assert "src/research_tree/turn_contract.py" in scope["files"]


# --- detect-changes report mode ------------------------------------------------


def test_report_mode_passes_when_changed_files_are_declared(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = auditor()
    scope = module.load_impact_scope(write_scope(tmp_path))
    report = write_report(
        tmp_path,
        [{"symbol": "verify_traces", "file": "src/research_tree/turn_contract.py"}],
    )
    result = module.audit_impact_scope(scope, module.changed_files_from_report(report))
    assert result["ok"] is True
    assert result["undeclared"] == []


def test_report_mode_fails_naming_undeclared_files(tmp_path: Path) -> None:
    module = auditor()
    scope = module.load_impact_scope(write_scope(tmp_path))
    report = write_report(
        tmp_path,
        [
            {"symbol": "verify_traces", "file": "src/research_tree/turn_contract.py"},
            {"symbol": "evaluate", "file": "src/research_tree/decision_frame.py"},
        ],
    )
    result = module.audit_impact_scope(scope, module.changed_files_from_report(report))
    assert result["ok"] is False
    assert result["undeclared"] == ["src/research_tree/decision_frame.py"]


def test_report_accepts_string_entries_and_alias_keys(tmp_path: Path) -> None:
    module = auditor()
    scope = module.load_impact_scope(write_scope(tmp_path))
    report = write_report(tmp_path, ["src/research_tree/turn_contract.py"])
    assert module.audit_impact_scope(scope, module.changed_files_from_report(report))["ok"] is True
    aliased = write_report(tmp_path, [{"path": "src/research_tree/turn_contract.py"}], raw=None)
    assert module.audit_impact_scope(scope, module.changed_files_from_report(aliased))["ok"] is True


def test_unrecognized_report_shape_is_rejected_and_named(tmp_path: Path) -> None:
    module = auditor()
    scope = module.load_impact_scope(write_scope(tmp_path))
    broken = write_report(tmp_path, [], raw="{not json")
    with pytest.raises(module.ImpactScopeError, match="detect-changes"):
        module.changed_files_from_report(broken)
    empty = write_report(tmp_path, [], raw=json.dumps({"unrelated": []}))
    with pytest.raises(module.ImpactScopeError, match="detect-changes"):
        module.changed_files_from_report(empty)
    assert scope  # scope loads independently of the report


# --- git-diff fallback mode (documented CLI limitation) ------------------------


def test_diff_mode_passes_when_commits_stay_in_scope(tmp_path: Path) -> None:
    module = auditor()
    repo = init_repo(tmp_path)
    commit_file(repo, "src/in_scope.py", "x = 2\n")
    scope = module.load_impact_scope(write_scope(tmp_path, files=["src/in_scope.py"]))
    changed = module.changed_files_from_diff(repo, "HEAD~1")
    assert changed == ("src/in_scope.py",)
    assert module.audit_impact_scope(scope, changed)["ok"] is True


def test_diff_mode_fails_naming_out_of_scope_commit(tmp_path: Path) -> None:
    module = auditor()
    repo = init_repo(tmp_path)
    commit_file(repo, "src/in_scope.py", "x = 2\n")
    commit_file(repo, "src/out_of_scope.py", "y = 3\n")
    scope = module.load_impact_scope(write_scope(tmp_path, files=["src/in_scope.py"]))
    result = module.audit_impact_scope(scope, module.changed_files_from_diff(repo, "HEAD~2"))
    assert result["ok"] is False
    assert result["undeclared"] == ["src/out_of_scope.py"]


# --- CLI surface ---------------------------------------------------------------


def test_cli_requires_exactly_one_change_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = auditor()
    scope = write_scope(tmp_path)
    with pytest.raises(SystemExit) as neither:
        module.main(["--impact-scope", str(scope)])
    assert neither.value.code == 2
    report = write_report(tmp_path, ["src/research_tree/turn_contract.py"])
    with pytest.raises(SystemExit) as both:
        module.main(
            [
                "--impact-scope",
                str(scope),
                "--detect-changes-report",
                str(report),
                "--diff-base",
                "dev",
            ]
        )
    assert both.value.code == 2


def test_cli_exit_codes_and_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = auditor()
    scope = write_scope(tmp_path)
    passing = write_report(tmp_path, [{"file": "src/research_tree/turn_contract.py"}])
    assert module.main(["--impact-scope", str(scope), "--detect-changes-report", str(passing)]) == 0
    first = capsys.readouterr().out
    assert json.loads(first)["ok"] is True
    assert module.main(["--impact-scope", str(scope), "--detect-changes-report", str(passing)]) == 0
    assert capsys.readouterr().out == first  # deterministic
    failing = write_report(tmp_path, [{"file": "src/research_tree/decision_frame.py"}])
    assert module.main(["--impact-scope", str(scope), "--detect-changes-report", str(failing)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["undeclared"] == ["src/research_tree/decision_frame.py"]
