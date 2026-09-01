"""Issue #328: heterogeneous multi-host install plans are per-host, not all-or-nothing."""

from __future__ import annotations

import re

from research_tree.skill_setup import (
    plan_heterogeneous_install,
)


def test_mixed_scope_project_skips_hermes_with_external_dirs_guidance(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    plan = plan_heterogeneous_install(
        hosts=("codex", "claude", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
    )

    by_host = {entry["host"]: entry for entry in plan["entries"]}
    assert by_host["codex"]["action"] == "install"
    assert by_host["claude"]["action"] == "install"
    assert by_host["hermes"]["action"] == "skipped"
    assert by_host["hermes"]["required_config"]
    snippet = by_host["hermes"]["required_config"]
    snippet_yaml = snippet["yaml"] if isinstance(snippet, dict) else str(snippet)
    assert "external_dirs" in snippet_yaml
    # The guidance must point at the machine-readable snippet (idempotent key path)
    snippet_yaml = snippet["yaml"] if isinstance(snippet, dict) else str(snippet)
    assert "skills:" in snippet_yaml and "external_dirs" in snippet_yaml


def test_plan_three_phase_dry_run_returns_action_skips_required_config(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    plan = plan_heterogeneous_install(
        hosts=("codex", "claude", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
        dry_run=True,
    )
    for entry in plan["entries"]:
        assert entry["action"] in {"install", "skipped", "current", "conflict"}
        assert "host" in entry and "target" in entry and "scope" in entry
        assert "rollback_boundary" in entry and "discovery" in entry


def test_status_reports_per_host_independently(tmp_path) -> None:
    from research_tree.skill_setup import installation_status_per_host

    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    status = installation_status_per_host(
        hosts=("codex", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=tmp_path,
    )
    assert "hosts" in status and isinstance(status["hosts"], dict)
    assert set(status["hosts"]) == {"codex", "hermes"}
    # Aggregate does not hide partial readiness
    assert "aggregate_ready" in status
    for host, entry in status["hosts"].items():
        assert "ready" in entry and "reason" in entry


def test_unsupported_combination_is_plan_entry_not_exception(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    # Hermes on project scope MUST NOT raise — it must produce a skipped entry
    # with required_config guidance (issue #328 acceptance).
    plan = plan_heterogeneous_install(
        hosts=("hermes",),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
    )
    assert plan["entries"][0]["host"] == "hermes"
    assert plan["entries"][0]["action"] == "skipped"


def test_hermes_external_dirs_snippet_is_idempotent(tmp_path) -> None:
    from research_tree.skill_setup import hermes_external_dirs_snippet

    snippet = hermes_external_dirs_snippet(source_parent=tmp_path / "src")
    snippet_yaml = snippet["yaml"] if isinstance(snippet, dict) else snippet
    assert isinstance(snippet_yaml, str)
    # Apply twice → no diff
    merged_a = _apply_yaml_fragment("external_dirs: [/tmp/old]", snippet_yaml)
    merged_b = _apply_yaml_fragment(merged_a, snippet_yaml)
    assert merged_a == merged_b, "external_dirs snippet must be idempotent"
    # Preserves unrelated keys
    unrelated = _apply_yaml_fragment("garbage: keep me\nzoom: true", snippet_yaml)
    assert "zoom: true" in unrelated and "garbage: keep me" in unrelated


def _apply_yaml_fragment(existing: str, fragment: str) -> str:
    """Tiny ad-hoc merge for idempotency: append external_dirs entries, never overwrite unrelated keys."""

    existing_entries = re.findall(r"external_dirs:\s*\[([^\]]*)\]", existing)
    new_entries = re.findall(r"external_dirs:\s*\[([^\]]*)\]", fragment)
    seen: set[str] = set()
    combined: list[str] = []
    for raw in existing_entries + new_entries:
        for item in re.split(r",\s*", raw):
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                combined.append(item)
    lines = existing.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("external_dirs:"):
            skip = True
            out.append(f"external_dirs: [{', '.join(combined)}]")
        elif skip and stripped.startswith("-"):
            continue
        elif skip and stripped and not stripped.startswith("-"):
            skip = False
            out.append(line)
        else:
            out.append(line)
    if not any(line.startswith("external_dirs:") for line in out):
        out.append(f"external_dirs: [{', '.join(combined)}]")
    return "\n".join(out)


def test_one_host_conflict_does_not_fail_plan_for_others(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    # Pre-create conflicting user-owned file at the resolved claude project target
    conflict_target = project.expanduser().resolve() / ".claude" / "skills" / "research-tree"
    conflict_target.mkdir(parents=True, exist_ok=True)
    (conflict_target / "SKILL.md").write_text("user-owned\n", encoding="utf-8")
    plan = plan_heterogeneous_install(
        hosts=("codex", "claude", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
    )
    by_host = {entry["host"]: entry for entry in plan["entries"]}
    assert by_host["codex"]["action"] == "install"
    assert by_host["claude"]["action"] == "conflict"
    assert by_host["hermes"]["action"] == "skipped"
    assert not plan["aggregate_ready"]


def test_rollback_boundary_is_per_host_target_path(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    plan = plan_heterogeneous_install(
        hosts=("codex", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
    )
    for entry in plan["entries"]:
        if entry["action"] in {"install", "conflict"}:
            assert entry["rollback_boundary"] == entry["target"]
        elif entry["action"] == "skipped":
            assert entry["rollback_boundary"] == "n/a"


def test_unavailable_home_does_not_crash_plan(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    # Home that doesn't exist — user-scope target resolution still produces a valid path
    plan = plan_heterogeneous_install(
        hosts=("codex",),
        source=repo,
        scope="user",
        home=tmp_path / "missing-home",
        project_root=project,
    )
    assert plan["entries"][0]["action"] == "install"
    assert "missing-home" in plan["entries"][0]["target"]


def test_repeated_invocation_is_idempotent(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    plan_a = plan_heterogeneous_install(
        hosts=("codex", "claude", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
    )
    plan_b = plan_heterogeneous_install(
        hosts=("codex", "claude", "hermes"),
        source=repo,
        scope="project",
        home=home,
        project_root=project,
    )
    by_a = {entry["host"]: entry for entry in plan_a["entries"]}
    by_b = {entry["host"]: entry for entry in plan_b["entries"]}
    for host in by_a:
        assert by_a[host]["target"] == by_b[host]["target"], f"{host} target drifted between calls"
        assert by_a[host]["action"] == by_b[host]["action"]
