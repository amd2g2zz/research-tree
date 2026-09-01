"""Issue #292 gate 4: three-host operator rehearsal — user-facing output contracts.

The rehearsal ran install -> doctor -> status-current -> run -> resume ->
status -> verify through the real CLI for codex, claude, and hermes against
temp simulated host homes.  These tests pin the operator-facing fixes the
rehearsal exposed:

1. doctor must not report a phantom ``claude-code`` installation host when the
   operator selected codex or hermes (false positive found in rehearsal).
2. doctor must keep the ``skill_setup`` digest/hook bookkeeping internal
   (schema hiding) and surface only operator-readable fields.
3. install must not echo the internal ``payload_files`` manifest.
4. run/resume must not echo the internal hook event ``record_path``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from research_tree import cli

ROOT = Path(__file__).resolve().parents[1]
REHEARSAL_RUN_OPTIONS = (
    "--outcome",
    "summarize the governance state of the demo project",
    "--scope",
    "this demo workspace only",
    "--authority",
    "operator authorized a read-only rehearsal",
    "--success-oracle",
    "an independent receipt confirms the rehearsal summary",
)
USER_FACING_INSTALLATION_FIELDS = {
    "host",
    "scope",
    "status",
    "reason",
    "target",
    "discovery",
}


def _json_output(capsys: pytest.CaptureFixture[str]) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out.strip()
    open_match = re.search(r"<rt:(?:tool-output|error)[^>]*>", out)
    assert open_match, out
    close = "</rt:tool-output>" if "<rt:tool-output" in out else "</rt:error>"
    return json.loads(out[open_match.end() : out.rindex(close)])


def _install_arguments(host: str, tmp_path: Path) -> list[str]:
    codex_home = ["--codex-home", str(tmp_path / "codex-home")] if host == "codex" else []
    return [
        "install",
        "--host",
        host,
        "--mode",
        "copy",
        "--scope",
        "user",
        "--source",
        str(ROOT),
        "--home",
        str(tmp_path / "home"),
        *codex_home,
    ]


def _doctor_arguments(host: str, tmp_path: Path) -> list[str]:
    codex_home = ["--codex-home", str(tmp_path / "codex-home")] if host == "codex" else []
    return [
        "doctor",
        "--host",
        host,
        "--source",
        str(ROOT),
        "--home",
        str(tmp_path / "home"),
        *codex_home,
    ]


@pytest.mark.parametrize("host", ("codex", "claude", "hermes"))
def test_copy_install_then_doctor_status_current_and_no_phantom_host_entry(
    host: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """copy-install -> doctor reports exactly the selected host as current."""

    assert cli.main(_install_arguments(host, tmp_path)) == 0
    installed = _json_output(capsys)
    assert installed["status"] == "installed"
    assert installed["readiness"] == {"ready": True, "failure_reasons": []}

    assert cli.main(_doctor_arguments(host, tmp_path)) == 0
    doctor = _json_output(capsys)
    assert doctor["status"] == "healthy"
    assert doctor["result"]["installation"]["state"] == "ready"
    assert set(doctor["result"]["installation"]["hosts"]) == {host}, doctor["result"]["installation"]["hosts"]


def test_doctor_all_hosts_reports_all_selected_hosts_without_phantom_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--host all`` echoes the full registry; no phantom claude-code key."""

    home = tmp_path / "shared-home"
    for host in ("codex", "claude", "hermes"):
        arguments = [
            "install",
            "--host",
            host,
            "--mode",
            "copy",
            "--scope",
            "user",
            "--source",
            str(ROOT),
            "--home",
            str(home),
        ]
        assert cli.main(arguments) == 0
        _json_output(capsys)

    arguments = [
        "doctor",
        "--host",
        "all",
        "--source",
        str(ROOT),
        "--home",
        str(home),
    ]
    assert cli.main(arguments) == 0
    doctor = _json_output(capsys)
    assert set(doctor["result"]["installation"]["hosts"]) == {"codex", "claude", "hermes"}
    assert {item["host"] for item in doctor["result"]["installations"]} == {"codex", "claude", "hermes"}


@pytest.mark.parametrize("host", ("codex", "claude", "hermes"))
def test_doctor_installations_surface_is_user_readable_without_internal_bookkeeping(
    host: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Digests, hook bookkeeping, and activation placeholders stay internal."""

    assert cli.main(_install_arguments(host, tmp_path)) == 0
    _json_output(capsys)
    assert cli.main(_doctor_arguments(host, tmp_path)) == 0
    doctor = _json_output(capsys)

    installations = doctor["result"]["installations"]
    assert installations, doctor["result"]
    for installation in installations:
        assert set(installation) == USER_FACING_INSTALLATION_FIELDS
        assert installation["status"] == "current"
        assert installation["host"] == host


@pytest.mark.parametrize("host", ("codex", "claude", "hermes"))
def test_install_output_hides_internal_payload_manifest(
    host: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The packaged-file manifest is an internal schema detail, not user output."""

    assert cli.main(_install_arguments(host, tmp_path)) == 0
    installed = _json_output(capsys)

    for installation in installed["result"]["installations"]:
        assert "payload_files" not in installation
        assert "skill_source" not in installation
        assert "package" not in installation
        assert installation["action"] == "installed"
        assert installation["status"] == "current"


@pytest.mark.parametrize("host", ("codex", "claude", "hermes"))
def test_run_and_resume_output_hides_internal_hook_record_path(
    host: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """run/resume report hook availability without the internal event ledger path."""

    assert cli.main(_install_arguments(host, tmp_path)) == 0
    _json_output(capsys)

    identity = [
        "--workspace",
        str(tmp_path / "workspace"),
        "--host",
        host,
        "--project-id",
        f"demo-project-{host}",
        "--run-id",
        f"demo-run-{host}",
    ]
    assert cli.main(["run", *identity, *REHEARSAL_RUN_OPTIONS]) == 0
    created = _json_output(capsys)
    assert created["status"] == "prepared"
    assert created["result"]["hook_probe"] == {"status": "available"}

    assert cli.main(["resume", *identity]) == 0
    resumed = _json_output(capsys)
    assert resumed["status"] == "resumed"
    assert resumed["result"]["hook_probe"] == {"status": "available"}
