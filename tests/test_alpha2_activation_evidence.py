from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_activation_status_exposes_four_non_conflated_evidence_states(tmp_path) -> None:
    from research_tree.skill_setup import activation_status

    result = activation_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )
    states = result["installations"][0]["evidence_states"]
    assert states["discovery"]["status"] == "pass"
    assert states["current_installation"]["status"] == "fail"
    assert states["live_body_injection"]["status"] == "unknown"
    assert states["post_activation_behavior"]["status"] == "unknown"
    assert states["live_body_injection"]["cannot_be_inferred_from"] == [
        "SKILL.md file read",
        "package-only activation receipt",
    ]


def test_current_install_does_not_claim_live_activation(tmp_path) -> None:
    from research_tree.skill_setup import activation_status, install_skill

    install_skill(
        ("claude",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )
    result = activation_status(
        ("claude",),
        source=ROOT,
        scope="user",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )
    states = result["installations"][0]["evidence_states"]
    assert states["current_installation"]["status"] == "pass"
    assert states["live_body_injection"]["status"] == "unknown"
    assert result["installations"][0]["activation_status"] == "awaiting_live_probe"


def test_native_probe_records_unavailable_evidence(tmp_path, monkeypatch) -> None:
    from research_tree import skill_setup

    monkeypatch.setattr(skill_setup.shutil, "which", lambda _name: None)
    unavailable = skill_setup.native_activation_probe("hermes", cwd=tmp_path)
    assert unavailable == {
        "host": "hermes",
        "status": "unavailable",
        "reason": "host_cli_not_found",
        "command_name": "hermes",
        "expected_response": "research-tree activation: RT-ACTIVE-V1-HERMES",
    }


@pytest.mark.parametrize(
    ("host", "expected_command", "sentinel"),
    [
        (
            "codex",
            ["codex", "exec", "$research-tree --activation-probe"],
            "RT-ACTIVE-V1-CODEX",
        ),
        (
            "claude",
            [
                "claude",
                "-p",
                "/research-tree --activation-probe",
                "--output-format",
                "text",
            ],
            "RT-ACTIVE-V1-CLAUDE",
        ),
        (
            "hermes",
            [
                "hermes",
                "-z",
                "/research-tree --activation-probe",
                "--skills",
                "research-tree",
            ],
            "RT-ACTIVE-V1-HERMES",
        ),
    ],
)
def test_native_probe_records_exact_host_command_and_output(
    tmp_path: Path,
    host: str,
    expected_command: list[str],
    sentinel: str,
) -> None:
    from research_tree import skill_setup

    def exact_runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"research-tree activation: {sentinel}\n",
            stderr="",
        )

    passed = skill_setup.native_activation_probe(
        host,
        cwd=tmp_path,
        executable=expected_command[0],
        runner=exact_runner,
    )
    assert passed["status"] == "passed"
    assert passed["command"] == expected_command
    assert passed["exact_output"] == f"research-tree activation: {sentinel}"


def test_windows_command_shim_uses_comspec_without_shell_true(monkeypatch) -> None:
    from research_tree import skill_setup

    monkeypatch.setenv("ComSpec", r"C:\Windows\System32\cmd.exe")
    command = skill_setup._native_probe_command(
        "codex", r"C:\Tools\codex.CMD", windows=True
    )

    assert command == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        r"C:\Tools\codex.CMD",
        "exec",
        "$research-tree --activation-probe",
    ]


def test_windows_command_shim_rejects_non_cmd_comspec(monkeypatch) -> None:
    from research_tree import skill_setup

    monkeypatch.setenv("ComSpec", r"C:\Tools\Terminal.exe")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")

    command = skill_setup._native_probe_command(
        "codex", r"C:\Tools\codex.CMD", windows=True
    )

    assert command[0] == r"C:\Windows\System32\cmd.exe"


def test_native_probe_rejects_non_exact_output(tmp_path: Path) -> None:
    from research_tree import skill_setup

    def noisy_runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="prefix research-tree activation: RT-ACTIVE-V1-CODEX\n",
            stderr="",
        )

    result = skill_setup.native_activation_probe(
        "codex", cwd=tmp_path, executable="codex", runner=noisy_runner
    )
    assert result["status"] == "failed"
    assert result["exact_output"].startswith("prefix ")


def test_native_probe_hashes_stderr_without_persisting_raw_diagnostics(
    tmp_path: Path,
) -> None:
    from research_tree import skill_setup

    def diagnostic_runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="provider session secret-token",
        )

    result = skill_setup.native_activation_probe(
        "codex", cwd=tmp_path, executable="codex", runner=diagnostic_runner
    )

    assert "secret-token" not in str(result)
    assert "stderr_excerpt" not in result
    assert result["stderr_present"] is True
    assert result["stderr_bytes"] == len("provider session secret-token".encode("utf-8"))
    assert len(result["stderr_sha256"]) == 64


def test_live_probe_advances_only_live_injection_state(
    tmp_path: Path, monkeypatch
) -> None:
    from research_tree import skill_setup

    skill_setup.install_skill(
        ("codex",),
        source=ROOT,
        scope="user",
        mode="copy",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
    )
    receipt = {
        "host": "codex",
        "status": "passed",
        "command": ["codex", "exec", "$research-tree --activation-probe"],
        "returncode": 0,
        "exact_output": "research-tree activation: RT-ACTIVE-V1-CODEX",
        "expected_response": "research-tree activation: RT-ACTIVE-V1-CODEX",
        "stderr_excerpt": "",
    }
    monkeypatch.setattr(skill_setup, "native_activation_probe", lambda *_args, **_kwargs: receipt)

    result = skill_setup.activation_status(
        ("codex",),
        source=ROOT,
        scope="user",
        home=tmp_path / "home",
        project_root=tmp_path / "project",
        run_native_probes=True,
    )
    installation = result["installations"][0]

    assert installation["activation_status"] == "live_activation_verified"
    assert installation["evidence_states"]["live_body_injection"]["status"] == "pass"
    assert installation["evidence_states"]["post_activation_behavior"]["status"] == "unknown"
